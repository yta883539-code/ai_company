# draft作成時のevent_memo保存設計(フェーズ102)

## 1. 背景

README.mdフェーズ101「`process_generation_after_payment()`自体をCloud Function
エントリポイントに結線する」実装の過程で、次の未設計ギャップを発見した。

- `generation_retry_and_refund.GenerationFn`は`(draft_id: str) -> dict`という契約で、
  実際のLLM生成(`mock_llm_client.run_form_submission_pipeline()`相当)を呼ぶには
  主催者が入力した5要素(`capacity`・`entry_exit_points`・`admission_type`・`staffing`・
  `outdoor_queue`、form_submission_intake.EventMemoInput)が`draft_id`から取り出せる
  必要がある。
- しかし`one_time_draft/{draft_id}`を表す`OneTimeDraft`(stripe_webhook.py)は、
  決済確認後に必要な情報(`checkout_session_id`・`customer_email`・`payment_intent_id`)
  しか保持しておらず、Checkout Session作成前のWebフォーム入力自体をどこに・どう保存するかが
  未設計のまま残っていた。

one-time-checkout-no-account-design.md(フェーズ10)は「`draft_id`を主キーとするワンタイム
トークン方式」「Stripe Checkout one-time payment modeの`client_reference_id`に`draft_id`を
設定してFirestore `one_time_draft/{draft_id}`と紐付ける」と設計していたが、この`draft_id`が
いつ・どの入力を伴って作成されるかの詳細は未記載だった。

## 2. 設計

- `draft_id`は、Webフォーム送信(`form_submission_intake.handle_form_submission()`)が
  LLMリクエストペイロードを返した時点(=必須項目充足、`status=insufficient_input`で
  完結しない場合)に、Checkout Session作成の直前に生成する(採番方式自体は
  draft-id-last4-collision-design.mdフェーズ53を踏襲、本設計では変更しない)。
- 採番と同時に`OneTimeDraftStoreProtocol.create_draft(draft_id, event_memo=..., 
  expires_at=..., status="awaiting_payment")`を呼び、Webフォームの生ペイロード(dict、
  `EventMemoInput`の5フィールド)をそのまま`event_memo`として`one_time_draft/{draft_id}`
  ドキュメントに保存する。正規化済みの`EventMemoInput`ではなく生ペイロードを保存するのは、
  `form_submission_intake.parse_form_payload()`の正規化ロジック(空白除去等)が将来変更
  されても、生成時に`handle_form_submission()`を再度通すだけで常に最新ロジックで再評価
  できるようにするため。
- `status=insufficient_input`で完結する場合はCheckout Session自体を作成しないため
  `create_draft()`も呼ばれない(=`one_time_draft`ドキュメントは必須項目充足済みの入力
  についてのみ存在する、という既存の暗黙の前提を明文化する)。
- 決済完了後、`generate_fn(draft_id)`(draft_generation_fn.build_generation_fn()が
  組み立てる)は`draft_store.get(draft_id).event_memo`を取り出し、
  `form_submission_intake.handle_form_submission()`に再度通した上でLLMを呼び出す。
  再度intake層を通すことで、(a)design上は発生しないはずだが`event_memo`が保存時点と
  現在のロジックで判定が変わった場合も防御的にinsufficient_input応答へ倒せる、
  (b)`build_llm_request_payload()`が組み立てるLLMリクエストペイロードの形を
  intake層・生成時点で重複実装しない、という2つの利点がある。
- LLM出力の検証(`mock_llm_client.validate_llm_output()`)でエラーが検出された場合は
  `GenerationError`を送出し、`generation_retry_and_refund.process_generation_after_
  payment()`の既存リトライ・返金フローにそのまま委ねる(同モジュール冒頭docstringが
  既に「検証エラーも生成失敗として同列に扱う」と明記している方針どおり)。

## 3. 実コード化(本フェーズ)

- `stripe_webhook.py`: `OneTimeDraft`に`event_memo: Optional[dict]`を追加。
  `OneTimeDraftStoreProtocol`に`create_draft()`を追加し、`InMemoryOneTimeDraftStore`に
  実装した(既存の`seed()`はテスト用の直接投入経路として維持、両立する)。
- `draft_generation_fn.py`(新規): `build_generation_fn(draft_store, llm_client,
  scenario_for_draft)`が`GenerationFn`契約を満たすクロージャを組み立てる。`event_memo`が
  見つからない場合は`DraftEventMemoMissingError`(`GenerationError`のサブクラス)を送出する。
- テスト: `test_draft_generation_fn.py`(新規、6件)・`test_stripe_webhook.py`の
  `CreateDraftTest`(新規、3件)。

## 4. 残課題・次回候補

- `scenario_for_draft`は本モック環境固有の引数であり、実LLM接続後は`LlmCallClient.generate()`
  自体がscenario引数を持たない契約に差し替わる想定(mock_llm_client.pyの既存の割り切りを
  踏襲)。実LLM接続時に`build_generation_fn()`のシグネチャ自体を見直す必要がある。
- `event_memo`を生ペイロードのまま保存する方式は、将来`parse_form_payload()`が後方互換の
  ない形でフィールド名を変更した場合、保存済みドラフトの再評価に影響しうる(本フェーズでは
  発生しうる仮説として記録するのみ、実際の対応は変更発生時に検討)。
- Checkout Session作成エンドポイント自体(`draft_id`採番から`create_draft()`呼び出し、
  Stripe Checkout Session作成までを結ぶCloud Functionエントリポイント)はまだコード化
  されていない(`receive_stripe_webhook()`は決済完了後のWebhook受信口のみを担当し、
  Checkout Session作成リクエスト自体は別エンドポイントの責務、tech-stack.md参照)。
