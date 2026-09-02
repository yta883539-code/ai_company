# オーナーが「ブロック中かつ契約継続中」の能動検知設計(フェーズ続き176)

## 背景

follow-unfollow-event-handling-design.md「残課題」に、aircon-pashaフェーズ167の
blocked-but-billing-detection-design.md相当(能動検知バッチ)の要否検討が未着手のまま
残っていた。aircon-pasha・course-set-pashaは既に同種の検知の仕組みを持つ(aircon-pasha
フェーズ167・course-set-pashaフェーズ142)一方、本ventureだけが手つかずだった。

## 本venture固有の前提: 「誰の」ブロックが問題なのか

follow-unfollow-event-handling-design.md「前提の整理」の通り、本ventureのLINE公式
アカウントは店舗ごとに1つ発行され、**一般顧客とオーナー自身の両方が同じアカウントを
フォローする**。Stripeの課金対象は店舗(オーナー)であり一般顧客ではないため、
aircon-pasha/course-set-pashaがuser_id単位で追跡する`is_following`をそのまま
持ち込むのは適切ではない。本venture固有の課題は「多数いる顧客のうち誰がブロックしたか」
ではなく、**「store_id(=公式アカウント)ごとに、オーナー自身がブロックしているか」**
の1ビットだけであり、これは`store_profile_store.py`が既に保持する
`owner_user_id`(store-id-resolution-and-owner-identity-design.md)と同じ粒度
(店舗単位)で管理するのが自然である。

## 1. 決定: `owner_is_following`フィールドの追加(店舗単位)

firestore-data-model.md`stores/{storeId}`ドキュメントに`ownerIsFollowing: bool`
(既定値`true`)を追加する。`prototype/store_profile_store.py`の
`StoreProfileStoreProtocol`/`InMemoryStoreProfileStore`に対応する
`get_owner_is_following(store_id) -> bool`(既定`True`)・
`set_owner_is_following(store_id, value: bool) -> None`を追加する。

- 既定値`True`: 店舗レコードは`owner_user_id`確定(オンボーディングのテストメッセージ
  受信時、owner-notification-channel-design.md)より前から存在しうるため、値が
  未設定の間は「フォロー中」として安全側に倒す(course-set-pasha/aircon-pashaの
  `is_following`既定値と同じ考え方)。
- `process_follow_event()`: `event["source"]["userId"] == self._owner_user_id`
  (かつ`owner_user_id`が確定済み)の場合のみ`True`に戻す(再フォロー)。
  一般顧客のfollowイベントでは何も書き込まない。
- `process_unfollow_event()`: 同様に`event["source"]["userId"] ==
  self._owner_user_id`の場合のみ`False`に設定する。一般顧客のunfollowでは
  何も書き込まない(follow-unfollow-event-handling-design.md 3節の「会話状態・
  予約データは何もしない」という既存方針は変更しない。今回追加するのは
  オーナー本人のunfollow検知の1点のみ)。
- `owner_user_id`が未確定(オンボーディング未完了)の間にオーナーがブロックしても
  判別できない(aircon-pashaの連携コード未確定時と同種の限界)。この場合は
  検知漏れとなるが、オンボーディング未完了の店舗はそもそも稼働開始前でありStripe
  課金も発生していないため実害は小さいと判断する。

## 2. 検知条件

`owner_is_following == False` かつ `suspension_reason not in ("cancelled",
"trial_unselected")` を満たすstore_idを「ブロック中かつ契約継続中」候補とする。

`suspension_reason`(payment-failure-dunning-design.md・dormant-mode-renotification-
design.md準拠)の4値のうち、除外する2つの理由:

- `"cancelled"`: 契約自体が終了済み(aircon-pashaの`current_plan_id is None`と同じ
  「もう課金されていない」除外条件)。
- `"trial_unselected"`: トライアル終了時に有料プランを選択しないまま休止モードへ
  移行した状態。dormant-mode-renotification-design.mdが定める通り、この状態では
  **Stripeへの課金自体が発生していない**(有料転換前に休止したケース)ため、
  aircon-pasha設計の「トライアル中(有料転換前)も候補に含める」とは事情が異なる
  (aircon-pashaのトライアル中は「トライアル終了後に自動的に有料転換する」設計だが、
  本venture休止モードは逆に「有料転換しなかったから休止した」状態であり、放置しても
  無断課金は発生しない)。休止モードからの再通知は既にdormant-mode-renotification-
  design.mdが別途カバーしており、本設計の対象外とする。

残る2値(`None`=通常課金中、`"payment_failed"`=決済失敗による猶予期間中)はいずれも
Stripe側で何らかの課金関係が継続中(または継続しようとしている)ため候補に含める。
`"payment_suspended"`(猶予期間経過後の制限モード、owner-settings-wireframe.md
フェーズ続き108参照)も、契約自体はまだ`cancelled`になっていない(オーナーが挽回
できる余地が残る)ため候補に含める。

通知対象はaircon-pasha/course-set-pashaと同じく**オーナー自身**とする。ただし本venture
はオーナー自身がブロックした対象そのものであるため、通知はLINE経由では送達不可
(follow-unfollow-event-handling-design.md 3節)。したがって通知チャネルはメール等の
代替経路に限定される。本フェーズでは検知ロジック(候補一覧の抽出)までを設計・実装
対象とし、代替チャネルでの実際の送信配線はaircon-pasha同様に次回以降の課題として残す
(メール送信の実行自体もオーナー承認が必要なアクションのため、いずれにせよ着手できない)。

## 3. 実装方針・実装状況

`prototype/blocked_but_billing_candidates.py`に
`list_blocked_but_billing_candidates(store) -> list[str]`を実装した。
`BlockedButBillingCandidateStoreProtocol`(`get_owner_is_following`・
`get_suspension_reason`・`all_store_ids`の3メソッドのみを要求する薄いProtocol、
aircon-pasha版と同じ設計)を`InMemoryStoreProfileStore`が構造的に満たす形とした
(`get_suspension_reason`/`set_suspension_reason`・`all_store_ids`を
`store_profile_store.py`に新規追加)。`suspension_reason`は本来
`cloud_function_subscription_*_webhook.py`側の`StoreSubscriptionState`が
関数呼び出しごとに受け渡す値だが、firestore-data-model.mdでは
`stores/{storeId}`の同一ドキュメント上のフィールドであるため、
`InMemoryStoreProfileStore`側にも同じ粒度で保持先を持たせることは
データモデルと矛盾しない(実運用では同一Firestoreドキュメントへの読み書きに収束する)。

`ConversationEventProcessor.__init__`に任意引数`store_profile:
Optional[OwnerFollowStatusStoreProtocol] = None`を追加し(`record_store`・
`confirmed_reply_recorder`と同じ「未指定時は何もしない」後方互換パターン)、
`process_follow_event()`/`process_unfollow_event()`から1節の条件で
`set_owner_is_following()`を呼ぶよう配線した。

MVPでは`InMemoryStoreProfileStore.all_store_ids()`による線形走査で代替する
(将来Firestoreの複合クエリ〈`ownerIsFollowing == false AND suspensionReason NOT
IN ("cancelled", "trial_unselected")`〉にそのまま対応させられる形を想定、
aircon-pasha版と同じ考え方)。

テスト計12件(`owner_is_following`のfollow/unfollow配線6件、
`list_blocked_but_billing_candidates()`の候補判定6件)を追加、venture全体
565件全件パス・schema検証25件パスを確認した。

## 4. 未着手のまま残る課題

- 候補一覧を実際にオーナーへ届ける手段(代替チャネル、メール等)の設計・実装。
  aircon-pashaフェーズ174はLINE Flex Messageでオーナー自身に通知できたが、本venture
  はオーナー自身がブロックした対象そのものであるためLINE経由の通知が原理的に使えない
  (course-set-pasha/aircon-pashaには無い制約)。メール送信の実行自体もアカウント作成・
  送信操作としてオーナー承認が必要なため、実装できても実行はできない。
- 誰が/どの頻度でこの関数を呼ぶか(日次Cloud Scheduler相当)自体の実際の作成・接続は
  オーナー承認待ちの範囲として残る(course-set-pasha・aircon-pashaの同種案件と同じ整理)。
- `owner_user_id`確定前(オンボーディング未完了)のオーナーunfollowは検知漏れとなる点は
  1節に記載した通り仕様上の割り切りとするが、実測データが取れた段階で頻度を確認する
  価値はある。
