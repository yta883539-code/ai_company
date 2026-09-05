# 解約確定・解約予約(cancel_at_period_end)受理/取り消し通知設計

フェーズ184。course-set-pashaのsubscription-cancelled-notification-design.md(フェーズ155)・
subscription-cancellation-scheduled-notification-design.md(フェーズ156)を本ventureへ横展開する。

## 1. 発見した記載漏れ

course-set-pashaのフェーズ157「次にやること(候補)」に、本venture(aircon-pasha)・
line-reservation-aiが将来この通知を実装する際は同種の判定ロジックを横展開する旨の記載が
残っていた。実際に本ventureの現状を確認したところ、次の2つの顧客向けLINE通知がいずれも
未実装であることが判明した。

- `customer.subscription.deleted`(契約終了)受信時の解約完了案内。
  `stripe_dispatch.dispatch_stripe_event()`の`_SUBSCRIPTION_DELETED`分岐は削除候補化
  (`deletion_candidate.py`)・`current_plan_id`クリア(`plan_store`)・
  `blocked_but_billing_owner_notified_at`クリア(`blocked_but_billing_store`)のみを行い、
  業者本人への通知は一切送っていなかった。
- `customer.subscription.updated`受信時の`cancel_at_period_end`変化(解約予約受理・
  解約取り消し)案内。`_SUBSCRIPTION_UPDATED`分岐は`status`による削除候補クリアと
  `plan_store`同期のみを行い、`previous_attributes`との比較自体を行っていなかった。

`stripe-cancellation-deletion-candidate-trigger-design.md`・
`subscription-cancellation-flow-design.md`のいずれにもLINE通知配線への言及は無く、
新規の記載漏れ(未着手のまま候補にすら挙がっていなかった)と判断した。

## 2. 本ventureの通知チャネル

course-set-pashaはLINE公式アカウントのReply/Push双方でプレーンテキストを送るが、本venture
(aircon-pasha)は既存の全通知モジュール(`payment_failure.py`・
`payment_recovery_notification.py`・`payment_failure_reminder_scheduler.py`・
`trial_end_scheduler.py`等)が一貫して`LinePushClient.send_flex_message(user_id, alt_text,
contents)`によるFlex Message送信のみを使っている(プレーンテキストの`send_message()`は
使わない)。本モジュールもこの既存パターンに合わせ、`payment_recovery_notification.
_build_flex_message()`と同じ「bodyテキストのみのシンプルなbubble」形式で送る
(CTAボタンは付けない。解約予約受理案内はポータルURLへの案内文言を本文中に含める形とし、
`payment_recovery_notification.py`と同様ボタン化はしない。理由: ポータルURLはbit.ly等の
短縮リンクではなく都度発行のセッションURLで、既存の`format_payment_portal_reply_message()`
(`cloud_function_webhook.py`)も本文埋め込み形式のため一貫性を優先した)。

## 3. classify_cancel_at_period_end_change()

course-set-pashaのフェーズ156をそのまま踏襲する。本ventureも`suspension_reason`相当の
複数休止要因の区別を持たないため(`payment_suspended_at`の設定有無のみ)、
line-reservation-aiのようなガード条件は不要。

```
before=False, after=True  -> OUTCOME_CANCELLATION_SCHEDULED (解約予約受理)
before=True,  after=False -> OUTCOME_CANCELLATION_RESCHEDULED (解約取り消し)
それ以外                    -> OUTCOME_NO_CHANGE (通知しない)
```

`previous_attributes`に`cancel_at_period_end`キーが無い場合(この属性が変化していない
イベント)は変化なしとして扱う(`stripe_dispatch.py`側で判定、design 5節参照)。

## 4. メッセージ文言

`SUBSCRIPTION_CANCELLED_MESSAGE`(`customer.subscription.deleted`向け)は
course-set-pashaの文言を本venture固有の業務内容(「投稿文の生成」→「作業完了報告・
お手入れ案内の生成」)に翻案する。

```
契約終了のご案内

ご契約が終了しました。ご利用ありがとうございました。
本日以降、作業完了報告・お手入れ案内の生成はご利用いただけません。

またのご利用をお待ちしております。再開をご希望の際は、いつでも新規契約と
同じお手続きでお申し込みいただけます。
```

`SUBSCRIPTION_CANCELLATION_RESCHEDULED_MESSAGE`(解約取り消し向け、差し込み情報なし):

```
解約のお取り消しを承りました

解約のお取り消しを承りました。引き続きご利用いただけます。

ご不明な点がございましたら、本トークルームに質問内容をメッセージでお送りください。
```

(course-set-pashaは「このトークルームへご返信ください」だが、本ventureのLINE公式
アカウントは業者からのフリーテキスト返信をトリガーに投稿文生成を行う設計〈LLMシステム
プロンプト〉のため、返信を促す文言は生成フローと混同を招く。当初は「トライアル終了案内・
生成一時停止のメッセージに記載のお問い合わせ先までご連絡ください」という暫定文言としたが、
フェーズ188でtrial_end_scheduler.py・payment_suspension_scheduler.py・
cloud_function_webhook.pyのPAYMENT_SUSPENDED_MESSAGEを確認した結果、いずれもFlex
Messageのボタン誘導のみでお問い合わせ先の記載自体が存在せず、この参照が事実と異なる
不整合だったと判明した。本ventureのLLMシステムプロンプトはstatus=cancellation_intent/
downgrade_intent/cancellation_unclearとしてトークルームへの自由文の請求関連の質問を
既に処理できる(render_subscription_procedure_notice、5節参照)ため、「返信」ではなく
「質問内容をメッセージで送る」という表現にすることで、生成フロー〈業務報告の投稿〉との
混同を避けつつ実際に機能する問い合わせ導線を案内する文言へ修正した。)

`SUBSCRIPTION_CANCELLATION_SCHEDULED_MESSAGE`(解約予約受理向け、`period_end_date`・
ポータルURLを差し込む):

```
解約のお手続きを承りました

解約のお手続きを承りました。以下の点をご確認ください。

・ご利用は今回の請求期間の終了日({period_end_date})まで通常通り継続します
  (作業完了報告・お手入れ案内の生成に制限はありません)
・終了日以降は作業完了報告・お手入れ案内の生成がご利用いただけなくなります
・日割りでの返金は行っておりません

解約を取り消したい場合は、終了日より前であれば下記からお手続きが可能です。

▼ お手続きはこちら
{PORTAL_LINK_PLACEHOLDER}

またのご利用をお待ちしております。
```

`period_end_date`は`current_period_end`(Unixタイムスタンプ)をJSTの`YYYY-MM-DD`形式へ
変換する(course-set-pashaと同じ`_format_period_end_date_jst()`、数値でない・bool・
欠落時は`None`扱いで日付なし表現「今回の請求期間の終了日まで」へフォールバック)。

ポータルURLの差し込みは`cloud_function_webhook.PORTAL_LINK_PLACEHOLDER`+
`PORTAL_LINK_UNAVAILABLE_FALLBACK`方式を再利用する(`format_payment_portal_reply_
message()`と同じ2定数)。

**本フェーズのスコープ外だった項目(次回以降の課題、design 6節参照)**: course-set-pasha
フェーズ157(subscription-cancellation-scheduled-message-suspension-consistency-
design.md)で対応した「決済失敗による制限モード中に解約予約を行った場合、上記の『生成に
制限はありません』が事実と矛盾する」というギャップは、本ventureにも`payment_suspended_at`
という同種の状態が存在するため同じ問題が起こりうる。本フェーズ(184)はまず通知そのものの
新規実装を優先し、制限モード整合性チェックは次フェーズ以降に横展開する方針としたが、
フェーズ185で対応済み(本venture版subscription-cancellation-scheduled-message-
suspension-consistency-design.md参照)。

## 5. `stripe_dispatch.py`への配線

`dispatch_stripe_event()`に新規引数`cancellation_push_client`
(`subscription_cancellation_notification.LinePushClient`、省略時`None`)・
`portal_link_provider`(`cloud_function_webhook.PortalLinkProvider`、省略時`None`)を追加する。
既存の`payment_store`等と同じ「未指定時は何もしない後方互換」方針を踏襲する。

- `_SUBSCRIPTION_DELETED`分岐: `cancellation_push_client`指定時、既存の削除候補化・
  `plan_store`/`blocked_but_billing_store`処理の後に
  `handle_subscription_cancelled(user_id, cancellation_push_client)`を呼び、
  `notified`の成否を`StripeDispatchResult`の`cancellation_notified_user_ids`/
  `cancellation_notification_failed_user_ids`へ記録する。
- `_SUBSCRIPTION_UPDATED`分岐: `cancellation_push_client`指定時、
  `event["data"].get("previous_attributes", {})`から`cancel_at_period_end`の前後比較を
  行う。`previous_attributes`にキーが無ければ変化なしとしてスキップする(design 3節)。
  変化があれば`handle_subscription_cancellation_update(user_id, before, after,
  data_object.get("current_period_end"), cancellation_push_client, portal_link_provider)`
  を呼び、結果を`cancellation_scheduled_notified_user_ids`/
  `cancellation_rescheduled_notified_user_ids`/
  `cancellation_update_notification_failed_user_ids`へ記録する。既存の`status`による
  削除候補クリア・`plan_store`同期とは独立した処理のため互いの結果に影響しない
  (course-set-pashaフェーズ156と同じ設計判断)。

`stripe_webhook.receive_stripe_webhook()`(実HTTPエントリポイント)への配線は、
`payment_store`等の先例(フェーズ139→149のように後続フェーズで追加)にならい、
本フェーズでは`dispatch_stripe_event()`単体の実装・検証にとどめ、次回以降の課題として残す。

## 6. 残課題

- ~~制限モード中(`payment_suspended_at`設定済み)の解約予約受理案内の文言整合性チェック
  (course-set-pashaフェーズ157の横展開)。~~ → フェーズ185で対応済み
  (subscription-cancellation-scheduled-message-suspension-consistency-design.md参照)。
- ~~`stripe_webhook.receive_stripe_webhook()`への`cancellation_push_client`/
  `portal_link_provider`引数の配線(実HTTPエントリポイント経由での検証)。フェーズ185時点で
  未着手のまま残っている。~~ → フェーズ186で対応済み(`prototype/stripe_webhook.py`の
  `receive_stripe_webhook()`に両引数を追加し`dispatch_stripe_event()`へそのまま委譲済み。
  同ファイル57・331行のdocstring参照)。
- ~~解約取り消し案内メッセージの問い合わせ導線文言の見直し(design 4節参照)。~~ →
  フェーズ188で対応済み。事実と異なる参照(トライアル終了案内・生成一時停止メッセージに
  お問い合わせ先の記載があるという誤った前提)を修正し、実際に機能する
  cancellation_unclear等の自由文問い合わせ導線を案内する文言へ変更した(4節参照)。
- 実LINE Push Message API・実Stripeアカウント接続はオーナー承認待ち(pending-approval.md
  参照)。
