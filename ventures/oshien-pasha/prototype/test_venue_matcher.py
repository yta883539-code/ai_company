#!/usr/bin/env python3
"""venue_matcher.pyのロジック検証(他prototypeテストと同じ素朴なassertベース形式)。

schema/venue-master.json・schema/ambiguity-watchlist.jsonの実データを読み込んで検証する
(フィクスチャを別途用意せず、実運用データとの整合をそのまま確認する方針)。
"""

from __future__ import annotations

import json
from pathlib import Path

from venue_matcher import match_venue

PASS = 0
FAIL = 0

BASE_DIR = Path(__file__).parent.parent


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL: {label}")


def _load_master():
    with open(BASE_DIR / "schema" / "venue-master.json", encoding="utf-8") as f:
        return json.load(f)


def _load_watchlist():
    with open(BASE_DIR / "schema" / "ambiguity-watchlist.json", encoding="utf-8") as f:
        return json.load(f)


def test_exact_match() -> None:
    master = _load_master()
    result = match_venue("東京ドーム", master)
    check("exact match: venue_matched is True", result["venue_matched"] is True)
    check("exact match: confidence is exact", result["match_confidence"] == "exact")
    check(
        "exact match: matched_canonical_name is 東京ドーム",
        result["matched_canonical_name"] == "東京ドーム",
    )
    check(
        "exact match: nearest_station_note mentions 水道橋",
        "水道橋" in result["nearest_station_note"],
    )


def test_exact_match_normalizes_fullwidth_space() -> None:
    master = _load_master()
    # バンテリンドーム ナゴヤ(canonical_name自体が半角スペースを含む)に対して、
    # 全角スペース入力がNFKC正規化で半角に揺れても一致することを確認する。
    result = match_venue("バンテリンドーム　ナゴヤ", master)
    check(
        "fullwidth-space input normalizes to match a canonical name containing a space",
        result["venue_matched"] is True and result["match_confidence"] == "exact",
    )


def test_alias_match() -> None:
    master = _load_master()
    result = match_venue("ナゴヤドーム", master)
    check("alias match: venue_matched is True", result["venue_matched"] is True)
    check("alias match: confidence is alias", result["match_confidence"] == "alias")
    check(
        "alias match: resolves to canonical name バンテリンドーム ナゴヤ",
        result["matched_canonical_name"] == "バンテリンドーム ナゴヤ",
    )


def test_ambiguity_watchlist_takes_precedence_over_partial_match() -> None:
    master = _load_master()
    watchlist = _load_watchlist()
    # "日本ガイシ"単独は、どの会場のcanonical_name/aliasにも完全一致しない(登録済み
    # エイリアスは「日本ガイシホール」等、より長い文字列のため)。混同注意リスト照合が
    # なければ部分一致フォールバックに流れてしまう入力を使って、手順3.5が先に効くことを確認する。
    result = match_venue("日本ガイシ", master, watchlist)
    check(
        "ambiguous input stays venue_matched=False (no overconfident guess)",
        result["venue_matched"] is False,
    )
    check(
        "ambiguous input note warns about the two distinct facilities",
        "別施設" in result["nearest_station_note"],
    )
    check(
        "ambiguous input does not get a confident matched_canonical_name",
        result["matched_canonical_name"] is None,
    )


def test_partial_match_fallback_is_tentative() -> None:
    master = _load_master()
    result = match_venue("ナゴヤドーム前", master)
    check(
        "partial match fallback: venue_matched stays False (conservative)",
        result["venue_matched"] is False,
    )
    check(
        "partial match fallback: confidence is partial",
        result["match_confidence"] == "partial",
    )
    check(
        "partial match fallback: note hedges with 断定できません",
        "断定できません" in result["nearest_station_note"],
    )


def test_no_match() -> None:
    master = _load_master()
    result = match_venue("どこかの体育館", master)
    check("no match: venue_matched is False", result["venue_matched"] is False)
    check("no match: confidence is none", result["match_confidence"] == "none")
    check(
        "no match: generic guidance note returned",
        "一般的な調べ方" in result["nearest_station_note"],
    )


def test_operational_status_note_for_closed_venue() -> None:
    master = _load_master()
    closed_venues = [
        v for v in master["venues"] if v.get("operational_status") == "closed"
    ]
    check("fixture has at least one closed venue to exercise", len(closed_venues) >= 1)
    if not closed_venues:
        return
    venue = closed_venues[0]
    result = match_venue(venue["canonical_name"], master)
    check(
        "closed venue: operational_status_note is non-null",
        result["operational_status_note"] is not None,
    )
    check(
        "closed venue: operational_status_note advises checking organizer info",
        "主催者発表" in result["operational_status_note"],
    )


def test_operational_status_note_is_none_for_active_venue() -> None:
    master = _load_master()
    result = match_venue("東京ドーム", master)
    check(
        "active venue: operational_status_note is None",
        result["operational_status_note"] is None,
    )


if __name__ == "__main__":
    test_exact_match()
    test_exact_match_normalizes_fullwidth_space()
    test_alias_match()
    test_ambiguity_watchlist_takes_precedence_over_partial_match()
    test_partial_match_fallback_is_tentative()
    test_no_match()
    test_operational_status_note_for_closed_venue()
    test_operational_status_note_is_none_for_active_venue()
    print(f"PASS={PASS} FAIL={FAIL}")
