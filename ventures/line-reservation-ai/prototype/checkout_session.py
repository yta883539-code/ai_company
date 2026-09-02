#!/usr/bin/env python3
"""checkout-initiation-flow-design.md(フェーズ続き139)で設計した、Stripe Checkout Session
作成APIへ渡すパラメータ、およびLINEへ戻る導線のリンクを組み立てるロジック。

位置づけ:
- 実LIFF(LINE Front-end Framework)のIDトークン検証、実Stripe Checkout Session作成API
  呼び出し、LINE公式アカウント開設(Basic ID確定)はいずれも実アカウント接続後の話であり、
  外部サービスへの設定・実HTTPリクエスト送信を伴うためオーナー承認待ち(pending-approval.md
  参照)。
- 本モジュールはそれとは独立に、認証済みuser_id(呼び出し元でLIFF IDトークン検証済みの
  前提)と既存stripe_customer_idの有無からCheckout Session作成APIへ渡すパラメータを組み立てる
  部分、および公式アカウントのBasic IDからLINEへ戻るユニバーサルリンクを組み立てる部分のみを、
  実HTTPリクエストなしで検証可能にしたもの。
- `verify_checkout_authorization()`/`render_checkout_authorization_error_page()`
  (2026-09-02追記): checkout-initiation-flow-design.md 9節・10節、store-id-resolution-and-
  owner-identity-design.md「残課題」に残っていた、認可チェック(`store_id`から解決した
  `owner_user_id`とLIFF IDトークン検証済みの個人`user_id`の一致確認)不一致時のオーナー向け
  エラー文言・案内先を設計・実装した。

設計の参照元: checkout-initiation-flow-design.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote

from store_profile_store import StoreProfileStoreProtocol

# design 3節: 実LPドメイン確定までの仮のプレースホルダ。呼び出し元・テストで上書き可能。
DEFAULT_SUCCESS_URL = "https://example.com/line-reservation-ai/checkout/success"
DEFAULT_CANCEL_URL = "https://example.com/line-reservation-ai/checkout/cancel"

_LINE_UNIVERSAL_LINK_BASE = "https://line.me/R/ti/p/"


def build_checkout_session_params(
    user_id: str,
    existing_stripe_customer_id: Optional[str] = None,
    *,
    success_url: str = DEFAULT_SUCCESS_URL,
    cancel_url: str = DEFAULT_CANCEL_URL,
) -> dict:
    """Stripe Checkout Session作成APIへ渡すパラメータを組み立てる(design 3節・5節)。

    - `user_id`は店舗オーナーのLINE user_id(design 0節)。空文字列・Noneの場合は
      `ValueError`。呼び出し元でLIFF IDトークン検証済みの認証済みuser_idが必ず先に
      得られている前提を明示するガード。
    - `existing_stripe_customer_id`が渡された場合のみ`"customer"`キーを追加し、既存の
      Stripe顧客を再利用する(重複顧客レコード防止、design 3節手順3)。
    """
    if not user_id:
        raise ValueError("user_id must be a non-empty string")

    params: dict = {
        "mode": "subscription",
        "client_reference_id": user_id,
        "success_url": success_url,
        "cancel_url": cancel_url,
    }
    if existing_stripe_customer_id:
        params["customer"] = existing_stripe_customer_id

    return params


def build_line_return_link(basic_id: str) -> str:
    """LINE公式アカウントのトーク画面へ戻るユニバーサルリンクを組み立てる(design 4節)。

    `https://line.me/R/ti/p/{basic_id}`形式。LINEアプリが端末にインストールされていれば
    アプリを起動しトーク画面へ、未インストールならブラウザでLINEのダウンロード誘導ページへ
    遷移する(design 4節で比較した3案のうち、ユニバーサルリンク案を採用)。

    `basic_id`が空文字列・Noneの場合は`ValueError`(公式アカウント開設〈オーナー承認待ち〉
    前に誤ったリンクを組み立てて掲載してしまう事故を防ぐガード)。
    """
    if not basic_id:
        raise ValueError("basic_id must be a non-empty string")

    return _LINE_UNIVERSAL_LINK_BASE + quote(basic_id)


# design 9節手順3の認可チェック不一致理由(design 10節)。
AUTHORIZATION_DENIED_OWNER_NOT_SET = "owner_user_id_not_set"
AUTHORIZATION_DENIED_USER_ID_MISMATCH = "user_id_mismatch"


@dataclass
class AuthorizationResult:
    """`verify_checkout_authorization()`の結果(design 10節)。

    `authorized`がFalseの場合、`denied_reason`は
    `AUTHORIZATION_DENIED_OWNER_NOT_SET`(store_idに紐づく`owner_user_id`が
    未設定=接続テスト未実施)か`AUTHORIZATION_DENIED_USER_ID_MISMATCH`
    (検証済み個人user_idが`owner_user_id`と一致しない)のいずれかを保持する。
    """

    authorized: bool
    denied_reason: Optional[str] = None


def verify_checkout_authorization(
    store_id: str,
    requester_user_id: str,
    store: StoreProfileStoreProtocol,
) -> AuthorizationResult:
    """checkout-initiation-flow-design.md 9節手順3の認可チェック本体(design 10節で新設)。

    `store_id`・`requester_user_id`(LIFF IDトークン検証済みの個人user_id、呼び出し元で
    検証済みの前提)がいずれも空文字列・Noneの場合は`ValueError`(検証前の値を渡す呼び出し側の
    実装ミスを早期に検知するガードであり、`AuthorizationResult`では表現しない)。

    `store.get_owner_user_id(store_id)`が`None`(店舗が接続テストを未実施でowner_user_id
    未設定)の場合、`requester_user_id`と`owner_user_id`が一致しない場合のいずれも
    `authorized=False`を返し、決済(Checkout Session作成)を続行させない。
    """
    if not store_id:
        raise ValueError("store_id must be a non-empty string")
    if not requester_user_id:
        raise ValueError("requester_user_id must be a non-empty string")

    owner_user_id = store.get_owner_user_id(store_id)
    if owner_user_id is None:
        return AuthorizationResult(
            authorized=False, denied_reason=AUTHORIZATION_DENIED_OWNER_NOT_SET
        )
    if owner_user_id != requester_user_id:
        return AuthorizationResult(
            authorized=False, denied_reason=AUTHORIZATION_DENIED_USER_ID_MISMATCH
        )
    return AuthorizationResult(authorized=True)


# design 10節: success_urlページと同じ「単一トーン(standard相当)で統一する」方針
# (checkout-initiation-flow-design.md 4節)を踏襲し、エラーページもトーン分岐しない。
_AUTHORIZATION_ERROR_MESSAGES = {
    AUTHORIZATION_DENIED_OWNER_NOT_SET: (
        "お支払い手続きを開始できませんでした。\n"
        "このお店ではまだ【予約とれる君】の接続テストが完了していないため、"
        "オーナー様の確認が取れていません。\n"
        "お手数ですが、まずはLINEのトーク画面で接続テストメッセージを送信のうえ、"
        "あらためて手続きをお試しください。"
    ),
    AUTHORIZATION_DENIED_USER_ID_MISMATCH: (
        "お支払い手続きを開始できませんでした。\n"
        "このお店のお支払い手続きは、接続テストを行ったオーナー様のLINEアカウントからのみ"
        "行っていただけます。\n"
        "オーナー様ご本人のLINEアカウントで、あらためて手続きをお試しください。"
    ),
}

_AUTHORIZATION_ERROR_TITLE = "お支払い手続きを続けられません"


def render_checkout_authorization_error_page(
    denied_reason: str, line_return_link: str
) -> str:
    """認可チェック不一致時にsuccess_url/cancel_urlと同じWeb静的ページとして表示する
    エラー文言を組み立てる(design 10節)。

    `denied_reason`は`AUTHORIZATION_DENIED_OWNER_NOT_SET`/
    `AUTHORIZATION_DENIED_USER_ID_MISMATCH`のいずれか(未知の値は`ValueError`、
    `AuthorizationResult.denied_reason`以外の値を誤って渡す実装ミスを早期に検知する)。
    `line_return_link`は`build_line_return_link()`の返り値をそのまま渡す想定で、
    success_urlページ(design 4節)と同じ「LINEに戻る」導線をエラー時にも用意する。
    """
    if denied_reason not in _AUTHORIZATION_ERROR_MESSAGES:
        raise ValueError(f"unknown denied_reason: {denied_reason!r}")
    if not line_return_link:
        raise ValueError("line_return_link must be a non-empty string")

    body = _AUTHORIZATION_ERROR_MESSAGES[denied_reason]
    return (
        f"{_AUTHORIZATION_ERROR_TITLE}\n\n"
        f"{body}\n\n"
        f"▼ LINEに戻る\n"
        f"{line_return_link}"
    )
