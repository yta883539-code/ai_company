# トライアル開始起点(初回follow時 vs 初回生成時)の確定

作成日: 2026-08-23(フェーズ100)

trial-end-notification-design.md(フェーズ99)5節「今後の課題」1点目、pricing-plan.mdの
「導入から14日間」の「導入」が初回follow時・初回生成時のどちらを指すか未確定だった点を
確定する。

## 1. 結論: 起点は「初回生成成功時」とする

trial-end-notification-design.mdが仮起点としていた「初回follow時」ではなく、
「初回生成成功時」(first-generation-notice-implementation-design.mdが既に`usage_counter`に
`first_generation_notice_sent`として記録している、そのユーザーにとって生涯最初の生成成功時点)
を14日間トライアルの起点として確定する。

## 2. 理由

- follow-event-welcome-message-design.mdの通り、follow時点ではまだ連携コードが発行された
  だけで、申込フォーム提出・連携コード解決(user_id紐付け)が完了するまでサービスを一切
  利用できない。follow〜フォーム提出の間隔は本人のタイミング次第で不確定であり、この間隔が
  長いユーザーほど実質的な利用可能日数が14日より目減りする、という不公平が生じる。
- 一方、初回生成成功時点は「実際に価値(投稿文・告知文・履歴記録の下書き)を受け取った
  瞬間」であり、pricing-plan.mdが意図する「無料で試せる期間」の起点として最も実態に近い。
- first-generation-notice-implementation-design.md 1節で、`usage_counter`ドキュメントに
  「そのユーザーにとって生涯で最初の生成成功時」を検知する`first_generation_notice_sent`
  フィールドと判定ロジック(`is_first_generation = counter.count == 0`)が既に実装済み
  (`prototype/cloud_function_webhook.py`)であり、同じ判定タイミングに`trial_start_at`を
  便乗させれば追加のイベント検知・スケジューラを新設せずに済む(line-reservation-ai/
  aircon-pashaで一貫している「既存の生成完了フローに便乗させ、追加のAPI呼び出し・課金を
  発生させない」方針と整合する)。
- 生成回数条件(A: 5回到達)は初回生成成功時点を`count=1`とする起点と自然に整合する
  (仮にfollow時起点のままだと、「期間は初回follow基準・回数は初回生成基準」で2つの
  条件が別々の起点を持つねじれが生じてしまう)。

## 3. usage_counterドキュメントへのフィールド追加

tech-stack.mdの`usage_counter/{user_id}`(`month`・`count`・`first_generation_notice_sent`)に
以下を追加する。

```
usage_counter/{user_id}
  month: string
  count: number
  first_generation_notice_sent: bool
  trial_start_at: timestamp | null   # 新規追加。初回生成成功時に1回だけ設定、以降不変
```

- 書き込みタイミングは`first_generation_notice_sent`と同じ「初回生成成功時
  (`is_first_generation`が真の分岐)」とし、`increment_and_mark_notice()`
  (`AtomicNoticeUsageCounterProtocol`)を呼ぶ同一書き込みに相乗りさせる想定
  (実Firestore接続時、単一ドキュメント更新の原子性を保つため。詳細な引数追加・
  疑似コードは次回の実装フェーズで行う)。
- `trial_start_at`が`null`のまま(=初回生成がまだ行われていない)ユーザーに対しては、
  (B)期間到達判定の日次スケジューラは判定対象外とする(トライアルはまだ開始していない
  ため、期間切れ通知を送りようがない)。

## 4. pricing-plan.md・trial-end-notification-design.mdへの反映

- pricing-plan.md「無料トライアル条件(仮)」の「期間: 導入から14日間」を、「期間: 初回の
  投稿文生成成功から14日間」に表現を確定する(本ドキュメント確定を受けての表現統一。
  実際の書き換えは本ドキュメント作成と同時に行う、下記参照)。
- trial-end-notification-design.md 2節(B)「トライアル開始(初回follow、または初回生成の
  いずれかを起点とする。起点の確定は5節「今後の課題」参照)」は、本ドキュメントの確定に
  伴い「トライアル開始(初回生成成功時、`trial_start_at`)」に更新する。

## 5. 今後の課題

- (解消済み 2026-08-23 12:00 UTC・フェーズ101: `trial_start_at`の実書き込みロジックを
  実装した。`UsageCounterProtocol`に`set_trial_start_at_if_unset()`・`get_trial_start_at()`を
  追加、`AtomicNoticeUsageCounterProtocol.increment_and_mark_notice()`に`trial_start_at`
  引数〈既定None〉を追加し、`InMemoryUsageCounter`側の実装・テストも完了済み。
  `prototype/cloud_function_webhook.py`に現存する。本節は本ドキュメント〈フェーズ100〉作成後の
  更新が漏れていた記載漏れであり、フェーズ147で発見・訂正した)
- (解消済み 2026-08-23 15:00 UTC・フェーズ102: (B)期間到達判定用の日次スケジューラ本体を
  `trial-end-scheduler-design.md`として新規設計し、`prototype/trial_end_scheduler.py`に
  `select_due_trial_end_notifications()`・`send_trial_end_notifications()`として実装した。
  上記と同じくフェーズ147で発見・訂正した記載漏れ)。
- 「浮いた作業時間の目安」の試算値未作成、生成一時停止判定の実装は
  trial-end-notification-design.md 5節に記載の通り未解決のまま。
- LIFFアプリの実登録・Cloud Scheduler実行環境の構築はオーナー承認待ち
  (pending-approval.md参照)。
