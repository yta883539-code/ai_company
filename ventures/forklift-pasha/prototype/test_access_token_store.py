#!/usr/bin/env python3
"""access_token_store.pyの境界値テスト(フェーズ134)。pure stdlibのみで実行する
(test_trial_management.py等と同じ方針)。

実行方法: python3 prototype/test_access_token_store.py
"""

import sys
from datetime import datetime

from access_token_store import (
    AccessTokenStoreUrlProvider,
    InMemoryAccessTokenStore,
    issue_initial_access_token,
    record_access_and_get_previous,
    reissue_access_token,
)


def _check(label, actual, expected):
    if actual == expected:
        print(f"[OK] {label}")
        return True
    print(f"[NG] {label}: 期待={expected!r} 実際={actual!r}")
    return False


def main():
    results = []

    # --- issue_initial_access_token: 初回は新規発行し、以降は同じ値を返す ---
    store = InMemoryAccessTokenStore()
    token1 = issue_initial_access_token(store, "op1")
    token1_again = issue_initial_access_token(store, "op1")
    results.append(_check(
        "issue_initial_access_token: 二重呼び出しでも値が変わらない",
        token1_again,
        token1,
    ))
    results.append(_check(
        "issue_initial_access_token: ストアに反映されている",
        store.get_access_token("op1"),
        token1,
    ))
    results.append(_check(
        "issue_initial_access_token: 逆引きできる",
        store.get_internal_id_by_access_token(token1),
        "op1",
    ))

    # --- reissue_access_token: 常に新トークンを発行し、旧トークンは失効する ---
    store = InMemoryAccessTokenStore()
    old_token = issue_initial_access_token(store, "op2")
    new_token = reissue_access_token(store, "op2")
    results.append(_check(
        "reissue_access_token: 新トークンは旧トークンと異なる",
        new_token != old_token,
        True,
    ))
    results.append(_check(
        "reissue_access_token: ストアの値が新トークンに更新されている",
        store.get_access_token("op2"),
        new_token,
    ))
    results.append(_check(
        "reissue_access_token: 旧トークンでの逆引きは失効している",
        store.get_internal_id_by_access_token(old_token),
        None,
    ))
    results.append(_check(
        "reissue_access_token: 新トークンで逆引きできる",
        store.get_internal_id_by_access_token(new_token),
        "op2",
    ))

    # --- 2者のトークンは独立している ---
    store = InMemoryAccessTokenStore()
    token_a = issue_initial_access_token(store, "opA")
    token_b = issue_initial_access_token(store, "opB")
    results.append(_check(
        "issue_initial_access_token: 2者のトークンは異なる",
        token_a != token_b,
        True,
    ))

    # --- record_access_and_get_previous: 初回アクセスは前回値がNone ---
    store = InMemoryAccessTokenStore()
    now1 = datetime(2026, 10, 12, 9, 0, 0)
    previous = record_access_and_get_previous(store, "op3", now1)
    results.append(_check(
        "record_access_and_get_previous: 初回アクセスの前回値はNone",
        previous,
        None,
    ))
    results.append(_check(
        "record_access_and_get_previous: 今回のアクセス時刻が保存されている",
        store.get_last_accessed_at("op3"),
        now1,
    ))

    # --- record_access_and_get_previous: 2回目は1回目の時刻を前回値として返す ---
    now2 = datetime(2026, 10, 13, 10, 30, 0)
    previous2 = record_access_and_get_previous(store, "op3", now2)
    results.append(_check(
        "record_access_and_get_previous: 2回目アクセスの前回値は1回目の時刻",
        previous2,
        now1,
    ))
    results.append(_check(
        "record_access_and_get_previous: 2回目アクセスで保存値が更新されている",
        store.get_last_accessed_at("op3"),
        now2,
    ))

    # --- AccessTokenStoreUrlProvider: トークン未発行はNone ---
    store = InMemoryAccessTokenStore()
    provider = AccessTokenStoreUrlProvider(store, "https://example.com")
    results.append(_check(
        "AccessTokenStoreUrlProvider: トークン未発行はNone",
        provider.get_access_url("op4"),
        None,
    ))

    # --- AccessTokenStoreUrlProvider: トークン発行済みはURLを組み立てる ---
    token4 = issue_initial_access_token(store, "op4")
    results.append(_check(
        "AccessTokenStoreUrlProvider: 発行済みトークンからURLを組み立てる",
        provider.get_access_url("op4"),
        f"https://example.com/f/{token4}",
    ))

    # --- AccessTokenStoreUrlProvider: base_urlの末尾スラッシュは二重にならない ---
    provider_trailing_slash = AccessTokenStoreUrlProvider(store, "https://example.com/")
    results.append(_check(
        "AccessTokenStoreUrlProvider: base_url末尾スラッシュがあっても二重にならない",
        provider_trailing_slash.get_access_url("op4"),
        f"https://example.com/f/{token4}",
    ))

    passed = sum(1 for r in results if r)
    total = len(results)
    print(f"\n{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
