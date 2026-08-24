# new_booking時のneeds_owner_check見落とし修正設計(フェーズ続き135)

## 背景・発見の経緯

multi-turn-scenario-harness-design.md「残る課題」(2026-08-24 15:00 UTC〜20:00 UTC・フェーズ続き134)
でE8(自然文とJSONの矛盾)をハーネス化した際、以下の実装ギャップを発見した。

- E8の期待される構造化出力は`conversation-samples-test-cases.md`記載どおり
  `{intent: "new_booking", confirmed: false, needs_owner_check: true, ...}`であり、
  `intent`は`new_booking`のまま(矛盾検知による安全側上書きは`confirmed`と
  `needs_owner_check`のみ)。
- しかし`cloud_function_process_event.py`の`ConversationEventProcessor.process()`は
  `intent`の値だけで分岐しており、`needs_owner_check`を直接参照する箇所は無い。
  `intent == "new_booking"`はそのまま通常の予約フロー(`_start_new_booking`等)へ進み、
  `_notify_owner()`はintentがfaq(faq_segments付き)/escalation/cancel/change/
  その他非new_bookingの場合、または`_start_new_booking`内のunregistered_menu検出時
  にしか呼ばれない。
- `NotificationLogAggregator.record()`も`needs_owner_check`がtrueであれば処理には入るが、
  `escalation_reason`が未設定かつ`intent`が`escalation`でない場合は
  `unimplemented_feature`/`SYSTEM_ESCALATION_REASONS`/`consultation_count`の
  いずれのバケットにも該当せず、集計上は完全に無視される。

結果として、「AIが確定と矛盾する出力を返したため安全側でconfirmed:falseに倒した」という
本来オーナーに知らせるべき異常が、顧客には(候補提示止まりで確定させないという)最低限の
安全性は保たれるものの、オーナー側には一切通知も集計もされない状態になっていた。

## 対応方針

「確定させない」という顧客向けの安全性(既存のE8テストで確認済み・変更しない)は維持したまま、
`intent == "new_booking"`かつ`needs_owner_check: true`の場合に、サーバー側で以下を合成する。

1. `escalation_reason: "output_contradiction"`をイベントに合成する。
   - `llm-system-prompt-draft.md`の現行ルールでは、LLMが`intent: new_booking`のまま
     `escalation_reason`を付与することは起こらない(rule10のunimplemented_feature等、
     escalation_reasonが関わるケースは必ず`intent: escalation`にする設計)ため、
     無条件に合成してよい(既存の値の有無で分岐する必要はない)。
   - `unregistered_menu`(`_start_new_booking()`内、メニュー未登録時)と同じパターンで、
     LLM出力ではなくサーバー側が状況から合成するreason値であり、
     `booking_output.schema.json`の`escalation_reason` enum(`consultation`/
     `unimplemented_feature`、LLM自身が出力してよい値のみを列挙)には含めない。
   - `engine.py`の`SYSTEM_ESCALATION_REASONS`(システム内部イベント扱い)に追加し、
     `_SYSTEM_EVENT_LABELS`にラベル「AI応答の矛盾検知(要確認)」を追加する。
     これにより`NotificationLogAggregator.record()`は`system_event_counts`側へ
     正しく計上され(consultation_countではなく)、`is_escalation_event_owner_notable()`・
     `_escalation_type_label()`もそのまま正しく機能する。
2. 合成後の`escalation_reason`付きイベントで`self._notify_owner()`を呼び、
   即時/ウィンドウ集約いずれかの経路でオーナーへ通知する(通常のシステムイベントと同じ
   `EscalationConsolidator`の扱いに乗せる)。
3. 顧客向けの処理は変更しない。`intent`は`new_booking`のままなので、直後の
   `stage`分岐(`_start_new_booking`/`_handle_candidate_selection`/`_handle_details`)へ
   そのまま進み、候補提示等の通常フローを継続する(E8テストで確認済みの「confirmed:falseの
   まま候補提示止まりで完結する」安全性はそのまま)。

## 実装箇所

`ConversationEventProcessor.process()`(`cloud_function_process_event.py`)で、
`intent = output.get("intent")`を`self._logs.record()`より前に計算するよう並べ替え、
その直後に上記の合成+`_notify_owner()`呼び出しを追加する。`self._logs.record()`は
合成後の`output`(escalation_reason付き)を渡すことで、ログ集計とオーナー通知の両方が
一貫した`escalation_reason`を見るようにする。

## 影響範囲の確認

- `_start_new_booking`/`_handle_candidate_selection`/`_handle_details`はいずれも
  `output.get("escalation_reason")`を参照しないため、合成した`escalation_reason`が
  通常の予約フローの判定に影響することはない(コードベース全体を`escalation_reason`で
  grepして確認済み)。
- 既存テスト(`test_cloud_function_process_event.py`)で`needs_owner_check: true`かつ
  `intent: "new_booking"`の組み合わせを使うケースは存在しなかった(既存ケースは
  すべてfaq/escalation intent)ため、既存テストへの副作用は無い想定。

## 実装・検証結果

上記の設計どおり`engine.py`(`SYSTEM_ESCALATION_REASONS`・`_SYSTEM_EVENT_LABELS`への
`output_contradiction`追加)・`cloud_function_process_event.py`(`process()`)を実装し、
以下のテストを追加・更新した。

- `test_cloud_function_process_event.py`
  `NewBookingContradictionOwnerNotificationTests`(新規)。顧客向けフローが不変であること
  (`test_customer_flow_still_presents_candidates_unchanged`)、オーナーへ
  `output_contradiction`ラベルで通知され`NotificationLogAggregator.system_event_counts`に
  計上されること(`test_owner_is_notified_with_output_contradiction_label`)を確認。
- `test_scenario_harness.py`
  `E8NaturalLanguageJsonContradictionScenarioTest`のテスト名・docstring・アサーションを
  修正後の挙動(オーナー通知が実際に届く)に合わせて更新
  (`test_contradiction_safe_side_output_never_confirms_and_notifies_owner`)。

`prototype/`配下の全テスト(319件)・`schema/validate_test_cases.py`(25件)がいずれもパス。

## 残る課題

- `escalation_reason: "output_contradiction"`という名称・ラベル文言は今回の暫定案。
  実LLM接続後、矛盾検知処理そのものを実装する段になった際に見直す可能性がある。
- 同様のパターン(`needs_owner_check: true`だがintentの分岐先がオーナー通知を呼ばない
  組み合わせ)が他のintentでも起こりうるかは未点検。次回以降の点検課題として残す。
