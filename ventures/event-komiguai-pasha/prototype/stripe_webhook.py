"""Stripe Webhookの署名検証・受信エントリポイント(stripe-webhook-signature-verification-
design.md フェーズ99)・冪等性チェック(stripe-event-idempotency-design.md フェーズ99)。

one-time-checkout-no-account-design.md(フェーズ10)5節が「stripe-webhook-signature-
verification-design.md相当」「stripe-event-idempotency-design.md相当」という実在しない
ファイル名を前提に書いていた記載を、本モジュールと対応するdesign 2ファイルの新規作成で
実体に置き換える。

本venture(event-komiguai-pasha)は継続課金モデル(aircon-pasha等)と異なり、
`checkout.session.completed`の1種類のみを扱う単発決済モデルのため、`dispatch_stripe_
event()`のような汎用ディスパッチャは導入しない。`one_time_draft/{draft_id}`のステータス
遷移自体が「一度しか進まない」設計(design 2-2節)であることに加え、エントリポイント層の
`event_id_store`による冪等性チェックを多層防御として併設する。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional


class StripeEventIdStoreProtocol:
    """stripe-event-idempotency-design.md 2節: `event.id`単位の処理済み記録を保持する
    ストアのインターフェース。`draft_id`単位の`OneTimeDraftStoreProtocol`とはキーの性質が
    異なるため独立させる(aircon-pasha版と同じ設計判断)。"""

    def has_processed(self, event_id: str) -> bool:
        raise NotImplementedError

    def mark_processed(self, event_id: str) -> None:
        raise NotImplementedError


class InMemoryStripeEventIdStore:
    """design 3節: 検証用のインメモリ実装。プロセス起動ごとに初期化されるため、実Cloud
    Functions環境では呼び出しをまたいで保持されない(既存の各種InMemoryストアと同じ
    既知の限界)。"""

    def __init__(self) -> None:
        self._processed_event_ids: set = set()

    def has_processed(self, event_id: str) -> bool:
        return event_id in self._processed_event_ids

    def mark_processed(self, event_id: str) -> None:
        self._processed_event_ids.add(event_id)


@dataclass
class OneTimeDraft:
    """`one_time_draft/{draft_id}`の最小表現(draft-id-last4-collision-design.mdフェーズ53・
    ttl-expiry-result-delivery-refund-design.mdフェーズ12で確定済みのフィールドのうち、
    本モジュールが読み書きするものだけを保持する)。"""

    draft_id: str
    status: str  # "awaiting_payment" | "generated" | "out_of_scope" |
    #  "insufficient_input" | "generation_failed" | "expired_after_payment"
    expires_at: Optional[datetime] = None
    checkout_session_id: Optional[str] = None
    customer_email: Optional[str] = None


class OneTimeDraftStoreProtocol:
    """`one_time_draft`コレクションへのアクセスを抽象化するインターフェース。"""

    def get(self, draft_id: str) -> Optional[OneTimeDraft]:
        raise NotImplementedError

    def mark_payment_confirmed(
        self, draft_id: str, *, checkout_session_id: str, customer_email: Optional[str]
    ) -> None:
        raise NotImplementedError

    def mark_expired_after_payment(self, draft_id: str) -> None:
        raise NotImplementedError


class InMemoryOneTimeDraftStore:
    """検証用のインメモリ実装(実Firestore接続は実GCPプロジェクト作成後の課題)。"""

    def __init__(self) -> None:
        self._drafts: dict = {}

    def seed(self, draft: OneTimeDraft) -> None:
        self._drafts[draft.draft_id] = draft

    def get(self, draft_id: str) -> Optional[OneTimeDraft]:
        return self._drafts.get(draft_id)

    def mark_payment_confirmed(
        self, draft_id: str, *, checkout_session_id: str, customer_email: Optional[str]
    ) -> None:
        draft = self._drafts.get(draft_id)
        if draft is None:
            return
        draft.checkout_session_id = checkout_session_id
        draft.customer_email = customer_email

    def mark_expired_after_payment(self, draft_id: str) -> None:
        draft = self._drafts.get(draft_id)
        if draft is None:
            return
        draft.status = "expired_after_payment"


def verify_stripe_signature(
    payload: bytes,
    sig_header: Optional[str],
    webhook_secret: str,
    *,
    tolerance_seconds: int = 300,
    now: Optional[float] = None,
) -> bool:
    """`Stripe-Signature`ヘッダを検証する(design 1節のアルゴリズムどおり、aircon-pasha/
    course-set-pasha版と同一の汎用ロジック)。

    - `sig_header`が無い/空文字列、または`t`・`v1`を含まない不正な形式なら`False`。
    - `v1`が複数含まれる場合(シークレットローテーション中)、いずれか1つでも一致すれば
      検証成功とする。`v0`(旧方式)は一切参照しない。
    - 署名が一致してもタイムスタンプが`tolerance_seconds`(デフォルト300秒)の許容範囲外
      なら`False`とする(リプレイ攻撃対策)。
    """
    if not sig_header:
        return False

    timestamp: Optional[str] = None
    v1_signatures: List[str] = []
    for item in sig_header.split(","):
        if "=" not in item:
            continue
        key, _, value = item.partition("=")
        key = key.strip()
        value = value.strip()
        if key == "t":
            timestamp = value
        elif key == "v1":
            v1_signatures.append(value)

    if timestamp is None or not v1_signatures:
        return False

    try:
        timestamp_int = int(timestamp)
    except ValueError:
        return False

    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    expected = hmac.new(
        webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256
    ).hexdigest()

    signature_matches = any(
        hmac.compare_digest(expected, candidate) for candidate in v1_signatures
    )
    if not signature_matches:
        return False

    resolved_now = now if now is not None else time.time()
    if abs(resolved_now - timestamp_int) > tolerance_seconds:
        return False

    return True


@dataclass
class CheckoutCompletionResult:
    """handle_checkout_session_completed()の結果(stripe-webhook-signature-verification-
    design.md 2節)。"""

    draft_id: Optional[str] = None
    # "proceed_to_generation" | "already_processed" | "expired" |
    # "draft_not_found" | "missing_fields"
    outcome: str = "missing_fields"
    customer_email: Optional[str] = None
    checkout_session_id: Optional[str] = None


def handle_checkout_session_completed(
    event: dict,
    store: OneTimeDraftStoreProtocol,
    *,
    now: Optional[datetime] = None,
) -> CheckoutCompletionResult:
    """`checkout.session.completed`イベントから`client_reference_id`(=`draft_id`、
    one-time-checkout-no-account-design.mdフェーズ10 2節で確定済み)を取り出し、対応する
    `one_time_draft`ドキュメントを検証する(design 2節)。

    本venture固有の3段ガード(design 2節):
    1. `draft_id`に対応するドラフトが見つからない場合は`draft_not_found`として区別し、
       何も書き込まない(想定外の順序でCheckout Sessionが作成された場合に、存在しない
       draft_idへ書き込んでデータを汚さないための安全策。aircon-pasha版の
       `user_profile_not_found`と同じ位置づけ)。
    2. ドラフトが既に`awaiting_payment`以外のステータスに遷移済みの場合(2回目以降の
       イベント配信、または既に生成試行済み)は`already_processed`として扱い、生成処理を
       再実行しない(design 2-2節「天然の冪等性ガード」)。
    3. `expires_at`を過ぎている場合は`expired`として扱い、ステータスを
       `expired_after_payment`に更新し生成処理は行わない(ttl-expiry-result-delivery-
       refund-design.mdフェーズ12 1節の防御的チェック。返金フロー自体のトリガーは本関数の
       範囲外、design 5節「残課題」参照)。

    いずれにも該当しなければ`proceed_to_generation`として、`checkout_session_id`・
    `customer_email`をドラフトへ書き込んだ上で返す(実際のLLM生成呼び出しは呼び出し側の
    責務、本関数はWebhook受信口の検証までに限定する)。
    """
    data_object = event.get("data", {}).get("object", {})
    draft_id = data_object.get("client_reference_id")

    if not isinstance(draft_id, str) or not draft_id:
        return CheckoutCompletionResult(outcome="missing_fields")

    draft = store.get(draft_id)
    if draft is None:
        return CheckoutCompletionResult(draft_id=draft_id, outcome="draft_not_found")

    if draft.status != "awaiting_payment":
        return CheckoutCompletionResult(draft_id=draft_id, outcome="already_processed")

    resolved_now = now if now is not None else datetime.now(timezone.utc)
    if draft.expires_at is not None and resolved_now > draft.expires_at:
        store.mark_expired_after_payment(draft_id)
        return CheckoutCompletionResult(draft_id=draft_id, outcome="expired")

    checkout_session_id = data_object.get("id")
    customer_details = data_object.get("customer_details") or {}
    customer_email = customer_details.get("email") or data_object.get("customer_email")

    store.mark_payment_confirmed(
        draft_id,
        checkout_session_id=checkout_session_id
        if isinstance(checkout_session_id, str)
        else None,
        customer_email=customer_email if isinstance(customer_email, str) else None,
    )

    return CheckoutCompletionResult(
        draft_id=draft_id,
        outcome="proceed_to_generation",
        customer_email=customer_email if isinstance(customer_email, str) else None,
        checkout_session_id=checkout_session_id
        if isinstance(checkout_session_id, str)
        else None,
    )


@dataclass
class StripeWebhookReceiverResult:
    """receive_stripe_webhook()の結果。"""

    status_code: int
    checkout_result: Optional[CheckoutCompletionResult] = None
    error: Optional[str] = None
    duplicate: bool = False
    ignored_type: Optional[str] = None


def receive_stripe_webhook(
    body: bytes,
    signature_header: Optional[str],
    webhook_secret: str,
    *,
    draft_store: OneTimeDraftStoreProtocol,
    event_id_store: Optional[StripeEventIdStoreProtocol] = None,
    now: Optional[datetime] = None,
) -> StripeWebhookReceiverResult:
    """Cloud Functionの本体エントリポイント(Stripe版、単発決済モデル)。

    - 署名検証(`verify_stripe_signature()`)に失敗した場合は401相当を返し、以降の配線を
      一切行わない。
    - 署名検証後にbodyをJSONとしてパースする。失敗時・dict以外の場合は400相当を返す。
    - `event_id_store`指定時、パース済みイベントの`id`が既に処理済みであれば
      `handle_checkout_session_completed()`を呼び出さず`duplicate=True`とともに200を
      返す(stripe-event-idempotency-design.md 2節)。`id`が欠落・非文字列の場合は
      チェックをスキップする(安全側)。
    - イベント種別が`checkout.session.completed`の場合のみ`handle_checkout_session_
      completed()`へ振り分ける。それ以外の種別は本venture固有のディスパッチ対象が
      無いため`ignored_type`として200を返す(Stripe側の再送ループを避けるため常に200)。
    """
    resolved_now = now if now is not None else datetime.now(timezone.utc)
    if not verify_stripe_signature(
        body, signature_header, webhook_secret, now=resolved_now.timestamp()
    ):
        return StripeWebhookReceiverResult(status_code=401, error="invalid_signature")

    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return StripeWebhookReceiverResult(status_code=400, error="invalid_json")

    if not isinstance(parsed, dict):
        return StripeWebhookReceiverResult(status_code=400, error="invalid_event")

    event_id = parsed.get("id")
    check_idempotency = event_id_store is not None and isinstance(event_id, str)
    if check_idempotency and event_id_store.has_processed(event_id):
        return StripeWebhookReceiverResult(status_code=200, duplicate=True)

    event_type = parsed.get("type")
    if event_type != "checkout.session.completed":
        if check_idempotency:
            event_id_store.mark_processed(event_id)
        return StripeWebhookReceiverResult(
            status_code=200,
            ignored_type=event_type if isinstance(event_type, str) else None,
        )

    checkout_result = handle_checkout_session_completed(
        parsed, draft_store, now=resolved_now
    )
    if check_idempotency:
        event_id_store.mark_processed(event_id)
    return StripeWebhookReceiverResult(status_code=200, checkout_result=checkout_result)


def _demo() -> None:
    secret = "whsec_demo_secret"
    payload = (
        b'{"id":"evt_demo","type":"checkout.session.completed",'
        b'"data":{"object":{"client_reference_id":"draft_demo",'
        b'"id":"cs_demo","customer_details":{"email":"demo@example.com"}}}}'
    )
    timestamp = int(time.time())
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    header = f"t={timestamp},v1={sig}"
    print("valid signature ->", verify_stripe_signature(payload, header, secret))
    print("missing header ->", verify_stripe_signature(payload, None, secret))


if __name__ == "__main__":
    _demo()
