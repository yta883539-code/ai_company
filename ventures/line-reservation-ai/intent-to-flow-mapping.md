# LLM構造化出力 → ConversationFlowStateMachine呼び出しの対応付け

conversation-flow-state-machine-design.md で残課題としていた、LLMの構造化出力
(intent/datetime_candidate/confirmed等、schema/booking_output.schema.json準拠)から
`ConversationFlowStateMachine`の各メソッド(select_slot()/provide_details())を
どのタイミングで呼び出すかの対応付けを整理する。

## 対応表(会話の各ターンで、直前のLLM出力をもとに呼び出し側が行う処理)

| LLM出力の状態 | 呼び出し側ステージ前提 | 呼ぶメソッド | 備考 |
|---|---|---|---|
| `intent: new_booking`, `datetime_candidate`が曖昧(複数候補あり得る) | `candidates_presented`より前 | `search_candidates_from_llm_output()` → `present_candidates()` | 「来週土曜」等は`requested_date_range`/`time_of_day_preference`を`AvailabilitySearcher`に渡して複数候補に展開してから`present_candidates()`を呼ぶ(2026-08-01 00:00 UTC実装済み、下記「このステップで実施したこと」参照) |
| `intent: new_booking`, 顧客が候補から1件を特定できる返信 | `candidates_presented` | `resolve_candidate_selection()` → `select_slot()` | 提示した候補一覧(`search_candidates_from_llm_output()`の戻り値)から顧客の返信に対応する`slot_key`を特定する処理は`resolve_candidate_selection()`としてルールベースで実装済み(2026-08-01 01:00 UTC、[candidate-presentation-and-selection-design.md](candidate-presentation-and-selection-design.md)参照)。`None`が返った場合は`format_reconfirm_message()`を送信し`select_slot()`は呼ばない |
| `intent: new_booking`, `name`と`menu`が両方非nullで`confirmed: false` | `awaiting_details` | `provide_details()` | このLLM出力自体は「氏名・メニューを聞き取れた」ことを表し、確定の可否(hold中の枠との整合)はBookingSlotManager側が判定する |
| `intent: new_booking`, `confirmed: true`(LLMが確定文言を生成) | - | (呼ばない) | `confirmed`はLLMの発話意図フラグであり、実際の確定はBookingSlotManager.confirm()の成功可否が真実。provide_details()の戻り値(bool)を正としてLLMのconfirmedと矛盾する場合は安全側([schema-validation-report.md](schema-validation-report.md)のE8方針)に倣いエスカレーションする |
| `intent: cancel` | 任意 | `cancel_booking()` | cancel-intent-handling-design.md準拠(2026-08-02実装)。stageに応じてhold/confirm済みの枠を`release()`し、confirmed分のみEscalationConsolidator経由でオーナーへ通知する |
| `intent: escalation` / `faq` / `change` / その他 | 任意 | (呼ばない) | 予約フロー外。EscalationConsolidator/NotificationLogAggregator側の処理に委ねる(`change`は未実装、cancel-intent-handling-design.mdの残課題) |

## 解決済み: 提示した候補一覧から顧客の返信に対応する`slot_key`を特定する処理

`search_candidates_from_llm_output()`(prototype/engine.py)により
`requested_date_range`/`time_of_day_preference` → 空き枠候補一覧の変換は実装済みになり、
その次のステップ「提示した候補一覧(例: 3件)のうち、顧客が『2番目で』『8/9の12:00〜でお願いします』
のように返信した内容から`select_slot()`に渡す`slot_key`を1件特定する処理」は
candidate-presentation-and-selection-design.mdでルールベースの解決方式として設計し、
`format_candidates_message()`/`resolve_candidate_selection()`/`format_reconfirm_message()`として
`prototype/engine.py`に実装済み(2026-08-01 01:00 UTC、詳細は下記「このステップで実施したこと」参照)。
LLM構造化出力のスキーマ拡張は行わず、顧客の生返信テキストを直接`resolve_candidate_selection()`に
渡す設計とした(スキーマ拡張要否の再検討はcandidate-presentation-and-selection-design.mdの
「今後の課題」に残す)。

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
- (2026-08-01 01:00 UTC追記)上記で判明した課題に対応。候補一覧の採番提示文言・
  顧客返信からのslot_key特定ロジック・特定不能時の再確認文言をcandidate-presentation-and-selection-design.mdで
  設計し、`format_candidates_message()`/`resolve_candidate_selection()`/`format_reconfirm_message()`を
  `prototype/engine.py`に実装した。`resolve_candidate_selection()`は漢数字・丸数字・「N番目」表記・
  数字のみの返信を候補番号として優先的に解釈し、それ以外は候補labelの日付・時刻文字列との突き合わせに
  委ねる(`"8/9の方で"`のような日付の数字を候補番号と誤爆させないための設計、詳細は設計doc2節)。
  デモに番号指定・全角数字・漢数字・自然文(日付+時刻)・特定不能の5パターンを追加し、
  いずれも意図通りの結果になることを確認済み。
