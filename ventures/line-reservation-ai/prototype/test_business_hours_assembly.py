#!/usr/bin/env python3
"""business_hours_assembly.pyの単体テスト。
business-hours-raw-to-searcher-assembly-design.mdで設計した、raw値からの
AvailabilitySearcher組み立てを検証する。"""

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from business_hours_assembly import (  # noqa: E402
    BusinessHoursRawFormatError,
    build_availability_searcher_for_store,
    parse_business_hours_segments,
    parse_closed_dates,
    parse_weekday_business_hours_raw,
)
from engine import AvailabilitySearcher  # noqa: E402
from store_settings_save_flow import InMemoryStoreSettingsStore  # noqa: E402


class ParseBusinessHoursSegmentsTest(unittest.TestCase):
    def test_single_segment(self):
        self.assertEqual(parse_business_hours_segments("10:00-19:00"), [(600, 1140)])

    def test_multiple_segments_comma_separated(self):
        self.assertEqual(
            parse_business_hours_segments("9:00-12:00,15:00-19:00"),
            [(540, 720), (900, 1140)],
        )

    def test_rejects_empty_string(self):
        with self.assertRaises(BusinessHoursRawFormatError):
            parse_business_hours_segments("")

    def test_rejects_malformed_segment(self):
        with self.assertRaises(BusinessHoursRawFormatError):
            parse_business_hours_segments("10時-19時")

    def test_rejects_out_of_range_hour(self):
        with self.assertRaises(BusinessHoursRawFormatError):
            parse_business_hours_segments("25:00-26:00")


class ParseWeekdayBusinessHoursRawTest(unittest.TestCase):
    def test_separates_closed_sentinel_from_overrides(self):
        overrides, extra_closed = parse_weekday_business_hours_raw(
            {5: "10:00-15:00", 6: "定休日"}
        )
        self.assertEqual(overrides, {5: [(600, 900)]})
        self.assertEqual(extra_closed, frozenset({6}))

    def test_empty_dict_returns_empty_results(self):
        overrides, extra_closed = parse_weekday_business_hours_raw({})
        self.assertEqual(overrides, {})
        self.assertEqual(extra_closed, frozenset())


class ParseClosedDatesTest(unittest.TestCase):
    def test_parses_iso_dates(self):
        self.assertEqual(
            parse_closed_dates(["2026-09-15", "2026-12-31"]),
            frozenset({date(2026, 9, 15), date(2026, 12, 31)}),
        )

    def test_rejects_malformed_date(self):
        with self.assertRaises(BusinessHoursRawFormatError):
            parse_closed_dates(["2026/09/15"])


class BuildAvailabilitySearcherForStoreTest(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryStoreSettingsStore()
        self.store_id = "store1"
        self.store.set_business_hours_raw(self.store_id, "10:00-19:00")

    def test_raises_when_business_hours_not_configured(self):
        empty_store = InMemoryStoreSettingsStore()
        with self.assertRaises(BusinessHoursRawFormatError):
            build_availability_searcher_for_store("unconfigured", empty_store)

    def test_builds_searcher_with_defaults_when_optional_fields_unset(self):
        searcher = build_availability_searcher_for_store(self.store_id, self.store)
        self.assertIsInstance(searcher, AvailabilitySearcher)

    def test_wires_closed_weekdays_and_weekday_overrides_and_closed_dates(self):
        self.store.set_closed_weekdays(self.store_id, [0])
        self.store.set_weekday_business_hours_raw(
            self.store_id, {5: "10:00-15:00", 6: "定休日"}
        )
        self.store.set_closed_dates(self.store_id, ["2026-09-15"])
        self.store.set_slot_interval_minutes(self.store_id, 45)

        searcher = build_availability_searcher_for_store(self.store_id, self.store)

        self.assertEqual(searcher._interval, 45)
        # 明示的なclosed_weekdays(月=0)と、weekday_business_hours_rawの"定休日"(日=6)の
        # 両方が合流していることを確認する(design 3節の和集合方針)。
        self.assertEqual(searcher._closed_weekdays, frozenset({0, 6}))
        self.assertEqual(searcher._weekday_business_hours, {5: [(600, 900)]})
        self.assertEqual(searcher._closed_dates, frozenset({date(2026, 9, 15)}))

    def test_falls_back_to_default_slot_interval_when_unset(self):
        searcher = build_availability_searcher_for_store(
            self.store_id, self.store, default_slot_interval_minutes=20
        )
        self.assertEqual(searcher._interval, 20)


if __name__ == "__main__":
    unittest.main()
