# LLM構造化出力 → ConversationFlowStateMachine呼び出しの対応付け

conversation-flow-state-machine-design.md で残課題としていた、LLMの構造化出力
(intent/datetime_candidate/confirmed等、schema/booking_output.schema.json準拠)から
`ConversationFlowStateMachine`の各メソッド(select_slot()/provide_details())を
どのタイミングで呼び出すかの対応付けを整理する。

## 対応表(会話の各ターンで、直前のLLM出力をもとに呼び出し側が行う処理)

| LLM出力の状態 | 呼び出し側ステージ前提 | 呼ぶメソッド | 備考 |
|---|---|---|---|
| `intent: new_booking`, `datetime_candidate`が曖昧(複数候補あり得る) | `candidates_presented`より前 | (呼ばない。候補提示メッセージを返すのみ) | 「来週土曜」等は空き枠検索で複数候補に展開してから`present_candidates()`を呼ぶ |
| `intent: new_booking`, 顧客が候補から1件を特定できる返信 | `candidates_presented` | `select_slot()` | 特定された候補を`slot_key`に変換する処理が別途必要(下記「残課題」参照) |
| `intent: new_booking`, `name`と`menu`が両方非nullで`confirmed: false` | `awaiting_details` | `provide_details()` | このLLM出力自体は「氏名・メニューを聞き取れた」ことを表し、確定の可否(hold中の枠との整合)はBookingSlotManager側が判定する |
| `intent: new_booking`, `confirmed: true`(LLMが確定文言を生成) | - | (呼ばない) | `confirmed`はLLMの発話意図フラグであり、実際の確定はBookingSlotManager.confirm()の成功可否が真実。provide_details()の戻り値(bool)を正としてLLMのconfirmedと矛盾する場合は安全側([schema-validation-report.md](schema-validation-report.md)のE8方針)に倣いエスカレーションする |
| `intent: escalation` / `faq` / その他 | 任意 | (呼ばない) | 予約フロー外。EscalationConsolidator/NotificationLogAggregator側の処理に委ねる |

## 残課題: `datetime_candidate`(自然文)→`slot_key`(具体的な枠)への変換

上記対応表のうち、`select_slot()`を呼ぶために必要な「顧客の自然文の日時表現を
具体的な`slot_key`(店舗ID・日付・時間帯のタプル)へ変換する処理」は、
本ventureではまだ設計・実装されていない。これには以下が必要になる:

1. 空き枠検索(店舗の営業時間・メニュー所要時間・既存予約からの空き算出)
2. LLMが返す`datetime_candidate`(自然文、例:「来週土曜の午後」)を空き枠検索の
   クエリ条件(日付範囲・時間帯範囲)へ変換する処理
3. 検索結果が複数ある場合の`present_candidates()`(候補提示)への差し戻し

これは`prototype/engine.py`の現在の5コンポーネントには含まれておらず、
「空き枠管理(在庫)」という新しいコンポーネントの新規設計が必要になる。
次のvent前進ステップの候補とする。

## このステップで実施したこと

- `pending-timeout-ux.md`の文言案4(保留取得に失敗した場合の案内文)を
  `ConversationFlowStateMachine.select_slot()`の戻り値に接続した
  (`SelectSlotResult(success, message)`。失敗時、呼び出し側はmessageをそのまま
  顧客へ送信できる)。代替候補の文言(`alt_candidates`)は空き枠検索が未実装のため
  呼び出し側が用意する前提とした。
- 上記の対応表により、LLM構造化出力のフィールドとConversationFlowStateMachineの
  呼び出しタイミングの原則を明文化した(ただし`datetime_candidate`→`slot_key`変換は未実装、上記残課題を参照)。
