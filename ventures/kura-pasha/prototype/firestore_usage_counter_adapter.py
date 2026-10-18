"""firestore-usage-counter-provider-adapter-design.md 2節・5節(フェーズ226版)の設計を
実コードに落としたもの。course-set-pashaフェーズ312のfirestore_usage_counter_adapter.py
(UsageCounterProtocol向け)と同型の構成を、本ventureのUsageCounterStoreProtocol
(get/set/increment_or_resetの3メソッド構成)に合わせて横展開したもの。

実Firestoreプロジェクトへの接続自体はpending-approval.md記載の通りオーナー承認待ちのため、
本モジュールはgoogle-cloud-firestore SDKを直接importしない。コンストラクタに渡す
`firestore_client`は、`collection(name).document(id)`で取得したドキュメント参照が
`get()`(DocumentSnapshotを返す。`.exists`・`.to_dict()`を持つ)・`set(data)`を持ち、
`firestore_client.transaction()`がトランザクションオブジェクト(`get(doc_ref)`・
`set(doc_ref, data)`・`commit()`を持つ)を返す、という設計で前提にしたのと同じ最小
インターフェースを満たせばよい(実SDKでもテスト用フェイクでも差し替え可能)。
"""

from __future__ import annotations


class TransactionConflict(Exception):
    """トランザクションがコミット時に競合を検出した場合に送出される(実SDKでは
    `google.api_core.exceptions.Aborted`相当)。`firestore_client.transaction()`が
    返すオブジェクトの`commit()`がこの例外を送出する契約とし、`increment_or_reset()`側で
    有限回リトライする。"""


class FirestoreUsageCounterProvider:
    """UsageCounterStoreProtocolの実Firestore接続実装(get/set/increment_or_reset)。

    usage_counter/{workshop_id}ドキュメントのmonth・countフィールドを読み書きする
    (firestore-usage-counter-provider-adapter-design.md 2節)。
    """

    def __init__(self, firestore_client) -> None:
        self._client = firestore_client
        self._collection = firestore_client.collection("usage_counter")

    def get(self, workshop_id: str) -> tuple[str, int] | None:
        """テスト向けの状態検証用途にのみ残す非原子的メソッド。本流
        (check_and_increment_usage)ではincrement_or_resetのみを使う(design.md 5節)。"""
        snapshot = self._collection.document(workshop_id).get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict() or {}
        if "month" not in data or "count" not in data:
            return None
        return (data["month"], data["count"])

    def set(self, workshop_id: str, month: str, count: int) -> None:
        """テスト向けの状態検証用途にのみ残す非原子的メソッド。"""
        self._collection.document(workshop_id).set({"month": month, "count": count})

    _MAX_COMMIT_ATTEMPTS = 5

    def increment_or_reset(self, workshop_id: str, current_month: str) -> int:
        """read-modify-writeをトランザクション内に閉じ込め、design.md 3節で指摘された
        並行リクエストによるカウント消失(race condition)を避ける。保存済みの月が
        current_monthと一致しなければcount=0から、一致すれば現在のcountから、いずれも
        +1した結果を返す。

        design.md 5節(フェーズ226)で確定したfail-open方針に従い、最大試行回数を超えて
        コミットできなかった場合(接続エラー・トランザクション競合の多発等)は例外を
        伝播させず、当月初回利用として1を返す(取り漏れは許容し、生成リクエストを
        止めない)。
        """
        doc_ref = self._collection.document(workshop_id)

        try:
            for _ in range(self._MAX_COMMIT_ATTEMPTS):
                transaction = self._client.transaction()
                snapshot = transaction.get(doc_ref)
                data = snapshot.to_dict() or {} if snapshot.exists else {}
                count_before = data.get("count", 0) if data.get("month") == current_month else 0
                count_after = count_before + 1
                transaction.set(doc_ref, {"month": current_month, "count": count_after})
                try:
                    transaction.commit()
                except TransactionConflict:
                    continue
                return count_after
        except Exception:
            return 1

        return 1
