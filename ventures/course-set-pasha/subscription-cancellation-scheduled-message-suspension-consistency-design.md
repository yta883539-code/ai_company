# 解約予約受理案内メッセージと制限モード状態の整合性対応(フェーズ157)

## 1. 経緯・発見した問題

subscription-cancellation-scheduled-notification-design.md(フェーズ156)7節「次回以降の
課題」には、以下の項目が検証課題として保留されていた。

> 3節で述べた「`suspension_reason`相当のガード(決済失敗による制限モード中は解約予約
> 通知を出さない等の調整要否)」は、実際に決済失敗と解約予約が同時発生するケースの
> 実運用データが無いため、今回は検証課題として保留する。

この記載は「通知を送るか送らないか(ガード)」の観点のみを扱っていたが、本フェーズで
`render_subscription_cancellation_scheduled_message()`(フェーズ156)の実際の文面を
確認したところ、通知の送信可否ではなく**文面の内容自体が事実と矛盾しうる**という、
より具体的な問題を発見した。

同メッセージには次の一文が固定で含まれる。

> ・ご利用は今回の請求期間の終了日(YYYY-MM-DD)まで通常通り継続します
> (投稿文の生成に制限はありません)

しかし本ventureには、`invoice.payment_failed`受信から`PAYMENT_FAILURE_GRACE_PERIOD_DAYS`
(7日、`cloud_function_webhook.py`)を超えて決済失敗が続いた場合に投稿文の生成そのものを
停止する「制限モード」(payment-failure-dunning-design.md 3節の段階3、
`cloud_function_webhook._is_payment_suspended()`で都度判定)が既に存在する。したがって、

- 顧客が決済失敗により既に制限モードへ移行済み(投稿文の生成が既に一時停止中)の状態で
- Stripeカスタマーポータル等から解約予約(`cancel_at_period_end: false → true`)を行うと

「投稿文の生成に制限はありません」という案内が、実際の状態(生成は既に停止中)と
真っ向から矛盾したまま顧客に送信されてしまう。これは「通知を送るか否か」の問題ではなく
「送る内容が正しいか」の問題であり、フェーズ156時点の7節はこの観点を明示的に検討して
いなかった(`classify_cancel_at_period_end_change()`のdocstringが「本ventureは
`suspension_reason`相当の別立て状態を持たないためガード条件を持たない」と述べていたのは
「送信可否のガード」の話であり、文面の正確性とは別の論点である)。

## 2. 対応方針

「送るか送らないか」ではなく「送る内容を状態に応じて出し分ける」方針を採る。解約予約
受理自体は制限モードの有無に関わらず事実として発生しており、通知自体を抑制すると
顧客は自分の解約予約が受理されたことを知る手段を失ってしまう(payment-failure側の
リマインド通知〈payment-failure-reminder-scheduler-design.md〉とは目的が異なる別の
情報のため、通知を統合・省略すべきでもない)。よって、

- `OUTCOME_CANCELLATION_SCHEDULED`の案内メッセージ生成時のみ、現在制限モード中かどうかを
  判定し、`is_currently_suspended=True`の場合は「投稿文の生成に制限はありません」の一文を
  「契約自体は終了日まで継続するが、決済失敗による制限モードのため投稿文の生成は既に
  一時停止しており、解約予約とは別にお支払い方法のご確認が必要」という趣旨の文言に
  差し替える。
- `OUTCOME_CANCELLATION_RESCHEDULED`(解約取り消し)側のメッセージ
  (`SUBSCRIPTION_CANCELLATION_RESCHEDULED_MESSAGE`)は「解約のお取り消しを承りました。
  引き続きご利用いただけます」という趣旨で生成の可否に触れておらず、制限モード中でも
  文言と矛盾しないため変更不要と判断した。

## 3. 実装

`prototype/subscription_cancellation_notification.py`に以下を追加した。

- `_is_payment_suspended_now(usage_counter, user_id, now)`: 判定条件は
  `cloud_function_webhook._is_payment_suspended()`(フェーズ118)と同一
  (`now - get_payment_failure_detected_at(user_id) >= PAYMENT_FAILURE_GRACE_PERIOD_DAYS`日)。
  Stripe側Cloud Function(`stripe_webhook.py`)とLINE側Cloud Function
  (`cloud_function_webhook.py`)は別々にデプロイされる想定のため判定ロジック自体は
  各Cloud Function側に薄く複製する既存方針(aircon-pashaの`stripe_dispatch.py`の
  `payment_store`引数運用等と同じ)を踏襲する一方、猶予日数の定数
  (`PAYMENT_FAILURE_GRACE_PERIOD_DAYS`)は値のズレを防ぐため同一`prototype/`ディレクトリ内の
  `cloud_function_webhook.py`からそのままインポートする(本モジュールは既に同モジュールから
  `PORTAL_LINK_PLACEHOLDER`等をインポートしており、追加の結合ではない)。
  `usage_counter`が`get_payment_failure_detected_at`に未対応、または検知時刻・`now`の
  いずれかが得られない場合は安全側デフォルトとして`False`を返す。
- `render_subscription_cancellation_scheduled_message()`に`is_currently_suspended: bool =
  False`引数を追加。`True`の場合のみ該当の一文を差し替える。デフォルト`False`のため
  既存呼び出し経路への後方互換を保つ。
- `handle_subscription_cancellation_update()`に`usage_counter`・`now`引数(いずれも
  `Optional`、デフォルト`None`)を追加。`OUTCOME_CANCELLATION_SCHEDULED`の場合のみ
  `_is_payment_suspended_now()`を評価してメッセージ生成へ渡す。

`prototype/stripe_webhook.py`の`dispatch_stripe_event()`
`customer.subscription.updated`分岐では、既存の`usage_counter`引数(フェーズ119で
`invoice.payment_failed`/`invoice.payment_succeeded`向けに追加済み)と`now`引数
(invoice側分岐で使う`resolved_now`と同じ「未指定なら`datetime.now(timezone.utc)`」方針を
このブロック内でも独立に適用した`resolved_now_for_suspension_check`)を、そのまま
`handle_subscription_cancellation_update()`へ追加で渡すよう配線した。`usage_counter`
未指定(`None`)時は`_is_payment_suspended_now()`が安全側で`False`を返すため、
フェーズ156時点の呼び出し経路(制限モード判定なし)と同じ挙動が保たれる。

## 4. テスト

`test_subscription_cancellation_notification.py`に以下を追加する。

- `_is_payment_suspended_now()`: 猶予期間超過時に`True`、未経過時に`False`、
  `usage_counter`/`now`いずれか未指定時・`get_payment_failure_detected_at`未対応時・
  検知時刻未設定時に`False`を返すことを確認するテスト。
- `render_subscription_cancellation_scheduled_message()`: `is_currently_suspended=True`
  時に新しい文言(「投稿文の生成は既に一時停止しています」)を含み、従来の「投稿文の
  生成に制限はありません」という一文を含まないことを確認するテスト。
  `is_currently_suspended`未指定(デフォルト`False`)時は従来通りの文言のままである
  ことを確認する既存テストは変更しない(後方互換の確認を兼ねる)。
- `handle_subscription_cancellation_update()`: `usage_counter`で制限モード中と判定
  される状態を渡した場合に送信される文面が制限モード向けの文言に切り替わること、
  `OUTCOME_CANCELLATION_RESCHEDULED`側では`usage_counter`/`now`を渡しても文面が
  変化しないことを確認するテスト。

`test_stripe_webhook.py`には、`customer.subscription.updated`(`cancel_at_period_end`
`false→true`)受信時に`usage_counter`が制限モード中の顧客を記録している場合、送信される
メッセージが制限モード向けの文言に切り替わることを確認する結合テストを追加する。

## 5. 次回以降の課題

- 制限モード中の解約予約案内メッセージの具体的な文言(お支払い方法確認と解約予約という
  2つの手続きが並行して存在する状態の説明)は、実際の顧客からの問い合わせ実績が無い
  ため、初期案として妥当性を検証する必要がある。
- line-reservation-ai・aircon-pashaは本フェーズ時点でまだ解約予約受理時点の顧客向け
  通知自体を実装していないため、同様の矛盾が将来実装時に再発しないよう、実装時には
  本ドキュメントの3節の判定ロジック(`_is_payment_suspended_now()`相当)の横展開を
  検討すべきである。
- 実LINE Push Message API接続・実Stripe接続はいずれも実アカウント作成
  (オーナー承認待ち)後の課題として引き続き残る。
