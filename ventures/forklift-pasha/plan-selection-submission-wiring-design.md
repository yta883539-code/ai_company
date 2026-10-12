# プラン選択ページ: 申し込みボタンの送信配線設計(フェーズ143)

README.mdフェーズ142「次回候補(2)」(`plan-selection.html`のボタンから
`checkout_session.main(request)`への実際の送信配線、`access_token`をアクセスURL
`/f/{accessToken}`から取得する方法の検討を含む)に対応する。

## 1. 結論: JSのfetch呼び出しは不要。サーバー側レンダリング+プレーンなリンクで足りる

README.mdフェーズ142「次回候補(2)」は「fetch呼び出し配線」という表現を使っていたが、
本venture他の画面モックアップ(`daily.html`・`monthly.html`・`annual.html`・`index.html`・
`settings.html`、いずれも「JS不使用・外部公開なし・バックエンド接続なし」方針)との整合を
検討した結果、本エンドポイントについてもJS(`fetch()`等)は不要であり、プレーンな
`<a href>`(またはGETフォーム)で設計できることが分かった。理由は以下の2点。

1. **`access_token`の取得方法**: `access-url-reissue-http-entry-point-design.md`(フェーズ136)
   が既に確立している前提どおり、`plan-selection.html`自体が`https://<ドメイン>/f/{accessToken}`
   形式のURL配下(実デプロイ後は例えば`/f/{accessToken}/plans`)でサーバー側(Cloud Functions)
   によって動的に生成される想定である。`settings.html`の「あなたのアクセスURL」欄が
   ダミー値("f3x9k2qh7mN8pLw2")を表示しているのと同じく、実デプロイ後はサーバー側が
   リクエストURLから`access_token`を取り出し、そのままテンプレート変数としてページ内の
   各リンクのクエリパラメータに埋め込む。ブラウザ側のJSが`window.location`等からトークンを
   再抽出する処理は不要(そもそも本venture他ページも含め、動的なURLパース処理は一切
   JSに依存していない)。
2. **Checkout Session発行結果の扱い**: `checkout_session.main(request)`は現状、成功時に
   `checkout_session_params`(Stripe Checkout Session作成APIへ渡すパラメータdict)をJSONで
   返す設計(フェーズ142)だが、これは「実Stripe API呼び出し」(残課題、オーナー承認待ち)を
   行う前の中間状態である。実際にStripeへ接続する際は、`main(request)`内で
   `stripe.checkout.sessions.create(**checkout_session_params)`を呼び、返ってきた
   `session.url`へのHTTPリダイレクト(303 See Other)をレスポンスとする設計に変更する
   (course-set-pasha・line-reservation-ai等、LIFF経由でCheckout Session発行後にStripeの
   `session.url`へリダイレクトする既存パターンと同型。本ventureが異なるのは認証方式
   〈access_token vs LIFF IDトークン〉のみで、Checkout Session発行後の遷移方式自体は
   他ventureと揃える)。この方式であれば、ブラウザは単に通常のリンク遷移としてエンド
   ポイントのURLへ移動するだけでよく、JSによるレスポンス受信・画面遷移制御が一切不要になる。

## 2. 具体的なマークアップ(実デプロイ後)

```html
<a class="apply-btn" href="https://REGION-PROJECT.cloudfunctions.net/forklift-pasha-checkout?access_token={{access_token}}&plan=light">このプランで申し込む</a>
```

- `{{access_token}}`はサーバー側テンプレートがページ生成時に埋め込む値(ページ自体が
  `/f/{accessToken}`配下で動的生成されるため、クライアント側で別途取得・送信する手段は
  不要)。
- `plan`パラメータは各プランカードに既存の`data-plan-id`属性(フェーズ141)と同じ値
  ("light"/"standard"/"fleet")をリンクのクエリパラメータとして静的に埋め込む(カード
  ごとに異なるURLを持つだけで、JSによる動的な値の差し込みは不要)。
- ボタンを`<a>`タグ(リンク)にするため、現在の`<button type="button" disabled>`とは
  HTML要素自体が変わる。CSSクラス`.apply-btn`はそのまま流用できるよう、リンクにも同じ
  見た目(ボタン型リンク、`display: block`+パディング)を適用する前提とする。

## 3. 本ファイル(`web-form-mockup/plan-selection.html`)自体への反映は次回以降

上記は「実デプロイ後」の構成の設計であり、本venture他の画面モックアップと同じ方針
(実Stripe接続・実ドメイン確定がオーナー承認待ちの間は、ボタンは`disabled`のまま変更
しない)を踏襲し、本フェーズでは`plan-selection.html`自体の実装変更は行わない。実際に
`<button disabled>`を`<a href>`に差し替える作業、および`checkout_session.main()`を
JSON返却からHTTPリダイレクト返却に変更する実装(`stripe.checkout.sessions.create()`の
実呼び出しを含む)は、実Stripeアカウント接続(オーナー承認待ち、pending-approval.md
2026-10-06 22:00 UTC記載)後にまとめて着手する。

## 4. 残課題

- 上記1.2で述べた`main(request)`のレスポンス方式変更(JSON→HTTPリダイレクト)自体は、
  実Stripe接続前でも`build_checkout_session_params()`の出力を使ったテスト(リダイレクト
  先URLをStripeのダミーレスポンスで代用する等)として先行実装できる可能性があるが、
  本フェーズでは設計のみとし実装は次回以降の課題とする。
- `plan-selection.html`が実際にどのURLパス(例: `/f/{accessToken}/plans`)で配信される
  かのルーティング確定自体は、`settings.html`等の他画面と共通の「複数画面を1つの
  `access_token`配下でどう振り分けるか」という、まだ本venture内で明文化されていない
  論点であり、次回以降の課題として残る。

最終更新: 2026-10-12 20:00 UTC(フェーズ143: `plan-selection.html`の申し込みボタンの送信
配線を設計し、JSのfetch呼び出しは不要でサーバー側レンダリング+プレーンなリンク、かつ
`checkout_session.main()`はJSON返却からStripe Checkout URLへのHTTPリダイレクト返却に
変更する方式が本venture他ページの「JS不使用」方針と整合することを確認した。コード・
HTML自体の変更は実Stripe接続待ちのため次回以降とする)
