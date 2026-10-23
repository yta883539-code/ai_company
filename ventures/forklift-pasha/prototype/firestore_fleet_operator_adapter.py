"""fleet-operator-store-firestore-adapter-design.md(フェーズ160)「3. 各メソッドの実装方針」の
**基盤グループ**(email・plan_id・stripe_customer_id〈順引き+逆引き〉・trial_start_atの
4フィールド、計9メソッド)の設計を実コードに落としたもの。aircon-pashaの
firestore_user_profile_adapter.py・kura-pashaのfirestore_workshop_adapter.pyと同型の方針を
踏襲し、google-cloud-firestore SDKを直接importしない(`firestore_client`に
`collection(name).document(id)`で取得したドキュメント参照が`get()`(`.exists`・`.to_dict()`を
持つSnapshotを返す)・`set(data, merge=...)`を持てば実SDKでもテスト用フェイクでも差し替え
可能)。

`FleetOperatorStoreProtocol`(prototype/trial_management.py)は本venture最大のProtocolで
15メソッドを持つが、design.md「一度に全メソッドを設計すると検討事項が発散するため、関連性の
高い最小グループから着手する」方針により、本モジュールは基盤グループのみを対象とする。
残りのグループ(trial_generation_count+trial_end_notified_at、upgraded_at、canceled_at、
deletion_confirmation系3、all_internal_ids)は design.md 4節の次回候補として残っている。

design.md 3.2節の判断により、`set_stripe_customer_id`はFirestore版では旧IDの逆引き
エントリを明示的に削除する処理を持たない(`stripeCustomerId`フィールドが新IDで上書きされた
瞬間に旧IDでの単一フィールドクエリは自動的に0件になるため)。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional


class FirestoreFleetOperatorStore:
    """FleetOperatorStoreProtocolの実Firestore接続実装(基盤グループ: email・plan_id・
    stripe_customer_id〈順引き+逆引き〉・trial_start_atの4フィールド、計9メソッドのみ。
    design.md 4節に残る他グループは本クラスには未実装)。
    fleet_operator/{internal_id}ドキュメントを読み書きする(firestore-data-model.md
    「1. fleet_operator/{internal_id}」)。
    """

    def __init__(self, firestore_client) -> None:
        self._client = firestore_client
        self._operators = firestore_client.collection("fleet_operator")

    def _doc_ref(self, internal_id: str):
        return self._operators.document(internal_id)

    def _get_field(self, internal_id: str, field: str):
        try:
            snapshot = self._doc_ref(internal_id).get()
        except Exception:
            # design.md 3.4節・access-token-store-firestore-adapter-design.mdと同じ
            # 安全側方針。一時的な接続エラーも「未設定」(None)に合流させる。
            return None
        if not snapshot.exists:
            return None
        return (snapshot.to_dict() or {}).get(field)

    def get_email(self, internal_id: str) -> "str | None":
        return self._get_field(internal_id, "email")

    def set_email(self, internal_id: str, value: str) -> None:
        self._doc_ref(internal_id).set({"email": value}, merge=True)

    def get_plan_id(self, internal_id: str) -> "str | None":
        return self._get_field(internal_id, "planId")

    def set_plan_id(self, internal_id: str, value: str) -> None:
        self._doc_ref(internal_id).set({"planId": value}, merge=True)

    def get_stripe_customer_id(self, internal_id: str) -> "str | None":
        return self._get_field(internal_id, "stripeCustomerId")

    def set_stripe_customer_id(self, internal_id: str, value: str) -> None:
        # design.md 3.2節: 旧逆引きエントリの明示的な削除は不要(Firestoreはライブ
        # クエリのため、上書きされた瞬間に旧IDでの単一フィールドクエリは自動的に0件になる)。
        self._doc_ref(internal_id).set({"stripeCustomerId": value}, merge=True)

    def get_internal_id_by_stripe_customer_id(
        self, stripe_customer_id: str
    ) -> "str | None":
        # design.md 3.3節: stripeCustomerIdフィールドへの単一フィールドクエリ。
        query = self._operators.where("stripeCustomerId", "==", stripe_customer_id).limit(1)
        docs = list(query.stream())
        return docs[0].id if docs else None

    def get_trial_start_at(self, internal_id: str) -> "datetime | None":
        return self._get_field(internal_id, "trialStartAt")

    def set_trial_start_at(self, internal_id: str, value: datetime) -> None:
        # design.md 3.4節(a): 「既に設定済みの場合は上書きしない」制約は素朴なupdate/set
        # では再現できないため、呼び出し側の規約(先にget_trial_start_at()で既存値の有無を
        # 確認してから呼ぶ)に委ねる方針を本フェーズで仮決めした(トランザクション導入は
        # 時期尚早な最適化と判断、4節に再検討の前提を残す)。本アダプタ自身は常に書き込む。
        self._doc_ref(internal_id).set({"trialStartAt": value}, merge=True)
