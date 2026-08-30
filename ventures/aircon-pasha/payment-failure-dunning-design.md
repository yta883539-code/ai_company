# 決済失敗(カード継続課金エラー)時の案内設計

作成日: 2026-08-28(フェーズ139)

## 背景

line-reservation-aiのpayment-failure-dunning-design.mdは、「トライアル終了時に有料プランを
未選択のまま放置した場合」(休止モード、billing-upgrade-flow-design.md)とは別に、「いったん
有料プランへ加入し継続課金が始まった後、カード期限切れ・利用限度額超過等で毎月の自動課金
自体が失敗するケース」(dunning対応)を扱っている。本ventureにも同種の状態遷移
(trial-end-notification-design.mdの「生成一時停止」)・解約時のデータ削除候補化
(stripe-cancellation-deletion-candidate-trigger-design.md)は既に設計・実装済みだが、
「加入後にカード決済そのものが失敗するケース」はどのドキュメントにも定義がなく、
未検討のまま残っていたため本ドキュメントで整理する。

決済代行サービス自体の契約・実装配線は引き続きオーナー承認待ち(pending-approval.md参照)
のため、本ドキュメントは机上の設計のみを行い、実装・実際の課金は行わない。

## 1. 本venture固有の前提整理(line-reservation-aiとの違い)

line-reservation-aiは「店舗↔顧客」の予約受付という継続的なサービスであり、決済失敗時に
止めるかどうかの対象は「新規予約受付」だった。本ventureは業者からのメモ送信の都度、
単発でLLM生成を行う単方向バッチ処理(README.md)であり、既にトライアル終了後の
未アップグレード状態向けに`_is_generation_paused(profile)` / `GENERATION_PAUSED_MESSAGE`
(trial-end-notification-design.md 4節、フェーズ138実装)という「生成そのものを止める」
仕組みが存在する。決済失敗時に止める対象も同じ「生成」であるため、既存の一時停止判定に
決済失敗由来の理由を追加する形で設計するのが自然で、line-reservation-aiのように
「予約受付」と「確定済み予約・リマインド」を区別する必要はない(本ventureには
「確定済み処理を継続する」という区別対象がそもそも存在しない)。

| | 生成一時停止(既存、trial-end-notification-design.md) | 決済失敗(本ドキュメント) |
|---|---|---|
| 発生条件 | トライアル終了時に一度も有料プランを選択していない | 既に有料プランへ加入済みで、毎月の継続課金が失敗した |
| `UserProfile`の状態 | `trial_end_notified_at`設定済み・`upgraded_at`未設定 | `upgraded_at`設定済み(=一度は加入した)・決済失敗検知済み |
| オーナー(業者)の心理的状態 | 検討中・未決断 | 「払っているつもり」の場合が多く、通知を見落とすと不満につながりやすい |
| 猶予期間中の生成可否 | 不可(即一時停止) | 可(即座に止めない。理由は下記2節) |

decision: 決済失敗は「意図的な未加入」ではなく大半はカード更新のし忘れ等の事務的な理由と
想定されるため、line-reservation-aiと同じく猶予期間を設けたうえで、既存の一時停止機構とは
区別した独立フローとして設計する。

## 2. 再試行(リトライ)方針

line-reservation-aiのpayment-failure-dunning-design.md 5節で確認済みの一次情報
(Stripe Billingのスマートリトライ: 標準設定は最大2週間で最大8回、カスタム設定は
1・3・5・7日間隔で最大3〜4回)をそのまま踏襲する。本venture固有の再検証は不要と判断した。
理由は line-reservation-aiと同じく、自前のリトライスケジュール実装コストに見合う
メリットが薄く(unit-economics-estimate.mdで確認済みの原価構造は同種)、決済代行サービス側の
実績あるロジックを流用する方が安全なため。自前で持つのは「決済失敗イベントをWebhookで
受け取り、`user_profile`の状態を更新し、業者へLINE通知する」部分のみとする。

## 3. 猶予期間と生成可否の扱い

決済失敗検知後、即座に生成を止めない。以下の3段階とする(line-reservation-aiの3段階構成を
「予約受付」→「生成」に読み替え)。

| 段階 | タイミング | 生成可否 |
|---|---|---|
| 1. 通常運用 | 決済成功中 | 可 |
| 2. 猶予期間(`payment_failed`) | 決済失敗検知〜7日間 | 可 |
| 3. 制限モード(`payment_suspended`) | 猶予期間終了後も未解消 | 不可(既存の`_is_generation_paused`相当の分岐を再利用) |

- 猶予期間7日はline-reservation-aiの暫定値(実測データなし)をそのまま踏襲する。両venture
  とも「カード会社への問い合わせ・再登録」という同種の事務作業待ちのため、venture固有の
  再検討は不要と判断した。
- 段階3(制限モード)の生成停止は、実装時に`_is_generation_paused(profile)`の判定条件へ
  「`payment_suspended`状態」も含める(条件のORを1つ増やすだけ)想定とし、
  `GENERATION_PAUSED_MESSAGE`とは別の専用メッセージ(4節)を返す。既存の一時停止ロジックの
  「LLM呼び出し・カウント処理を一切行わず即時案内を返す」という骨格自体は流用し、
  二重に一時停止機構を実装しない。

## 4. 通知文言(業者向け、tone-and-manner-guideline.md準拠)

tone-and-manner-guideline.md方針に従い、宛先は依頼者(施工完了報告の転送先)ではなく
業者本人向けであることを明確にする。ですます調・絵文字不使用、謝罪は「恐れ入りますが」
程度を1回のみ、見出し【】は付けない(フォールバック通知等と同じく、それ自体が独立した
1つの返信として完結する文言のため方針4に従う)。

### 決済失敗検知時(猶予期間開始)

```
お支払いの確認をお願いします。

いつもご利用ありがとうございます。今回のお支払い手続きが完了できませんでした
(カードの有効期限切れ・利用限度額等が考えられます)。

現在、報告文の生成は通常どおりご利用いただけます。
7日以内にお支払い方法をご確認・更新いただけますようお願いします。

▼ お支払い方法を確認する
{決済ページURL}
```

### 猶予期間終了直前(3日前リマインド、1回のみ)

```
お支払い確認のお願い(再送)です。

お支払い手続きが未完了のままです。このままですと3日後に報告文の生成を
一時停止いたします。

▼ お支払い方法を確認する
{決済ページURL}
```

### 制限モード移行時(段階3)

```
お支払い未確認のため、報告文の生成を一時停止しました。

恐れ入りますが、お支払い方法をご確認ください。確認完了後、自動で生成を再開します。

▼ お支払い方法を確認する
{決済ページURL}
```

### 決済成功による復旧時

```
お支払いを確認しました。

お支払い手続きが完了しました。報告文の生成を再開しましたので、
引き続きよろしくお願いします。
```

line-reservation-aiのフェーズ続き115で判明した「猶予期間中に決済が成功した場合は復旧通知の
文言を出し分ける必要がある」という論点(3分岐: 制限モードからの復旧/猶予期間中の完了通知/
状態リセットのみ)は、本ventureでも同様に発生する見込みが高い。ただし本ventureは
`_is_generation_paused`の判定条件を1つ増やすだけの単純な構造のため、この分岐の詳細設計は
`invoice.payment_succeeded`Webhookの受信配線を実装する段階(次回以降)で行うこととし、
本フェーズでは先行して起こりうる論点として書き残すにとどめる。

**(2026-08-28 追記・フェーズ146で対応)** 上記の3分岐を`prototype/payment_recovery_
notification.py`として実装した。line-reservation-aiの`classify_payment_succeeded()`と
同じ考え方で`classify_payment_recovery()`を新設し、`payment_suspended_at`設定済み→
「制限モードからの復旧」(本節のPAYMENT_RECOVERED_MESSAGE、上記文言をそのまま使用)、
`payment_failure_detected_at`未設定→「dunning対象外」(通知なし)、それ以外で
`payment_failure_reminder_sent_at`設定済み→「猶予期間中の完了通知」(新設した
PAYMENT_CONFIRMED_IN_GRACE_MESSAGE、「再開」ではなく「解消」と表現)、いずれでもない→
「状態リセットのみ」(通知なし)の4分類とした。本ventureはline-reservation-aiと異なり
決済失敗検知時(段階1)の通知を実際に送信する配線がまだ存在しないため(本節末尾・6節
「今後の課題」参照)、「猶予期間中に一度でも通知済みか」の判定は`payment_failure_
reminder_sent_at`(本venture唯一の送信済みフラグ)のみで行った。状態リセットは
`payment_failure.py`の`clear_payment_failure_on_success()`をそのまま再利用した。
テスト13件追加、venture全体288件全件パス・schema検証9件パスを確認した。承認不要な
設計・実装・テスト追加のみで、外部サービスへの公開・アカウント作成・支払い等は発生
していないためpending-approval.mdへの追記なし。実際のStripe Webhook受信エンドポイント
からの呼び出し配線、および決済失敗検知時(段階1)通知の実送信配線自体は次回以降の課題
として残る。

## 5. CTA方式(本venture固有)

course-set-pashaのdecision(LIFF URLプレースホルダ埋め込み方式)ではなく、本ventureが
checkout-initiation-flow-design.md(フェーズ131)以降一貫して採用してきたpostback方式の
quick_reply(フェーズ137で確立、`GENERATION_PAUSED_MESSAGE`にも同じ方式を適用済み)を、
上記4節の「お支払い方法を確認する」ボタンにもそのまま適用する想定とする。ただし本ドキュメントの
`{決済ページURL}`はcheckout-initiation-flow-design.mdの新規Checkout Session作成フローとは異なり、
「既存サブスクリプションの支払い方法更新」を行うStripe Customer Portalへの遷移が必要になる
見込みがあり、これはcheckout-initiation-flow-design.mdの新規Checkout Session発行ロジック
(`build_checkout_session_params()`)とは別物になる(Stripe Billing Portalセッション作成が
必要)。

**(2026-08-28 追記・フェーズ142で解消)** この懸案は新規クライアント種別を追加するまでもなく、
本venture既存の`PortalLinkProvider`Protocol(`render_subscription_procedure_notice()`が
解約・プラン変更案内向けに既に使っている、`get_portal_url(user_id) -> Optional[str]`で
Stripe Billing Portalの一時URLを取得する差し替え可能な口)をそのまま再利用することで解消した。
`process_postback_event()`に`portal_link_provider`引数を追加し、`data`が
`UPDATE_PAYMENT_METHOD_POSTBACK_DATA`の場合は`build_checkout_session_params()`/
`checkout_session_client.create()`を経由せず`portal_link_provider.get_portal_url(user_id)`を
呼ぶ分岐とした。詳細は6節・prototype/cloud_function_webhook.py参照。

## 6. 残課題

- ~~`UserProfile`・`UserProfileStoreProtocol`への状態フィールド追加(`payment_failure_detected_at`
  等、フィールド名・型は実装着手時に確定)。~~ → フェーズ140で対応済み。
  `payment_failure_detected_at`・`payment_suspended_at`の2フィールドを追加した
  (prototype/user_id_linking.py)。
- ~~`stripe_dispatch.py`の`dispatch_stripe_event()`への`invoice.payment_failed`・
  `invoice.payment_succeeded`イベント種別の追加~~ → フェーズ140で対応済み。
  新規`prototype/payment_failure.py`(deletion_candidate.pyと同じ位置づけの薄いProtocol・
  純粋関数)を追加し、`dispatch_stripe_event()`に`payment_store`引数(省略時はこれまで
  通り`ignored_types`扱い、後方互換)を追加して2イベント種別を振り分けるようにした。
  `invoice.payment_failed`→`mark_payment_failure_detected()`(`payment_failure_
  detected_at`に検知時刻を記録、猶予期間の日数判定自体はスケジューラ未実装のためまだ
  行わない)、`invoice.payment_succeeded`→`clear_payment_failure_on_success()`
  (`payment_failure_detected_at`・`payment_suspended_at`の両方をクリア)とした。
  テスト15件追加(test_payment_failure.py 8件・test_stripe_dispatch.py 7件)、
  venture全体235件全件パスを確認した。承認不要な設計・実装・テスト追加のみで、
  外部サービスへの公開・アカウント作成・支払い等は発生していないためpending-approval.md
  への追記なし。
- ~~`_is_generation_paused(profile)`の判定条件拡張(制限モード状態を含める)、および
  制限モード専用メッセージの`process_memo_event()`への配線。~~ → フェーズ141で対応済み。
  course-set-pashaフェーズ140の`_is_payment_suspended()`と同じ考え方で、
  `_is_generation_paused()`を直接拡張するのではなく別関数`_is_payment_suspended(profile)`
  として新設し(判定条件が`upgraded_at`の有無で排他的なため、既存関数への条件追加より
  責務を分けた方が安全と判断)、`process_memo_event()`に`PAYMENT_SUSPENDED_MESSAGE`を
  返す分岐(`MemoProcessResult.payment_suspended`)として配線した。ただしcourse-set-pasha
  (検知時刻+猶予日数から都度算出、スケジューラ不要)とは異なり、本ventureは既存の
  `payment_suspended_at`フィールド(フェーズ140で追加済み)の設定有無で判定する設計の
  ままとした。このためスケジューラ未実装の現時点では`payment_suspended_at`を書き込む
  経路がまだ存在せず、制限モード応答は実際にはまだ発火しない(判定ロジック・応答文言・
  テストのみ先行整備)。CTAボタンの遷移先(Stripe Customer Portal)はpostback_data
  (`action=update_payment_method`)を仮に用意したのみで、`process_postback_event()`側の
  実処理配線は次項と合わせて次回以降の課題として残した。テスト4件追加、venture全体239件
  全件パス・schema検証9件パスを確認した。承認不要な設計・実装・テスト追加のみで、
  外部サービスへの公開・アカウント作成・支払い等は発生していないためpending-approval.md
  への追記なし。
- ~~5節で触れたStripe Customer Portal(支払い方法更新用URL発行)の要否・実装方式の検討。~~
  → フェーズ142で対応済み。新規クライアント種別は不要で、既存の`PortalLinkProvider`
  (`render_subscription_procedure_notice()`と共有)を再利用する形で解消した。
  `process_postback_event()`に`portal_link_provider`引数を追加し、
  `UPDATE_PAYMENT_METHOD_POSTBACK_DATA`受信時は`portal_link_provider.get_portal_url(user_id)`
  を呼び、未接続・取得失敗時は`PORTAL_LINK_UNAVAILABLE_FALLBACK`を返す(URL取得に失敗した
  ことをボタンをタップした業者に無反応で示すのではなく、既存のフォールバック文言で明示する
  方針)。テスト5件追加(process_postback_event向け4件・dispatch_webhook_events向け1件)、
  venture全体244件全件パス・schema検証9件パスを確認した。承認不要な設計・実装・テスト
  追加のみで、外部サービスへの公開・アカウント作成・支払い等は発生していないため
  pending-approval.mdへの追記なし。
- ~~猶予期間終了直前リマインドを送信するスケジューラ(trial-end-scheduler-design.mdの
  日次バッチと同種の仕組みを流用できる見込みだが、本ドキュメントでは未検討)。~~ →
  フェーズ143で対応済み。payment-failure-reminder-scheduler-design.md新規作成、
  trial-end-scheduler-design.mdと同じ全体構成(Cloud Scheduler日次バッチ→抽出→Flex
  Message送信→フラグ書き込み)を踏襲した。新規フィールド`payment_failure_reminder_sent_at`
  をuser_id_linking.pyに追加し、`prototype/payment_failure_reminder_scheduler.py`に
  `select_due_payment_failure_reminders()`(検知から4日=猶予期間7日-3日経過で対象)・
  `build_payment_failure_reminder_flex_message()`(ボタンは既存の
  `UPDATE_PAYMENT_METHOD_BUTTON_LABEL`/`UPDATE_PAYMENT_METHOD_POSTBACK_DATA`を再利用)・
  `send_payment_failure_reminders()`を実装した。あわせて`clear_payment_failure_on_success()`
  が新フィールドもクリアするよう拡張し(決済成功後に再度失敗した際もリマインドが送れる
  ようにするため)、テスト19件追加(payment_failure_reminder_scheduler向け13件・
  payment_failure向け2件・user_id_linking向け4件)、venture全体263件全件パス・
  schema検証9件パスを確認した。承認不要な設計・実装・テスト追加のみで、外部サービスへの
  公開・アカウント作成・支払い等は発生していないためpending-approval.mdへの追記なし。
- ~~決済失敗検知時(段階1)通知の実送信配線~~ → フェーズ147で対応済み。
  `prototype/payment_failure.py`に`handle_payment_failure_detected()`を新設し、design 4節
  「決済失敗検知時(猶予期間開始)」の文言をFlex Message化(`build_payment_failure_
  detected_flex_message()`、既存の`UPDATE_PAYMENT_METHOD_BUTTON_LABEL`/`_POSTBACK_DATA`
  ボタンを再利用)して送信し、送信成功時のみ`mark_payment_failure_detected()`で状態を
  書き込む設計とした(`handle_payment_succeeded()`と対称に、送信失敗時は状態を変更せず
  Webhookリトライに委ねる)。`stripe_dispatch.py`の`dispatch_stripe_event()`に
  `push_client`引数(省略時はこれまで通り状態書き込みのみで通知なし、後方互換)を追加し、
  `invoice.payment_failed`受信時に配線した。テスト6件追加(test_payment_failure.py 4件・
  test_stripe_dispatch.py 2件)、venture全体294件全件パス・schema検証9件パスを確認した。
  承認不要な設計・実装・テスト追加のみで、外部サービスへの公開・アカウント作成・支払い等は
  発生していないためpending-approval.mdへの追記なし。なお`invoice.payment_succeeded`側の
  復旧通知(`handle_payment_succeeded()`、フェーズ146で実装済みだが`dispatch_stripe_event()`
  への配線は未着手のまま)は、モジュールごとに`LinePushDeliveryError`を別クラスとして
  定義している既存の慣習上、本フェーズの`push_client`とは別の配線検討が必要なため、
  ~~次回以降の課題として残した。~~ → フェーズ148で対応済み。`dispatch_stripe_event()`に
  `recovery_push_client`引数(`payment_recovery_notification.LinePushClient`と同名だが
  別クラスの、既存の慣習を踏襲した専用Protocol)を追加し、`invoice.payment_succeeded`
  受信時に`payment_store`から読み取った現在状態を`PaymentFailureReminderUserState`へ
  詰め替えて`handle_payment_succeeded()`へ委譲する形で解消した(未指定時は従来通り
  `clear_payment_failure_on_success()`を直接呼ぶのみで後方互換)。さらにフェーズ149では
  実HTTPエントリポイント(`stripe_webhook.py`の`receive_stripe_webhook()`)が
  `payment_store`・`push_client`・`recovery_push_client`の3引数を`dispatch_stripe_event()`
  へ委譲せず握りつぶしていた配線漏れも解消済み。テスト・コード変更は既存フェーズで
  完了済みのため、本フェーズ(154)はこのドキュメント記載漏れの反映のみ。
- ~~`cloud_function_webhook.py`の`_is_payment_suspended()`直前のコメントが「スケジューラ
  自体は次回以降の課題として未実装」のまま残っていた(フェーズ145で`payment_suspension_
  scheduler.py`のsend_payment_suspensions()として実装済みだったのに更新漏れ)。~~ →
  フェーズ155で対応済み。コメントをフェーズ145実装済みの旨に更新し、あわせて
  `test_payment_suspension_scheduler.py`のテストがローカル定義のスタブストアのみを
  使っており、`send_payment_suspensions()`が書き込む`payment_suspended_at`と
  `_is_payment_suspended()`が読む`payment_suspended_at`が実際に同一の
  `InMemoryUserProfileStore`経由でつながることを確認する結線テストが存在しなかった
  (フェーズ149のstripe_webhook.py・フェーズ153のtrial_end_scheduler.pyと同種の抜け)ため、
  `test_cloud_function_webhook.py`に`PaymentSuspensionSchedulerToPaymentSuspendedWiringTest`
  を新設した(制限モード応答への切り替わり確認・猶予期間未経過ユーザーは切り替わらない
  ことの確認、テスト2件)。venture全体318件全件パス・schema検証9件パスを確認した。
- 実際のWebhook受信・Firestore書き込み・LINE送信配線、決済代行サービスとの契約自体は
  引き続きオーナー承認待ち(pending-approval.md参照)。
- 猶予期間7日・リマインド1回のみという値は、line-reservation-aiと同じく実測データの
  無い暫定値のまま。
