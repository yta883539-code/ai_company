# Stripeカスタマーポータルリンク(`portal_url`)取得方式の設計

作成日: 2026-09-04(フェーズ続き192)

## 1. 発端

course-set-pashaフェーズ158で「本venture(line-reservation-ai)側にも
`cancellation_push_client`/`portal_link_provider`の配線漏れが残っていないか確認」が
次回候補として申し送られたため、本venture側の該当箇所を棚卸しした。

## 2. 調査結果: 配線漏れではなく、そもそも取得方式自体が未設計

aircon-pasha(`portal-session-provider-design.md`)・course-set-pasha
(`customer-portal-session-endpoint-design.md`)は、解約案内メッセージへ差し込む
Stripeカスタマーポータルへのリンクを、`PortalLinkProvider.get_portal_url(user_id) ->
Optional[str]`という**呼び出し時に都度URLを生成するコールバック**として設計しており、
`receive_stripe_webhook()`が`portal_link_provider`引数として受け取って
`dispatch_stripe_event()`に配線する構造になっている。

一方、本ventureの`cloud_function_subscription_activated_webhook.StoreSubscriptionState`・
`cloud_function_subscription_cancelled_webhook.StoreSubscriptionState`(解約用の別クラス、
`stripe_webhook_entry_point.py`では`StoreCancellationState`としてimport)は、いずれも
`portal_url: str`という**store状態に保存された固定フィールド**として扱っており、
`render_subscription_activated_message()`・`render_cancellation_scheduled_message()`は
`state.portal_url`をそのままメッセージ本文へ埋め込んでいる。

この`portal_url`フィールドが実際にいつ・どうやって値を持つのかを設計するドキュメント・
実装(`portal_session.py`相当)は、本ventureには一度も存在しなかった
(`ls ventures/line-reservation-ai/*portal*`で該当なし、`prototype/`内に
`portal_session.py`も無い)。したがって「配線漏れ」ではなく、**そもそもaircon-pasha・
course-set-pashaが採用した`PortalLinkProvider`パターン自体が導入されていない**という、
一段階手前の設計ギャップだった。

## 3. なぜ「stateに保存された固定URL」は問題か

Stripe Customer Portalのセッション(`stripe.billing_portal.Session.create()`)が返す
URLは、Stripe公式の想定として「作成直後にユーザーをリダイレクトさせる一時的なリンク」
であり、長期間保存して後から再利用する用途を想定したものではない(Checkout Session URLと
同様、作成から時間が経つほど有効性が保証されなくなる)。

本ventureの現状の設計は次の2箇所で`state.portal_url`を送信メッセージに埋め込んでいる。

- `handle_subscription_activated()`(決済完了直後の案内メッセージ)
- `handle_subscription_updated()`の`OUTCOME_CANCELLATION_SCHEDULED`分岐
  (解約予約受理案内メッセージ)

後者は特に問題が大きい。解約予約案内メッセージは店舗オーナーが受け取ってから実際に
リンクをクリックするまでの時間差が数日〜数週間(請求期間終了まで)空くこともあり得る
運用であり、「送信時点で有効だった固定URL」をLINEメッセージ本文に静的に埋め込む
現状の設計では、オーナーが後日メッセージを読み返してリンクを踏んだ時点で
リンクが無効化されている可能性が高い。aircon-pasha・course-set-pashaが
`PortalLinkProvider`を「stateに保存せず、必要になった瞬間に都度生成する」設計に
したのは、この失効問題を避けるためだったと考えられる(両venture側の設計docに
明記はないが、Stripeの一時リンクという性質上、同じ結論に至るのは自然)。

## 4. 対応方針

aircon-pasha・course-set-pashaと同じ`PortalLinkProvider`パターンへ揃える。

1. `state.portal_url: str`フィールドを、両`StoreSubscriptionState`クラスから削除する
   (状態として永続化・保存する対象から外す)。
2. `render_subscription_activated_message()`・`render_cancellation_scheduled_message()`の
   引数を`portal_url: str`から`portal_url: Optional[str]`に変え、`None`の場合は
   「マイページ」の案内文言自体を省略する安全側フォールバックを設計する(courseset-pasha・
   aircon-pashaの`PORTAL_LINK_UNAVAILABLE_FALLBACK`相当の考え方を踏襲)。
3. `handle_subscription_activated()`・`handle_subscription_updated()`の呼び出し元
   (`receive_stripe_webhook()`)に`portal_link_provider: Optional[PortalLinkProvider]`
   引数を追加し、メッセージ整形の直前に`portal_link_provider.get_portal_url(store_id)`を
   呼んで都度URLを解決する(`portal_link_provider`が`None`の場合は3.のフォールバック文言に
   委ねる)。
4. `PortalLinkProvider`Protocol定義・`StripePortalLinkProvider`実装本体
   (`prototype/portal_session.py`新規)は、aircon-pashaの`portal-session-provider-design.md`
   3節の設計をほぼそのまま流用できる(本ventureもLINEのpostbackイベント由来の
   `store_id`/`user_id`をそのまま渡せばよく、course-set-pashaのようなLIFF IDトークン
   検証を経由しないaircon-pasha方式が本ventureにも当てはまる)。

## 5. 実装状況

実装済み(2026-09-04 17:00 UTC、フェーズ続き193)。上記4点をすべて実装した。

1. `cloud_function_subscription_activated_webhook.StoreSubscriptionState`・
   `cloud_function_subscription_cancelled_webhook.StoreSubscriptionState`から
   `portal_url: str`フィールドを削除した。
2. `render_subscription_activated_message()`・`render_cancellation_scheduled_message()`の
   引数を`portal_url: Optional[str]`に変更した。`None`の場合、前者は「ご登録内容の
   確認・変更」案内行自体を省略し、後者は「▼ お手続きはこちら」のURLブロックを
   「このトークルームへご返信ください」導線に差し替える(3.で定めた通りの安全側
   フォールバック)。
3. `handle_subscription_activated()`・`handle_subscription_updated()`に
   `portal_url: Optional[str] = None`引数を追加し、`stripe_webhook_entry_point.
   receive_stripe_webhook()`が`EVENT_CHECKOUT_SESSION_COMPLETED`・
   `EVENT_CUSTOMER_SUBSCRIPTION_UPDATED`の各分岐でメッセージ整形の直前に
   `portal_link_provider.get_portal_url(store_id)`を呼んで都度解決し引数として渡す
   (`portal_link_provider`が`None`の場合は解決せず`None`のまま渡し、2.のフォールバックに
   委ねる)。
4. `PortalLinkProvider`Protocol定義・`StripePortalLinkProvider`実装本体を
   `prototype/portal_session.py`として新規作成した(aircon-pashaのportal_session.pyを
   ほぼそのまま流用、`store_profile_store.StoreProfileStoreProtocol.
   get_stripe_customer_id()`を最小限のstructural typingで利用)。

テスト16件追加(`test_portal_session.py`9件新規・`test_cloud_function_subscription_
activated_webhook.py`2件追加・`test_cloud_function_subscription_cancelled_webhook.py`
3件追加・`test_stripe_webhook_entry_point.py`4件追加)、venture全体710件全件
(`python3 -m unittest discover -s prototype -p "test_*.py"`)パス・schema検証25件
(`python3 schema/validate_test_cases.py`)パスを確認した。

## 6. 今後の課題

- `PortalLinkProvider`実装本体の実`stripe.billing_portal.Session.create()`呼び出しへの
  差し替え、および`get_stripe_webhook_runtime_dependencies()`への実際の配線は、
  実Stripeアカウント接続(オーナー承認待ち、pending-approval.md参照)後の課題として残る
  (aircon-pashaの同ドキュメント6節と同じ位置づけ)。
