#!/usr/bin/env python3
"""checkout_session.pyの検証用テスト。`python3 test_checkout_session.py`で実行する。"""

from checkout_session import (
    PLAN_ID_TO_STRIPE_PRICE_ID,
    build_checkout_session_params,
)

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
    else:
        FAIL += 1
        print(f"FAIL: {label}")


def test_raises_for_empty_workshop_id():
    try:
        build_checkout_session_params("", "light")
        check("空文字列workshop_idでValueError", False)
    except ValueError:
        check("空文字列workshop_idでValueError", True)


def test_raises_for_none_workshop_id():
    try:
        build_checkout_session_params(None, "light")
        check("None workshop_idでValueError", False)
    except ValueError:
        check("None workshop_idでValueError", True)


def test_raises_for_unknown_plan_id():
    try:
        build_checkout_session_params("W1", "unknown_plan")
        check("未知のplan_idでValueError", False)
    except ValueError:
        check("未知のplan_idでValueError", True)


def test_basic_params_without_existing_customer():
    params = build_checkout_session_params("W1", "light")
    check("mode=subscription", params["mode"] == "subscription")
    check("client_reference_id=workshop_id", params["client_reference_id"] == "W1")
    check(
        "line_itemsにlightのPrice IDを設定",
        params["line_items"] == [{"price": PLAN_ID_TO_STRIPE_PRICE_ID["light"], "quantity": 1}],
    )
    check("customerキーは含まれない", "customer" not in params)
    check("success_urlが既定値", params["success_url"].endswith("/success"))
    check("cancel_urlが既定値", params["cancel_url"].endswith("/cancel"))


def test_includes_customer_when_existing_stripe_customer_id_given():
    params = build_checkout_session_params("W2", "standard", existing_stripe_customer_id="cus_123")
    check("customer=既存stripe_customer_id", params["customer"] == "cus_123")
    check(
        "line_itemsにstandardのPrice IDを設定",
        params["line_items"] == [{"price": PLAN_ID_TO_STRIPE_PRICE_ID["standard"], "quantity": 1}],
    )


def test_multi_craftsman_plan_resolves_correct_price_id():
    params = build_checkout_session_params("W3", "multi_craftsman")
    check(
        "line_itemsにmulti_craftsmanのPrice IDを設定",
        params["line_items"] == [{"price": PLAN_ID_TO_STRIPE_PRICE_ID["multi_craftsman"], "quantity": 1}],
    )


def test_custom_success_and_cancel_url_override_defaults():
    params = build_checkout_session_params(
        "W4",
        "light",
        success_url="https://example.com/custom/success",
        cancel_url="https://example.com/custom/cancel",
    )
    check("success_urlの上書きが反映される", params["success_url"] == "https://example.com/custom/success")
    check("cancel_urlの上書きが反映される", params["cancel_url"] == "https://example.com/custom/cancel")


if __name__ == "__main__":
    test_raises_for_empty_workshop_id()
    test_raises_for_none_workshop_id()
    test_raises_for_unknown_plan_id()
    test_basic_params_without_existing_customer()
    test_includes_customer_when_existing_stripe_customer_id_given()
    test_multi_craftsman_plan_resolves_correct_price_id()
    test_custom_success_and_cancel_url_override_defaults()
    print(f"PASS={PASS} FAIL={FAIL}")
    if FAIL:
        raise SystemExit(1)
