#!/usr/bin/env python3
"""portal_session.pyの検証用テスト。`python3 test_portal_session.py`で実行する。

portal-session-provider-design.md 2節のパラメータ組み立てルール・StripePortalLinkProvider
(user_id→workshop_id→stripe_customer_idの2ホップ解決・契約者本人限定)の挙動を確認する。
"""

from portal_session import (
    DEFAULT_RETURN_URL,
    StripePortalLinkProvider,
    build_portal_session_params,
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


class _StubUserProfileStore:
    def __init__(self, workshop_ids=None):
        self._workshop_ids = workshop_ids or {}
        self.get_workshop_id_calls = []

    def get_workshop_id(self, user_id):
        self.get_workshop_id_calls.append(user_id)
        return self._workshop_ids.get(user_id)


class _StubWorkshopStore:
    def __init__(self, contractor_user_ids=None, stripe_customer_ids=None):
        self._contractor_user_ids = contractor_user_ids or {}
        self._stripe_customer_ids = stripe_customer_ids or {}
        self.get_contractor_user_id_calls = []
        self.get_stripe_customer_id_calls = []

    def get_contractor_user_id(self, workshop_id):
        self.get_contractor_user_id_calls.append(workshop_id)
        return self._contractor_user_ids[workshop_id]

    def get_stripe_customer_id(self, workshop_id):
        self.get_stripe_customer_id_calls.append(workshop_id)
        return self._stripe_customer_ids.get(workshop_id)


def test_build_params_raises_for_empty_stripe_customer_id():
    try:
        build_portal_session_params("")
        check("空文字列stripe_customer_idでValueError", False)
    except ValueError:
        check("空文字列stripe_customer_idでValueError", True)


def test_build_params_raises_for_none_stripe_customer_id():
    try:
        build_portal_session_params(None)
        check("None stripe_customer_idでValueError", False)
    except ValueError:
        check("None stripe_customer_idでValueError", True)


def test_build_params_contain_customer_and_default_return_url():
    params = build_portal_session_params("cus_existing456")
    check("customerが一致", params["customer"] == "cus_existing456")
    check("return_urlがデフォルト", params["return_url"] == DEFAULT_RETURN_URL)


def test_build_params_custom_return_url_is_used():
    params = build_portal_session_params("cus_existing456", return_url="https://example.com/back")
    check("カスタムreturn_urlが反映", params["return_url"] == "https://example.com/back")


def test_returns_none_when_user_not_linked_to_any_workshop():
    user_store = _StubUserProfileStore()
    workshop_store = _StubWorkshopStore()
    creator_calls = []
    provider = StripePortalLinkProvider(
        user_store,
        workshop_store,
        session_creator=lambda params: creator_calls.append(params) or "unused",
    )

    result = provider.get_portal_url("u_unknown")

    check("未紐付けuser_idはNone", result is None)
    check("session_creatorは呼ばれない", creator_calls == [])
    check("get_workshop_idが呼ばれる", user_store.get_workshop_id_calls == ["u_unknown"])


def test_returns_none_when_user_is_not_the_contractor():
    user_store = _StubUserProfileStore({"u_member": "w1"})
    workshop_store = _StubWorkshopStore(
        contractor_user_ids={"w1": "u_contractor"},
        stripe_customer_ids={"w1": "cus_123"},
    )
    creator_calls = []
    provider = StripePortalLinkProvider(
        user_store,
        workshop_store,
        session_creator=lambda params: creator_calls.append(params) or "unused",
    )

    result = provider.get_portal_url("u_member")

    check("契約者以外はNone", result is None)
    check("session_creatorは呼ばれない(契約者以外)", creator_calls == [])
    check(
        "get_stripe_customer_idは呼ばれない(契約者判定で打ち切り)",
        workshop_store.get_stripe_customer_id_calls == [],
    )


def test_returns_none_when_contractor_has_no_stripe_customer_id():
    user_store = _StubUserProfileStore({"u_contractor": "w1"})
    workshop_store = _StubWorkshopStore(
        contractor_user_ids={"w1": "u_contractor"},
        stripe_customer_ids={},
    )
    creator_calls = []
    provider = StripePortalLinkProvider(
        user_store,
        workshop_store,
        session_creator=lambda params: creator_calls.append(params) or "unused",
    )

    result = provider.get_portal_url("u_contractor")

    check("stripe_customer_id未登録はNone", result is None)
    check("session_creatorは呼ばれない(未登録)", creator_calls == [])


def test_calls_session_creator_with_built_params_and_returns_its_result():
    user_store = _StubUserProfileStore({"u_contractor": "w1"})
    workshop_store = _StubWorkshopStore(
        contractor_user_ids={"w1": "u_contractor"},
        stripe_customer_ids={"w1": "cus_existing456"},
    )
    creator_calls = []

    def fake_session_creator(params):
        creator_calls.append(params)
        return "https://billing.stripe.com/p/session/fake123"

    provider = StripePortalLinkProvider(user_store, workshop_store, session_creator=fake_session_creator)

    result = provider.get_portal_url("u_contractor")

    check("契約者は正しいURLを取得", result == "https://billing.stripe.com/p/session/fake123")
    check(
        "session_creatorへ正しいparamsが渡る",
        creator_calls == [{"customer": "cus_existing456", "return_url": DEFAULT_RETURN_URL}],
    )


def test_custom_return_url_is_propagated_to_session_creator():
    user_store = _StubUserProfileStore({"u_contractor": "w1"})
    workshop_store = _StubWorkshopStore(
        contractor_user_ids={"w1": "u_contractor"},
        stripe_customer_ids={"w1": "cus_existing456"},
    )
    creator_calls = []
    provider = StripePortalLinkProvider(
        user_store,
        workshop_store,
        session_creator=lambda params: creator_calls.append(params) or "url",
        return_url="https://example.com/back",
    )

    provider.get_portal_url("u_contractor")

    check("カスタムreturn_urlがsession_creatorに伝播", creator_calls[0]["return_url"] == "https://example.com/back")


def test_default_session_creator_raises_not_implemented():
    user_store = _StubUserProfileStore({"u_contractor": "w1"})
    workshop_store = _StubWorkshopStore(
        contractor_user_ids={"w1": "u_contractor"},
        stripe_customer_ids={"w1": "cus_existing456"},
    )
    provider = StripePortalLinkProvider(user_store, workshop_store)

    try:
        provider.get_portal_url("u_contractor")
        check("デフォルトsession_creatorはNotImplementedError", False)
    except NotImplementedError:
        check("デフォルトsession_creatorはNotImplementedError", True)


if __name__ == "__main__":
    test_build_params_raises_for_empty_stripe_customer_id()
    test_build_params_raises_for_none_stripe_customer_id()
    test_build_params_contain_customer_and_default_return_url()
    test_build_params_custom_return_url_is_used()
    test_returns_none_when_user_not_linked_to_any_workshop()
    test_returns_none_when_user_is_not_the_contractor()
    test_returns_none_when_contractor_has_no_stripe_customer_id()
    test_calls_session_creator_with_built_params_and_returns_its_result()
    test_custom_return_url_is_propagated_to_session_creator()
    test_default_session_creator_raises_not_implemented()
    print(f"PASS={PASS} FAIL={FAIL}")
    if FAIL:
        raise SystemExit(1)
