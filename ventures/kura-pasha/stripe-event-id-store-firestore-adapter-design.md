# event.idべき等性Store(processed_stripe_events)の実Firestore接続アダプタ設計

## 1. 背景

stripe-event-idempotency-design.md(フェーズ77)5節「残課題」は、`StripeEventIdStoreProtocol`
(`has_processed`/`mark_processed`、stripe_webhook.py 117〜139行目)の検証用実装として
`InMemoryStripeEventIdStore`のみを実装し、「実Firestore接続(`processed_stripe_events`
コレクション実装)は、実Stripe/実GCPプロジェクト接続後(オーナー承認待ち)の課題として残る」
としていた。

しかし、line-webhook-event-id-store-firestore-adapter-design.md(フェーズ288)が
linking-code-store-firestore-adapter-design.md(フェーズ213・250)の前例を踏まえて明確化した
通り、本venture(kura-pasha)のFirestoreアダプタは実GCPプロジェクト・実SDKへ接続しない純粋な
Pythonコードとして実装可能(`collection(name).document(id)`が`get()`/`set(data)`を持つ
Snapshotを返す、という最小インターフェースさえ満たせば実SDKでもテスト用フェイクでも差し替え
可能な設計)である。フェーズ77時点での「残課題」判定は、結合実装フェーズ(実GCP接続)と
アダプタの机上実装そのものを区別せずに書かれた陳腐化記載だったため、本ドキュメントで是正し
先行実装する。

## 2. 設計方針

- **コレクション名**: `processed_stripe_events`(新規、design 3節の想定通り)。ドキュメントIDを
  `event_id`とし、`line_webhook_event_ids`と同じくキー単位の読み書きのみで、範囲クエリ・
  `items()`相当は不要(`has_processed()`/`mark_processed()`のみがProtocolの全メソッド)。
- **フィールド**: `processed_at`(`mark_processed`時刻)のみ。stripe-event-idempotency-design.md
  5節が「TTL付きコレクションでの自動削除も将来検討課題とするが、本フェーズの範囲外」と明記
  している通り、`line_webhook_event_ids`(フェーズ288)のような`expires_at`
  フィールド・TTLポリシーは本フェーズでは設けない(Stripeイベントの再送は通常数日以内に収まる
  実務上の前提〈Stripe公式ドキュメント〉があり、無期限保持でも実害が小さいため緊急度が低い。
  将来必要になった場合は`line_webhook_event_ids`と同じ`expires_at`方式を横展開すればよい)。
  本フェーズ(続き291)でこの前提をWebSearchで裏取りしたところ、本セッションのネットワーク
  制限により`docs.stripe.com`自体には直接アクセスできなかったものの、複数の独立した技術系
  解説記事(Webhook再送実装を扱うブログ・開発者向けガイド等)がStripeの再送スケジュールを
  「即時→5分→30分→1時間→2時間→4時間→8時間→16時間→24時間→48時間→72時間(最大11回)」
  または「指数バックオフで最大数時間〜72時間程度」と一致して説明しており、いずれも最終的な
  再送停止は数日(目安として72時間≒3日前後)以内に収まるという本設計の前提と整合する
  (Stripe公式ドキュメントでの一次確認は未達のため、将来`docs.stripe.com`へのアクセスが
  可能になった際に一次情報での確認を推奨する注記を残す。本TTL見送りの判断自体は変更しない)。
- **`has_processed()`**: ドキュメントの`exists`をそのまま返す。
- **`mark_processed()`**: `processed_at`を`set()`で書き込む(既存ドキュメントの上書きも許容、
  `event_id`は冪等キーのため再呼び出しでも問題ない)。
- **読み取り失敗時のフォールバック**: `FirestorePendingLinkStore`(フェーズ213)・
  `FirestoreLineWebhookEventIdStore`(フェーズ288)と同じ判断により、`get()`が例外を
  投げた場合(ネットワークエラー・権限エラー等)は「未処理」(`False`)に倒す。安全側
  (重複排除ストアが一時的に読めない場合は従来通り処理を続行させ、Stripe側の再送を正常に
  ハンドルする)と判断した。`mark_processed()`側の書き込み失敗は本設計では吸収しない
  (他アダプタと同じく呼び出し元〈`receive_stripe_webhook()`〉が例外伝播を許容する前提)。

```python
class FirestoreStripeEventIdStore:
    """StripeEventIdStoreProtocol(processed_stripe_events/{eventId}向け)の
    実Firestore接続実装。TTLは本フェーズの対象外(design 2節)。
    """

    def __init__(self, firestore_client) -> None:
        self._collection = firestore_client.collection("processed_stripe_events")

    def has_processed(self, event_id: str) -> bool:
        try:
            snapshot = self._collection.document(event_id).get()
        except Exception:
            return False
        return bool(snapshot.exists)

    def mark_processed(self, event_id: str) -> None:
        self._collection.document(event_id).set({"processed_at": datetime.now(timezone.utc)})
```

## 3. 検討事項

- **`firestore.rules`の更新**: 本venture全7コレモデル(craftsman_workshop・
  stripe_customer_index・user_profile・pending_workshop_invites・pending_links・
  usage_counter・line_webhook_event_ids)はいずれもクライアント直接アクセスを一切想定しない
  deny-all設計(firestore-security-rules-draft.md)。新規コレクション
  `processed_stripe_events`もCloud Functions(Admin SDK)経由のサーバーサイド処理専用であり
  同じ理由でdeny-allとするため、`firestore.rules`に本コレクションのdeny-allルールを追加した
  (本フェーズで実施、8コレクション目)。
- **複合インデックス**: `has_processed()`/`mark_processed()`いずれもドキュメントID
  (`event_id`)単位の直接アクセスのみで範囲クエリ・ソートを伴わないため、
  firestore-composite-index-plan.mdの対象外(`line_webhook_event_ids`と同じ理由)。同ドキュメントの
  コレクション数の記載を8コレモデルに合わせて更新した。
- **依存ライブラリ**: 他アダプタと同じく`google-cloud-firestore`を想定
  (tech-stack.md記載の選定と一致)。`firestore_client`をコンストラクタ注入する形とし、
  実SDK未接続の間は`InMemoryStripeEventIdStore`を使い続ける(本クラスは結合実装時の
  差し替え先として先行実装するのみ)。

## 4. 残課題・次回候補

- 実Firestoreプロジェクト・GCPアカウントの開設自体はpending-approval.md記載
  (2026-10-23 19:00 UTC記載分、firestore-provider-adapter-design.md 4節参照)の承認待ちで
  あり、本クラスを実際に`receive_stripe_webhook()`へ注入する結合作業は承認後に行う。
- `processed_stripe_events`コレクションへのTTLポリシー導入(2節で見送った`expires_at`方式の
  横展開)は、実運用でのドキュメント蓄積量が問題になった場合に改めて検討する。
- aircon-pasha・course-set-pasha・forklift-pasha・event-komiguai-pasha側のStripe event.id
  べき等性対策(それぞれ既にInMemory実装は完了済み)についても、実Firestoreアダプタが
  未着手であれば、それぞれが「7venture中最も更新が止まっていたventure」として選ばれた回に
  本ドキュメントと同型の対応を横展開できる(README.md次回候補)。

最終更新: 2026-11-08 11:00 UTC(新規作成。stripe-event-idempotency-design.md 5節の
「実Firestore接続は実GCPプロジェクト接続後」という記載が、line-webhook-event-id-store-
firestore-adapter-design.md〈フェーズ288〉で確立した「アダプタの机上実装と結合実装フェーズは
区別できる」という方針に照らすと陳腐化していたことを発見・是正し、先行実装した)。

追記: 2026-11-08 18:00 UTC(フェーズ続き291: 2節のTTL見送り判断の前提
「Stripeイベントの再送は通常数日以内に収まる」をWebSearchで裏取りし、複数の独立した
技術系解説記事による一致した説明(72時間程度・最大11回前後の指数バックオフ)で整合を確認。
docs.stripe.comへの一次情報アクセスは本セッションのネットワーク制限により未達のため、
その旨を注記として残した。判断自体〈TTL見送り〉は変更なし。コード変更なし)。
