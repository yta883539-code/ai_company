# 削除候補最終確認クエリの統合方針決定(フェーズ320)

## 位置づけ

kura-pashaフェーズ239(deletion-candidate-query-consolidation-decision.md)の次回候補
「同種の『InMemory実装では2段階だが実クエリでは1段に統合可能』なパターンが他venture
(aircon-pasha・course-set-pasha・forklift-pasha・line-reservation-ai)の削除候補・通知系
処理にも存在するかどうかの横展開検討」を受け、本venture(aircon-pasha)に最初に横展開する。

本venture(`prototype/deletion_candidate.py`・`prototype/deletion_candidate_final_
confirmation.py`)の構成はkura-pashaと同型である。

- 1段目: `deletion_candidate.list_deletion_candidates(store, now)` — 単一フィールド範囲
  クエリ`deletion_candidate_at <= now`を満たすuser_idを抽出(firestore-composite-index-
  plan.mdでは索引不要な単純range queryのため、従来これまで複合インデックス一覧#1〜#4には
  含めていなかった)。
- 2段目: `build_deletion_candidate_confirmation_states()`で1段目の結果にstoreから
  `is_following`・`deletion_confirmation_sent_at`を付加し、
  `select_due_deletion_candidate_final_confirmations()`がインメモリで
  `deletion_confirmation_sent_at is None`のみを残す。

## 結論: 統合する

`list_deletion_candidates()`の呼び出し元は`run_due_deletion_candidate_final_
confirmations()`(`deletion_candidate_final_confirmation.py`)の1箇所のみ(`test_deletion_
candidate.py`の単体テストを除く)であり、本関数の結果は常に2段階目の`deletion_confirmation_
sent_at`判定とセットで使われる。他に独立した用途を持つ呼び出し元は存在しないため、統合しても
既存の機能・用途上の制約はない。

統合を推奨する理由は、kura-pashaフェーズ239と同一である。現状の2段階構成では、1段目の
`list_deletion_candidates()`が`deletion_candidate_at <= now`のみで候補を抽出するため、一度
`deletion_confirmation_sent_at`が設定された(=最終確認送達済みの)user_idも
`deletion_candidate_at`自体は解約日+365日のまま変化しないためこの一覧に永久に残り続ける。
また`route_deletion_candidate_confirmation()`で`MARK_UNREACHABLE`(LINEブロック中)に倒れた
user_idは`deletion_confirmation_sent_at`が設定されないため毎回の実行で対象に残り続ける
(本venture固有の設計、モジュールdocstring参照)。この2種の「今後も対象に残り続ける候補」が
運用期間に比例して積み重なるため、実Firestore接続後にこの2段階構成をそのまま維持すると、
1段目のクエリは「本当に処理が必要な候補」だけでなく「既に送達済み、または連絡不能のまま
放置されている過去の解約者」まで毎回読み込み続けることになり、読み取り件数が単調に増加する。

単一クエリ`where deletion_confirmation_sent_at == null AND deletion_candidate_at <= now`
(複合インデックス新設が必要、下記参照)に統合すれば、Firestoreサーバー側で両条件を適用した
上で結果を返すため、読み取り件数は「本当に処理が必要な件数」(未送信かつ猶予期間超過)に
限定される。なお`MARK_UNREACHABLE`判定後も`deletion_confirmation_sent_at`は設定されない
ため、連絡不能のまま放置された候補は統合後もこの単一クエリに残り続ける点はkura-pashaと同じ
既知の限界として残る(解決には別途`deletion_confirmation_unreachable_at`を条件に加える等の
追加検討が必要だが、本フェーズの対象外とする)。

## 実装方針(結合実装フェーズ向けメモ)

- Firestoreアダプタ実装時、`list_deletion_candidates()`相当の関数は`deletion_confirmation_
  sent_at == null`の等価条件も含めた単一クエリとして実装し直す(現状の2関数構成
  〈`list_deletion_candidates()` → `build_deletion_candidate_confirmation_states()`〉は
  実Firestore版では1関数に統合される)。
- firestore-composite-index-plan.md(フェーズ314)の複合インデックス一覧に、本統合で必要と
  なる索引#5(`deletion_confirmation_sent_at` ASC, `deletion_candidate_at` ASC)を追加する
  (本フェーズで追記済み、下記参照)。
- InMemory実装・既存テスト(`test_deletion_candidate.py`・`test_deletion_candidate_final_
  confirmation.py`)は現状の2段階構成のままで構わない(インメモリ線形走査にコスト差はなく、
  Protocolのシグネチャを変える必要がないため)。本フェーズでは既存コード・テストへの変更は
  行わない。
- 本フェーズでは設計判断の記録とインデックス定義の追記のみに留め、実コード化(Firestore
  アダプタ本体の実装)は他の実Firestore接続作業と同様、オーナー承認後の結合実装フェーズに
  持ち越す。

## 残る課題

- 実際のFirestoreクエリ実装・複合インデックスのデプロイはGCPプロジェクト作成・Firestore
  有効化(オーナー承認待ち)後。
- `MARK_UNREACHABLE`のまま放置された候補が統合後の単一クエリに残り続ける点(上記)の扱いは
  次回候補として残す。
- 同種のパターンが残る横展開先(course-set-pasha・forklift-pasha・line-reservation-ai)の
  削除候補・通知系処理にも存在するかどうかの横展開検討は次回候補として残す。

最終更新: 2026-10-16 14:00 UTC(フェーズ320: kura-pashaフェーズ239の次回候補を受け、
deletion_candidate_final_confirmationの2段階クエリ構成を実Firestore接続後に1クエリへ統合
する方針を決定。`MARK_UNREACHABLE`候補が残り続ける本venture固有の論点を追加で記録。
firestore-composite-index-plan.mdに複合インデックス#5を追記。コード変更なし)
