#!/usr/bin/env python3
"""history_export.pyの単体テスト。schema/validate_test_cases.pyのTEST_CASESフィクスチャを
そのまま流用し、机上設計してきたhistory_rowsの期待出力とCSV変換結果の整合を確認する。"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "schema"))

from history_export import (  # noqa: E402
    HISTORY_CSV_HEADER,
    history_row_to_csv_fields,
    history_rows_to_csv_text,
)
from validate_test_cases import TEST_CASES  # noqa: E402


class HistoryRowToCsvFieldsTest(unittest.TestCase):
    def test_basic_row(self):
        row = TEST_CASES["G1_basic"]["history_rows"][0]
        fields = history_row_to_csv_fields(row)
        self.assertEqual(
            fields,
            ["2026-08-07", "エリアA", "黄テープ", "8", "ダイナミック、ムーブ重視"],
        )

    def test_null_date_and_count_use_placeholders(self):
        row = TEST_CASES["G3_count_and_date_unextractable"]["history_rows"][0]
        fields = history_row_to_csv_fields(row)
        self.assertEqual(fields[0], "未記入")
        self.assertEqual(fields[3], "不明")

    def test_no_feature_keywords_yields_empty_string(self):
        row = {
            "revision_date": "2026-08-08",
            "area": "エリアZ",
            "tape_color_or_grade_band": "青テープ",
            "count": 2,
            "feature_keywords": [],
        }
        fields = history_row_to_csv_fields(row)
        self.assertEqual(fields[4], "")


class HistoryRowsToCsvTextTest(unittest.TestCase):
    def test_multi_area_produces_header_plus_n_rows(self):
        history_rows = TEST_CASES["G4_multi_area_single_memo"]["history_rows"]
        text = history_rows_to_csv_text(history_rows)
        lines = text.strip("\n").split("\n")
        self.assertEqual(len(lines), 1 + len(history_rows))
        self.assertIn(",".join(HISTORY_CSV_HEADER), lines[0])

    def test_none_or_empty_returns_empty_string(self):
        self.assertEqual(history_rows_to_csv_text(None), "")
        self.assertEqual(history_rows_to_csv_text([]), "")

    def test_all_generated_fixtures_produce_expected_row_count(self):
        for case_id, instance in TEST_CASES.items():
            if instance.get("status") != "generated":
                continue
            history_rows = instance["history_rows"]
            text = history_rows_to_csv_text(history_rows)
            lines = text.strip("\n").split("\n")
            self.assertEqual(len(lines), 1 + len(history_rows), msg=f"case={case_id}")


if __name__ == "__main__":
    unittest.main()
