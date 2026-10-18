"""firestore-provider-adapter-design.md 19節(UsageCounterProtocolのget_count/increment
グループ)の設計を実コードに落としたもの。

実Firestoreプロジェクトへの接続自体はpending-approval.md記載の通りオーナー承認待ちのため、
本モジュールはgoogle-cloud-firestore SDKを直接importしない。コンストラクタに渡す
`firestore_client`は、`collection(name).document(id)`で取得したドキュメント参照が
`get()`(DocumentSnapshotを返す。`.exists`・`.to_dict()`を持つ)・`set(data)`を持ち、
`firestore_client.transaction()`がトランザクションオブジェクト(`get(doc_ref)`・
`set(doc_ref, data)`・`commit()`を持つ)を返す、という19.2節で前提にしたのと同じ
最小インターフェースを満たせばよい(実SDKでもテスト用フェイクでも差し替え可能)。
"""

from __future__ import annotations


class TransactionConflict(Exception):
    """トランザクションがコミット時に競合を検出した場合に送出される(実SDKでは
    `google.api_core.exceptions.Aborted`相当)。`firestore_client.transaction()`が
    返すオブジェクトの`commit()`がこの例外を送出する契約とし、`increment()`側で
    有限回リトライする。"""


class FirestoreUsageCounter:
    """UsageCounterProtocolの実Firestore接続実装(get_count/incrementの基本2メソッドのみ)。

    usage_counter/{user_id}ドキュメントのmonth・countフィールドを読み書きする
    (firestore-provider-adapter-design.md 19.2節)。
    """

    def __init__(self, firestore_client) -> None:
        self._client = firestore_client
        self._collection = firestore_client.collection("usage_counter")

    def get_count(self, user_id: str, month: str) -> int:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return 0
        data = snapshot.to_dict() or {}
        if data.get("month") != month:
            return 0
        return data.get("count", 0)

    _MAX_COMMIT_ATTEMPTS = 5

    def increment(self, user_id: str, month: str) -> int:
        """read-modify-writeをトランザクション内に閉じ込め、19.3節で指摘された
        短時間の連投によるカウント消失(race condition)を避ける。インクリメント後の
        カウント値を返す契約(UsageCounterProtocol)。

        `@firestore.transactional`デコレータが自動的に行うコミット競合時の再試行を、
        本モジュールではSDKに依存せず`TransactionConflict`捕捉による明示的なリトライ
        ループとして実装する(設計上の等価物)。
        """
        doc_ref = self._collection.document(user_id)

        for _ in range(self._MAX_COMMIT_ATTEMPTS):
            transaction = self._client.transaction()
            snapshot = transaction.get(doc_ref)
            data = snapshot.to_dict() or {} if snapshot.exists else {}
            count_before = data.get("count", 0) if data.get("month") == month else 0
            count_after = count_before + 1
            transaction.set(doc_ref, {"month": month, "count": count_after})
            try:
                transaction.commit()
            except TransactionConflict:
                continue
            return count_after

        raise TransactionConflict(
            f"increment(user_id={user_id!r}, month={month!r}) did not commit after "
            f"{self._MAX_COMMIT_ATTEMPTS} attempts"
        )
