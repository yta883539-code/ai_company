#!/usr/bin/env python3
"""itinerary_draft_postprocessor.pyのロジック検証(他prototypeテストと同じ素朴なassert
ベース形式)。test_venue_matcher.pyと同様、フィクスチャを別途用意せず実運用データ
(schema/venue-master.json・schema/ambiguity-watchlist.json)との整合をそのまま確認する。
"""

from __future__ import annotations

import json
from pathlib import Path

from itinerary_draft_postprocessor import apply_venue_match_postprocessing

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


def test_none_itinerary_draft_passthrough() -> None:
    master = _load_master()
    updated, conflicts = apply_venue_match_postprocessing(None, master)
    check("None itinerary_draft stays None", updated is None)
    check("None itinerary_draft produces no conflicts", conflicts == [])


def test_exact_match_overwrites_llm_false_claim() -> None:
    master = _load_master()
    draft = [
        {
            "venue_name_input": "東京ドーム",
            "venue_matched": False,
            "nearest_station_note": "ダミー(LLMが誤って生成した値)",
            "lodging_area_candidates": ["後楽園周辺"],
            "transport_note": "ダミーのtransport_note",
        }
    ]
    updated, conflicts = apply_venue_match_postprocessing(draft, master)
    check("exact match overwrite: venue_matched becomes True", updated[0]["venue_matched"] is True)
    check(
        "exact match overwrite: nearest_station_note mentions 水道橋",
        "水道橋" in updated[0]["nearest_station_note"],
    )
    check(
        "exact match overwrite: lodging_area_candidates is untouched",
        updated[0]["lodging_area_candidates"] == ["後楽園周辺"],
    )
    check(
        "exact match overwrite: transport_note is untouched",
        updated[0]["transport_note"] == "ダミーのtransport_note",
    )
    check("exact match overwrite: one conflict recorded", len(conflicts) == 1)
    check(
        "exact match overwrite: conflict records llm_claimed_matched=False",
        conflicts[0]["llm_claimed_matched"] is False,
    )
    check(
        "exact match overwrite: conflict records matcher_matched=True",
        conflicts[0]["matcher_matched"] is True,
    )


def test_matching_llm_claim_produces_no_conflict() -> None:
    master = _load_master()
    draft = [
        {
            "venue_name_input": "東京ドーム",
            "venue_matched": True,
            "nearest_station_note": "ダミー(上書きされる想定の値)",
            "lodging_area_candidates": [],
            "transport_note": "",
        }
    ]
    updated, conflicts = apply_venue_match_postprocessing(draft, master)
    check("matching claim: venue_matched stays True", updated[0]["venue_matched"] is True)
    check("matching claim: no conflict recorded", conflicts == [])


def test_closed_venue_appends_operational_status_note() -> None:
    master = _load_master()
    draft = [
        {
            "venue_name_input": "愛知県体育館",
            "venue_matched": True,
            "nearest_station_note": "ダミー",
            "lodging_area_candidates": [],
            "transport_note": "",
        }
    ]
    updated, _ = apply_venue_match_postprocessing(draft, master)
    note = updated[0]["nearest_station_note"]
    check(
        "closed venue: nearest_station_note mentions original station info",
        "名城公園" in note or "ドルフィンズアリーナ" in note or len(note) > 0,
    )
    check(
        "closed venue: operational_status_note is appended",
        "稼働していない可能性があります" in note,
    )


def test_ambiguity_watchlist_entry_produces_no_conflict_when_llm_agrees() -> None:
    master = _load_master()
    watchlist = _load_watchlist()
    entries = watchlist.get("entries", [])
    if not entries:
        return
    ambiguous_input = entries[0]["ambiguous_input_pattern"]
    draft = [
        {
            "venue_name_input": ambiguous_input,
            "venue_matched": False,
            "nearest_station_note": "ダミー",
            "lodging_area_candidates": [],
            "transport_note": "",
        }
    ]
    updated, conflicts = apply_venue_match_postprocessing(draft, master, watchlist)
    check(
        "ambiguity watchlist entry: venue_matched stays False",
        updated[0]["venue_matched"] is False,
    )
    check("ambiguity watchlist entry: no conflict recorded", conflicts == [])


def test_multiple_venues_processed_independently() -> None:
    master = _load_master()
    draft = [
        {
            "venue_name_input": "東京ドーム",
            "venue_matched": True,
            "nearest_station_note": "x",
            "lodging_area_candidates": [],
            "transport_note": "",
        },
        {
            "venue_name_input": "存在しない架空会場名12345",
            "venue_matched": True,
            "nearest_station_note": "x",
            "lodging_area_candidates": [],
            "transport_note": "",
        },
    ]
    updated, conflicts = apply_venue_match_postprocessing(draft, master)
    check("multiple venues: two items returned", len(updated) == 2)
    check("multiple venues: first item matched", updated[0]["venue_matched"] is True)
    check("multiple venues: second item not matched", updated[1]["venue_matched"] is False)
    check("multiple venues: one conflict recorded (second item only)", len(conflicts) == 1)
    check(
        "multiple venues: conflict is for the unmatched venue",
        conflicts[0]["venue_name_input"] == "存在しない架空会場名12345",
    )


def main() -> int:
    test_none_itinerary_draft_passthrough()
    test_exact_match_overwrites_llm_false_claim()
    test_matching_llm_claim_produces_no_conflict()
    test_closed_venue_appends_operational_status_note()
    test_ambiguity_watchlist_entry_produces_no_conflict_when_llm_agrees()
    test_multiple_venues_processed_independently()
    print(f"PASS={PASS} FAIL={FAIL}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
