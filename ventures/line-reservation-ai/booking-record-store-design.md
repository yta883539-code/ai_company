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

## MVPスコープの範囲外として残す点(次の課題)

いずれも実ホスティング基盤への接続時に、この最小インターフェースを実装したFirestore版
クラスへ差し替える際に併せて設計する。

- 来店後のstatus更新(`来店予定` → `来店済み`/`NO_SHOW_CONFIRMED_STATUS`への遷移。
  no-show-handling.md参照)。
- リマインド返信検知(customer-reply-detection-design.md)による`reminder_replied`更新。
- 複数プロセス・複数インスタンス間での永続化(engine.pyの他の状態と同様、単一プロセスの
  メモリ内でのみ有効)。
- 「[今週分をCSVで書き出す]」ボタン押下→実際のファイルダウンロードへの配線、および
  画面表示そのものへの配線は、フロントエンド実装(ホスティング基盤確定後)の課題として
  引き続き残る。
