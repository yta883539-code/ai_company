# 削除候補最終確認クエリの統合方針決定(フェーズ163)

## 位置づけ

kura-pashaフェーズ240(deletion-candidate-query-consolidation-horizontal-survey.md)の
次回候補(2)「course-set-pasha・forklift-pashaにも、aircon-pashaの
deletion-candidate-query-consolidation-decision.md相当の決定docを新設し、複合インデックス
設計に反映する」を受け、本venture(forklift-pasha)に横展開する。

本venture(`prototype/deletion_candidate.py`)の構成はkura-pasha・aircon-pashaと同型である
(関数名のみ異なる、horizontal-survey.md「forklift-pasha」節で確認済み)。

- 1段目: `list_deletion_candidates(store, now)` — `canceled_at`が設定済みかつ
  `now >= canceled_at + 365日`のinternal_id一覧を抽出(単一フィールド範囲クエリ、
  `canceledAt <= now - 365日`相当)。
- 2段目: `select_due_deletion_candidate_final_confirmations(store, candidates)` —
  1段目の結果から、`deletion_confirmation_sent_at`・`deletion_confirmation_unreachable_at`
  のいずれかが既に設定済みの候補をインメモリで除外する。
  `cloud_function_send_deletion_confirmations.py:96`からこの順で呼び出される。

## 結論: 統合する

`list_deletion_candidates()`の呼び出し元は`cloud_function_send_deletion_confirmations.main()`
(`test_deletion_candidate.py`の単体テストを除く)の1箇所のみであり、本関数の結果は常に
2段階目の`select_due_deletion_candidate_final_confirmations()`判定とセットで使われる。
他に独立した用途を持つ呼び出し元は存在しないため、統合しても既存の機能・用途上の制約はない。

統合を推奨する理由は、kura-pashaフェーズ239・aircon-pashaフェーズ320と同一である。現状の
2段階構成では、1段目の`list_deletion_candidates()`が`canceled_at + 365日 <= now`のみで
候補を抽出するため、一度`deletion_confirmation_sent_at`または`deletion_confirmation_
unreachable_at`が設定された事業者も`canceled_at`自体は変化しないためこの一覧に永久に残り
続ける。実Firestore接続後にこの2段階構成をそのまま維持すると、1段目のクエリは「本当に処理が
必要な候補」だけでなく「既に送信済み、または連絡不能と判定済みの過去の解約者」まで毎回
読み込み続けることになり、読み取り件数が運用期間に比例して単調に増加する。

単一クエリ`where deletionConfirmationSentAt == null AND deletionConfirmationUnreachableAt
== null AND canceledAt <= (now - 365日)`に統合すれば、Firestoreサーバー側で3条件を適用した
上で結果を返すため、読み取り件数は「本当に処理が必要な件数」に限定される。

## `MARK_UNREACHABLE`相当(連絡不能)候補のクリア機構について

aircon-pashaフェーズ320〜321では、LINEブロック由来の`MARK_UNREACHABLE`候補が統合後の単一
クエリに永久に残り続ける問題を、再フォロー時に`deletion_confirmation_unreachable_at`を
クリアする`clear_deletion_confirmation_unreachable_at()`の新設で解消していた。

本venture(forklift-pasha)は連絡経路がメール1本のみで、LINEの「ブロック→再フォロー」に
相当する「連絡不能状態から自然に復帰するイベント」が存在しない(`deletion_candidate.py`
モジュールdocstring・UNREACHABLE_REASON定義参照、メール未登録/送信失敗のいずれも事業者側の
能動的な操作では解消されない)。このため、連絡不能と判定された候補はaircon-pashaのような
クリア配線を新設しても解消トリガーが存在せず、`clear_*()`相当の関数を追加する意義がない
(呼び出すタイミングが存在しない)。

したがって本ventureでは、連絡不能と判定された候補は単一クエリ統合後も恒久的に対象外となる
ことを意図した仕様とする(自動削除・自動再送の対象から外れるだけで、
`list_unreachable_deletion_candidates()`によるオーナー向けレポートには引き続き残り続け、
オーナーが対話セッションでメールアドレスの再確認依頼や個別削除可否を判断する前提は変わらない)。
これはkura-pasha(連絡不能概念自体を持たない)・aircon-pasha(再フォローで復帰可能)とは
異なる、本venture固有の設計判断として明記する。

## 実装方針(結合実装フェーズ向けメモ)

- Firestoreアダプタ実装時、`list_deletion_candidates()`相当の関数は`deletionConfirmationSentAt
  == null AND deletionConfirmationUnreachableAt == null`の2つの等価条件を含めた単一クエリ
  として実装し直す(現状の2関数構成〈`list_deletion_candidates()` →
  `select_due_deletion_candidate_final_confirmations()`〉は実Firestore版では1関数に統合
  される)。
- firestore-composite-index-plan.md(フェーズ150)の複合インデックス一覧に、本統合で必要と
  なる索引#3(`deletionConfirmationSentAt` ASC, `deletionConfirmationUnreachableAt` ASC,
  `canceledAt` ASC)を追加する(本フェーズで追記済み、下記参照)。
- InMemory実装・既存テスト(`test_deletion_candidate.py`)は現状の2段階構成のままで構わない
  (インメモリ線形走査にコスト差はなく、Protocolのシグネチャを変える必要がないため)。
  本フェーズでは既存コード・テストへの変更は行わない(前節のクリア機構の見送りを含め、
  コード変更は本フェーズの対象外)。
- 本フェーズでは設計判断の記録とインデックス定義の追記のみに留め、実コード化(Firestore
  アダプタ本体の実装)は他の実Firestore接続作業と同様、オーナー承認後の結合実装フェーズに
  持ち越す。

## 残る課題

- 実際のFirestoreクエリ実装・複合インデックスのデプロイはGCPプロジェクト作成・Firestore
  有効化(オーナー承認待ち)後。
- 残る横展開先(course-set-pasha)への同種決定docの新設は次回候補として残す
  (course-set-pashaはkura-pashaフェーズ240時点でfirestore-composite-index-plan.md自体が
  未着手のため、まず同ドキュメントの新設から必要になる)。

最終更新: 2026-10-17 02:00 UTC(フェーズ163: kura-pashaフェーズ240の横展開調査を受け、
本ventureの削除候補最終確認クエリの2段階構成を実Firestore接続後に1クエリへ統合する方針を
決定。連絡経路がメール1本のみで「連絡不能からの自然復帰イベント」が存在しないため、
aircon-pashaのクリア配線は本ventureには適用しない(連絡不能候補は恒久的に対象外とする)方針
も明記した。firestore-composite-index-plan.mdに複合インデックス#3を追加。コード変更なし、
`python3 prototype/run_all_tests.py`で全18ファイル中18件成功(回帰なし)を確認した。承認が
必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していないため
pending-approval.mdへの追記なし。)
