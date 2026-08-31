# 「ブロック中かつ契約継続中」業者の能動検知設計(フェーズ167)

## 背景

unfollow-billing-faq.md「今後の課題」に、次の未着手事項が残っていた。

> 本サービス側から能動的に「ブロック中かつ契約継続中」の業者を検知し、メール等の代替経路で
> 解約案内を送るプロアクティブな通知バッチの要否・設計は未着手。実LINE・実Stripe接続後に
> unfollow発生率・実際の問い合わせ件数が実測できた段階で優先度を判断する。

follow-unfollow-event-handling-design.md 2節の決定通り、本ventureはunfollow時に契約情報
(`current_plan_id`・`stripe_customer_id`等)を一切変更しない(再フォロー時の手間を省くため)。
その結果、「LINEをブロックしているのに課金だけ続く」状態が業者側から見えないまま放置されうる
という課題は変わらず残る一方、そもそも**本サービス側にも「誰がブロック中か」を追跡する手段が
無かった**(`process_unfollow_event()`は「何もしない」実装だったため、design 2節「決定の
まとめ」表の通り、unfollowイベント自体が記録されない)。プロアクティブな検知バッチを設計する
以前に、この検知手段の欠如がより根本的なギャップだった。

## 1. 決定: `is_following`フィールドの追加

`UserProfile`(user_id_linking.py)に`is_following: bool = True`を追加する。

- 既定値`True`: `UserProfile`は連携時(=フォロー中でなければ連携コードをLINEトークに送信
  できない)に生成されるため、生成時点では常にフォロー中。
- `process_follow_event()`: `profile_store`が渡され、対応するprofileが既に存在する場合
  (再フォロー)のみ`True`に戻す。未連携user_id(初回follow)はそもそもprofileが存在しない
  ため対象外。
- `process_unfollow_event()`: `profile_store`が渡され、対応するprofileが存在する場合のみ
  `False`に設定する。

この更新は「契約情報」ではなく「実際にメッセージが届くかどうか」を追跡する別軸のフラグであり、
follow-unfollow-event-handling-design.md 2節の決定(`current_plan_id`等の契約情報は不変)とは
矛盾しない。`pending_links`・`usage_counter`も従来通り一切変更しない。

## 2. 検知条件

`is_following == False` かつ `current_plan_id is not None`(未契約でも解約済みでもない=
何らかのプラン契約中、トライアル中を含む)を満たすuser_idを「ブロック中かつ契約継続中」候補
とする。

`current_plan_id`を判定根拠に使うのは、フェーズ161で確立済みの配線
(`subscription_plan_sync.clear_current_plan_on_subscription_deleted()`が
`customer.subscription.deleted`受信時に`current_plan_id`をNoneへ戻す)をそのまま再利用でき、
解約済み(=もう課金されていない)業者を誤って候補に含めない安全側の判定にもなるため。

トライアル中(有料転換前)にブロックした業者も候補に含める。まだ無料期間内でも、放置すれば
トライアル終了通知(trial-end-notification-design.md)がLINE経由で届かないまま自動的に
有料転換し、業者が気づかないうちに初回課金が発生しうるためで、早期検知の価値がある。

通知対象は**業者本人ではなくオーナー自身**とする。LINEをブロックした業者にLINE経由で
再度連絡することはできない(送達不可、design 2節)ため、「オーナーが候補一覧を見て、必要で
あればメール等の別チャネルで個別対応する」運用を想定する(unfollow-billing-faq.mdの
問い合わせ対応テンプレートは業者からの問い合わせへの事後対応、本設計はオーナー側からの
事前検知という位置づけで補完関係にある)。

## 3. 実装方針・実装状況

`prototype/blocked_but_billing_candidates.py`に`list_blocked_but_billing_candidates(store)`を
実装した(deletion_candidate.pyの`list_deletion_candidates()`と同じ、読み出し専用の候補
リスト関数)。`BlockedButBillingCandidateStoreProtocol`(`get_is_following`・
`get_current_plan_id`・`all_user_ids`の3メソッドのみを要求する薄いProtocol)を
`InMemoryUserProfileStore`が構造的に満たす形とした。

MVPでは`InMemoryUserProfileStore.all_user_ids()`による線形走査で代替する(将来Firestoreの
複合クエリ〈`is_following == False AND current_plan_id != null`〉にそのまま対応させられる形を
想定)。テスト6件(候補該当・フォロー中除外・解約済み除外・トライアル中候補への算入・複数候補の
user_id昇順ソート・profile未存在の無視)を追加、venture全体370件全件パス・schema検証9件パスを
確認した。

`process_follow_event()`/`process_unfollow_event()`への`is_following`更新配線、および
`dispatch_webhook_events()`からの`profile_store`結線もあわせて実装済み(テスト計6件追加、
上記370件に含む)。

## 4. 未着手のまま残る課題

- **候補一覧をオーナーへ実際に届ける手段は未設計・未接続**。本フェーズで実装したのは
  「候補を洗い出す純粋関数」までであり、(a) 誰が/どの頻度でこの関数を呼ぶか(日次バッチ、
  Cloud Scheduler等)、(b) 洗い出した結果をオーナーにどう届けるか(メール・Slack通知等)は
  未設計のまま残る。これらは実LINE・実Stripe接続(いずれもオーナー承認待ち、
  pending-approval.md記載済み)後、実際にunfollowイベントが発生し始めてから設計する方が
  精度が高いと判断し、あえて先送りする。
- Cloud Schedulerの新規作成・メール送信の実行はいずれも外部サービス側の設定・送信操作に
  該当し、オーナーの許可が必要なアクションであるため、実際の接続作業自体は着手しない
  (course-set-pasha・line-reservation-aiの同種案件と同じ整理)。
- line-reservation-aiにも同種の未着手課題(unfollow時のuser_profile扱い)が残っているため、
  次回以降の展開候補とする(本venture固有の`is_following`設計をそのまま持ち込めるかは
  line-reservation-ai側のuser_profileスキーマ次第で要確認)。
