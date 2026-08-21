# Webhook本体のHTTPエントリポイント設計

作成日: 2026-08-21(フェーズ82)

webhook-event-dispatch-design.md「残課題」1点目だった「実際にHTTPリクエストボディ(JSON)を
パースして`events`配列を取り出す部分・`verify_line_signature()`との結線(署名検証失敗時は
`dispatch_webhook_events()`自体を呼ばない)」に対応する。フェーズ81時点では
`verify_line_signature()`(署名検証)と`dispatch_webhook_events()`(イベント種別振り分け)が
それぞれ単体で存在するのみで、両者を実際のHTTPリクエストボディ(bytes)から結ぶ
エントリポイント関数が未実装だった。

## 1. 方針: `receive_webhook()`

line-reservation-aiの`webhook_receiver()`(prototype/cloud_function_webhook.py)と同じ
位置づけの関数として、`receive_webhook(body, signature_header, channel_secret, **dispatch_kwargs)`
を追加した。line-reservation-ai版との違いは、line-reservation-ai側は`events`をあらかじめ
パース済みの引数として受け取る設計だったのに対し、本venture版は生のリクエストボディ
(bytes)自体を受け取り、関数内で`json.loads()`によるパースまで行う点(webhook-event-
dispatch-design.mdで名指しされていた「JSONパース」自体をここで解消するため)。

```python
def receive_webhook(
    body: bytes, signature_header, channel_secret, *,
    linking_store=None, reply_client=None, llm_call=None,
    form_link_provider=None, portal_link_provider=None,
    usage_counter=None, plan=None, month=None,
    first_generation_notice_store=None, gym_area_config_store=None,
    purge_throttle=None, rng=None, now=None,
) -> WebhookReceiverResult:
```

処理順序:

1. `verify_line_signature(body, signature_header, channel_secret)`が`False`なら、
   JSONパース・`dispatch_webhook_events()`のいずれも呼ばずに`status_code=401`を返す
   (不正なリクエストへの余計な処理を避ける、line-reservation-aiと同じ方針)。
2. 署名検証通過後、`body`を`json.loads()`でパースする。デコード・パースに失敗した場合は
   `status_code=400`(`error="invalid_json"`)を返す。
3. パース結果が`dict`かつ`events`キーが`list`であることを確認する。そうでない場合は
   `status_code=400`(`error="missing_events"`)を返す(LINE Platformからの実際の
   リクエストでは通常発生しないはずだが、エントリポイントとして不正な入力に対しても
   例外を外に漏らさない設計とする)。
4. 上記を通過した`events`をそのまま`dispatch_webhook_events()`に委譲し、
   `status_code=200`・`dispatch_result`にその戻り値を格納して返す。

`WebhookReceiverResult`(dataclass)は`status_code`・`dispatch_result`
(成功時のみ`DispatchResult`)・`error`(失敗時のみ理由コード文字列)の3フィールドとした。

## 2. プロトタイプ実装方針

- `cloud_function_webhook.py`に`WebhookReceiverResult`・`receive_webhook()`を追加した。
  既存の`verify_line_signature()`・`dispatch_webhook_events()`はいずれも変更しない
  (両者を結ぶ薄いラッパーとして追加する)。
- テストは`test_cloud_function_webhook.py`の`ReceiveWebhookTest`に追加し、
  (1)署名不正時は401かつdispatch自体が呼ばれない(reply_client.sentが空のまま)、
  (2)JSONとしてパースできないbodyは400・`error="invalid_json"`、
  (3)`events`キーが無いbodyは400・`error="missing_events"`、
  (4)正常なリクエストは200・`dispatch_result`にdispatch_webhook_events()相当の結果が
  格納される、の4ケースを最低限カバーした(テスト4件追加、course-set-pasha配下
  計176件パス)。

## 残課題

- (解消 2026-08-21 09:00 UTC・フェーズ83): 実際のCloud Functions(`functions_framework`)の
  リクエストオブジェクトから`body`(`request.get_data()`)・署名ヘッダ
  (`request.headers.get("X-Line-Signature")`)を取り出してこの関数に渡す薄い配線を、
  `main(request)`として実装した。`functions_framework`自体はインポートせず、
  `get_data()`・`headers.get(...)`という同じインターフェースにのみ依存する設計としたため、
  実パッケージのインストール・実デプロイなしに単体テスト可能にした
  (`_StubFlaskRequest`スタブでの5ケース、course-set-pasha配下計190件パス)。
  `channel_secret`は環境変数`LINE_CHANNEL_SECRET`から取得する設計とした。
  実LINE/実LLM/実Firestoreクライアントの組み立ては`get_runtime_dependencies()`に
  切り出し、現時点(オーナー承認待ち)では空辞書(全依存未接続)を返す実装とした。
- 実Cloud Functionsデプロイ自体(実GCPプロジェクト作成・実LINE公式アカウント接続)は、
  いずれもアカウント作成・外部サービス公開に該当しオーナー承認待ちのため未着手のまま残る。
- `channel_secret`の実際の値の取得・保管方法(Secret Manager等)、および
  `get_runtime_dependencies()`を実クライアントに差し替える実装自体は、上記デプロイ時の
  設計課題として別途残る。
