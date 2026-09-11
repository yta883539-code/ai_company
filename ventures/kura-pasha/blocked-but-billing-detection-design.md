# 「ブロック中かつ契約継続中」契約者の能動検知設計(フェーズ80)

## 背景

unfollow-billing-faq.md「今後の課題」に、次の未着手事項が残っていた。

> 「ブロック中かつ契約継続中」契約者の検知手段(他venture3件のblocked-but-billing-
> detection-design.md相当)の設計・実装は、その前提となるStripe Webhook受信・
> `user_profile`の`is_following`相当フィールドの追加自体が本venture未着手のため、
> それらの実装後の課題として残る。

前提だった「Stripe Webhook受信」は既にstripe_webhook.py(フェーズ50・51等)として実装済み
であり、残る前提は「`user_profile`への`is_following`相当フィールドの追加」のみだった。
本フェーズはこの前提を解消したうえで、aircon-pasha/blocked-but-billing-detection-design.md
(フェーズ167)を本venture固有のworkshop(工房)構造へ翻案する形で検知ロジックを設計・
実装する。

## 1. 他venture3件との構造的な違い

aircon-pasha・course-set-pasha・line-reservation-aiはいずれも1事業者=1契約(1つのLINE
user_id=1つの契約)が前提のため、「ブロック中」と「契約継続中」はどちらも同一user_idの
属性として素直に判定できる。

本ventureはcraftsman-account-linking-design.md(フェーズ25)で確立した通り、契約単位は
`craftsman_workshop/{workshop_id}`であり、1つのworkshopに複数のuser_id(契約者
`contractor_user_id`+その他メンバー`member_user_ids`)が所属しうる。一方、「フォロー
中かどうか」はLINEアカウント(user_id)ごとの属性であり、workshop全体の属性ではない。
このため、本venture固有の設計課題は「workshopに複数いるメンバーのうち、誰の
`is_following`を検知条件に使うか」という点になる。

答えは明快で、trial-end-notification-design.md・payment-failure-dunning-design.md・
subscription-cancellation-notification-design.md等、本venture既存の全ての課金関連通知が
一貫して**契約者(`contractor_user_id`)のみ**を宛先としている(共同利用者には送らない
方針、subscription-cancellation-flow-design.md「複数職人プラン固有の論点」以来)。
したがって、「ブロックにより課金関連通知が届かなくなる」というリスクも契約者の
`is_following`のみに依存する。契約者以外のメンバーがブロックしても、そのメンバー宛の
課金通知はそもそも存在しないため本検知の対象外とする(2節参照)。

## 2. 決定: `user_profile.is_following`フィールドの追加

`UserProfileStoreProtocol`(usage_counter_workshop.py)に`get_is_following`/
`set_is_following`を追加し、`InMemoryUserProfileStore`は`dict`ベースで実装した
(既定値`True`。プロフィールは連携時=workshop作成時にしか生成されないため、生成時点では
常にフォロー中)。

- `process_follow_event()`: `profile_store`が渡され、かつ対象user_idが既にworkshopへ
  連携済み(`get_workshop_id(user_id)`が非None、既存の「連携済みかどうか」の判定を
  そのまま流用しaircon-pashaの`exists()`相当の別メソッドは追加しない)の場合のみ
  `True`に戻す(再フォロー)。未連携user_id(初回follow、まだprofile自体が存在しない)は
  対象外。
- `process_unfollow_event()`: 同様に連携済みの場合のみ`False`に設定する。

aircon-pasha同様、これは「契約情報」ではなく「実際にメッセージが届くかどうか」を追跡する
別軸のフラグであり、follow-unfollow時にplan_id・subscription_status等の契約情報を一切
変更しないという既存の設計判断(unfollow-billing-faq.md「前提の整理」節)とは矛盾しない。

## 3. 検知条件

`craftsman_workshop`を`all_workshop_ids()`で走査し、次の両方を満たすworkshop_idを
「ブロック中かつ契約継続中」候補とする。

1. `get_subscription_status(workshop_id) != "canceled"`(trialing/active/past_due
   いずれか。まだ何らかの形で課金対象または課金候補である)
2. `is_following(get_contractor_user_id(workshop_id)) == False`(契約者本人がLINEを
   ブロック中)

判定根拠に`subscription_status`を使い、`plan_id`を使わないのが本venture固有の差分
(aircon-pasha等は`current_plan_id`が解約時に`None`へ戻る設計のためそれを使う)。
本ventureの`plan_id`は`checkout.session.completed`受信時の上書き専用フィールド
(craftsman-account-linking-design.md フェーズ66追記7節)であり、解約後もクリアされず
workshop作成時の値が残り続けるため契約有無の判定には使えない。一方
`subscription_status`は`customer.subscription.deleted`受信時に
`handle_customer_subscription_deleted()`(stripe_webhook.py)が確実に`"canceled"`へ
更新するため、こちらを解約済み判定に使うのが本venture向けの正しい翻案となる。

トライアル中(`"trialing"`)の契約者がブロックした場合も候補に含める(aircon-pashaと
同じ理由: 放置すればトライアル終了通知〈trial-end-notification-design.md〉が届かない
まま自動的に有料転換し、契約者が気づかないうちに初回課金が発生しうるため)。

通知対象は契約者本人ではなく**オーナー自身**とする(aircon-pasha 2節と同じ理由:
LINEをブロックした契約者にLINE経由で再度連絡することはできないため、「オーナーが候補
一覧を見て、必要であればメール等の別チャネルで個別対応する」運用を想定する)。

## 4. 実装状況

`prototype/blocked_but_billing_candidates.py`に`list_blocked_but_billing_candidates
(workshop_store, profile_store)`を実装した。`BlockedButBillingCandidateWorkshopStoreProtocol`
(`get_contractor_user_id`・`get_subscription_status`・`all_workshop_ids`の3メソッドのみを
要求する薄いProtocol)・`BlockedButBillingCandidateProfileStoreProtocol`
(`get_is_following`のみ)の2つに分け、`WorkshopStoreProtocol`/`UserProfileStoreProtocol`
(ひいては`InMemoryWorkshopStore`/`InMemoryUserProfileStore`)が構造的にこれらを満たす形と
した(aircon-pasha版は1つのProtocolで足りたが、本ventureはworkshop/profileの2つのストアに
分かれているため2つのProtocolに分割した点が差分)。

MVPでは`all_workshop_ids()`による線形走査で代替する(将来Firestoreの複合クエリに
対応させられる形を想定)。テスト7件(契約者ブロック時の候補該当・フォロー中除外・解約済み
除外・トライアル中候補への算入・非契約者メンバーのブロックは対象外・複数候補の
workshop_id昇順ソート・候補0件時の空リスト)を追加、venture全体596件全件
(`python3 test_*.py`を各ファイルで直接実行)・schema検証27件いずれもパスを確認した。

`process_follow_event()`/`process_unfollow_event()`への`is_following`更新配線、および
`dispatch_webhook_events()`からの`user_profile_store`結線もあわせて実装済み(テスト8件
追加、上記に含む)。

## 5. 未着手のまま残る課題

- ~~候補一覧を実際にオーナーへ届ける手段(aircon-pasha/blocked-but-billing-owner-
  notification-design.md相当のFlex Message通知・日次Cloud Schedulerでの実行)は本フェーズの
  対象外とし、次回以降の課題として残す。~~ → フェーズ81・
  blocked-but-billing-owner-notification-design.mdで解消済み(本venture一貫の
  プレーンテキスト形式へ翻案、送信ロジック・冪等性フィールド・クリア配線を実装済み)。
- Cloud Schedulerの新規作成・メール送信の実行はいずれも外部サービス側の設定・送信操作に
  該当し、オーナーの許可が必要なアクションであるため、実際の接続作業自体は着手しない
  (他venture3件と同じ整理)。
- 契約者以外のメンバーがブロックしたケース(2節で対象外とした)について、生成リクエストへの
  応答自体は届かなくなるが契約情報には影響しないため、本設計とは別に「メンバー宛の応答
  未達」自体を検知・通知する必要があるかどうかは次の課題とする(本フェーズのスコープは
  あくまで課金関連通知の宛先である契約者に限定した)。

最終更新: 2026-09-11 05:00 UTC
