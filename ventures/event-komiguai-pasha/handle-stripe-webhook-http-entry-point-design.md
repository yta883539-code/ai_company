# `handle_stripe_webhook` Cloud Run functions HTTPエントリポイント設計

README.mdフェーズ110の次回候補(2)「残り2関数(`handle_stripe_webhook`・
`get_result_page`)についても本フェーズ・フェーズ109と同型の`main(request)`薄配線を
設計・実装する」のうち、`handle_stripe_webhook`分に対応する。

submit-event-form-http-entry-point-design.md(フェーズ110)・inquiry-form-http-entry-point-
design.md(フェーズ109)と同じ方針(本体はbytes/dictのみを扱い実クラウド接続なしで
テスト可能、`main(request)`だけが実`functions_framework`リクエストオブジェクトを扱う薄い
配線)を踏襲する。

## 1. 位置づけ

- 業務ロジック自体は`stripe_webhook.receive_stripe_webhook()`(フェーズ99、署名検証・
  冪等性チェック・`checkout.session.completed`への振り分け・生成リトライ/返金への結線
  までを結ぶ1本のエントリポイント関数)として既に実コード化済みであり、本設計は
  「実Cloud Functionsリクエストオブジェクトからどうbody・`Stripe-Signature`ヘッダ・
  webhook secretを取り出し`receive_stripe_webhook()`へ渡すか」のみを新規に扱う。
- aircon-pasha/course-set-pasha版は`stripe_webhook.py`自身に`main(request)`を実装する
  構成だが、本venture(event-komiguai-pasha)はフェーズ109・110で確立した「業務ロジックと
  薄い`main(request)`配線を別ファイルに分離する」方針(`inquiry_form_http_entry.py`+
  `cloud_function_submit_inquiry.py`、`checkout_session_http_entry.py`+
  `cloud_function_submit_event_form.py`)を踏襲し、新規に`cloud_function_handle_stripe_
  webhook.py`を作成する(`stripe_webhook.py`自体は変更しない)。

## 2. リクエスト・レスポンス形状

- リクエスト: Stripeが送信するWebhookペイロード(bytes)と`Stripe-Signature`ヘッダ。
- `receive_stripe_webhook()`の`status_code`が200の場合はレスポンス本文`"OK"`を返し、
  それ以外(401: 署名検証失敗、400: JSONパース失敗)の場合は`result.error`をそのまま
  本文として返す(aircon-pasha/course-set-pasha版`stripe_webhook.main()`と同じ形状。
  Stripe側は本文の内容を解釈せずステータスコードのみで再送判定するため、JSON化せず
  プレーンテキストで十分という既存方針を踏襲する)。

## 3. 実Stripe接続前のランタイム依存

- `webhook_secret`は環境変数`STRIPE_WEBHOOK_SECRET`から取得する(aircon-pasha/
  course-set-pasha版と同じ環境変数名、未設定時は空文字列=常に署名検証失敗という
  安全側の既定動作)。
- `draft_store`は既存の`InMemoryOneTimeDraftStore`(stripe_webhook.py)、
  `event_id_store`は既存の`InMemoryStripeEventIdStore`(同ファイル)をそのまま
  再利用する。
- `generate_fn`・`refund_client`・`email_sender`の3引数は本フェーズでは渡さない
  (`get_handle_stripe_webhook_runtime_dependencies()`は`draft_store`・`event_id_store`の
  2つのみを返す)。理由:
  1. `generate_fn`は`draft_generation_fn.build_generation_fn()`で組み立てる必要があるが、
     同関数の`scenario_for_draft`引数は「本モック環境固有」(draft_generation_fn.py
     冒頭docstring)であり、実LLM接続後は不要になる想定の検証用引数のため、本番相当の
     Cloud Function既定値としてそのまま採用するのは適切でない。
  2. `refund_client`・`email_sender`の実装(`InMemoryRefundClient`・
     `InMemoryEmailSender`)はいずれも「検証用、呼び出し引数を記録するだけ」
     (generation_retry_and_refund.py)であり、実際に主催者へ返金・メール送信した
     ことにはならない。
  3. `receive_stripe_webhook()`は3引数のうち1つでも欠ける場合は`generation_outcome=None`
     のまま返す設計(フェーズ100「次回候補(2)」で確定した意図的な分岐)のため、本フェーズで
     2引数のみを渡しても既存の後方互換動作がそのまま適用され、`checkout.session.
     completed`受信時の署名検証・冪等性チェック・`handle_checkout_session_completed()`
     への振り分け自体(本フェーズが主対象とするHTTPエントリポイント配線)は正しく動作する。
- 呼び出しごとに新規生成されるため、実Cloud Functions環境でも呼び出しをまたいで状態
  (`draft`・処理済み`event_id`)が保持されない既知の限界が残る(他Cloud Function同様、
  実Firestore接続後に解消される)。

## 4. 残課題

- 実GCPプロジェクト・実Stripeアカウント作成がオーナーから承認された場合、
  `get_handle_stripe_webhook_runtime_dependencies()`の中身を実Firestore
  (`OneTimeDraftStoreProtocol`・`StripeEventIdStoreProtocol`実装)に差し替えるだけで
  `main()`・`stripe_webhook.py`双方を変更せずに接続できる(`submit_event_form`・
  `submit_inquiry`側と同じ差し替え容易性の方針)。
- `generate_fn`・`refund_client`・`email_sender`の実装(実LLM・実Stripe Refund API・
  実メール送信)の結線は、実Stripeアカウント作成・実メール送信手段確定(いずれも
  オーナー承認待ち)後の別課題として残す。現時点では`checkout.session.completed`
  受信後の決済確認(`mark_payment_confirmed()`)までは行われるが、生成・返金までは
  自動実行されない(design 3節の意図的な分岐どおり)。
- `get_result_page`の同型配線は次回候補として残す(本venture全体の4 Cloud Run
  functionsのうち残り1関数)。
