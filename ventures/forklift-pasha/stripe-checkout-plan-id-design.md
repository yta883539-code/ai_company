# Stripe決済導線: plan_idの書き込み元設計

作成日: 2026-10-11 10:00 UTC(フェーズ124)

README.mdフェーズ123「次回候補」(2)で残課題として記録されていた「plan_idの
fleet_operatorへの書き込み元(Stripe決済導線設計、本venture未着手)」に着手する。

## 1. 問題設定

`overage_notifications.py`(フェーズ115)は`format_fleet_overage_notice()`等で
`plan_id`("light"/"standard"/"fleet")を受け取る前提で実装済みだが、この`plan_id`が
`fleet_operator`ドキュメントにいつ・どう書き込まれるかは本venture側で一度も設計されて
いなかった(フェーズ123で`process_form_submission()`への組み込みを意図的に見送った理由)。

本ventureは他venture(aircon-pasha/course-set-pasha/kura-pasha/line-reservation-ai)と
異なり、Stripe Checkout Session作成・Webhook受信エントリポイント自体のモジュール
(`checkout_session.py`/`stripe_webhook.py`相当)がまだ存在しない
(payment-identity-verification-design.mdはCheckout Session発行時の本人確認方式
〈client_reference_id = internal_id〉のみを設計済みで、購入プランの記録は対象外)。
本フェーズはそのエントリポイント自体の実装は次回以降の課題として残しつつ、
ストア側の読み書き(`FleetOperatorStoreProtocol`)と、Stripeイベントデータから
`plan_id`を解決する純粋関数を先行して用意する。

## 2. 方針

course-set-pasha/checkout-session-plan-selection-design.md(フェーズ152)の
`metadata.plan`方式を本venture向けに踏襲しつつ、1点簡略化する。

- 他venture: `metadata.plan`に日本語プラン名(例: `"ライト"`)を入れ、各ventureの
  プランキー集合へ読み替える。
- 本venture: `overage_notifications.PLAN_VEHICLE_LIMIT`等が既に`"light"`/`"standard"`/
  `"fleet"`という英語キーを正としているため、`metadata.plan`にもそのまま同じ値を
  入れる想定とする(日本語⇔英語の変換テーブルを追加で持たずに済む)。

## 3. 初回プラン記録: checkout.session.completed

1. Webフォームのプラン選択UI(未実装、`web-form-mockup/`相当の拡張として次回以降の
   課題)が、Checkout Session作成リクエストに選択プラン(`"light"`/`"standard"`/
   `"fleet"`のいずれか)を付与する。
2. Checkout Session作成処理(`checkout_session.py`相当、未実装)が`metadata: {"plan":
   <選択値>}`をパラメータに含める(course-set-pashaと同じ理由で`line_items`の
   expandではなく`metadata`経由にする)。
3. Webhookエントリポイント(`stripe_webhook.py`相当、未実装)が`checkout.session.
   completed`受信時に`data.object.metadata`を`plan_id_resolution.
   write_plan_id_from_checkout_session_metadata(store, internal_id, metadata)`へ渡す。
   未知の値・`metadata`欠落時は書き込まない(安全側、course-set-pashaの方針を踏襲)。

## 4. プラン変更時の同期: customer.subscription.updated

カスタマーポータル経由のプラン変更は`metadata`が引き継がれないため、
line-reservation-ai/subscription-plan-sync-design.md(フェーズ続き220)の方式を踏襲する。

- 実Stripe Price作成時に`lookup_key`を設定する(`forklift_pasha_light`/
  `forklift_pasha_standard`/`forklift_pasha_fleet`。実際の設定はオーナー承認後、
  pending-approval.md参照)。
- Webhookエントリポイントが`customer.subscription.updated`受信時に
  `plan_id_resolution.sync_plan_id_on_subscription_event(store, internal_id,
  data_object)`を呼ぶ。解決できた`plan_id`が既存値と異なる場合のみ書き込む
  (差分チェックをaircon-pasha/kura-pasha/line-reservation-aiの教訓を踏まえ
  最初から組み込んだ)。

## 5. 実装した変更

- `prototype/trial_management.py`: `FleetOperatorStoreProtocol`/
  `InMemoryFleetOperatorStore`に`get_plan_id`/`set_plan_id`を追加(`get_upgraded_at`/
  `set_upgraded_at`と同じ「上書き可」方針、`get_trial_start_at`等と異なり
  「初回のみ」の制約は設けない)。
- `prototype/plan_id_resolution.py`(新設): `KNOWN_PLAN_IDS`(`overage_notifications.
  PLAN_VEHICLE_LIMIT`のキーを単一の正として同期)・`LOOKUP_KEY_TO_PLAN_ID`・
  `write_plan_id_from_checkout_session_metadata()`・`resolve_plan_id_from_
  subscription()`・`sync_plan_id_on_subscription_event()`を実装。

## 6. 動作確認

- `test_plan_id_resolution.py`(新設、19件): 既知/未知のplan・metadata欠落時の安全側
  挙動、既知/未知のlookup_key解決、差分チェックによる書き込み省略/再書き込み、
  operator間の独立性を確認。
- `python3 prototype/run_all_tests.py`: 8ファイル全件パス(既存7ファイル→8ファイル、
  本モジュールのテスト追加分を含む)。
- `python3 schema/validate_test_cases.py`: 11件全件パス(変更なし。`plan_id`はLLM
  構造化出力に登場しないフィールドのためschema側への影響なし)。

## 7. 次の課題

- Checkout Session作成・Webhook受信エントリポイント自体のモジュール(他venture
  `checkout_session.py`/`stripe_webhook.py`相当)の実装自体が本venture未着手のまま。
  本フェーズで用意したストア・解決関数はこのエントリポイントからの呼び出しを待つ
  状態にある。
- Webフォームのプラン選択UI(`web-form-mockup/`の拡張)自体も未実装。
- 実Stripeアカウント接続後、Price作成時に`forklift_pasha_light`/`_standard`/`_fleet`の
  `lookup_key`を実際に設定する作業自体はオーナー承認待ちの範囲(pending-approval.md参照)。
- `process_form_submission()`(フェーズ123)への`overage_notifications.py`組み込みは、
  本フェーズでplan_idの書き込み元を設計したことで前提が一つ解消されたが、実際の組み込みは
  上記エントリポイント実装後に行う(フェーズ123の判断を維持)。

最終更新: 2026-10-11 10:00 UTC(フェーズ124: 本ドキュメント新設。plan_idの書き込み元を
checkout.session.completed〈初回〉・customer.subscription.updated〈変更時〉の2経路で
設計し、`plan_id_resolution.py`を実装。テスト19件追加、全8ファイルパス)
