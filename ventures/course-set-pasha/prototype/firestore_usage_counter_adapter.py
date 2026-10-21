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

from datetime import datetime
from typing import Optional


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

    def increment_and_mark_notice(
        self,
        user_id: str,
        month: str,
        mark_notice_sent: bool,
        trial_start_at: Optional[datetime] = None,
    ) -> int:
        """firestore-provider-adapter-design.md 20.2節: count増分・
        (mark_notice_sent=Trueの場合のみ)first_generation_notice_sentの更新・
        (trial_start_atが渡され、かつ未設定の場合のみ)trial_start_atの設定を
        単一トランザクション(単一書き込み)として行う。increment()のトランザクションへ
        委譲すると入れ子トランザクションになり実SDKでは扱えないため、increment()とは
        別に3フィールド分の更新を展開した実装とする(20.3節「委譲実装にしなかった理由」)。

        既存ドキュメントの他フィールド(first_generation_notice_sent・trial_start_at)を
        今回の呼び出しが指定していない場合でも消さないよう、トランザクション内で読んだ
        `data`を書き込み前のベースにする(実SDKの`merge=True`相当)。インクリメント後の
        カウント値を返す契約(AtomicNoticeUsageCounterProtocol)。
        """
        doc_ref = self._collection.document(user_id)

        for _ in range(self._MAX_COMMIT_ATTEMPTS):
            transaction = self._client.transaction()
            snapshot = transaction.get(doc_ref)
            data = dict(snapshot.to_dict() or {}) if snapshot.exists else {}
            count_before = data.get("count", 0) if data.get("month") == month else 0
            count_after = count_before + 1
            data["month"] = month
            data["count"] = count_after
            if mark_notice_sent:
                data["first_generation_notice_sent"] = True
            if trial_start_at is not None and "trial_start_at" not in data:
                data["trial_start_at"] = trial_start_at
            transaction.set(doc_ref, data)
            try:
                transaction.commit()
            except TransactionConflict:
                continue
            return count_after

        raise TransactionConflict(
            f"increment_and_mark_notice(user_id={user_id!r}, month={month!r}) did not "
            f"commit after {self._MAX_COMMIT_ATTEMPTS} attempts"
        )

    def set_upgraded_at_if_unset(self, user_id: str, upgraded_at: datetime) -> None:
        """firestore-provider-adapter-design.md 22.2節: `upgraded_at`が未設定の場合
        のみ設定する(`set_trial_start_at_if_unset`と同じ「1回だけ設定」契約)。

        Stripeのat-least-once配信により`checkout.session.completed`が重複配信
        された場合、素朴な「読んでNoneなら書く」の2回の独立呼び出しでは両方がNoneを
        読んで2回とも書き込んでしまう(22.3節)ため、increment()と同じ
        TransactionConflict捕捉によるリトライループでこれを避ける。
        """
        doc_ref = self._collection.document(user_id)

        for _ in range(self._MAX_COMMIT_ATTEMPTS):
            transaction = self._client.transaction()
            snapshot = transaction.get(doc_ref)
            data = dict(snapshot.to_dict() or {}) if snapshot.exists else {}
            if "upgraded_at" in data:
                return
            data["upgraded_at"] = upgraded_at
            transaction.set(doc_ref, data)
            try:
                transaction.commit()
            except TransactionConflict:
                continue
            return

        raise TransactionConflict(
            f"set_upgraded_at_if_unset(user_id={user_id!r}) did not commit after "
            f"{self._MAX_COMMIT_ATTEMPTS} attempts"
        )

    def get_upgraded_at(self, user_id: str) -> Optional[datetime]:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("upgraded_at")

    def set_trial_end_notified_at(self, user_id: str, notified_at: datetime) -> None:
        """firestore-provider-adapter-design.md 22.2節: 呼び出し元
        (`select_due_trial_end_notifications()`)が既に`trial_end_notified_at is None`
        のユーザーのみに絞り込むため、本メソッド自体はトランザクション不要の単純な
        上書き(他フィールドを消さないよう既存データをベースにマージ)で良い。
        """
        doc_ref = self._collection.document(user_id)
        snapshot = doc_ref.get()
        data = dict(snapshot.to_dict() or {}) if snapshot.exists else {}
        data["trial_end_notified_at"] = notified_at
        doc_ref.set(data)

    def get_trial_end_notified_at(self, user_id: str) -> Optional[datetime]:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("trial_end_notified_at")

    def increment_trial_generation_count(self, user_id: str) -> int:
        """firestore-provider-adapter-design.md 23.2節: `trial_generation_count`を+1し、
        インクリメント後の値を返す。trial-end-notification-design.md 3節の通知文言
        (「投稿文生成: ○回」)に使うトライアル期間限定の累計値で、19節の`count`(月次で
        リセットされる)とは別フィールドとして扱い、月境界の影響を受けず単調増加する。
        19.3節と同種のread-modify-write競合をincrement()と同じリトライループで避ける。
        """
        doc_ref = self._collection.document(user_id)

        for _ in range(self._MAX_COMMIT_ATTEMPTS):
            transaction = self._client.transaction()
            snapshot = transaction.get(doc_ref)
            data = dict(snapshot.to_dict() or {}) if snapshot.exists else {}
            count_after = data.get("trial_generation_count", 0) + 1
            data["trial_generation_count"] = count_after
            transaction.set(doc_ref, data)
            try:
                transaction.commit()
            except TransactionConflict:
                continue
            return count_after

        raise TransactionConflict(
            f"increment_trial_generation_count(user_id={user_id!r}) did not commit "
            f"after {self._MAX_COMMIT_ATTEMPTS} attempts"
        )

    def get_trial_generation_count(self, user_id: str) -> int:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return 0
        return (snapshot.to_dict() or {}).get("trial_generation_count", 0)

    def increment_trial_area_count(self, user_id: str, area_count: int) -> int:
        """23.2節: `increment_trial_generation_count`と同型だが、固定+1ではなく
        引数`area_count`(1回の生成におけるhistory_rowsの要素数)を加算する点のみ異なる。
        """
        doc_ref = self._collection.document(user_id)

        for _ in range(self._MAX_COMMIT_ATTEMPTS):
            transaction = self._client.transaction()
            snapshot = transaction.get(doc_ref)
            data = dict(snapshot.to_dict() or {}) if snapshot.exists else {}
            count_after = data.get("trial_area_count", 0) + area_count
            data["trial_area_count"] = count_after
            transaction.set(doc_ref, data)
            try:
                transaction.commit()
            except TransactionConflict:
                continue
            return count_after

        raise TransactionConflict(
            f"increment_trial_area_count(user_id={user_id!r}, area_count={area_count!r}) "
            f"did not commit after {self._MAX_COMMIT_ATTEMPTS} attempts"
        )

    def get_trial_area_count(self, user_id: str) -> int:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return 0
        return (snapshot.to_dict() or {}).get("trial_area_count", 0)

    def set_payment_failure_detected_at(
        self, user_id: str, detected_at: datetime
    ) -> None:
        """firestore-provider-adapter-design.md 24.2節: 検知のたびに最新の検知時刻へ
        単純に上書きする契約(古い検知時刻を残す理由がない)のため、トランザクション
        不要。既存データをベースにマージして他フィールドを消さない(24.3節
        「merge=Trueを使う理由」、本モジュール内では`set_trial_end_notified_at`と
        同じ「読んでから全フィールドを書き戻す」方式で表現する)。
        """
        doc_ref = self._collection.document(user_id)
        snapshot = doc_ref.get()
        data = dict(snapshot.to_dict() or {}) if snapshot.exists else {}
        data["payment_failure_detected_at"] = detected_at
        doc_ref.set(data)

    def get_payment_failure_detected_at(self, user_id: str) -> Optional[datetime]:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("payment_failure_detected_at")

    def clear_payment_failure_detected_at(self, user_id: str) -> None:
        """9.3節(aircon-pasha 11節と同じ結論)の通り、`None`書き込みでclearを表現する。"""
        doc_ref = self._collection.document(user_id)
        snapshot = doc_ref.get()
        data = dict(snapshot.to_dict() or {}) if snapshot.exists else {}
        data["payment_failure_detected_at"] = None
        doc_ref.set(data)

    def set_payment_failure_reminder_sent_at(
        self, user_id: str, sent_at: datetime
    ) -> None:
        doc_ref = self._collection.document(user_id)
        snapshot = doc_ref.get()
        data = dict(snapshot.to_dict() or {}) if snapshot.exists else {}
        data["payment_failure_reminder_sent_at"] = sent_at
        doc_ref.set(data)

    def get_payment_failure_reminder_sent_at(
        self, user_id: str
    ) -> Optional[datetime]:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("payment_failure_reminder_sent_at")

    def clear_payment_failure_reminder_sent_at(self, user_id: str) -> None:
        doc_ref = self._collection.document(user_id)
        snapshot = doc_ref.get()
        data = dict(snapshot.to_dict() or {}) if snapshot.exists else {}
        data["payment_failure_reminder_sent_at"] = None
        doc_ref.set(data)

    def set_payment_suspension_owner_notified_at(
        self, user_id: str, notified_at: datetime
    ) -> None:
        """firestore-provider-adapter-design.md 25.2節: payment_failure_reminder_sent_at
        と同じ単純な上書き契約(cloud_function_webhook.py 401〜406行目docstring)の
        ため、トランザクション不要。フェイクのdocument.set(data)がmerge引数を取らない
        ため、24節の各メソッドと同じ「読んでから全フィールドを書き戻す」方式で表現する。
        """
        doc_ref = self._collection.document(user_id)
        snapshot = doc_ref.get()
        data = dict(snapshot.to_dict() or {}) if snapshot.exists else {}
        data["payment_suspension_owner_notified_at"] = notified_at
        doc_ref.set(data)

    def get_payment_suspension_owner_notified_at(
        self, user_id: str
    ) -> Optional[datetime]:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get(
            "payment_suspension_owner_notified_at"
        )

    def clear_payment_suspension_owner_notified_at(self, user_id: str) -> None:
        """25.3節(9節・24節と同じ):`None`書き込みでclearを表現する。"""
        doc_ref = self._collection.document(user_id)
        snapshot = doc_ref.get()
        data = dict(snapshot.to_dict() or {}) if snapshot.exists else {}
        data["payment_suspension_owner_notified_at"] = None
        doc_ref.set(data)

    def set_subscription_canceled_at(
        self, user_id: str, canceled_at: datetime
    ) -> None:
        """firestore-provider-adapter-design.md 26.2節: `customer.subscription.deleted`
        受信時(解約確定)の単純な上書き契約(24・25節と同じ考え方)のため、トランザクション
        不要。「読んでから全フィールドを書き戻す」方式で他フィールドを消さない。
        """
        doc_ref = self._collection.document(user_id)
        snapshot = doc_ref.get()
        data = dict(snapshot.to_dict() or {}) if snapshot.exists else {}
        data["subscription_canceled_at"] = canceled_at
        doc_ref.set(data)

    def get_subscription_canceled_at(self, user_id: str) -> Optional[datetime]:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("subscription_canceled_at")

    def clear_subscription_canceled_at(self, user_id: str) -> None:
        """`customer.subscription.created`受信時(再契約)に解約フラグを消去する
        (9節・24節・25節と同じ`None`書き込みでclearを表現する)。"""
        doc_ref = self._collection.document(user_id)
        snapshot = doc_ref.get()
        data = dict(snapshot.to_dict() or {}) if snapshot.exists else {}
        data["subscription_canceled_at"] = None
        doc_ref.set(data)

    def set_subscription_state_event_time(
        self, user_id: str, event_time: datetime
    ) -> None:
        """26.1節: `customer.subscription.deleted`/`created`系の配信順序ガード用の
        基準時刻。stale判定の比較はdispatch_stripe_event()側の責務であり、本メソッドは
        単純な上書きでよい(`clear_*`はProtocolに存在しない、26.3節)。"""
        doc_ref = self._collection.document(user_id)
        snapshot = doc_ref.get()
        data = dict(snapshot.to_dict() or {}) if snapshot.exists else {}
        data["subscription_state_event_time"] = event_time
        doc_ref.set(data)

    def get_subscription_state_event_time(
        self, user_id: str
    ) -> Optional[datetime]:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get("subscription_state_event_time")

    def set_payment_failure_state_event_time(
        self, user_id: str, event_time: datetime
    ) -> None:
        """26.1節: `invoice.payment_failed`/`succeeded`(dunning系)の配信順序ガード用の
        基準時刻。`subscription_state_event_time`とは別イベント系列のため独立して持つ。"""
        doc_ref = self._collection.document(user_id)
        snapshot = doc_ref.get()
        data = dict(snapshot.to_dict() or {}) if snapshot.exists else {}
        data["payment_failure_state_event_time"] = event_time
        doc_ref.set(data)

    def get_payment_failure_state_event_time(
        self, user_id: str
    ) -> Optional[datetime]:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get(
            "payment_failure_state_event_time"
        )

    def set_subscription_updated_event_time(
        self, user_id: str, event_time: datetime
    ) -> None:
        """26.1節: `customer.subscription.updated`の配信順序ガード用の基準時刻。
        `subscription_state_event_time`とは別イベント系列のため独立して持つ。"""
        doc_ref = self._collection.document(user_id)
        snapshot = doc_ref.get()
        data = dict(snapshot.to_dict() or {}) if snapshot.exists else {}
        data["subscription_updated_event_time"] = event_time
        doc_ref.set(data)

    def get_subscription_updated_event_time(
        self, user_id: str
    ) -> Optional[datetime]:
        snapshot = self._collection.document(user_id).get()
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get(
            "subscription_updated_event_time"
        )
