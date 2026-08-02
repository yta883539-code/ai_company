# 確定操作競合時の新しい空き枠の再提示

## 位置づけ
booking-slot-manager-design.md・webhook-function-b-implementation.mdの「未実装のまま残るもの」に
挙げていた、確定操作(`BookingSlotManager.confirm()`)自体が別ユーザーとの競合で失敗した場合の
「後着の予約に新しい候補を再提示する」動作を実装した。従来は謝罪文言(`BOOKING_CONFLICT_MESSAGE`)
を送るのみで、空き枠の再検索・再提示は行っていなかった。

## 設計
- `ConversationEventProcessor`に`_search_context_by_user`(user_id → (元のLLM出力, メニュー所要時間)の
  キャッシュ)を新設した。`_start_new_booking()`で最初の候補検索を行った時点の`output`
  (`requested_date_range`/`time_of_day_preference`を含む)とメニュー所要時間をここに保存する。
- `provide_details()`が`False`(確定操作競合)を返した場合、新設した
  `_represent_candidates_after_conflict()`を呼ぶ。この時点で`ConversationFlowStateMachine`側は
  既にstageを`candidates_presented`へ差し戻し、オーナーへの通知(`EscalationConsolidator.on_event()`、
  `escalation_reason='booking_conflict'`)も完了済みのため、ここでの追加のオーナー通知は行わない。
- キャッシュした検索条件で`search_candidates_from_llm_output()`を`now`(競合が判明した時点の時刻)を
  基準に再実行する。奪われた枠は`BookingSlotManager`側で既に別ユーザーの`confirmed`状態になっているため、
  `AvailabilitySearcher.find_candidates()`が自然に候補から除外する(特別な除外ロジックは不要)。
- 新しい候補が1件以上見つかった場合: `present_candidates()`でFlowの状態(候補一覧・
  `reconfirm_count`等)を上書きし、`_candidates_by_user`のキャッシュも更新したうえで、
  `BOOKING_CONFLICT_RETRY_MESSAGE`(謝罪+再案内する旨)に続けて`format_candidates_message()`で
  新しい候補一覧を送る。以降は通常の候補提示済み(`candidates_presented`)と同じ流れで、
  顧客はそのまま番号で選び直せる。
- 検索条件のキャッシュが無い(通常発生しない想定外ケース)場合や、再検索しても候補が0件
  (近日中に空きが無い)の場合は、従来通り`BOOKING_CONFLICT_MESSAGE`のみを送り、オーナーの人手対応に
  委ねるフォールバックを維持した。

## テスト(`prototype/test_cloud_function_process_event.py`)
- 競合発生時に奪われた枠を除いた新しい候補一覧がその場で送信されること、
  再提示された候補からも通常どおり番号選択→hold まで進められること
  (`test_booking_conflict_notifies_owner_once_and_represents_fresh_candidates`)
- 検索条件キャッシュが無いケースでは従来通り謝罪文言のみを送るフォールバックが働くこと
  (`test_booking_conflict_falls_back_to_apology_when_no_alternative_slot`)
- 既存69件(旧68件から純増1件)全件パス確認済み。

## 残る課題
- 再検索は初回提示時と同じ検索条件(日付レンジ・時間帯希望)をそのまま使い回す設計のため、
  「近隣の別日を広げて探す」等の柔軟な代替提案は行わない(範囲拡張はスコープ外として残す)。
- 実LLM/実LINE API接続自体は引き続きpending-approval.md記載のオーナー承認待ち。
