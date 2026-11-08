# event.idべき等性Store(processed_stripe_events)の実Firestore接続アダプタ設計

## 1. 背景

stripe-event-idempotency-design.md(フェーズ151)5節「残課題」は、`StripeEventIdStoreProtocol`
(`has_processed`/`mark_processed`、stripe_webhook.py 933〜954行目)の検証用実装として
`InMemoryStripeEventIdStore`のみを実装し、「実Firestore接続(`processed_stripe_events`
コレクション実装)は、実Stripe/実GCPプロジェクト接続後(オーナー承認待ち)の課題として残る」
としていた。

しかし、kura-pashaのstripe-event-id-store-firestore-adapter-design.md(フェーズ290)が
line-webhook-event-id-store-firestore-adapter-design.md(フェーズ288)・
linking-code-store-firestore-adapter-design.mdの前例を踏まえて明確化した通り、本venture
(course-set-pasha)のFirestoreアダプタも実GCPプロジェクト・実SDKへ接続しない純粋なPython
コードとして実装可能(`collection(name).document(id)`が`get()`/`set(data)`を持つSnapshotを
返す、という最小インターフェースさえ満たせば実SDKでもテスト用フェイクでも差し替え可能な設計)
である。フェーズ151時点での「残課題」判定は、結合実装フェーズ(実GCP接続)とアダプタの
机上実装そのものを区別せずに書かれた陳腐化記載だったため、本ドキュメントで是正し、
kura-pasha版(フェーズ290)と同型の設計をそのまま横展開する(kura-pasha版README次回候補
「aircon-pasha・course-set-pasha・forklift-pasha・event-komiguai-pashaへの横展開」の
2件目に対応)。

## 2. 設計方針(kura-pasha版を踏襲、venture固有の差異なし)

- **コレクション名**: `processed_stripe_events`(新規)。ドキュメントIDを`event_id`とし、
  `has_processed()`/`mark_processed()`のみがProtocolの全メソッドであり、範囲クエリ・
  `items()`相当は不要。
- **フィールド**: `processed_at`(`mark_processed`時刻)のみ。TTL付き自動削除は
  stripe-event-idempotency-design.md 5節で元々「将来検討課題」としていた通り本フェーズの
  対象外とする(kura-pashaフェーズ続き291がWebSearchで裏取りした「Stripeイベントの再送は
  通常72時間前後〈最大11回前後の指数バックオフ〉で収まる」という前提を本ventureにも適用する。
  一次情報〈docs.stripe.com〉での確認は未達のままだが、判断自体〈TTL見送り〉は変更しない)。
- **`has_processed()`**: ドキュメントの`exists`をそのまま返す。
- **`mark_processed()`**: `processed_at`を`set()`で書き込む(既存ドキュメントの上書きも許容、
  `event_id`は冪等キーのため再呼び出しでも問題ない)。
- **読み取り失敗時のフォールバック**: 本venture既存の各アダプタ(firestore_user_profile_
  adapter.py等)・kura-pasha版と同じ判断により、`get()`が例外を投げた場合(ネットワーク
  エラー・権限エラー等)は「未処理」(`False`)に倒す(安全側: 重複排除ストアが一時的に
  読めない場合は従来通り処理を続行させ、Stripe側の再送を正常にハンドルする)。
  `mark_processed()`側の書き込み失敗は本設計では吸収しない(呼び出し元
  `receive_stripe_webhook()`が例外伝播を許容する前提)。

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

- **`firestore.rules`の更新**: 本venture既存4コレクション(usage_counter・user_profile・
  stripe_customer_index・pending_links)はいずれもクライアント直接アクセスを一切想定しない
  deny-all設計。新規コレクション`processed_stripe_events`もCloud Functions(Admin SDK)
  経由のサーバーサイド処理専用であり同じ理由でdeny-allとするため、`firestore.rules`に
  本コレクションのdeny-allルールを追加した(本フェーズで実施、5コレクション目)。
- **複合インデックス**: `has_processed()`/`mark_processed()`いずれもドキュメントID
  (`event_id`)単位の直接アクセスのみで範囲クエリ・ソートを伴わないため、
  firestore-composite-index-plan.mdの対象外(kura-pasha版と同じ理由)。同ドキュメントの
  コレクション数の記載を5コレクション構成に合わせて更新した。
- **依存ライブラリ**: 他アダプタと同じく`google-cloud-firestore`を想定(tech-stack.md記載の
  選定と一致)。`firestore_client`をコンストラクタ注入する形とし、実SDK未接続の間は
  `InMemoryStripeEventIdStore`を使い続ける(本クラスは結合実装時の差し替え先として先行実装
  するのみ)。

## 4. 残課題・次回候補

- 実Firestoreプロジェクト・GCPアカウントの開設自体はpending-approval.md記載の承認待ちであり、
  本クラスを実際に`receive_stripe_webhook()`へ注入する結合作業は承認後に行う。
- `processed_stripe_events`コレクションへのTTLポリシー導入は、実運用でのドキュメント蓄積量が
  問題になった場合に改めて検討する。
- aircon-pasha・forklift-pasha・event-komiguai-pasha側のStripe event.idべき等性対策
  (それぞれ既にInMemory実装は完了済み)についても、実Firestoreアダプタが未着手であれば、
  それぞれが「7venture中最も更新が止まっていたventure」として選ばれた回に本ドキュメントと
  同型の対応を横展開できる(kura-pasha版README次回候補の残り)。

最終更新: 2026-11-08 21:00 UTC(新規作成。stripe-event-idempotency-design.md 5節の
「実Firestore接続は実GCPプロジェクト接続後」という記載が、kura-pashaのフェーズ290で確立した
「アダプタの机上実装と結合実装フェーズは区別できる」という方針に照らすと陳腐化していたことを
発見・是正し、kura-pasha版を横展開して先行実装した)。
