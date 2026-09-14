# 制限モード移行時のオーナー(運営者)向け能動通知 設計(フェーズ116)

payment-failure-dunning-design.md「6. 残課題」に残っていた「course-set-pasha・aircon-pasha
・line-reservation-aiは3日前リマインド送信専用スケジューラ・運営者向け通知
(payment-suspension-owner-notification-design.md相当)を持つが、本ventureは(a)LINE公式
アカウント接続前でCloud Scheduler等の定期実行基盤自体をまだ設計していないこと、(b)本フェーズ
では『検知時通知』『制限モード』『復旧時通知』という核となる3機構を優先することから、
リマインドスケジューラ・運営者向け通知は本ドキュメントのスコープ外」に対応する。

daily-scheduler-design.md(フェーズ112)で日次Cloud Scheduler基盤自体は設計済みになった
ため、本ドキュメントは残る2件のうち「運営者向け通知」を対象とする(3日前リマインド
スケジューラは引き続き次の課題として残す、8節参照)。

course-set-pasha/payment-suspension-owner-notification-design.md(フェーズ118相当)の
設計をそのまま踏襲しつつ、本venture固有の前提へ翻案する。blocked-but-billing-owner-
notification-design.md(フェーズ81)で確立済みの「workshop単位・プレーンテキスト」という
翻案方針もあわせて踏襲する。

## 1. 「オーナー」の定義

これまでの通知設計(trial-end-notification-design.md、payment-failure-dunning-design.md等)
はすべて「契約者(職人・工房)へLINE Push」を対象としてきた。本ドキュメントの「オーナー」は
それと異なり、鞍パシャッとというサービスそのものを運営する側(本AI Companyの実オーナー)を
指す。用語混同を避けるため、以降本ドキュメント内ではサービス利用者を「契約者」、運営者を
「オーナー」と呼び分ける(course-set-pasha版と同じ整理)。

## 2. 本venture固有の差分: workshop単位・都度算出・単一ストアで完結

- course-set-pasha版は`_is_payment_suspended()`という顧客ごとの都度算出関数を持つが、
  本ventureは既に同種の`is_payment_suspended(workshop_id, now, workshop_store)`
  (usage_counter_workshop.py、フェーズ56)を持つため、そのまま再利用する。新規の状態
  フラグは追加しない。
- 通知対象はworkshop_id単位で扱い、送信文言の組み立てにあたっては
  `workshop_store.get_contractor_user_id(workshop_id)`で契約者user_idを引き直す
  (blocked-but-billing-owner-notification-design.md 1節と同じ翻案)。
- blocked-but-billingは「検知用ストア(profile_store)」と「通知用ストア」を分ける必要が
  あったが、本ドキュメントの判定に必要な情報(`payment_failure_detected_at`・猶予日数・
  通知済み時刻)はいずれも`WorkshopStoreProtocol`1つに揃っているため、候補一覧を返す
  専用ファイル(`blocked_but_billing_candidates.py`相当)を新設せず、
  `payment_suspension_owner_notification.py`内の
  `select_due_payment_suspension_owner_notifications()`一本で「全workshop走査→制限モード
  判定→未通知判定」まで完結させる。

## 3. 通知先の設計

course-set-pasha版と同じく、送信先は固定の1件(オーナー自身のLINEユーザーID)。
`OWNER_LINE_USER_ID_PLACEHOLDER`というプレースホルダ定数で表現し、実際のオーナーLINE
ユーザーIDの取得・設定は既存の「実LINE公式アカウント接続」(README.md該当箇所、オーナー
承認待ちの範囲)にそのまま含まれるため、新たな承認待ち事項としては扱わない
(pending-approval.mdへの追記は不要と判断)。

## 4. 検知条件(いつ送るか)

`select_due_payment_suspension_owner_notifications(now, workshop_store)`が対象を絞り込む。
以下すべてを満たすworkshop_idのみを対象とする。

- `is_payment_suspended(workshop_id, now, workshop_store)`が真(`payment_failure_
  detected_at`が設定済み、かつ検知時刻からPAYMENT_FAILURE_GRACE_PERIOD_DAYS〈7日〉以上
  経過している=既に制限モードへ移行済み)
- `payment_suspension_owner_notified_at`が未設定(1回のみ送信。日次実行の重複・遅延に
  対しても再送されない)

新規フィールド`payment_suspension_owner_notified_at`は、既存の`blocked_but_billing_owner_
notified_at`と対称な位置づけの冪等性フラグとして`WorkshopStoreProtocol`に追加した
(usage_counter_workshop.pyフェーズ116)。

## 5. 通知文言

顧客(契約者)ごとに内容が変わる管理者向け通知のため、契約者識別子(`contractor_user_id`)と
検知からの経過日数を埋め込む(course-set-pasha版と同じ構成)。

```
【鞍パシャッと運営】制限モード移行のお知らせ

以下の契約者が決済失敗の猶予期間を超え、受注内容整理メモ・納品案内・お手入れ案内の
生成の制限モードへ移行しました。

契約者ID: {contractor_user_id}
決済失敗検知からの経過日数: {elapsed_days}日

必要に応じて契約者への個別フォロー(お支払い方法のご案内等)をご検討ください。
```

## 6. 送信・書き込み配線とクリア方式(course-set-pasha版との差異)

`send_payment_suspension_owner_notifications()`(Cloud Function相当)が本体。
`blocked_but_billing_owner_notification.send_blocked_but_billing_owner_notifications()`と
同型の「送信成功時のみ`payment_suspension_owner_notified_at`を書き込み、失敗時は書き込まず
次回実行時に自然に再試行対象として残る」設計を踏襲する。

course-set-pasha版は`invoice.payment_succeeded`受信時に`clear_payment_failure_detected_at()`
・`clear_payment_failure_reminder_sent_at()`と並べて`clear_payment_suspension_owner_
notified_at()`を個別に呼ぶ設計だが、本ventureは既存の`InMemoryWorkshopStore.
clear_payment_failure_detected_at()`が`payment_failure_reminder_sent_at`もあわせて
クリアする方式(フェーズ56時点で確立済み、payment_failure_notification.py参照)を既に
採っているため、本ドキュメントも同じ方式を踏襲し、`payment_suspension_owner_notified_at`
も`clear_payment_failure_detected_at()`内でまとめてクリアするようにした(usage_counter_
workshop.pyフェーズ116)。この結果、`payment_failure_notification.handle_payment_
succeeded()`側のコード変更は不要になった(呼び出し箇所を追加する必要がない分、
course-set-pasha版より配線がシンプルになる翻案上の利点)。

クリアしないと、同じ契約者が将来再び決済に失敗して制限モードへ移行した際に
`payment_suspension_owner_notified_at`が過去の値のまま残り、二度とオーナー通知が
飛ばなくなるため(course-set-pasha版6節と同じ理由)。

## 7. 実装

`prototype/payment_suspension_owner_notification.py`(新規)・
`prototype/test_payment_suspension_owner_notification.py`(新規、11件)として実装した。
`usage_counter_workshop.py`へ`get_payment_suspension_owner_notified_at`/
`set_payment_suspension_owner_notified_at`(WorkshopStoreProtocol・InMemoryWorkshopStore
両方)を追加し、`clear_payment_failure_detected_at()`の修正もあわせて行った。

## 8. 今後の課題

- オーナーのLINEユーザーIDの実際の取得・設定は、実LINE API接続と合わせてオーナー承認待ちの
  範囲(既存の記載を参照、新規追加なし)。
- 契約者識別子として`contractor_user_id`(LINEのuserId)をそのまま通知に載せる案で暫定と
  したが、実運用では工房名等に変換した方がオーナーにとって分かりやすい可能性がある
  (course-set-pasha版7節と同じ、次回以降の検討課題)。
- payment-failure-dunning-design.md「残課題」がもう1件挙げていた「3日前リマインド送信
  専用スケジューラ(`payment_failure_reminder_scheduler.py`相当)」は、本ドキュメントの
  対象外のまま残る。daily-scheduler-design.md(フェーズ112)の日次実行基盤は既にあるため、
  次回以降はそちらへの統合を優先候補とする。
- 制限モード移行以外にも、決済失敗検知時点(段階2、猶予期間開始時)でもオーナーへ即時
  通知すべきか(顧客への影響が生じる前の早期把握)は、猶予期間中に自然回復するケースまで
  毎回オーナーに通知が飛ぶと通知過多になる可能性があり、course-set-pasha版と同じく次回
  以降の検討課題として残す。

最終更新: 2026-09-14 10:00 UTC(フェーズ116: 新規作成)
