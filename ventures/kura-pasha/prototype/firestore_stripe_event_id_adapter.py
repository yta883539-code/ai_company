"""stripe-event-id-store-firestore-adapter-design.mdの設計を実コードに落としたもの。
firestore_line_webhook_event_id_adapter.py(フェーズ288)と同型の方針を踏襲し、
google-cloud-firestore SDKを直接importしない(`firestore_client`に
`collection(name).document(id)`で取得したドキュメント参照が`get()`(`.exists`を持つ
Snapshotを返す)・`set(data)`を持てば実SDKでもテスト用フェイクでも差し替え可能)。

`InMemoryStripeEventIdStore`(stripe_webhook.py)と異なり、TTLは本フェーズの対象外
(design.md 2節: Stripeイベントの再送は通常数日以内に収まる実務上の前提があり、将来
必要になった場合はline_webhook_event_idsと同じexpires_at方式を横展開すればよい)。
"""

from __future__ import annotations

from datetime import datetime, timezone


class FirestoreStripeEventIdStore:
    """StripeEventIdStoreProtocol(processed_stripe_events/{eventId}向け)の
    実Firestore接続実装(design.md 2節)。
    """

    def __init__(self, firestore_client) -> None:
        self._collection = firestore_client.collection("processed_stripe_events")

    def has_processed(self, event_id: str) -> bool:
        try:
            snapshot = self._collection.document(event_id).get()
        except Exception:
            # ネットワークエラー・権限エラー等は「未処理」(False)に倒す(design.md 2節)。
            # 重複排除ストアが一時的に読めない場合でも、Stripe側の再送を正常にハンドル
            # できるよう処理続行を優先する安全側の判断。
            return False
        return bool(snapshot.exists)

    def mark_processed(self, event_id: str) -> None:
        self._collection.document(event_id).set(
            {"processed_at": datetime.now(timezone.utc)}
        )
