# トライアル終了通知・条件A(生成回数到達)の実装

作成日: 2026-08-24(フェーズ113)

trial-end-notification-design.md「5. 今後の課題」に残っていた「(A)(B)いずれの経路かを...
次回行う」のうち、(A)生成回数到達側がprocess_memo_event()内で検知・送信されるところまで
未実装だった点に対応する(trial-end-scheduler-design.mdのCloud Function Dは(B)期間到達側の
日次スケジューラのみをカバーしており、(A)側はメッセージ文言の設計(trial-end-notification-
design.md 3節)のみで実装が残っていた)。

## 1. 実装方針

first-generation-notice-implementation-design.mdの「生成完了時の返信に便乗させる」方式を
踏襲し、追加のプッシュAPI呼び出し・課金を発生させない。

`prototype/cloud_function_webhook.py`の`process_memo_event()`内、
`increment_trial_generation_count()`呼び出し直後(既に(1)有料転換済みでない
(`get_upgraded_at() is None`)ことが確認済みのブロック内)に以下を追加した。

1. `increment_trial_generation_count()`の返り値(インクリメント後のカウント)を
   `trial_generation_count`として受け取る。
2. `increment_trial_area_count()`の返り値も同様に`trial_area_count`として受け取る
   (`increment_trial_area_count`未対応のusage_counter実装では`None`のまま、
   `format_trial_end_notification_message()`側の既存フォールバックに委ねる)。
3. `trial_generation_count == TRIAL_GENERATION_LIMIT`(新設、
   `trial_end_scheduler.py`に`= 5`として定義。pricing-plan.md「生成5回到達」と一致)
   かつ`get_trial_end_notified_at(user_id) is None`(未通知)の場合のみ、
   `trial_end_scheduler.format_trial_end_notification_message()`で組み立てた通知文を
   返信本文の末尾に追記し、`set_trial_end_notified_at(user_id, now)`を呼ぶ。
4. `get_trial_end_notified_at`/`set_trial_end_notified_at`のいずれかを実装しない
   usage_counterでは本ブロック自体をスキップする(既存のhasattr()判定パターンを踏襲)。

## 2. (B)期間到達側との整合

`select_due_trial_end_notifications()`(trial_end_scheduler.py)は
`trial_end_notified_at is not None`のユーザーを対象外にする設計に既になっているため、
(A)側がこの返信便乗で先に`set_trial_end_notified_at()`を書き込んでおけば、(B)側の日次
スケジューラは自動的にそのユーザーをスキップする。逆に(B)側が先に発火した場合も、(A)側は
本実装の`get_trial_end_notified_at(user_id) is None`チェックで送信をスキップする。
どちらが先でも「いずれか早い方で1回のみ」(trial-end-notification-design.md 2節)が保たれる。

## 3. 対象外にした範囲

- trial-end-notification-design.md「4. トライアル終了後(未アップグレード)の挙動」で
  「本フェーズでは範囲外」とされた「生成一時停止」(トライアル終了後の生成リクエストを
  拒否する分岐)は、本フェーズでも引き続き未実装のまま残す。通知の送信条件(A)を実装した
  ことで「トライアル終了検知」自体は行われるようになったため、次回はこの検知結果
  (`get_trial_end_notified_at(user_id) is not None`かつ`get_upgraded_at(user_id) is None`)を
  使って生成一時停止を実装することが可能になった。
- 実LINE Push Message API・実Cloud Scheduler接続(オーナー承認待ち)を要する(B)側の実配線は
  対象外(trial-end-scheduler-design.md参照、変更なし)。

## テスト

`prototype/test_cloud_function_webhook.py`に`ProcessMemoEventTrialEndNotificationTest`を
新設し、以下を確認した(course-set-pasha配下319件パス・schema検証9件パス)。

1. 5回目の生成完了時、返信本文にトライアル終了通知文言(「無料トライアル、お疲れさまでした」)が
   追記されること。
2. 5回目の生成完了時、`set_trial_end_notified_at()`が呼ばれ`get_trial_end_notified_at()`が
   非Noneになること。
3. 4回目まではまだ通知文言が追記されないこと。
4. 既に`trial_end_notified_at`が設定済み((B)側で先に送信済み等)の場合、5回目到達時でも
   二重送信しないこと。
5. 既に有料転換済み(`upgraded_at`設定済み)の場合、5回到達しても送信されないこと
   (既存の`get_upgraded_at() is None`ガードにより、この経路自体が実行されない)。
