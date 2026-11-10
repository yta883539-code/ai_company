# `submit_event_form` Cloud Run functions HTTPエントリポイント設計

README.mdフェーズ109の次回候補(2)「残り3関数(`submit_event_form`・
`handle_stripe_webhook`・`get_result_page`)についても`submit_inquiry`と同型の
`main(request)`薄配線を設計・実装する」のうち、`submit_event_form`分に対応する。

inquiry-form-http-entry-point-design.md(フェーズ109)と同じ方針(本体はbytes/dictのみを
扱い実クラウド接続なしでテスト可能、`main(request)`だけが実`functions_framework`
リクエストオブジェクトを扱う薄い配線)を踏襲する。

## 1. 位置づけ

- 業務ロジック自体は`checkout_session_creation.create_checkout_session_for_event_memo()`
  (フェーズ105〜67、必須項目チェック〜draft作成〜Stripe Checkout Session作成までを
  結ぶ1本のエントリポイント関数)として既に実コード化済みであり、本設計は「Webフォームの
  生POSTリクエスト(bytes)をどう受け取り、`create_checkout_session_for_event_memo()`の
  戻り値(`CheckoutSessionCreationResult`)をどうHTTPレスポンスに変換するか」のみを
  新規に扱う。

## 2. リクエスト・レスポンス形状

- リクエスト: Webフォームが送信するJSON本文(`capacity`・`entry_exit_points`・
  `admission_type`・`staffing`・`outdoor_queue`・任意で`idempotency_key`)。
  `inquiry_form_http_entry.py`と同じく、JSONパース失敗時・本文がdictでない場合は400を
  返す(`{"ok": false, "error": "..."}`)。
- `create_checkout_session_for_event_memo()`の`outcome`に応じて分岐する:
  - `outcome="insufficient_input"`: `insufficient_input_response`
    (schema/output.schema.jsonの形に沿った`status="insufficient_input"`応答、
    form_submission_intake.build_insufficient_input_response()が組み立てた dict)を
    そのまま200で返す。主催者の入力不備は正常系の応答(フォーム側がその場で再入力を
    促す画面に使う)であり、リクエスト自体は正しく処理できているため400にはしない
    (`inquiry_form_http_entry.py`のmissing_fields応答が400である理由(問い合わせは
    単純な必須項目欠落=クライアント側バリデーション漏れとして扱う)とは異なり、本
    venture側は4出力生成の分岐そのものをフォーム側に表示する想定のため区別する)。
  - `outcome="checkout_session_created"`: `{"ok": true, "draft_id": str,
    "checkout_url": str}`を200で返す(`draft_id_last4`・`checkout_session_id`は
    ブラウザ側に渡す必要がないため含めない。オーナー検索用の`draft_id_last4`は
    Firestore側のドキュメントフィールドとしてのみ保持する、既存方針どおり)。

## 3. 実Stripe接続前のランタイム依存

- `StripeCheckoutSessionClientProtocol`の検証用インメモリ実装
  (`InMemoryCheckoutSessionClient`)を`checkout_session_creation.py`に新設する。
  `create_session()`呼び出しごとに決定的でない`cs_inmemory_{uuid4}`セッションIDと
  ダミーの`checkout_url`を返すのみで、実Stripe API呼び出しは行わない
  (実Stripeアカウント接続は実GCPプロジェクト作成同様、オーナー承認待ちの範囲
  pending-approval.md参照)。既存テスト専用の`StubCheckoutSessionClient`
  (test_checkout_session_creation.py)とは別物とし、本番配線側
  (`cloud_function_submit_event_form.py`)が使う既定値としてのみ用いる。
- `draft_store`は既存の`InMemoryOneTimeDraftStore`(stripe_webhook.py)、
  `idempotency_store`は既存の`InMemoryIdempotencyKeyIndexStore`
  (idempotency_key_index_store.py)をそのまま再利用する。
- `base_url`は実ドメイン確定(web-form-hosting-selection.md参照、オーナー承認待ち)
  前のため、`get_submit_event_form_runtime_dependencies()`では
  `"https://example.invalid"`のようなプレースホルダ値を返す
  (`submit_inquiry`側に相当する設計判断なし。本関数が新たに導入する)。

## 4. 残課題

- 実GCPプロジェクト・実Stripeアカウント作成がオーナーから承認された場合、
  `get_submit_event_form_runtime_dependencies()`の中身を実Firestore
  (`OneTimeDraftStoreProtocol`実装)・実Stripeクライアント・確定済み`base_url`に
  差し替えるだけで`main()`・`checkout_session_http_entry.py`双方を変更せずに接続できる
  (`submit_inquiry`側と同じ差し替え容易性の方針)。
- `handle_stripe_webhook`・`get_result_page`の同型配線は次回候補として残す。
