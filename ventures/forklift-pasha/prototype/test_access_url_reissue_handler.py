#!/usr/bin/env python3
"""access_url_reissue_handler.pyの境界値テスト(フェーズ135)。pure stdlibのみで実行する
(test_access_token_store.py等と同じ方針)。

実行方法: python3 prototype/test_access_url_reissue_handler.py
"""

import sys

from access_token_store import (
    AccessTokenStoreUrlProvider,
    InMemoryAccessTokenStore,
    issue_initial_access_token,
)
from access_url_reissue_handler import (
    ReissueRequestRejected,
    handle_reissue_request,
    receive_reissue_request,
)
from trial_management import InMemoryFleetOperatorStore


def _check(label, actual, expected):
    if actual == expected:
        print(f"[OK] {label}")
        return True
    print(f"[NG] {label}: 期待={expected!r} 実際={actual!r}")
    return False


def _make_deps(base_url="https://example.com"):
    token_store = InMemoryAccessTokenStore()
    email_store = InMemoryFleetOperatorStore()
    provider = AccessTokenStoreUrlProvider(token_store, base_url)
    return token_store, email_store, provider


def main():
    results = []

    # --- 新しいメールアドレスの入力なし: 既存アドレス宛への単純な再発行 ---
    token_store, email_store, provider = _make_deps()
    email_store.set_email("op1", "owner@example.com")
    old_token = issue_initial_access_token(token_store, "op1")

    result = handle_reissue_request(token_store, email_store, provider, "op1")

    results.append(_check(
        "新トークンは旧トークンと異なる",
        token_store.get_access_token("op1") != old_token,
        True,
    ))
    results.append(_check(
        "旧トークンは失効している(逆引き不可)",
        token_store.get_internal_id_by_access_token(old_token),
        None,
    ))
    results.append(_check(
        "送信先は既存の登録アドレスのまま",
        result.destination_email,
        "owner@example.com",
    ))
    results.append(_check(
        "email_changedはFalse",
        result.email_changed,
        False,
    ))
    results.append(_check(
        "new_access_urlは新トークンを含むURL",
        result.new_access_url,
        f"https://example.com/f/{token_store.get_access_token('op1')}",
    ))

    # --- 新しいメールアドレスを入力: メールアドレス変更を伴う再発行 ---
    token_store, email_store, provider = _make_deps()
    email_store.set_email("op2", "old@example.com")
    issue_initial_access_token(token_store, "op2")

    result = handle_reissue_request(
        token_store, email_store, provider, "op2", new_email="new@example.com"
    )

    results.append(_check(
        "メールアドレスが更新されている",
        email_store.get_email("op2"),
        "new@example.com",
    ))
    results.append(_check(
        "送信先は新アドレス",
        result.destination_email,
        "new@example.com",
    ))
    results.append(_check(
        "email_changedはTrue",
        result.email_changed,
        True,
    ))

    # --- 新しいメールアドレス欄が空白のみ: 「変更なし」として扱う ---
    token_store, email_store, provider = _make_deps()
    email_store.set_email("op3", "owner3@example.com")
    issue_initial_access_token(token_store, "op3")

    result = handle_reissue_request(
        token_store, email_store, provider, "op3", new_email="   "
    )

    results.append(_check(
        "空白のみの入力はメールアドレスを変更しない",
        email_store.get_email("op3"),
        "owner3@example.com",
    ))
    results.append(_check(
        "空白のみの入力はemail_changed=False",
        result.email_changed,
        False,
    ))

    # --- 不正な形式のメールアドレス: 例外を送出し、トークンは再発行しない ---
    token_store, email_store, provider = _make_deps()
    email_store.set_email("op4", "owner4@example.com")
    old_token = issue_initial_access_token(token_store, "op4")

    raised = False
    try:
        handle_reissue_request(
            token_store, email_store, provider, "op4", new_email="not-an-email"
        )
    except ReissueRequestRejected:
        raised = True

    results.append(_check(
        "不正な形式のメールアドレスはReissueRequestRejectedを送出する",
        raised,
        True,
    ))
    results.append(_check(
        "拒否された場合トークンは再発行されない",
        token_store.get_access_token("op4"),
        old_token,
    ))
    results.append(_check(
        "拒否された場合メールアドレスも変更されない",
        email_store.get_email("op4"),
        "owner4@example.com",
    ))

    # --- receive_reissue_request(): 正常系(有効なaccess_token) ---
    token_store, email_store, provider = _make_deps()
    email_store.set_email("op5", "owner5@example.com")
    token5 = issue_initial_access_token(token_store, "op5")

    http_result = receive_reissue_request(token_store, email_store, provider, token5)

    results.append(_check(
        "正常系のstatus_codeは200",
        http_result.status_code,
        200,
    ))
    results.append(_check(
        "正常系のresult.internal_idは解決したinternal_idと一致",
        http_result.result.internal_id if http_result.result else None,
        "op5",
    ))
    results.append(_check(
        "正常系はerrorを持たない",
        http_result.error,
        None,
    ))

    # --- receive_reissue_request(): access_token欠落 ---
    token_store, email_store, provider = _make_deps()
    email_store.set_email("op6", "owner6@example.com")
    issue_initial_access_token(token_store, "op6")

    http_result = receive_reissue_request(token_store, email_store, provider, "")

    results.append(_check(
        "access_token欠落時のstatus_codeは400",
        http_result.status_code,
        400,
    ))
    results.append(_check(
        "access_token欠落時のerrorはmissing_access_token",
        http_result.error,
        "missing_access_token",
    ))
    results.append(_check(
        "access_token欠落時はhandle_reissue_request()が呼ばれずメールアドレスも変化しない",
        email_store.get_email("op6"),
        "owner6@example.com",
    ))

    # --- receive_reissue_request(): 無効なaccess_token ---
    token_store, email_store, provider = _make_deps()

    http_result = receive_reissue_request(
        token_store, email_store, provider, "no-such-token"
    )

    results.append(_check(
        "無効なaccess_tokenのstatus_codeは404",
        http_result.status_code,
        404,
    ))
    results.append(_check(
        "無効なaccess_tokenのerrorはunknown_access_token",
        http_result.error,
        "unknown_access_token",
    ))

    # --- receive_reissue_request(): 不正なnew_email(トークンは再発行されない) ---
    token_store, email_store, provider = _make_deps()
    email_store.set_email("op7", "owner7@example.com")
    token7 = issue_initial_access_token(token_store, "op7")

    http_result = receive_reissue_request(
        token_store, email_store, provider, token7, new_email="not-an-email"
    )

    results.append(_check(
        "不正なnew_emailのstatus_codeは400",
        http_result.status_code,
        400,
    ))
    results.append(_check(
        "不正なnew_emailのerrorはinvalid_email",
        http_result.error,
        "invalid_email",
    ))
    results.append(_check(
        "不正なnew_emailの場合アクセストークンは再発行されない",
        token_store.get_access_token("op7"),
        token7,
    ))
    results.append(_check(
        "不正なnew_emailの場合メールアドレスも変更されない",
        email_store.get_email("op7"),
        "owner7@example.com",
    ))

    ok = all(results)
    print(f"\n{sum(results)}/{len(results)} passed")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
