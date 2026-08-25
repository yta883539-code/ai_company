import hashlib
import hmac
import unittest

from stripe_webhook import verify_stripe_signature

SECRET = "whsec_test_secret"
PAYLOAD = b'{"id":"evt_1","type":"customer.subscription.deleted"}'
NOW = 1_700_000_000.0


def _sign(payload: bytes, secret: str, timestamp: int) -> str:
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()


def _header(payload: bytes, secret: str, timestamp: int, *, extra_v1=None, v0=None) -> str:
    parts = [f"t={timestamp}"]
    sig = _sign(payload, secret, timestamp)
    parts.append(f"v1={sig}")
    if extra_v1:
        parts.append(f"v1={extra_v1}")
    if v0:
        parts.append(f"v0={v0}")
    return ",".join(parts)


class VerifyStripeSignatureTest(unittest.TestCase):
    def test_valid_signature_within_tolerance_returns_true(self):
        timestamp = int(NOW)
        header = _header(PAYLOAD, SECRET, timestamp)
        self.assertTrue(verify_stripe_signature(PAYLOAD, header, SECRET, now=NOW))

    def test_missing_header_returns_false(self):
        self.assertFalse(verify_stripe_signature(PAYLOAD, None, SECRET, now=NOW))
        self.assertFalse(verify_stripe_signature(PAYLOAD, "", SECRET, now=NOW))

    def test_malformed_header_returns_false(self):
        self.assertFalse(
            verify_stripe_signature(PAYLOAD, "not-a-valid-header", SECRET, now=NOW)
        )
        self.assertFalse(
            verify_stripe_signature(PAYLOAD, "t=1700000000", SECRET, now=NOW)
        )
        self.assertFalse(
            verify_stripe_signature(PAYLOAD, "v1=deadbeef", SECRET, now=NOW)
        )

    def test_signature_mismatch_returns_false(self):
        timestamp = int(NOW)
        header = _header(PAYLOAD, "wrong_secret", timestamp)
        self.assertFalse(verify_stripe_signature(PAYLOAD, header, SECRET, now=NOW))

    def test_valid_signature_outside_tolerance_returns_false(self):
        timestamp = int(NOW) - 301
        header = _header(PAYLOAD, SECRET, timestamp)
        self.assertFalse(verify_stripe_signature(PAYLOAD, header, SECRET, now=NOW))

    def test_future_timestamp_outside_tolerance_returns_false(self):
        timestamp = int(NOW) + 301
        header = _header(PAYLOAD, SECRET, timestamp)
        self.assertFalse(verify_stripe_signature(PAYLOAD, header, SECRET, now=NOW))

    def test_secret_rotation_matches_any_v1_signature(self):
        timestamp = int(NOW)
        correct_sig = _sign(PAYLOAD, SECRET, timestamp)
        header = f"t={timestamp},v1=deadbeef,v1={correct_sig}"
        self.assertTrue(verify_stripe_signature(PAYLOAD, header, SECRET, now=NOW))

    def test_only_v0_present_returns_false(self):
        timestamp = int(NOW)
        v0_sig = hmac.new(SECRET.encode("utf-8"), PAYLOAD, hashlib.sha1).hexdigest()
        header = f"t={timestamp},v0={v0_sig}"
        self.assertFalse(verify_stripe_signature(PAYLOAD, header, SECRET, now=NOW))


if __name__ == "__main__":
    unittest.main()
