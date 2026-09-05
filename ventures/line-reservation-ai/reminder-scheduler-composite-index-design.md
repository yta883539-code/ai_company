# Cloud Function C(send_reminders)のFirestore複合インデックス具体化(フェーズ続き199)

## 位置づけ

firestore-composite-index-plan.md(フェーズ続き198)の「残る課題」に、
reminder-scheduler-design.mdの`select_due_initial_reminders()`/`select_due_resends()`が
実際に必要とするFirestore複合クエリ・インデックスが未確定のまま残っていた。
本ドキュメントでこれを具体化する。

## Cloud Function C側のクエリと関数内ロジックの切り分け

reminder-scheduler-design.mdの全体構成図が示す通り、Cloud Function Cの処理は
2段階に分かれている。

1. **Firestoreクエリ**: 「全店舗の confirmed かつ archivedAt == null な予約」を取得する。
   firestore-data-model.md 3節で既に、この条件は`stage == "confirmed" AND
   archivedAt == null`のクエリで対象を拾うと明記済みだった(2026-08-02時点で確定済み。
   ただし対応する`firestore.indexes.json`の索引定義自体は未着手のまま残っていた)。
2. **インメモリ判定**: 1で取得した`bookings`(Pythonのリスト)に対して、
   `select_due_initial_reminders(bookings, now)`/`select_due_resends(bookings, now, ...)`が
   `target_datetime <= now`・`予約日 > 今日`・`customer_replied_at`の有無等を判定する。
   これらはFirestoreへのクエリ条件ではなく、既に取得済みのPythonオブジェクトに対する
   通常の関数呼び出しである(reminder_scheduler.pyの実装済みシグネチャ
   `select_due_initial_reminders(bookings, now)`が示す通り、引数は`bookings`という
   コレクションであり、Firestoreクエリオブジェクトではない)。

このため、firestore-composite-index-plan.md「残る課題」が示唆していた
「reminder-scheduler-design.mdのconversationsクエリ」は、実際には1の
`stage == "confirmed" AND archivedAt == null`のみであり、2のtarget_datetime等の
条件に対応するFirestore複合インデックスは**そもそも不要**(インメモリ判定のため)
という点が、これまでどの設計docにも明記されていなかった曖昧さだった。

## 追加した複合インデックス(#5)

| # | 対象コレクション | クエリの用途 | フィールド(順序) | クエリスコープ |
|---|---|---|---|---|
| 5 | `conversations`(`stores/{storeId}/conversations/{sessionId}`) | Cloud Function C: 全店舗横断で前日リマインド・当日再送の候補となりうる確定予約(`stage == "confirmed" AND archivedAt == null`)を抽出 | `stage` ASC, `archivedAt` ASC | **Collection group**(#1・#2と同じく`stores/{storeId}/conversations`という店舗ごとのサブコレクション構造を全店舗横断で読むため) |

`firestore.indexes.json`(venture直下)に5件目の索引定義として追記した。

補足: 等値条件(`==`)のみを組み合わせるクエリは、単一コレクションスコープであれば
Firestoreの自動インデックスのマージ結合で複合インデックス無しに処理できる場合がある。
しかし本クエリは#1・#2と同様に`queryScope: COLLECTION_GROUP`が必須であり、
collection groupクエリは自動インデックスの対象外(単一フィールドの自動インデックスは
コレクション単位で作成されるため、店舗ごとのサブコレクションを横断するcollection group
読み取りには及ばない)であるため、等値条件のみであっても明示的な複合インデックス定義が
必要になる。この点は#1・#2の「補足」で指摘した内容の再確認にあたる。

## 残る課題

- 本インデックス(#5)を含む`firestore.indexes.json`全体のデプロイ自体は、
  GCPプロジェクト作成・Firestore有効化(オーナー承認待ち)の後の課題として残る。
- `select_due_resends()`の`customer_replied_at`判定・当日朝9時条件はインメモリ判定で
  完結するため追加インデックスは不要と結論したが、将来的に確定予約数が増加し
  「全confirmed予約をメモリに読み込んでからインメモリ判定する」方式がコスト・
  レイテンシ上ボトルネックになった場合(unit-economics-estimate.md・
  firestore-traffic-cost-estimate.mdの残課題である実測待ちと合わせて要検証)、
  `target_datetime`をFirestore側にも保持してクエリ条件に含める再設計が必要になる
  可能性がある。現時点では想定顧客数(数十〜百店舗規模、reminder-scheduler-design.md)
  では確定予約の総数は小さく、インメモリ判定で十分と判断し、先送りとする。
