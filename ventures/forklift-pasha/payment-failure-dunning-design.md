# 決済失敗(カード継続課金エラー)時の猶予期間・制限モード設計

作成日: 2026-10-17(フェーズ167)

## 背景

line-reservation-ai・aircon-pasha・course-set-pasha・kura-pashaはいずれも
payment-failure-dunning-design.md(決済失敗検知〜猶予期間〜制限モードの設計)を既に
持つが、本venture(forklift-pasha)にはこれに相当する文書・実装が存在せず、既存の
状態判定(`is_trial_period_over`・`is_generation_paused`・`is_subscription_canceled`、
いずれも`trial_management.py`)は「無料トライアル終了後・未アップグレード」「解約済み」の
2系統しか扱っていなかった。有料転換後(`upgraded_at`設定済み・`canceled_at`未設定)に
カード期限切れ等で毎月の自動課金自体が失敗する状態(dunning)を一切扱っていない欠落が
あったため、他venture4件の設計を本venture固有の前提へ翻案し、本ドキュメントで正式に
設計する。

決済代行サービス自体の契約・実LINE/メール送信配線は引き続きオーナー承認待ち
(pending-approval.md参照)のため、本ドキュメントは机上の設計と、実Stripe接続なしで
検証可能なプロトタイプコードの実装のみを行い、実際の課金・送信は行わない。

## 1. 本venture固有の前提整理(他venture4件との違い)

- 本ventureは`subscription_status`(trialing/active/past_due/canceled等の列挙値)を
  持たない。既存の`is_trial_period_over`・`is_generation_paused`・
  `is_subscription_canceled`がいずれも個別のタイムスタンプフィールド
  (`trial_start_at`・`trial_end_notified_at`・`upgraded_at`・`canceled_at`)からの
  都度計算で状態を表現する設計のため、決済失敗も同じ流儀で
  `payment_failure_detected_at`という単一のタイムスタンプフィールドのみを新設し、
  専用の状態文字列は持たない(aircon-pashaの`UserProfile`も同種のタイムスタンプ
  直接保持方式であり、本venture既存の設計思想とも合致する)。
- 顧客接点はLINEではなくメール(`email`フィールド、payment-identity-verification-
  design.md・cloud_function_send_trial_end_emails.py)である。したがって通知は
  他venture4件のLINE Push文言ではなく、メール文言として設計する。
- Customer Portal相当のURL発行(`PortalLinkProvider`)は本venture未実装
  (portal-session-provider-design.mdに相当する文書自体が存在しない)。本ドキュメントの
  通知文言はkura-pashaと同じく、URLを差し込まず「ご契約時にご案内した画面」という
  表現に留める簡略化を採る。
- 本フェーズ(167)では、他venture4件が複数フェーズに分けて実装した
  (検知→猶予期間→制限モード→リマインド→運営者通知→復旧通知、の一連)うち、
  MVPとして優先度が高い中核3機構(検知記録・猶予期間判定・復旧時クリア)のみを
  設計・実装する。リマインド送信スケジューラ・運営者向け通知・復旧時メール送信配線は
  5節「残課題」に明記し、次回以降のフェーズに委ねる。

## 2. 再試行(リトライ)方針

他venture4件で確認済みの一次情報(Stripe Billingのスマートリトライ: 標準設定は最大2週間で
最大8回)をそのまま踏襲する。本venture固有の再検証は不要と判断した。

## 3. 猶予期間と記録整形可否の扱い

決済失敗検知後、即座に記録整形(点検記録簿整形・期限リマインド生成)を止めない。
他venture4件と同じ「猶予期間7日」を暫定値として踏襲する。

| 段階 | 判定条件 | 記録整形可否 |
|---|---|---|
| 1. 通常運用 | `payment_failure_detected_at`未設定 | 可 |
| 2. 猶予期間 | `payment_failure_detected_at`設定済み・経過7日未満 | 可 |
| 3. 制限モード | `payment_failure_detected_at`設定済み・経過7日以上 | 不可 |

判定対象は有料転換済み(`upgraded_at`設定済み)かつ未解約(`canceled_at`未設定)の
事業者のみとする。トライアル中・解約済みの事業者は既存の`is_generation_paused`・
`is_subscription_canceled`がそれぞれ優先的に処理するため、本設計の対象外。

呼び出し側での優先順位は既存の`is_subscription_canceled` → 本設計の
`is_payment_suspended` → 既存の`is_generation_paused`の順とする(解約が決済失敗より
優先、決済失敗がトライアル終了判定より優先。解約済みなら`canceled_at`が常に真実を
表し、決済失敗の状態は意味を持たなくなるため)。

## 4. 通知文言(メール、ですます調・絵文字不使用)

本venture既存のメール文言(trial-end-notification-design.md相当、本venture未作成だが
`cloud_function_send_trial_end_emails.py`のdocstringに沿う)と同じトーンを踏襲する。
宛先は`email`フィールド(事業者の経営者・現場責任者)。

### 決済失敗検知時(猶予期間開始、`invoice.payment_failed`受信時に即送信)

```
【フォークリフトパシャっと】お支払いの確認をお願いします

いつもご利用ありがとうございます。
今回のお支払い手続きが完了できませんでした(カードの有効期限切れ・利用限度額等が
考えられます)。

現在、点検記録簿の整形・期限リマインドの生成は通常どおりご利用いただけます。
7日以内にお支払い方法をご確認・更新いただけますようお願いします(ご契約時に
ご案内した画面からご確認いただけます)。
```

### 制限モード移行時(段階3、生成リクエスト時に返す応答文言)

```
お支払い手続きが確認できないため、点検記録簿の整形・期限リマインドの生成を
一時停止しています。お支払い方法をご確認いただければ、確認完了後に自動で
生成を再開します。
```

### 決済成功による復旧時

kura-pashaと同じ理由(3日前リマインド送信済みフラグを本フェーズでは持たないため、
猶予期間中の解消と制限モードからの復旧を区別する情報が無い)で、本フェーズのMVPは
以下の2分岐のみとする。

| 分岐 | 判定条件 | 文言 |
|---|---|---|
| 1. 制限モードからの復旧 | 経過日数 ≧ 7日だった | 「再開しました」 |
| 2. 猶予期間中の解消 | 経過日数 < 7日だった | 通知なし、状態のみクリア |

```
【フォークリフトパシャっと】お支払いを確認しました

お支払い手続きが完了しました。ご不便をおかけしました。
点検記録簿の整形・期限リマインドの生成を再開しましたので、引き続きよろしく
お願いします。
```

## 5. 実装方針

- `trial_management.py`: `FleetOperatorStoreProtocol`/`InMemoryFleetOperatorStore`へ
  `get_payment_failure_detected_at`/`set_payment_failure_detected_at`
  (`None`渡しでクリア、`set_canceled_at`と同じ「上書き可・Noneでpop」方針)を追加する。
- `prototype/payment_failure.py`(新規): `PAYMENT_FAILURE_GRACE_PERIOD_DAYS = 7`定数、
  `mark_payment_failure_detected()`(複数回の失敗通知でも最新の失敗日時で上書き、
  aircon-pashaと同じ「安全側」判断)・`clear_payment_failure_on_success()`・
  `is_payment_suspended(internal_id, now, store)`(3節の経過日数判定、`upgraded_at`
  未設定または`canceled_at`設定済みの場合は常にFalse)・4節の3文言定数・
  `classify_payment_recovery()`(2分岐の判定のみ)を実装する。
- `stripe_webhook.py`: `handle_invoice_payment_failed()`/
  `handle_invoice_payment_succeeded()`を追加し、`receive_stripe_webhook()`が
  受理するイベント種別に`invoice.payment_failed`/`invoice.payment_succeeded`を
  加えて配線する。いずれも`data_object.customer`から
  `get_internal_id_by_stripe_customer_id()`で逆引きする(既存3ハンドラと同じパターン)。

## 6. 残課題

- 検知時・復旧時メールの実送信配線(`cloud_function_send_trial_end_emails.py`相当の
  メール送信基盤を本用途に再利用する設計)は次回以降の課題。
- 猶予期間終了直前のリマインド送信・運営者向け通知は、本venture側にまだ日次スケジューラ
  (他venture4件のdaily-scheduler-design.md相当)自体が無いため次回以降の課題。
  実装した際は、4節「決済成功による復旧時」を「リマインド送信済みか否か」で3分岐へ
  精緻化できる(他venture4件と同じ形へ揃える)。
- 猶予期間7日という値は、他venture共通で実測データの無い暫定値のまま。
- 実際のWebhook受信・状態保存・メール送信配線(実Stripe/メール送信サービス接続)は
  引き続きオーナー承認待ち(pending-approval.md参照)。
