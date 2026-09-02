#!/usr/bin/env python3
"""
store-settings-save-flow-design.mdで設計した、owner-settings-wireframe.mdの
営業情報設定ページ保存(Googleフォーム+GAS Webhook想定)から、
onboarding-completion-message-design.md/store_profile_store.
evaluate_onboarding_completion_message_dispatch()呼び出しまでを結線する。

位置づけ:
- 本モジュールはonboarding-completion-message-design.mdの発火判定に必要な最小範囲
  (営業曜日・営業時間の設定有無・予約枠の間隔・同時受付可能数・メニュー件数)の
  正規化・書き込みのみを扱う。曜日別営業時間の複数区間バリデーション自体
  (business-hours-lunch-break.md・weekday-specific-business-hours.md)や、臨時休業日の
  入力バリデーション自体(ad-hoc-closed-dates-support.md、過去日付・重複日付チェックは
  No-codeフォームツールのUX側に委ねる方針で本コードの範囲外)は別課題として残る
  (store-settings-save-flow-design.md 2節)が、両者の生値(raw)自体の保存は8節で
  結線した(2026-09-02定例更新)。
- メッセージトーン・常連客とみなす来店回数・FAQ情報は発火判定には使わないが、
  Firestoreへの書き込み自体は7節で結線する(2026-08-31定例更新)。
- 曜日別営業時間・臨時休業日も同様に発火判定には使わないが、Firestoreへの書き込み自体は
  8節で結線した(2026-09-02定例更新)。`AvailabilitySearcher`が要求する分単位の
  構造化済み値(`weekday_business_hours: dict[int, tuple[int,int]]`・
  `closed_dates: frozenset[date]`、weekday-specific-business-hours.md・
  ad-hoc-closed-dates-support.md参照)への変換は、`business_hours_raw`と同様
  raw文字列のまま保存するに留め、実際の変換処理はConversationEventProcessorの
  組み立て(store-id-resolution-and-owner-identity-design.md「残課題」記載の
  ファクトリ関数)側の課題として残す。
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

    def set_message_tone(self, user_id: str, message_tone: str) -> None:
        ...

    def set_repeat_customer_visit_threshold(self, user_id: str, threshold: int) -> None:
        ...

    def set_faq_info(self, user_id: str, faq_info: dict) -> None:
        ...

    def set_weekday_business_hours_raw(
        self, user_id: str, weekday_business_hours_raw: dict
    ) -> None:
        ...

    def set_closed_dates(self, user_id: str, closed_dates: list) -> None:
        ...


class InMemoryStoreSettingsStore(InMemoryStoreProfileStore):
    """`InMemoryStoreProfileStore`に、design 6節で追加するMVP必須項目フィールド
    (businessHoursRaw・closedWeekdays・slotIntervalMinutes・concurrentCapacity・
    menus)と、design 7節・8節で追加する任意項目フィールド(messageTone・
    repeatCustomerVisitThreshold・faqInfo・weekdayBusinessHoursRaw・closedDates)の
    保持を追加した検証用スタブ。"""

    def __init__(self) -> None:
        super().__init__()
        self._business_hours_raw: dict[str, str] = {}
        self._closed_weekdays: dict[str, list] = {}
        self._slot_interval_minutes: dict[str, int] = {}
        self._concurrent_capacity: dict[str, int] = {}
        self._menus: dict[str, list] = {}
        self._message_tone: dict[str, str] = {}
        self._repeat_customer_visit_threshold: dict[str, int] = {}
        self._faq_info: dict[str, dict] = {}
        self._weekday_business_hours_raw: dict[str, dict] = {}
        self._closed_dates: dict[str, list] = {}

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

    def set_message_tone(self, user_id: str, message_tone: str) -> None:
        self._message_tone[user_id] = message_tone

    def get_message_tone(self, user_id: str) -> str:
        return self._message_tone.get(user_id, _DEFAULT_MESSAGE_TONE)

    def set_repeat_customer_visit_threshold(self, user_id: str, threshold: int) -> None:
        self._repeat_customer_visit_threshold[user_id] = threshold

    def get_repeat_customer_visit_threshold(self, user_id: str) -> int:
        return self._repeat_customer_visit_threshold.get(
            user_id, _DEFAULT_REPEAT_CUSTOMER_VISIT_THRESHOLD
        )

    def set_faq_info(self, user_id: str, faq_info: dict) -> None:
        self._faq_info[user_id] = dict(faq_info)

    def get_faq_info(self, user_id: str) -> dict:
        return dict(self._faq_info.get(user_id, _EMPTY_FAQ_INFO))

    def set_weekday_business_hours_raw(
        self, user_id: str, weekday_business_hours_raw: dict
    ) -> None:
        self._weekday_business_hours_raw[user_id] = dict(weekday_business_hours_raw)

    def get_weekday_business_hours_raw(self, user_id: str) -> dict:
        return dict(self._weekday_business_hours_raw.get(user_id, {}))

    def set_closed_dates(self, user_id: str, closed_dates: list) -> None:
        self._closed_dates[user_id] = list(closed_dates)

    def get_closed_dates(self, user_id: str) -> list:
        return list(self._closed_dates.get(user_id, []))


# design 4節: "30分"・"1"のような表示文字列から数字部分を抽出するために使う。
_DIGITS_PATTERN = re.compile(r"\d+")

_WEEKDAYS_PER_WEEK = 7

# design 7.1節: message-tone-variants.mdで定義済みの3値。owner-settings-wireframe.mdの
# プルダウンの既定値でもある。
_VALID_MESSAGE_TONES = frozenset({"standard", "formal", "casual"})
_DEFAULT_MESSAGE_TONE = "standard"

# design 7.1節: 未入力・抽出不能時、precheck-strengthening.mdの簡略化判定を機能させ続ける
# ためNoneのまま放置せずこの既定値を書き込む(firestore-data-model.mdの既定値3と一致)。
_DEFAULT_REPEAT_CUSTOMER_VISIT_THRESHOLD = 3

# design 7.1節: faq-response-templates.mdのテンプレート項目と一致する支払い方法のみを許可する。
_VALID_FAQ_PAYMENT_METHODS = frozenset(
    {"現金", "クレジット", "電子マネー", "QRコード決済"}
)

_EMPTY_FAQ_INFO = {"address": "", "parking": "", "paymentMethods": []}


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


def normalize_message_tone(raw_value: object) -> str:
    """design 7.1節: 想定外の値は既定値`standard`にフォールバックする
    (誤ったトーンで送信するより既定の安全な文体を優先する)。"""
    if isinstance(raw_value, str) and raw_value in _VALID_MESSAGE_TONES:
        return raw_value
    return _DEFAULT_MESSAGE_TONE


def normalize_repeat_customer_visit_threshold(raw_value: object) -> int:
    """design 7.1節: `_extract_positive_int()`を再利用しつつ、`slot_interval_minutes`等
    とは異なり抽出できない場合もNoneのまま放置せず既定値3を返す。"""
    extracted = _extract_positive_int(raw_value)
    if extracted is None:
        return _DEFAULT_REPEAT_CUSTOMER_VISIT_THRESHOLD
    return extracted


def normalize_faq_info(payload: dict) -> dict:
    """design 7.1節: owner-settings-wireframe.md「店舗FAQ情報の入力欄」の3項目を正規化する。
    未入力の項目はエラーにせず空文字列/空配列のまま返す(232行目の「空欄は未登録として扱う」
    方針どおり)。"""
    address = payload.get("faq_address", "")
    if not isinstance(address, str):
        address = ""

    parking_available = payload.get("faq_parking_available")
    if parking_available == "あり":
        capacity = _extract_positive_int(payload.get("faq_parking_capacity_raw"))
        parking = f"あり({capacity}台)" if capacity is not None else "あり"
    elif parking_available == "なし":
        parking = "なし"
    else:
        parking = ""

    raw_payment_methods = payload.get("faq_payment_methods", [])
    if not isinstance(raw_payment_methods, list):
        raw_payment_methods = []
    payment_methods = [
        method
        for method in raw_payment_methods
        if isinstance(method, str) and method in _VALID_FAQ_PAYMENT_METHODS
    ]

    return {
        "address": address.strip(),
        "parking": parking,
        "paymentMethods": payment_methods,
    }


def normalize_weekday_business_hours_raw(payload: dict) -> dict[int, str]:
    """design 8節: 「曜日ごとに営業時間を変える」トグルON時に届く
    `weekday_business_hours_raw`(キー: `date.weekday()`準拠0〜6、値: `business_hours_raw`と
    同じ表記の生文字列)を正規化する。トグルOFF・未入力時はキー自体が省略される想定のため
    空dictを返す。妥当な曜日キー(0〜6の整数、JSON経由の文字列キーも許容)以外・
    空文字列の値は不正入力として黙って除外する(business_hours_rawの空欄チェックと同様、
    区間としての妥当性検証自体はweekday-specific-business-hours.md側の担当)。"""
    raw = payload.get("weekday_business_hours_raw", {})
    if not isinstance(raw, dict):
        return {}
    normalized: dict[int, str] = {}
    for raw_weekday, raw_value in raw.items():
        try:
            weekday = int(raw_weekday)
        except (TypeError, ValueError):
            continue
        if weekday < 0 or weekday >= _WEEKDAYS_PER_WEEK:
            continue
        if not isinstance(raw_value, str) or not raw_value.strip():
            continue
        normalized[weekday] = raw_value.strip()
    return normalized


def normalize_closed_dates(payload: dict) -> list[str]:
    """design 8節: 臨時休業日入力欄(`closed_dates`、`YYYY-MM-DD`形式の生文字列の配列)を
    正規化する。過去日付・重複日付のインライン警告はNo-codeフォームツールのUX側に委ねる方針
    (ad-hoc-closed-dates-support.md「残課題」)のため、ここでは非文字列・空文字列の除外と
    重複排除(入力順を保持)のみを行う。"""
    raw = payload.get("closed_dates", [])
    if not isinstance(raw, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            continue
        value = item.strip()
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
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
    message_tone: str = _DEFAULT_MESSAGE_TONE
    repeat_customer_visit_threshold: int = _DEFAULT_REPEAT_CUSTOMER_VISIT_THRESHOLD
    faq_info: dict = None  # type: ignore[assignment]
    weekday_business_hours_raw: dict = None  # type: ignore[assignment]
    closed_dates: list = None  # type: ignore[assignment]
    error: Optional[str] = None

    def __post_init__(self) -> None:
        if self.faq_info is None:
            self.faq_info = dict(_EMPTY_FAQ_INFO)
        if self.weekday_business_hours_raw is None:
            self.weekday_business_hours_raw = {}
        if self.closed_dates is None:
            self.closed_dates = []


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
    message_tone = normalize_message_tone(payload.get("message_tone_raw"))
    repeat_customer_visit_threshold = normalize_repeat_customer_visit_threshold(
        payload.get("repeat_customer_visit_threshold_raw")
    )
    faq_info = normalize_faq_info(payload)
    weekday_business_hours_raw = normalize_weekday_business_hours_raw(payload)
    closed_dates = normalize_closed_dates(payload)

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
    store.set_message_tone(user_id, message_tone)
    store.set_repeat_customer_visit_threshold(
        user_id, repeat_customer_visit_threshold
    )
    store.set_faq_info(user_id, faq_info)
    store.set_weekday_business_hours_raw(user_id, weekday_business_hours_raw)
    store.set_closed_dates(user_id, closed_dates)

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
        message_tone=message_tone,
        repeat_customer_visit_threshold=repeat_customer_visit_threshold,
        faq_info=faq_info,
        weekday_business_hours_raw=weekday_business_hours_raw,
        closed_dates=closed_dates,
    )
