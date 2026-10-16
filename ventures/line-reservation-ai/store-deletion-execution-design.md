# 削除候補の実際の削除実行: 設計(オーナー個別指示オンリー方式)

作成日: 2026-10-16(フェーズ続き323、2026-10-15 23:00 UTC記載の次回候補(2)
「削除候補の実際の削除実行バッチ自体は本venture・他4venture共通でいずれも未設計のまま
残っているため、aircon-pasha等の既存設計方針に合わせた設計に着手するかどうかの検討」を受けて着手)

## 1. 前提の確認

- store-deletion-candidate-final-confirmation-design.md(フェーズ続き317以降)・
  store-deletion-candidate-unreachable-owner-review-design.md(フェーズ続き320)はいずれも
  「削除候補の選定」「最終確認の送信」「連絡不能の読み取り専用レポート」までを設計・実装済みで、
  実際にFirestoreドキュメント(`stores/{storeId}`本体+5サブコレクション)を削除する処理
  自体はスコープ外として明示的に残していた(store_deletion_candidate.py冒頭コメント、
  render_unreachable_store_deletion_candidates_report()の「本リストは自動削除の対象では
  ありません」文言)。
- aircon-pasha・course-set-pasha・kura-pashaの同名モジュール(`deletion_candidate_final_
  confirmation.py`等)を確認したところ、いずれも同じ理由(実際の削除実行バッチがまだ存在
  しないため)で削除実行自体は未実装であり、本venture含む5venture全てで横並びに未着手の
  ままであることを確認した(grep `execute_deletion|delete_store|WriteBatch`で該当なし)。
- data-retention-policy.mdは削除方針として「MVPでは専用の削除バッチジョブは実装せず、
  実際のホスティング基盤確定後にCloud Schedulerによる日次〜週次バッチとして実装する」と
  記載しているが、これは文字どおり読むと「削除実行をCloud Schedulerで自動化する」方針に
  見える一方、store-deletion-candidate-unreachable-owner-review-design.mdは「連絡不能
  ケースは自動削除には進まず、オーナーが対話セッションで個別に削除可否を判断する」と
  明記しており、両文書の記述には緊張関係がある。本設計では後者(個別オーナー判断)を
  正とする。理由: (1)削除は不可逆操作であり、休止モード通知・最終確認通知のような
  再送可能な操作と異なりミスの訂正ができない、(2)aircon-pasha等の既存venture群も実質的に
  「削除実行バッチ」自体をいずれも実装していない(設計上の建前はCloud Scheduler化だが、
  実装着手例が存在しない)ことから、本リポジトリ全体の実務上の運用は既に個別オーナー判断に
  収束していると判断できる、(3)README.mdの運営ルール(手順5)自体が「支払い・アカウント
  作成・外部公開・送信など許可が必要なアクション」についてオーナーの個別承認を原則としており、
  顧客データの永久削除もこれに準ずる取り扱いとするのが安全側である。
- 本フェーズでは、data-retention-policy.mdの「削除の実行方法(MVP)」節の記述
  (Cloud Scheduler日次〜週次バッチ)を、本節の結論(個別オーナー判断)と整合させるよう
  補記する(4節参照)。

## 2. 方針

- **自動削除バッチは実装しない**。Cloud Scheduler・Cloud Functionsのいずれからも
  削除実行関数を呼び出す配線(`main(request)`等)を一切用意しない。これは実装漏れではなく、
  意図的にエントリポイントを作らないという設計上の決定である。
- 削除実行は、オーナーが本リポジトリとの対話セッション内で特定の`store_id`を指定して
  明示的に指示した場合にのみ、関数を直接呼び出す形で行う(本リポジトリの運営エージェントが
  対話の中で`execute_store_deletion()`相当の処理を実行する想定。Webhook等の外部経路からの
  到達性は持たせない)。
- 削除実行の対象を絞り込むための読み取り専用レポートは、既存の2系統
  (`list_store_deletion_candidates()`=最終確認未送信の新規候補、
  `list_unreachable_store_deletion_candidates()`=連絡不能と判定済みの候補)に加えて、
  最終確認は送信できたが長期間応答がない候補も含めて一覧化する必要があるが、
  「応答」の検出自体が既存のdormant再通知判定(`select_due_dormant_events()`)と同じ
  既知の限界(返信文面の内容を見ず、再開〈`stripe_customer_id`設定〉のみを「反応」とみなす)
  を抱えており、本フェーズで新たに解消する対象ではない(store-deletion-candidate-final-
  confirmation-design.md 4節が既に許容範囲と判断済み)。したがって本フェーズでは
  「最終確認送信済み(`store_deletion_confirmation_sent_at`設定済み)」という既存フラグの
  ままをオーナー提示対象とし、新たな「応答検出」フィールドの追加は行わない。

## 3. 削除実行対象の統合レポート(`render_deletion_execution_review_report()`)

- 既存の2系統のレポートをオーナーが1回の対話で見渡せるよう統合し、以下の3区分で表示する。
  1. 最終確認送信済み(`store_deletion_confirmation_sent_at`が設定済みかつ
     `store_deletion_confirmation_unreachable_at`が未設定): LINE pushで最終確認は届いて
     いるが未応答の候補。
  2. 連絡不能(`store_deletion_confirmation_unreachable_at`設定済み):
     既存の`list_unreachable_store_deletion_candidates()`と同じ対象。
  3. (参考情報)最終確認未送信の新規削除候補数(`list_store_deletion_candidates()`の件数のみ、
     詳細は別レポートのまま)。
- いずれの区分も「本リストは自動削除の対象ではありません。削除を実行する場合は、対話セッションで
  個別の店舗IDを指定してオーナーが明示的に指示してください」という文言を末尾に含める
  (既存の`render_unreachable_store_deletion_candidates_report()`と同じ注意書きを徹底する)。

## 4. 削除実行本体(`execute_store_deletion()`)

- シグネチャ: `execute_store_deletion(store_id: str, store_doc: DeletionTargetStoreProtocol,
  subcollections: Sequence[SubcollectionDeleterProtocol], *, confirmed_by_owner: bool) -> DeletionExecutionResult`。
- `confirmed_by_owner`はキーワード専用引数とし、デフォルト値を持たせない(呼び出し側が
  明示的に`True`を渡さない限り呼び出し自体が`TypeError`になる、またはキーワード省略時は
  `confirmed_by_owner=False`を渡したのと同じ扱いにして`DeletionNotConfirmedError`を投げる)。
  これにより、将来誤って本関数がスケジューラ等から条件判定なしに呼ばれても、
  `confirmed_by_owner=True`という明示的な意思表示が伴わない限り実削除に進まない
  安全策とする。
- 削除順序: data-retention-policy.md「サブコレクションとの削除順序」節の採用方針どおり、
  5サブコレクション(`bookingSlots`・`conversations`・`notificationLogEntries`・
  `notificationLogUniqueTopics`・`escalationWindows`)を**この順**で全件削除してから、
  最後に`stores/{storeId}`本体ドキュメントを削除する。途中で例外が発生した場合は、
  どのサブコレクションまで削除済みかを`DeletionExecutionResult.completed_subcollections`
  に記録して再試行可能にする(親ドキュメントが残っている限り`store_id`の手がかりを
  失わないため、同design節が指摘する再実行可能性を保つ)。
- 実際のFirestoreへの接続・`collection.list_documents()`によるページング・
  `WriteBatch`(上限500件/バッチ)の実装自体は、他ventureの同種処理と同様、実Firestore接続後
  (オーナー承認待ち)の課題として引き続き残す。本フェーズでは、依存注入可能な
  `SubcollectionDeleterProtocol`(`delete_all() -> int`、削除件数を返す)・
  `DeletionTargetStoreProtocol`(`delete() -> None`)を定義し、InMemory実装でオーケストレーション
  ロジック(順序・エラー時の再試行可能性・`confirmed_by_owner`ガード)のみを検証する。

## 5. data-retention-policy.mdの整合

- 「削除の実行方法(MVP)」節の記述(Cloud Scheduler日次〜週次バッチ)は、本設計の結論
  (個別オーナー判断・自動削除バッチは実装しない)と矛盾するため、本文書の方針を正としたうえで
  同節に注記を追記する(本フェーズ内で実施、data-retention-policy.md側の更新を参照)。

## 6. 本フェーズのスコープ

- 本フェーズは設計文書化+オーケストレーションロジックの実装(InMemoryスタブによるテストのみ)
  とし、実Firestore接続・Cloud Scheduler/Cloud Functions配線は行わない(意図的にスコープ外、
  2節参照)。承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は本フェーズでは
  発生していないためpending-approval.mdへの追記なし(実Firestore接続自体は既存の承認待ち
  事項の範囲内であり、新たな承認待ち事項ではない)。

## 7. 次回候補

1. 承認待ち事項(顧客ヒアリングの実連絡・実Firestore/GCPプロジェクト等)がオーナーから
   承認された場合は本venture既存設計一式の実装着手を最優先。
2. 同種の「削除実行オーケストレーションロジックの設計・InMemoryスタブ実装」を、
   aircon-pasha・course-set-pasha・kura-pashaの3venture(いずれもコレクション構成が
   本ventureと異なるため横展開には個別の設計調整が必要)へ横展開するかどうかの検討。
3. 他venture・アイデア領域の前進。
