# Webhook本体のHTTPエントリポイント設計

作成日: 2026-08-23(フェーズ115)

follow-unfollow-event-handling-design.md「残課題」およびフェーズ114で解消した
`dispatch_webhook_events()`実装の先にある残課題、「実際のHTTPリクエスト(署名ヘッダ付き
JSONボディ)を受け取り、署名検証を通してから`dispatch_webhook_events()`へ渡す」という
入口部分に対応する。course-set-pashaの`receive-webhook-http-entry-point-design.md`
(フェーズ82・83)と同じ位置づけだが、本ventureはフェーズ114時点で`verify_line_signature()`
自体が未実装(course-set-pasha・line-reservation-aiには既に存在)だったため、本ドキュメントは
署名検証関数の新設からあわせて設計する。

## 1. 方針: `verify_line_signature()`

line-reservation-ai・course-set-pashaと同じ実装(Python標準ライブラリの`hmac`・`hashlib`・
`base64`のみで完結、外部認証・実チャネルシークレットは不要)をそのまま踏襲する。

```python
def verify_line_signature(body: bytes, signature_header: Optional[str], channel_secret: str) -> bool:
```

- `signature_header`が空(None・空文字列)の場合は即`False`。
- `hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()`を
  Base64エンコードした値と`signature_header`を`hmac.compare_digest()`で比較する
  (タイミング攻撃対策、他ventureと同じ)。
- 実際の`channel_secret`の値はLINE公式アカウント開設(アカウント作成、オーナー承認待ち)
  後に得られる値のため、検証ロジック自体はここで実装するが実運用の検証はその後になる。

## 2. 方針: `receive_webhook()`

course-set-pashaの`receive_webhook(body, signature_header, channel_secret, **dispatch_kwargs)`
と同じ設計とする。

```python
def receive_webhook(
    body: bytes, signature_header: Optional[str], channel_secret: str, *,
    reply_client=None, llm_call=None, profile_store=None, linking_store=None,
    form_link_provider=None, portal_link_provider=None, usage_counter=None,
    plan=None, month=None, now=None,
) -> WebhookReceiverResult:
```

処理順序:

1. `verify_line_signature(body, signature_header, channel_secret)`が`False`なら、
   JSONパース・`dispatch_webhook_events()`のいずれも呼ばずに`status_code=401`
   (`error="invalid_signature"`)を返す(不正なリクエストへの余計な処理を避ける)。
2. 署名検証通過後、`body`を`json.loads()`でパースする。デコード・パース失敗時は
   `status_code=400`(`error="invalid_json"`)。
3. パース結果が`dict`かつ`events`キーが`list`であることを確認する。そうでなければ
   `status_code=400`(`error="missing_events"`)(LINE Platformからの実リクエストでは
   通常発生しないが、入口として不正な入力に例外を漏らさない設計とする)。
4. 通過した`events`をそのまま`dispatch_webhook_events()`に委譲し、`status_code=200`・
   `dispatch_result`にその戻り値を格納して返す。他のキーワード引数はすべてそのまま
   `dispatch_webhook_events()`へ転送する。

`WebhookReceiverResult`(dataclass)は`status_code: int`・`dispatch_result: Optional[DispatchResult]`
(成功時のみ)・`error: Optional[str]`(失敗時のみ理由コード文字列)の3フィールドとする。

## 3. プロトタイプ実装方針

- `cloud_function_webhook.py`に`verify_line_signature()`・`WebhookReceiverResult`・
  `receive_webhook()`を追加する(`dispatch_webhook_events()`の直後、`_demo()`の直前に配置)。
  既存の`dispatch_webhook_events()`・`process_follow_event()`等は変更しない
  (それらを結ぶ薄い入口を追加するのみ)。
- テストは`test_cloud_function_webhook.py`に`VerifyLineSignatureTest`・`ReceiveWebhookTest`
  クラスを新設し、最低限以下をカバーする。
  - 署名検証: 正しい署名は`True`、誤った署名・署名ヘッダ欠落はいずれも`False`。
  - `receive_webhook()`: (1)署名不正時は401・`dispatch_webhook_events()`自体が
    呼ばれない(reply_clientに何も送信されない)、(2)JSONとして不正なbodyは400・
    `invalid_json`、(3)`events`キーが無い/list以外のbodyは400・`missing_events`、
    (4)正常な`follow`イベント入りリクエストは200・`dispatch_result.follow_results`に
    1件反映される、の4ケース。

## 残課題

- (解消済み 2026-08-23 21:00 UTC・フェーズ116: 実際のCloud Functions(`functions_framework`)の
  リクエストオブジェクトから`body`(`request.get_data()`)・署名ヘッダ
  (`request.headers.get("X-Line-Signature")`)を取り出して`receive_webhook()`に渡す
  `get_runtime_dependencies()`・`main(request)`(course-set-pashaフェーズ83相当)を
  prototype/cloud_function_webhook.pyに実装した。テスト5件(`MainEntryPointTest`)を追加、
  全121件パスを確認した)
- 実Cloud Functionsデプロイ自体(実GCPプロジェクト作成・実LINE公式アカウント接続)は、
  いずれもアカウント作成・外部サービス公開に該当しオーナー承認待ちのため未着手のまま残る。
- `channel_secret`の実際の値の取得・保管方法(Secret Manager等)は、上記デプロイ時の
  設計課題として別途残る。
