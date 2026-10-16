# 削除候補最終確認クエリの統合方針決定(フェーズ239)

## 位置づけ

フェーズ234(firestore-composite-index-plan.md)で「結合実装フェーズでの判断課題」として
保留されていた、`deletion_candidate.list_deletion_candidates()`(単一フィールド範囲クエリ:
`deletion_candidate_at <= now`)と`build_deletion_candidate_confirmation_states()`
(インメモリでの`deletion_confirmation_sent_at == null`フィルタ)の2段階構成を、実Firestore
接続後に複合インデックス#4(`deletion_confirmation_sent_at` ASC, `deletion_candidate_at` ASC)
を使う1クエリへ統合するかどうかについて、判断を行う。deletion-candidate-final-confirmation-
design.md 7節・README.mdフェーズ238次回候補(3)に対応。

## 結論: 統合する

`list_deletion_candidates()`の呼び出し元を確認した結果、
`run_due_deletion_candidate_final_confirmations()`(`deletion_candidate_final_confirmation.py`)
の1箇所のみであり、本関数の結果は常に2段階目の`deletion_confirmation_sent_at`判定とセットで
使われる。他に独立した用途を持つ呼び出し元は存在しない(`test_deletion_candidate.py`の
単体テストを除く)ため、統合しても既存の機能・用途上の制約はない。

統合を推奨する理由(firestore-composite-index-plan.md記載のとおり機能上必須ではないが、
推奨する技術的理由):

現状の2段階構成では、1段目の`list_deletion_candidates()`が`deletion_candidate_at <= now`
のみで候補を抽出するため、一度`deletion_confirmation_sent_at`が設定された(=最終確認送信
済みの)workshop_idも、`deletion_candidate_at`自体は解約日+365日のまま変化しないため、
この一覧に永久に残り続ける。実Firestore接続後にこの2段階構成をそのまま維持すると、1段目の
クエリは「本当に処理が必要な候補」だけでなく「既に送信済みで今後何もする必要がない過去の
解約者全件」まで毎日読み込み続けることになり、読み取り件数がサービス運用期間に比例して
単調に増加する(送信済み件数は増え続け、減ることがないため)。

複合インデックス#4を用いた単一クエリ
`where deletion_confirmation_sent_at == null AND deletion_candidate_at <= now`に統合すれば、
Firestoreサーバー側で両条件を適用した上で結果を返すため、読み取り件数は「本当に処理が必要な
件数」(未送信かつ猶予期間超過、かつ「連絡不能」で再チェック対象のものを含む)に限定され、
送信済み件数の増加に影響されない。

## 実装方針(結合実装フェーズ向けメモ)

- Firestoreアダプタ実装時、`list_deletion_candidates()`相当の関数は
  `deletion_confirmation_sent_at == null`の等価条件も含めた、複合インデックス#4を使う単一
  クエリとして実装し直す(現状の2関数構成〈`list_deletion_candidates()` →
  `build_deletion_candidate_confirmation_states()`〉は実Firestore版では1関数に統合される)。
- InMemory実装・既存テスト(`test_deletion_candidate.py`・
  `test_deletion_candidate_final_confirmation.py`)は現状の2段階構成のままで構わない
  (インメモリ線形走査にコスト差はなく、Protocolのシグネチャを変える必要がないため)。
  本フェーズでは既存コード・テストへの変更は行わない。
- 本フェーズでは設計判断の記録のみに留め、実コード化(Firestoreアダプタ本体の実装)は他の
  実Firestore接続作業と同様、オーナー承認後の結合実装フェーズに持ち越す。

## 残る課題

- 実際のFirestoreクエリ実装・複合インデックスのデプロイはGCPプロジェクト作成・Firestore
  有効化(オーナー承認待ち)後。
- 同種の「InMemory実装では2段階だが実クエリでは1段に統合可能」なパターンが他venture
  (aircon-pasha・course-set-pasha・forklift-pasha・line-reservation-ai)の削除候補・通知系
  処理にも存在するかどうかの横展開検討は次回候補として残す。

最終更新: 2026-10-16 13:00 UTC(フェーズ239: フェーズ234の次回候補を受け、
deletion_candidate_final_confirmationの2段階クエリ構成を実Firestore接続後に1クエリへ統合
する方針を決定。読み取り件数が送信済み件数の増加に比例して単調増加する問題を解消できることを
統合理由として記録。コード変更なし)
