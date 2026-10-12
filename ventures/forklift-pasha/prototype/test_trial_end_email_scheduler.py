#!/usr/bin/env python3
"""trial_end_email_scheduler.pyのテスト。
trial-end-notification-design.md 2節(B)経路・フェーズ132の設計指針(解約済み除外の優先度)を
検証する。"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from trial_end_email_scheduler import (  # noqa: E402
    ACCESS_URL_UNAVAILABLE_FALLBACK,
    EMAIL_SUBJECT,
    EmailDeliveryError,
    InMemoryEmailSenderClient,
    is_trial_end_email_due,
    render_trial_end_email_body,
    run_due_trial_end_emails,
    select_due_trial_end_emails,
    send_trial_end_emails,
)
from trial_management import TRIAL_PERIOD_DAYS, InMemoryFleetOperatorStore  # noqa: E402


class _FailingEmailSenderClient:
    def send_email(self, to_email: str, subject: str, body: str) -> None:
        raise EmailDeliveryError("simulated outage")


class _StaticAccessUrlProvider:
    def __init__(self, url: "str | None") -> None:
        self._url = url

    def get_access_url(self, internal_id: str) -> "str | None":
        return self._url


class IsTrialEndEmailDueTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 10, 12, 7, 0, 0)
        self.store = InMemoryFleetOperatorStore()
        self.store.set_email("fo_1", "owner1@example.com")

    def test_exactly_30_days_elapsed_is_due(self) -> None:
        self.store.set_trial_start_at("fo_1", self.now - timedelta(days=TRIAL_PERIOD_DAYS))
        self.assertTrue(is_trial_end_email_due("fo_1", self.now, self.store))

    def test_31_days_elapsed_is_due(self) -> None:
        self.store.set_trial_start_at("fo_1", self.now - timedelta(days=31))
        self.assertTrue(is_trial_end_email_due("fo_1", self.now, self.store))

    def test_29_days_elapsed_is_not_due(self) -> None:
        self.store.set_trial_start_at("fo_1", self.now - timedelta(days=29))
        self.assertFalse(is_trial_end_email_due("fo_1", self.now, self.store))

    def test_trial_start_at_unset_is_not_due(self) -> None:
        self.assertFalse(is_trial_end_email_due("fo_1", self.now, self.store))

    def test_already_notified_is_not_due(self) -> None:
        # (A)経路(生成回数到達)で既に通知済みの場合は(B)経路側で再通知しない。
        self.store.set_trial_start_at("fo_1", self.now - timedelta(days=40))
        self.store.set_trial_end_notified_at("fo_1", self.now - timedelta(days=1))
        self.assertFalse(is_trial_end_email_due("fo_1", self.now, self.store))

    def test_canceled_is_excluded_even_if_period_elapsed(self) -> None:
        # フェーズ132の設計指針: is_subscription_canceled()を最優先で評価し即時除外する。
        self.store.set_trial_start_at("fo_1", self.now - timedelta(days=40))
        self.store.set_canceled_at("fo_1", self.now - timedelta(days=2))
        self.assertFalse(is_trial_end_email_due("fo_1", self.now, self.store))


class SelectDueTrialEndEmailsTest(unittest.TestCase):
    def test_filters_and_preserves_order(self) -> None:
        now = datetime(2026, 10, 12, 7, 0, 0)
        store = InMemoryFleetOperatorStore()
        for internal_id in ("fo_1", "fo_2", "fo_3"):
            store.set_email(internal_id, f"{internal_id}@example.com")
        store.set_trial_start_at("fo_1", now - timedelta(days=40))  # due
        store.set_trial_start_at("fo_2", now - timedelta(days=5))  # not due(期間未到達)
        store.set_trial_start_at("fo_3", now - timedelta(days=35))  # due
        self.assertEqual(
            select_due_trial_end_emails(["fo_1", "fo_2", "fo_3"], now, store),
            ["fo_1", "fo_3"],
        )


class RenderTrialEndEmailBodyTest(unittest.TestCase):
    def test_includes_generation_count_and_access_url(self) -> None:
        body = render_trial_end_email_body(3, "fo_1", _StaticAccessUrlProvider("https://example.com/f/tok123"))
        self.assertIn("これまでの点検記録整形実績: 3回", body)
        self.assertIn("https://example.com/f/tok123", body)

    def test_falls_back_when_provider_is_none(self) -> None:
        body = render_trial_end_email_body(0, "fo_1", None)
        self.assertIn(ACCESS_URL_UNAVAILABLE_FALLBACK, body)

    def test_falls_back_when_provider_returns_falsy(self) -> None:
        body = render_trial_end_email_body(0, "fo_1", _StaticAccessUrlProvider(None))
        self.assertIn(ACCESS_URL_UNAVAILABLE_FALLBACK, body)


class SendTrialEndEmailsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 10, 12, 7, 0, 0)
        self.store = InMemoryFleetOperatorStore()

    def test_sends_and_marks_notified(self) -> None:
        self.store.set_email("fo_1", "owner1@example.com")
        self.store.set_trial_start_at("fo_1", self.now - timedelta(days=31))
        client = InMemoryEmailSenderClient()

        result = send_trial_end_emails(["fo_1"], self.now, self.store, client)

        self.assertEqual(result.sent, ["fo_1"])
        self.assertEqual(len(client.sent), 1)
        to_email, subject, _body = client.sent[0]
        self.assertEqual(to_email, "owner1@example.com")
        self.assertEqual(subject, EMAIL_SUBJECT)
        self.assertEqual(self.store.get_trial_end_notified_at("fo_1"), self.now)

    def test_not_due_is_skipped_and_not_sent(self) -> None:
        self.store.set_email("fo_1", "owner1@example.com")
        self.store.set_trial_start_at("fo_1", self.now - timedelta(days=5))
        client = InMemoryEmailSenderClient()

        result = send_trial_end_emails(["fo_1"], self.now, self.store, client)

        self.assertEqual(result.sent, [])
        self.assertEqual(client.sent, [])
        self.assertIsNone(self.store.get_trial_end_notified_at("fo_1"))

    def test_missing_email_is_skipped_and_recorded(self) -> None:
        # set_emailを呼ばないため対象外(全事業者は初回登録時にemail必須のため通常発生
        # しないが、安全策としての挙動を確認する)。
        self.store.set_trial_start_at("fo_1", self.now - timedelta(days=31))
        client = InMemoryEmailSenderClient()

        result = send_trial_end_emails(["fo_1"], self.now, self.store, client)

        self.assertEqual(result.skipped_no_email, ["fo_1"])
        self.assertEqual(client.sent, [])
        self.assertIsNone(self.store.get_trial_end_notified_at("fo_1"))

    def test_delivery_failure_does_not_mark_notified(self) -> None:
        self.store.set_email("fo_1", "owner1@example.com")
        self.store.set_trial_start_at("fo_1", self.now - timedelta(days=31))

        result = send_trial_end_emails(
            ["fo_1"], self.now, self.store, _FailingEmailSenderClient()
        )

        self.assertEqual(result.failed, ["fo_1"])
        self.assertIsNone(self.store.get_trial_end_notified_at("fo_1"))

    def test_canceled_operator_is_not_sent(self) -> None:
        self.store.set_email("fo_1", "owner1@example.com")
        self.store.set_trial_start_at("fo_1", self.now - timedelta(days=31))
        self.store.set_canceled_at("fo_1", self.now - timedelta(days=1))
        client = InMemoryEmailSenderClient()

        result = send_trial_end_emails(["fo_1"], self.now, self.store, client)

        self.assertEqual(result.sent, [])
        self.assertEqual(client.sent, [])


class RunDueTrialEndEmailsTest(unittest.TestCase):
    def test_enumerates_all_internal_ids_from_store(self) -> None:
        now = datetime(2026, 10, 12, 7, 0, 0)
        store = InMemoryFleetOperatorStore()
        store.set_email("fo_1", "owner1@example.com")
        store.set_trial_start_at("fo_1", now - timedelta(days=31))
        store.set_email("fo_2", "owner2@example.com")
        store.set_trial_start_at("fo_2", now - timedelta(days=5))
        client = InMemoryEmailSenderClient()

        result = run_due_trial_end_emails(store, now, client)

        self.assertEqual(result.sent, ["fo_1"])
        self.assertEqual(len(client.sent), 1)


if __name__ == "__main__":
    unittest.main()
