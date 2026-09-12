# subscription-plan-sync-design.md

フェーズ93(2026-09-12 17:00 UTC)。Stripeカスタマーポータル経由のプラン変更
(アップグレード/ダウングレード)を`craftsman_workshop/{workshop_id}.plan_id`へ
反映する同期処理の設計。

## 1. 発見の経緯

aircon-pashaフェーズ208(15:00 UTC定例更新)は、course-set-pashaのsubscription-plan-
change-design.md(フェーズ続き154)で解消済みだった「プラン変更を伴わない
`customer.subscription.updated`イベントでの無駄な書き込み」と同種のギャップが
`subscription_plan_sync.py`に残っていたことを発見・解消し、「kura-pasha・
line-reservation-aiへの横展開要否は次回以降の棚卸し候補として残す」と申し送っていた。

本フェーズで棚卸しを行ったところ、kura-pashaの状況はaircon-pasha側の対応(差分チェック
の追加)より手前の段階、すなわち**同期処理そのものが一度も実装されていない**という
より根本的な配線漏れだったと判明した。

## 2. 既存の実態

- `usage_counter_workshop.py`の`get_plan_id(workshop_id)`は、`craftsman_workshop/
  {workshop_id}.plan_id`を読み、`PLAN_LIMITS`(light/standard/multi_craftsman)と
  突き合わせて生成回数上限を決定する(`check_and_increment_usage()`)。
- `plan_id`を書き込むのは`stripe_webhook.py`の`handle_checkout_session_completed()`
  (`checkout.session.completed`受信時、`metadata.plan_id`から)のみで、
  `handle_customer_subscription_updated()`(`customer.subscription.updated`受信時)は
  `cancel_at_period_end`・`current_period_end`のみを扱い、`plan_id`には一切触れていな
  かった。
- 一方、subscription-cancellation-flow-design.md「ダウングレード(プラン変更)フロー」
  (フェーズ55)は、Stripeカスタマーポータル経由のダウングレード時「上限判定にのみ
  新プラン(下位プラン)の上限値を即時適用する」と確定済みだった。この「即時適用」を
  実現する手段が存在しないまま設計上だけ確定していた状態だった。

## 3. 対応

`prototype/subscription_plan_sync.py`を新設し、aircon-pasha/prototype/
subscription_plan_sync.py(フェーズ177・208)の設計をkura-pasha固有の構造へ翻案した。

- `resolve_plan_id_from_subscription(data_object)`: `items.data[0].price.lookup_key`
  から`LOOKUP_KEY_TO_PLAN_ID`(`kura_pasha_light`/`kura_pasha_standard`/
  `kura_pasha_multi_craftsman` → `light`/`standard`/`multi_craftsman`)で解決する。
  解決できない場合は常に`None`(呼び出し元は既存値を維持)。
- `sync_plan_on_subscription_event(store, workshop_id, data_object)`: 解決できた
  plan_idが既存の`get_plan_id(workshop_id)`と異なる場合のみ`set_plan()`を呼ぶ
  (差分チェックはaircon-pashaフェーズ208の教訓を踏まえ最初から組み込んだ)。
  `get_plan_id`が`KeyError`を送出する場合(plan_id未設定、通常発生しない想定)は
  「既存値と異なる」とみなし常に書き込む安全側の挙動とする。
- `handle_customer_subscription_updated()`(stripe_webhook.py)から、
  `current_period_end`の永続化と同じ位置(`push_client is None`の早期returnより前)で
  呼び出す。通知の要否・成否とは独立に同期する。

## 4. 本venture固有の差異(aircon-pashaとの比較)

- aircon-pashaの`CurrentPlanStoreProtocol.get_current_plan_id()`は`Optional[str]`
  (未契約時`None`)だが、kura-pashaの`WorkshopStoreProtocol.get_plan_id()`は`str`を
  返す(workshop作成時に必ず暫定plan_idが設定される設計、craftsman-account-linking-
  design.md フェーズ66追記7節)。このため`sync_plan_on_subscription_event()`は
  `KeyError`を安全側で吸収する形にした(3節参照)。
- aircon-pashaは`customer.subscription.deleted`受信時に`clear_current_plan_on_
  subscription_deleted()`で`current_plan_id`を`None`へ戻すが、kura-pashaは解約後も
  workshop自体が残り`plan_id`を特別な値に戻す必要がない(次回契約時に
  `checkout.session.completed`が新たなplan_idを設定し直す、既存の
  `handle_customer_subscription_deleted()`は`subscription_status`のみを変更し
  `plan_id`には触れない)。したがって本ventureには対応する処理を実装しない。

## 5. 動作確認

- `test_subscription_plan_sync.py`(新設、14件): lookup_key解決の網羅・差分チェックに
  よる書き込み省略/再書き込みを確認。
- `test_stripe_webhook.py`(3件追加): `handle_customer_subscription_updated()`から
  実際に`plan_id`が同期されること、`items`欠落時は変更されないこと、`push_client`
  未指定でも同期されることを確認。
- `python3 prototype/run_all_tests.py`: 10 files run, 10 passed(既存652件+新規21件)。
- `python3 schema/validate_test_cases.py`: 27件全件パス(変更前と同じ結果、schema/
  output.schema.jsonへの影響は無い。`plan_id`はLLM構造化出力に登場しないフィールド)。

## 6. 次の課題

- 実Stripeアカウント接続後、Price作成時に`kura_pasha_light`/`kura_pasha_standard`/
  `kura_pasha_multi_craftsman`のlookup_keyを実際に設定する作業自体はオーナー承認待ちの
  範囲(pending-approval.md参照)であり、本フェーズでは行っていない。
- line-reservation-aiへの同種ギャップの横展開要否は次回以降の棚卸し候補として残す
  (line-reservation-aiはワークショップ単位ではなく店舗単位の契約構造であり、そもそも
  複数プランを持つか自体を要確認)。
