"""idempotency-key-write-conflict-control-design.md(フェーズ67・68)の設計を実コードに
落とした、`idempotency_key_index`コレクション向けの実Firestore接続実装。

kura-pasha/firestore_stripe_event_id_adapter.py等と同じ方針で、google-cloud-firestore
SDKを直接importしない(`firestore_client`に`collection(name).document(id)`で取得した
ドキュメント参照が、`create(data)`〈既存ドキュメントがあれば何らかの例外を送出する〉・
`get()`〈`.exists`・`.to_dict()`を持つSnapshotを返す〉を満たせば、実SDKでもテスト用
フェイクでも差し替え可能)。

design.md 3節が前提とする「`create()`相当、既存ドキュメントがあれば`ALREADY_EXISTS`で
失敗する」という操作は、実SDKでは`google.api_core.exceptions.AlreadyExists`を送出する。
本アダプタは実SDKを直接importしない方針を優先し、`create()`が送出する例外の型を区別せず
`Exception`全体を「作成失敗→既存ドキュメントの読み取りにフォールバック」として扱う。
これにより、本来は`AlreadyExists`以外(ネットワークエラー・権限エラー等)と区別されるべき
失敗も同じ分岐に倒れてしまう点は、実Firestore接続後(オーナー承認待ち)に
`google.api_core.exceptions.AlreadyExists`を明示的にimportして区別する詳細化が必要な
残課題として明記する。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from idempotency_key_index_store import AlreadyReservedError


class FirestoreIdempotencyKeyIndexStore:
    """IdempotencyKeyIndexStoreProtocol(idempotency_key_index/{idempotencyKey}向け)の
    実Firestore接続実装(design.md 3節)。
    """

    def __init__(self, firestore_client) -> None:
        self._collection = firestore_client.collection("idempotency_key_index")

    def reserve_or_get(
        self,
        idempotency_key: str,
        *,
        collection: str,
        document_id: str,
        created_at: datetime,
        expire_at: Optional[datetime] = None,
    ) -> str:
        doc_ref = self._collection.document(idempotency_key)
        data = {
            "collection": collection,
            "documentId": document_id,
            "createdAt": created_at,
        }
        if expire_at is not None:
            data["expireAt"] = expire_at

        try:
            doc_ref.create(data)
        except Exception:
            # design.md 3節手順4: 既存ドキュメントから`documentId`を読み取り、
            # 新規作成をスキップして既存値を返す。読み取り自体も失敗する場合は、
            # 上記docstring記載の残課題のとおり区別せず`AlreadyReservedError`を送出する
            # (呼び出し側は「安全にこの書き込みを進められない」ことだけが分かればよい)。
            try:
                snapshot = doc_ref.get()
            except Exception as read_error:
                raise AlreadyReservedError(
                    f"idempotency_key_index/{idempotency_key}: create()失敗後のget()も失敗"
                ) from read_error
            if not snapshot.exists:
                raise AlreadyReservedError(
                    f"idempotency_key_index/{idempotency_key}: create()失敗だがget()は未発見"
                )
            existing = snapshot.to_dict() or {}
            existing_document_id = existing.get("documentId")
            if existing_document_id is None:
                raise AlreadyReservedError(
                    f"idempotency_key_index/{idempotency_key}: documentIdフィールド欠落"
                )
            return existing_document_id

        return document_id
