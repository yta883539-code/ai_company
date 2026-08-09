# 予約記録の取得元(InMemoryBookingRecordStore)設計メモ

## 背景・課題

`format_booking_list_csv()`(予約一覧ページ「今週分をCSVで書き出す」)・
`build_customer_detail_view()`(顧客詳細ページ)は、いずれも「既にどこからか取得済みの
データ」を受け取って表示用に変換するだけの関数として先に実装されていた。しかしその
「取得元」(確定予約の一覧を店舗・期間で絞り込んで取得する処理、顧客ごとの過去予約記録を
取得する処理)自体は未実装のまま、README.md「次にやること」に
「ホスティング基盤(Cloud Functions)接続後の課題」として残っていた。

## 設計方針

`llm_call`スタブ(実LLM呼び出しを差し替え可能にした既存の設計)と同じ考え方を、
永続ストレージの取得元にも適用した。

- `InMemoryBookingRecordStore`(`prototype/engine.py`)が最小インターフェースを持つ:
  - `record_confirmed(store_id, slot_key, customer_name, menu)`: 確定予約を1件記録する。
  - `list_booking_entries(store_id, start_date, end_date)`: `BookingListEntry`のリストを
    返す。`format_booking_list_csv()`にそのまま渡せる。
  - `customer_records(customer_name)`: `CustomerBookingRecord`のリストを返す。
    `build_customer_detail_view()`にそのまま渡せる。
- `ConversationFlowStateMachine`に`record_store`(任意引数、既定None)を追加。渡すと
  `provide_details()`の確定成功時に自動で`record_confirmed()`を呼ぶ。未指定時は従来通り
  何もしない(既存呼び出し側・テストへの後方互換)。
- 実際のFirestore等への差し替えは、同じ3メソッドを実装した別クラスに置き換えるだけで
  済む設計とした。GCPプロジェクト作成・実Firestore接続そのものは行っていない
  (オーナー承認待ち、pending-approval.md参照)。

## デモ・テスト

- `prototype/engine.py`の`_demo()`末尾に、確定フロー→`InMemoryBookingRecordStore`→
  `format_booking_list_csv()`/`build_customer_detail_view()`まで一気通貫で確認できる
  デモを追加した。
- `prototype/test_engine.py`に`InMemoryBookingRecordStoreTest`(5件)を新規追加。
  店舗・期間での絞り込み、時刻順ソート、確定前(`provide_details()`未実行)は記録しない
  こと、`record_store`未指定時の後方互換、を確認済み。既存テストと合わせて全87件パス。

## キャンセル・変更時の記録更新(2026-08-09 08:00 UTC追記)

上記「次の課題」だった、`cancel_booking()`/`change_booking()`と連動した記録更新を実装した。

- `InMemoryBookingRecordStore`に`record_cancelled(store_id, slot_key, status)`を新規追加。
  `_StoredBookingRecord`に`status_override`フィールド(既定None)を追加し、該当レコードへ
  `CANCELLED_STATUS`(「キャンセル済み」)または`CHANGED_STATUS`(「変更済み」)を書き込む。
  レコード自体は削除しない(顧客詳細ページの来店履歴として引き続き参照できるようにするため。
  `CustomerBookingRecord.status`のdocstringが元々「その他(キャンセル済み等)」を許容していた
  設計方針を踏襲)。
- `ConversationFlowStateMachine.cancel_booking()`/`change_booking()`のconfirmed分岐に、
  `record_store`が指定されていれば`record_cancelled()`を呼ぶ配線を追加した。
  `escalation_reason`(`booking_cancelled`/`booking_change_started`)と対応させ、
  cancelは`CANCELLED_STATUS`、changeは`CHANGED_STATUS`を使い分ける。
- `list_booking_entries()`(予約一覧CSV、来店予定のみを対象とする想定)は
  `status_override`が設定されたレコードを除外するよう変更。`customer_records()`
  (顧客詳細ページ)は引き続き全件を返す。
- change後に新しい日時で再確定した場合、旧レコード(変更済み)とは別に新レコードが
  来店予定として追加される(上書きではなく2件になる。顧客の予約変遷を追える設計)。
- テスト3件を新規追加(`test_cancel_booking_after_confirmed_updates_record_store_status`・
  `test_change_booking_after_confirmed_updates_record_store_status`・
  `test_cancel_booking_without_record_store_does_not_raise`)。既存分含め全90件パス。

## 来店後のstatus更新(2026-08-09 10:00 UTC追記)

上記「次の課題」だった、no-show-handling.mdが定めるオーナーの1タップ操作(予約一覧からの
手動チェック)を反映する`record_visited()`/`record_no_show_confirmed()`を実装した。

- `InMemoryBookingRecordStore`に`record_visited(store_id, slot_key)`・
  `record_no_show_confirmed(store_id, slot_key)`を新規追加。いずれも`record_cancelled()`と
  同じ内部処理(`_update_status()`に共通化)で、該当レコードの`status_override`へ
  `VISITED_STATUS`(来店済み・新設)/`NO_SHOW_CONFIRMED_STATUS`(既存)を書き込む。
  レコードは削除しない(顧客詳細ページの来店履歴として引き続き参照できるようにするため、
  `record_cancelled()`と同じ方針)。
- `record_cancelled()`と同様、`ConversationFlowStateMachine`からの自動呼び出しは行わない。
  no-show-handling.mdの通り「来店済み」チェックも「無断キャンセル確定」も顧客側の会話フローでは
  なくオーナー側設定画面(予約一覧)での手動操作が起点のため、呼び出し元はオーナー向けUI配線
  (ホスティング基盤確定後)側になる想定。
- `list_booking_entries()`(予約一覧CSV、来店予定のみ対象)からは来店済み・無断キャンセル確定の
  レコードも除外される(cancel/change済みと同じ扱い)。`customer_records()`(顧客詳細ページ)には
  引き続き含まれ、`build_customer_detail_view()`の無断キャンセル確定数・直近の無断キャンセル日の
  集計に反映される。
- テスト3件を新規追加(`test_record_visited_updates_status_and_excludes_from_booking_list`・
  `test_record_no_show_confirmed_is_counted_by_customer_detail_view`・
  `test_record_visited_for_unknown_slot_does_not_raise`)。既存分含め全93件パス。

- (解消済み 2026-08-09 11:00 UTC: リマインド返信検知(customer-reply-detection-design.md)による
  `reminder_replied`更新を実装した。`record_reminder_replied(store_id, slot_key)`を新設し、
  `ConversationFlowStateMachine.record_reminder_reply(user_id)`から、confirmed状態の会話に
  何らかのメッセージが届いた事実(内容は問わない)を渡す。Cloud Function B
  (`cloud_function_process_event.py`の`process()`)から、既存の`confirmed_reply_recorder`
  (customerRepliedAt、Firestore向け)と並行してこのメソッドを呼ぶよう配線した。
  `confirmed_reply_recorder`と異なりFirestore接続を要さないため、GCPプロジェクト作成前でも
  動作する(record_store自体がインメモリのため)。テスト7件新規追加、既存分含め全210件パス
  (詳細はREADME.mdフェーズ(続き93)参照))

## MVPスコープの範囲外として残す点(次の課題)

いずれも実ホスティング基盤への接続時に、この最小インターフェースを実装したFirestore版
クラスへ差し替える際に併せて設計する。

- 複数プロセス・複数インスタンス間での永続化(engine.pyの他の状態と同様、単一プロセスの
  メモリ内でのみ有効)。
- 「[今週分をCSVで書き出す]」ボタン押下→実際のファイルダウンロードへの配線、予約一覧ページの
  「来店済み」チェック操作・オーナー向け通知(no-show-handling.md)からの実呼び出し配線、および
  画面表示そのものへの配線は、フロントエンド実装(ホスティング基盤確定後)の課題として
  引き続き残る。
