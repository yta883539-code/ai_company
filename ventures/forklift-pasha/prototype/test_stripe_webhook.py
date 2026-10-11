#!/usr/bin/env python3
"""stripe_webhook.pyの境界値テスト(フェーズ127)。pure stdlibのみで実行する
(trial_management.py・checkout_session.py等と同じ方針)。

実行方法: python3 prototype/test_stripe_webhook.py
"""

import hashlib
import hmac
import json
import sys
import time
from datetime import datetime, timezone

from stripe_webhook import (
    get_stripe_runtime_dependencies,
    handle_checkout_session_completed,
    receive_stripe_webhook,
    verify_stripe_signature,
)
from trial_management import InMemoryFleetOperatorStore

SECRET = "whsec_test_secret"


def _check(label, actual, expected):
    if actual == expected:
        print(f"[OK] {label}")
        return True
    print(f"[NG] {label}: 期待={expected!r} 実際={actual!r}")
    return False


def _sign(payload: bytes, timestamp: int, secret: str = SECRET) -> str:
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig}"


def _checkout_event(
    internal_id="internal-1", stripe_customer_id="cus_123", plan="standard"
) -> dict:
    return {
        "id": "evt_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": internal_id,
                "customer": stripe_customer_id,
                "metadata": {"plan": plan},
            }
        },
    }


def main():
    results = []

    # --- verify_stripe_signature ---
    payload = b'{"id":"evt_demo"}'
    now = time.time()
    results.append(_check(
        "正しい署名は検証OK",
        verify_stripe_signature(payload, _sign(payload, int(now)), SECRET, now=now),
        True,
    ))
    results.append(_check(
        "ヘッダ無しは検証NG",
        verify_stripe_signature(payload, None, SECRET, now=now),
        False,
    ))
    results.append(_check(
        "空文字列ヘッダは検証NG",
        verify_stripe_signature(payload, "", SECRET, now=now),
        False,
    ))
    results.append(_check(
        "t・v1を含まない不正形式は検証NG",
        verify_stripe_signature(payload, "garbage", SECRET, now=now),
        False,
    ))
    results.append(_check(
        "誤ったシークレットは検証NG",
        verify_stripe_signature(payload, _sign(payload, int(now)), "whsec_wrong", now=now),
        False,
    ))
    results.append(_check(
        "許容範囲外のタイムスタンプは検証NG",
        verify_stripe_signature(
            payload, _sign(payload, int(now) - 301), SECRET, now=now
        ),
        False,
    ))

    # --- handle_checkout_session_completed: 正常系 ---
    store = InMemoryFleetOperatorStore()
    result = handle_checkout_session_completed(
        _checkout_event(), store, now=datetime(2026, 10, 11, tzinfo=timezone.utc)
    )
    results.append(_check("linked=True", result.linked, True))
    results.append(_check(
        "stripe_customer_idが書き込まれる", store.get_stripe_customer_id("internal-1"), "cus_123"
    ))
    results.append(_check("plan_idが書き込まれる", store.get_plan_id("internal-1"), "standard"))
    results.append(_check("plan_id_written=True", result.plan_id_written, True))
    results.append(_check(
        "upgraded_atが書き込まれる",
        store.get_upgraded_at("internal-1"),
        datetime(2026, 10, 11, tzinfo=timezone.utc),
    ))
    results.append(_check("upgraded_at_written=True", result.upgraded_at_written, True))
    results.append(_check(
        "逆引きでinternal_idが解決できる",
        store.get_internal_id_by_stripe_customer_id("cus_123"),
        "internal-1",
    ))

    # --- handle_checkout_session_completed: 2回目受信はupgraded_atを上書きしない ---
    result2 = handle_checkout_session_completed(
        _checkout_event(), store, now=datetime(2026, 11, 1, tzinfo=timezone.utc)
    )
    results.append(_check(
        "再送時はupgraded_atを上書きしない",
        store.get_upgraded_at("internal-1"),
        datetime(2026, 10, 11, tzinfo=timezone.utc),
    ))
    results.append(_check("再送時はupgraded_at_written=False", result2.upgraded_at_written, False))

    # --- handle_checkout_session_completed: 異常系 ---
    store2 = InMemoryFleetOperatorStore()
    missing_customer = handle_checkout_session_completed(
        {"data": {"object": {"client_reference_id": "internal-2"}}}, store2
    )
    results.append(_check("customer欠落はlinked=False", missing_customer.linked, False))
    results.append(_check(
        "customer欠落時は書き込まない", store2.get_stripe_customer_id("internal-2"), None
    ))

    missing_internal_id = handle_checkout_session_completed(
        {"data": {"object": {"customer": "cus_999"}}}, store2
    )
    results.append(_check("internal_id欠落はlinked=False", missing_internal_id.linked, False))

    # --- handle_checkout_session_completed: 未知のplanは書き込まない ---
    store3 = InMemoryFleetOperatorStore()
    unknown_plan_result = handle_checkout_session_completed(
        _checkout_event(internal_id="internal-3", plan="premium"), store3
    )
    results.append(_check(
        "未知のplanはplan_id_written=False", unknown_plan_result.plan_id_written, False
    ))
    results.append(_check("未知のplanはplan_idを書き込まない", store3.get_plan_id("internal-3"), None))

    # --- receive_stripe_webhook: 署名検証失敗 ---
    store4 = InMemoryFleetOperatorStore()
    body = json.dumps(_checkout_event()).encode("utf-8")
    bad_sig_result = receive_stripe_webhook(body, None, SECRET, store=store4)
    results.append(_check("署名無しは401", bad_sig_result.status_code, 401))

    # --- receive_stripe_webhook: 正常系(checkout.session.completed) ---
    ts = int(time.time())
    good_result = receive_stripe_webhook(
        body, _sign(body, ts), SECRET, store=store4, now=datetime.fromtimestamp(ts, tz=timezone.utc)
    )
    results.append(_check("正常系は200", good_result.status_code, 200))
    results.append(_check(
        "checkout_link_result.linked=True", good_result.checkout_link_result.linked, True
    ))
    results.append(_check(
        "store側にも反映される", store4.get_stripe_customer_id("internal-1"), "cus_123"
    ))

    # --- receive_stripe_webhook: 未対応イベント種別は200で無視 ---
    other_event_body = json.dumps({"id": "evt_2", "type": "customer.subscription.deleted"}).encode(
        "utf-8"
    )
    other_ts = int(time.time())
    other_result = receive_stripe_webhook(
        other_event_body, _sign(other_event_body, other_ts), SECRET, store=store4
    )
    results.append(_check("未対応イベントは200", other_result.status_code, 200))
    results.append(_check(
        "未対応イベントはcheckout_link_result無し", other_result.checkout_link_result, None
    ))

    # --- receive_stripe_webhook: 不正JSONは400 ---
    invalid_json_body = b"not json"
    invalid_ts = int(time.time())
    invalid_result = receive_stripe_webhook(
        invalid_json_body, _sign(invalid_json_body, invalid_ts), SECRET, store=store4
    )
    results.append(_check("不正JSONは400", invalid_result.status_code, 400))

    # --- get_stripe_runtime_dependencies ---
    deps = get_stripe_runtime_dependencies()
    results.append(_check("storeキーが存在する", "store" in deps, True))
    results.append(_check(
        "storeはFleetOperatorStoreProtocolを満たす",
        hasattr(deps["store"], "set_stripe_customer_id"),
        True,
    ))

    passed = sum(1 for r in results if r)
    print(f"\n{len(results)}件中{passed}件成功")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
