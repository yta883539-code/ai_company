#!/usr/bin/env python3
"""prototype/cloud_function_webhook.py の自動テストスイート(unittest、外部ライブラリ非依存)。

実行方法: python3 -m unittest test_cloud_function_webhook -v
          (prototype/ディレクトリで実行)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cloud_function_webhook import (  # noqa: E402
    InMemoryTaskQueueClient,
    handle_webhook_event,
    make_task_name,
    render_enqueue_failed_owner_notification,
    verify_line_signature,
    webhook_receiver,
)

CHANNEL_SECRET = "test-secret"


class _AlwaysFailingTaskQueueClient:
    """Cloud Tasksのクォータ超過・一時的なネットワーク障害等を模す(TaskAlreadyExistsError以外)。"""

    def create_task(self, task_name: str, payload: dict) -> None:
        raise RuntimeError("simulated transient Cloud Tasks failure")


def _signed_body(events: list[dict]) -> tuple[bytes, str]:
    body = json.dumps({"events": events}).encode("utf-8")
    signature = base64.b64encode(
        hmac.new(CHANNEL_SECRET.encode("utf-8"), body, hashlib.sha256).digest()
    ).decode("utf-8")
    return body, signature


class MakeTaskNameTests(unittest.TestCase):
    def test_derives_deterministic_name_from_webhook_event_id(self):
        self.assertEqual(
            make_task_name("01J8ZC9Q1QK7X3S6VN9R2E4T8P"),
            "line-event-01J8ZC9Q1QK7X3S6VN9R2E4T8P",
        )

    def test_same_event_id_yields_same_task_name(self):
        self.assertEqual(make_task_name("abc123"), make_task_name("abc123"))

    def test_rejects_empty_event_id(self):
        with self.assertRaises(ValueError):
            make_task_name("")

    def test_rejects_disallowed_characters(self):
        with self.assertRaises(ValueError):
            make_task_name("has a space")


class HandleWebhookEventTests(unittest.TestCase):
    def setUp(self):
        self.queue = InMemoryTaskQueueClient()

    def test_enqueues_normal_event(self):
        event = {"webhookEventId": "E1", "deliveryContext": {"isRedelivery": False}}
        result = handle_webhook_event(event, self.queue)
        self.assertTrue(result.enqueued)
        self.assertEqual(result.reason, "enqueued")
        self.assertIn("line-event-E1", self.queue.created)

    def test_skips_redelivery_without_enqueueing(self):
        event = {"webhookEventId": "E2", "deliveryContext": {"isRedelivery": True}}
        result = handle_webhook_event(event, self.queue)
        self.assertFalse(result.enqueued)
        self.assertEqual(result.reason, "skipped_redelivery")
        self.assertEqual(self.queue.created, {})

    def test_second_call_with_same_event_id_is_deduplicated(self):
        event = {"webhookEventId": "E3", "deliveryContext": {"isRedelivery": False}}
        first = handle_webhook_event(event, self.queue)
        second = handle_webhook_event(event, self.queue)
        self.assertTrue(first.enqueued)
        self.assertFalse(second.enqueued)
        self.assertEqual(second.reason, "skipped_duplicate_task")
        self.assertEqual(len(self.queue.created), 1)

    def test_missing_delivery_context_is_treated_as_not_redelivery(self):
        event = {"webhookEventId": "E4"}
        result = handle_webhook_event(event, self.queue)
        self.assertTrue(result.enqueued)

    def test_missing_webhook_event_id_raises(self):
        with self.assertRaises(ValueError):
            handle_webhook_event({"type": "message"}, self.queue)

    def test_enqueue_failure_other_than_duplicate_is_given_up_not_raised(self):
        # enqueue-fallback-owner-notification-design.md(本venture版)2節準拠。
        # TaskAlreadyExistsError以外の例外(クォータ超過等)は呼び出し元へ伝播させず、
        # そのイベントの処理を断念する("enqueue_failed")。他venture版のような同期
        # フォールバックは行わない(Function A単一責務設計を破るため)。
        event = {"webhookEventId": "E5", "deliveryContext": {"isRedelivery": False}}
        result = handle_webhook_event(event, _AlwaysFailingTaskQueueClient())
        self.assertFalse(result.enqueued)
        self.assertEqual(result.reason, "enqueue_failed")
        self.assertEqual(result.webhook_event_id, "E5")


class VerifyLineSignatureTests(unittest.TestCase):
    def test_valid_signature_passes(self):
        body, signature = _signed_body([{"webhookEventId": "E1"}])
        self.assertTrue(verify_line_signature(body, signature, CHANNEL_SECRET))

    def test_invalid_signature_fails(self):
        body, _ = _signed_body([{"webhookEventId": "E1"}])
        self.assertFalse(verify_line_signature(body, "not-the-real-signature", CHANNEL_SECRET))

    def test_missing_signature_header_fails(self):
        body, _ = _signed_body([{"webhookEventId": "E1"}])
        self.assertFalse(verify_line_signature(body, None, CHANNEL_SECRET))

    def test_wrong_channel_secret_fails(self):
        body, signature = _signed_body([{"webhookEventId": "E1"}])
        self.assertFalse(verify_line_signature(body, signature, "wrong-secret"))


class WebhookReceiverTests(unittest.TestCase):
    def setUp(self):
        self.queue = InMemoryTaskQueueClient()

    def test_valid_signature_returns_200_and_enqueues_events(self):
        events = [
            {"webhookEventId": "E1", "deliveryContext": {"isRedelivery": False}},
            {"webhookEventId": "E2", "deliveryContext": {"isRedelivery": False}},
        ]
        body, signature = _signed_body(events)
        result = webhook_receiver(body, signature, CHANNEL_SECRET, events, self.queue)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(result.results), 2)
        self.assertEqual(len(self.queue.created), 2)

    def test_invalid_signature_returns_401_without_enqueueing(self):
        events = [{"webhookEventId": "E1", "deliveryContext": {"isRedelivery": False}}]
        body, _ = _signed_body(events)
        result = webhook_receiver(body, "bogus", CHANNEL_SECRET, events, self.queue)
        self.assertEqual(result.status_code, 401)
        self.assertEqual(result.results, [])
        self.assertEqual(self.queue.created, {})

    def test_line_retry_after_lost_200_is_deduplicated_at_queue_level(self):
        events = [{"webhookEventId": "E1", "deliveryContext": {"isRedelivery": False}}]
        body, signature = _signed_body(events)
        first = webhook_receiver(body, signature, CHANNEL_SECRET, events, self.queue)
        second = webhook_receiver(body, signature, CHANNEL_SECRET, events, self.queue)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(first.results[0].enqueued)
        self.assertFalse(second.results[0].enqueued)
        self.assertEqual(second.results[0].reason, "skipped_duplicate_task")

    def test_malformed_event_is_skipped_but_response_is_still_200(self):
        events = [
            {"type": "message"},  # webhookEventId欠落(通常発生しない異常系)
            {"webhookEventId": "E2", "deliveryContext": {"isRedelivery": False}},
        ]
        body, signature = _signed_body(events)
        result = webhook_receiver(body, signature, CHANNEL_SECRET, events, self.queue)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(result.results), 1)
        self.assertEqual(result.results[0].webhook_event_id, "E2")

    def test_destination_is_copied_into_each_enqueued_payload(self):
        # store-id-resolution-and-owner-identity-design.md準拠。Cloud Function B
        # (cloud_function_process_event.pyのresolve_store_id_from_destination())が
        # デキュー後にstoreIdを解決できるよう、Cloud Function Aの時点で各イベントの
        # payloadにdestinationを複製しておく必要がある。
        events = [
            {"webhookEventId": "E1", "deliveryContext": {"isRedelivery": False}},
            {"webhookEventId": "E2", "deliveryContext": {"isRedelivery": False}},
        ]
        body, signature = _signed_body(events)
        result = webhook_receiver(
            body, signature, CHANNEL_SECRET, events, self.queue, destination="Uofficialaccount123"
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(
            self.queue.created["line-event-E1"]["destination"], "Uofficialaccount123"
        )
        self.assertEqual(
            self.queue.created["line-event-E2"]["destination"], "Uofficialaccount123"
        )
        # 呼び出し元が渡した元のeventsリストの要素自体は変更しない(webhook_receiver内で
        # コピーしてから複製している)。
        self.assertNotIn("destination", events[0])

    def test_destination_omitted_keeps_previous_behavior(self):
        # destination未指定(既存呼び出し元との後方互換)の場合はキー自体を付与しない。
        events = [{"webhookEventId": "E1", "deliveryContext": {"isRedelivery": False}}]
        body, signature = _signed_body(events)
        result = webhook_receiver(body, signature, CHANNEL_SECRET, events, self.queue)
        self.assertEqual(result.status_code, 200)
        self.assertNotIn("destination", self.queue.created["line-event-E1"])

    def test_enqueue_failures_are_aggregated_but_response_is_still_200(self):
        # enqueue-fallback-owner-notification-design.md(本venture版)3節準拠。
        # 200は維持しつつ(LINE側の不要な再送連鎖を避ける)、失敗したwebhookEventIdを
        # WebhookReceiverResult.enqueue_failed_webhook_event_idsへ集約する。
        events = [
            {"webhookEventId": "E1", "deliveryContext": {"isRedelivery": False}},
            {"webhookEventId": "E2", "deliveryContext": {"isRedelivery": False}},
        ]
        body, signature = _signed_body(events)
        result = webhook_receiver(
            body, signature, CHANNEL_SECRET, events, _AlwaysFailingTaskQueueClient()
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(result.results), 2)
        self.assertTrue(all(r.reason == "enqueue_failed" for r in result.results))
        self.assertEqual(result.enqueue_failed_webhook_event_ids, ["E1", "E2"])

    def test_enqueue_failed_webhook_event_ids_empty_when_no_failures(self):
        events = [{"webhookEventId": "E1", "deliveryContext": {"isRedelivery": False}}]
        body, signature = _signed_body(events)
        result = webhook_receiver(body, signature, CHANNEL_SECRET, events, self.queue)
        self.assertEqual(result.enqueue_failed_webhook_event_ids, [])


class RenderEnqueueFailedOwnerNotificationTests(unittest.TestCase):
    # enqueue-fallback-owner-notification-design.md(本venture版)4節で確定した(a)案
    # (HTTPハンドラ経由の即時通知)が使う文言テンプレートの検証。

    def test_empty_list_still_renders_zero_count(self):
        text = render_enqueue_failed_owner_notification([])
        self.assertIn("件数: 0件", text)
        self.assertIn("webhookEventId: \n", text)

    def test_few_ids_are_all_listed_without_truncation(self):
        text = render_enqueue_failed_owner_notification(["E1", "E2"])
        self.assertIn("件数: 2件", text)
        self.assertIn("webhookEventId: E1, E2", text)
        self.assertNotIn("他", text)

    def test_exactly_five_ids_are_not_truncated(self):
        ids = [f"E{i}" for i in range(1, 6)]
        text = render_enqueue_failed_owner_notification(ids)
        self.assertIn("件数: 5件", text)
        self.assertIn("webhookEventId: E1, E2, E3, E4, E5", text)
        self.assertNotIn("他", text)

    def test_more_than_five_ids_are_truncated_with_remainder_count(self):
        ids = [f"E{i}" for i in range(1, 8)]  # 7件
        text = render_enqueue_failed_owner_notification(ids)
        self.assertIn("件数: 7件", text)
        self.assertIn("webhookEventId: E1, E2, E3, E4, E5 ...他2件", text)


if __name__ == "__main__":
    unittest.main()
