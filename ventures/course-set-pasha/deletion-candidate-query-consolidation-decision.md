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

## `MARK_UNREACHABLE`候補の扱い(フェーズ300で解消)

aircon-pashaフェーズ321で発見された、`MARK_UNREACHABLE`に倒れた候補(LINEブロック中で
最終確認が送達できなかった候補)が`deletion_confirmation_sent_at`を設定されないため、
統合後の単一クエリに永久に残り続める問題は、本ventureにも同様に存在することを確認した
(`route_deletion_candidate_confirmation()`の経路判定・`send_deletion_candidate_final_
confirmations()`の書き込みロジックがaircon-pasha版と同型のため)。

aircon-pashaフェーズ321の「クリア配線」(`clear_deletion_confirmation_unreachable_at()`)
と同じ考え方を適用し、`prototype/deletion_candidate_final_confirmation.py`に同名関数を
新設した。本venture固有の2store構成(モジュールdocstring参照、`deletion_confirmation_
unreachable_at`は`deletion_store`〈`InMemoryProfileDeletionCandidateStore`〉側が保持し、
`is_following`は別の`profile_store`側が保持する)のため、`cloud_function_webhook.
process_follow_event()`・`dispatch_webhook_events()`の両方に新規の`deletion_store`引数
(未指定時はクリアを行わない安全側デフォルト)を追加し、再フォロー時に
`clear_blocked_but_billing_owner_notified_at()`と並んで呼ぶよう配線した。aircon-pashaは
単一storeで両方を満たすため引数が1つで済むが、本ventureは元々2store構成を採用している
ための実装差分であり、機能差はない。

これにより、再フォロー後は`deletion_confirmation_unreachable_at`・`unreachable_reason`が
クリアされ、次回バッチで通常のLINE push経路に戻れる。一方、再フォローされないまま連絡
不能が続く候補は`deletion_confirmation_unreachable_at`が設定されたままになるため、実
Firestore接続後の単一クエリに`deletion_confirmation_unreachable_at == null`を等価条件
として追加できる(下記「実装方針」更新)。

InMemory実装・既存テストは本変更の対象(`test_deletion_candidate_final_confirmation.py`に
`ClearDeletionConfirmationUnreachableAtTest`3件、`test_cloud_function_webhook.py`に
`test_refollow_clears_deletion_confirmation_unreachable_at`・`test_deletion_confirmation_
unreachable_at_untouched_when_deletion_store_not_given`の2件を追加)。

## 実装方針(結合実装フェーズ向けメモ)(フェーズ300で更新)

- Firestoreアダプタ実装時、`list_deletion_candidates()`相当の関数は`deletion_confirmation_
  sent_at == null AND deletion_confirmation_unreachable_at == null`の2つの等価条件を含めた
  単一クエリとして実装し直す(フェーズ299時点では`sent_at`のみの等価条件だったが、本フェーズ
  で`unreachable_at`も条件に追加)。
- 本venture側にはaircon-pasha等が持つ`firestore-composite-index-plan.md`・
  `firestore.indexes.json`がまだ存在しない(deployment-runbook.mdで複合インデックス1件が
  必要になる旨の記載修正のみ済)ため、これらのファイル新設・複合インデックスの具体的な
  フィールド構成の記載は次回候補として残す。
- InMemory実装・既存テスト(`test_deletion_candidate.py`・`test_deletion_candidate_final_
  confirmation.py`)の`select_due_deletion_candidate_final_confirmations()`自体は変更不要
  (インメモリ線形走査にコスト差はなく、Protocolのシグネチャを変える必要がないため)。
  「クリア配線」(`clear_deletion_confirmation_unreachable_at()`・
  `process_follow_event()`/`dispatch_webhook_events()`への配線)のみを本フェーズで追加した。
- 実Firestoreクエリ本体の実装(Firestoreアダプタ本体)は他の実Firestore接続作業と同様、
  オーナー承認後の結合実装フェーズに持ち越す。

## 残る課題

- 実際のFirestoreクエリ実装・複合インデックスのデプロイはGCPプロジェクト作成・Firestore
  有効化(オーナー承認待ち)後。
- `firestore-composite-index-plan.md`・`firestore.indexes.json`の本venture向け新設
  (aircon-pasha・kura-pasha・forklift-pashaが既に持つもの)は次回候補として残す。
- 残る横展開先(forklift-pasha・line-reservation-ai)への同種の棚卸し・クリア配線の適用は
  次回候補として残す。

最終更新: 2026-10-16 22:00 UTC(フェーズ300: aircon-pashaフェーズ321で解消された`MARK_
UNREACHABLE`候補が統合後の単一クエリに永久に残り続ける問題が本ventureにも存在することを
確認し、同じ「クリア配線」を適用して解消。本venture固有の2store構成に合わせ
`process_follow_event()`・`dispatch_webhook_events()`に`deletion_store`引数を新設。
InMemory実装・テスト5件追加、テスト761件・schema検証21件パス)
