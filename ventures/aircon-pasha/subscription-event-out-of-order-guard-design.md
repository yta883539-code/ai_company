# Stripe Webhook配信順序入れ替わりガード(subscription-event-out-of-order-guard-design.md)

## 1. 発見の経緯

course-set-pashaフェーズ261・262は、`customer.subscription.deleted`/`customer.subscription.
created`のいずれかがWebhookの配信順序保証の欠如(Stripe公式ドキュメントが明記する「イベントは
発生順に届くとは限らず、再送により大幅に遅延することもある」)により入れ替わって届いた場合、
`subscription_canceled_at`(フェーズ258)・`deletion_candidate_at`(deletion_candidate.py)の
いずれも、届いた時点のイベントを無条件に「最新の真実」として適用していたため、次の両方向の
バグが理論上存在することを発見・修正した。

- ケースA: 解約直後に別プランで即再契約した際、配信順序が入れ替わりdeletedがcreatedより後に
  届くと、既に新契約で有効なユーザーを誤ってブロックしてしまう。
- ケースB: 初回契約イベント(created)の配信がリトライで大幅に遅延し、その間に本当に解約
  (deleted)された場合、遅れて届いたcreatedが解約確定フラグを誤って消去し、`subscription_
  canceled_at`導入自身が防ごうとした「解約後も生成を無期限に使い続けられる」欠落が別経路で
  再発する。

course-set-pashaフェーズ262は「同種ガードがaircon-pasha・kura-pasha・line-reservation-aiにも
必要なパターンが存在するかの横断確認」を次回候補として残していた。本フェーズはaircon-pasha側を
確認した。

## 2. 確認結果: aircon-pashaにも同型の欠落が2箇所あった

aircon-pashaは`subscription-canceled-immediate-block-design.md`(フェーズ275、course-set-pasha
フェーズ258の横展開)で`subscription_canceled_at`を、`stripe-cancellation-deletion-candidate-
trigger-design.md`(フェーズ123)で`deletion_candidate_at`をそれぞれ持つが、いずれも
`stripe_dispatch.py`/`deletion_candidate.py`のコード上、course-set-pashaが修正前に持っていたのと
全く同じ「イベントの到着順を無条件に真実とする」実装のままだった(`mark_deletion_candidate_
on_subscription_deleted()`のdocstringが「既に設定済みの場合も最新の解約日を基準に上書きする、
design記載の『安全側』判断」と明記していた点も含め、修正前のcourse-set-pashaと同一)。

## 3. 修正内容

course-set-pashaフェーズ261・262と同じ考え方を、aircon-pashaの既存の型(`store`=
`ProfileDeletionCandidateStoreProtocol`、`payment_store`=`UserProfileStoreProtocol`/
`InMemoryUserProfileStore`)に合わせてそれぞれ独立に実装した。

### 3.1 `deletion_candidate.py`(`deletion_candidate_at`)

- `ProfileDeletionCandidateStoreProtocol`に`get_deletion_candidate_state_event_time()`/
  `set_deletion_candidate_state_event_time()`を追加し、`InMemoryProfileDeletionCandidateStore`
  にも実装した(`deletion_candidate_at`を最後に実際に反映した〈mark/clearを問わない〉イベントの
  `event.created`を別辞書で保持する)。
- `_is_stale_deletion_candidate_event()`/`_record_deletion_candidate_state_event_time()`を新設
  し、`mark_deletion_candidate_on_subscription_deleted()`/`clear_deletion_candidate_on_
  subscription_reactivated()`の冒頭でstale判定を行う。`clear_...()`は`event_time`を新規の
  オプション引数(既定`None`)として追加し、省略時は従来通り無条件クリアの後方互換を維持する。
  `store`が新メソッドに未対応(将来的な専用スタブ等)の場合は判定不能として常に適用する
  (hasattr方針、course-set-pashaと同じ)。

### 3.2 `stripe_dispatch.py`/`user_id_linking.py`(`subscription_canceled_at`)

- `UserProfile`に`subscription_state_event_time: Optional[datetime] = None`を追加。
  `UserProfileStoreProtocol`に`get_subscription_state_event_time()`/`set_subscription_state_
  event_time()`を追加し、`InMemoryUserProfileStore`にも実装した。`resolve_linking_code()`
  (再連携時のフィールド引き継ぎ)にも本フィールドを追加した(`subscription_canceled_at`と
  対になるフィールドのため、引き継ぎ漏れがあると再連携のたびに順序ガードの記録が失われる)。
- `stripe_dispatch.py`に`_is_stale_subscription_state_event()`/`_record_subscription_state_
  event_time()`を新設し、`customer.subscription.deleted`分岐の`set_subscription_canceled_at()`
  呼び出し・`customer.subscription.created`分岐の`set_subscription_canceled_at(user_id, None)`
  呼び出しのそれぞれをstale判定でガードした。`_SUBSCRIPTION_CREATED`分岐はこれまで`event.
  created`を一切読んでいなかったため、本フェーズで読み取りを追加した(数値でない/存在しない
  場合は判定不能として従来通り適用、既存呼び出し経路への後方互換)。
- `StripeDispatchResult`に`stale_subscription_deleted_user_ids`/`stale_subscription_created_
  user_ids`を追加し、スキップが発生したuser_idを記録できるようにした。

`deletion_candidate_at`用と`subscription_canceled_at`用の順序判定は、それぞれ`store`/
`payment_store`という別インスタンスの状態としてお互い独立に保持・判定する(course-set-pasha
フェーズ262が「各venture独立のコピーであり共有モジュールではない」として先送りにした横断確認の
中で、同一venture内でも`deletion_candidate_at`と`subscription_canceled_at`はそもそも別ストアで
あるため、両者間で状態を共有する設計にはしていない、course-set-pashaと同じ構成)。

## 4. テスト

- `test_deletion_candidate.py`に`StaleEventGuardTest`(ケースA・ケースB・正常順序の回帰確認・
  `event_time`省略時の後方互換確認、4件)を追加。
- `test_stripe_dispatch.py`に`test_stale_deleted_event_skipped_when_older_than_already_applied_
  created`・`test_stale_created_event_skipped_when_older_than_already_applied_deleted`・
  `test_created_without_created_field_still_applies_for_backward_compatibility`(3件)を追加。
- 既存テスト(フェーズ275時点の`subscription_canceled_at`関連テストを含む)はいずれも変更なしで
  パスすることを確認した(後方互換が保たれている)。
- venture全体638件(`python3 -m unittest discover -s prototype -p "test_*.py"`、変更前631件+
  新規7件)・schema検証25件(`python3 schema/validate_test_cases.py`)いずれもパス。

## 5. 残課題

- `customer.subscription.updated`受信時の`clear_deletion_candidate_on_subscription_
  reactivated()`呼び出し(`_REACTIVATED_STATUSES`分岐)には`event_time`を渡していない
  (course-set-pashaフェーズ261・262と同じスコープ。`updated`イベントはstatus遷移の検出が
  主目的で、`deleted`/`created`ほど配信順序入れ替わりの実害〈永続的な誤ブロック・誤解除〉が
  大きくないと判断されたため、本フェーズもcourse-set-pashaの既存スコープを踏襲した)。
- kura-pasha・line-reservation-aiへの同種ガードの要否確認はcourse-set-pashaフェーズ262から
  引き続き未着手(line-reservation-aiは`subscription_status`列挙型の単一フィールド方式〈フェーズ
  続き278確認済み〉、kura-pashaも`subscription_status`列挙型方式〈フェーズ190確認〉のため、
  タイムスタンプ比較という同一の実装パターンはそのまま適用できず、列挙型方式における配信順序
  入れ替わりの影響〈更新順序が入れ替わった場合に最終的な列挙値が誤る可能性〉を別途検討する
  必要がある。次回候補とする)。

## 6. フェーズ283: `plan_store`/`blocked_but_billing_store`側の非対称是正

フェーズ282は`customer.subscription.deleted`分岐の決済失敗フィールドクリア・解約確定案内通知を
`is_stale_deleted_event`でガードしたが、同じ分岐内の`plan_store.clear_current_plan_on_
subscription_deleted()`(current_plan_idをNoneへ戻す)・`blocked_but_billing_store.clear_
blocked_but_billing_owner_notified_at()`は、`is_stale_deleted_event`算出より前に無条件で
実行されたまま残っていた。stale(=既により新しいcustomer.subscription.createdで有効化済み)な
deletedイベントが遅延到着した場合、この2箇所は次のような実害を持つ非対称だった。

- `current_plan_id`クリア: 有効な契約者のプランIDを誤ってNone(未契約)へ戻してしまう。
  `current_plan_id`を参照する他の機能(プラン別の生成回数上限判定など)が、実際には有効な
  契約者を未契約として扱ってしまうおそれがある。
- `blocked_but_billing_owner_notified_at`クリア: 「ブロック中かつ契約継続中」候補として
  一度オーナーへ通知済みのフラグを、契約が実際には継続しているにもかかわらず解約が確定した
  かのように誤って早期クリアしてしまう。

`stripe_dispatch.py`の`customer.subscription.deleted`分岐で、`is_stale_deleted_event`の算出を
`mark_deletion_candidate_on_subscription_deleted()`呼び出し直後(決済失敗フィールドクリア・
`subscription_canceled_at`設定・解約確定案内通知の3箇所と共通化する位置)まで前倒しし、
`plan_store`呼び出し・`blocked_but_billing_store`呼び出しの両方をこの判定でガードするよう
変更した(course-set-pasha/kura-pasha/line-reservation-aiと同じ「stale全体スキップ」方針への
統一を、本venture内の`customer.subscription.deleted`分岐が持つ副作用5箇所〈deletion_
candidate・plan・blocked_but_billing・payment_failure・cancellation通知〉すべてに拡張)。
`payment_store`未指定時は`_is_stale_subscription_state_event()`が判定不能として常に`False`
(非stale)を返すため、`plan_store`/`blocked_but_billing_store`のみを指定し`payment_store`を
指定しない既存呼び出し経路では従来通り無条件適用のままとなる(後方互換)。

テスト2件追加(`test_stale_deleted_event_does_not_clear_current_plan_id`・
`test_stale_deleted_event_does_not_clear_blocked_but_billing_owner_notified_at`)、
venture全体646件(644→646)・schema検証25件いずれもパス。
