#!/usr/bin/env python3
"""liff_plan_card_action.pyのテスト。liff-plan-selection-ui-wireframe.mdの各プラン
カードのボタン遷移先の出し分けを検証する。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from liff_plan_card_action import resolve_plan_card_action  # noqa: E402


class ResolvePlanCardActionTest(unittest.TestCase):
    def test_trial_user_starts_checkout_for_any_card(self) -> None:
        self.assertEqual(
            resolve_plan_card_action(None, "ライト"), "start_checkout"
        )
        self.assertEqual(
            resolve_plan_card_action(None, "セッター複数"), "start_checkout"
        )

    def test_current_plan_card_is_marked_current(self) -> None:
        self.assertEqual(
            resolve_plan_card_action("スタンダード", "スタンダード"), "current_plan"
        )

    def test_other_plan_card_opens_portal_for_upgrade(self) -> None:
        self.assertEqual(
            resolve_plan_card_action("ライト", "スタンダード"), "open_portal"
        )

    def test_other_plan_card_opens_portal_for_downgrade(self) -> None:
        self.assertEqual(
            resolve_plan_card_action("セッター複数", "ライト"), "open_portal"
        )


if __name__ == "__main__":
    unittest.main()
