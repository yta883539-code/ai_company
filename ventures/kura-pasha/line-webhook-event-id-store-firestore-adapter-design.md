# webhookEventId処理済みStore(line_webhook_event_ids)の実Firestore接続アダプタ設計

## 1. 背景

line-webhook-event-id-idempotency-design.md(フェーズ286)・同4節「TTL設計」(フェーズ287)は、
`LineWebhookEventIdStoreProtocol`(`has_processed`/`mark_processed`、
cloud_function_webhook.py 1884〜1897行目)の検証用実装として`InMemoryLineWebhookEventIdStore`
のみを実装し、「実Firestoreアダプタでは`expires_at`フィールド+Firestoreネイティブ
TTLポリシーで同等の挙動を実現する想定」(design doc 4-1節)を次回候補として残していた。
本ドキュメントはその残課題を扱う。

linking-code-store-firestore-adapter-design.md(フェーズ213・250)・invite-code-store-
firestore-adapter-design.md(フェーズ214・250)が確立した通り、本venture(kura-pasha)の
Firestoreアダプタは実GCPプロジェクト・実SDKへ接続しない純粋なPythonコードとして実装可能
(「最小インターフェース」〈`collection(name).document(id)`が`get()`/`set(data)`/
`delete()`を持つSnapshotを返す〉さえ満たせば実SDKでもテスト用フェイクでも差し替え可能な
設計)であるため、本フェーズでも結合実装フェーズを待たずに実コード化する。

## 2. 設計方針

- **コレクション名**: `line_webhook_event_ids`(新規)。ドキュメントIDを`webhook_event_id`
  とし、他コレクション(`pending_links`等)と同じくキー単位の読み書きのみで、範囲クエリ・
  `items()`相当は不要(`has_processed()`/`mark_processed()`のみがProtocolの全メソッド)。
- **フィールド**: `processed_at`(`mark_processed`時刻)・`expires_at`
  (= `processed_at` + `ttl_seconds`、デフォルトは`DEFAULT_LINE_WEBHOOK_EVENT_ID_TTL_SECONDS`
  = 7日)の2フィールドのみ。`expires_at`をFirestoreネイティブの「TTLポリシー」機能の対象
  フィールドに設定することで、ドキュメントの自動削除をFirestore側に委譲する想定
  (design doc 4-1節と同じ方針)。
- **`has_processed()`**: ドキュメントの`exists`をそのまま返す。TTL超過後もFirestore側の
  実削除には数時間程度のタイムラグが生じうるが、`InMemoryLineWebhookEventIdStore`の
  コメント(cloud_function_webhook.py 1917〜1926行目)の通り、このタイムラグは
  「再送が来た時点で記録さえ残っていれば重複は防げる」という安全側にしか作用しないため、
  アプリケーション側で`expires_at`を読んで追加の期限判定を行う必要はない
  (= `InMemoryLineWebhookEventIdStore`のような`del`による能動的な失効処理は実装しない。
  Firestore側のTTLポリシーが実体を担う)。
- **`mark_processed()`**: `processed_at`・`expires_at`の2フィールドを`set()`で書き込む
  (既存ドキュメントの上書きも許容、`webhook_event_id`は冪等キーのため再呼び出しでも
  問題ない)。
- **読み取り失敗時のフォールバック**: `FirestorePendingLinkStore`(フェーズ213)と同じ
  判断により、`get()`が例外を投げた場合(ネットワークエラー・権限エラー等)は
  「未処理」(`False`)に倒す。安全側(重複排除のためのストアが一時的に読めない場合は
  従来通り処理を続行させ、LINE側の再送を正常にハンドルする)と判断した。
  `mark_processed()`側の書き込み失敗は本設計では吸収しない(他アダプタと同じく
  呼び出し元〈`receive_webhook()`〉が例外伝播を許容する前提、design doc 3節と整合)。

```python
class FirestoreLineWebhookEventIdStore:
    """LineWebhookEventIdStoreProtocol(line_webhook_event_ids/{webhookEventId}向け)の
    実Firestore接続実装。InMemoryLineWebhookEventIdStoreと異なり、TTL超過の能動的な
    失効処理はFirestoreネイティブのTTLポリシー(expires_atフィールド対象)に委譲する。
    """

    def __init__(
        self,
        firestore_client,
        *,
        ttl_seconds: int = DEFAULT_LINE_WEBHOOK_EVENT_ID_TTL_SECONDS,
    ) -> None:
        self._collection = firestore_client.collection("line_webhook_event_ids")
        self._ttl_seconds = ttl_seconds

    def has_processed(
        self, webhook_event_id: str, *, now: Optional[datetime] = None
    ) -> bool:
        try:
            snapshot = self._collection.document(webhook_event_id).get()
        except Exception:
            return False
        return bool(snapshot.exists)

    def mark_processed(
        self, webhook_event_id: str, *, now: Optional[datetime] = None
    ) -> None:
        resolved_now = now if now is not None else datetime.now(timezone.utc)
        self._collection.document(webhook_event_id).set(
            {
                "processed_at": resolved_now,
                "expires_at": resolved_now + timedelta(seconds=self._ttl_seconds),
            }
        )
```

## 3. 検討事項

- **`now`引数の扱い**: Protocol上は`has_processed`/`mark_processed`双方が`now`引数を
  取るが(フェーズ287、テスト時刻注入用)、`has_processed()`はFirestore側TTLポリシーに
  期限判定を委譲するため`now`を実際には使わない(設計方針参照)。`mark_processed()`は
  `expires_at`算出に使う。インターフェース互換のため両メソッドとも引数自体は受け取る。
- **`firestore.rules`の更新**: 本venture全6コレクション(craftsman_workshop・
  stripe_customer_index・user_profile・pending_workshop_invites・pending_links・
  usage_counter)はいずれもクライアント直接アクセスを一切想定しないdeny-all設計
  (firestore-security-rules-draft.md)。新規コレクション`line_webhook_event_ids`も
  Cloud Functions(Admin SDK)経由のサーバーサイド処理専用であり同じ理由でdeny-allと
  するため、`firestore.rules`に本コレクションのdeny-allルールを追加した
  (本フェーズで実施、7コレクション目)。
- **複合インデックス**: `has_processed()`/`mark_processed()`いずれもドキュメントID
  (`webhook_event_id`)単位の直接アクセスのみで範囲クエリ・ソートを伴わないため、
  firestore-composite-index-plan.mdの対象外(`usage_counter`と同じ理由)。同ドキュメントの
  コレクション数の記載を7コレモデルに合わせて更新した。
- **依存ライブラリ**: 他アダプタと同じく`google-cloud-firestore`を想定
  (tech-stack.md記載の選定と一致)。`firestore_client`をコンストラクタ注入する形とし、
  実SDK未接続の間は`InMemoryLineWebhookEventIdStore`を使い続ける(本クラスは結合実装時の
  差し替え先として先行実装するのみ)。

## 4. 残課題・次回候補

- 実Firestoreプロジェクト・GCPアカウントの開設自体はpending-approval.md記載
  (2026-10-23 19:00 UTC記載分、firestore-provider-adapter-design.md 4節参照)の承認待ちで
  あり、本クラスを実際に`dispatch_webhook_events()`/`receive_webhook()`へ注入する結合作業は
  承認後に行う。
- `line_webhook_event_ids`コレクションに対するFirestore側TTLポリシー(`expires_at`
  フィールド対象)の実際の設定も、結合実装フェーズでGCPコンソール/`gcloud`経由で行う
  (本ドキュメントは机上設計のみ)。
- aircon-pasha・course-set-pashaへのwebhookEventIdべき等性対策(TTL設計・Firestore
  アダプタ含む)の横展開は、それぞれが「7venture中最も更新が止まっていたventure」として
  選ばれた回に対応する(README.md次回候補、継続)。
