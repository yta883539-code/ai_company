# NotificationLogAggregatorのシステム内部イベント記録ギャップ修正(2026-08-02 19:00 UTC)

## 背景
README.mdの「次にやること」に長らく残っていた課題。`SYSTEM_ESCALATION_REASONS`
(`booking_conflict` / `candidate_selection_unresolved` / `booking_cancelled` /
`cancel_not_found` / `booking_change_started` / `change_not_found`)は
`NotificationLogAggregator.system_event_counts`で理由別集計する設計だったが、
実際にはこれらのイベントが`logs.record()`まで届いていなかった。

## 発覚したギャップ(2箇所)

### (1) 配線漏れ: consolidatorにしか通知していなかった
`ConversationFlowStateMachine`(engine.py)は`EscalationConsolidator`しか
コンストラクタで受け取っておらず、`provide_details()`のbooking_conflict・
`cancel_booking()`のbooking_cancelled・`change_booking()`のbooking_change_started・
`select_slot_from_reply()`のcandidate_selection_unresolvedは、いずれも
`self._consolidator.on_event(...)`のみを呼んでいた。`NotificationLogAggregator`
のインスタンス自体を持っていないため、記録しようがなかった。

`cloud_function_process_event.py`の`_handle_cancel`/`_handle_change`の
found=False分岐(cancel_not_found/change_not_found)も同様に、
`self._consolidator.on_event(...)`だけを呼び、`self._logs.record(...)`
(自身がコンストラクタで受け取っているにもかかわらず)を呼んでいなかった。

### (2) NotificationLogAggregator.record()自体の分類条件の不備
配線を直した後にテストが失敗して判明した、より根の深い問題。`record()`は
```python
if output.get("intent") == "escalation" and output.get("needs_owner_check"):
```
という条件でシステムイベント分類ロジックに入っていたが、`booking_cancelled`/
`booking_change_started`/`cancel_not_found`/`change_not_found`は
`intent`がそれぞれ`"cancel"`/`"change"`のまま渡ってくる(`booking_conflict`/
`candidate_selection_unresolved`は`intent: "escalation"`で発火するため
この問題は表面化していなかった)。`SYSTEM_ESCALATION_REASONS`に4つの理由を
追加した2026-08-02時点で、本来この分岐条件も合わせて緩めるべきだったが
見落とされていた。

## 修正方針
1. `ConversationFlowStateMachine.__init__`に`logs: Optional[NotificationLogAggregator] = None`
   を追加(既存呼び出し側・26箇所のテストとの後方互換のためNoneデフォルト)。
   `_notify_system_event()`という内部ヘルパーを新設し、consolidator通知とlogs記録を
   1箇所にまとめて4つの発火箇所全てから呼ぶようにした。
2. `cloud_function_process_event.py`の2つのfound=False分岐に`self._logs.record(...)`
   呼び出しを追加。`_demo()`でも`logs`を`flow`と`processor`の両方に共有させるよう
   生成順序を修正(従来は`flow`生成後に`logs`を作っていたため共有できていなかった)。
3. `NotificationLogAggregator.record()`の分類条件を、`intent == "escalation"`必須から
   `needs_owner_check`必須+`escalation_reason`の値で判定する方式に変更。
   `consultation_count`(厳守事項6の一般相談)のみ引き続き`intent == "escalation"`を
   要求し、未知の理由文字列を誤って一般相談扱いしないようにした。

## 影響範囲・確認
- engine.py: `NotificationLogAggregator.record()`、`ConversationFlowStateMachine`
  (コンストラクタ・4箇所の発火メソッド)
- prototype/cloud_function_process_event.py: `_handle_cancel`/`_handle_change`の
  found=False分岐、`_demo()`の生成順序
- test_engine.py: `ConversationFlowStateMachineSystemEventLoggingTest`を新設
  (booking_conflict/booking_cancelled/booking_change_started/
  candidate_selection_unresolvedの4種+logs未指定時の後方互換を確認)
- test_cloud_function_process_event.py: `_new_processor`のlogs配線を修正し、
  cancel_not_found/change_not_found/booking_cancelled/booking_change_started/
  booking_conflictの既存テストに`logs.system_event_counts`の検証を追加
- 全125件のテストがパス(python3 -m unittest test_engine test_cloud_function_process_event
  test_reminder_scheduler test_cloud_function_webhook)。schema/validate_test_cases.pyの
  22件も引き続き全件パス(このMD修正はLLM構造化出力のスキーマには影響しないため無関係)。

## 残る課題
- 通知ログ集計画面(スプレッドシート版MVP)の実運用配線自体は、実LLM/実LINE API/
  実Cloud Scheduler接続(オーナー承認待ち、pending-approval.md参照)に依存するため
  未着手のまま。今回の修正で「机上実装としてはsystem_event_countsが正しく積み上がる」
  状態になったので、実接続後はこの値をそのまま集計画面のシステムイベント件数として使える。
