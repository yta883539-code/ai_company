# 決済失敗(カード継続課金エラー)時の案内設計

作成日: 2026-08-28(フェーズ117)

## 背景

line-reservation-aiのpayment-failure-dunning-design.md、およびそれを本venture固有の
前提へ翻案したaircon-pashaのpayment-failure-dunning-design.md(2026-08-28フェーズ139)は、
いずれも「トライアル終了時に有料プランを未選択のまま放置した場合」(本venture用語では
trial-end-notification-design.md 4節の「生成一時停止」)とは別に、「いったん有料プランへ
加入し継続課金が始まった後、カード期限切れ・利用限度額超過等で毎月の自動課金自体が
失敗するケース」(dunning対応)を扱っている。本ventureにも「生成一時停止」機構
(フェーズ114実装済み、`_is_generation_paused()`/`GENERATION_PAUSED_MESSAGE`)・解約時の
データ削除候補化(フェーズ91・stripe-cancellation-deletion-candidate-trigger-design.mdで
既に設計済み。本ドキュメント作成時点(フェーズ117)で「本venture未着手」と誤記していたが、
実際には本venture自身の既存ドキュメントであり誤り)は存在するが、「加入後にカード決済
そのものが失敗するケース」はどのドキュメントにも定義がなく未検討のまま残っていたため、
aircon-pashaと同様に本ドキュメントで整理する。

決済代行サービス自体の契約・実装配線は引き続きオーナー承認待ち(pending-approval.md参照)
のため、本ドキュメントは机上の設計のみを行い、実装・実際の課金は行わない。

## 1. 本venture固有の前提整理(aircon-pashaとの違い)

aircon-pashaのpayment-failure-dunning-design.md 1節は、`UserProfile`という単一の
データクラスに`upgraded_at`等のフィールドを持たせる設計を前提にしていた。本ventureは
`usage_counter`という`UsageCounterProtocol`(`get_trial_end_notified_at()`/
`get_upgraded_at()`/`set_upgraded_at()`等のメソッド群)を注入依存として扱う設計
(フェーズ103・105・114)のため、決済失敗由来の状態も新規フィールドではなく
`UsageCounterProtocol`への追加メソッド(`get_payment_failure_detected_at()`/
`set_payment_failure_detected_at()`/`clear_payment_failure_detected_at()`等、
実装着手時に確定)として設計するのが一貫性がある。

またCTA方式もaircon-pashaのpostback方式quick_replyではなく、本ventureが
checkout-initiation-flow-design.md(フェーズ98)以降一貫して採用しているLIFF経由の
Checkout Session作成導線(`LIFF_URL_PLACEHOLDER`をトライアル終了通知
(trial-end-notification-design.md 3節)と同じ形でメッセージ本文に埋め込む方式)を
踏襲する。本ventureはpostbackボタンではなくプレーンテキスト内のリンクとして案内する
点がaircon-pashaと異なる。

| | 生成一時停止(既存、trial-end-notification-design.md) | 決済失敗(本ドキュメント) |
|---|---|---|
| 発生条件 | トライアル終了時に一度も有料プランを選択していない(`get_trial_end_notified_at()`設定済み・`get_upgraded_at()`未設定) | 既に有料プランへ加入済み(`get_upgraded_at()`設定済み)で、毎月の継続課金が失敗した |
| 生成可否 | 不可(即一時停止) | 可(即座に止めない。理由は下記2節) |
| オーナー(セッター・ジムオーナー)の心理的状態 | 検討中・未決断 | 「払っているつもり」の場合が多く、通知を見落とすと不満につながりやすい |

decision: 決済失敗は「意図的な未加入」ではなく大半はカード更新のし忘れ等の事務的な理由と
想定されるため、line-reservation-ai・aircon-pashaと同じく猶予期間を設けたうえで、
既存の一時停止機構とは区別した独立フローとして設計する。

## 2. 再試行(リトライ)方針

line-reservation-aiのpayment-failure-dunning-design.md 5節で確認済みの一次情報
(Stripe Billingのスマートリトライ: 標準設定は最大2週間で最大8回、カスタム設定は
1・3・5・7日間隔で最大3〜4回)をそのまま踏襲する。unit-economics-estimate.mdで
確認済みの原価構造は他ventureと同種であり、本venture固有の再検証は不要と判断した。
自前で持つのは「決済失敗イベントをWebhookで受け取り、`usage_counter`の状態を更新し、
セッター・ジムオーナーへLINE通知する」部分のみとする。

## 3. 猶予期間と生成可否の扱い

決済失敗検知後、即座に生成を止めない。以下の3段階とする(line-reservation-ai・
aircon-pashaと同じ「猶予期間7日」を暫定値として踏襲)。

| 段階 | タイミング | 生成可否 |
|---|---|---|
| 1. 通常運用 | 決済成功中 | 可 |
| 2. 猶予期間(`payment_failed`) | 決済失敗検知〜7日間 | 可 |
| 3. 制限モード(`payment_suspended`) | 猶予期間終了後も未解消 | 不可(既存の`_is_generation_paused()`相当の分岐を再利用) |

- 猶予期間7日は他venture共通の暫定値(実測データなし)をそのまま踏襲する。venture固有の
  再検討は不要と判断した。
- 段階3(制限モード)の生成停止は、実装時に`_is_generation_paused()`の判定条件へ
  「`payment_suspended`状態」も含める(条件のORを1つ増やすだけ)想定とし、
  `GENERATION_PAUSED_MESSAGE`とは別の専用メッセージ(4節)を返す。既存の一時停止ロジックの
  「LLM呼び出し・トライアル生成回数カウントのいずれも行わず定型文を返す」という骨格自体は
  流用し、二重に一時停止機構を実装しない。

## 4. 通知文言(ですます調・絵文字不使用、本venture単一トーン)

本ventureはmessage-tone-variants.md相当の複数トーン切り替えを導入していない
(trial-end-notification-design.md 3節の既存注記の通り)ため、以下は単一文言のみ用意する。
宛先はジムオーナー・フリーランスセッター本人。

### 決済失敗検知時(猶予期間開始)

```
[コースセットパシャッと] お支払いの確認をお願いします

いつもご利用ありがとうございます。
今回のお支払い手続きが完了できませんでした
(カードの有効期限切れ・利用限度額等が考えられます)。

現在、投稿文の生成は通常どおりご利用いただけます。
7日以内にお支払い方法をご確認・更新いただけますようお願いします。

▼ お支払い方法を確認する
[LIFF経由の決済導線リンク]
```

### 猶予期間終了直前(3日前リマインド、1回のみ)

```
[コースセットパシャッと] お支払い確認のお願い(再送)

お支払い手続きが未完了のままです。
このままですと3日後に投稿文の生成を一時停止いたします。

▼ お支払い方法を確認する
[LIFF経由の決済導線リンク]
```

### 制限モード移行時(段階3)

```
[コースセットパシャッと] 投稿文の生成を一時停止しました

お支払い手続きが確認できないため、投稿文の生成を一時停止しました。
お支払い方法をご確認いただければ、確認完了後に自動で生成を再開します。

▼ お支払い方法を確認する
[LIFF経由の決済導線リンク]
```

### 決済成功による復旧時(3分岐、フェーズ121で確定)

line-reservation-aiのフェーズ続き115・aircon-pashaのフェーズ146と同じ考え方で、
`invoice.payment_succeeded`受信時は以下の3分岐で通知文言を出し分ける(状態のみリセットし
通知を送らない「状態リセットのみ」を加えると実質4分岐)。本ventureは`payment_suspended_at`
のような別立ての状態フラグを持たず、制限モード(段階3)は検知時刻からの経過日数で都度算出する
設計(3節)のため、分岐の判定にはevent受信時刻(`now`相当)と`payment_failure_detected_at`の
差分を用いる(aircon-pashaが`payment_suspended_at is not None`という保存済みフラグで
判定するのと異なり、本ventureは都度計算する点が実装上の相違点)。

| 分岐 | 判定条件 | 文言 |
|---|---|---|
| 1. 制限モードからの復旧 | `payment_failure_detected_at`設定済み かつ (`now - payment_failure_detected_at`) ≧ 猶予期間(7日) | 「再開しました」 |
| 2. 猶予期間中の解消 | `payment_failure_detected_at`設定済み・上記に該当せず、かつ`payment_failure_reminder_sent_at`設定済み(リマインド受信後) | 「解消されました」 |
| 3. 状態リセットのみ | `payment_failure_detected_at`設定済み・上記いずれにも該当せず(検知はされたがリマインド未送信、生成も止まっていない) | 通知なし、状態のみクリア |
| 4. 対象外 | `payment_failure_detected_at`未設定(通常の毎月課金成功) | 何もしない |

分岐1(制限モードからの復旧、生成が実際に止まっていた)は「再開しました」、分岐2(猶予期間中で
生成は止まっていない)は「再開」ではなく「解消されました」と表現を分ける
(GENERATION_PAUSED_MESSAGE等と同じ「実際には止まっていないものを止まっていたかのように
書かない」という配慮、line-reservation-ai・aircon-pashaと同じ判断)。

```
[コースセットパシャッと] お支払いを確認しました  ← 分岐1(制限モードからの復旧)

お支払い手続きが完了しました。ご不便をおかけしました。
投稿文の生成を再開しましたので、引き続きよろしくお願いします。
```

```
[コースセットパシャッと] お支払いを確認しました  ← 分岐2(猶予期間中の解消)

先日ご案内したお支払いに関するご確認事項は解消されました。
投稿文の生成は引き続きご利用いただけますので、このままご利用ください。
```

実装は`prototype/payment_recovery_notification.py`(フェーズ121)の`classify_payment_recovery()`・
`handle_payment_succeeded()`参照。

**(2026-08-31 追記・フェーズ136で記載訂正)** 直前の「`invoice.payment_succeeded`受信時の
実際の呼び出し配線(`stripe_webhook.py`の`dispatch_stripe_event()`は現状、通知を送らず
状態クリアのみを行う実装〈フェーズ119〉のままであり、本モジュールへの差し替えは次回以降の
課題として残る)」という記載は、実際にはフェーズ122(`dispatch_stripe_event()`への
`push_client`引数追加、`invoice.payment_succeeded`受信時に`handle_payment_succeeded()`へ
委譲する配線)で既に対応済みだったにもかかわらず未訂正のまま残っていた記載漏れ
(下記6節フェーズ122の記載、およびフェーズ127・132・133と同種のドキュメント整合性
メンテナンス)。実装は`stripe_webhook.py` `dispatch_stripe_event()`の
`invoice.payment_succeeded`分岐(`push_client is not None`時に`handle_payment_succeeded()`へ
委譲)、および`test_stripe_webhook.py`の関連テストで検証済みであることを確認した。

## 5. CTAリンクの実装課題(本venture固有)

trial-end-notification-design.md 3節のCTAリンクは「LIFF経由のCheckout Session作成導線
(新規サブスクリプション申込)」であり、`build_checkout_session_params()`
(checkout-session-endpoint-design.md)が発行する新規Checkout Sessionを前提にしている。
一方、決済失敗からの復旧に必要なのは「既存サブスクリプションの支払い方法更新」であり、
これは新規Checkout Session発行とは別物のStripe Customer Portal(Billing Portal)
セッション作成が必要になる見込みがある(aircon-pashaフェーズ139・5節で指摘済みの論点と
同種)。本ventureはLIFF方式を既にCTA全般の標準としているため、Customer Portalへの遷移リンクも
同じLIFFアプリ内から`liff.getIDToken()`で取得したuser_idを使って発行する設計に揃えられる
見込みが高いが、Portalセッション作成エンドポイント自体の設計は次回以降の課題として残す。

**(2026-09-03 追記・フェーズ148で対応)** Portalセッション作成エンドポイント自体の設計を
customer-portal-session-endpoint-design.md(新規)で行い、`prototype/portal_session.py`に
`create_portal_session()`・`build_portal_session_params()`・`main(request)`を実装した
(checkout-session-endpoint-design.md・`checkout_session.py`と対称の構成)。既存
`stripe_customer_id`を持たないuser_idへの誤発行を防ぐガード(404・`no_stripe_customer`)を
新設した点がCheckout Session版との差分。`PortalLinkProvider`の実装本体(実
`stripe.billing_portal.Session.create()`呼び出し)は引き続きオーナー承認待ちの課題として
残る(詳細はcustomer-portal-session-endpoint-design.md 6節)。

**(2026-08-29 追記・フェーズ123で一部対応)** 「制限モード移行時(段階3)」の応答文言
(`PAYMENT_SUSPENDED_MESSAGE`)については、既存の`PortalLinkProvider`Protocolを再利用する
形で本節の懸念を解消した。詳細は6節参照。

**(2026-08-29 追記・フェーズ126で対応)** 3日前リマインド(`payment_failure_reminder_
scheduler.py`)も同じ`PortalLinkProvider`を再利用する形で対応した。詳細は6節参照。

**(2026-08-30 追記・フェーズ続き132で記載訂正)** 直前の「決済失敗検知時通知(猶予期間開始時の
初回案内)は未対応のまま残る」という記載は、実際にはフェーズ124(`stripe_webhook.py`
`dispatch_stripe_event()`の`invoice.payment_failed`受信時に
`payment_recovery_notification.handle_payment_failure_detected()`経由で実送信する配線)・
フェーズ127(同通知への`portal_link_provider`差し込み)で既に対応済みだったにもかかわらず
未訂正のまま残っていた記載漏れ。`test_stripe_webhook.py`の
`test_marks_payment_failure_detected_when_customer_resolves`以下の一連のテスト、および
`test_portal_link_provider_is_substituted_into_notification`・
`test_no_portal_link_provider_sends_fallback_message`で実送信配線・ポータルURL差し込みの
両方が検証済みであることを確認した。残るのは`PortalLinkProvider`実装側
(`stripe.billing_portal.Session.create()`相当の実Stripe接続)のみで、これは引き続き
オーナー承認待ち(pending-approval.md参照)。

## 6. 残課題

- (解消済み 2026-08-28 10:00 UTC・フェーズ118: `UsageCounterProtocol`への状態管理メソッド
  `get_payment_failure_detected_at()`/`set_payment_failure_detected_at()`/
  `clear_payment_failure_detected_at()`を`cloud_function_webhook.py`に追加し、
  `InMemoryUsageCounter`にも実装した。あわせて`_is_payment_suspended()`
  (検知時刻からPAYMENT_FAILURE_GRACE_PERIOD_DAYS=7日以上経過したかを都度算出、
  別立ての状態フラグは追加しない設計とした)を新設し、`process_memo_event()`に
  `PAYMENT_SUSPENDED_MESSAGE`を返す分岐として配線した。テスト7件追加、
  venture全体334件全件パス・schema検証9件パスを確認した。次点はStripe側の
  実際のイベント受信配線〈下記2点目〉)
- (解消済み 2026-08-28 14:00 UTC・フェーズ119: Stripe Webhookイベントディスパッチ機構
  (`stripe_webhook.py`の`dispatch_stripe_event()`)へ`invoice.payment_failed`・
  `invoice.payment_succeeded`の2イベント種別ハンドラを追加した。`usage_counter`引数
  (未指定時は`ignored_types`扱いの後方互換オプトイン、aircon-pashaの`payment_store`引数と
  同じ方針)を新設し、`invoice.payment_failed`受信時は`set_payment_failure_detected_at()`、
  `invoice.payment_succeeded`受信時は`get_payment_failure_detected_at()`が非nullの
  場合のみ`clear_payment_failure_detected_at()`を呼ぶ設計とした。`receive_stripe_
  webhook()`からも`usage_counter`を委譲するよう配線済み。テスト9件追加、venture全体
  343件全件パス・schema検証9件パスを確認した)
- (解消済み 2026-08-28 10:00 UTC・フェーズ118: `_is_generation_paused()`本体は変更せず、
  同じ設計思想の`_is_payment_suspended()`を別関数として新設する形で判定条件を追加した
  〈両者は「既に有料転換済みか否か」で前提条件が排他的なため、1つの関数に統合するより
  責務を分けた方が明確と判断〉。制限モード専用メッセージ`PAYMENT_SUSPENDED_MESSAGE`の
  `process_memo_event()`への配線もあわせて完了した)
- ~~5節で触れたStripe Customer Portal(支払い方法更新用URL発行)の要否・実装方式の検討。~~
  → フェーズ123で対応済み。既存の`PortalLinkProvider`(`render_subscription_procedure_
  notice()`が解約・ダウングレード案内向けに既に使用)をそのまま再利用できると判明し、
  新規クライアント種別は不要と判断した(aircon-pashaフェーズ142と同じ結論)。
  `cloud_function_webhook.py`に`render_payment_suspended_message(portal_link_provider,
  user_id)`を新設し、`PAYMENT_SUSPENDED_MESSAGE`の`PORTAL_LINK_PLACEHOLDER`
  (従来は誤って新規Checkout用の`LIFF_URL_PLACEHOLDER`を埋め込んでいた)を実URLへ
  置換する。providerが未接続・user_id不明・URL取得失敗のいずれかの場合は
  `PORTAL_LINK_UNAVAILABLE_FALLBACK`へ全文差し替える(`render_subscription_procedure_
  notice()`と同じ契約)。`process_memo_event()`の制限モード分岐をこの関数経由に差し替えた。
  テスト3件追加、venture全体382件全件パス・schema検証9件パスを確認した。承認不要な
  設計・実装・テスト追加のみで、外部サービスへの公開・アカウント作成・支払い等は発生
  していないためpending-approval.mdへの追記なし。なお`payment_failure_reminder_
  scheduler.py`の3日前リマインド文言も同じ`LIFF_URL_PLACEHOLDER`の誤用が残っており、
  そちらは全ユーザー共通の1回限りメッセージ整形(ループ外で1回だけ組み立てる設計)を
  ユーザーごとのポータルURL解決に対応させる改修が必要なため、次回以降の課題として残す。
- (解消済み 2026-08-29 18:00 UTC・フェーズ126: 上記で先送りしていた
  `payment_failure_reminder_scheduler.py`の改修を行った。`PAYMENT_FAILURE_REMINDER_
  TEMPLATE`の`LIFF_URL_PLACEHOLDER`を`PORTAL_LINK_PLACEHOLDER`へ差し替え、
  `render_payment_suspended_message()`と同じ契約の`render_payment_failure_reminder_
  message(portal_link_provider, user_id)`を新設した。`send_payment_failure_reminders()`
  は`liff_url`引数を`portal_link_provider`引数へ差し替え、メッセージ整形をループ外の
  1回限りからユーザーごとの呼び出しへ変更した(`format_payment_failure_reminder_
  message()`は削除)。テスト7件追加、venture全体408件全件パス・schema検証9件パスを
  確認した。承認不要な設計・実装・テスト追加のみで、外部サービスへの公開・アカウント
  作成・支払い等は発生していないためpending-approval.mdへの追記なし。なお`payment_
  recovery_notification.py`の`build_payment_failure_detected_message()`
  (決済失敗検知時〈段階1〉の初回案内)も同じ`LIFF_URL_PLACEHOLDER`誤用が残っており、
  こちらは次回以降の課題として残す。通知本体の実送信配線(実LINE公式アカウント接続)は
  引き続きオーナー承認待ちの範囲)
  → **(2026-08-30 追記・フェーズ129で解消済みと判明)** フェーズ127で
  `build_payment_failure_detected_message(liff_url)`を`render_payment_failure_
  detected_message(portal_link_provider, user_id)`へ差し替え済み(`prototype/
  payment_recovery_notification.py`163行目)。本節の「次回以降の課題として残す」
  という記載だけがフェーズ127実施後も更新されず取り残されていた記載漏れ。詳細は
  README フェーズ127参照。
- (解消済み 2026-08-28 19:00 UTC・フェーズ120: 猶予期間終了直前リマインドを送信する
  スケジューラを設計・実装した(payment-failure-reminder-scheduler-design.md新規作成、
  `prototype/payment_failure_reminder_scheduler.py`)。詳細は同ドキュメント参照)
- (解消済み 2026-08-29 01:00 UTC・フェーズ121: 4節で先送りしていた「猶予期間中に決済が
  成功した場合の復旧通知の3分岐」の詳細設計・実装を行った。`prototype/payment_recovery_
  notification.py`新規作成、`classify_payment_recovery()`・`handle_payment_succeeded()`
  実装。詳細は4節参照)
- (解消済み 2026-08-29 03:00 UTC・フェーズ122: `dispatch_stripe_event()`(`stripe_webhook.py`)に
  `push_client`引数(省略時は後方互換で通知なし、aircon-pashaの`payment_failure.py`
  `push_client`引数と同じ方針)を追加し、`invoice.payment_succeeded`受信時に
  `payment_recovery_notification.handle_payment_succeeded()`へ委譲するよう配線した。
  本ventureは`payment_recovery_notification.py`が`trial_end_scheduler.py`の
  `LinePushClient`/`LinePushDeliveryError`をそのまま再利用しており、aircon-pashaの
  `payment_failure.py`のようにモジュールごとに別クラスの例外を定義していないため、
  aircon-pashaのフェーズ147時点で先送りされていた「復旧通知側の配線」を本ventureでは
  そのまま行えた。送信失敗時(`OUTCOME_SEND_FAILED`)は状態を変更せずWebhookリトライに
  委ねる設計とした。`receive_stripe_webhook()`にも同じ`push_client`引数を追加し
  委譲した。テスト6件追加、venture全体379件全件パス・schema検証9件パスを確認した)
- 実際のWebhook受信・状態保存・LINE送信配線(実LINE公式アカウント接続)、決済代行サービスとの
  契約自体は引き続きオーナー承認待ち(pending-approval.md参照)。
- 猶予期間7日・リマインド1回のみという値は、他venture共通で実測データの無い暫定値のまま。
