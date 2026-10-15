# 申込フォーム提出フロー: Cloud Functions HTTPエントリポイント設計

作成日: 2026-10-15(フェーズ316)

## 1. 背景・残っていた欠落

- course-set-pashaフェーズ295は、同venture内で「`handle_form_submission_with_linking_
  code()`(ロジック本体)は実装・テスト済みだったが、それを実際のGAS Webhook POST
  リクエストから呼び出すCloud Functions HTTPエントリポイント自体が一度も実装されていない」
  という欠落を発見・是正し(`application_form_submission_http_entry.py`・
  `cloud_function_application_form_submission.py`を新規実装)、次回候補(2)として
  「同種の欠落が他venture(aircon-pasha・kura-pasha・line-reservation-ai)にも無いかの
  横展開調査」を残した。
- 本フェーズでこの横展開調査を行った結果、kura-pasha・line-reservation-aiはいずれも
  Googleフォームによる申込チャネルを持たない(LINE友だち追加起点のフローのみ)ため本件は
  該当しないが、aircon-pashaには同型の欠落がそのまま存在することを確認した。
  - `user-account-linking-design.md`(フェーズ107)が設計し、`user_id_linking.
    issue_linking_code_on_form_submission()`(フェーズ113実装済み)・
    `application_form_submission_flow.handle_form_submission()`(フェーズ279実装済み、
    GAS Webhookペイロードの検証→連携コード発行への委譲ロジック本体)までは完了していた。
  - しかし他の全Cloud Function(`cloud_function_webhook.py`・
    `cloud_function_run_daily_checks.py`等)が備える「実`functions_framework`リクエスト
    オブジェクトを受け取る薄い`main(request)`配線」が、申込フォーム提出経路にだけ
    存在せず、`handle_form_submission()`を実際のGAS Webhook POSTリクエストから
    呼び出す経路が未設計のまま放置されていた(course-set-pashaフェーズ295と同種の
    欠落が本ventureにも残っていた)。本ドキュメントはこの欠落を埋める。

## 2. course-set-pasha版との向きの違い

- course-set-pashaはフォーム入力が「LINE友だち追加時に発行済みの連携コード」を受け取って
  `user_id`へ解決する向きのため、HTTPレスポンスはフォーム入力の成否(`{"ok", "error"}`)
  のみを返せば足りた。
- 本ventureはuser-account-linking-design.md 1節の通り紐付けの向きが逆(フォーム送信が
  連携コードの発行契機)のため、HTTPレスポンスには発行した連携コード自体
  (`linking_code`)を含める必要がある。design 2節が想定する「フォーム送信完了画面
  (サンクスページ)への表示」「入力済みメールアドレス宛への確認メール送信」のいずれも、
  GAS側が連携コードの値を受け取れなければ実現できないため。

## 3. 認証方式(共有シークレット)

- course-set-pashaフェーズ295と同じ方式を採用する。Google Apps Script(GAS)の
  `UrlFetchApp.fetch()`にはLINE/Stripeのような標準署名方式が無いため、GAS側
  `PropertiesService`(スクリプトプロパティ、GASエディタ上で手動設定・コードに
  ハードコードしない)に保存した共有シークレット文字列を、GASが
  `UrlFetchApp.fetch(url, {headers: {"X-Form-Webhook-Secret": secret}, ...})`で
  リクエストヘッダに載せて送信し、Cloud Function側は環境変数
  `FORM_WEBHOOK_SHARED_SECRET`と比較する。
  - 比較は`hmac.compare_digest()`でタイミング攻撃を避ける(定数時間比較)。
  - 一致しない場合は401を返し、`handle_form_submission()`へは処理を進めない
    (ペイロード検証より認証を先に行う)。
  - `expected_secret`が空文字列(環境変数未設定)の場合は、course-set-pasha版と同じく
    安全側に倒して常に401とする(空文字列同士の一致で無認証運用になる事故を避ける)。
  - シークレット自体の値の生成・設定作業(GAS Script Properties設定・Cloud Functions
    環境変数設定)は外部サービス側の実設定操作であり、Googleフォーム作成+GAS Webhook
    設定自体(pending-approval.md 2026-08-23 04:00 UTC記載の承認待ち事項)の範囲内で
    オーナー承認後に行う。本ドキュメント・実装はロジック設計のみで新たな承認待ち事項を
    追加するものではない。

## 4. リクエスト・レスポンス形状

- リクエスト: `POST`、JSON本文
  ```json
  {
    "form_submission_id": "form-123",
    "business_name": "テストクリーニング",
    "business_type": "独立系",
    "email": "owner@example.com"
  }
  ```
  ヘッダ: `X-Form-Webhook-Secret: <共有シークレット>`
  `form_submission_id`はGAS側`e.response.getId()`(Googleフォームの個別回答ID)を
  そのまま使う想定(design 2節`pending_links`の必須フィールドと一致させる)。
- レスポンス(すべてJSON本文):
  - 200: `{"ok": true, "linking_code": "<6文字のコード>", "error": null}`
  - 401: `{"ok": false, "linking_code": null, "error": "..."}`
    (`X-Form-Webhook-Secret`ヘッダ欠落または不一致)
  - 400: `{"ok": false, "linking_code": null, "error": "..."}`
    (JSON本文が不正〈パース不能〉、または必須フィールドの検証エラー。
    `handle_form_submission()`が返すエラー文言をそのまま使う)
- GAS側は200の場合に`linking_code`を取り出し、サンクスページ表示用の文字列組み立て・
  確認メール送信(いずれも実装は別途、オーナー承認後)に使う。401/400の場合は
  course-set-pasha版と同じくログに残すのみで、フォーム回答者への追加のエラー表示は
  行わない(Googleフォーム自体の標準完了画面は変更しない、MVPの割り切り)。

## 5. プロトタイプ実装方針

- `application_form_submission_http_entry.py`(新規)に、実クラウド接続なしで検証可能な
  `receive_application_form_submission(raw_body, secret_header, expected_secret, store,
  now, rng) -> FormSubmissionReceiveResult`を実装する。`cloud_function_webhook.
  receive_webhook()`と同じ「本体はdict/bytesのみを扱いテスト可能、`main(request)`だけが
  実`functions_framework`オブジェクトに依存する」構成を踏襲する。`user_id_linking.py`・
  `application_form_submission_flow.py`の双方に依存するため、course-set-pasha版と同じ
  理由(循環import回避)でどちらのモジュールにも追記せず新規ファイルとした。
- `cloud_function_application_form_submission.py`(新規)に薄い`main(request)`を実装する。
  `request.get_data()`でbytesを取得、`request.headers.get("X-Form-Webhook-Secret")`で
  ヘッダを取得、環境変数`FORM_WEBHOOK_SHARED_SECRET`(未設定時は空文字列、
  `cloud_function_webhook.main()`の`LINE_CHANNEL_SECRET`未設定時と同じ安全側挙動)を
  読み、`receive_application_form_submission()`に委譲する。
- 実Firestore接続(`pending_links`コレクション)は他Cloud Function同様、実GCPプロジェクト・
  Googleフォーム+GAS Webhook自体がオーナー承認待ちのため、現時点では
  `InMemoryLinkingCodeStore`を返す`get_application_form_submission_runtime_
  dependencies()`を使う。乱数生成(`rng`)も本番では`random.Random()`(シード無し)を
  使う想定だが、現時点ではテストと同じ`random.Random`インスタンスを都度生成する
  (呼び出しをまたいだ再現性は不要、`issue_linking_code_on_form_submission()`の
  重複判定が実質的な一意性を保証する)。

## 6. GAS側スクリプト草案

- 実際のGoogleフォーム作成・GASプロジェクトの作成・デプロイ自体はオーナー承認待ち
  (pending-approval.md 2026-08-23 04:00 UTC記載の承認待ち事項)だが、承認後すぐに
  貼り付けられるよう、`onFormSubmit`トリガーで呼ばれる想定のGAS(`.gs`、JavaScript方言)
  コード草案を`gas-script-draft.md`に記録した(コード自体は実行・デプロイされておらず、
  リポジトリ内のテキストとして保持するのみ)。

## 7. 次回候補

- 承認待ち事項(launch-readiness-checklist.md相当、pending-approval.md参照)がオーナーから
  承認された場合、実シークレット値の環境変数設定・GASへの貼り付けから着手する。
- GAS側が受け取った`linking_code`をサンクスページにどう表示するか(Googleフォーム標準の
  完了画面はGAS onFormSubmitトリガー〈送信後に非同期実行〉からは動的に書き換えられない
  制約があるため、確認メール送信〈design 2節〉を主経路とするか、Googleフォームを
  埋め込んだ独自LPに切り替えるかの検討。実デプロイ時の課題として残す)。
- 他venture・アイデア領域の前進。
