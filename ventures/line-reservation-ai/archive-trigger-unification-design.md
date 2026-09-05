# archive_completed_conversations() 実行トリガーの統一設計(フェーズ続き202)

## 位置づけ

target-datetime-denormalization-contingency-design.md(フェーズ続き201)の
「残る課題」に、「archive処理の遅延自体が原因で〈Cloud Function Cが読み込む
confirmed件数が〉膨らんでいる場合は、本設計の対象外(archive処理側の頻度見直しで
対応すべき別問題)として切り分ける」という先送り事項が残っていた。本ドキュメントは
その「archive処理側の頻度見直し」に着手し、現行設計(idle-conversation-trigger-
design.md)に残っていた遅延リスクを具体化・解消する。

## 1. 現行設計の再点検で見つかった問題

idle-conversation-trigger-design.mdは`archive_completed_conversations()`
(confirmed-state-archival.md)の実行トリガーとして「案B: Webhook便乗」を採用し、
`maybe_run_archive()`として実装済み(engine.py)。この方式は**店舗ごとに**
Webhookを受信するたびに(5分間引きで)その店舗のアーカイブ処理を実行する。

これは「専用インフラ不要で今すぐ実装できる」という利点がある一方、次の弱点を
見落としていた。

- アーカイブ対象は「来店日を過ぎたconfirmed会話」であり、**その店舗への新規の
  問い合わせ(Webhook)が届かない限り実行されない**。
- 来店日を過ぎた後、その店舗が(閑散期・長期休業・廃業間際等の理由で)しばらく
  顧客からのメッセージを受け取らなければ、`archivedAt`はnullのまま何日でも
  残り続ける。最大遅延はARCHIVE_AFTER_VISIT(1日)のような固定値ではなく、
  **「次にその店舗へ問い合わせが来るまでの時間」という店舗トラフィックに依存した
  無制限の値**になる。
- reminder-scheduler-composite-index-design.md/target-datetime-denormalization-
  contingency-design.mdが前提とする「Cloud Function Cが1回の実行で読み込む
  `stage == "confirmed" AND archivedAt == null`の件数」は、この遅延が積み重なる
  ほど本来の(来店予定の)件数以上に膨らむ。1,000件という切り替え閾値の妥当性を
  損なう変動要因になっていた。

## 2. 解決方針: Cloud Function C(send_reminders)からも実行する

reminder-scheduler-design.mdの設計により、Cloud Function Cは既に
「1店舗1ジョブではなく全店舗共通の単一Cloud Schedulerジョブ」として
**店舗のトラフィック(Webhook到着)の有無に関係なく**15分間隔(暫定)で
定期実行される設計になっている。この特性はarchive処理の要件(「来店日超過を
確実かつ低遅延で検知したい、ただし1日単位の粒度で十分」)に理想的に合致する。

そこで、`archive_completed_conversations()`相当の判定を**Cloud Function Cの
処理にも追加する**。Webhook便乗トリガー(案B)は廃止せず、高トラフィック店舗での
早期アーカイブに引き続き寄与するため併用する(「ベルト・アンド・サスペンダー」)。
Cloud Function C側を**正規のトリガー**、Webhook便乗を**補助的な早期実行**と
位置づけることで、店舗トラフィックが途絶えても最大遅延がCloud Scheduler起動間隔
(暫定15分)に収まるようになり、1,000件閾値の変動要因だった「archive遅延」を
実質的に排除できる。

## 3. 実装

`prototype/reminder_scheduler.py`に、`select_due_initial_reminders()`/
`select_due_resends()`と同じ入出力パターンの新関数を追加した。

- `ReminderBooking`に`archived_at: Optional[datetime] = None`フィールドを追加
  (firestore-data-model.mdの`conversations/{sessionId}.archivedAt`に対応)。
- `ARCHIVE_AFTER_VISIT_DAYS = 1`定数(confirmed-state-archival.mdの
  `ARCHIVE_AFTER_VISIT`と同値。値を変更する場合は両ファイルを揃えて更新する)。
- `select_confirmed_to_archive(bookings, now, after_visit_days=1) -> list[ReminderBooking]`:
  `archived_at is None`かつ`(now.date() - booking_date).days >= after_visit_days`の
  予約を返す(confirmed-state-archival.mdの判定式`now.date() - visit_date >=
  ARCHIVE_AFTER_VISIT`をそのまま踏襲、時刻ではなく日付単位の差分)。

`prototype/cloud_function_send_reminders.py`の`send_reminders()`に、初回
リマインド・再送の送信処理とは独立した最後のステップとして`select_confirmed_to_archive()`
の呼び出しを追加し、対象予約の`archived_at`を更新する。`SendRemindersResult`に
`archived: list[str]`(booking_id)を追加し、呼び出し元のログ・監視で件数を
追跡できるようにした。送信処理の成否(`failed`)とは無関係に常に実行する
(関心事が異なるため)。

テスト: `select_confirmed_to_archive()`単体のケース(未到達/翌日到達/既アーカイブ
除外/未来予約除外/閾値カスタマイズ)を`test_reminder_scheduler.py`に7件、
`send_reminders()`との結線(店舗トラフィック非依存でアーカイブされること、
同一実行内の送信失敗と独立していること等)を`test_cloud_function_send_reminders.py`に
4件追加した。venture全体746件全件・schema検証25件パスを確認済み。

## 4. 関連ドキュメントとの整合性

- confirmed-state-archival.mdの「実行トリガー」節(「実際のホスティング基盤が
  決まった時点で確定する」という未確定の記載)は、本ドキュメントとidle-
  conversation-trigger-design.mdにより「案B(Webhook便乗、補助)+ Cloud Function C
  定期実行(正規)」の併用に確定したため、追記が必要(次項で対応)。
- idle-conversation-trigger-design.mdの「未解決事項」に残っていた「トラフィックが
  長時間絶える営業時間外にconfirmed会話が長時間`_states`に残り続ける点」は、
  Cloud Function C側の定期実行により解消される(次項で反映)。

## 残る課題

- 実際のFirestoreクエリ(Cloud Function Cがconfirmed予約を読み込む際の
  `archivedAt`更新の書き込み)・実Cloud Scheduler設定は実Firestore接続後の課題
  (オーナー承認待ち、pending-approval.md参照)。
- ~~Cloud Function Cは現状「未送信・当日再送候補」の絞り込み済みbookingsを引数で
  受け取る設計(reminder-scheduler-design.md)だが、アーカイブ対象の判定には
  「archivedAtがnullな全confirmed予約」が必要なため、呼び出し元(Firestore読み取り
  クエリ)側で「未送信/再送候補」と「未アーカイブconfirmed」の2種類のクエリ結果を
  どうbookings一覧にまとめて渡すか(またはsend_reminders()を2回に分けて呼ぶか)の
  結線は、実Firestore接続時に別途詰める必要がある(本フェーズは判定ロジック自体の
  実装・検証にとどめた)。~~ → フェーズ続き203(2026-09-05 16:00 UTC)で解消済み。
  この懸念は「2種類のクエリ結果を結合する必要がある」という前提そのものが誤りだった。
  reminder-scheduler-design.md冒頭の全体構成図(手順1)は元々「全店舗のconfirmed かつ
  archivedAt == null な予約」という**単一のFirestoreクエリ**を想定しており、この
  条件は「未送信・当日再送候補」(予約日が未来または当日)と「未アーカイブconfirmed」
  (来店日超過)のいずれも包含する上位集合になっている。`select_due_initial_reminders()`
  (予約日 > 今日)・`select_due_resends()`(予約日 == 今日)・
  `select_confirmed_to_archive()`(来店日+`after_visit_days`日以上経過)は互いに
  `booking_date`と`now`の関係で排他的に分岐する条件のため、この単一クエリの結果を
  そのまま1回の`send_reminders()`呼び出しに渡すだけで3カテゴリすべてが正しく
  処理される(クエリを2種類用意して結合する処理も、`send_reminders()`を2回に
  分けて呼ぶ処理も不要)。`prototype/test_cloud_function_send_reminders.py`の
  `SingleQueryCoversAllThreeCategoriesTests`に、初回リマインド対象・当日再送対象・
  アーカイブ対象の3カテゴリを1つのbookingsリストに混在させて1回の呼び出しで
  検証するテストを追加した(テスト1件追加、venture全体747件全件・schema検証25件
  パスを確認)。呼び出し元が実際に発行するFirestoreクエリ自体(`WHERE stage ==
  "confirmed" AND archivedAt == null`相当)の実装は引き続き実Firestore接続後の
  課題として残る(上記1点目と同じ)。
