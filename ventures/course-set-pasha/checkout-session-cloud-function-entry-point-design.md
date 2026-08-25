# Checkout Session Cloud Functionsエントリポイント設計

作成日: 2026-08-25(フェーズ115)

checkout-session-endpoint-design.md(フェーズ112)「残課題」2点目だった、
`create_checkout_session()`を実Cloud Functionsのリクエストオブジェクト
(`functions_framework`が渡すFlask Request互換インターフェース)に接続する`main(request)`
本体の設計・実装。stripe_webhook.main()(フェーズ96・
stripe-webhook-cloud-function-entry-point-design.md)と対称の構成とする。

## 1. 方針

- `checkout_session.py`に閉じたまま、stripe版の`main(request)`と同じ薄い配線パターンを
  踏襲する。`functions_framework`自体はインポートせず、`request.headers.get(...)`という
  インターフェースにのみ依存する(ローカルテストでは同じインターフェースを持つ軽量スタブで
  代替可能)。
- 認証ヘッダ名は`Authorization`(`"Bearer <IDトークン>"`形式、LIFF標準)。

## 2. `verify_id_token`の扱い: 未実装プレースホルダ

stripe版の`resolve_user_id`(暫定的に常に`None`を返す関数で代替できた)と異なり、
`verify_id_token`はLINE Platform APIの`/oauth2/v2.1/verify`相当への実HTTPリクエストが
本質であり、恒久的に「常に失敗を返す」ダミーで代替すると誤って動いているように見えてしまう。
そのため、以下の方針とする。

- `_verify_id_token_not_implemented(id_token)`という名前の関数を用意し、呼ばれたら
  `NotImplementedError`を送出する(LIFFアプリ実登録・オーナー承認待ちであることを
  意図的に明示する)。
- `main(request)`は、`create_checkout_session()`の呼び出しを`try/except NotImplementedError`
  で囲み、捕捉した場合は`status_code=501`・`error="verify_id_token_not_implemented"`相当の
  レスポンスを返す(通常のCloud Functionsの未捕捉例外による500汎用エラーより、原因が
  「未実装」であることを呼び出し元〈LIFFフロントエンド〉が判別しやすくなる)。
- `Authorization`ヘッダが欠落・不正な形式の場合は、`create_checkout_session()`の早期
  リターン(401、`verify_id_token`未呼び出し)がそのまま活きるため、`NotImplementedError`には
  到達しない(フロントエンドの実装ミス・トークン未添付は401、サーバー側の未実装は501で
  切り分けられる)。

## 3. `get_checkout_runtime_dependencies()`

stripe版の`get_stripe_runtime_dependencies()`と対称の構成。

- `user_profile_store`: `InMemoryUserProfileStore()`
  (`application_form_submission_flow.py`)を1つ生成する。実運用ではStripe側
  Cloud Functionと同一Firestoreの`user_profile`コレクションを共有する想定だが、本プロセスでは
  別プロセス・別インスタンスとして初期化されるため、既存`stripe_customer_id`の引き継ぎは
  呼び出しをまたいで保持されない(`stripe_webhook.get_stripe_runtime_dependencies()`の
  既知の限界と同様、実Firestore接続後に解消される)。
- `verify_id_token`: `_verify_id_token_not_implemented`。LIFFアプリ実登録
  (オーナー承認待ち)後に実装本体へ差し替える(checkout-session-endpoint-design.md
  「残課題」1点目)。

## 4. `main(request)`

```python
def main(request):
    authorization_header = request.headers.get("Authorization")
    try:
        result = create_checkout_session(
            authorization_header, **get_checkout_runtime_dependencies()
        )
    except NotImplementedError:
        return "verify_id_token_not_implemented", 501

    if result.status_code == 200:
        return result.checkout_session_params, 200
    return (result.error or "error"), result.status_code
```

stripe版`main()`と同じ形の戻り値((body, status_code)のタプル)とする(成功時のbodyは
`checkout_session_params`のdictそのもの。実Cloud Functions環境ではこのdictを
`stripe.checkout.Session.create(**params)`へ渡す配線が別途必要で、checkout-session-endpoint-
design.md「残課題」3点目のまま残る)。

## 残課題

- `verify_id_token`実装本体(LINE Platform API `/oauth2/v2.1/verify`への実HTTPリクエスト)は
  引き続きLIFFアプリ実登録後(オーナー承認待ち)の課題として残る。本フェーズでは、それまでの
  間`main(request)`が501を返すことで「未実装」であることを明示できる状態にした。
- `checkout_session_params`を実際にStripe Checkout Session作成APIへ渡し、返り値のURLを
  レスポンスとして返す処理は、実Stripeアカウント接続(オーナー承認待ち)後の課題として残る
  (checkout-session-endpoint-design.md「残課題」3点目と同じ)。
- 実Cloud Functions環境で`user_profile_store`をFirestore版に差し替える配線は、
  stripe側と同時に実Firestore接続確定後に行う。
