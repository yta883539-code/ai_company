# LLM構造化出力 → ConversationFlowStateMachine呼び出しの対応付け

conversation-flow-state-machine-design.md で残課題としていた、LLMの構造化出力
(intent/datetime_candidate/confirmed等、schema/booking_output.schema.json準拠)から
`ConversationFlowStateMachine`の各メソッド(select_slot()/provide_details())を
どのタイミングで呼び出すかの対応付けを整理する。

## 対応表(会話の各ターンで、直前のLLM出力をもとに呼び出し側が行う処理)

| LLM出力の状態 | 呼び出し側ステージ前提 | 呼ぶメソッド | 備考 |
|---|---|---|---|
| `intent: new_booking`, `datetime_candidate`が曖昧(複数候補あり得る) | `candidates_presented`より前 | `search_candidates_from_llm_output()` → `present_candidates()` | 「来週土曜」等は`requested_date_range`/`time_of_day_preference`を`AvailabilitySearcher`に渡して複数候補に展開してから`present_candidates()`を呼ぶ(2026-08-01 00:00 UTC実装済み、下記「このステップで実施したこと」参照) |
| `intent: new_booking`, 顧客が候補から1件を特定できる返信 | `candidates_presented` | `select_slot()` | 直前に提示した候補一覧(`search_candidates_from_llm_output()`の戻り値)から顧客の返信に対応する`slot_key`を特定する処理(自然文での選択肢特定)は本ステップでは未実装(下記「残課題」参照) |
| `intent: new_booking`, `name`と`menu`が両方非nullで`confirmed: false` | `awaiting_details` | `provide_details()` | このLLM出力自体は「氏名・メニューを聞き取れた」ことを表し、確定の可否(hold中の枠との整合)はBookingSlotManager側が判定する |
| `intent: new_booking`, `confirmed: true`(LLMが確定文言を生成) | - | (呼ばない) | `confirmed`はLLMの発話意図フラグであり、実際の確定はBookingSlotManager.confirm()の成功可否が真実。provide_details()の戻り値(bool)を正としてLLMのconfirmedと矛盾する場合は安全側([schema-validation-report.md](schema-validation-report.md)のE8方針)に倣いエスカレーションする |
| `intent: escalation` / `faq` / その他 | 任意 | (呼ばない) | 予約フロー外。EscalationConsolidator/NotificationLogAggregator側の処理に委ねる |

## 残課題: 提示した候補一覧から顧客の返信に対応する`slot_key`を特定する処理

`search_candidates_from_llm_output()`(prototype/engine.py)により
`requested_date_range`/`time_of_day_preference` → 空き枠候補一覧の変換は実装済みになったが、
その次のステップ「提示した候補一覧(例: 3件)のうち、顧客が『2番目で』『8/9の午後1時の方で』
のように返信した内容から`select_slot()`に渡す`slot_key`を1件特定する処理」は未設計・未実装。
これには以下が必要になる:

1. 候補一覧に採番(1/2/3等)を振って顧客へ提示する文言設計(まだ未着手)
2. 顧客の返信(番号指定/自然文での再指定/曖昧で特定不能)を`slot_key`または
   「特定不能→再確認」に振り分けるLLM構造化出力の拡張(現状のスキーマには候補選択用の
   フィールドが無い)
3. 特定不能時の再確認メッセージ設計

次のvent前進ステップの候補とする。

## このステップで実施したこと

- `pending-timeout-ux.md`の文言案4(保留取得に失敗した場合の案内文)を
  `ConversationFlowStateMachine.select_slot()`の戻り値に接続した
  (`SelectSlotResult(success, message)`。失敗時、呼び出し側はmessageをそのまま
  顧客へ送信できる)。代替候補の文言(`alt_candidates`)は空き枠検索が未実装のため
  呼び出し側が用意する前提とした。
- 上記の対応表により、LLM構造化出力のフィールドとConversationFlowStateMachineの
  呼び出しタイミングの原則を明文化した。
- (2026-08-01 00:00 UTC追記)`requested_date_range`/`time_of_day_preference`を
  `AvailabilitySearcher.find_candidates()`に接続する`search_candidates_from_llm_output()`を
  `prototype/engine.py`に新規実装した。`requested_date_range`がnull(LLMが日付の手がかりを
  抽出できなかった場合)はNoneを返し、聞き直し文言の設計は呼び出し側の課題として残した。
  デモ(`_demo()`)にLLM構造化出力→検索→`present_candidates()`→`select_slot()`までの
  一連の流れを追加し、動作を確認済み。これにより上記「残課題」が新たな次の課題として判明した。
