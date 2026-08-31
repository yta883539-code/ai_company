#!/usr/bin/env python3
"""
store-settings-save-flow-design.mdで設計した、owner-settings-wireframe.mdの
営業情報設定ページ保存(Googleフォーム+GAS Webhook想定)から、
onboarding-completion-message-design.md/store_profile_store.
evaluate_onboarding_completion_message_dispatch()呼び出しまでを結線する。

位置づけ:
- 本モジュールはonboarding-completion-message-design.mdの発火判定に必要な最小範囲
  (営業曜日・営業時間の設定有無・予約枠の間隔・同時受付可能数・メニュー件数)の
  正規化・書き込みのみを扱う。曜日別営業時間の複数区間バリデーション
  (business-hours-lunch-break.md・weekday-specific-business-hours.md)や
  臨時休業日・メッセージトーン・常連客閾値・FAQ情報の保存処理は別課題として残す
  (store-settings-save-flow-design.md 2節)。
- 実際のGoogleフォーム作成・GAS配置、実Firestore接続は「外部サービスへの実設定」
  「アカウント作成」に該当し、引き続きオーナー承認待ち(pending-approval.md参照)。
  本モジュールはGAS Webhookから届く想定のペイロードをどう検証・正規化し、
  どうstores/{storeId}ドキュメントへ書き込み、オンボーディング完了判定へ渡すかという
  処理ロジック自体を実クラウド接続なしで検証可能にしたもの
  (course-set-pasha/application_form_submission_flow.pyと同じ位置づけ)。

設計の参照元: store-settings-save-flow-design.md
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

sys.path.insert(0, str(Path(__file__).parent))

from cloud_function_process_event import LinePushClient  # noqa: E402
from cloud_function_send_onboarding_completion_message import (  # noqa: E402
    handle_onboarding_completion_message_dispatch,
)
from store_profile_store import (  # noqa: E402
    InMemoryStoreProfileStore,
    StoreProfileStoreProtocol,
)


class StoreSettingsStoreProtocol(StoreProfileStoreProtocol, Protocol):
    """`stores/{storeId}`ドキュメントのうちMVP必須項目フィールドへの書き込みを表す
    (store-settings-save-flow-design.md 6節)。読み取りメソッドは
    `StoreProfileStoreProtocol`を継承して共有する(実Firestore化時は単一ドキュメント
    アクセスに統合できるようにするため、application-form-submission-flow-design.md
    4節と同じ考え方)。"""

    def set_business_hours_raw(self, user_id: str, business_hours_raw: str) -> None:
        ...

    def set_closed_weekdays(self, user_id: str, closed_weekdays: list) -> None:
        ...

    def set_slot_interval_minutes(self, user_id: str, minutes: int) -> None:
        ...

    def set_concurrent_capacity(self, user_id: str, capacity: int) -> None:
        ...

    def set_menus(self, user_id: str, menus: list) -> None:
        ...


class InMemoryStoreSettingsStore(InMemoryStoreProfileStore):
    """`InMemoryStoreProfileStore`に、design 6節で追加するMVP必須項目フィールド
    (businessHoursRaw・closedWeekdays・slotIntervalMinutes・concurrentCapacity・
    menus)の保持を追加した検証用スタブ。"""

    def __init__(self) -> None:
        super().__init__()
        self._business_hours_raw: dict[str, str] = {}
        self._closed_weekdays: dict[str, list] = {}
        self._slot_interval_minutes: dict[str, int] = {}
        self._concurrent_capacity: dict[str, int] = {}
        self._menus: dict[str, list] = {}

    def set_business_hours_raw(self, user_id: str, business_hours_raw: str) -> None:
        self._business_hours_raw[user_id] = business_hours_raw

    def get_business_hours_raw(self, user_id: str) -> str:
        return self._business_hours_raw.get(user_id, "")

    def set_closed_weekdays(self, user_id: str, closed_weekdays: list) -> None:
        self._closed_weekdays[user_id] = list(closed_weekdays)

    def get_closed_weekdays(self, user_id: str) -> list:
        return list(self._closed_weekdays.get(user_id, []))

    def set_slot_interval_minutes(self, user_id: str, minutes: int) -> None:
        self._slot_interval_minutes[user_id] = minutes

    def get_slot_interval_minutes(self, user_id: str) -> Optional[int]:
        return self._slot_interval_minutes.get(user_id)

    def set_concurrent_capacity(self, user_id: str, capacity: int) -> None:
        self._concurrent_capacity[user_id] = capacity

    def get_concurrent_capacity(self, user_id: str) -> Optional[int]:
        return self._concurrent_capacity.get(user_id)

    def set_menus(self, user_id: str, menus: list) -> None:
        self._menus[user_id] = list(menus)

    def get_menus(self, user_id: str) -> list:
        return list(self._menus.get(user_id, []))


# design 4節: "30分"・"1"のような表示文字列から数字部分を抽出するために使う。
_DIGITS_PATTERN = re.compile(r"\d+")

_WEEKDAYS_PER_WEEK = 7


def _extract_positive_int(raw_value: object) -> Optional[int]:
    """design 4節の抽出ルール。数字が抽出できない、または0以下の場合はNone
    (`evaluate_onboarding_completion_message_dispatch()`側で未設定として扱われる)。"""
    if not isinstance(raw_value, str):
        return None
    match = _DIGITS_PATTERN.search(raw_value)
    if not match:
        return None
    value = int(match.group())
    return value if value > 0 else None


def normalize_menus(raw_menus: object) -> list[dict]:
    """design 4節: `name`が空文字列・非文字列の要素は不正入力として除外する。"""
    if not isinstance(raw_menus, list):
        return []
    normalized: list[dict] = []
    for item in raw_menus:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        normalized.append(
            {"name": name.strip(), "duration_minutes": item.get("duration_minutes")}
        )
    return normalized


@dataclass
class StoreSettingsSubmissionResult:
    """`handle_store_settings_submission()`の結果(design 6節のエントリポイントの
    戻り値)。"""

    ok: bool
    user_id: Optional[str] = None
    business_hours_configured: bool = False
    slot_interval_minutes: Optional[int] = None
    concurrent_capacity: Optional[int] = None
    menu_count: int = 0
    onboarding_completion_message_dispatched: bool = False
    error: Optional[str] = None


def handle_store_settings_submission(
    payload: dict,
    store: StoreSettingsStoreProtocol,
    *,
    payment_page_url: str,
    push_client: LinePushClient,
    tone: str = "standard",
) -> StoreSettingsSubmissionResult:
    """design 3節のGAS Webhookペイロードを検証・4節の正規化を行い、5節の書き込みと
    `handle_onboarding_completion_message_dispatch()`への結線までを行う。"""
    user_id = payload.get("user_id")
    if not isinstance(user_id, str) or not user_id.strip():
        return StoreSettingsSubmissionResult(
            ok=False, error="user_id is missing or not a non-empty string"
        )

    business_hours_raw = payload.get("business_hours_raw", "")
    if not isinstance(business_hours_raw, str):
        return StoreSettingsSubmissionResult(
            ok=False, error="business_hours_raw must be a string"
        )

    closed_weekdays = payload.get("closed_weekdays", [])
    if not isinstance(closed_weekdays, list):
        return StoreSettingsSubmissionResult(
            ok=False, error="closed_weekdays must be a list"
        )

    slot_interval_minutes = _extract_positive_int(
        payload.get("slot_interval_minutes_raw")
    )
    concurrent_capacity = _extract_positive_int(
        payload.get("concurrent_capacity_raw")
    )
    menus = normalize_menus(payload.get("menus"))

    business_hours_configured = bool(business_hours_raw.strip()) and (
        len(set(closed_weekdays)) < _WEEKDAYS_PER_WEEK
    )

    store.set_business_hours_raw(user_id, business_hours_raw.strip())
    store.set_closed_weekdays(user_id, closed_weekdays)
    if slot_interval_minutes is not None:
        store.set_slot_interval_minutes(user_id, slot_interval_minutes)
    if concurrent_capacity is not None:
        store.set_concurrent_capacity(user_id, concurrent_capacity)
    store.set_menus(user_id, menus)

    dispatched = handle_onboarding_completion_message_dispatch(
        user_id,
        business_hours_configured=business_hours_configured,
        slot_interval_minutes=slot_interval_minutes,
        concurrent_capacity=concurrent_capacity,
        menu_count=len(menus),
        store=store,
        payment_page_url=payment_page_url,
        push_client=push_client,
        tone=tone,
    )

    return StoreSettingsSubmissionResult(
        ok=True,
        user_id=user_id,
        business_hours_configured=business_hours_configured,
        slot_interval_minutes=slot_interval_minutes,
        concurrent_capacity=concurrent_capacity,
        menu_count=len(menus),
        onboarding_completion_message_dispatched=dispatched,
    )
