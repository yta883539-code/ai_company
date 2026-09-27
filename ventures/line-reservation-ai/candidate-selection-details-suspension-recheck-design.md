# 候補提示後・確定前のsuspension_reason再チェック設計

作成日: 2026-09-27(フェーズ続き277)

## 背景

new-booking-suspension-guard-parity-review.md(フェーズ続き276)「確認2」が「次回以降の課題」
として残していた、`_handle_candidate_selection()`(候補選択)・`_handle_details()`(氏名・
メニュー確認→確定)到達時点でのsuspension_reason再チェックの要否について、本フェーズで設計・
実装した。

## 結論: 再チェックを追加する(優先度低だが対応コストは小さいと判明したため前倒し)

フェーズ続き276時点では「`change_context`をターンをまたいで保持する新しい状態の追加が必要で、
既存の`_search_context_by_user`等と同様のper-user辞書を増やす設計判断を伴う」ため実装作業の
規模が大きいと見積もっていたが、実際に設計してみると以下の理由で対応コストは小さいと判明した。

- ブロック時の後始末(hold中の枠のrelease・会話状態の削除)は
  `ConversationFlowStateMachine.cancel_booking()`をそのまま再利用できる。この時点のstageは
  `candidates_presented`/`awaiting_details`のいずれかで`confirmed`ではないため、
  `cancel_booking()`はオーナー通知を発生させない(同メソッドのdocstring「candidates_presented:
  まだhold()していないため取り消す実体が無く、会話状態のみ削除する」「awaiting_details:
  pending状態のholdをrelease()し、会話状態を削除する」「confirmed分のオーナー通知はここで行う」
  参照)。`_start_new_booking()`のブロック時にオーナー通知が無いことと挙動が揃う。
- 「change経由で開始されたか」の状態は、既存の`_search_context_by_user`と全く同じタイミング
  (`_start_new_booking()`が候補を提示する直前)で設定・同じタイミング(`_handle_cancel()`/
  `_handle_change()`の後始末)でクリアすればよく、新しいクリアポイントを追加する必要がない。

## 実装

### 1. 新しいper-user辞書 `_change_context_by_user: dict[str, bool]`

`_search_context_by_user`と同じ場所(`ConversationEventProcessor.__init__`)で宣言し、
`_start_new_booking()`が候補を提示する直前(`_search_context_by_user[user_id] = ...`の直後)で
`self._change_context_by_user[user_id] = change_context`を記録する。未記録(キー無し)の場合は
`False`扱い(=再チェックする、安全側デフォルト)とする。

クリアは`_search_context_by_user`と同じ2箇所(`_handle_cancel()`・`_handle_change()`の後始末)
に`.pop(user_id, None)`を追加するのみで揃う。

### 2. 再チェック処理 `_block_in_progress_new_booking_if_suspended()`

```python
def _block_in_progress_new_booking_if_suspended(self, user_id, now) -> Optional[DispatchResult]:
    if self._change_context_by_user.get(user_id, False):
        return None
    if not self._is_new_booking_blocked_by_suspension():
        return None
    self._flow.cancel_booking(user_id, now)
    self._candidates_by_user.pop(user_id, None)
    self._held_label_by_user.pop(user_id, None)
    self._search_context_by_user.pop(user_id, None)
    self._change_context_by_user.pop(user_id, None)
    suspension_reason = self._store_profile.get_suspension_reason(self._store_id)
    self._send(user_id, SUSPENDED_NEW_BOOKING_MESSAGE, now)
    return DispatchResult(action="new_booking_blocked_suspended", detail=suspension_reason)
```

`_handle_candidate_selection()`・`_handle_details()`の冒頭でこれを呼び、`None`以外が返れば
即座にその`DispatchResult`を返して以降の処理(候補選択・氏名確認)を行わない。

`change_context=True`(change経由、旧予約を既に解放済み)の場合はスキップし続ける。スキップ
しないと、旧予約を解放済みの顧客が新旧どちらの予約も持たない状態に陥ってしまうため
(suspension-reason-new-booking-block-design.md「change_context=Trueの場合はブロックしない」と
同じ懸念、new-booking-suspension-guard-parity-review.md「確認2」参照)。

### 3. 永続化配線への追加

processor-cache-persistence-design.md(フェーズ続き190)が定義した`processorCache`の4フィールド
(`candidates`/`heldLabel`/`searchContext`/`pendingNewBookingContext`)に、5番目のフィールドと
して`changeContext`(真偽値)を追加した。`_export_processor_cache_for_user()`/
`_import_processor_cache_for_user()`の両方に`searchContext`と同じタイミングで読み書きする分岐を
追加した。Cloud Functionの再起動を挟んでも(新規`ConversationEventProcessor`インスタンスでも)
change経由フローの識別状態が失われず、誤って再チェックでブロックされないようにするため
(この永続化が無いと、change経由で候補提示した直後に再起動を挟むと`_change_context_by_user`が
空になり、デフォルトのFalse=再チェック対象扱いに戻ってしまい、旧予約を解放済みの顧客が新旧
どちらの予約も持たない状態に陥りうる)。

## テスト

`test_cloud_function_process_event.py`に`CandidateSelectionDetailsSuspensionRecheckTests`を
新設し、以下4件を追加した。

1. `test_suspension_after_presentation_blocks_selection_for_fresh_new_booking`: 候補提示後
   (`change_context=False`)にsuspension_reasonが設定された場合、候補選択ターンで
   `new_booking_blocked_suspended`になり会話状態・ローカルキャッシュが後始末されること。
2. `test_suspension_after_selection_blocks_details_for_fresh_new_booking`: 候補選択(hold)後に
   suspension_reasonが設定された場合、氏名確認ターンで同様にブロックされること。
3. `test_change_context_bypasses_recheck_through_confirmation_while_suspended`: change経由
   (`change_context=True`)で始まった候補提示は、suspension_reasonが設定されていても候補選択・
   確定まで一貫してブロックされないこと(test_change_after_confirmed_still_re_searches_while_
   suspendedの延長)。
4. `test_change_context_persists_across_fresh_processor_instances`: `changeContext`が
   `processorCache`へ永続化され、全く新規のprocessor/flowインスタンス(Cloud Function再起動を
   模す)でも復元されて候補選択時に誤ってブロックされないこと。

venture全体870件(既存866件+新規4件)・schema検証28件、いずれもパスを確認した
(`python3 -m unittest discover -p "test_*.py"`、`python3 schema/validate_test_cases.py`)。

## 今回のスコープに含めなかったもの・次の課題

- `_handle_faq`/`_handle_escalation`/`_handle_cancel`は本フェーズの対象外(new-booking-
  suspension-guard-parity-review.md「確認3」の結論のまま変更なし)。
- 他venture(course-set-pasha・kura-pasha・aircon-pasha)への同種パターン(change/変更フロー
  自体は無いため直接の横展開対象ではないが、「候補提示・確定までの複数ターンにまたがるフロー」
  自体がこのventure固有の設計であり、他ventureは1メッセージ完結型の生成のため該当パターンが
  存在しない可能性が高い)の横断確認は次回以降の課題とする。
- 実Firestore・実LINE Messaging API接続は引き続きオーナー承認待ちの課題として残る
  (pending-approval.md参照)。

承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していないため
pending-approval.mdへの追記なし。
