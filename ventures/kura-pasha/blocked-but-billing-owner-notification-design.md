# 「ブロック中かつ契約継続中」候補のオーナー通知 設計(フェーズ81)

blocked-but-billing-detection-design.md(フェーズ80)「5. 未着手のまま残る課題」に
残っていた「候補一覧を実際にオーナーへ届ける手段(aircon-pasha/blocked-but-billing-
owner-notification-design.md相当のFlex Message通知・日次Cloud Schedulerでの実行)は
本フェーズの対象外とし、次回以降の課題として残す」に対応する。
`list_blocked_but_billing_candidates()`(フェーズ80)が洗い出した候補workshop_idを、
実際に運営者(オーナー、本AI Companyの実オーナー。契約継続中の職人=顧客とは別人)へ
届けるバッチと通知チャネルを設計する。

aircon-pasha(フェーズ174)・course-set-pasha(フェーズ143)は同種の課題に既に対応済みで
あり、本ドキュメントはその横展開にあたる。

## 1. 本venture固有の差分: workshop_id単位・契約者への翻案

aircon-pasha等(1事業者=1契約)の候補一覧はuser_id単位だが、本ventureの
`list_blocked_but_billing_candidates()`はworkshop単位契約という構造(craftsman-account-
linking-design.md)を反映してworkshop_idの一覧を返す(blocked-but-billing-detection-
design.md 2節)。したがって本設計も一貫してworkshop_id単位で扱い、送信文言の組み立てに
あたっては`workshop_store.get_contractor_user_id(workshop_id)`で契約者user_idを引き直す
(2節)。

## 2. メッセージ形式: プレーンテキスト

aircon-pashaの`LinePushClient`はFlex Message専用(`send_flex_message`)だが、本venture
一貫の`LinePushClient`(subscription_cancellation_notification.py、フェーズ54)は
course-set-pasha方式と同じプレーンテキストの`send_message(user_id, text)`のみを提供する。
このため本設計はaircon-pasha版のFlex Message形式ではなく、course-set-pasha版に近い
プレーンテキストのオーナー通知文を採用する。

## 3. 送信先

本ventureにはcourse-set-pashaのpayment-suspension-owner-notification-design.mdに相当する
「オーナー固定宛先」の先行設計が無いため、本ドキュメントで新規に
`OWNER_LINE_USER_ID_PLACEHOLDER`を導入する。実際のオーナーLINEユーザーIDの取得・設定は
既存の「実LINE公式アカウント接続」(README.md該当箇所、オーナー承認待ちの範囲)に含まれる
ため、新たな承認待ち事項としては扱わない(pending-approval.mdへの追記は不要)。

## 4. 冪等性(いつ・誰を通知するか)

`list_blocked_but_billing_candidates()`は毎回「現時点でブロック中かつ契約継続中の全候補」
を返す設計であり、そのまま毎日通知すると同じ候補を延々と再通知し続けてしまう。他venture3件
と同じ考え方で、workshop_idごとに一度だけ通知する冪等性フィールド
`blocked_but_billing_owner_notified_at`を`craftsman_workshop`(usage_counter_workshop.py
の`WorkshopStoreProtocol`)に新設した(実装済み、下記5節参照)。`user_profile`ではなく
`craftsman_workshop`側に持たせるのは、候補一覧自体がworkshop_id単位であり
(`get_trial_end_notified_at`と同じ理由)、本フィールドを1つのworkshopに複数いるメンバーの
うち誰のuser_idにも紐付ける必要が無いため。

- 通知対象は「`list_blocked_but_billing_candidates()`の結果に含まれる」かつ
  「`blocked_but_billing_owner_notified_at`が未設定」のworkshop_idのみ(新規候補のみを
  通知する、digest形式ではなく1候補=1回の個別通知)。
- 送信成功時のみ`blocked_but_billing_owner_notified_at`を書き込む(送信失敗時は書き込まず
  次回実行時に自然に再試行対象として残る、既存の全通知バッチと同じ方式)。

## 5. 実装状況

`prototype/blocked_but_billing_owner_notification.py`に
`select_new_blocked_but_billing_candidates_for_notification()`(4節の抽出条件)・
`build_blocked_but_billing_owner_notification_message()`(2節のプレーンテキスト整形)・
`send_blocked_but_billing_owner_notifications()`(Cloud Function本体、契約者user_idの解決に
`get_contractor_user_id()`を使う3節相当のresolver引数を持つ)を実装した。
`usage_counter_workshop.py`の`WorkshopStoreProtocol`/`InMemoryWorkshopStore`に
`get_blocked_but_billing_owner_notified_at`/`set_blocked_but_billing_owner_notified_at`を
追加した(構造的に本モジュールの`BlockedButBillingOwnerNotifiedAtStoreProtocol`を満たす)。
テスト14件を新規ファイル`test_blocked_but_billing_owner_notification.py`に追加し、
venture全体603件→624件全件・schema検証27件いずれもパスを確認した。

## 6. クリア配線(本フェーズで実装済み)

- 「フォロー再開」(契約者本人のis_followingがTrueに戻る)、または「解約確定」
  (`customer.subscription.deleted`受信で`subscription_status`が`"canceled"`になる)の
  いずれかが起きた時点で`blocked_but_billing_owner_notified_at`をクリアする配線を実装した
  (aircon-pashaがフェーズ174→175の2段階で踏んだ順序を本ventureでは1フェーズにまとめて
  実装したもの)。`blocked_but_billing_owner_notification.py`の
  `clear_blocked_but_billing_owner_notified_at()`(設定済みの場合のみクリアしTrue/Falseを
  返す純粋関数)を新設し、`cloud_function_webhook.process_follow_event()`
  (新規引数`workshop_store`、省略時はクリアをスキップする後方互換)・
  `stripe_webhook.handle_customer_subscription_deleted()`(`set_subscription_status`成功時に
  常時呼び出し、追加引数不要)の両方から呼び出す。`dispatch_webhook_events()`の
  followイベント処理からも`workshop_store`を配線した。テスト計7件(clear関数自体3件
  〈上記5節に含む〉・process_follow_event経由2件・dispatch_webhook_events経由1件・
  handle_customer_subscription_deleted経由2件)を追加、venture全体件数は5節の624件に含む。

## 7. 今後の課題

- 実Firestoreフィールド追加・実際のCloud Scheduler作成・実LINE API接続はオーナー承認待ちの
  範囲(既存の記載を参照、新規追加なし)。

最終更新: 2026-09-11 06:00 UTC
