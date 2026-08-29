# 制限モード移行時のオーナー(運営者)向け能動通知 設計

payment-failure-reminder-scheduler-design.md 7節が残した課題への対応。本ventureは
`payment_suspended_at`のような専用フラグを持たず、`_is_payment_suspended()`
(cloud_function_webhook.py)による都度算出のみで制限モードを判定している
(フェーズ118)。そのため現状、決済失敗のまま猶予期間(7日)を超えて制限モードへ
移行した顧客がいても、次にその顧客自身がメモを送ってきて`PAYMENT_SUSPENDED_MESSAGE`が
返信される(受動的経路)まで、誰もそれに気づかない。本ドキュメントは、制限モードへの
移行を検知し、運営者(本ventureを実際に営むオーナー、course-set-pashaというサービス
自体の提供者。顧客であるボルダリングジムオーナーとは別人)へ能動的に知らせる通知の
設計を行う。

## 1. 「オーナー」の定義とこれまでの用語との違い

これまでの通知設計(trial-end-scheduler-design.md、payment-failure-dunning-design.md等)
はすべて「顧客(ボルダリングジムオーナー)へLINE Push」を対象としてきた。本ドキュメントの
「オーナー」はそれと異なり、course-set-pashaというサービスそのものを運営する側
(本AI Companyの実オーナー)を指す。用語混同を避けるため、以降本ドキュメント内では
サービス利用者を「顧客」、運営者を「オーナー」と呼び分ける。

## 2. 通知先の設計

- 顧客ごとに送信先が変わる従来の通知(`push_client.send_message(user_id, text)`)とは異なり、
  本通知の送信先は固定の1件(オーナー自身のLINEユーザーID、またはオーナーのみが参加する
  運営用LINEグループ)である。
- 固定送信先IDは環境変数等の設定値として持つ想定とし、本モジュールでは
  `OWNER_LINE_USER_ID_PLACEHOLDER`というプレースホルダ定数で表現する
  (trial_end_scheduler.pyの`LIFF_URL_PLACEHOLDER`と同じ考え方)。実際のオーナーLINE
  ユーザーIDの取得・設定自体は、既存の「実LINE API接続はオーナー承認待ちの範囲」
  (README.md該当箇所)にそのまま含まれるため、新たな承認待ち事項としては扱わない
  (pending-approval.mdへの追記は不要と判断)。

## 3. 検知条件(いつ送るか)

`select_due_payment_suspension_owner_notifications()`が対象を絞り込む。以下すべてを
満たす顧客のみを対象とする。

- `payment_failure_detected_at`が設定済み
- `now - payment_failure_detected_at >= grace_period_days`(7日。既に制限モードに
  入っている顧客のみが対象。payment_failure_reminder_scheduler.pyの
  `select_due_payment_failure_reminders()`が同じ経過日数の「未満」側を対象とするのと
  ちょうど対になる)
- `payment_suspension_owner_notified_at`が未設定(1回のみ送信。日次実行の重複・遅延に
  対しても再送されない)

新規フィールド`payment_suspension_owner_notified_at`は、既存の`payment_failure_reminder_
sent_at`と対称な位置づけの冪等性フラグとして`UsageCounterProtocol`に追加する。

## 4. 通知文言

顧客ごとに内容が変わる管理者向け通知のため、顧客識別子(`user_id`、実運用では顧客管理用の
表示名等に置き換わる想定)と検知からの経過日数を埋め込む。

```
[コースセットパシャッと運営] 制限モード移行のお知らせ

以下の顧客が決済失敗の猶予期間(7日)を超え、投稿文生成の制限モードへ移行しました。

顧客ID: {user_id}
決済失敗検知からの経過日数: {elapsed_days}日

必要に応じて顧客への個別フォロー(お支払い方法のご案内等)をご検討ください。
```

## 5. 送信・書き込み配線

`send_payment_suspension_owner_notifications()`(Cloud Function F相当)が本体。
`payment_failure_reminder_scheduler.py`の`send_payment_failure_reminders()`と同型の
「送信成功時のみ`payment_suspension_owner_notified_at`を書き込み、失敗時は書き込まず
次回実行時に自然に再試行対象として残る」設計を踏襲する。顧客ごとに文面が変わるため、
`format_payment_failure_reminder_message()`(全顧客共通の固定文言)とは異なり、
ループ内で顧客ごとにメッセージを組み立てる。

## 6. 復旧時のクリア

`invoice.payment_succeeded`受信時(`payment_recovery_notification.handle_payment_
succeeded()`)、既存の`clear_payment_failure_detected_at()`/`clear_payment_failure_
reminder_sent_at()`と並べて`clear_payment_suspension_owner_notified_at()`も呼ぶ。
クリアしないと、同じ顧客が将来再び決済に失敗して制限モードへ移行した際に
`payment_suspension_owner_notified_at`が過去の値のまま残り、二度とオーナー通知が
飛ばなくなるため(`payment_failure_reminder_sent_at`のクリアと全く同じ理由、
payment-failure-reminder-scheduler-design.md 3節参照)。

## 7. 今後の課題

- オーナーのLINEユーザーID(または運営用グループID)の実際の取得・設定は、実LINE API
  接続と合わせてオーナー承認待ちの範囲(既存の記載を参照、新規追加なし)。
- 顧客識別子として`user_id`(LINEのuserId、無機質な文字列)をそのまま通知に載せる案で
  暫定としたが、実運用では顧客管理シート等と突き合わせて店舗名に変換した方がオーナーに
  とって分かりやすい可能性がある。突き合わせの仕組み自体は本ventureの範囲外(オーナーが
  手元の顧客管理手段で行う想定)とし、本ドキュメントは`user_id`表示までを設計範囲とする。
- 制限モード移行以外にも、決済失敗検知時点(段階1)でもオーナーへ即時通知すべきか
  (顧客への影響が生じる前の早期把握)は、猶予期間中に自然回復するケースまで毎回
  オーナーに通知が飛ぶと通知過多になる可能性があり、次回以降の検討課題として残す。
