#!/usr/bin/env python3
"""venue_matcher.pyのロジック検証(他prototypeテストと同じ素朴なassertベース形式)。

schema/venue-master.json・schema/ambiguity-watchlist.jsonの実データを読み込んで検証する
(フィクスチャを別途用意せず、実運用データとの整合をそのまま確認する方針)。
"""

from __future__ import annotations

import json
from pathlib import Path

from venue_matcher import _station_note, match_venue

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


def test_ambiguity_watchlist_ariake() -> None:
    master = _load_master()
    watchlist = _load_watchlist()
    # "有明"単独は、どの会場のcanonical_name/aliasにも完全一致しない(有明アリーナの
    # canonical_nameは「有明アリーナ」でありaliasesも空のため)。有明コロシアムは
    # venue-master.json未登録のため、混同注意リスト照合(手順3.5)がなければ部分一致
    # フォールバックに流れてしまう入力を使って、本フェーズ追加分が機能することを確認する。
    result = match_venue("有明", master, watchlist)
    check(
        "ariake ambiguous input stays venue_matched=False (no overconfident guess)",
        result["venue_matched"] is False,
    )
    check(
        "ariake ambiguous input note warns about the two distinct facilities",
        "別施設" in result["nearest_station_note"],
    )
    check(
        "ariake ambiguous input does not get a confident matched_canonical_name",
        result["matched_canonical_name"] is None,
    )


def test_ambiguity_watchlist_osakajo() -> None:
    master = _load_master()
    watchlist = _load_watchlist()
    # "大阪城"単独は、どの会場のcanonical_name/aliasにも完全一致しない(大阪城ホールの
    # canonical_nameは「大阪城ホール」でありaliasesも空のため)。大阪城野外音楽堂は
    # venue-master.json未登録のため、混同注意リスト照合(手順3.5)がなければ部分一致
    # フォールバックに流れてしまう入力を使って、本フェーズ追加分が機能することを確認する。
    result = match_venue("大阪城", master, watchlist)
    check(
        "osakajo ambiguous input stays venue_matched=False (no overconfident guess)",
        result["venue_matched"] is False,
    )
    check(
        "osakajo ambiguous input note warns about the two distinct facilities",
        "別施設" in result["nearest_station_note"],
    )
    check(
        "osakajo ambiguous input does not get a confident matched_canonical_name",
        result["matched_canonical_name"] is None,
    )


def test_ambiguity_watchlist_yokohama_buntai() -> None:
    master = _load_master()
    watchlist = _load_watchlist()
    # 旧称「横浜文化体育館」は再整備で「横浜BUNTAI」「横浜武道館」の2施設に分かれ、いずれも
    # venue-master.json未登録(両方registered_in_venue_master=false)。混同注意リスト照合
    # (手順3.5)がなければ部分一致フォールバックに流れてしまう入力で、本フェーズ追加分が
    # 機能することを確認する。
    result = match_venue("横浜文化体育館", master, watchlist)
    check(
        "yokohama buntai ambiguous input stays venue_matched=False (no overconfident guess)",
        result["venue_matched"] is False,
    )
    check(
        "yokohama buntai ambiguous input note warns about the two distinct facilities",
        "別施設" in result["nearest_station_note"],
    )
    check(
        "yokohama buntai ambiguous input does not get a confident matched_canonical_name",
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
        "partial match fallback: note uses 文例A (single candidate) wording",
        "断定はできません" in result["nearest_station_note"]
        and "バンテリンドーム ナゴヤ" in result["nearest_station_note"],
    )


def test_partial_match_fallback_with_multiple_candidates() -> None:
    master = _load_master()
    # 「ドルフィンズアリーナ」(愛知県体育館のalias)と「ビッグハット」(長野ビッグハットのalias)
    # を両方含む入力で、文例B(候補複数件)に分岐することを確認する。
    result = match_venue("ドルフィンズアリーナからビッグハットへ移動", master)
    check(
        "partial match (multiple): venue_matched stays False",
        result["venue_matched"] is False,
    )
    check(
        "partial match (multiple): confidence is partial",
        result["match_confidence"] == "partial",
    )
    check(
        "partial match (multiple): note uses 文例B (multiple candidates) wording",
        "本サービスでは判別できません" in result["nearest_station_note"],
    )
    check(
        "partial match (multiple): both candidate canonical names appear",
        "愛知県体育館" in result["nearest_station_note"]
        and "長野ビッグハット" in result["nearest_station_note"],
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


def test_station_note_uses_access_note_when_car_or_bus() -> None:
    # access-mode-alternative-to-walk-minutes-note-design.md(フェーズ157)の疑似コードの
    # 実コード化を検証する。venue-master.json側の既存51件はいずれもaccess_mode未設定
    # (="walk"扱い)のため、ここでは設計のみ先行していたcar_or_bus分岐を直接構築したdictで検証する。
    venue = {
        "nearest_station": "JR高知駅",
        "access_mode": "car_or_bus",
        "access_note": "車で7分(公式の徒歩分数情報は確認できていません)",
        "walk_minutes_note": "徒歩20〜30分程度",
    }
    check(
        "car_or_bus: access_note is used instead of walk_minutes_note",
        _station_note(venue)
        == "JR高知駅(車で7分(公式の徒歩分数情報は確認できていません))",
    )


def test_station_note_falls_back_to_walk_minutes_note_without_access_note() -> None:
    # access_mode="car_or_bus"でもaccess_note未設定の場合は、従来のwalk_minutes_note
    # (フォールバック文言含む)にフォールバックする設計〈同design.md〉を検証する。
    venue_with_walk_note = {
        "nearest_station": "JR高知駅",
        "access_mode": "car_or_bus",
        "walk_minutes_note": "徒歩20〜30分程度",
    }
    check(
        "car_or_bus without access_note: falls back to walk_minutes_note",
        _station_note(venue_with_walk_note) == "JR高知駅(徒歩20〜30分程度)",
    )
    venue_without_either = {"nearest_station": "JR高知駅", "access_mode": "car_or_bus"}
    check(
        "car_or_bus without access_note or walk_minutes_note: falls back to default label",
        _station_note(venue_without_either) == "JR高知駅(徒歩目安不明)",
    )


def test_station_note_default_access_mode_is_unaffected() -> None:
    # access_mode省略時(既存51件すべて)は後方互換のため挙動が変わらないことを確認する。
    venue = {"nearest_station": "JR水道橋駅", "walk_minutes_note": "徒歩5分前後"}
    check(
        "default access_mode (omitted): behavior unchanged",
        _station_note(venue) == "JR水道橋駅(徒歩5分前後)",
    )


if __name__ == "__main__":
    test_exact_match()
    test_exact_match_normalizes_fullwidth_space()
    test_alias_match()
    test_ambiguity_watchlist_takes_precedence_over_partial_match()
    test_ambiguity_watchlist_ariake()
    test_ambiguity_watchlist_osakajo()
    test_ambiguity_watchlist_yokohama_buntai()
    test_partial_match_fallback_is_tentative()
    test_partial_match_fallback_with_multiple_candidates()
    test_no_match()
    test_operational_status_note_for_closed_venue()
    test_operational_status_note_is_none_for_active_venue()
    test_station_note_uses_access_note_when_car_or_bus()
    test_station_note_falls_back_to_walk_minutes_note_without_access_note()
    test_station_note_default_access_mode_is_unaffected()
    print(f"PASS={PASS} FAIL={FAIL}")
