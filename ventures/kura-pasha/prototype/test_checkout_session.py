#!/usr/bin/env python3
"""checkout_session.pyの検証用テスト。`python3 test_checkout_session.py`で実行する。"""

from checkout_session import (
    DEFAULT_CHECKOUT_PLAN,
    PLAN_ID_TO_STRIPE_PRICE_ID,
    START_CHECKOUT_POSTBACK_DATA,
    build_checkout_session_params,
    build_start_checkout_postback_data,
    parse_start_checkout_postback_data,
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
    check("metadata.plan_idにplan_idを埋め込む", params["metadata"] == {"plan_id": "light"})


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


def test_build_start_checkout_postback_data_embeds_plan_id():
    check(
        "light用postback_data",
        build_start_checkout_postback_data("light") == "action=start_checkout&plan=light",
    )
    check(
        "multi_craftsman用postback_data",
        build_start_checkout_postback_data("multi_craftsman")
        == "action=start_checkout&plan=multi_craftsman",
    )


def test_build_start_checkout_postback_data_raises_for_unknown_plan_id():
    try:
        build_start_checkout_postback_data("unknown_plan")
        check("未知のplan_idでValueError(build)", False)
    except ValueError:
        check("未知のplan_idでValueError(build)", True)


def test_parse_start_checkout_postback_data_plan_specific():
    check(
        "plan=standardを解釈",
        parse_start_checkout_postback_data("action=start_checkout&plan=standard") == "standard",
    )
    check(
        "plan=multi_craftsmanを解釈",
        parse_start_checkout_postback_data("action=start_checkout&plan=multi_craftsman")
        == "multi_craftsman",
    )


def test_parse_start_checkout_postback_data_plan_unspecified_returns_default():
    check(
        "プラン未指定はDEFAULT_CHECKOUT_PLAN",
        parse_start_checkout_postback_data(START_CHECKOUT_POSTBACK_DATA) == DEFAULT_CHECKOUT_PLAN,
    )


def test_parse_start_checkout_postback_data_returns_none_for_unrelated_or_unknown():
    check("無関係なdataはNone", parse_start_checkout_postback_data("action=cancel_subscription") is None)
    check("Noneはそのまま None", parse_start_checkout_postback_data(None) is None)
    check(
        "未知のplan_idはNone",
        parse_start_checkout_postback_data("action=start_checkout&plan=unknown_plan") is None,
    )


if __name__ == "__main__":
    test_raises_for_empty_workshop_id()
    test_raises_for_none_workshop_id()
    test_raises_for_unknown_plan_id()
    test_basic_params_without_existing_customer()
    test_includes_customer_when_existing_stripe_customer_id_given()
    test_multi_craftsman_plan_resolves_correct_price_id()
    test_custom_success_and_cancel_url_override_defaults()
    test_build_start_checkout_postback_data_embeds_plan_id()
    test_build_start_checkout_postback_data_raises_for_unknown_plan_id()
    test_parse_start_checkout_postback_data_plan_specific()
    test_parse_start_checkout_postback_data_plan_unspecified_returns_default()
    test_parse_start_checkout_postback_data_returns_none_for_unrelated_or_unknown()
    print(f"PASS={PASS} FAIL={FAIL}")
    if FAIL:
        raise SystemExit(1)
