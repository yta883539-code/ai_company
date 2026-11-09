"""idempotency-key-write-conflict-control-design.md(フェーズ67・68)の設計を実コードに
落としたもの。`idempotency_key_index/{idempotencyKey}`コレクションへのアクセスを
`IdempotencyKeyIndexStoreProtocol`として抽象化し、検証用の`InMemoryIdempotencyKeyIndexStore`
を本モジュールに、実Firestore接続向けの`FirestoreIdempotencyKeyIndexStore`は
firestore_idempotency_key_index_adapter.pyに分けて実装する(他ventureのInMemory/Firestore
アダプタ分割と同じ方針)。

design.md 3節の「存在しなければ作成、存在すれば失敗」という原子的操作を`reserve_or_get()`
として表現する。呼び出し側(form_submission_intake.py・inquiry_form_intake.py相当、
いずれも未結線)は、新規`draft_id`/`inquiry_id`をUUID4で生成した後に本メソッドを呼び、
返り値が自分が渡した`document_id`と一致すれば新規作成成功、異なれば既存の
`document_id`(先行リクエストが確保した値)を使う、という呼び出し契約になる。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


class AlreadyReservedError(Exception):
    """design.md 3節の「既存ドキュメントがあるためALREADY_EXISTSで失敗」に対応する、
    実装の都合に依存しない共通の例外型。InMemory実装・Firestoreアダプタのいずれも
    この例外は外に投げず、`reserve_or_get()`内部でキャッチして既存値の読み取りに
    フォールバックする(呼び出し側が意識する必要はない)。"""


@dataclass
class IdempotencyKeyIndexEntry:
    """`idempotency_key_index/{idempotencyKey}`ドキュメントの最小表現(design.md 3節・
    5節で確定済みのフィールドのみ)。"""

    collection: str  # "one_time_draft" | "inquiry"
    document_id: str
    created_at: datetime
    expire_at: Optional[datetime] = None


class IdempotencyKeyIndexStoreProtocol:
    """`idempotency_key_index`コレクションへのアクセスを抽象化するインターフェース。"""

    def reserve_or_get(
        self,
        idempotency_key: str,
        *,
        collection: str,
        document_id: str,
        created_at: datetime,
        expire_at: Optional[datetime] = None,
    ) -> str:
        """design.md 3節の手順2〜4を1メソッドに結線する。

        `idempotency_key_index/{idempotency_key}`が存在しなければ、渡された
        `collection`・`document_id`・`created_at`(・`expire_at`)で新規作成し、
        `document_id`をそのまま返す(=呼び出し側が本体ドキュメントの新規作成に進む)。
        既に存在する場合は新規作成をスキップし、既存ドキュメントの`document_id`を
        返す(=呼び出し側は新規作成した`document_id`を捨て、返り値を使う)。
        """
        raise NotImplementedError


class InMemoryIdempotencyKeyIndexStore:
    """検証用のインメモリ実装(実Firestore接続は実GCPプロジェクト作成後の課題)。

    CPythonのdictはGIL配下での単純な読み書きがアトミックに振る舞うため、本スタブの
    範囲では「存在しなければ作成」をif文1つで表現しても、design.md 3節が要求する
    排他性を検証目的では再現できる(実Firestore側の原子性保証そのものの検証ではない
    ことに注意)。
    """

    def __init__(self) -> None:
        self._entries: dict = {}

    def reserve_or_get(
        self,
        idempotency_key: str,
        *,
        collection: str,
        document_id: str,
        created_at: datetime,
        expire_at: Optional[datetime] = None,
    ) -> str:
        existing = self._entries.get(idempotency_key)
        if existing is not None:
            return existing.document_id
        self._entries[idempotency_key] = IdempotencyKeyIndexEntry(
            collection=collection,
            document_id=document_id,
            created_at=created_at,
            expire_at=expire_at,
        )
        return document_id
