#!/usr/bin/env python3
"""checkout-initiation-flow-design.md(フェーズ続き139)「残課題」の店舗プロフィールストア
(`stripe_customer_id`保持用)を実装する。

位置づけ:
- firestore-data-model.md 1節`stores/{storeId}`ドキュメントに`stripeCustomerId`フィールドを
  追加する形を想定した`StoreProfileStoreProtocol`と、その場しのぎ検証用の
  `InMemoryStoreProfileStore`を提供する。
- course-set-pasha/stripe-customer-id-linking-design.mdの`UserProfileStoreProtocol`拡張
  (`set_stripe_customer_id`/逆引き)と同じ考え方だが、本venture(line-reservation-ai)では
  逆引き(`stripe_customer_id → user_id`)はcheckout-initiation-flow-design.mdの範囲では
  不要(Webhookディスパッチのresolve_user_id側は本ventureでは別課題として未着手)なため、
  順引き(`user_id → stripe_customer_id`)の2メソッドのみを持たせる薄いスコープとする。
- 実Firestore接続(GCPプロジェクト設定を伴う)はオーナー承認待ちのため、本モジュールは
  実HTTPリクエスト・実DB接続なしで検証可能な範囲(Protocol定義・InMemory実装・
  `build_checkout_session_params()`との結線ヘルパー)にとどめる。

設計の参照元: checkout-initiation-flow-design.md 3節、firestore-data-model.md 1節
"""

from __future__ import annotations

from typing import Optional, Protocol


class StoreProfileStoreProtocol(Protocol):
    """`stores/{storeId}`ドキュメントの`stripeCustomerId`フィールドを読み書きするための
    最小インターフェース(firestore-data-model.md 1節)。"""

    def get_stripe_customer_id(self, user_id: str) -> Optional[str]:
        ...

    def set_stripe_customer_id(self, user_id: str, stripe_customer_id: str) -> None:
        ...


class InMemoryStoreProfileStore:
    """実Firestore接続前の検証用スタブ。プロセス内の`dict`に保持するのみで、
    course-set-pasha/stripe_webhook.pyの`InMemoryUserProfileStore`と同様、
    呼び出しをまたいだ永続化(実Cloud Functions環境でのコールドスタート間保持)は
    保証しない暫定実装。"""

    def __init__(self) -> None:
        self._stripe_customer_ids: dict[str, str] = {}

    def get_stripe_customer_id(self, user_id: str) -> Optional[str]:
        return self._stripe_customer_ids.get(user_id)

    def set_stripe_customer_id(self, user_id: str, stripe_customer_id: str) -> None:
        if not user_id:
            raise ValueError("user_id must be a non-empty string")
        if not stripe_customer_id:
            raise ValueError("stripe_customer_id must be a non-empty string")
        self._stripe_customer_ids[user_id] = stripe_customer_id


def resolve_existing_stripe_customer_id(
    user_id: str, store: StoreProfileStoreProtocol
) -> Optional[str]:
    """checkout-initiation-flow-design.md 3節手順3
    (`build_checkout_session_params()`呼び出し前に既存customerの有無を確認する処理)に対応する
    薄いヘルパー。`store.get_stripe_customer_id()`をそのまま呼ぶだけだが、呼び出し元
    (Checkout Session作成エンドポイント予定地)で`store`の型を意識せず
    `StoreProfileStoreProtocol`のみに依存させるための結線点として切り出す。
    """
    if not user_id:
        raise ValueError("user_id must be a non-empty string")
    return store.get_stripe_customer_id(user_id)
