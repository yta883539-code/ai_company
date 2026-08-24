# Stripe Webhook Cloud Functionsエントリポイント設計

stripe-webhook-http-entry-point-design.md「残課題」1点目だった、`receive_stripe_webhook()`を
実Cloud Functionsのリクエストオブジェクト(`functions_framework`が渡すFlask Request互換
インターフェース)に接続する`main(request)`本体の設計・実装。LINE版
`cloud_function_webhook.main()`(フェーズ83)と対称の構成とする。

## 1. 方針

- `cloud_function_webhook.py`とは別ファイル(`stripe_webhook.py`)に閉じたまま、LINE版の
  `main(request)`と同じ薄い配線パターンを踏襲する。`functions_framework`自体は
  インポートせず、`request.get_data()`・`request.headers.get(...)`という
  インターフェースにのみ依存する(ローカルテストでは同じインターフェースを持つ
  軽量スタブで代替可能)。
- 署名ヘッダ名は`Stripe-Signature`(Stripe公式仕様)。
- `webhook_secret`は環境変数`STRIPE_WEBHOOK_SECRET`から取得する(残課題1点目で
  想定されていた名前をそのまま採用)。未設定時は空文字列を渡し、
  `verify_stripe_signature()`側の「不正な形式」判定により401となる
  (LINE版`main()`の`LINE_CHANNEL_SECRET`未設定時と同じ安全側の挙動)。

## 2. `get_stripe_runtime_dependencies()`

`receive_stripe_webhook()`が要求する`store`・`resolve_user_id`は(LINE版の
`reply_client`/`llm_call`と異なり)`None`を許容しない必須の依存関係のため、
LINE版のように空辞書`{}`を返すだけでは足りない。以下の暫定実装とする。

- `store`: `InMemoryProfileDeletionCandidateStore()`(deletion_candidate.py)を
  返す。実Firestore接続は実GCPプロジェクト作成(オーナー承認待ち、
  pending-approval.md参照)後の課題として別途残る。**プロセス起動ごとに初期化される
  ため、実Cloud Functions環境では呼び出しをまたいで削除候補フラグが保持されない
  点に注意。実運用にはFirestore版ストアへの差し替えが必須**(LINE版の
  `get_runtime_dependencies()`と同様、差し替えのみで`main()`・
  `receive_stripe_webhook()`双方を変更せず接続できる設計)。
- `resolve_user_id`: `stripe-webhook-event-dispatch-design.md`で名指しされていた
  未解決事項(`stripe_customer_id → user_id`変換の実装自体)がまだ本venture内で
  未着手のため、暫定的に常に`None`を返す関数とする。`dispatch_stripe_event()`は
  `resolve_user_id`が`None`を返すケースを`unresolved_customers`として安全に扱い
  200を返す設計(フェーズ94で確認済み)のため、この暫定実装でもStripe側の再送
  ループは発生しない。実装本体(申込フォーム提出フローのどこで
  `stripe_customer_id`を`user_profile`に書き込むか)は引き続き別課題として残す。

## 3. `main(request)`

```
body = request.get_data()
signature_header = request.headers.get("Stripe-Signature")
webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

result = receive_stripe_webhook(
    body, signature_header, webhook_secret, **get_stripe_runtime_dependencies()
)

if result.status_code == 200:
    return "OK", 200
return (result.error or "error"), result.status_code
```

LINE版`main()`と同じ形の戻り値((body, status_code)のタプル)とする。

## 残課題

- (解消済み 2026-08-24 16:00 UTC: 本節がフェーズ96時点の記述のまま更新されておらず、
  実際には`resolve_user_id`の実装本体はフェーズ97・`stripe-customer-id-linking-design.md`/
  `make_resolve_user_id()`で既に対応済みだったことを確認した(README「次にやること」
  2026-08-23 02:00 UTC・フェーズ97の記載を参照)。`prototype/stripe_webhook.py`の
  `get_stripe_runtime_dependencies()`は`InMemoryUserProfileStore()`を1つ生成して
  `resolve_user_id`と共有し、`checkout.session.completed`で書き込んだ紐付けを同一プロセス内の
  `customer.subscription.*`解決で読める設計に更新済み(常時`None`を返す暫定実装ではない)。
  本節はドキュメントの記載更新漏れによる見かけ上の残課題だった。)
- `store`・`user_profile_store`をFirestore版に差し替える作業は、実GCPプロジェクト作成
  (オーナー承認待ち)後の課題として引き続き残る(プロセス起動ごとに初期化されるため、
  実Cloud Functions環境では呼び出しをまたいで削除候補フラグ・紐付けが保持されない)。
- `webhook_secret`実際の値の取得・保管方法(Secret Manager等)も同様に実Stripeアカウント
  接続(オーナー承認待ち)後の課題として残る。
