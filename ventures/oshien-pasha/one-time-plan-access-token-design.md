# 都度プラン(mode=payment)用access_tokenの永続化・1回使用後の失効設計(フェーズ104)

result-display-page-generation-request-design.md(フェーズ102)3節が未解決のまま残した
「都度プラン(mode=payment、1決済=1回)のaccess_tokenがどのストアに保存され、1回使用後に
どう失効させるか」に対応する。

## 1. 前提の再確認: フェーズ36決定との矛盾

firestore-data-model.md 0節(フェーズ36)は「都度プランは識別子を持たないためコレクション
自体が存在しない」と決定していたが、この決定はcheckout-result-http-entry-point-design.md
(フェーズ100)・result-display-page-generation-request-design.md(フェーズ102)が確定させた
「決済完了→`access_token`発行→結果ページ→生成リクエスト」という共通エントリポイント設計
より前のものであり、両エントリポイントは現状、月額フリーパス(`fan_pass`)専用の実装に
なっている。都度プランもこの共通エントリポイントを経由する以上、フェーズ36の決定は
事実上成立しなくなっており、都度プラン側にも何らかの永続化が必要と判断する(本フェーズで
フェーズ36の記述を上書きする)。

なお、本設計の対象は**有料の都度プラン決済(2回目以降、Stripe Checkout `mode=payment`)**
に限る。pricing-plan.md「無料トライアル条件」が確定させた「初回1回は無料・カード登録なし」
の経路は決済自体が発生しないため本設計の対象外とし、別途検討課題として残す(4節参照)。

## 2. コレクション方針: `one_time_pass/{internal_id}`を新設(`fan_pass`とは分離)

event-komiguai-pashaの`one_time_draft`(アカウント登録なし単発決済の設計、one-time-checkout-
no-account-design.md)と同じ考え方で、`fan_pass`コレクションに混在させず独立コレクションと
する。

- `fan_pass`は`subscriptionStatus`・`stripeSubscriptionId`等サブスクリプション固有フィールド
  を持ち、都度プランを同居させると大半のフィールドがnull許容になり可読性が落ちる
  (フェーズ36の名称一本化はあくまで「月額フリーパスを指す名前をfan_passに統一する」議論で
  あり、都度プランを同一コレクションに格納する判断ではなかったことを明記しておく)。
- 都度プランは「1 Checkout Session = 1 回の生成」で完結するため、`fan_pass`のように
  `stripeSubscriptionId`経由の間接解決は不要で、`stripeCheckoutSessionId`自体を直接の
  ドキュメントキー相当として扱える(3節参照)。

```
one_time_pass/{internal_id}
{
  accessToken: "...",            // サーバー側ランダム発行。fan_passと同じ命名・生成方式
  stripeCheckoutSessionId: "...", // Webhook(checkout.session.completed, mode=payment)から
                                   // 取得。本コレクション内で一意(dedupキー)
  consumedAt: null,               // number(Unixエポック秒) | null。生成成功後にセットする
                                   // 「1回使用後の失効」フラグ本体(5節)
  createdAt: ...,                 // number。expiresAt算出の起点
  expiresAt: ...,                 // number。createdAt + 24時間
                                   // (event-komiguai-pashaのttl-expiry-result-delivery-
                                   // refund-design.mdと同じ24時間を踏襲。「当落発表後の
                                   // 短期間に使い切る」という本venture自体の利用シーンとも
                                   // 整合する)
}
```

## 3. ルックアップの一本化: `get_by_checkout_session_id`

checkout_result_page_handler.pyの現状実装は、(a)`checkout_session_id`からStripe
subscription_idを取得→(b)`fan_pass_store.get_by_stripe_subscription_id()`という2段引きで、
`mode=subscription`専用になっている。都度プランは`stripe_subscription_id`を持たないため
この経路に乗らない。

対応として、`resolve_checkout_result()`が呼ぶルックアップ手順を、Checkout Sessionの`mode`
フィールドで分岐する`CombinedPassLookupProtocol`に差し替える案を採用する。

```python
class CombinedPassLookupProtocol(Protocol):
    def get_by_checkout_session(
        self, checkout_session_id: str
    ) -> "PassLookupResult | None":
        """Stripe側でSessionのmodeを確認し、
        mode == "subscription" なら get_subscription_id_for_session() 経由で
        fan_pass_store.get_by_stripe_subscription_id() に委譲、
        mode == "payment" なら one_time_pass_store.get_by_checkout_session_id() に
        直接委譲する。戻り値は access_token・(都度プランのみ)consumed 済みかどうかを
        含む共通の PassLookupResult に正規化する。"""
        ...
```

既存の`StripeCheckoutSessionLookupProtocol.get_subscription_id_for_session()`は
subscription経路専用のメソッドとしてそのまま残し、`CombinedPassLookupProtocol`がその上位に
位置するラッパーという位置づけにする(フェーズ100の実装・テストへの破壊的変更を避ける)。

ポーリングのループ構造自体(最大5回・1秒間隔、`CheckoutResultPageResult.status`の
`"ready"`/`"pending"`分岐)は変更不要で、ルックアップ手順の差し替えのみで両プランに対応できる。

## 4. 1回使用後の失効(`consumedAt`)

`receive_generation_request()`(フェーズ102)が`one_time_pass`の`access_token`を受け取った
場合、生成処理の前後で次の分岐を追加する。

1. `get_by_access_token()`で該当ドキュメントを特定(見つからない場合は既存どおり404
   `unknown_access_token`)。
2. `consumedAt`が既に設定されている場合、生成を実行せず`status_code=403`
   (`error="already_consumed"`)を返す。fan-pass-canceled-access-block-design.mdが
   `subscriptionStatus == "canceled"`を403に変換するのと同じステータスコード帯を踏襲し、
   「本人特定はできたが利用権限がない」系のエラーとして扱う。
3. `expiresAt`を過ぎている場合は、`consumedAt`の状態によらず`status_code=404`
   (`error="unknown_access_token"`)として扱う(期限切れと「そもそも存在しない」を呼び出し側
   から区別させない。forklift-pashaの既存方針と同じ、情報漏洩を避ける設計)。
4. 上記いずれにも該当しない場合のみLLM生成を実行し、成功時に`consumedAt`を現在時刻で
   更新する(更新順序: LLM呼び出し成功確認後。生成失敗時に`consumedAt`を書き込んでしまうと
   支払い済みの利用者が1回も生成できないまま権利を失うため、「生成成功を確認してから
   消費済みにする」順序を厳守する)。

月額フリーパス側(`fan_pass`)には`consumedAt`に相当するフィールドを設けない(無制限利用の
ため消費という概念自体がない)。`receive_generation_request()`はストアの種別
(`fan_pass`か`one_time_pass`か)に応じてこの分岐の要否自体を切り替える必要があり、具体的な
分岐コード(`isinstance`相当の判定か、`PassLookupResult`に`plan_type`フィールドを持たせるか)
は次回以降のプロトタイプ実コード化時に確定する。

## 5. 残課題

- 本設計のプロトタイプ実コード化(`prototype/one_time_pass_store.py`新規作成、
  `fan_pass_store.py`と同型のインメモリ実装・テスト)。
- `CombinedPassLookupProtocol`・`PassLookupResult`の実コード化と、既存
  `checkout_result_page_handler.py`・`test_checkout_result_page_handler.py`への組み込み
  (破壊的変更を避けるリファクタリング手順の検討を含む)。
- 都度プラン・初回無料体験(決済なし)の経路設計(1節で対象外とした残課題。決済が発生しない
  ため`stripeCheckoutSessionId`を鍵にできず、別の識別手段〈Cookieの一時セッションID等〉が
  必要になる可能性がある)。
- `expiresAt`超過かつ未消費(`consumedAt`が null)のまま期限切れとなった場合の返金方針
  (event-komiguai-pashaのttl-expiry-result-delivery-refund-design.mdが同種の論点を解決済み
  のため、同パターンの適用可否を次回検討する)。
- 実Firestore接続・実Stripe Webhook登録はオーナー承認が必要なアクション(既存の承認待ち
  事項の範囲内)のため、本メモは設計の検討に留める(コード実装・外部サービスへの接続は
  一切行っていない)。承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は
  本フェーズでは発生していないためpending-approval.mdへの新規追記は不要。

最終更新: 2026-11-09 14:00 UTC(フェーズ104: フェーズ102・3節の残課題に対応し、都度プラン用
`one_time_pass`コレクション・`consumedAt`による1回使用後の失効設計・`CombinedPassLookupProtocol`
によるルックアップ一本化方針を確定。フェーズ36の「都度プランはコレクションを持たない」決定が
フェーズ100・102の共通エントリポイント設計により前提から外れていたことも明記した)
