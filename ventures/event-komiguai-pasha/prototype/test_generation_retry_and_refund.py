import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generation_retry_and_refund import (  # noqa: E402
    GenerationError,
    InMemoryEmailSender,
    InMemoryRefundClient,
    process_generation_after_payment,
)
from stripe_webhook import CheckoutCompletionResult, InMemoryOneTimeDraftStore  # noqa: E402


def _proceed_result(
    draft_id="draft_abc",
    customer_email="organizer@example.com",
    payment_intent_id="pi_abc",
):
    return CheckoutCompletionResult(
        draft_id=draft_id,
        outcome="proceed_to_generation",
        customer_email=customer_email,
        checkout_session_id="cs_abc",
        payment_intent_id=payment_intent_id,
    )


class AlwaysSucceedsGenerator:
    def __init__(self, output=None):
        self.calls = 0
        self.output = output or {"status": "generated"}

    def __call__(self, draft_id: str) -> dict:
        self.calls += 1
        return self.output


class FailsThenSucceedsGenerator:
    """fail_count回だけGenerationErrorを送出し、以降は成功する(リトライ挙動の検証用)。"""

    def __init__(self, fail_count: int, output=None):
        self.fail_count = fail_count
        self.calls = 0
        self.output = output or {"status": "generated"}

    def __call__(self, draft_id: str) -> dict:
        self.calls += 1
        if self.calls <= self.fail_count:
            raise GenerationError("一時的なLLM API障害")
        return self.output


class AlwaysFailsGenerator:
    def __init__(self):
        self.calls = 0

    def __call__(self, draft_id: str) -> dict:
        self.calls += 1
        raise GenerationError("恒常的な生成失敗")


class ProcessGenerationAfterPaymentTest(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryOneTimeDraftStore()
        self.refund_client = InMemoryRefundClient()
        self.email_sender = InMemoryEmailSender()

    def test_not_applicable_when_outcome_is_not_proceed_to_generation(self):
        checkout_result = CheckoutCompletionResult(
            draft_id="draft_abc", outcome="already_processed"
        )
        generator = AlwaysSucceedsGenerator()
        result = process_generation_after_payment(
            checkout_result,
            generator,
            self.store,
            self.refund_client,
            self.email_sender,
        )
        self.assertEqual(result.outcome, "not_applicable")
        self.assertEqual(generator.calls, 0)
        self.assertEqual(self.refund_client.calls, [])

    def test_succeeds_on_first_attempt_no_retry(self):
        generator = AlwaysSucceedsGenerator({"status": "generated"})
        checkout_result = _proceed_result()
        result = process_generation_after_payment(
            checkout_result, generator, self.store, self.refund_client, self.email_sender
        )
        self.assertEqual(result.outcome, "generated")
        self.assertEqual(result.attempts, 1)
        self.assertEqual(generator.calls, 1)
        self.assertEqual(self.refund_client.calls, [])
        self.assertEqual(self.email_sender.sent, [])

    def test_succeeds_after_one_retry(self):
        generator = FailsThenSucceedsGenerator(fail_count=1)
        checkout_result = _proceed_result()
        result = process_generation_after_payment(
            checkout_result, generator, self.store, self.refund_client, self.email_sender
        )
        self.assertEqual(result.outcome, "generated")
        self.assertEqual(result.attempts, 2)
        self.assertEqual(generator.calls, 2)
        self.assertEqual(self.refund_client.calls, [])

    def test_succeeds_on_third_attempt_uses_up_both_retries(self):
        generator = FailsThenSucceedsGenerator(fail_count=2)
        checkout_result = _proceed_result()
        result = process_generation_after_payment(
            checkout_result, generator, self.store, self.refund_client, self.email_sender
        )
        self.assertEqual(result.outcome, "generated")
        self.assertEqual(result.attempts, 3)
        self.assertEqual(generator.calls, 3)

    def test_generation_status_is_written_to_store(self):
        self.store.seed(
            _seed_draft("draft_abc")
        )
        generator = AlwaysSucceedsGenerator({"status": "out_of_scope"})
        checkout_result = _proceed_result()
        process_generation_after_payment(
            checkout_result, generator, self.store, self.refund_client, self.email_sender
        )
        self.assertEqual(self.store.get("draft_abc").status, "out_of_scope")

    def test_exhausts_all_attempts_then_refunds_and_emails(self):
        self.store.seed(_seed_draft("draft_abc"))
        generator = AlwaysFailsGenerator()
        checkout_result = _proceed_result(payment_intent_id="pi_xyz")
        result = process_generation_after_payment(
            checkout_result,
            generator,
            self.store,
            self.refund_client,
            self.email_sender,
            retry_url="https://example.com/retry/draft_abc",
        )
        self.assertEqual(result.outcome, "refunded")
        self.assertEqual(result.attempts, 3)
        self.assertEqual(generator.calls, 3)
        self.assertEqual(self.refund_client.calls, ["pi_xyz"])
        self.assertEqual(self.store.get("draft_abc").status, "refunded")
        self.assertEqual(len(self.email_sender.sent), 1)
        sent = self.email_sender.sent[0]
        self.assertEqual(sent["to"], "organizer@example.com")
        self.assertEqual(sent["template_key"], "generation_failed_refund_email")
        self.assertEqual(sent["retry_url"], "https://example.com/retry/draft_abc")

    def test_draft_marked_generation_failed_before_refund_attempt(self):
        """返金自体が失敗するケースでも、途中経過として一度"generation_failed"を
        経由していること自体は常に成り立つ(design 3-2節の手順2→3の順序)。"""

        class RaisingRefundClient:
            def create_refund(self, payment_intent_id: str) -> dict:
                raise RuntimeError("stripe.error.InvalidRequestError: 返金可能期間を超過")

        self.store.seed(_seed_draft("draft_abc"))
        generator = AlwaysFailsGenerator()
        checkout_result = _proceed_result()
        result = process_generation_after_payment(
            checkout_result,
            generator,
            self.store,
            RaisingRefundClient(),
            self.email_sender,
        )
        self.assertEqual(result.outcome, "refund_failed")
        self.assertEqual(self.store.get("draft_abc").status, "generation_failed")
        self.assertEqual(self.email_sender.sent, [])
        self.assertTrue(any("返金API呼び出しが失敗しました" in w for w in result.warnings))

    def test_missing_payment_intent_id_skips_refund_defensively(self):
        self.store.seed(_seed_draft("draft_abc"))
        generator = AlwaysFailsGenerator()
        checkout_result = _proceed_result(payment_intent_id=None)
        result = process_generation_after_payment(
            checkout_result, generator, self.store, self.refund_client, self.email_sender
        )
        self.assertEqual(result.outcome, "refund_failed")
        self.assertEqual(self.refund_client.calls, [])
        self.assertEqual(self.store.get("draft_abc").status, "generation_failed")
        self.assertTrue(any("payment_intent_id" in w for w in result.warnings))

    def test_missing_customer_email_skips_notification_email(self):
        self.store.seed(_seed_draft("draft_abc"))
        generator = AlwaysFailsGenerator()
        checkout_result = _proceed_result(customer_email=None)
        result = process_generation_after_payment(
            checkout_result, generator, self.store, self.refund_client, self.email_sender
        )
        self.assertEqual(result.outcome, "refunded")
        self.assertEqual(self.email_sender.sent, [])
        self.assertTrue(any("customer_email" in w for w in result.warnings))


def _seed_draft(draft_id: str):
    from stripe_webhook import OneTimeDraft

    return OneTimeDraft(draft_id=draft_id, status="awaiting_payment")


if __name__ == "__main__":
    unittest.main()
