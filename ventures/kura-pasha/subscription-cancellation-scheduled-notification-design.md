# 解約予約受理・解約取り消し(customer.subscription.updated)の契約者向けLINE通知設計(フェーズ55)

作成日: 2026-09-09(フェーズ55)

## 1. 経緯

subscription-cancellation-notification-design.md(フェーズ54)「5. 残課題」1点目に
残っていた、`customer.subscription.updated`イベントの`cancel_at_period_end`前後比較に
よる「解約予約受理」「解約取り消し」の2つの案内メッセージ配線に対応する。
course-set-pasha/subscription-cancellation-scheduled-notification-design.md
(フェーズ156)の設計・実装(`classify_cancel_at_period_end_change()`・
`render_subscription_cancellation_scheduled_message()`・
`render_subscription_cancellation_rescheduled_message()`・
`handle_subscription_cancellation_update()`)を、本venture固有の状態モデルへ翻案する。

## 2. workshop_idの解決

`customer.subscription.updated`も`customer.subscription.deleted`(フェーズ53)と同様
`client_reference_id`を持たないイベントであるため、`data_object.get("customer")`
(Stripe顧客ID)を`workshop_store.get_workshop_id_by_stripe_customer_id()`で逆引きする
既存ロジックをそのまま再利用する。`customer`が空・欠落、または逆引きで解決できなかった
場合は、`handle_customer_subscription_deleted()`と同じ扱い(`invalid`/`unresolved`)とし
`set_subscription_status`・通知処理のいずれも行わない。

## 3. 「直前のcancel_at_period_end」・期間終了日の取得

course-set-pasha設計(フェーズ156・1節・2節)と同じ考え方をそのまま採用する。

```
data_object = event["data"]["object"]
previous = event["data"].get("previous_attributes", {})
after = data_object.get("cancel_at_period_end", False)
before = previous.get("cancel_at_period_end", after)
```

`previous_attributes`に`cancel_at_period_end`キー自体が存在しない場合(別フィールドの
変化で発火した場合)は`before = after`(変化なし)として扱う。`current_period_end`
(Unixタイムスタンプ)はJST(UTC+9固定、他venture・本venture既存方針と同じ)の
`YYYY-MM-DD`形式へ変換して案内文へ差し込み、存在しない・数値でない場合は日付なしの
表現にフォールバックする(course-set-pasha`_format_period_end_date_jst()`と同じ
考え方)。本venture固有の状態として別途保存・比較する設計は採らない(Stripeが差分を
運んでくれるため自前で二重管理しない、course-set-pasha・line-reservation-aiと同じ理由)。

## 4. 分類ロジック

`subscription_cancellation_notification.py`に追加する
`classify_cancel_at_period_end_change(before: bool, after: bool) -> str`は
course-set-pasha版と完全に同一(before/after比較のみ)。本ventureも
course-set-pashaと同様`suspension_reason`相当の別立て状態(決済失敗ダニングによる
制限モード)を持たない(payment-failure-dunning相当の設計は本venture未着手のため、
そもそも制限モードとの整合ガード自体が対象外)。よってline-reservation-aiの
`classify_subscription_update()`が持つガード条件、course-set-pashaフェーズ157が
追加した`is_currently_suspended`分岐のいずれも移植しない(本venture未実装の機能への
言及になるため、次の課題〈7節〉に留める)。

## 5. 案内メッセージ

本ventureはフェーズ54で確定した既存方針(契約終了通知はトーン分岐なし・差し込み
情報を最小限に絞る単一のプレーンテキスト)をそのまま踏襲する。加えて、本venture
コード内には`PortalLinkProvider`相当の抽象化がどこにも存在しない
(subscription-cancellation-flow-design.md「1. 解約意図検知時の案内メッセージ」の
`{Stripeカスタマーポータル URL}`は設計文書内の記述例に留まり、prototype/コードとして
実装されていない)。course-set-pashaのURL差し込み方式をそのまま移植すると本venture
未実装の抽象化を持ち込むことになるため、本フェーズではURL差し込みを行わない
(手続き先の案内は既存の解約意図検知フロー〈design.md1節〉に委ねる想定とし、この
簡略化を7節に明記する)。

`render_subscription_cancellation_scheduled_message(period_end_date: Optional[str]) -> str`:
「解約のお手続きを承りました」「今回の請求期間の終了日({period_end_date})までは
引き続きご利用いただけます」「終了日以降は受注内容整理メモ・納品案内・お手入れ案内の
生成がご利用いただけなくなります」「取り消しをご希望の場合は終了日より前にLINEで
その旨をお知らせください」の4点を含む。`period_end_date`が`None`の場合は「今回の
請求期間の終了日まで」という日付なしの表現に差し替える。

`render_subscription_cancellation_rescheduled_message() -> str`:
「解約のお取り消しを承りました」「引き続きご利用いただけます」の2点を含む固定文言
(course-set-pasha版と同じく差し込み情報なし)。

送信先は解約完了通知(フェーズ54)と同じく契約者本人(`contractor_user_id`)に限定する
(subscription-cancellation-flow-design.md「複数職人プラン固有の論点」の権限モデルと
整合させるため)。

## 6. `handle_customer_subscription_updated()`・ディスパッチ側の配線

`stripe_webhook.py`に新規関数`handle_customer_subscription_updated()`を追加する。
`handle_customer_subscription_deleted()`と同じ`invalid`/`unresolved`判定
(2節)を経てworkshop_idを解決した後、3節の前後比較→4節の分類→(no_change以外なら)
5節のメッセージ送信、を行う。

```
@dataclass
class CustomerSubscriptionUpdatedResult:
    workshop_id: Optional[str] = None
    invalid: bool = False
    unresolved: bool = False
    outcome: str = OUTCOME_NO_CHANGE
    notified: bool = False
```

`OUTCOME_NO_CHANGE`時は送信を一切行わず(状態変更も無し、5節)、
`push_client`が`None`の場合も従来通り送信しない(フェーズ54と同じ後方互換方針)。

`receive_stripe_webhook()`が受理するイベント種別に`"customer.subscription.updated"`を
追加し、`handle_customer_subscription_updated()`へディスパッチする。`invalid`時は
`status_code=400`、`unresolved`時は`unresolved_customer=True`とし`status_code=200`
(既存の`customer.subscription.deleted`と同じ扱い、Stripe側への無限リトライを避ける)。

本イベントは`set_subscription_status`等の状態変更を一切伴わない
(course-set-pashaフェーズ156と同じ判断: 書き換え対象のフィールドが本venture側にも
存在しないため)。

## 7. 次の課題

- 5節で述べたとおり、本フェーズでは案内メッセージにStripeカスタマーポータルURL等の
  具体的な手続き先を含めない。実際に「取り消したい」というLINEメッセージを受け取った
  際の処理(解約意図検知〈厳守事項7a〉の応用、または別途の取り消し処理)は本venture
  未設計であり、次の課題として残す。
- course-set-pashaフェーズ157(決済失敗による制限モード中の解約予約との整合)相当の
  ガードは、本venture側に決済失敗ダニング機能自体が無いため対象外のまま(4節)。
- 実LINE Push Message API接続・実Stripe接続はいずれも実アカウント作成
  (オーナー承認待ち)後の課題として引き続き残る。
