# 削除候補最終確認クエリの統合方針決定(フェーズ299)

## 位置づけ

kura-pashaフェーズ239(ventures/kura-pasha/deletion-candidate-query-consolidation-
decision.md)で指摘された「InMemory実装では2段階だが実Firestoreクエリでは1段に統合
できる」パターンが本venture(course-set-pasha)にも存在するかどうかを棚卸しした
(kura-pashaフェーズ239次回候補(2)、aircon-pashaフェーズ320で同パターンがaircon-pasha
にも存在すると確認済み、残る横展開先はcourse-set-pasha・forklift-pasha・
line-reservation-ai)。

## 確認結果: 同じパターンが存在する

`prototype/deletion_candidate.py`の`list_deletion_candidates()`
(`deletion_candidate_at <= now`の線形走査、kura-pasha版と同じ設計コメント「Firestoreの
範囲クエリにそのまま対応させられる形を想定」)と、
`prototype/deletion_candidate_final_confirmation.py`の
`build_deletion_candidate_confirmation_states()`(`deletion_confirmation_sent_at is None`
によるインメモリフィルタ、同関数は`list_deletion_candidates()`が返すuser_id一覧を受け取る
専用の後続処理)という、kura-pashaと全く同型の2段階構成であることを確認した。
`list_deletion_candidates()`の呼び出し元は`deletion_candidate_final_confirmation.py`内の
1箇所のみで、他に独立した用途を持つ呼び出し元は存在しない(`test_deletion_candidate.py`の
単体テストを除く)。

## 結論: 統合する(kura-pashaフェーズ239と同じ結論)

理由もkura-pashaフェーズ239と同じ: 現状の2段階構成では、一度
`deletion_confirmation_sent_at`が設定された(送信済みの)user_idも
`deletion_candidate_at`自体は変化しないため`list_deletion_candidates()`の結果に
永久に残り続け、実Firestore接続後は読み取り件数が送信済み件数の増加に比例して単調に
増加する。複合インデックス`deletion_confirmation_sent_at ASC, deletion_candidate_at ASC`
を用いた単一クエリ
`where deletion_confirmation_sent_at == null AND deletion_candidate_at <= now`に統合
すれば、この問題を回避できる。

## deployment-runbook.mdの記載修正が必要

ステップ2(45-50行)に「line-reservation-aiのような複合インデックスを要するクエリは
無いため、`firestore.indexes.json`の追加設定は不要」という記載があるが、本決定により
これは誤りであることが判明した。本venture作成時点ではまだ`deletion_candidate`関連の
2段階構成に複合インデックスが有用であるという着眼点(kura-pashaフェーズ239)が無かった
ため見落とされていたと考えられる。deployment-runbook.mdの該当記載を修正し、結合実装
フェーズで複合インデックス1件(`firestore.indexes.json`への追加)が必要になる旨を
明記する(本フェーズで実施)。

## 実装方針(結合実装フェーズ向けメモ)

- Firestoreアダプタ実装時、`list_deletion_candidates()`相当の関数は
  `deletion_confirmation_sent_at == null`の等価条件も含めた、複合インデックスを使う
  単一クエリとして実装し直す(現状の2関数構成は実Firestore版では1関数に統合される)。
- InMemory実装・既存テスト(`test_deletion_candidate.py`・
  `test_deletion_candidate_final_confirmation.py`)は現状の2段階構成のままで構わない
  (インメモリ線形走査にコスト差はなく、Protocolのシグネチャを変える必要がないため)。
  本フェーズでは既存コード・テストへの変更は行わない。
- 本フェーズでは設計判断の記録とドキュメント修正のみに留め、実コード化(Firestoreアダプタ
  本体の実装・`firestore.indexes.json`への実際の追加)は他の実Firestore接続作業と同様、
  オーナー承認後の結合実装フェーズに持ち越す。

## 残る課題

- 実際のFirestoreクエリ実装・複合インデックスのデプロイはGCPプロジェクト作成・Firestore
  有効化(オーナー承認待ち)後。
- 残る横展開先(forklift-pasha・line-reservation-ai)への同種の棚卸しは次回候補として残す。

最終更新: 2026-10-16 20:00 UTC(フェーズ299: kura-pashaフェーズ239の次回候補を受け、
同じ2段階→1段統合パターンが本ventureにも存在することを確認し、統合する方針を決定。
deployment-runbook.mdの「複合インデックス不要」という記載が誤りであることも判明し、
修正が必要であることを記録。コード変更なし)
