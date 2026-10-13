#!/usr/bin/env python3
"""vehicle-label-duplicate-handling-design.md 2節〜4節(フェーズ114)が机上設計のみに
留めていた`vehicle_id`発行・重複チェックのロジック本体を、実際に呼び出せるコードに
落とし込む(design.md「6. 未確定・次回候補」には挙がっていないが、本体: design.mdの
『2. vehicle_idの発行方式』『3. 重複判定の方針』『4. 新規メモ受信時のフロー』自体が
フェーズ114では文書化のみで、実コードが一切存在していなかったという欠落への対応)。

位置づけ:
- `vehicle`コレクションへの実Firestore接続はGCPプロジェクト作成に該当し、オーナー承認待ち
  (pending-approval.md記載の既存承認待ち事項の範囲内)のため、本モジュールは他venture・
  他モジュールと同じ方針で、design.md 2節の方式(Firestore自動生成ID)をInMemoryで模した
  `VehicleStoreProtocol`/`InMemoryVehicleStore`のみを用意する。
- design.md 2節が指摘する「`(operatorInternalId, vehicleLabel)`のFirestore複合インデックスが
  必要」という実クエリの話は本モジュールの範囲外(InMemory実装はPythonのdictキーで直接
  検索するため、インデックスの有無は結果に影響しない。実デプロイ時のFirestore側インデックス
  定義は依然design.md「6.」の次回候補として残る)。
- 「新規」と判定した場合のみ、既存のoverage_notifications.record_vehicle_and_get_overage_
  notice()にdelta=1で委譲し、`vehicleCount`加算・プラン超過通知の両方を行う。「既存」と
  判定した場合はdesign.md 4節3.「何もしない」のとおりvehicleCountに一切触れない
  (record_vehicle_and_get_overage_notice自体は呼ばない)。

設計の参照元: vehicle-label-duplicate-handling-design.md
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Protocol

from overage_notifications import (
    VehicleCountStoreProtocol,
    record_vehicle_and_get_overage_notice,
)


class VehicleStoreProtocol(Protocol):
    """`vehicle/{vehicle_id}`コレクションの最小限の読み書きを模したProtocol
    (design.md 2節: vehicle_idはFirestore自動生成ID、3節: `(operatorInternalId,
    vehicleLabel)`の完全一致検索)。"""

    def find_vehicle_id(
        self, operator_internal_id: str, vehicle_label: str
    ) -> "str | None":
        """(operatorInternalId, vehicleLabel)の完全一致(呼び出し側でトリム済みを前提、
        design.md 3節)で既存vehicle_idを探す。見つからない場合はNone。"""
        ...

    def create_vehicle(self, operator_internal_id: str, vehicle_label: str) -> str:
        """新規vehicleドキュメントを作成し、新たに発行したvehicle_idを返す。同じキーに対し
        複数回呼ぶと、呼ぶたびに別のvehicle_idを発行する(重複呼び出しの抑止は本モジュールの
        `register_vehicle_from_inspection_memo()`側の責務)。"""
        ...


class InMemoryVehicleStore:
    """vehicleコレクションを模したInMemory実装(Firestore接続は未実装のまま)。"""

    def __init__(self) -> None:
        self._vehicle_id_by_key: "dict[tuple[str, str], str]" = {}

    def find_vehicle_id(
        self, operator_internal_id: str, vehicle_label: str
    ) -> "str | None":
        return self._vehicle_id_by_key.get((operator_internal_id, vehicle_label))

    def create_vehicle(self, operator_internal_id: str, vehicle_label: str) -> str:
        # design.md 2節: Firestore自動生成IDのInMemory代替。access_token_store.
        # generate_access_token()と同じく`secrets`モジュールで推測不能な値を生成する
        # (ただし本IDは内部参照専用でユーザーに配布しないため、桁数はaccess_tokenより
        # 短い12バイトで足りる)。
        vehicle_id = secrets.token_hex(12)
        self._vehicle_id_by_key[(operator_internal_id, vehicle_label)] = vehicle_id
        return vehicle_id


@dataclass(frozen=True)
class VehicleRegistrationResult:
    vehicle_id: str
    is_new_vehicle: bool
    overage_notice: "str | None"


def register_vehicle_from_inspection_memo(
    vehicle_store: VehicleStoreProtocol,
    vehicle_count_store: VehicleCountStoreProtocol,
    operator_internal_id: str,
    raw_vehicle_label: str,
    plan_id: str,
) -> VehicleRegistrationResult:
    """design.md「4. 新規メモ受信時のフロー」をそのままコード化する。

    1. `raw_vehicle_label`の前後空白をトリムする(design.md 3節、トリムのみの正規化。
       全角/半角統一等は一切行わない)。
    2. `(operator_internal_id, vehicle_label)`の完全一致で既存vehicle_idを探す。
    3. 見つかった場合: 何もしない(再利用。`vehicleCount`加算・プラン超過通知のいずれも
       発生しない)。
    4. 見つからなかった場合: 新規vehicleドキュメントを作成し、overage_notifications.
       record_vehicle_and_get_overage_notice()にdelta=1(既定値)で委譲して`vehicleCount`を
       1増やし、プラン超過を新たに跨いだ場合のみ通知文を得る。

    点検記録の整形自体(design.md 4節5.)は本関数の責務外であり、呼び出し側が本関数の結果に
    関わらず常に実行する想定(design.mdの「台数超過が判明しても記録生成を止めない」方針どおり、
    本関数は例外を送出しない)。
    """

    vehicle_label = raw_vehicle_label.strip()
    existing_vehicle_id = vehicle_store.find_vehicle_id(operator_internal_id, vehicle_label)
    if existing_vehicle_id is not None:
        return VehicleRegistrationResult(
            vehicle_id=existing_vehicle_id, is_new_vehicle=False, overage_notice=None
        )

    vehicle_id = vehicle_store.create_vehicle(operator_internal_id, vehicle_label)
    overage_notice = record_vehicle_and_get_overage_notice(
        vehicle_count_store, operator_internal_id, plan_id
    )
    return VehicleRegistrationResult(
        vehicle_id=vehicle_id, is_new_vehicle=True, overage_notice=overage_notice
    )


if __name__ == "__main__":
    raise SystemExit(
        "このモジュールは直接実行しない。テストはtest_vehicle_registry.pyを使うこと。"
    )
