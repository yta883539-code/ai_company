"""line-webhook-event-id-store-firestore-adapter-design.md(フェーズ288)の設計を実コードに
落としたもの。firestore_linking_code_adapter.py(フェーズ213・250)と同型の方針を踏襲し、
google-cloud-firestore SDKを直接importしない(`firestore_client`に`collection(name)
.document(id)`で取得したドキュメント参照が`get()`(`.exists`・`.to_dict()`を持つ
Snapshotを返す)・`set(data)`を持てば実SDKでもテスト用フェイクでも差し替え可能)。

`InMemoryLineWebhookEventIdStore`(cloud_function_webhook.py)と異なり、TTL超過の能動的な
失効処理は実装しない。`expires_at`フィールドをFirestoreネイティブの「TTLポリシー」機能の
対象に設定することでドキュメントの自動削除をFirestore側に委譲する設計のため
(design.md 2節)。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

#: line-webhook-event-id-idempotency-design.md 4節で定義したデフォルト値
#: (cloud_function_webhook.pyのDEFAULT_LINE_WEBHOOK_EVENT_ID_TTL_SECONDSと同じ値だが、
#: 循環import回避のためここでは独立した定数として持つ)。
DEFAULT_LINE_WEBHOOK_EVENT_ID_TTL_SECONDS = 7 * 24 * 60 * 60


class FirestoreLineWebhookEventIdStore:
    """LineWebhookEventIdStoreProtocol(line_webhook_event_ids/{webhookEventId}向け)の
    実Firestore接続実装(design.md 2節)。
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
            # ネットワークエラー・権限エラー等は「未処理」(False)に倒す(design.md 2節)。
            # 重複排除ストアが一時的に読めない場合でも、LINE側の再送を正常にハンドル
            # できるよう処理続行を優先する安全側の判断。
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
