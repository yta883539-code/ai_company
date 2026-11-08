"""stripe-event-id-store-firestore-adapter-design.mdの設計を実コードに落としたもの
(kura-pashaフェーズ290版の横展開)。

実Firestoreプロジェクトへの接続自体はpending-approval.md記載の通りオーナー承認待ちのため、
本モジュールはgoogle-cloud-firestore SDKを直接importしない。既存の各アダプタ
(firestore_user_profile_adapter.py等)と同じ最小インターフェース(collection(name).
document(id)がget()/set(data)を持つドキュメント参照を返す)を前提にする。
"""

from __future__ import annotations

from datetime import datetime, timezone


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
        doc_ref = self._collection.document(event_id)
        doc_ref.set({"processed_at": datetime.now(timezone.utc)})
