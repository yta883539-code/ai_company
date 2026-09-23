# 制限モード移行時のオーナー(運営者)向け能動通知 設計(フェーズ255)

course-set-pashaのpayment-suspension-owner-notification-design.md(フェーズ125)・
kura-pashaの同種実装(daily-scheduler-design.md Cloud Function G「制限モード移行時の
オーナー通知」、pending-approval.md 2026-09-15 03:00 UTC記載)を本ventureへ横展開する。
blocked-but-billing-owner-notification-design.md(フェーズ174)冒頭が引用していた通り、
course-set-pashaのpayment-suspension-owner-notification-design.mdは「同様の設計は
aircon-pasha側でも横展開可能」と位置づけられていたが、決済失敗まわりの通知(段階1検知・
段階2リマインド・段階3制限モード移行・復旧)がフェーズ139〜149で一通り実装されたのちも、
この「オーナー自身への能動通知」だけは本venture・line-reservation-aiのいずれにも横展開
されないまま取り残されていた。course-set-pasha・kura-pashaに存在し、blocked-but-billing-
owner-notification-design.md(顧客のLINEブロックというオーナーへの別種の能動通知)には
既に前例があるにもかかわらず、決済失敗まわりの能動通知が本ventureに欠けているのは
cross-venture parityの抜け漏れであり、本フェーズで対応する。

## 1. 「オーナー」の定義

blocked-but-billing-owner-notification-design.md 1節と同じ区別を用いる。本ドキュメントの
「オーナー」は本ventureを実際に営む運営者(本AI Companyの実オーナー)を指し、顧客
(エアコンクリーニング業者)とは別人である。以降、サービス利用者を「業者」、運営者を
「オーナー」と呼び分ける。

## 2. 送信先・メッセージ形式

blocked-but-billing-owner-notification-design.md 1〜2節で確立済みの方式をそのまま踏襲する。

- 送信先は`OWNER_LINE_USER_ID_PLACEHOLDER`(blocked_but_billing_owner_notification.pyで
  定義済みの定数をそのまま再利用する。オーナー宛先は本venture内で1箇所に集約する方針に
  沿い、本モジュールで新たに定義しない)。
- 本venture一貫の`LinePushClient`(trial_end_scheduler.py)は`send_flex_message(user_id,
  alt_text, contents)`のみを提供するため、course-set-pasha版(プレーンテキスト)とは
  異なり、ボタンを持たないシンプルなbubble形式のFlex Messageとする
  (blocked_but_billing_owner_notification.pyと同じ構成)。

## 3. 検知条件(いつ送るか) — course-set-pashaとの設計上の違い

course-set-pashaはUsageCounterProtocolが`payment_suspended_at`のような専用フラグを
持たず`_is_payment_suspended()`による都度算出のみで制限モードを判定しているため、
`select_due_payment_suspension_owner_notifications()`は`payment_failure_detected_at`
からの経過日数(猶予期間7日)を毎回再計算する設計になっている(payment-suspension-
owner-notification-design.md 3節)。

一方、本ventureはpayment-failure-dunning-design.md・フェーズ140で追加した`payment_
suspended_at`フィールドを既に持ち、猶予期間経過後に制限モードへ移行した「その瞬間」を
`payment_suspension_scheduler.send_payment_suspensions()`が明示的に書き込む設計を
フェーズ145から採用している(payment_recovery_notification.pyのdocstringが同種の
設計差を既に説明している通り)。したがって本ドキュメントでは経過日数を再計算せず、
「`payment_suspended_at`が設定済み(既に制限モードへ移行済み)」かつ「`payment_
suspension_owner_notified_at`が未設定(1回のみ送信)」という、既存フィールドの
設定有無のみで判定するより単純な条件を採用する。

- `payment_suspended_at`が設定済み
- `payment_suspension_owner_notified_at`が未設定(1回のみ送信。日次実行の重複・遅延に
  対しても再送されない)

新規フィールド`payment_suspension_owner_notified_at`は、既存の`blocked_but_billing_
owner_notified_at`と対称な位置づけの冪等性フラグとして`UserProfile`
(user_id_linking.py)に追加する。

## 4. 通知文言

course-set-pashaのpayment-suspension-owner-notification-design.md 4節の文言を、本venture
の業種(エアコンクリーニング業者)・呼称(「業者」)に合わせて翻案する。業者ごとに内容が
変わる管理者向け通知のため、業者識別子(`user_id`、実運用では`business_name`〈UserProfile
既存フィールド〉に置き換わる想定)と決済失敗検知からの経過日数を埋め込む。

```
[エアコンパシャッと運営] 制限モード移行のお知らせ

以下の業者が決済失敗の猶予期間(7日)を超え、作業完了報告・お手入れ案内生成の
制限モードへ移行しました。

業者ID: {user_id}
決済失敗検知からの経過日数: {elapsed_days}日

必要に応じて業者への個別フォロー(お支払い方法のご案内等)をご検討ください。
```

`elapsed_days`は`now - payment_failure_detected_at`(日数)から算出する
(`payment_suspended_at`ではなく`payment_failure_detected_at`を起点にするのは、
猶予期間の起点そのものを示すため。course-set-pasha版と同じ考え方)。

## 5. バッチ実行主体・実行頻度

`payment_suspension_scheduler.py`(Cloud Function G)の直後、同じ日次ジョブ内で実行する
「Cloud Function H」相当と位置づける(blocked-but-billing-owner-notification-design.md
3節の「Cloud Function G」という名称と重複するため、本ドキュメントでは本venture内の実行
順序に合わせてHと呼ぶ。実際のCloud Function名は実装時に確定)。`send_payment_
suspensions()`が`payment_suspended_at`を書き込んだ直後の状態を読むことになるため、
同一バッチ実行内で後段に配置することで、制限モードへ移行した業者を移行当日中に
オーナーへ知らせられる。

## 6. 送信・書き込み配線

`send_payment_suspension_owner_notifications()`(Cloud Function H本体)が本体。
`blocked_but_billing_owner_notification.send_blocked_but_billing_owner_notifications()`
と同型の「送信成功時のみ`payment_suspension_owner_notified_at`を書き込み、失敗時は
書き込まず次回実行時に自然に再試行対象として残る」設計を踏襲する。

## 7. 復旧時のクリア

`invoice.payment_succeeded`受信時、既存の`payment_failure.clear_payment_failure_on_
success()`(`payment_failure_detected_at`・`payment_suspended_at`・`payment_failure_
reminder_sent_at`の3フィールドをクリア)に、新規`payment_suspension_owner_notified_at`
のクリアもあわせて行うよう拡張する。クリアしないと、同じ業者が将来再び決済に失敗して
制限モードへ移行した際に`payment_suspension_owner_notified_at`が過去の値のまま残り、
二度とオーナー通知が飛ばなくなるため(course-set-pasha版6節・payment_failure_reminder_
sent_atのクリアと全く同じ理由)。`clear_payment_failure_on_success()`は
`payment_recovery_notification.handle_payment_succeeded()`から既に呼ばれている
(3分岐のOUTCOME_RECOVERED_FROM_SUSPENSION・OUTCOME_SILENT_RESET経路の両方)ため、
呼び出し配線自体の追加変更は不要で、`clear_payment_failure_on_success()`本体の拡張のみで
完結する。

なお`blocked_but_billing_owner_notified_at`(フェーズ174)は`clear_payment_failure_on_
success()`の対象に含めない。両者はトリガー(決済失敗の解消/フォロー再開・解約確定)が
異なる独立した状態であり、混在させると片方のイベントで両方がクリアされてしまい
意味が変わるため、既存の`clear_blocked_but_billing_owner_notified_at()`(フォロー再開・
解約確定時に呼ばれる専用関数)とは別のまま維持する。

## 8. 今後の課題

- オーナーのLINEユーザーID(`OWNER_LINE_USER_ID_PLACEHOLDER`)の実際の取得・設定、実際の
  Cloud Scheduler作成・実LINE API接続はいずれもオーナー承認待ちの範囲(既存の記載を参照、
  新規追加なし)。
- 業者識別子として`user_id`をそのまま通知に載せる案で暫定としたが、実運用では
  `business_name`(UserProfile既存フィールド)を使った方がオーナーにとって分かりやすい
  可能性がある(course-set-pasha版7節と同じ課題)。本ドキュメントは`user_id`表示までを
  設計範囲とする。
- 決済失敗検知時点(段階1)でもオーナーへ即時通知すべきかは、猶予期間中に自然回復する
  ケースまで毎回通知が飛ぶと通知過多になる可能性があり、次回以降の検討課題として残す
  (course-set-pasha版7節と同じ課題)。

設計の参照元: course-set-pasha/payment-suspension-owner-notification-design.md,
blocked-but-billing-owner-notification-design.md, payment-failure-dunning-design.md,
payment-failure-reminder-scheduler-design.md
