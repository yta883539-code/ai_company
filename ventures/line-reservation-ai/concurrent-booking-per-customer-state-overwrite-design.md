# 同一顧客が2件目の予約会話を開始した場合の_states上書き問題

作成日: 2026-11-21(フェーズ続き398)

## 発見の経緯

cancel-intent-handling-design.mdの残る課題の洗い出し中に、`ConversationFlowStateMachine`が
`_states[user_id]`を1顧客あたり1レコードのみ保持する設計になっている点を確認した。
`present_candidates()`(engine.py 1015〜1024行目)のdocstringには「新規会話・再提示のいずれでも
状態を初期化する」と明記されており、実装も`self._states[user_id] = _ConversationState(...)`で
既存レコードの有無を確認せず常に上書きする。

## 問題のシナリオ

常連客(N4想定)が既に`confirmed`(確定済み、例: 来週土曜10時のカラー予約)の状態で
`_states`に記録されている最中に、同じ顧客が別件の新規予約(例: 来月の別メニュー)の会話を
開始すると、`present_candidates()`が`_states[user_id]`を無条件に`candidates_presented`へ
上書きする。この結果:

1. 直後に顧客が「さっきの予約やっぱりキャンセルします」(=1件目の確定予約を指す)と送っても、
   `cancel_booking()`は現在の`stage`(2件目の`candidates_presented`または`awaiting_details`)
   しか参照できないため、cancel-intent-handling-design.mdの表に従い「候補提示中/仮押さえ中の
   キャンセル」として処理されてしまう(1件目の確定予約の`slot_key`はどこにも保持されなくなり、
   `BookingSlotManager`側はconfirmedのまま残り続け、顧客の意図と食い違う)。
2. 逆に2件目の会話を終える前に1件目について`change_booking()`を呼びたい場合も同様に
   現在のstageしか見えず、1件目の`slot_key`への参照手段が無い。
3. `archive_completed_conversations()`・`release_idle_conversations()`はいずれも
   `_states[user_id]`という1顧客1レコードの前提で来店日判定・タイムアウト判定を行っているため、
   2件目の状態で上書きされた後は1件目の確定予約がこの2つのクリーンアップ処理の対象からも
   外れる(実害は限定的だが、設計の前提が崩れている状態ではある)。

`BookingSlotManager`側の枠自体(1件目の`confirmed`ステータス)は`_states`とは別テーブルで
保持されているため消えず、前日リマインド等のスケジューラ発火経路(reminder-scheduler-design.md)が
`BookingSlotManager`の確定枠一覧から直接組み立てる設計であれば1件目のリマインドは影響を受けない
と見られるが、会話内でのcancel/change(自然文によるキャンセル・変更申し出)は`_states`経由のみの
ため、1件目は会話内キャンセル・変更の対象から実質的に外れてしまう。

## 対象顧客層における実在性

想定顧客層(美容室・整体院・パーソナルジム・学習塾)では、常連客が「次回の予約」を会計時に
その場で確定し、後日気が変わって別日程の予約を追加で申し出る、または定期便(整体院の週1
メンテナンス等)の次々回分を前倒しで確保するといった運用は現実的にありうる。頻度は高くない
可能性があるが、ゼロではない。

## 実装状況(2026-11-22 03:00 UTC追記)

下記1(最小対応案)を実装済み。`engine.py`の`present_candidates()`が、既存状態
`state.stage == "confirmed"`を検知した場合に状態を上書きせず
`escalation_reason="second_booking_while_confirmed_exists"`(`SYSTEM_ESCALATION_REASONS`に追加済み)
でオーナーへエスカレーションするよう変更し、戻り値を`None`から新設の
`PresentCandidatesResult`(`escalated`/`message`/`owner_notify_actions`)に変更した。
呼び出し側`cloud_function_process_event.py`の`_start_new_booking()`・
`_represent_candidates_after_conflict()`の2箇所を、戻り値の`escalated`を見て
エスカレーション時は候補提示メッセージを送らずハンドオフ文言を送る分岐に更新した
(`change_booking()`が呼び出し前にconfirmed状態を`del`済みのため、change経由では
この分岐は発生しない)。`prototype/test_engine.py`に回帰テスト2件
(`test_present_candidates_escalates_when_customer_already_has_confirmed_booking`/
`test_present_candidates_does_not_escalate_without_existing_confirmed_state`)を追加した。
あわせて、同一user_idでのリピート予約を前提に`present_candidates()`を2回呼んでいた既存テスト
`test_count_unique_customers_counts_distinct_names_per_store`
(`InMemoryBookingRecordStoreTest`)が新しいエスカレーション分岐に抵触して失敗することを発見し、
1件目の確定後に`archive_completed_conversations()`を呼んで確定済み会話メモリから外す
(本番の来店日+ARCHIVE_AFTER_VISIT経過後の自動アーカイブと同じ手順)よう修正して回帰を解消した。
既存テスト1064件(line-reservation-ai全体)・schema検証28件いずれもパス。

## 対応方針(当初案。1は実装済み、2は未着手)

既存の「1顧客1レコード」前提を全面的に「複数同時保持」に変更する実装(`_states[user_id]`を
`_ConversationState`単体から`list[_ConversationState]`へ変更し、`cancel_booking()`・
`change_booking()`・`release_idle_conversations()`・`archive_completed_conversations()`の
4メソッド全てで「どのレコードを対象とするか」の判定ロジックが追加で必要になる)は影響範囲が
大きいため、本フェーズでは設計のみ提示し実装は次回以降に回す。

1. **最小対応案(推奨)**: `present_candidates()`で上書き前に既存`state.stage == "confirmed"`
   を検知した場合、上書きせず新規会話をエスカレーション(`escalation_reason`を新設、例:
   `second_booking_while_confirmed_exists`)してオーナー対応に委ねる。実装コストが小さく、
   「状態なし」をオーナー転送にした既存方針(cancel-intent-handling-design.md)と同じ
   安全側の考え方を踏襲できる。常連客が2件目を自分で申し出るケース自体の頻度は高くないと
   見られるため、まずはこの簡易対応で運用し、実際の問い合わせ頻度を見てから本格対応
   (下記2)を検討するのが妥当と判断する。
2. **本格対応案**: `_states[user_id]`を`list[_ConversationState]`化し、cancel/change時に
   該当する予約を顧客との直前の会話文脈(どの予約について話しているか)またはオーナーへの
   確認で特定する。実装・テストコストが大きいため、1の運用実績を見てから着手するか判断する。

## 残る課題

- `cloud_function_process_event.py`の実HTTPエントリポイントに近いレベルの統合テスト
  (LINE Webhookペイロード・LLM出力をモックした`test_cloud_function_process_event.py`側)への
  第2ブッキングエスカレーションシナリオの追加は未着手(本フェーズはengine.py単体テストまで)。
- `BookingSlotManager`側で同一顧客名(`name`)による複数confirmed枠の検索が現状可能か
  (オーナーが2件目をどちらの予約として処理すべきか判断する際に使う)の確認も未着手。
- 上記「本格対応案2」(`_states[user_id]`の`list`化)は、最小対応案1の運用実績
  (実際にこのescalation_reasonが発火する頻度)を見てから着手するか判断する。
- 実LLM/実LINE API接続自体(オーナー承認待ち、pending-approval.md参照)。
