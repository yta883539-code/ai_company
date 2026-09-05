# Firestore複合インデックス定義の集約(フェーズ続き198)

## 位置づけ

deployment-runbook.md ステップ2「Firestore有効化」に以下の記載が残っていた。

> ただしfirestore-transaction-design.mdで前提としているコンポジットインデックスのみ、
> デプロイ前に`firestore.indexes.json`として定義しコンソールまたは
> `gcloud firestore indexes composite create`で先行作成する
> (対象: booking_slotsのstore_id+status+start_time等、複合クエリを使う箇所)。

しかし実際に複合インデックスが必要と個別に記録されていた箇所は、これまで
firestore-transaction-design.md・firestore-data-model.md・trial-end-scheduler-design.md
の3ファイルに分散したままで、いずれも「実装着手時に具体的に記述する」「実GCPプロジェクト
作成後にコンソールの自動提案リンクから作成する」として先送りにされていた。本ドキュメントは
それらを1箇所に集約し、実際にデプロイ可能な`firestore.indexes.json`を先行して書き出す
(GCPプロジェクト作成・Firestore有効化自体はオーナー承認待ちのため、ここではJSONの
中身を確定するだけの机上作業に留まる)。

## 集約した複合インデックス一覧

| # | 対象コレクション | クエリの用途 | フィールド(順序) | クエリスコープ | 出典 |
|---|---|---|---|---|---|
| 1 | `escalationWindows`(`stores/{storeId}/escalationWindows/{sessionId}`) | `flush_due_windows()`: 全店舗横断で`queuedCount > 0 AND windowOpenedAt < (now - WINDOW)`を満たすウィンドウを検出 | `queuedCount` ASC, `windowOpenedAt` ASC | **Collection group**(全店舗横断のため`storeId`を跨いだ検索が必須) | firestore-transaction-design.md「`flush_due_windows()`のクエリ設計」 |
| 2 | `conversations`(`stores/{storeId}/conversations/{sessionId}`) | `release_idle_conversations()`/`archive_completed_conversations()`: 全店舗横断で`lastActivityAt`が閾値を超えた失効候補を検出 | `storeId` ASC, `lastActivityAt` ASC | **Collection group** | firestore-data-model.md 3節「`release_idle_conversations()`〜」 |
| 3 | `notificationLogEntries`(`stores/{storeId}/notificationLogEntries/{autoId}`) | トライアル終了レポート(Cloud Function E)の`auto_handled_faq_count`集計: 特定1店舗内で`category == "auto_handled_faq" AND createdAt >= trialStartAt AND createdAt < trialStartAt+14days`を`count()`集約 | `category` ASC, `createdAt` ASC | Collection(呼び出し時に`storeId`が既知の1店舗クエリのため、collection groupではなく通常のサブコレクションクエリで足りる) | firestore-data-model.md 4節「トライアル期間(14日)を跨いだ集計クエリ」 |
| 4 | `stores`(ルートコレクション) | トライアル終了レポート候補抽出: 全店舗から`trialStartAt <= (now - 14日) AND trialEndReportSentAt == null`を検出 | `trialStartAt` ASC, `trialEndReportSentAt` ASC | Collection(`stores`はルートコレクションのため通常スコープで全店舗を横断できる) | trial-end-scheduler-design.md 3節「Firestoreクエリへの変換は〜」 |

補足:
- #1・#2は`stores/{storeId}/...`という同名サブコレクションが店舗ごとに存在する構造
  (firestore-data-model.md「設計方針」)のため、単一店舗クエリではなく
  `db.collection_group("escalationWindows")`/`db.collection_group("conversations")`の
  ように**collection group**として問い合わせる必要がある。Firestoreの複合インデックスは
  デフォルトでは「単一コレクションスコープ」で作成されるため、`firestore.indexes.json`
  側で`"queryScope": "COLLECTION_GROUP"`を明示しないと、これらのクエリはコンソールの
  自動提案(実行時エラーからのリンク)を経ても正しいスコープの索引を得られない可能性がある
  点は、これまでのどの設計docにも明記されていなかった実装時の見落としやすい注意点として
  本ドキュメントで新たに指摘する。
- #3は逆に、Cloud Function Eが処理対象の店舗ごとに`stores/{storeId}/notificationLogEntries`
  という具体的なパスを組み立てて問い合わせるため、collection groupは不要(通常の
  サブコレクションクエリで十分)。#1・#2との違いを明確にするため表に明記した。
- deployment-runbook.mdが例示していた「booking_slotsのstore_id+status+start_time」は、
  現時点でreminder-scheduler-design.md・candidate-buffer-analysis.md等のどの設計docにも
  具体的なクエリ条件として明記された記載が見当たらず、deployment-runbook.md執筆時点での
  見込み記載(具体化前のプレースホルダ)だったと判断する。reminder-scheduler-design.mdの
  `select_due_initial_reminders()`/`select_due_resends()`は`conversations`ドキュメントの
  `stage`/`reminderSentAt`/`resendSentAt`/`customerRepliedAt`等の等価条件を組み合わせる
  設計だが、これを全店舗横断のFirestoreクエリとして具体的にどう表現するか(#2と同じ
  collection groupクエリに条件を追加する形になる見込み)は本ドキュメントでは未確定のまま
  次回以降の課題として残す(下記「残る課題」参照)。deployment-runbook.mdの当該箇所は
  誤解を避けるため、booking_slotsという具体的なコレクション名を含む記載を削除し、
  「上記4件(本ドキュメント参照)に加え、reminder-scheduler-design.mdのconversations
  クエリは次回以降に具体化」という記載に更新する。

## 生成した`firestore.indexes.json`

上記1〜4を`gcloud firestore indexes composite create`相当の宣言的定義として
`firestore.indexes.json`(venture直下)に書き出した。実際の`gcloud firestore deploy
--only firestore:indexes`実行は、GCPプロジェクト作成・Firestore有効化(オーナー承認待ち)
の後にステップ2の一部として行う。

## 残る課題

- ~~reminder-scheduler-design.mdの`select_due_initial_reminders()`/`select_due_resends()`が
  実際に必要とするFirestore複合クエリ・インデックスの具体化(上記補足参照)。~~
  (解消済み 2026-09-05 07:00 UTC: reminder-scheduler-composite-index-design.md
  〈フェーズ続き199〉参照。実際にFirestoreクエリ条件になるのは`stage == "confirmed"
  AND archivedAt == null`(collection group、索引#5として追加)のみで、
  `target_datetime`等はインメモリ判定のため追加インデックス不要と判明した)
- 本表の各インデックスが実際にFirestoreコンソールの「クエリ実行時エラーからの自動提案」と
  一致するかは、実Firestore接続後(オーナー承認待ち)の検証課題として残る。
- 想定データ量でのインデックス自体のストレージ課金への影響は、firestore-traffic-cost-estimate.md
  の残課題(実クライアント接続による実測待ち)と合わせて未着手のまま。
