#!/usr/bin/env python3
"""
README.mdフェーズ102の次回候補(3)「Checkout Session作成エンドポイント自体(draft_id
採番からcreate_draft()呼び出し、Stripe Checkout Session作成までを結ぶCloud Function
エントリポイント)のコード化」に対応するモジュール。

one-time-checkout-no-account-design.md(フェーズ10)2節の手順1〜3、draft-id-last4-
collision-design.md(フェーズ53)1節のUUID4採用、draft-creation-and-event-memo-
storage-design.md(フェーズ102)で設計済みのcreate_draft()呼び出しを、Webフォーム
送信を受けてStripe Checkout Sessionを発行するまでの1本のエントリポイント関数として
結線する。

位置づけ:
- `stripe_webhook.py`が決済完了後(`checkout.session.completed`受信以降)を担うのに
  対し、本モジュールはその手前、Webフォーム送信直後(決済開始前)を担う。両者は
  `one_time_draft/{draft_id}`を介して疎結合(本モジュールが`create_draft()`で作成し、
  `stripe_webhook.py`が`mark_payment_confirmed()`以降で更新する)。
- 必須項目が欠落している場合(`form_submission_intake.handle_form_submission()`が
  `status=insufficient_input`応答を返す場合)はdraft自体を作成せずCheckout Sessionも
  作成しない(one-time-checkout-no-account-design.md 2節の前提どおり、決済は必須項目
  充足後にのみ発生させる)。
- 実Stripe API呼び出し(`stripe.checkout.Session.create()`相当)は
  `StripeCheckoutSessionClientProtocol`に委ね、本モジュールは`draft_id`発行・TTL
  (`expires_at`)算出・`create_draft()`呼び出し・Checkout Session作成呼び出しの順序と
  引数の組み立てのみを担う(実Stripeアカウント接続自体はオーナー承認待ちの範囲、
  pending-approval.md参照)。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from form_submission_intake import handle_form_submission

# one-time-checkout-no-account-design.md 2節: 単発利用プラン(500円/回、JPY)。
DEFAULT_AMOUNT_JPY = 500
DEFAULT_CURRENCY = "jpy"
# ttl-expiry-result-delivery-refund-design.md(フェーズ12)1節: 未決済ドラフトのTTL想定。
DEFAULT_TTL_HOURS = 24
# stripe-checkout-session-params-design.md(フェーズ105): Checkout決済ページ・レシートに
# 表示される商品名(price_dataインライン指定、固定のPrice IDは使わない)。
STRIPE_PRODUCT_NAME_JA = "イベントこみぐあいパシャっと 一次チェック(1回)"


def build_stripe_checkout_session_params(
    *,
    amount: int,
    currency: str,
    client_reference_id: str,
    success_url: str,
    cancel_url: str,
) -> dict:
    """実`stripe.checkout.Session.create(**params)`呼び出しにそのまま渡すparams dictを
    組み立てる(stripe-checkout-session-params-design.md参照)。

    aircon-pasha等のサブスクリプション(`mode="subscription"`、事前作成済みPrice ID参照)
    とは異なり、本ventureは単発決済(`mode="payment"`)かつ単一金額のため、Price IDを
    事前作成せず`price_data`で金額・商品名をインライン指定する方式を採用する。
    `StripeCheckoutSessionClientProtocol.create_session()`の実クライアント実装
    (実Stripeアカウント接続後、オーナー承認待ちの範囲)がこの関数の返り値を使う想定で、
    本関数自体は`stripe`パッケージに依存しない純粋関数。
    """
    return {
        "mode": "payment",
        "client_reference_id": client_reference_id,
        "success_url": success_url,
        "cancel_url": cancel_url,
        "line_items": [
            {
                "price_data": {
                    "currency": currency,
                    "unit_amount": amount,
                    "product_data": {
                        "name": STRIPE_PRODUCT_NAME_JA,
                    },
                },
                "quantity": 1,
            }
        ],
    }


@dataclass(frozen=True)
class CheckoutSessionResult:
    """`StripeCheckoutSessionClientProtocol.create_session()`の戻り値。実Stripe APIの
    `Session`オブジェクトのうち、本モジュールが使う2フィールドのみを抜き出した表現。"""

    session_id: str
    checkout_url: str


class StripeCheckoutSessionClientProtocol:
    """実Stripe Checkout Session作成呼び出しを抽象化するインターフェース(実接続は
    オーナー承認待ちの範囲のため、本モジュールからは呼び出し方式のみを規定する)。"""

    def create_session(
        self,
        *,
        amount: int,
        currency: str,
        client_reference_id: str,
        success_url: str,
        cancel_url: str,
    ) -> CheckoutSessionResult:
        """one-time-checkout-no-account-design.md 2節手順3: `mode="payment"`の
        Checkout Sessionを作成する。`customer_email`は呼び出し時に渡さず、Stripe
        Checkoutページ自体の標準のメールアドレス入力欄で収集する想定(ttl-expiry-
        result-delivery-refund-design.md 2節の`customer_email`必須化は、Checkout
        ページでの収集を前提にしたWebhook側〈`stripe_webhook.py`〉の処理を指す)。
        `success_url`/`cancel_url`の構築方式はcheckout-session-success-cancel-url-
        design.md(フェーズ104)参照。実クライアント実装は本メソッドの引数から
        `build_stripe_checkout_session_params()`(stripe-checkout-session-params-
        design.md、フェーズ105)でparams dictを組み立て、
        `stripe.checkout.Session.create(**params)`に渡す想定。"""
        raise NotImplementedError


class InMemoryCheckoutSessionClient(StripeCheckoutSessionClientProtocol):
    """submit-event-form-http-entry-point-design.md(フェーズ110)3節: 実Stripeアカウント
    接続(オーナー承認待ち)前の`main(request)`配線が使う検証用の既定実装。呼び出しごとに
    一意だが決定的でないセッションIDを返すのみで、実Stripe APIは呼び出さない。
    テスト専用のStubCheckoutSessionClient(test_checkout_session_creation.py、呼び出し
    記録を保持する)とは別物で、本番配線側のデフォルト値としてのみ使う。"""

    def create_session(
        self, *, amount, currency, client_reference_id, success_url, cancel_url
    ) -> CheckoutSessionResult:
        session_id = f"cs_inmemory_{uuid.uuid4()}"
        return CheckoutSessionResult(
            session_id=session_id,
            checkout_url=f"https://checkout.stripe.invalid/{session_id}",
        )


@dataclass(frozen=True)
class CheckoutSessionCreationResult:
    """`create_checkout_session_for_event_memo()`の戻り値。`outcome`で2経路を区別する。"""

    outcome: str  # "insufficient_input" | "checkout_session_created"
    insufficient_input_response: Optional[dict] = None
    draft_id: Optional[str] = None
    draft_id_last4: Optional[str] = None
    checkout_session_id: Optional[str] = None
    checkout_url: Optional[str] = None


def _default_draft_id_factory() -> str:
    # draft-id-last4-collision-design.md(フェーズ53)1節で確定済みのUUID4方式。
    return str(uuid.uuid4())


def create_checkout_session_for_event_memo(
    raw_payload: dict,
    draft_store,
    checkout_client: StripeCheckoutSessionClientProtocol,
    base_url: str,
    *,
    now: Optional[datetime] = None,
    ttl_hours: int = DEFAULT_TTL_HOURS,
    amount: int = DEFAULT_AMOUNT_JPY,
    currency: str = DEFAULT_CURRENCY,
    draft_id_factory: Callable[[], str] = _default_draft_id_factory,
    idempotency_store=None,
) -> CheckoutSessionCreationResult:
    """Webフォーム送信の生ペイロードを受け取り、(a)必須項目欠落ならinsufficient_input
    応答をその場で返す(draft・Checkout Sessionいずれも作成しない)、(b)充足していれば
    draft_idを発行して`one_time_draft/{draft_id}`を作成し、Stripe Checkout Sessionを
    作成して`draft_id`・`checkout_url`等を返す、という1本のエントリポイント。

    tech-stack.md(フェーズ7)が想定するCloud Run functionsのHTTPSトリガーから、
    Webフォームの生POSTボディ(dict化済み)を`raw_payload`としてそのまま渡される想定。
    `base_url`(末尾スラッシュなし)はsuccess_url/cancel_url構築用
    (checkout-session-success-cancel-url-design.md フェーズ104参照)。

    `idempotency_store`(idempotency_key_index_store.IdempotencyKeyIndexStoreProtocol
    相当、省略可)を渡した場合、`raw_payload["idempotency_key"]`(web-form-ui-design.md
    3節でクライアント側が送信ボタン押下時に生成する値)をキーに`reserve_or_get()`を呼ぶ
    (idempotency-key-write-conflict-control-design.mdフェーズ67の原子的衝突検知方式)。
    同一`idempotency_key`での再送(二重クリック・ネットワーク再試行等)が検知された場合は
    `one_time_draft`の新規作成をスキップし、既存`draft_id`に対してCheckout Sessionのみを
    新規作成して返す(idempotency-key-duplicate-detection-firestore-query-design.mdフェーズ70
    7.2節のとおり、Checkout Session自体はidempotency_keyに紐づかないため二重決済には
    つながらない)。`idempotency_store`省略時・`idempotency_key`未送信時は従来どおり常に
    新規draftを作成する(後方互換)。
    """

    intake_result = handle_form_submission(raw_payload)
    if "status" in intake_result:
        # design 2節: 必須項目充足後にのみ決済を発生させる(insufficient_input応答は
        # draft作成前にLLM・Stripeいずれも呼ばずその場で返す)。
        return CheckoutSessionCreationResult(
            outcome="insufficient_input",
            insufficient_input_response=intake_result,
        )

    candidate_draft_id = draft_id_factory()
    resolved_now = now if now is not None else datetime.now(timezone.utc)
    expires_at = resolved_now + timedelta(hours=ttl_hours)

    idempotency_key = raw_payload.get("idempotency_key")
    draft_id = candidate_draft_id
    if idempotency_store is not None and idempotency_key:
        draft_id = idempotency_store.reserve_or_get(
            idempotency_key,
            collection="one_time_draft",
            document_id=candidate_draft_id,
            created_at=resolved_now,
            expire_at=expires_at,
        )

    if draft_id == candidate_draft_id:
        draft_store.create_draft(
            draft_id,
            event_memo=raw_payload,
            expires_at=expires_at,
        )
    # draft_id != candidate_draft_id: 既存のidempotency_keyが既にdraft_idを確保済み
    # (フェーズ67 3節手順4)。create_draft()は呼ばず、既存draftに対してCheckout Session
    # のみを新規発行する。

    session = checkout_client.create_session(
        amount=amount,
        currency=currency,
        client_reference_id=draft_id,
        success_url=f"{base_url}/result/{draft_id}",
        cancel_url=f"{base_url}/",
    )

    return CheckoutSessionCreationResult(
        outcome="checkout_session_created",
        draft_id=draft_id,
        draft_id_last4=draft_id[-4:],
        checkout_session_id=session.session_id,
        checkout_url=session.checkout_url,
    )
