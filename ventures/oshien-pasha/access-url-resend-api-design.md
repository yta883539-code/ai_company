# アクセスURL再送フロー・APIエンドポイント設計(フェーズ42)

フェーズ41(email-lookup-necessity-review.md)で確定した方針
「`email`はFirestore側の検索鍵にはせず、Stripe API側の顧客検索
(`customers.list(email=...)`)→サブスクリプション検索(`subscriptions.list(customer=...)`)
経路で`stripeSubscriptionId`を得て、既存の`get_by_stripe_subscription_id`で
`fan_pass`ドキュメントを特定する」を、monthly-pass-identity-design.md 3節の
「アクセスURLを再送する」ページ(メールアドレス入力1項目のみの軽量フォーム)の
処理本体として設計・コード化する(README.mdフェーズ41「次回候補(2)」対応)。

forklift-pashaの`access_url_reissue_handler.py`・`access-url-reissue-http-entry-point-
design.md`(フェーズ135・136)と同じ「処理本体を先に机上実装し、HTTP配線は承認後」の
方針を踏襲するが、本人特定の起点が異なる点が設計上の最大の差分である。

## 1. forklift-pashaとの差分: 本人特定の起点

forklift-pashaの再発行エンドポイントは、利用者が**既に持っている**`accessToken`付きURL
(`/f/{accessToken}`)で開かれる設定ページからの操作であり、URLパス自体が本人特定の鍵になる
(access-url-reissue-http-entry-point-design.md 1節)。

本venture(oshien-pasha)の「アクセスURLを再送する」ページは、**アクセスURLを失った**
利用者のための入口であるため、`accessToken`を前提にできない。代わりに利用者が入力した
`email`を起点に、Stripe API側で本人(有効な月額フリーパスのサブスクリプション)を
特定する必要がある(monthly-pass-identity-design.md 3節2.)。したがって本エンドポイントは
forklift-pashaの「URLパス解決」ではなく「外部API(Stripe)への問い合わせ」が認証相当の
役割を果たす。

## 2. `StripeSubscriptionLookupProtocol`

Stripe APIへの実際の呼び出し(`customers.list`・`subscriptions.list`)は本フェーズでは
行わず、usage_counter.py・fan_pass_store.pyと同じ「インターフェースのみ確定し、
インメモリの偽実装でロジックを検証する」方針を踏襲する。

```python
class StripeSubscriptionLookupProtocol(Protocol):
    def find_active_subscription_id_by_email(self, email: str) -> str | None:
        """`customers.list(email=...)`→`subscriptions.list(customer=..., status="active")`
        の実呼び出しを1回の問い合わせに集約した抽象。該当する顧客が存在しない、または
        有効なサブスクリプションを持たない場合はNone(例外にしない。「登録されていない
        メールアドレス」は想定される正常系の分岐のため)。

        同一メールアドレスに対し複数の有効なサブスクリプションが見つかった場合は、
        fan-pass-store-protocol-design.md 3節が確定した「同一Stripe顧客が有効な
        サブスクリプションを複数持たない」という単一プラン前提が崩れた異常系として
        MultipleActiveSubscriptionsErrorを送出する。
        """
        ...
```

## 3. 処理本体: `handle_resend_request()`

```python
def handle_resend_request(
    fan_pass_store: FanPassStoreProtocol,
    stripe_lookup: StripeSubscriptionLookupProtocol,
    email: str,
    *,
    new_access_token_factory: Callable[[], str],
) -> ResendRequestResult:
```

処理順序:

1. `stripe_lookup.find_active_subscription_id_by_email(email)`で`stripe_subscription_id`を
   解決する。`None`の場合、`fan_pass_store`には一切アクセスせず`found=False`で返す。
2. 解決できた場合、`fan_pass_store.get_by_stripe_subscription_id(stripe_subscription_id)`で
   `fan_pass`ドキュメントを特定する(Stripe側に有効なサブスクリプションがあるのに
   Firestore側にドキュメントが無いのは、Webhook処理の未完了・不整合を示す異常系のため
   `FanPassNotFoundForSubscriptionError`を送出し、呼び出し側でアラート対象として扱う)。
3. `new_access_token_factory()`で新トークンを生成し、
   `fan_pass_store.reissue_access_token(internal_id, new_access_token=...)`で上書きする
   (旧トークンは即時失効。forklift-pashaと同じ「常に新規発行」方針)。
4. 送信先メールアドレスは**利用者が入力した`email`**とする(fan_passドキュメントの
   `email`フィールドへの書き戻しは行わない。入力メールアドレスの誤字・別アドレスからの
   問い合わせ可能性があり、Stripe顧客検索に使われた`email`自体を信頼して返送先とするのが
   最小の設計である。`email`フィールドの更新要否は別課題として残す)。
5. `found=True`・`new_access_url`・`destination_email`(入力された`email`そのもの)を
   `ResendRequestResult`として返す。実際のメール送信はここでは行わない
   (他venture共通の運用方針〈メール連携接続後、送信直前に毎回オーナー確認〉に従う)。

`found=False`の場合も`destination_email`は返さず、呼び出し側(HTTPエントリポイント)が
「メールアドレスが見つからない」旨をそのまま利用者に見せない設計とする(3節参照)。

## 4. レスポンスの扱い: 「見つからない」をどう見せるか

forklift-pashaは`accessToken`方式のため「無効なトークン」=404という明確な異常系だが、
本ventureの`email`入力フォームでは、「このメールアドレスは登録されていません」を正直に
返すと、第三者が総当たりでメールアドレスの登録有無を探索できてしまう(ユーザー列挙
〈enumeration〉のリスク)。したがって、`found`の真偽にかかわらずHTTPレスポンスは
常に同一の`200`・同一の案内文(「ご入力いただいたメールアドレス宛にご案内をお送りします」)
を返し、実際に送信するかどうかの分岐はサーバー内部(メール送信実装時、オーナー確認の対象を
`found=True`の場合のみに絞る)に閉じ込める方針とする。

- `handle_resend_request()`自体は`found: bool`を含む`ResendRequestResult`を返す
  (呼び出し側・テストが内部状態を区別できるようにする)。
- HTTPエントリポイント(次回以降のコード化対象)は`found`の値を問わず`"OK", 200`のみを
  返し、レスポンス本文・ステータスコードに差を持たせない。

## 5. 残課題

- HTTPエントリポイント(`receive_resend_request()`相当、`request.form.get("email")`からの
  値取り出し配線)のコード化は次回以降とする(forklift-pashaのフェーズ135→136の順序を踏襲)。
- `StripeSubscriptionLookupProtocol`の実Stripe接続実装、実際のメール送信実装・接続は
  いずれもオーナー承認が必要なアクション(既存の承認待ち事項の範囲内)のため本フェーズでは
  行わない。
- fan_passドキュメントの`email`フィールドを、再送フローで入力された新しいメールアドレスで
  更新するべきかどうかは未検討のまま残す(3節参照)。

実LLM呼び出し・Stripe等決済代行サービスとの実接続、実際のFirestore・GCPプロジェクト作成・
メール送信実装自体はオーナー承認が必要なアクションに該当するため、本メモは設計・仮説の検討と
インメモリでの机上コード化に留める(外部サービスへの接続は一切行っていない)。承認が必要な
アクション(支払い・アカウント作成・外部公開・送信等)は本フェーズでは発生していないため
pending-approval.mdへの新規追記は不要(既存の承認待ち事項の範囲内で扱う)。

最終更新: 2026-10-31 22:00 UTC(フェーズ42: アクセスURL再送フローの処理本体
`handle_resend_request()`・`StripeSubscriptionLookupProtocol`を設計し、
prototype/access_url_resend_handler.pyとしてコード化した)
