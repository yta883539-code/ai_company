# 「ブロック中かつ契約継続中」候補検知の設計(フェーズ142)

作成日: 2026-09-02(フェーズ142)

## 背景

unfollow-billing-faq.md「今後の課題」に、フェーズ141時点でも次の記載が未着手のまま
残っていた。

> 本サービス側から能動的に「ブロック中かつ契約継続中」のユーザーを検知し、メール等の
> 代替経路で解約案内を送るプロアクティブな通知バッチの要否・設計は未着手。

これはaircon-pashaがフェーズ167で対応した課題(blocked-but-billing-detection-design.md)と
同種の課題である。着手前に確認したところ、aircon-pashaは`UserProfile`に
`is_following: bool`と`current_plan_id: Optional[str]`の両方を保持しており、この2つの
組み合わせで判定していた。一方、本venture(course-set-pasha)は、

- `unfollow`イベント受信時に「フォロー状態」自体を記録する手段がそもそも無かった
  (`process_unfollow_event()`は`pending_links`の削除のみを行い、`is_following`相当の
  フィールドは未実装だった。aircon-pashaがフェーズ167で発見したのと同じ種類の記載漏れ)。
- `current_plan_id`のような「現在のプラン」を表す専用フィールドも持たない。代わりに
  stripe-cancellation-deletion-candidate-trigger-design.md(フェーズ91)の
  `deletion_candidate_at`(`customer.subscription.deleted`受信時に設定、`created`/
  `updated`(active/trialingへの復帰)受信時にクリア)を「解約検知済みかどうか」の
  代理指標として既に運用している。

したがって本venture向けにaircon-pashaと全く同じ`current_plan_id`を新設するのではなく、
既存の`deletion_candidate_at`を再利用する設計とする(重複するフィールドを増やさない)。

## 1. `is_following`フラグの新設

`application_form_submission_flow.UserProfileStoreProtocol`に`set_is_following`/
`get_is_following`/`all_user_ids`を追加した。`InMemoryUserProfileStore`が実装を持つ。

- 未記録のuser_id(followイベントを一度も受けていない場合を含む)は`get_is_following()`が
  `True`を返す(aircon-pashaの`is_following: bool = True`デフォルトと同じ安全側の初期値)。
- `cloud_function_webhook.process_follow_event()`/`process_unfollow_event()`に
  `profile_store`引数(未指定時は`None`、既存呼び出し経路への後方互換)を追加し、
  follow受信時は`True`、unfollow受信時は`False`へ更新するよう配線した
  (`dispatch_webhook_events()`からの結線含む)。
- unfollow-event-handling-design.md論点3(`user_profile`は一切削除・変更しない)は
  `gym_area_pairs`・`email`等の「ユーザー設定・利用実績データ」を対象にした結論であり、
  `is_following`は「ブロック中かつ契約継続中」の検知専用に新設した別種のフラグのため、
  同結論とは矛盾しない(同ファイルに注記追加)。

## 2. 判定条件

`is_following == False` かつ `get_stripe_customer_id(user_id) is not None`
(=一度でもStripe Checkoutを完了しStripe顧客が作成されている) かつ
`deletion_candidate_at is None`(=`customer.subscription.deleted`をまだ受信していない、
すなわち解約が確認されていない)を満たす`user_id`を候補とする。

- `stripe_customer_id`の有無だけでは「現在も課金が継続しているか」までは分からない
  (Checkoutを1度行ったが後に解約したユーザーも`stripe_customer_id`は保持したまま)。
  `deletion_candidate_at is None`を組み合わせることで「解約Webhookをまだ受けていない」
  ユーザーに絞り込み、aircon-pashaの`current_plan_id is not None`に近い精度に寄せる。
- ただし本条件は「トライアル中で一度もCheckoutを完了していない」ユーザーは
  `stripe_customer_id`が無いため対象外になる(aircon-pashaの`current_plan_id`は
  トライアル中も設定される想定だった点との差異)。トライアル中ユーザーの`stripe_customer_id`
  発行有無は checkout-initiation-flow-design.md の設計に依存するため、本フェーズでは
  深追いせず、実Stripe接続後の実測で必要なら見直す前提を残す(下記「残る限界」参照)。

## 3. プロトタイプ実装方針

`prototype/blocked_but_billing_candidates.py`を新設する。aircon-pasha版と異なり、
判定に必要な2つの状態(`is_following`・`stripe_customer_id`は`UserProfileStoreProtocol`、
`deletion_candidate_at`は`ProfileDeletionCandidateStoreProtocol`)が別々のストアに
分かれているため、`list_blocked_but_billing_candidates()`は2つのストアを引数に取る形にする
(単一Protocolでのduck typingにはしない。実Firestoreでは両方とも同一の`user_profile`
ドキュメントのフィールドになる想定のため、接続後に1つのFirestoreクライアントを2回
渡すだけで済む)。

- `list_blocked_but_billing_candidates(profile_store, deletion_store) -> list[str]`
  読み出し専用。`profile_store.all_user_ids()`を走査し、上記2節の3条件を満たす
  user_idをuser_id昇順で返す(`deletion_candidate.list_deletion_candidates()`と
  同じ「MVPでは線形走査、将来Firestoreの複合クエリに置き換え可能」という位置づけ)。
- 洗い出した候補への実際の通知(オーナーへのメール送信等)は行わない
  (aircon-pasha版と同じ、design 2節「通知対象」相当の議論はunfollow-billing-faq.md
  「今後の課題」に既にある内容を踏襲し本フェーズでは再検討しない)。

## 残る限界・今後の課題

- トライアル中(Checkout未完了)でブロックしたユーザーは本ロジックでは検知できない
  (2節参照)。トライアル中ユーザーに対する`stripe_customer_id`発行タイミングは
  実Stripe接続後に確定する見込みのため、それまでは「Checkout完了後の有料ユーザーのみ」を
  対象にした保守的な検知として位置づける。
- 候補一覧をオーナーへ実際に届ける手段(バッチ実行主体・通知チャネル)は、aircon-pashaと
  同様に未設計のまま残す。実LINE・実Stripe接続後にunfollow発生率が実測できてから設計する
  方が精度が高いという、aircon-pashaフェーズ167の判断をそのまま踏襲する。
