# 厳守事項2(候補提示→選択→確定の2ステップ厳守)の構造的保証の確認(2026-08-22 04:00 UTC)

## 位置づけ

llm-quality-verification-plan.mdの検証観点表・行2「厳守事項2(候補提示→選択→確定の2ステップを
必ず踏む)」は「人手のみ(会話が複数ターンにまたがるため機械チェック困難)」と分類されていた。
fixed-vocabulary-tone-check-design.mdで固定語彙(項目2・3)が「LLMの自由文ではなく構造化データの
組み立て方によって構造的に保証されている」と整理したのと同じ観点で、この厳守事項についても
呼び出し側の実装(`intent-to-flow-mapping.md`・`ConversationFlowStateMachine`)がどこまで
構造的に保証しているかを確認した。

## 確認したこと

`prototype/engine.py`の`ConversationFlowStateMachine.provide_details()`は次の実装になっている
(engine.py:1030-1032):

```python
state = self._states.get(user_id)
if state is None or state.stage != "awaiting_details":
    raise ConversationFlowError(f"unexpected stage for provide_details: {state}")
```

`awaiting_details`ステージに到達できるのは`select_slot()`(候補選択)が成功した場合のみ
(conversation-flow-state-machine-design.md「実装した状態遷移」参照)。つまり、呼び出し側が
`select_slot()`を経ずに`provide_details()`を呼ぶと、状態が`candidates_presented`のままなので
必ず`ConversationFlowError`が送出され、確定(`confirmed`)へは進めない。

さらに`intent-to-flow-mapping.md`の対応表を確認すると、`provide_details()`を呼ぶ条件は
「呼び出し側ステージ前提: `awaiting_details`」と明記されており、LLM出力の`confirmed: true`
フラグそのものではこのメソッドを呼ばない設計になっている(対応表4行目「(呼ばない)」)。
つまり、LLMが仮に「候補提示を省略していきなり確定文言を生成」しても、呼び出し側コードが
`awaiting_details`ステージでない限り`provide_details()`を呼び出さない/呼び出しても例外になるため、
**候補提示→選択のステップをスキップして確定状態に進むことはコード上構造的に不可能**である。

## 機械チェックとしての裏付け

`prototype/test_engine.py`の`ConversationFlowStateMachineTest`に
`test_provide_details_before_select_slot_raises`を追加した。`present_candidates()`直後
(`candidates_presented`)の状態から`select_slot()`を経ずに`provide_details()`を呼ぶと
`ConversationFlowError`になり、例外後もステージが`candidates_presented`のまま
(誤って`confirmed`へ進んでいない)ことを確認するテスト。既存の
`test_unexpected_stage_call_raises`は「そもそも会話状態が存在しないユーザー」のケースのみを
カバーしていたため、「候補提示済みだが選択未了」という厳守事項2に直接対応するケースを
新たにカバーした。`python3 -m unittest discover`でline-reservation-ai配下全296件パスを確認済み
(このテスト追加分含む)。

## llm-quality-verification-plan.mdへの反映

検証観点表・行2の「機械チェック可否」を「人手のみ」から「一部機械チェック可能」に更新し、
以下の切り分けを明記する:

- **機械チェック可能な部分**: 呼び出し側コードが`select_slot()`を経ずに`confirmed`へ進むことは
  ConversationFlowStateMachineの例外機構により構造的に不可能。この保証自体は
  `test_provide_details_before_select_slot_raises`で検証済み(コードが将来変更されても
  テストが壊れて検知できる)。
- **引き続き人手判定が必要な部分**: LLMが実際に生成する自由文の会話として、顧客に対し
  候補提示のターンを踏んだ自然な文面になっているか(構造化出力のintent/confirmed等の
  フィールド自体は正しくても、自由文側の言い回しが唐突に確定を装っていないか等)は、
  実LLM接続後に人手で確認する必要がある。

## 残る課題

- ~~この確認はconversation-flow-state-machine-design.md・intent-to-flow-mapping.mdの設計通りに
  Cloud Functions側の実装が呼び出し順序を守っている前提に立っている。実際のWebhook実装
  (`prototype/cloud_function_process_event.py`)がこの対応表通りに`provide_details()`を
  呼んでいるかどうかの確認は別途行っていない(次回以降の点検候補)。~~
  → 対応済み(2026-09-15、フェーズ続き231)。`prototype/cloud_function_process_event.py`の
  `_process_message_event()`(730行台〜)を確認したところ、`intent == "new_booking"`の分岐は
  `self._flow.stage(user_id)`(793行目、ConversationFlowStateMachine自身から読み取った値)
  のみを見て`stage == "awaiting_details"`の時だけ`_handle_details()`(内部で`provide_details()`
  を呼ぶ)へルーティングしており(798-799行目)、`stage == "candidates_presented"`の間は
  LLM出力の`name`/`menu`/`confirmed`フィールドの中身に関わらず必ず`_handle_candidate_
  selection()`へ渡ることを確認した(intent-to-flow-mapping.mdの「呼び出し側ステージ前提:
  awaiting_details」の記載と一致)。分岐条件が(LLM出力ではなく)ConversationFlowStateMachine
  自身が管理するstageという単一の真実源(single source of truth)を参照しているため、
  Cloud Functions側の実装ミスで呼び出し順序がずれる余地は構造的に小さいと判断した。
  この保証を機械的に裏付けるため、`test_cloud_function_process_event.py`に
  `test_details_shaped_output_at_candidates_presented_stage_does_not_skip_selection`を
  新規追加した(candidates_presented状態でLLM出力がname・menu両方非null・confirmed: true という
  「provide_details()を誘発しそうな中身」であっても、reply_textが候補ラベルに一致しなければ
  `action: reask`のままcandidates_presentedに留まり、`confirmed`へは進まないことを確認)。
  venture全体806件全件(`python3 -m unittest discover -s prototype -p "test_*.py"`)・
  schema検証27件(`python3 schema/validate_test_cases.py`)いずれもパスを確認した。
  承認不要なコード確認・テスト追加のみで、外部サービスへの公開・アカウント作成・支払い・
  送信等は今回発生していないためpending-approval.mdへの追記なし。
- aircon-pasha・course-set-pashaは会話フロー型ではなくメモ入力→単発生成型のため、この種の
  複数ターン状態遷移の構造的保証という論点自体が存在しない(line-reservation-ai固有)。
