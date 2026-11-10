# 問い合わせフォーム: Cloud Run functions HTTPエントリポイント設計

作成日: 2026-11-10(フェーズ109)

## 1. 背景・残っていた欠落

- フェーズ108は`inquiry_form_intake.handle_inquiry_form_submission()`(入力検証・
  `inquiry`ドキュメント組み立て・idempotency_key_index結線)まで実装したが、次回候補(2)として
  「Cloud Run functionsの実HTTPSトリガーから`handle_inquiry_form_submission()`を実際に呼び出し、
  戻り値の`document`が`None`でない場合のみFirestore `inquiry`コレクションへ`add()`する結線」を
  残していた。本ドキュメントはこの欠落を埋める。
- `runtime-dependency-switching-design.md`(フェーズ64)3節が確定した本venture全体のCloud Run
  functions境界は4関数: `submit_event_form`・`handle_stripe_webhook`・`get_result_page`・
  `submit_inquiry`。本ドキュメントは`submit_inquiry`関数の実装にあたる。
  (なお調査の結果、4関数のうちいずれについても`functions_framework`の`main(request)`薄配線が
  本venture配下に1件も実装されていないことを確認した。他3関数の同種配線は本ドキュメントの
  対象外とし、次回候補として残す。)

## 2. 認証方式: 共有シークレット不要

- aircon-pasha/application-form-submission-http-entry-point-design.md(フェーズ316)は
  Google Apps Script(GAS)がWebhook中継する構成のため共有シークレットヘッダを要求したが、
  本ventureの`submit_inquiry`は`web-form-ui-design.md`(フェーズ65)1節が確定した通り
  「エンドユーザーのブラウザから直接呼ばれるHTTPSトリガー」であり、GASのような中間サーバーを
  介さない。ブラウザ側に共有シークレットを埋め込むことは秘匿性が無く無意味なため、
  `submit_event_form`・`get_result_page`と同様、本関数も共有シークレット検証を行わない
  (Firestoreセキュリティルール側で書き込み内容を制限する方針は別途`firestore.rules`が担う)。

## 3. リクエスト・レスポンス形状

- リクエスト: `POST`、JSON本文(`inquiry-form-ui-draft.md`フェーズ52のフォーム項目)
  ```json
  {
    "draft_id": "draft-abc123",
    "customer_email": "customer@example.com",
    "category": "メール未着",
    "detail": "確認メールが届きません",
    "idempotency_key": "client-generated-uuid4"
  }
  ```
  `idempotency_key`は`web-form-ui-design.md`2節の通り、送信ボタン押下時にクライアント側が
  生成し、再試行時は同じキーを使い回す(省略可、省略時は`inquiry_form_intake.py`の既存の
  後方互換動作により常に新規`inquiry_id`を発行する)。
- レスポンス(すべてJSON本文):
  - 200: `{"ok": true, "inquiry_id": "<uuid4>", "error": null}`
    (新規受付、または同一`idempotency_key`での再送検知による既存`inquiry_id`の返却の
    いずれも200とする。呼び出し元ブラウザにとっては「受付済み」という結果に差はないため。)
  - 400: `{"ok": false, "inquiry_id": null, "error": "..."}`
    (JSON本文が不正〈パース不能〉、または必須項目〈`draft_id`・`customer_email`・
    `category`〉の欠落。`inquiry_form_intake.handle_inquiry_form_submission()`が返す
    `message`をそのまま使う。)
  - フロントエンド側の技術的エラーコードを表示しない方針(`web-form-ui-design.md`3節)は
    本エントリポイントの対象外(本ドキュメントはサーバー側の配線のみを扱う)。

## 4. プロトタイプ実装方針

- `prototype/inquiry_collection_store.py`(新規)に、実クラウド接続なしで検証可能な
  `InquiryCollectionProtocol`/`InMemoryInquiryCollection`を実装する。Firestore `inquiry`
  コレクションへの書き込みを`add(inquiry_id, document)`の最小インターフェースとして抽象化する
  (`firestore_idempotency_key_index_adapter.py`と同じ「実SDKをimportせず最小インターフェースに
  依存する」方針)。`inquiry_id`はドキュメントID(`inquiry_form_intake.py`が発行)、
  `document`は`build_inquiry_document()`の戻り値をそのまま渡す。
- `prototype/inquiry_form_http_entry.py`(新規)に、`receive_inquiry_form_submission(raw_body,
  *, collection, idempotency_store=None, now=None) -> InquiryFormReceiveResult`を実装する。
  - `cloud_function_webhook.receive_webhook()`と同じ「本体はbytes/dictのみを扱い実クラウド
    接続なしでテスト可能、`main(request)`だけが実`functions_framework`リクエストオブジェクトを
    扱う薄い配線」構成を踏襲する(薄い配線側は`cloud_function_submit_inquiry.py`)。
  - JSONパース → `inquiry_form_intake.handle_inquiry_form_submission()`への委譲 →
    戻り値の`document`が`None`でない場合のみ`collection.add(inquiry_id, document)`を呼ぶ、
    という順序を1関数に結線する。
  - `created_at`(ドキュメント本体の文字列フィールド、`handle_inquiry_form_submission()`の
    必須引数)は本関数が`now.isoformat()`で注入する(呼び出し側がCloud Run functionsの
    HTTPSトリガーである想定、`inquiry_form_intake.py`冒頭の位置づけどおり)。
- `prototype/cloud_function_submit_inquiry.py`(新規)に薄い`main(request)`を実装する。
  `request.get_data()`でbytesを取得し、`receive_inquiry_form_submission()`に委譲する。
  実Firestore接続は実GCPプロジェクト作成(pending-approval.md記載、承認待ち)後の課題のため、
  現時点では`InMemoryInquiryCollection`・`InMemoryIdempotencyKeyIndexStore`を返す
  `get_submit_inquiry_runtime_dependencies()`を使う(他Cloud Function同様、実Firestore接続後は
  この関数の中身を差し替えるだけで`main()`・`receive_inquiry_form_submission()`双方を
  変更せずに接続できる)。

## 5. 次回候補

- 承認待ち事項(実GCPプロジェクト作成等)がオーナーから承認された場合、
  `get_submit_inquiry_runtime_dependencies()`を実Firestoreクライアントを返すように差し替える。
- 残り3関数(`submit_event_form`・`handle_stripe_webhook`・`get_result_page`)についても
  同種の`functions_framework`薄配線(`main(request)`)が本venture配下に1件も実装されていない
  ことを本フェーズで確認した。本ドキュメントと同型の設計・実装を順次行う。
- 他venture・アイデア領域の前進。
