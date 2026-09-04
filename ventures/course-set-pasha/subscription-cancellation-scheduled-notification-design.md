# 解約予約受理時点(cancel_at_period_end)の顧客向けLINE通知設計(フェーズ156)

subscription-cancelled-notification-design.md(フェーズ155)4節「次回以降の課題」に
残っていた、`customer.subscription.updated`受信時の「解約予約受理時点
(`cancel_at_period_end`の`false→true`変化)」「解約取り消し時点(`true→false`変化)」の
2つの案内メッセージ配線に対応する。line-reservation-aiフェーズ続き185
(`customer-subscription-updated-event-routing-design.md`)の設計・実装
(`cloud_function_subscription_cancelled_webhook.py`
`classify_subscription_update()`・`handle_subscription_updated()`・
`render_cancellation_scheduled_message()`・`render_cancellation_rescheduled_message()`)を、
本venture固有の状態モデルへ翻案する。

## 1. 「直前のcancel_at_period_end」の取得方法

line-reservation-ai設計と同じ考え方をそのまま採用する。Stripeの
`customer.subscription.updated`イベントは`event.data.object`(変化後の全フィールド)に
加えて`event.data.previous_attributes`(そのイベントで実際に変化したフィールドのみを
含む差分オブジェクト)を持つ。

```
data_object = event["data"]["object"]
previous = event["data"].get("previous_attributes", {})
after = data_object.get("cancel_at_period_end", False)
before = previous.get("cancel_at_period_end", after)
```

`cancel_at_period_end`が今回のイベントで変化していない場合(例: デフォルト支払い方法の
変更等、別のフィールド変化で発火した場合)は`previous_attributes`に
`cancel_at_period_end`キー自体が存在しないため、`before = after`(変化なし)として
扱ってよい。`classify_cancel_at_period_end_change()`(3節)は前後が同値なら
`OUTCOME_NO_CHANGE`を返す設計のため、この扱いは既存のプラン変更検知ロジック
(フェーズ153・154)と同じ`data_object`単体読み取り方針にも整合する。

本ventureはFirestore側に「前回のcancel_at_period_end」を別途保存・比較する設計を
採らない(line-reservation-aiと同じ理由: Stripeが差分を運んでくれるため、自前で状態を
持つと二重管理になり再送・順序入れ替わり時にかえって不整合を招くリスクがある)。

## 2. 期間終了日の取得

`data_object.get("current_period_end")`(Unixタイムスタンプ、Stripeのsubscription
オブジェクトにそのまま含まれるフィールド、追加API呼び出し不要)をJST(`tech-stack.md`・
`cloud_function_webhook.py` `_current_jst_month()`と同じUTC+9固定のタイムゾーン方針)の
`YYYY-MM-DD`形式に変換して案内文へ差し込む。`current_period_end`が存在しない・数値でない
場合は日付を差し込まない簡易文言(4節参照)にフォールバックする(安全側、壊れた日付を
顧客に見せない)。

## 3. 分類ロジック

`subscription_cancellation_notification.py`に追加する
`classify_cancel_at_period_end_change(before: bool, after: bool) -> str`:

```
if not before and after:
    return OUTCOME_CANCELLATION_SCHEDULED
if before and not after:
    return OUTCOME_CANCELLATION_RESCHEDULED
return OUTCOME_NO_CHANGE
```

line-reservation-aiの`classify_subscription_update()`と異なり、本ventureは
`suspension_reason`(店舗の制限モードを表す別立てフラグ)という状態を持たない
(payment-failure-dunning-design.md 3節のとおり、制限モードは
`payment_failure_detected_at`からの経過日数で都度算出する設計であり、決済失敗時に
`cancel_at_period_end`が同時に変化するケース自体は考慮しない)。よって
line-reservation-aiにある「`suspension_reason == "payment_failed"`の店舗には触れない」
ガードは本venture固有の状態モデルには存在せず、そのまま移植しない
(スコープを絞った判断であり将来の検証課題として4節に残す)。

## 4. 案内メッセージ

`SUBSCRIPTION_CANCELLED_MESSAGE`(フェーズ155)と同じくトーン分岐
(formal/standard/casual)は行わない単一のプレーンテキストとする
(本venture決済・契約系通知の一貫方針)。

`render_subscription_cancellation_scheduled_message(period_end_date: Optional[str],
portal_link_provider, user_id) -> str`:
「解約のお手続きを承りました」「今回の請求期間の終了日({period_end_date})までは
通常通りご利用いただけます」「終了日以降は投稿文の生成がご利用いただけなくなります」
「取り消しをご希望の場合は終了日より前に下記からお手続きください」の4点を含む。
URL差し込みは`payment_recovery_notification.py`
`render_payment_failure_detected_message()`と同じ`PORTAL_LINK_PLACEHOLDER`+
`.replace()`方式を踏襲し、`portal_link_provider`が未接続・`user_id`不明・URL取得失敗の
いずれかの場合は`PORTAL_LINK_UNAVAILABLE_FALLBACK`へ全文差し替える(壊れたURLを
顧客に見せない既存方針)。`period_end_date`が`None`(2節のフォールバック)の場合は
終了日の言及を「今回の請求期間の終了日まで」という日付なしの表現に差し替える。

`render_subscription_cancellation_rescheduled_message() -> str`:
「解約のお取り消しを承りました」「引き続きご利用いただけます」の2点を含む単純な固定文言
(line-reservation-ai版と異なり、`plan_name`・`period_end_date`は差し込まない。
理由: 本venture向け解約完了通知〈フェーズ155〉も同様に差し込み情報を最小限に絞っており、
本venture決済系通知全体の一貫方針として踏襲した)。

## 5. `dispatch_stripe_event()`側の配線

`customer.subscription.updated`分岐冒頭、既存のプラン変更検知(フェーズ153・154)の
直後に追加する。プラン変更検知とは独立した処理のため、互いの結果に影響しない
(同一イベント内で両方が発火しうる: 例えばプラン変更と同時に解約予約を行うケースは
Stripe上あり得るが、本フェーズでは各々を独立に評価するだけで十分と判断した)。

```
if push_client is not None:
    previous_attrs = event.get("data", {}).get("previous_attributes", {})
    after = data_object.get("cancel_at_period_end", False)
    before = previous_attrs.get("cancel_at_period_end", after)
    update_result = handle_subscription_cancellation_update(
        user_id, before, after, data_object.get("current_period_end"),
        push_client, portal_link_provider,
    )
    if update_result.outcome == OUTCOME_CANCELLATION_SCHEDULED:
        (成功/失敗をresultへ記録)
    elif update_result.outcome == OUTCOME_CANCELLATION_RESCHEDULED:
        (成功/失敗をresultへ記録)
    # OUTCOME_NO_CHANGE時は何もしない(送信なし)
```

`push_client`が`None`の場合は従来通り送信しない(既存の全通知配線と同じ後方互換方針)。
`StripeDispatchResult`に`cancellation_scheduled_notified_user_ids`・
`cancellation_rescheduled_notified_user_ids`・
`cancellation_update_notification_failed_user_ids`(送信失敗、いずれの分類も区別せず
1つにまとめる。フェーズ155の`cancellation_notification_failed_user_ids`と同様、
呼び出し側が失敗理由の分岐まで必要とする場面が今のところ無いため)を新設する。

本イベントは契約継続中(`OUTCOME_CANCELLATION_SCHEDULED`)または契約継続が確定した
(`OUTCOME_CANCELLATION_RESCHEDULED`)場合のみ発火するため、`store`(削除候補管理)側の
状態変更は行わない(line-reservation-aiの`handle_subscription_updated()`と同じ判断:
書き換え対象のフィールドが無いため`state`の書き戻しは不要)。既存の
`customer.subscription.updated`分岐末尾にある`active/trialing`ステータス判定
(削除候補クリア)より前に評価する(順序自体は変更しない、独立した処理のため
どちらが先でも結果に影響しないが、フェーズ153・154のプラン変更検知と並べる
可読性を優先した)。

## 6. テスト

- `test_subscription_cancellation_notification.py`:
  `classify_cancel_at_period_end_change()`の3分岐(scheduled/rescheduled/no_change)、
  `render_subscription_cancellation_scheduled_message()`の日付あり/なし・
  portal_link_provider未接続時のフォールバック、
  `render_subscription_cancellation_rescheduled_message()`の固定文言、
  `handle_subscription_cancellation_update()`の送信成功/失敗/no_change時に送信自体が
  行われないことを確認するテストを追加する。
- `test_stripe_webhook.py`: `customer.subscription.updated`受信時、
  `previous_attributes.cancel_at_period_end`の有無別(変化あり/`cancel_at_period_end`
  以外の理由での発火/`push_client`未接続/送信失敗)の観点を確認するテストを追加する。

## 7. 次回以降の課題

- 3節で述べた「`suspension_reason`相当のガード(決済失敗による制限モード中は解約予約
  通知を出さない等の調整要否)」は、実際に決済失敗と解約予約が同時発生するケースの
  実運用データが無いため、今回は検証課題として保留する。
- 実LINE Push Message API接続・実Stripe接続はいずれも実アカウント作成
  (オーナー承認待ち)後の課題として引き続き残る。
