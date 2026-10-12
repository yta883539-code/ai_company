#!/usr/bin/env python3
"""checkout_session.pyの境界値テスト(フェーズ125)。pure stdlibのみで実行する
(trial_management.py・plan_id_resolution.py等と同じ方針)。

実行方法: python3 prototype/test_checkout_session.py
"""

import sys

from access_token_store import InMemoryAccessTokenStore
from checkout_session import (
    PLAN_ID_TO_STRIPE_PRICE_ID,
    MockCheckoutSessionCreator,
    build_checkout_session_params,
    create_checkout_session,
    main as checkout_session_main,
)
from trial_management import InMemoryFleetOperatorStore


class _StubRequest:
    """main(request)のテスト用、functions_frameworkが渡すFlask Requestのうち
    `request.args.get()`インターフェースのみを模した最小スタブ(course-set-pasha/
    prototype/test_checkout_session.py `_StubFlaskRequest`と同系)。"""

    def __init__(self, args: dict):
        self.args = args


def _check(label, actual, expected):
    if actual == expected:
        print(f"[OK] {label}")
        return True
    print(f"[NG] {label}: 期待={expected!r} 実際={actual!r}")
    return False


def _check_raises(label, func, exc_type):
    try:
        func()
    except exc_type:
        print(f"[OK] {label}")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[NG] {label}: 期待={exc_type.__name__} 実際={type(e).__name__}")
        return False
    print(f"[NG] {label}: 例外が発生しなかった")
    return False


def main():
    results = []

    # --- 正常系: 新規顧客(email指定、existing_stripe_customer_id未指定) ---
    params = build_checkout_session_params("internal-1", "standard", email="owner@example.com")
    results.append(_check("mode=subscription", params["mode"], "subscription"))
    results.append(_check("client_reference_id=internal_id", params["client_reference_id"], "internal-1"))
    results.append(_check(
        "line_itemsはstandardのPrice ID",
        params["line_items"],
        [{"price": PLAN_ID_TO_STRIPE_PRICE_ID["standard"], "quantity": 1}],
    ))
    results.append(_check("metadata.plan=standard", params["metadata"], {"plan": "standard"}))
    results.append(_check("customer_emailが設定される", params.get("customer_email"), "owner@example.com"))
    results.append(_check("customerキーは設定されない", "customer" in params, False))
    results.append(_check("success_urlは既定値", params["success_url"].endswith("/success"), True))
    results.append(_check("cancel_urlは既定値", params["cancel_url"].endswith("/cancel"), True))

    # --- 正常系: 既存顧客(existing_stripe_customer_id指定) ---
    params2 = build_checkout_session_params(
        "internal-2", "fleet", email="owner2@example.com", existing_stripe_customer_id="cus_123"
    )
    results.append(_check("customer=既存Stripe顧客ID", params2.get("customer"), "cus_123"))
    results.append(_check(
        "existing_stripe_customer_id指定時はcustomer_emailを設定しない",
        "customer_email" in params2,
        False,
    ))
    results.append(_check("metadata.plan=fleet", params2["metadata"], {"plan": "fleet"}))

    # --- 正常系: emailもexisting_stripe_customer_idも未指定 ---
    params3 = build_checkout_session_params("internal-3", "light")
    results.append(_check("customer_emailキーは存在しない", "customer_email" in params3, False))
    results.append(_check("customerキーは存在しない", "customer" in params3, False))

    # --- 全既知プランでPrice IDが解決できる ---
    for plan_id in ("light", "standard", "fleet"):
        p = build_checkout_session_params("internal-x", plan_id)
        results.append(_check(
            f"plan_id={plan_id}のPrice IDが解決される",
            p["line_items"][0]["price"],
            PLAN_ID_TO_STRIPE_PRICE_ID[plan_id],
        ))

    # --- 異常系 ---
    results.append(_check_raises(
        "internal_idが空文字列はValueError",
        lambda: build_checkout_session_params("", "standard"),
        ValueError,
    ))
    results.append(_check_raises(
        "internal_idがNoneはValueError",
        lambda: build_checkout_session_params(None, "standard"),
        ValueError,
    ))
    results.append(_check_raises(
        "未知のplan_idはValueError",
        lambda: build_checkout_session_params("internal-1", "premium"),
        ValueError,
    ))

    # --- create_checkout_session(): 正常系 ---
    access_token_store = InMemoryAccessTokenStore()
    operator_store = InMemoryFleetOperatorStore()
    access_token_store.set_access_token("internal-10", "token-abc")
    operator_store.set_email("internal-10", "owner10@example.com")

    checkout_session_creator = MockCheckoutSessionCreator()

    result = create_checkout_session(
        "token-abc",
        "standard",
        access_token_store=access_token_store,
        operator_store=operator_store,
        checkout_session_creator=checkout_session_creator,
    )
    results.append(_check("正常系: status_code=200", result.status_code, 200))
    results.append(_check(
        "正常系: client_reference_idはaccess_tokenから解決したinternal_id",
        result.checkout_session_params["client_reference_id"],
        "internal-10",
    ))
    results.append(_check(
        "正常系: operator_storeのemailが反映される",
        result.checkout_session_params.get("customer_email"),
        "owner10@example.com",
    ))
    results.append(_check(
        "正常系: redirect_urlにinternal_idを含むCheckout URLが設定される",
        result.redirect_url,
        "https://checkout.stripe.com/mock-session/internal-10",
    ))

    # --- create_checkout_session(): 既存Stripe顧客 ---
    operator_store.set_stripe_customer_id("internal-10", "cus_existing")
    result_existing_customer = create_checkout_session(
        "token-abc",
        "fleet",
        access_token_store=access_token_store,
        operator_store=operator_store,
        checkout_session_creator=checkout_session_creator,
    )
    results.append(_check(
        "既存Stripe顧客: customerキーが設定される",
        result_existing_customer.checkout_session_params.get("customer"),
        "cus_existing",
    ))

    # --- create_checkout_session(): 異常系 ---
    results.append(_check(
        "access_token未指定は404",
        create_checkout_session(
            None,
            "standard",
            access_token_store=access_token_store,
            operator_store=operator_store,
            checkout_session_creator=checkout_session_creator,
        ).status_code,
        404,
    ))
    results.append(_check(
        "access_tokenが空文字列は404",
        create_checkout_session(
            "",
            "standard",
            access_token_store=access_token_store,
            operator_store=operator_store,
            checkout_session_creator=checkout_session_creator,
        ).status_code,
        404,
    ))
    results.append(_check(
        "未知のaccess_tokenは404",
        create_checkout_session(
            "token-unknown",
            "standard",
            access_token_store=access_token_store,
            operator_store=operator_store,
            checkout_session_creator=checkout_session_creator,
        ).status_code,
        404,
    ))
    results.append(_check(
        "未知のplan_idは400",
        create_checkout_session(
            "token-abc",
            "premium",
            access_token_store=access_token_store,
            operator_store=operator_store,
            checkout_session_creator=checkout_session_creator,
        ).status_code,
        400,
    ))
    results.append(_check(
        "plan_id未指定(None)は400",
        create_checkout_session(
            "token-abc",
            None,
            access_token_store=access_token_store,
            operator_store=operator_store,
            checkout_session_creator=checkout_session_creator,
        ).status_code,
        400,
    ))
    # 旧トークンでの照会は失効させる(access_token_store.set_access_tokenの既存方針)仕様を
    # 本関数越しにも確認する: 新トークンを再発行すると旧トークンは404になる。
    access_token_store.set_access_token("internal-10", "token-new")
    results.append(_check(
        "旧access_tokenは再発行後404(自然な失効)",
        create_checkout_session(
            "token-abc",
            "standard",
            access_token_store=access_token_store,
            operator_store=operator_store,
            checkout_session_creator=checkout_session_creator,
        ).status_code,
        404,
    ))

    # --- main(): Cloud Functionsエントリポイント自体の回帰確認(フェーズ144で303
    # リダイレクト返却に変更されたが、main()自体を直接呼ぶテストはこれまで無かった) ---
    body, status = checkout_session_main(_StubRequest({"plan": "light"}))
    results.append(_check("main(): access_token未指定は404", status, 404))
    results.append(_check(
        "main(): access_token未指定時のレスポンスボディ",
        body,
        "access_token_not_found",
    ))

    body_empty_args, status_empty_args = checkout_session_main(_StubRequest({}))
    results.append(_check(
        "main(): request.argsが空dictでも例外にならずaccess_token_not_found",
        (body_empty_args, status_empty_args),
        ("access_token_not_found", 404),
    ))

    # get_checkout_runtime_dependencies()はmain()が呼ばれるたびに新規のInMemoryストアを
    # 生成するため(同関数docstring記載の既知の限界)、main()越しに有効なaccess_tokenを
    # 渡しても常に未知のトークンとして404になる。したがってmain()の200/303応答(フェーズ144で
    # 実装したリダイレクト分岐)は、本テストファイルのように依存をmain()の外から注入できない
    # 限り到達できない。これは不具合ではなく既存の既知の限界の帰結であることをここで明示する。
    body_unknown, status_unknown = checkout_session_main(
        _StubRequest({"access_token": "token-abc", "plan": "light"})
    )
    results.append(_check(
        "main(): 有効そうなaccess_tokenを渡しても現状は404(本プロセス内で状態非保持のため、"
        "200/303応答はmain()への依存注入口が無い限り到達不可)",
        (body_unknown, status_unknown),
        ("access_token_not_found", 404),
    ))

    passed = sum(1 for r in results if r)
    print(f"\n{len(results)}件中{passed}件成功")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
