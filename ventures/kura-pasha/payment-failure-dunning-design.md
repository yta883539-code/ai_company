# 決済失敗(カード継続課金エラー)時の案内設計

作成日: 2026-09-09(フェーズ56)

## 背景

line-reservation-ai・aircon-pasha・course-set-pashaのpayment-failure-dunning-design.mdは
いずれも「いったん有料プランへ加入し継続課金が始まった後、カード期限切れ・利用限度額超過等で
毎月の自動課金自体が失敗するケース」(dunning対応)を扱っている。本ventureにはこれに相当する
ドキュメントがまだ存在せず、usage_counter_workshop.mdのフェーズ52注記(「past_dueも本フェーズ
では"active"ではない値として一律ブロック対象とし、ダニング固有の猶予期間の扱いは次にやること
候補に委ねる」)が示すとおり、`subscription_status="past_due"`になった瞬間に猶予期間なく生成が
止まる暫定実装のまま残っていた。本ドキュメントは他venture3件の設計を踏襲しつつ、本venture
固有の前提(workshop単位契約・契約者1名限定・PortalLinkProvider相当の抽象化が未実装)へ
翻案し、猶予期間付きのダニングフローとして正式に設計する。

決済代行サービス自体の契約・実装配線は引き続きオーナー承認待ち(pending-approval.md参照)の
ため、本ドキュメントは机上の設計と、実Stripe/LINE接続なしで検証可能なプロトタイプコードの
実装のみを行い、実際の課金・送信は行わない。

## 1. 本venture固有の前提整理(他venture3件との違い)

- 契約は`craftsman_workshop/{workshop_id}`単位、支払い名義人は`contractor_user_id`一人に
  限定される(subscription-cancellation-notification-design.md フェーズ54と同じ前提)。
  通知の宛先は常に契約者本人とし、共同利用者(その他メンバー)には送らない。
- 本venture側にはCustomer Portal相当のURL発行(`PortalLinkProvider`)が未実装
  (subscription-cancellation-scheduled-notification-design.md 5節で既出の制約)。他venture3件は
  通知本文にポータルURLを差し込むが、本ventureは差し込みを行わず、その旨を文言で案内する
  簡略化を採用する。
- course-set-pasha・aircon-pashaは「3日前リマインド」を送信する専用スケジューラ
  (`payment_failure_reminder_scheduler.py`相当)・運営者向け通知(payment-suspension-owner-
  notification-design.md相当)を持つが、本ventureは(a)LINE公式アカウント接続前でCloud
  Scheduler等の定期実行基盤自体をまだ設計していないこと、(b)本フェーズでは「検知時
  通知」「制限モード」「復旧時通知」という核となる3機構を優先することから、リマインド
  スケジューラ・運営者向け通知は本ドキュメントのスコープ外とし、6節「残課題」に明記する。

`usage_counter_workshop.py`は既に`WorkshopStoreProtocol.get_subscription_status()`/
`set_subscription_status()`(SUBSCRIPTION_STATUSES = trialing/active/past_due/canceled)を
持つため、`invoice.payment_failed`受信時は`set_subscription_status(workshop_id, "past_due")`、
`invoice.payment_succeeded`受信時は`set_subscription_status(workshop_id, "active")`という
既存の状態遷移をそのまま踏襲する。本ドキュメントで新設するのは、猶予期間の判定に使う
`payment_failure_detected_at`という別立ての時刻情報と、それに基づく通知・生成可否判定である。

## 2. 再試行(リトライ)方針

他venture3件で確認済みの一次情報(Stripe Billingのスマートリトライ: 標準設定は最大2週間で
最大8回)をそのまま踏襲する。unit-economics-estimate.mdで確認済みの原価構造も他ventureと
同種であり、本venture固有の再検証は不要と判断した。自前で持つのは「決済失敗イベントを
Webhookで受け取り、`craftsman_workshop`の状態を更新し、契約者へLINE通知する」部分のみ。

## 3. 猶予期間と生成可否の扱い

決済失敗検知後、即座に生成を止めない。以下の3段階とする(他venture3件と同じ「猶予期間
7日」を暫定値として踏襲する)。

| 段階 | タイミング | 生成可否 |
|---|---|---|
| 1. 通常運用 | 決済成功中(`subscription_status="active"`) | 可 |
| 2. 猶予期間(`payment_failure_detected_at`設定済み・経過7日未満) | 決済失敗検知〜7日間 | 可 |
| 3. 制限モード(`payment_failure_detected_at`設定済み・経過7日以上) | 猶予期間終了後も未解消 | 不可 |

- 猶予期間7日は他venture共通の暫定値(実測データなし)をそのまま踏襲する。
- 判定はcourse-set-pashaと同じく「別立ての状態フラグ(例: `payment_suspended_at`)を持たず、
  検知時刻からの経過日数を都度算出する」方式を採る(aircon-pashaの保存済みフラグ方式とは
  異なる)。理由は、本venture既存の`is_trial_period_over()`も同様に都度計算方式であり、
  実装スタイルを揃えた方が一貫性があるため。

**修正するバグ(usage_counter_workshop.mdフェーズ52で意図的に見送っていた既知の制約)**:
現行の`process_generation_request()`は`is_trial_period_over(...) and get_subscription_status()
!= "active"`という単一条件でブロックしており、`subscription_status="past_due"`になった瞬間
(トライアルは疾うに終えている有償契約者にとっては`is_trial_period_over`が常にTrueのため)
猶予期間なく即座に生成が止まっていた。これはフェーズ52時点で「ダニング固有の猶予期間の
扱いは次にやること候補に委ねる」と明記されていた既知の制約であり、本フェーズで解消する。
`subscription_status == "past_due"`の場合は`is_trial_period_over`の判定を経由せず、
`payment_failure_detected_at`からの経過日数のみで生成可否を決める専用の分岐に切り出す
(4節参照)。

## 4. 通知文言(ですます調・絵文字不使用、本venture単一トーン)

本ventureはmessage-tone-variants.md相当の複数トーン切り替えを導入していないため、以下は
単一文言のみ用意する。宛先は契約者本人(`contractor_user_id`)。PortalLinkProvider相当が
未実装のため、他venture3件と異なりURLは差し込まず、支払い方法の確認手段は「ご利用中の
決済手続き時にご案内したページ」という表現に留める(1節参照)。

### 決済失敗検知時(猶予期間開始、`invoice.payment_failed`受信時に即送信)

```
【鞍パシャッと】お支払いの確認をお願いします

いつもご利用ありがとうございます。
今回のお支払い手続きが完了できませんでした
(カードの有効期限切れ・利用限度額等が考えられます)。

現在、受注内容整理メモ・納品案内・お手入れ案内の生成は通常どおりご利用いただけます。
7日以内にお支払い方法をご確認・更新いただけますようお願いします
(ご利用中の決済手続き時にご案内した画面からご確認いただけます)。
```

### 制限モード移行時(段階3、生成リクエスト時に返す応答文言。プッシュ通知ではなく
`TRIAL_PERIOD_OVER_NOTICE`と同じ「生成リクエストへの応答」として返す)

```
お支払い手続きが確認できないため、受注内容整理メモ・納品案内・お手入れ案内の生成を
一時停止しています。
お支払い方法をご確認いただければ、確認完了後に自動で生成を再開します。
```

### 決済成功による復旧時(2分岐、他venture3件の3〜4分岐から簡略化。理由は6節参照)

| 分岐 | 判定条件 | 文言 |
|---|---|---|
| 1. 制限モードからの復旧 | `payment_failure_detected_at`設定済み かつ 経過日数 ≧ 7日 | 「再開しました」 |
| 2. 猶予期間中の解消(状態リセットのみ) | `payment_failure_detected_at`設定済み・上記に該当せず | 通知なし、状態のみクリア |
| 3. 対象外 | `payment_failure_detected_at`未設定(通常の毎月課金成功) | 何もしない |

本venture固有の簡略化: 他venture3件は「3日前リマインド送信済みか否か」で猶予期間中の解消を
さらに2つ(「解消されました」という通知あり/状態リセットのみの通知なし)に分けているが、
本ventureは3日前リマインドの送信インフラ自体が本フェーズの対象外(1節)であり
`payment_failure_reminder_sent_at`相当の状態を持たないため、この2つを区別できない。
猶予期間中の解消は一律「状態リセットのみ・通知なし」とする(送信済みリマインドが無いのに
「解消されました」という通知を送ると、契約者が心当たりのない通知を受け取ることになり
かえって不自然なため、送っていた通知への解消報告のみ通知する他venture3件の設計思想と
矛盾しない)。

```
【鞍パシャッと】お支払いを確認しました

お支払い手続きが完了しました。ご不便をおかけしました。
受注内容整理メモ・納品案内・お手入れ案内の生成を再開しましたので、引き続きよろしく
お願いします。
```

## 5. 実装方針

- `usage_counter_workshop.py`: `WorkshopStoreProtocol`へ`get_payment_failure_detected_at`/
  `set_payment_failure_detected_at`/`clear_payment_failure_detected_at`を追加し、
  `InMemoryWorkshopStore`にも実装する。`PAYMENT_FAILURE_GRACE_PERIOD_DAYS = 7`定数、
  `is_payment_suspended(workshop_id, now, workshop_store)`(経過日数判定)、
  `PaymentSuspendedError`例外、`PAYMENT_SUSPENDED_NOTICE`文言を新設する。
  `process_generation_request()`の判定を3節「修正するバグ」のとおり、
  `subscription_status == "past_due"`の専用分岐(`is_payment_suspended`のみで判定)と、
  それ以外の既存の`is_trial_period_over`分岐とに分離する。
- `prototype/payment_failure_notification.py`(新規): 4節の文言定数、
  `render_payment_failure_detected_message()`/`classify_payment_recovery()`/
  `handle_payment_failure_detected()`/`handle_payment_succeeded()`を実装する。
  `LinePushClient`/`LinePushDeliveryError`は`subscription_cancellation_notification.py`の
  ものをそのまま再利用し、モジュールごとに別クラスの例外を定義しない
  (course-set-pashaフェーズ122で確認済みの、複数モジュールにまたがる例外重複を避ける方針)。
- `stripe_webhook.py`: `handle_invoice_payment_failed()`/`handle_invoice_payment_succeeded()`を
  追加し、`receive_stripe_webhook()`が受理するイベント種別に`invoice.payment_failed`/
  `invoice.payment_succeeded`を加えて配線する。いずれも`data_object.customer`から
  `get_workshop_id_by_stripe_customer_id()`で逆引きする(`customer.subscription.deleted`と
  同じパターン)。

## 6. 残課題

- 3日前リマインドの送信(専用スケジューラの新設)、運営者向け通知(payment-suspension-
  owner-notification-design.md相当)は、本venture側にまだLINE公式アカウント接続前の
  定期実行基盤(Cloud Scheduler等)自体の設計が無いため、次回以降の課題として残す。
  実装した際は、4節の「猶予期間中の解消」を「リマインド送信済みか否か」で2分岐へ精緻化
  できる(他venture3件と同じ形へ揃える)。
- 実際のWebhook受信・状態保存・LINE送信配線(実LINE公式アカウント接続)、決済代行サービス
  との契約自体は引き続きオーナー承認待ち(pending-approval.md参照)。
- 猶予期間7日という値は、他venture共通で実測データの無い暫定値のまま。
- PortalLinkProvider相当の抽象化を将来導入する場合、4節の通知文言へURLを差し込む改修が
  必要になる(他venture3件と同じ構成に揃えられる見込み)。
