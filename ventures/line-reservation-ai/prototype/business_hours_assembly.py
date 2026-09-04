#!/usr/bin/env python3
"""business-hours-raw-to-searcher-assembly-design.md準拠。
store_settings_save_flow.pyに保存済みの営業時間raw値(業者向け設定フォームの生文字列・
生リスト)を、engine.AvailabilitySearcherが要求する分単位の構造化値へ変換する。

conversation-event-processor-assembly-design.md 4節の残課題(searcher組み立てに必要な
営業時間データをStoreSettingsStoreProtocol経由でどう読み出すか)への対応。
"""

from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from engine import AvailabilitySearcher  # noqa: E402
from store_settings_save_flow import StoreSettingsStoreProtocol  # noqa: E402

_CLOSED_SENTINEL = "定休日"
_SEGMENT_PATTERN = re.compile(r"^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$")


class BusinessHoursRawFormatError(ValueError):
    """raw値(business_hours_raw・weekday_business_hours_raw・closed_dates)の書式が
    不正な場合に送出する(design 4節)。"""


def _parse_hh_mm_to_minutes(hh: str, mm: str, original: str) -> int:
    hour = int(hh)
    minute = int(mm)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise BusinessHoursRawFormatError(f"時刻の値が範囲外です: {original!r}")
    return hour * 60 + minute


def parse_business_hours_segments(raw: str) -> list[tuple[int, int]]:
    """design 2節: カンマ区切りの"H:MM-H:MM"区間文字列を[(開始分,終了分), ...]へ変換する。
    区間同士の重複・逆転チェックはAvailabilitySearcher構築時の
    _normalize_business_hour_ranges()に委ね、ここでは書式のみを検証する。"""
    if not isinstance(raw, str) or not raw.strip():
        raise BusinessHoursRawFormatError("business_hours_rawが未設定です")
    segments = []
    for part in raw.split(","):
        part = part.strip()
        match = _SEGMENT_PATTERN.match(part)
        if not match:
            raise BusinessHoursRawFormatError(f"営業時間の書式が不正です: {part!r}")
        start_h, start_m, end_h, end_m = match.groups()
        start = _parse_hh_mm_to_minutes(start_h, start_m, part)
        end = _parse_hh_mm_to_minutes(end_h, end_m, part)
        segments.append((start, end))
    return segments


def parse_weekday_business_hours_raw(
    weekday_business_hours_raw: dict,
) -> tuple[dict[int, list[tuple[int, int]]], frozenset[int]]:
    """design 3節: "定休日"の曜日はclosed_weekdays側へ分離し、
    (曜日別上書きdict, 追加の終日休業曜日集合)を返す。"""
    overrides: dict[int, list[tuple[int, int]]] = {}
    extra_closed: set[int] = set()
    for weekday, raw_value in weekday_business_hours_raw.items():
        if raw_value == _CLOSED_SENTINEL:
            extra_closed.add(weekday)
        else:
            overrides[weekday] = parse_business_hours_segments(raw_value)
    return overrides, frozenset(extra_closed)


def parse_closed_dates(closed_dates_raw: list) -> frozenset[date]:
    """design 4節: "YYYY-MM-DD"文字列のリストをdateのfrozensetへ変換する。
    normalize_closed_dates()(store_settings_save_flow.py)は書式検証をしない方針のため、
    ここで初めて書式を検証する。"""
    parsed = set()
    for item in closed_dates_raw:
        try:
            parsed.add(date.fromisoformat(item))
        except (TypeError, ValueError) as exc:
            raise BusinessHoursRawFormatError(f"臨時休業日の書式が不正です: {item!r}") from exc
    return frozenset(parsed)


def build_availability_searcher_for_store(
    store_id: str,
    settings_store: StoreSettingsStoreProtocol,
    default_slot_interval_minutes: int = 30,
) -> AvailabilitySearcher:
    """design 4節: StoreSettingsStoreProtocol経由で読み出したraw値一式から
    AvailabilitySearcherを組み立てる最上位関数。business_hours_rawが未設定の店舗は
    オンボーディング未完了とみなし、BusinessHoursRawFormatErrorを送出する。"""
    business_hours = parse_business_hours_segments(settings_store.get_business_hours_raw(store_id))

    weekday_overrides, extra_closed_weekdays = parse_weekday_business_hours_raw(
        settings_store.get_weekday_business_hours_raw(store_id)
    )
    closed_weekdays = frozenset(settings_store.get_closed_weekdays(store_id)) | extra_closed_weekdays

    closed_dates = parse_closed_dates(settings_store.get_closed_dates(store_id))

    slot_interval_minutes = (
        settings_store.get_slot_interval_minutes(store_id) or default_slot_interval_minutes
    )

    return AvailabilitySearcher(
        business_hours=business_hours,
        slot_interval_minutes=slot_interval_minutes,
        closed_weekdays=closed_weekdays,
        weekday_business_hours=weekday_overrides,
        closed_dates=closed_dates,
    )
