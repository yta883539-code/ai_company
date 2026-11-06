#!/usr/bin/env python3
"""stripe_webhook.pyの境界値テスト(フェーズ127)。pure stdlibのみで実行する
(trial_management.py・checkout_session.py等と同じ方針)。

実行方法: python3 prototype/test_stripe_webhook.py
"""

import hashlib
import hmac
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

from stripe_webhook import (
    InMemoryStripeEventIdStore,
    get_stripe_runtime_dependencies,
    handle_checkout_session_completed,
    handle_customer_subscription_created,
    handle_customer_subscription_deleted,
    handle_customer_subscription_updated,
    handle_invoice_payment_failed,
    handle_invoice_payment_succeeded,
    receive_stripe_webhook,
    verify_stripe_signature,
)
from stripe_webhook import main as stripe_webhook_main
from trial_management import InMemoryFleetOperatorStore

SECRET = "whsec_test_secret"


class _StubHeaders:
    """main(request)のテスト用、`request.headers.get()`インターフェースのみを模した
    最小スタブ(checkout_session.pyテストの`_StubRequest`と同系)。"""

    def __init__(self, headers: dict):
        self._headers = headers

    def get(self, key, default=None):
        return self._headers.get(key, default)


class _StubWebhookRequest:
    """main(request)のテスト用、functions_frameworkが渡すFlask Requestのうち
    `request.get_data()`・`request.headers.get()`のみを模した最小スタブ。"""

    def __init__(self, body: bytes, headers: dict):
        self._body = body
        self.headers = _StubHeaders(headers)

    def get_data(self) -> bytes:
        return self._body


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
    internal_id="internal-1", stripe_customer_id="cus_123", plan="standard", created=None
) -> dict:
    event = {
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
    if created is not None:
        event["created"] = created
    return event


def _subscription_deleted_event(stripe_customer_id="cus_123", created=None) -> dict:
    event = {
        "id": "evt_sub_del_1",
        "type": "customer.subscription.deleted",
        "data": {"object": {"customer": stripe_customer_id}},
    }
    if created is not None:
        event["created"] = created
    return event


def _subscription_created_event(stripe_customer_id="cus_123", created=None) -> dict:
    event = {
        "id": "evt_sub_created_1",
        "type": "customer.subscription.created",
        "data": {"object": {"customer": stripe_customer_id}},
    }
    if created is not None:
        event["created"] = created
    return event


def _invoice_event(event_type: str, stripe_customer_id="cus_123", created=None) -> dict:
    event = {
        "id": f"evt_{event_type}_1",
        "type": event_type,
        "data": {"object": {"customer": stripe_customer_id}},
    }
    if created is not None:
        event["created"] = created
    return event


def _subscription_updated_event(
    stripe_customer_id="cus_123", lookup_key="forklift_pasha_fleet", created=None
) -> dict:
    event = {
        "id": "evt_sub_1",
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "customer": stripe_customer_id,
                "items": {"data": [{"price": {"lookup_key": lookup_key}}]},
            }
        },
    }
    if created is not None:
        event["created"] = created
    return event


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

    # --- handle_checkout_session_completed: 配信順序入れ替わりガード
    # (checkout-session-completed-event-order-guard-design.md、フェーズ213) ---
    store4 = InMemoryFleetOperatorStore()
    applied_first_checkout = handle_checkout_session_completed(
        _checkout_event(
            internal_id="internal-4", stripe_customer_id="cus_444", plan="light", created=2_000_000,
        ),
        store4,
        event_time=datetime.fromtimestamp(2_000_000, tz=timezone.utc),
    )
    results.append(_check("正常順序ではstale=False", applied_first_checkout.stale, False))
    results.append(_check(
        "正常順序ではstripe_customer_idが書き込まれる",
        store4.get_stripe_customer_id("internal-4"),
        "cus_444",
    ))

    stale_checkout = handle_checkout_session_completed(
        _checkout_event(
            internal_id="internal-4", stripe_customer_id="cus_old", plan="light", created=1_000_000,
        ),
        store4,
        event_time=datetime.fromtimestamp(1_000_000, tz=timezone.utc),
    )
    results.append(_check("遅延配信された古いイベントはstale=True", stale_checkout.stale, True))
    results.append(_check(
        "stale時はstripe_customer_idを書き換えない",
        store4.get_stripe_customer_id("internal-4"),
        "cus_444",
    ))

    same_time_checkout = handle_checkout_session_completed(
        _checkout_event(
            internal_id="internal-4", stripe_customer_id="cus_old", plan="light", created=2_000_000,
        ),
        store4,
        event_time=datetime.fromtimestamp(2_000_000, tz=timezone.utc),
    )
    results.append(_check("同時刻は既に処理済みとしてstale=True", same_time_checkout.stale, True))

    newer_checkout = handle_checkout_session_completed(
        _checkout_event(
            internal_id="internal-4", stripe_customer_id="cus_new", plan="light", created=3_000_000,
        ),
        store4,
        event_time=datetime.fromtimestamp(3_000_000, tz=timezone.utc),
    )
    results.append(_check("より新しいevent_timeは適用される", newer_checkout.stale, False))
    results.append(_check(
        "より新しいevent_timeでstripe_customer_idが更新される",
        store4.get_stripe_customer_id("internal-4"),
        "cus_new",
    ))

    # --- handle_checkout_session_completed: event_time省略時は従来通り無条件適用 ---
    store4b = InMemoryFleetOperatorStore()
    handle_checkout_session_completed(
        _checkout_event(internal_id="internal-4b", stripe_customer_id="cus_444b", plan="light"),
        store4b,
        event_time=None,
    )
    no_event_time_checkout = handle_checkout_session_completed(
        _checkout_event(internal_id="internal-4b", stripe_customer_id="cus_444b_new", plan="light"),
        store4b,
        event_time=None,
    )
    results.append(_check("event_time省略時はstale判定しない", no_event_time_checkout.stale, False))
    results.append(_check(
        "event_time省略時は無条件適用される",
        store4b.get_stripe_customer_id("internal-4b"),
        "cus_444b_new",
    ))

    # --- handle_customer_subscription_updated: 正常系(plan_id同期) ---
    store5 = InMemoryFleetOperatorStore()
    handle_checkout_session_completed(
        _checkout_event(internal_id="internal-5", stripe_customer_id="cus_555", plan="light"),
        store5,
    )
    sub_result = handle_customer_subscription_updated(
        _subscription_updated_event(stripe_customer_id="cus_555", lookup_key="forklift_pasha_fleet"),
        store5,
    )
    results.append(_check("synced=True", sub_result.synced, True))
    results.append(_check("internal_idが逆引きで解決される", sub_result.internal_id, "internal-5"))
    results.append(_check("plan_id_written=True", sub_result.plan_id_written, True))
    results.append(_check("plan_idがfleetに更新される", store5.get_plan_id("internal-5"), "fleet"))

    # --- handle_customer_subscription_updated: 既存値と同一なら書き込まない ---
    sub_result_same = handle_customer_subscription_updated(
        _subscription_updated_event(stripe_customer_id="cus_555", lookup_key="forklift_pasha_fleet"),
        store5,
    )
    results.append(_check(
        "既存値と同一の場合はplan_id_written=False", sub_result_same.plan_id_written, False
    ))

    # --- handle_customer_subscription_updated: customer欠落 ---
    missing_customer_sub = handle_customer_subscription_updated(
        {"data": {"object": {}}}, store5
    )
    results.append(_check(
        "customer欠落はsynced=False", missing_customer_sub.synced, False
    ))
    results.append(_check(
        "customer欠落はerror=missing_customer", missing_customer_sub.error, "missing_customer"
    ))

    # --- handle_customer_subscription_updated: 未知のstripe_customer_idは逆引き不可 ---
    unknown_customer_sub = handle_customer_subscription_updated(
        _subscription_updated_event(stripe_customer_id="cus_unknown"), store5
    )
    results.append(_check(
        "未知のcustomerはsynced=False", unknown_customer_sub.synced, False
    ))
    results.append(_check(
        "未知のcustomerはerror=unknown_customer", unknown_customer_sub.error, "unknown_customer"
    ))

    # --- handle_customer_subscription_updated: 未知のlookup_keyはplan_idを書き込まない ---
    unknown_lookup_sub = handle_customer_subscription_updated(
        _subscription_updated_event(stripe_customer_id="cus_555", lookup_key="unknown_key"),
        store5,
    )
    results.append(_check(
        "未知のlookup_keyはplan_id_written=False", unknown_lookup_sub.plan_id_written, False
    ))
    results.append(_check(
        "未知のlookup_keyはplan_idを変更しない", store5.get_plan_id("internal-5"), "fleet"
    ))

    # --- handle_customer_subscription_updated: 配信順序入れ替わりガード
    # (subscription-updated-event-order-guard-design.md、フェーズ212) ---
    store6 = InMemoryFleetOperatorStore()
    handle_checkout_session_completed(
        _checkout_event(internal_id="internal-6", stripe_customer_id="cus_666", plan="light"),
        store6,
    )
    applied_first = handle_customer_subscription_updated(
        _subscription_updated_event(
            stripe_customer_id="cus_666", lookup_key="forklift_pasha_fleet", created=2_000_000,
        ),
        store6,
        event_time=datetime.fromtimestamp(2_000_000, tz=timezone.utc),
    )
    results.append(_check("正常順序ではstale=False", applied_first.stale, False))
    results.append(_check("正常順序ではplan_idが反映される", store6.get_plan_id("internal-6"), "fleet"))

    stale_result = handle_customer_subscription_updated(
        _subscription_updated_event(
            stripe_customer_id="cus_666", lookup_key="forklift_pasha_light", created=1_000_000,
        ),
        store6,
        event_time=datetime.fromtimestamp(1_000_000, tz=timezone.utc),
    )
    results.append(_check("遅延配信された古いイベントはstale=True", stale_result.stale, True))
    results.append(_check("stale=Trueはsynced=False", stale_result.synced, False))
    results.append(_check(
        "stale時はplan_idを書き換えない", store6.get_plan_id("internal-6"), "fleet"
    ))

    same_time_result = handle_customer_subscription_updated(
        _subscription_updated_event(
            stripe_customer_id="cus_666", lookup_key="forklift_pasha_light", created=2_000_000,
        ),
        store6,
        event_time=datetime.fromtimestamp(2_000_000, tz=timezone.utc),
    )
    results.append(_check("同時刻は既に処理済みとしてstale=True", same_time_result.stale, True))

    newer_result = handle_customer_subscription_updated(
        _subscription_updated_event(
            stripe_customer_id="cus_666", lookup_key="forklift_pasha_light", created=3_000_000,
        ),
        store6,
        event_time=datetime.fromtimestamp(3_000_000, tz=timezone.utc),
    )
    results.append(_check("より新しいevent_timeは適用される", newer_result.stale, False))
    results.append(_check(
        "より新しいevent_timeでplan_idが更新される", store6.get_plan_id("internal-6"), "light"
    ))

    # --- handle_customer_subscription_updated: event_time省略時は従来通り無条件適用 ---
    store6b = InMemoryFleetOperatorStore()
    handle_checkout_session_completed(
        _checkout_event(internal_id="internal-6b", stripe_customer_id="cus_666b", plan="light"),
        store6b,
    )
    handle_customer_subscription_updated(
        _subscription_updated_event(stripe_customer_id="cus_666b", lookup_key="forklift_pasha_fleet"),
        store6b,
        event_time=None,
    )
    no_event_time_result = handle_customer_subscription_updated(
        _subscription_updated_event(stripe_customer_id="cus_666b", lookup_key="forklift_pasha_light"),
        store6b,
        event_time=None,
    )
    results.append(_check("event_time省略時はstale判定しない", no_event_time_result.stale, False))
    results.append(_check(
        "event_time省略時は無条件適用される", store6b.get_plan_id("internal-6b"), "light"
    ))

    # --- handle_customer_subscription_deleted: 正常系(canceled_at書き込み) ---
    store7 = InMemoryFleetOperatorStore()
    handle_checkout_session_completed(
        _checkout_event(internal_id="internal-7", stripe_customer_id="cus_777", plan="standard"),
        store7,
    )
    del_result = handle_customer_subscription_deleted(
        _subscription_deleted_event(stripe_customer_id="cus_777"),
        store7,
        now=datetime(2026, 10, 11, 20, 0, tzinfo=timezone.utc),
    )
    results.append(_check("canceled=True", del_result.canceled, True))
    results.append(_check("internal_idが逆引きで解決される", del_result.internal_id, "internal-7"))
    results.append(_check(
        "canceled_atが書き込まれる",
        store7.get_canceled_at("internal-7"),
        datetime(2026, 10, 11, 20, 0, tzinfo=timezone.utc),
    ))

    # --- handle_customer_subscription_deleted: upgraded_at設定済みでも解約を記録する ---
    results.append(_check(
        "upgraded_atが設定済みでもcanceled_atは書き込まれる(決済失敗未経験でも同様)",
        store7.get_upgraded_at("internal-7") is not None and store7.get_canceled_at("internal-7") is not None,
        True,
    ))

    # --- handle_customer_subscription_deleted: customer欠落 ---
    missing_customer_del = handle_customer_subscription_deleted({"data": {"object": {}}}, store7)
    results.append(_check("customer欠落はcanceled=False", missing_customer_del.canceled, False))
    results.append(_check(
        "customer欠落はerror=missing_customer", missing_customer_del.error, "missing_customer"
    ))

    # --- handle_customer_subscription_deleted: 未知のstripe_customer_idは逆引き不可 ---
    unknown_customer_del = handle_customer_subscription_deleted(
        _subscription_deleted_event(stripe_customer_id="cus_unknown"), store7
    )
    results.append(_check("未知のcustomerはcanceled=False", unknown_customer_del.canceled, False))
    results.append(_check(
        "未知のcustomerはerror=unknown_customer", unknown_customer_del.error, "unknown_customer"
    ))

    # --- handle_customer_subscription_created: 正常系(canceled_atのクリア) ---
    store9 = InMemoryFleetOperatorStore()
    handle_checkout_session_completed(
        _checkout_event(internal_id="internal-9", stripe_customer_id="cus_999a", plan="standard"),
        store9,
    )
    handle_customer_subscription_deleted(
        _subscription_deleted_event(stripe_customer_id="cus_999a"),
        store9,
        now=datetime(2026, 10, 11, 20, 0, tzinfo=timezone.utc),
    )
    results.append(_check(
        "前提: 解約でcanceled_atが設定されている",
        store9.get_canceled_at("internal-9") is not None,
        True,
    ))
    created_result = handle_customer_subscription_created(
        _subscription_created_event(stripe_customer_id="cus_999a"), store9
    )
    results.append(_check("cleared=True", created_result.cleared, True))
    results.append(_check("internal_idが逆引きで解決される", created_result.internal_id, "internal-9"))
    results.append(_check(
        "再契約でcanceled_atがクリアされる", store9.get_canceled_at("internal-9"), None
    ))

    # --- handle_customer_subscription_created: 解約を経ていない場合も冪等にcleared=True ---
    store10 = InMemoryFleetOperatorStore()
    handle_checkout_session_completed(
        _checkout_event(internal_id="internal-10", stripe_customer_id="cus_999b", plan="light"),
        store10,
    )
    never_canceled_result = handle_customer_subscription_created(
        _subscription_created_event(stripe_customer_id="cus_999b"), store10
    )
    results.append(_check(
        "解約未経験でもcleared=True", never_canceled_result.cleared, True
    ))
    results.append(_check(
        "canceled_atはNoneのまま", store10.get_canceled_at("internal-10"), None
    ))

    # --- handle_customer_subscription_created: customer欠落 ---
    missing_customer_created = handle_customer_subscription_created(
        {"data": {"object": {}}}, store9
    )
    results.append(_check(
        "customer欠落はcleared=False", missing_customer_created.cleared, False
    ))
    results.append(_check(
        "customer欠落はerror=missing_customer", missing_customer_created.error, "missing_customer"
    ))

    # --- handle_customer_subscription_created: 未知のstripe_customer_idは逆引き不可 ---
    unknown_customer_created = handle_customer_subscription_created(
        _subscription_created_event(stripe_customer_id="cus_unknown"), store9
    )
    results.append(_check(
        "未知のcustomerはcleared=False", unknown_customer_created.cleared, False
    ))
    results.append(_check(
        "未知のcustomerはerror=unknown_customer", unknown_customer_created.error, "unknown_customer"
    ))

    # --- handle_customer_subscription_deleted/created: 配信順序入れ替わりガード
    # (subscription-lifecycle-event-order-guard-design.md、フェーズ214、フェーズ213
    # 次回候補(1)) ---
    store13 = InMemoryFleetOperatorStore()
    handle_checkout_session_completed(
        _checkout_event(internal_id="internal-13", stripe_customer_id="cus_lc_1", plan="light"),
        store13,
    )
    applied_first_del = handle_customer_subscription_deleted(
        _subscription_deleted_event(stripe_customer_id="cus_lc_1", created=2_000_000),
        store13,
        now=datetime(2026, 10, 11, 20, 0, tzinfo=timezone.utc),
        event_time=datetime.fromtimestamp(2_000_000, tz=timezone.utc),
    )
    results.append(_check("正常順序ではstale=False(deleted)", applied_first_del.stale, False))
    results.append(_check(
        "正常順序ではcanceled_atが書き込まれる", store13.get_canceled_at("internal-13") is not None, True
    ))

    stale_del = handle_customer_subscription_deleted(
        _subscription_deleted_event(stripe_customer_id="cus_lc_1", created=1_000_000),
        store13,
        now=datetime(2026, 10, 11, 21, 0, tzinfo=timezone.utc),
        event_time=datetime.fromtimestamp(1_000_000, tz=timezone.utc),
    )
    results.append(_check("遅延配信された古いdeletedはstale=True", stale_del.stale, True))
    results.append(_check("stale=Trueはcanceled=False", stale_del.canceled, False))

    same_time_del = handle_customer_subscription_deleted(
        _subscription_deleted_event(stripe_customer_id="cus_lc_1", created=2_000_000),
        store13,
        event_time=datetime.fromtimestamp(2_000_000, tz=timezone.utc),
    )
    results.append(_check("同時刻は既に処理済みとしてstale=True(deleted)", same_time_del.stale, True))

    newer_created_clears = handle_customer_subscription_created(
        _subscription_created_event(stripe_customer_id="cus_lc_1", created=3_000_000),
        store13,
        event_time=datetime.fromtimestamp(3_000_000, tz=timezone.utc),
    )
    results.append(_check("より新しいevent_timeのcreatedは適用される", newer_created_clears.stale, False))
    results.append(_check(
        "より新しいcreatedでcanceled_atがクリアされる", store13.get_canceled_at("internal-13"), None
    ))

    # --- 解約直後の再契約での配信順序入れ替わり(本ガードの主目的のシナリオ):
    # 新しいcreated(再契約)を先に処理した後、古いdeleted(直前の解約)が遅延配信されても
    # canceled_atを誤って再設定しない ---
    stale_del_after_newer_created = handle_customer_subscription_deleted(
        _subscription_deleted_event(stripe_customer_id="cus_lc_1", created=2_500_000),
        store13,
        now=datetime(2026, 10, 11, 22, 0, tzinfo=timezone.utc),
        event_time=datetime.fromtimestamp(2_500_000, tz=timezone.utc),
    )
    results.append(_check(
        "再契約後に遅延配信された直前のdeletedはstale=True",
        stale_del_after_newer_created.stale,
        True,
    ))
    results.append(_check(
        "再契約後の遅延deletedでcanceled_atが再設定されない",
        store13.get_canceled_at("internal-13"),
        None,
    ))

    # --- handle_customer_subscription_created: event_time省略時は従来通り無条件適用 ---
    store13b = InMemoryFleetOperatorStore()
    handle_checkout_session_completed(
        _checkout_event(internal_id="internal-13b", stripe_customer_id="cus_lc_1b", plan="light"),
        store13b,
    )
    handle_customer_subscription_deleted(
        _subscription_deleted_event(stripe_customer_id="cus_lc_1b"),
        store13b,
        now=datetime(2026, 10, 11, 20, 0, tzinfo=timezone.utc),
        event_time=None,
    )
    no_event_time_created = handle_customer_subscription_created(
        _subscription_created_event(stripe_customer_id="cus_lc_1b"), store13b, event_time=None
    )
    results.append(_check(
        "event_time省略時はstale判定しない(created)", no_event_time_created.stale, False
    ))
    results.append(_check(
        "event_time省略時は無条件でcanceled_atがクリアされる",
        store13b.get_canceled_at("internal-13b"),
        None,
    ))

    # --- receive_stripe_webhook: customer.subscription.createdを正しくディスパッチする ---
    store11 = InMemoryFleetOperatorStore()
    handle_checkout_session_completed(
        _checkout_event(internal_id="internal-11", stripe_customer_id="cus_999c", plan="light"),
        store11,
    )
    handle_customer_subscription_deleted(
        _subscription_deleted_event(stripe_customer_id="cus_999c"),
        store11,
        now=datetime(2026, 10, 11, 20, 0, tzinfo=timezone.utc),
    )
    created_body = json.dumps(
        _subscription_created_event(stripe_customer_id="cus_999c")
    ).encode("utf-8")
    created_ts = int(time.time())
    created_dispatch_result = receive_stripe_webhook(
        created_body, _sign(created_body, created_ts), SECRET, store=store11
    )
    results.append(_check("正常系は200", created_dispatch_result.status_code, 200))
    results.append(_check(
        "subscription_created_result.cleared=True",
        created_dispatch_result.subscription_created_result.cleared,
        True,
    ))
    results.append(_check(
        "store側にも反映される", store11.get_canceled_at("internal-11"), None
    ))

    # --- handle_invoice_payment_failed() / handle_invoice_payment_succeeded() (フェーズ167) ---
    store12 = InMemoryFleetOperatorStore()
    handle_checkout_session_completed(
        _checkout_event(internal_id="internal-12", stripe_customer_id="cus_pf_1", plan="light"),
        store12,
    )
    now12 = datetime(2026, 10, 17, tzinfo=timezone.utc)
    failed_result = handle_invoice_payment_failed(
        _invoice_event("invoice.payment_failed", stripe_customer_id="cus_pf_1"),
        store12,
        now=now12,
    )
    results.append(_check("invoice.payment_failed: detected=True", failed_result.detected, True))
    results.append(_check(
        "invoice.payment_failed: payment_failure_detected_atが書き込まれる",
        store12.get_payment_failure_detected_at("internal-12"),
        now12,
    ))

    unknown_customer_failed = handle_invoice_payment_failed(
        _invoice_event("invoice.payment_failed", stripe_customer_id="cus_pf_unknown"), store12
    )
    results.append(_check(
        "invoice.payment_failed: 未知のcustomerはerror=unknown_customer",
        unknown_customer_failed.error,
        "unknown_customer",
    ))

    succeeded_result = handle_invoice_payment_succeeded(
        _invoice_event("invoice.payment_succeeded", stripe_customer_id="cus_pf_1"),
        store12,
        now=now12 + timedelta(days=1),
    )
    results.append(_check("invoice.payment_succeeded: cleared=True", succeeded_result.cleared, True))
    results.append(_check(
        "invoice.payment_succeeded: 猶予期間中(7日未満)の解消はresolved_within_grace_period",
        succeeded_result.recovery_kind,
        "resolved_within_grace_period",
    ))
    results.append(_check(
        "invoice.payment_succeeded: payment_failure_detected_atがクリアされる",
        store12.get_payment_failure_detected_at("internal-12"),
        None,
    ))

    noop_succeeded_result = handle_invoice_payment_succeeded(
        _invoice_event("invoice.payment_succeeded", stripe_customer_id="cus_pf_1"), store12
    )
    results.append(_check(
        "invoice.payment_succeeded: 未検知状態での受信はcleared=False",
        noop_succeeded_result.cleared,
        False,
    ))

    # --- handle_invoice_payment_failed/succeeded: 配信順序入れ替わりガード
    # (payment-failure-event-order-guard-design.md、フェーズ216、フェーズ214次回候補(1)・
    # フェーズ215次回候補(3)) ---
    store14 = InMemoryFleetOperatorStore()
    handle_checkout_session_completed(
        _checkout_event(internal_id="internal-14", stripe_customer_id="cus_pf_order", plan="light"),
        store14,
    )
    applied_first_failed = handle_invoice_payment_failed(
        _invoice_event("invoice.payment_failed", stripe_customer_id="cus_pf_order", created=2_000_000),
        store14,
        now=datetime(2026, 11, 6, 20, 0, tzinfo=timezone.utc),
        event_time=datetime.fromtimestamp(2_000_000, tz=timezone.utc),
    )
    results.append(_check("正常順序ではstale=False(failed)", applied_first_failed.stale, False))
    results.append(_check(
        "正常順序ではpayment_failure_detected_atが書き込まれる",
        store14.get_payment_failure_detected_at("internal-14") is not None,
        True,
    ))

    stale_failed = handle_invoice_payment_failed(
        _invoice_event("invoice.payment_failed", stripe_customer_id="cus_pf_order", created=1_000_000),
        store14,
        now=datetime(2026, 11, 6, 21, 0, tzinfo=timezone.utc),
        event_time=datetime.fromtimestamp(1_000_000, tz=timezone.utc),
    )
    results.append(_check("遅延配信された古いfailedはstale=True", stale_failed.stale, True))
    results.append(_check("stale=Trueはdetected=False", stale_failed.detected, False))

    # 決済成功(新しいevent_time)で復旧した後に、その成功より前の古いfailedが遅延配信
    # されても、復旧済みのdunning状態を誤って再開させない。
    newer_succeeded_recovers = handle_invoice_payment_succeeded(
        _invoice_event("invoice.payment_succeeded", stripe_customer_id="cus_pf_order", created=3_000_000),
        store14,
        now=datetime(2026, 11, 6, 22, 0, tzinfo=timezone.utc),
        event_time=datetime.fromtimestamp(3_000_000, tz=timezone.utc),
    )
    results.append(_check(
        "より新しいevent_timeのsucceededは適用される", newer_succeeded_recovers.stale, False
    ))
    results.append(_check(
        "より新しいsucceededでpayment_failure_detected_atがクリアされる",
        store14.get_payment_failure_detected_at("internal-14"),
        None,
    ))

    stale_failed_after_newer_succeeded = handle_invoice_payment_failed(
        _invoice_event("invoice.payment_failed", stripe_customer_id="cus_pf_order", created=2_500_000),
        store14,
        now=datetime(2026, 11, 6, 23, 0, tzinfo=timezone.utc),
        event_time=datetime.fromtimestamp(2_500_000, tz=timezone.utc),
    )
    results.append(_check(
        "決済成功後に遅延配信された直前のfailedはstale=True",
        stale_failed_after_newer_succeeded.stale,
        True,
    ))
    results.append(_check(
        "決済成功後の遅延failedでpayment_failure_detected_atが再設定されない",
        store14.get_payment_failure_detected_at("internal-14"),
        None,
    ))

    # --- handle_invoice_payment_failed/succeeded: event_time省略時は従来通り無条件適用 ---
    store14b = InMemoryFleetOperatorStore()
    handle_checkout_session_completed(
        _checkout_event(internal_id="internal-14b", stripe_customer_id="cus_pf_order_b", plan="light"),
        store14b,
    )
    no_event_time_failed = handle_invoice_payment_failed(
        _invoice_event("invoice.payment_failed", stripe_customer_id="cus_pf_order_b"),
        store14b,
        now=datetime(2026, 11, 6, 20, 0, tzinfo=timezone.utc),
        event_time=None,
    )
    results.append(_check(
        "event_time省略時はstale判定しない(failed)", no_event_time_failed.stale, False
    ))
    results.append(_check(
        "event_time省略時は無条件でpayment_failure_detected_atが書き込まれる",
        store14b.get_payment_failure_detected_at("internal-14b") is not None,
        True,
    ))

    # --- receive_stripe_webhook: invoice.payment_failed/succeededを正しくディスパッチする ---
    store13 = InMemoryFleetOperatorStore()
    handle_checkout_session_completed(
        _checkout_event(internal_id="internal-13", stripe_customer_id="cus_pf_2", plan="light"),
        store13,
    )
    pf_body = json.dumps(_invoice_event("invoice.payment_failed", stripe_customer_id="cus_pf_2")).encode("utf-8")
    pf_ts = int(time.time())
    pf_dispatch_result = receive_stripe_webhook(
        pf_body, _sign(pf_body, pf_ts), SECRET, store=store13
    )
    results.append(_check("invoice.payment_failedディスパッチは200", pf_dispatch_result.status_code, 200))
    results.append(_check(
        "invoice_payment_failed_result.detected=True",
        pf_dispatch_result.invoice_payment_failed_result.detected,
        True,
    ))
    results.append(_check(
        "store側にも反映される",
        store13.get_payment_failure_detected_at("internal-13") is not None,
        True,
    ))

    ps_body = json.dumps(_invoice_event("invoice.payment_succeeded", stripe_customer_id="cus_pf_2")).encode("utf-8")
    ps_ts = int(time.time())
    ps_dispatch_result = receive_stripe_webhook(
        ps_body, _sign(ps_body, ps_ts), SECRET, store=store13
    )
    results.append(_check("invoice.payment_succeededディスパッチは200", ps_dispatch_result.status_code, 200))
    results.append(_check(
        "invoice_payment_succeeded_result.cleared=True",
        ps_dispatch_result.invoice_payment_succeeded_result.cleared,
        True,
    ))
    results.append(_check(
        "store側にも反映される(クリア済み)",
        store13.get_payment_failure_detected_at("internal-13"),
        None,
    ))

    # --- receive_stripe_webhook: customer.subscription.deletedを正しくディスパッチする ---
    store8 = InMemoryFleetOperatorStore()
    handle_checkout_session_completed(
        _checkout_event(internal_id="internal-8", stripe_customer_id="cus_888", plan="light"),
        store8,
    )
    del_body = json.dumps(_subscription_deleted_event(stripe_customer_id="cus_888")).encode("utf-8")
    del_ts = int(time.time())
    del_dispatch_result = receive_stripe_webhook(
        del_body, _sign(del_body, del_ts), SECRET, store=store8
    )
    results.append(_check("正常系は200", del_dispatch_result.status_code, 200))
    results.append(_check(
        "subscription_deleted_result.canceled=True",
        del_dispatch_result.subscription_deleted_result.canceled,
        True,
    ))
    results.append(_check(
        "store側にも反映される", store8.get_canceled_at("internal-8") is not None, True
    ))

    # --- receive_stripe_webhook: customer.subscription.updatedを正しくディスパッチする ---
    store6 = InMemoryFleetOperatorStore()
    handle_checkout_session_completed(
        _checkout_event(internal_id="internal-6", stripe_customer_id="cus_666", plan="light"),
        store6,
    )
    sub_body = json.dumps(
        _subscription_updated_event(stripe_customer_id="cus_666", lookup_key="forklift_pasha_standard")
    ).encode("utf-8")
    sub_ts = int(time.time())
    sub_dispatch_result = receive_stripe_webhook(
        sub_body, _sign(sub_body, sub_ts), SECRET, store=store6
    )
    results.append(_check("正常系は200", sub_dispatch_result.status_code, 200))
    results.append(_check(
        "subscription_updated_result.synced=True",
        sub_dispatch_result.subscription_updated_result.synced,
        True,
    ))
    results.append(_check("store側にも反映される", store6.get_plan_id("internal-6"), "standard"))

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
    # (フェーズ129より前はこの例としてcustomer.subscription.deletedを使っていたが、
    # handle_customer_subscription_deleted()を追加したため対応済みイベントになった。
    # 本venture未着手のイベント種別の例としてinvoice.payment_failedに差し替える)
    other_event_body = json.dumps({"id": "evt_2", "type": "invoice.payment_failed"}).encode(
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
    results.append(_check(
        "未対応イベントはsubscription_deleted_result無し",
        other_result.subscription_deleted_result,
        None,
    ))

    # --- receive_stripe_webhook: 不正JSONは400 ---
    invalid_json_body = b"not json"
    invalid_ts = int(time.time())
    invalid_result = receive_stripe_webhook(
        invalid_json_body, _sign(invalid_json_body, invalid_ts), SECRET, store=store4
    )
    results.append(_check("不正JSONは400", invalid_result.status_code, 400))

    # --- receive_stripe_webhook: event_id_store(stripe-event-idempotency-design.md、
    # フェーズ215、kura-pashaの横断棚卸しで発見)。本venture唯一の非べき等な副作用である
    # invoice.payment_failedのpayment_failure_detected_at上書きが、再配信のたびに
    # 猶予期間の起算点をずらしてしまう欠落を、event_id_store指定で防げることを確認する ---
    store14 = InMemoryFleetOperatorStore()
    event_id_store14 = InMemoryStripeEventIdStore()
    handle_checkout_session_completed(
        _checkout_event(internal_id="internal-14", stripe_customer_id="cus_pf_dup", plan="light"),
        store14,
    )
    pf_dup_body = json.dumps(
        _invoice_event("invoice.payment_failed", stripe_customer_id="cus_pf_dup")
    ).encode("utf-8")
    pf_dup_ts1 = int(time.time())
    pf_dup_now1 = datetime.fromtimestamp(pf_dup_ts1, tz=timezone.utc)
    first_pf_result = receive_stripe_webhook(
        pf_dup_body,
        _sign(pf_dup_body, pf_dup_ts1),
        SECRET,
        store=store14,
        event_id_store=event_id_store14,
        now=pf_dup_now1,
    )
    results.append(_check(
        "初回のinvoice.payment_failedはduplicate=False", first_pf_result.duplicate, False
    ))
    first_detected_at = store14.get_payment_failure_detected_at("internal-14")
    results.append(_check(
        "初回でpayment_failure_detected_atが書き込まれる", first_detected_at, pf_dup_now1
    ))

    pf_dup_ts2 = pf_dup_ts1 + 86400
    pf_dup_now2 = datetime.fromtimestamp(pf_dup_ts2, tz=timezone.utc)
    second_pf_result = receive_stripe_webhook(
        pf_dup_body,
        _sign(pf_dup_body, pf_dup_ts2),
        SECRET,
        store=store14,
        event_id_store=event_id_store14,
        now=pf_dup_now2,
    )
    results.append(_check(
        "同一event.idの再配信はduplicate=True", second_pf_result.duplicate, True
    ))
    results.append(_check(
        "再配信はinvoice_payment_failed_resultを持たない(ハンドラ未呼び出し)",
        second_pf_result.invoice_payment_failed_result,
        None,
    ))
    results.append(_check(
        "再配信でpayment_failure_detected_atが上書きされない(猶予期間の起算点が後ろへ"
        "ずれない)",
        store14.get_payment_failure_detected_at("internal-14"),
        first_detected_at,
    ))

    # --- receive_stripe_webhook: event_id_store省略時は従来通り重複排除しない(後方互換) ---
    store15 = InMemoryFleetOperatorStore()
    handle_checkout_session_completed(
        _checkout_event(internal_id="internal-15", stripe_customer_id="cus_pf_nodup", plan="light"),
        store15,
    )
    pf_nodup_body = json.dumps(
        _invoice_event("invoice.payment_failed", stripe_customer_id="cus_pf_nodup")
    ).encode("utf-8")
    pf_nodup_ts1 = int(time.time())
    pf_nodup_now1 = datetime.fromtimestamp(pf_nodup_ts1, tz=timezone.utc)
    receive_stripe_webhook(
        pf_nodup_body, _sign(pf_nodup_body, pf_nodup_ts1), SECRET, store=store15,
        now=pf_nodup_now1,
    )
    pf_nodup_ts2 = pf_nodup_ts1 + 86400
    pf_nodup_now2 = datetime.fromtimestamp(pf_nodup_ts2, tz=timezone.utc)
    no_dedup_result = receive_stripe_webhook(
        pf_nodup_body, _sign(pf_nodup_body, pf_nodup_ts2), SECRET, store=store15,
        now=pf_nodup_now2,
    )
    results.append(_check(
        "event_id_store省略時はduplicate=False(後方互換)", no_dedup_result.duplicate, False
    ))
    results.append(_check(
        "event_id_store省略時は再配信でpayment_failure_detected_atが上書きされる"
        "(既存挙動のまま)",
        store15.get_payment_failure_detected_at("internal-15"),
        pf_nodup_now2,
    ))

    # --- InMemoryStripeEventIdStore 単体 ---
    bare_event_id_store = InMemoryStripeEventIdStore()
    results.append(_check(
        "未処理のevent_idはhas_processed=False",
        bare_event_id_store.has_processed("evt_bare_1"),
        False,
    ))
    bare_event_id_store.mark_processed("evt_bare_1")
    results.append(_check(
        "mark_processed後はhas_processed=True",
        bare_event_id_store.has_processed("evt_bare_1"),
        True,
    ))
    results.append(_check(
        "他のevent_idには影響しない",
        bare_event_id_store.has_processed("evt_bare_2"),
        False,
    ))

    # --- get_stripe_runtime_dependencies ---
    deps = get_stripe_runtime_dependencies()
    results.append(_check("storeキーが存在する", "store" in deps, True))
    results.append(_check(
        "storeはFleetOperatorStoreProtocolを満たす",
        hasattr(deps["store"], "set_stripe_customer_id"),
        True,
    ))
    results.append(_check(
        "event_id_storeキーが存在する(フェーズ215)", "event_id_store" in deps, True
    ))
    results.append(_check(
        "event_id_storeはInMemoryStripeEventIdStore",
        isinstance(deps["event_id_store"], InMemoryStripeEventIdStore),
        True,
    ))
    other_deps = get_stripe_runtime_dependencies()
    deps["event_id_store"].mark_processed("evt_shared_check")
    results.append(_check(
        "event_id_storeは呼び出しごとに独立した新規インスタンス",
        other_deps["event_id_store"].has_processed("evt_shared_check"),
        False,
    ))

    # --- main(): Cloud Functionsエントリポイント自体の回帰確認(checkout_session.main()の
    # フェーズ146と同じ依存注入パターンをstripe_webhook.main()にも適用) ---
    no_sig_body, no_sig_status = stripe_webhook_main(
        _StubWebhookRequest(b"{}", {"Stripe-Signature": None})
    )
    results.append(_check(
        "main(): 署名ヘッダ無しは401(runtime_dependencies省略時も既存挙動のまま)",
        no_sig_status,
        401,
    ))

    # runtime_dependencies省略時はget_stripe_runtime_dependencies()が呼び出しごとに
    # 新規のInMemoryFleetOperatorStore()を生成するため、main()越しに正常な署名付きイベントを
    # 送っても、本プロセス内で状態が共有される保証はない(事前紐付け済みのinternal_idを
    # 検証したい場合はruntime_dependencies注入が必要)。ここでは「新規ストアでも
    # checkout.session.completedの受信自体は200になる」ことを確認する。
    main_body = json.dumps(
        {
            "id": "evt_main_1",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "client_reference_id": "internal-main-1",
                    "customer": "cus_main_1",
                }
            },
        }
    ).encode("utf-8")
    main_ts = int(time.time())
    os.environ["STRIPE_WEBHOOK_SECRET"] = SECRET
    main_ok_body, main_ok_status = stripe_webhook_main(
        _StubWebhookRequest(
            main_body, {"Stripe-Signature": _sign(main_body, main_ts)}
        )
    )
    results.append(_check(
        "main(): runtime_dependencies省略時でも署名検証に通れば200", main_ok_status, 200
    ))

    # フェーズ146で確立した依存注入パターン: 事前に紐付け済みのstoreを注入すれば、
    # main()越しにその状態を検証できる。
    injected_store = InMemoryFleetOperatorStore()
    injected_response_body, injected_response_status = stripe_webhook_main(
        _StubWebhookRequest(
            main_body, {"Stripe-Signature": _sign(main_body, main_ts)}
        ),
        runtime_dependencies={"store": injected_store},
    )
    results.append(_check(
        "main(): runtime_dependencies注入時も200", injected_response_status, 200
    ))
    results.append(_check(
        "main(): runtime_dependencies注入時はmain()越しにstoreへ反映される"
        "(client_reference_idがstripe_customer_idに紐付く)",
        injected_store.get_stripe_customer_id("internal-main-1"),
        "cus_main_1",
    ))

    passed = sum(1 for r in results if r)
    print(f"\n{len(results)}件中{passed}件成功")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
