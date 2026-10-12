# アクセスURL再発行のHTTPエントリポイント設計

作成日: 2026-10-12(フェーズ136)

access_url_reissue_handler.py(フェーズ135)が机上実装した`handle_reissue_request()`の
先にある残課題、「settings.htmlの『アクセスURLを再発行する』ボタン・メールアドレス変更欄の
実際のHTTPリクエストを受け取り、`handle_reissue_request()`に渡す」という入口部分を設計する
(README.mdフェーズ135「次回候補(2)」対応)。aircon-pashaの`webhook-http-entry-point-
design.md`(フェーズ115)・stripe_webhook.pyの`main(request)`と同じ位置づけだが、本venture
では署名検証の代わりに「URLパスに含まれるアクセストークンから本人を特定する」という異なる
認証方式を扱う点が特徴である。

## 1. 前提: 本人特定の方式

本ventureの設定ページは`https://<ドメイン>/f/{accessToken}`形式のURL(access-token-
reissue-design.md 1節)でのみアクセスされ、ログインID・パスワードは存在しない。したがって
HTTPエントリポイントは、リクエストボディではなく**URLパス自体に含まれる`accessToken`**を
本人特定の鍵として扱う必要がある(settings.html自体がこのURLで開かれているため、ページ内の
フォームは`accessToken`を隠しフィールド等で再送する想定)。

- `access_token_store.get_internal_id_by_access_token(access_token)`で`internal_id`を
  解決する。見つからない場合(トークンが無効・既に再発行済みで失効済み)は、
  `handle_reissue_request()`を呼ばずに404相当のエラーを返す。
- 解決した`internal_id`を`handle_reissue_request()`にそのまま渡す。これにより
  `access_url_reissue_handler.py`自体は「どの`internal_id`に対する操作か」を信頼済みの
  入力として受け取れる設計を保てる(URLパス解決という認証はエントリポイント側の責務とし、
  処理本体に認証ロジックを混在させない)。

## 2. 方針: `ReissueHttpResult`・`receive_reissue_request()`

```python
@dataclass(frozen=True)
class ReissueHttpResult:
    status_code: int
    result: Optional[ReissueRequestResult] = None
    error: Optional[str] = None


def receive_reissue_request(
    access_token_store: AccessTokenStoreProtocol,
    email_store: _EmailFieldStoreProtocol,
    access_url_provider: _AccessUrlProviderProtocol,
    access_token: str,
    new_email: Optional[str] = None,
) -> ReissueHttpResult:
```

処理順序:

1. `access_token`が空(None・空文字列)の場合は、`get_internal_id_by_access_token()`を
   呼ばずに`status_code=400`(`error="missing_access_token"`)を返す。
2. `access_token_store.get_internal_id_by_access_token(access_token)`で`internal_id`を
   解決する。`None`の場合は`status_code=404`(`error="unknown_access_token"`、無効・
   失効済みトークンでの再発行要求。settings.html側は再発行後に旧URLを再度開くユーザーが
   想定されるため、不正アクセスというより「既に新URLをブックマークし直すべき」ケースが
   主と想定する)。
3. 解決した`internal_id`で`handle_reissue_request()`を呼ぶ。
   `access_url_reissue_handler.ReissueRequestRejected`が送出された場合
   (メールアドレス形式不正)は捕捉し、`status_code=400`(`error="invalid_email"`)を返す
   (stripe_webhook.pyの`main()`がステータスコード別にtry/exceptせず戻り値で分岐する
   のとは異なり、本関数は`handle_reissue_request()`が例外ベースの契約のため、例外→
   戻り値への変換をエントリポイント側で行う唯一の箇所とする)。
4. 成功時は`status_code=200`、`result`に`ReissueRequestResult`をそのまま格納する。

`new_email`が`None`・空文字列・空白のみのいずれの場合も、`handle_reissue_request()`に
そのまま転送する(「変更なし」の判定自体は処理本体側の既存ロジックに委ね、エントリポイント
側では分岐しない)。

## 3. レスポンス本文の扱い

本ventureの他のHTTPエントリポイント(`stripe_webhook.main()`・`cloud_function_send_trial_
end_emails.main()`)はいずれも成功時`"OK", 200`のような最小限の文字列を返すのみで、
JSON本文を組み立てていない。本エンドポイントも同じ方針を踏襲し、`new_access_url`や
`destination_email`をレスポンス本文に含めない(再発行後の新URLはメール送信でのみ本人に
届ける、既存の「アクセスURLはメールでのみ伝える」運用方針との整合。レスポンス本文に新URLを
含めてしまうと、ブラウザの開発者ツール等から新URLが閲覧者以外に漏洩する経路が増える)。

- 成功時: `"OK", 200`
- `missing_access_token`/`invalid_email`: `(error文字列), 400`
- `unknown_access_token`: `(error文字列), 404`

settings.html側(JS不使用のモックアップ)は、送信後の画面遷移で成功・失敗を区別する手段を
持たないため、実装時は「送信後は常に『メールをご確認ください』という案内画面に遷移させ、
エラー時の詳細はサーバーログでのみ確認する」という割り切りを採用する(他ventureのWeb
フォームが取る「エラー時もユーザーには一般的な案内のみ見せる」方針と同じ)。

## 4. プロトタイプ実装方針(次回以降)

- `prototype/access_url_reissue_handler.py`に`ReissueHttpResult`・
  `receive_reissue_request()`を追加する(`handle_reissue_request()`の直後に配置、既存の
  関数・クラスは変更しない)。
- Cloud FunctionsのHTTPエントリポイント`main(request)`は、`stripe_webhook.main()`と同様に
  実リクエストオブジェクトからの値取り出し配線のみを行う。`access_token`はURLパス
  (`request.path`から`/f/{token}`相当を切り出す、あるいはクエリパラメータ)、`new_email`は
  `request.form.get("new_email")`を想定する(具体的な取り出し方はWebフォーム側のルーティング
  実装〈承認待ち事項〉確定後に決める)。
- テストは`test_access_url_reissue_handler.py`に`ReceiveReissueRequestTest`クラスを新設し、
  最低限以下をカバーする想定。
  - 正常系: 有効な`access_token`→200・`result.internal_id`が解決した`internal_id`と一致。
  - `access_token`欠落→400・`missing_access_token`、`handle_reissue_request()`自体が
    呼ばれない(`email_store`に書き込みが発生しないことも確認)。
  - 無効な`access_token`→404・`unknown_access_token`。
  - 不正な`new_email`→400・`invalid_email`、かつアクセストークンが再発行されていないこと
    (`access_token_store`の値が変化していないこと)を確認する(`ReissueRequestRejected`が
    `handle_reissue_request()`内でトークン発行前に送出される既存の順序〈フェーズ135〉を
    エントリポイント側でも壊していないことの確認)。

## 残課題

- 実際のWebフォームのルーティング実装(`/f/{accessToken}`というパスをどのCloud
  Functions/Hostingで受けるか)自体は、本venture全体の稼働に必須の前提である実Firestore
  接続・実ドメイン確定と同じ、オーナー承認待ち事項の範囲内のため未着手のまま残す。
- `receive_reissue_request()`・`main(request)`自体のコード実装は次回以降に行う(本フェーズは
  設計のみ)。
