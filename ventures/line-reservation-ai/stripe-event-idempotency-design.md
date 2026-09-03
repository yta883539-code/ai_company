# Stripeイベント重複配信対策(event.idによるべき等性チェック)の設計

作成日: 2026-09-03(フェーズ続き179)

stripe-webhook-signature-verification-design.md「残課題」に残っていた「Stripeイベントの
重複配信対策(`event.id`によるべき等性チェック)」に対応する。aircon-pashaがフェーズ177・
course-set-pashaがフェーズ151で先行実装した設計(stripe-event-idempotency-design.md、
両ventureとも同一内容)をそのまま横展開する(べき等性チェック自体はStripeのWebhook配信
仕様〈同一イベントが複数回配信されうる〉に基づく汎用ロジックであり、venture固有の差異は
無い)。

## 1. 本venture固有の事情(組み込み位置の違い)

aircon-pasha・course-set-pashaは、署名検証〜イベント種別ディスパッチ〜各ハンドラ呼び出しを
一本につなぐ`receive_stripe_webhook()`という統合エントリポイントを既に持っており、べき等性
チェックはそのエントリポイント内(パース直後・ハンドラ呼び出し前)に組み込まれている。

本ventureはstripe-webhook-signature-verification-design.md「残課題」に記載のとおり、
`receive_stripe_webhook()`相当の統合エントリポイント(署名検証〜`route_stripe_event()`〜
`handle_checkout_session_completed()`等の実ハンドラ呼び出しを結ぶ層)がまだ存在しない。
そのため今回は、現時点で唯一の共通経路である`route_stripe_event()`(stripe-webhook-event-
dispatch-design.md)自体にべき等性チェックを組み込む。将来`receive_stripe_webhook()`相当を
新設する際は、`route_stripe_event()`が既にべき等性チェック済みのルートを返す前提で、
そのまま`store_id`が入っている場合のみ後続ハンドラを呼び出す配線にすればよい。

## 2. インターフェース

aircon-pasha/course-set-pashaと同一の`StripeEventIdStoreProtocol`・
`InMemoryStripeEventIdStore`を`prototype/stripe_webhook.py`に新設した。

```python
class StripeEventIdStoreProtocol:
    def has_processed(self, event_id: str) -> bool: ...
    def mark_processed(self, event_id: str) -> None: ...

class InMemoryStripeEventIdStore:
    ...  # setベースのインメモリ実装。実Firestore接続は実GCPプロジェクト作成後の課題
```

## 3. `route_stripe_event()`への組み込み

- 新規キーワード引数`event_id_store: Optional[StripeEventIdStoreProtocol] = None`を追加。
  省略時(`None`)は従来通りべき等性チェックを行わない(既存呼び出し経路への後方互換)。
- `event.get("id")`が文字列で、かつ`event_id_store.has_processed(event_id)`が`True`の
  場合、`resolve_store_id_by_customer()`の呼び出しを含む一切の解決処理を行わず
  `StripeEventRoute(event_type=event_type, duplicate=True)`を即座に返す(副作用ゼロ)。
- 重複でなかった場合は従来通りルート解決を行い、`ignored`(対象外イベント種別)も含めて
  結果を返す直前に`event_id_store.mark_processed(event_id)`を呼ぶ。対象外イベント種別も
  処理済みとして記録するのは、aircon-pashaの`receive_stripe_webhook()`と同じ方針
  (Stripe側の再送ループを避けるため、対象外イベントも一度見たら処理済みとして扱う)。
- `id`が欠落・非文字列の場合はチェック自体をスキップし従来通り処理する(安全側、
  他ventureと同じ方針)。

`StripeEventRoute`に`duplicate: bool = False`・`event_id: Optional[str] = None`の2
フィールドを追加した。

## 4. テスト

`prototype/test_stripe_webhook.py`に`RouteStripeEventIdempotencyTest`を新設し、以下を
確認した:

1. 初回配信は通常通り解決され、`event_id_store`に処理済みとして記録される
2. 同一`event.id`の2回目配信は`duplicate=True`となり`store_id`は`None`のまま
   (`resolve_store_id_by_customer`が呼ばれないことを`_raise_if_called`で確認)
3. 対象外イベント種別(`ignored=True`)も処理済みとして記録され、2回目配信は`duplicate=True`
4. `event.id`が欠落している場合はチェックがスキップされ、同一内容のイベントでも毎回
   通常通り解決される
5. `event_id_store`省略時(`None`)は従来通りの挙動(`duplicate`は常に`False`)

venture全体603件全件(python3 -m unittest discover -p "test_*.py")パス・schema検証25件
パスを確認した(テスト6件追加、603件 = 既存597件 + 新規6件)。

## 残課題

- (解消済み 2026-09-03 16:00 UTC・フェーズ続き183: `route_stripe_event()`を実際に
  `handle_subscription_activated()`・`handle_payment_succeeded()`・
  `handle_payment_failed()`へつなぐ統合エントリポイント`receive_stripe_webhook()`を
  stripe-webhook-http-entry-point-design.mdで設計し、
  `prototype/stripe_webhook_entry_point.py`として実装した。`route_stripe_event()`が
  返す`duplicate=True`ルートを見てハンドラ呼び出しをスキップする配線も含めて対応済み。
  詳細は同ドキュメント参照)
- `webhook_secret`の実際の値の取得・保管方法(Secret Manager等)は、実Stripeアカウント接続
  (オーナー承認待ち)後の設計課題として別途残る(署名検証設計から持ち越しの既存課題)。
- 実際のCloud Functions HTTPエントリポイント(`main(request)`相当、`request.get_data()`・
  `request.headers.get("Stripe-Signature")`からの取り出し配線)は、
  stripe-webhook-http-entry-point-design.md「今後の課題」のとおり本venture向けに
  まだ新規作成されていない(次回以降の課題)。
