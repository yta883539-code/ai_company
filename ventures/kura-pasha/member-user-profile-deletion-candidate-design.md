# 除外メンバーuser_profileの削除候補化設計(フェーズ続き341)

## 位置づけ

data-retention-policy.md「非契約者メンバー除外時の保存期間論点」次回候補・
downgrade-excess-member-handling-design.md「4. 未検証・残課題」フェーズ続き340で、
`workshop_id`のnull化(フェーズ続き340で実コード化済み)の次に必要と確定していた
「`workshop_id`がnullになったuser_profileを1年後に削除候補として洗い出すロジック」を
設計・実コード化する。

既存の`deletion_candidate.py`(workshop単位、Stripe解約を起点に
`deletion_candidate_at = 解約日 + 365日`を判定する設計、フェーズ232)と対になる、
user_profile単位の削除候補化ロジックとして設計する。

## 1. 基準時刻をどこで持つか

`deletion_candidate.py`はworkshop側に`deletion_candidate_at`(計算済みの絶対時刻)を
直接書き込む設計だったが、本ケースでは以下の理由から「除外された時刻(`unlinked_at`)を
記録し、判定時に`+365日`を加える」方式を採用した。

- `unlink()`はworkshop側の縮小処理(`check_and_apply_pending_member_reduction`)から
  呼ばれる唯一の書き込み経路であり、`deletion_candidate_at`という計算済みの値では
  なく「除外された事実とその時刻」を記録する方が、`unlink`という関数名の責務
  (workshop_idを外す)と素直に一致する。
- 保留期間(RETENTION_DAYS=365)は`deletion_candidate.py`で既に定数化されており、
  同じ値を再利用する(保存期間ポリシーの単一のソースを保つ)。

## 2. UserProfileStoreProtocolの拡張

`unlink(user_id: str, unlinked_at: Optional[datetime] = None) -> None`
(第2引数を追加、省略時は既存呼び出しとの後方互換のため何も記録しない)

`get_unlinked_at(user_id: str) -> Optional[datetime]`
`all_unlinked_user_ids(self) -> list[str]`(`unlinked_at`が記録済みのuser_id一覧。
`deletion_candidate.py`の`all_workshop_ids()`と同じ役割)

`link(user_id, workshop_id)`は、再リンク時に以前の`unlinked_at`を無条件でクリアする
(以前除外されたことは無関係になるため)。これは`deletion_candidate.py`の
`clear_deletion_candidate_on_subscription_reactivated`(再アクティブ化時はクリア)と
同じ方針である。

`InMemoryUserProfileStore`・`FirestoreUserProfileProvider`の両方に実装した
(Firestore版は`unlinked_at`フィールドを`user_profile/{user_id}`ドキュメントに追加し、
`all_unlinked_user_ids`は`firestore_workshop_adapter.all_workshop_ids`と同じ
「コレクション全件`.stream()`してクライアント側でフィルタ」方式。deletion-candidate-
query-consolidation-decision.md同様、実運用規模が大きくなれば複合インデックスを使う
単一クエリへの統合が将来の最適化候補として残る)。

## 3. 削除候補洗い出し関数

新規モジュール`prototype/member_user_profile_deletion_candidate.py`に
`list_member_deletion_candidates(user_profile_store, now) -> list[str]`を追加した。
`all_unlinked_user_ids()`を走査し、`get_unlinked_at(user_id) + RETENTION_DAYS <= now`の
user_idを返す(`deletion_candidate.list_deletion_candidates()`のuser_profile版)。
`RETENTION_DAYS`・内部の`_DELETION_CANDIDATE_DELAY`は`deletion_candidate.py`から
再importし、独自の定数は持たない(保存期間ポリシーの単一のソースを保つ)。

呼び出し元(`check_and_apply_pending_member_reduction`から`unlinked_at=now`を渡す配線)
は本フェーズで実装済み。`list_member_deletion_candidates()`自体を日次バッチ
(daily-scheduler-design.md)へ配線する作業は未着手(次回候補、下記参照)。

## 4. 本フェーズで対応した内容

- `UserProfileStoreProtocol.unlink`に`unlinked_at`引数を追加(`InMemoryUserProfileStore`・
  `FirestoreUserProfileProvider`両方)。
- `get_unlinked_at`・`all_unlinked_user_ids`を両実装に追加。
- `link()`実行時に`unlinked_at`をクリアする処理を両実装に追加。
- `check_and_apply_pending_member_reduction`の`unlink()`呼び出しに`unlinked_at=now`を
  渡すよう更新。
- 新規モジュール`member_user_profile_deletion_candidate.py`
  (`list_member_deletion_candidates`)を追加。
- 新規テスト: `test_usage_counter_workshop.py`2件(unlinked_at記録・再リンククリア)、
  `test_firestore_user_profile_adapter.py`4件、
  `test_member_user_profile_deletion_candidate.py`6件(新規ファイル)。
  既存テスト(unittest discover 337件→347件、run_all_tests.py 26→27ファイル、
  schema検証32件)とあわせて全件パス確認済み。

## 5. 未着手・次回候補

- `list_member_deletion_candidates()`を日次バッチ(daily-scheduler-design.md)へ
  配線し、`deletion_candidate_final_confirmation.py`相当の最終確認通知(LINE push、
  不達時はメール代替)へつなげる処理。data-retention-policy.md「削除候補化後の
  最終確認」節の仕組みを流用する想定(workshop版のdeletion_candidate_final_
  confirmation.pyをuser_profile向けに翻案するか、共通化できるかの検討を含む)。
- 実Firestore接続・実データでの`all_unlinked_user_ids`の挙動確認はオーナー承認待ちの
  範囲(pending-approval.md参照)で未実施。
- 2026-11-08 08:00 UTC記載の運営方針確認が引き続き未回答のまま7venture共通の最大の
  ボトルネックとして残っている(pending-approval.md参照)。

最終更新: 2026-11-28 15:00 UTC(フェーズ続き341: 新規作成。除外メンバーuser_profileの
削除候補化〈unlinked_at記録・洗い出しロジック〉を実コード化)
