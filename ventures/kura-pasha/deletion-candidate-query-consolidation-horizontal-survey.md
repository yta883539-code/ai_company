# 削除候補クエリ統合方針の横展開調査(フェーズ240)

## 位置づけ

deletion-candidate-query-consolidation-decision.md(フェーズ239)「残る課題」で次回候補と
していた、同種の「InMemory実装では2段階だが実クエリでは1段に統合可能」なパターンが他venture
(aircon-pasha・course-set-pasha・forklift-pasha・line-reservation-ai)の削除候補・通知系処理
にも存在するかどうかの横展開調査を行った。コード変更は行わず、各ventureの該当ファイルを読み、
構造を確認するのみに留める。

## 調査結果

### aircon-pasha: 同じ2段階構成が存在する

`deletion_candidate.list_deletion_candidates()`(`deletion_candidate_at <= now`のみで絞り込み)
→ `deletion_candidate_final_confirmation.build_deletion_candidate_confirmation_states()`
(`deletion_confirmation_sent_at`を読み取って状態を組み立てる)という2段階構成で、
`run_due_deletion_candidate_final_confirmations()`がこの順で呼び出す
(`deletion_candidate_final_confirmation.py:280-282`)。kura-pashaの決定と同じ理由
(送信済み件数の増加に比例して1段目の読み取り件数が単調増加する)がそのまま当てはまる。
なお本ventureはフェーズ321で`deletion_confirmation_unreachable_at == null`条件を同じ
複合インデックス(#5)に含める設計まで進めており、kura-pashaより統合方針の具体化が先行している。

### course-set-pasha: 同じ2段階構成が存在する

`deletion_candidate.list_deletion_candidates()`→
`deletion_candidate_final_confirmation.py`内の確認状態組み立て処理
(`deletion_candidate_final_confirmation.py:313`で呼び出し)という、aircon-pashaと同型の
2段階構成。本ventureはフェーズ238時点で`firestore-composite-index-plan.md`・
`firestore.indexes.json`自体がまだ存在しないため、統合方針の記録だけでなく複合インデックス
設計自体が未着手(aircon-pasha・forklift-pashaに後れを取っている)。

### forklift-pasha: 同じ2段階構成が存在する(関数名のみ異なる)

`list_deletion_candidates()`(`canceled_at + 365日`のみで絞り込み)→
`select_due_deletion_candidate_final_confirmations()`(`deletion_confirmation_sent_at`・
`deletion_confirmation_unreachable_at`の両方が未設定のものだけを残す)という2段階構成
(`cloud_function_send_deletion_confirmations.py:96`から呼び出し)。関数名は
`build_deletion_candidate_confirmation_states()`ではないが、構造は同一。

### line-reservation-ai: 既に単一述語に統合済み(対象外)

`is_store_deletion_candidate()`が`dormant_renotify_count`・`dormant_final_renotify_sent_at`・
`store_deletion_confirmation_sent_at`・`stripe_customer_id`・`suspension_reason`の5条件を
1つの述語関数内で判定し、`list_store_deletion_candidates()`はこの単一述語で全件を1回だけ
走査する(2段階に分かれていない)。これは4venture共通の「1段目で絞り込み→2段目で送信済み
判定」という構成ではなく、そもそも全条件を1つの関数にまとめた設計のため、本横展開の対象外
(統合方針を適用する必要がない、既に統合済みと同等の状態)。

## 結論

- aircon-pasha・course-set-pasha・forklift-pashaの3ventureには、kura-pashaフェーズ239で
  指摘したものと同じ「1段目のクエリが送信済み件数の増加に比例して読み取り件数が単調増加する」
  問題が存在する(aircon-pashaのみフェーズ321で統合方針の一部を複合インデックス設計に反映済み)。
- line-reservation-aiは単一述語設計のため対象外。
- 本フェーズでは調査結果の記録のみに留め、各ventureへの決定doc新設・複合インデックス設計への
  反映自体は各venture側の次回作業(または横展開担当フェーズ)に持ち越す。実コード化(Firestore
  アダプタ本体)はいずれも他の実Firestore接続作業と同様、オーナー承認後の結合実装フェーズに
  持ち越す。

## 次回候補

1. 承認待ち事項がオーナーから承認された場合はその着手を最優先。
2. course-set-pasha・forklift-pashaにも、aircon-pashaのdeletion-candidate-query-
   consolidation-decision.md相当の決定docを新設し、複合インデックス設計(course-set-pashaは
   firestore-composite-index-plan.md自体の新設から)に反映する。
3. 他venture・アイデア領域の前進。

最終更新: 2026-10-17 01:00 UTC(フェーズ240: フェーズ239「残る課題」の横展開調査を実施。
aircon-pasha・course-set-pasha・forklift-pashaには同じ2段階クエリ構成が存在し統合方針が
適用可能であること、line-reservation-aiは既に単一述語設計のため対象外であることを確認した。
コード変更なし)
