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

## `MARK_UNREACHABLE`候補の扱い(フェーズ321で解消)

フェーズ320時点では、`MARK_UNREACHABLE`に倒れた候補(ブロック中で送達できなかった候補)が
`deletion_confirmation_sent_at`を設定されないため、統合後の単一クエリ(#5)に永久に残り
続ける点を未解決の課題として残していた。

本フェーズでは、blocked-but-billing-owner-notification-design.md 6節「クリア配線」
(フェーズ175、`clear_blocked_but_billing_owner_notified_at()`)と同じ考え方を適用し、
`prototype/deletion_candidate_final_confirmation.py`に`clear_deletion_confirmation_
unreachable_at()`を新設した。`cloud_function_webhook.process_follow_event()`の
再フォロー時(`is_following`がTrueに戻るタイミング)に、既存の`blocked_but_billing_owner_
notified_at`のクリアと並んで本関数を呼ぶよう配線した(`UserProfileStoreProtocol`実装は
構造的に`DeletionConfirmationUnreachableAtStoreProtocol`〈読み書き両方〉を満たすため、
追加のアダプタは不要)。

これにより、ブロック解除(再フォロー)した候補は`deletion_confirmation_unreachable_at`・
`deletion_confirmation_unreachable_reason`の両方がクリアされ、次回バッチで通常のLINE push
経路に戻って最終確認を送達できる。一方、再フォローされないまま連絡不能が続く候補は
`deletion_confirmation_unreachable_at`が設定されたままになるため、実Firestore接続後の
単一クエリに`deletion_confirmation_unreachable_at == null`を等価条件として追加できる
(下記「実装方針」更新、複合インデックス#5を3フィールド構成に変更)。

`deletion-candidate-unreachable-owner-review-design.md`(オーナーが対話セッションで個別に
削除可否を判断するためのレポート、`list_unreachable_deletion_candidates()`)は本変更の
対象外で、クリアされた候補は次回レポート生成時に`deletion_confirmation_unreachable_at`が
Noneになるため自然に一覧から外れる(オーナー側の追加対応は不要)。

InMemory実装・既存テストは本変更の対象(`test_deletion_candidate_final_confirmation.py`に
`ClearDeletionConfirmationUnreachableAtTest`3件、`test_cloud_function_webhook.py`に
`test_refollow_clears_deletion_confirmation_unreachable_at`1件を追加)。実際の
`cloud_function_webhook.py`・`deletion_candidate_final_confirmation.py`へのコード追加は
本フェーズで実施済み(InMemory実装のみ、実Firestore接続は引き続きオーナー承認後)。

## 実装方針(結合実装フェーズ向けメモ)(フェーズ321で更新)

- Firestoreアダプタ実装時、`list_deletion_candidates()`相当の関数は`deletion_confirmation_
  sent_at == null AND deletion_confirmation_unreachable_at == null`の2つの等価条件を含めた
  単一クエリとして実装し直す(フェーズ320時点では`sent_at`のみの等価条件だったが、本フェーズ
  で`unreachable_at`も条件に追加)。
- firestore-composite-index-plan.md(フェーズ314)の複合インデックス#5を、
  (`deletion_confirmation_sent_at` ASC, `deletion_confirmation_unreachable_at` ASC,
  `deletion_candidate_at` ASC)の3フィールド構成に更新する(本フェーズで追記済み、下記参照)。
- InMemory実装・既存テスト(`test_deletion_candidate.py`・`test_deletion_candidate_final_
  confirmation.py`)の`select_due_deletion_candidate_final_confirmations()`自体は変更不要
  (インメモリ線形走査にコスト差はなく、Protocolのシグネチャを変える必要がないため)。
  「クリア配線」(`clear_deletion_confirmation_unreachable_at()`・
  `process_follow_event()`への配線)のみを本フェーズで追加した。
- 実Firestoreクエリ本体の実装(Firestoreアダプタ本体)は他の実Firestore接続作業と同様、
  オーナー承認後の結合実装フェーズに持ち越す。

## 残る課題

- 実際のFirestoreクエリ実装・複合インデックスのデプロイはGCPプロジェクト作成・Firestore
  有効化(オーナー承認待ち)後。
- 同種のパターンが残る横展開先(course-set-pasha・forklift-pasha・line-reservation-ai)の
  削除候補・通知系処理にも存在するかどうかの横展開検討は次回候補として残す。

最終更新: 2026-10-16 21:00 UTC(フェーズ321: フェーズ320の残る課題であった
`MARK_UNREACHABLE`候補が統合後の単一クエリに永久に残り続ける問題を解消。
`clear_deletion_confirmation_unreachable_at()`を新設し、再フォロー時のクリア配線を
`process_follow_event()`に追加(InMemory実装・テスト4件追加)。firestore-composite-
index-plan.mdの複合インデックス#5を3フィールド構成に更新。テスト719件・schema検証25件
パス)
