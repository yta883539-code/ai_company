# Checkout Session Cloud Functionsエントリポイント設計

README.mdフェーズ139〜141「次回候補(2)」(Webフォームバックエンドのルーティング実装が
確定した後のCheckout Session発行用`main(request)`自体のコード実装)に対応する。

## 1. 前提: Webフォームバックエンドのルーティング方針の確定

これまで「ルーティング実装が確定した後」という前提のまま複数フェーズ(139〜141)で
先送りされていたが、本フェーズで以下のとおり確定する。

tech-stack.md(フェーズ70)で選定済みのGCP Cloud Functions (2nd gen)は、1デプロイ=1エンド
ポイントの構成であり、本venture他の`main(request)`(`stripe_webhook.py`・
`cloud_function_send_trial_end_emails.py`)もそれぞれ独立したCloud Functionとして設計
されている(共有のルーター経由で複数エンドポイントを1つのCloud Functionに多重化する設計は
採用していない)。これはcourse-set-pasha・line-reservation-aiの`stripe_webhook.main()`と
`checkout_session.main()`が別々のCloud Functionである構成とも対称であり、本venture固有の
新しい決定を要する論点ではなかった。

よって「ルーティング実装」自体は存在せず、各プロトタイプモジュール(`checkout_session.py`・
`form_submission_flow.py`等)が自分の`main(request)`を持ち、それぞれ個別のURL
(実デプロイ後に確定、例: `https://REGION-PROJECT.cloudfunctions.net/forklift-pasha-checkout`)
に対応する、というこれまでの暗黙の前提をここで明文化する。これにより本フェーズ139〜141で
3回先送りされていた依存は解消され、`checkout_session.py`の`main(request)`実装に進める。

## 2. 認証方式: LIFF IDトークンではなくaccess_token

course-set-pasha・line-reservation-aiのCheckout Session発行エンドポイントは、入力チャネルが
LINE(LIFF)であるため`Authorization: Bearer <IDトークン>`によるLIFF ID Token検証で
`internal_id`を解決する。本ventureは入力チャネルが汎用Webフォーム(LINE非依存、tech-
stack.mdフェーズ70決定)であり、settings.html(フェーズ101)・
access-url-reissue-http-entry-point-design.mdが既に確立している「アクセスURL
(`https://<ドメイン>/f/{accessToken}`)に埋め込まれた`accessToken`で本人確認する」方式を
決済導線にもそのまま流用する。プラン選択ページ(`web-form-mockup/plan-selection.html`)は
このアクセスURL経由で開かれる前提のため、ページのJSが同じ`accessToken`をクエリパラメータ
`access_token`としてCheckout Session発行エンドポイントへ引き継ぐだけでよく、新しい認証機構を
追加で設計する必要はない。

未知・空の`access_token`の場合はstatus_code=404とする(「トークンが無効」である以上の情報
(本来正しい`internal_id`が存在するか等)を返さないため、401ではなく404とした。
access-url-reissue-http-entry-point-design.mdの既存方針があればそれに合わせる想定だが、
本venture内に先行する方針は無かったため今回新規に定めた)。

## 3. `create_checkout_session()`

```python
def create_checkout_session(
    access_token: "str | None",
    plan_id: "str | None",
    *,
    access_token_store: AccessTokenStoreProtocol,
    operator_store: FleetOperatorStoreProtocol,
) -> CheckoutSessionResult:
    if not access_token:
        return CheckoutSessionResult(status_code=404, error="access_token_not_found")
    internal_id = access_token_store.get_internal_id_by_access_token(access_token)
    if internal_id is None:
        return CheckoutSessionResult(status_code=404, error="access_token_not_found")
    if plan_id not in KNOWN_PLAN_IDS:
        return CheckoutSessionResult(status_code=400, error="unknown_plan_id")

    params = build_checkout_session_params(
        internal_id,
        plan_id,
        email=operator_store.get_email(internal_id),
        existing_stripe_customer_id=operator_store.get_stripe_customer_id(internal_id),
    )
    return CheckoutSessionResult(status_code=200, checkout_session_params=params)
```

- `build_checkout_session_params()`(フェーズ124、既存の純粋関数)はそのまま流用し、本関数が
  追加するのは「access_tokenからinternal_idを解決する」「email/stripe_customer_idを
  operator_storeから読む」「plan_idの事前チェック」の3点のみ。
- `internal_id`が未知の値でも`build_checkout_session_params()`自体はエラーにしない
  (`internal_id`の形式チェックのみ)ため、`access_token_store`側で事前に実在確認する
  本関数の役割が必須となる。
- email・stripe_customer_idが共に`None`の場合(新規・未設定)でも
  `build_checkout_session_params()`は両方未設定のまま呼べる(既存の`Optional`仕様通り)。

## 4. `main(request)`

```python
def main(request):
    access_token = request.args.get("access_token")
    plan_id = request.args.get("plan")
    result = create_checkout_session(
        access_token,
        plan_id,
        **get_checkout_runtime_dependencies(),
    )
    if result.status_code == 200:
        return result.checkout_session_params, 200
    return (result.error or "error"), result.status_code
```

course-set-pasha/line-reservation-aiの`main()`と異なり、LIFF未登録による`NotImplementedError`
処理(501)は不要(本venture認証方式に`verify_id_token`相当の外部サービス未接続ステップが
無いため)。

`get_checkout_runtime_dependencies()`は`stripe_webhook.get_stripe_runtime_dependencies()`と
対称の構成で、`InMemoryAccessTokenStore()`・`InMemoryFleetOperatorStore()`をそれぞれ1つ
生成する(実Firestore接続後は同一インスタンスをプロセス間で共有する構成に差し替える、
他venture既知の限界と同様)。

## 5. 残課題

- `checkout_session_params`を実際にStripe Checkout Session作成APIへ渡し、返り値のURLを
  レスポンスとして返す処理は、実Stripeアカウント接続(オーナー承認待ち、pending-
  approval.md 2026-10-06 22:00 UTC記載)後の課題として残る。
- `plan-selection.html`側のボタン(現在`disabled`固定)から本エンドポイントへの実際の
  fetch呼び出し配線(`access_token`をどう取得するか、URLパス`/f/{accessToken}`からの
  抽出を含む)は次回候補とする。
- 実Cloud Functionsデプロイ・実ドメイン確定はオーナー承認待ちの範囲内(tech-stack.md
  「未検証・残課題」参照)。

最終更新: 2026-10-12 19:00 UTC(フェーズ142: Webフォームバックエンドのルーティング方針
〈1Cloud Function=1エンドポイント、多重化ルーターは不要〉を確定し、Checkout Session発行
エンドポイントの認証方式〈LIFF IDトークンではなく既存のaccess_token機構を流用〉を設計した)
