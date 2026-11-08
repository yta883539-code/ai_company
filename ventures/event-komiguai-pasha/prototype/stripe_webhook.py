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

from generation_retry_and_refund import (
    EmailSenderProtocol,
    GenerationFn,
    GenerationOutcome,
    RefundClientProtocol,
    process_generation_after_payment,
)


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
    #  "insufficient_input" | "generation_failed" | "refunded" | "expired_after_payment"
    expires_at: Optional[datetime] = None
    checkout_session_id: Optional[str] = None
    customer_email: Optional[str] = None
    payment_intent_id: Optional[str] = None
    # ttl-expiry-result-delivery-refund-design.mdフェーズ12 3-2節のStripe Refund API
    # (`refunds.create`)の対象キー。checkout_session_idとは別物(Refund APIは
    # payment_intentを対象にする)のため、独立したフィールドとして保持する。
    event_memo: Optional[dict] = None
    # draft-creation-and-event-memo-storage-design.md(フェーズ102)。Webフォーム送信時に
    # 主催者が入力した5要素の生dict(form_submission_intake.EventMemoInputのraw_payload
    # 相当)。Checkout Session作成前のcreate_draft()呼び出し時点で保存し、決済完了後の
    # generate_fn(draft_id)がLLMへ渡す入力を取り出すために参照する(draft_generation_fn.py
    # 参照)。
    draft_id_last4: Optional[str] = None
    # draft-id-last4-collision-design.md(フェーズ53・58)4節。draft_idの末尾4文字を
    # そのまま複製したオーナー検索専用フィールド。一意キーではなく絞り込みのヒントに
    # 過ぎない(衝突時はcustomer_emailとの二段階照合、design 4節参照)。


class OneTimeDraftStoreProtocol:
    """`one_time_draft`コレクションへのアクセスを抽象化するインターフェース。"""

    def create_draft(
        self,
        draft_id: str,
        *,
        event_memo: dict,
        expires_at: Optional[datetime] = None,
        status: str = "awaiting_payment",
    ) -> None:
        """draft-creation-and-event-memo-storage-design.md(フェーズ102)。Webフォーム
        送信でform_submission_intake.handle_form_submission()がLLMリクエストペイロードを
        返した(必須項目充足・insufficient_input応答ではない)場合に、Checkout Session
        作成(`client_reference_id=draft_id`)の直前に1回だけ呼ばれる想定。"""
        raise NotImplementedError

    def get(self, draft_id: str) -> Optional[OneTimeDraft]:
        raise NotImplementedError

    def mark_payment_confirmed(
        self,
        draft_id: str,
        *,
        checkout_session_id: str,
        customer_email: Optional[str],
        payment_intent_id: Optional[str] = None,
    ) -> None:
        raise NotImplementedError

    def mark_expired_after_payment(self, draft_id: str) -> None:
        raise NotImplementedError

    def mark_generation_result(self, draft_id: str, *, status: str) -> None:
        """generation_retry_and_refund.pyが、生成成功時(status=LLM出力のstatus)・
        2回のリトライを尽くしても失敗した場合(status="generation_failed")・返金完了後
        (status="refunded")のいずれでもドラフトのステータスを更新するために使う、
        汎用のステータス書き込み口。"""
        raise NotImplementedError


class InMemoryOneTimeDraftStore:
    """検証用のインメモリ実装(実Firestore接続は実GCPプロジェクト作成後の課題)。"""

    def __init__(self) -> None:
        self._drafts: dict = {}

    def seed(self, draft: OneTimeDraft) -> None:
        self._drafts[draft.draft_id] = draft

    def create_draft(
        self,
        draft_id: str,
        *,
        event_memo: dict,
        expires_at: Optional[datetime] = None,
        status: str = "awaiting_payment",
    ) -> None:
        self._drafts[draft_id] = OneTimeDraft(
            draft_id=draft_id,
            status=status,
            expires_at=expires_at,
            event_memo=event_memo,
            draft_id_last4=draft_id[-4:] if draft_id else None,
        )

    def get(self, draft_id: str) -> Optional[OneTimeDraft]:
        return self._drafts.get(draft_id)

    def mark_payment_confirmed(
        self,
        draft_id: str,
        *,
        checkout_session_id: str,
        customer_email: Optional[str],
        payment_intent_id: Optional[str] = None,
    ) -> None:
        draft = self._drafts.get(draft_id)
        if draft is None:
            return
        draft.checkout_session_id = checkout_session_id
        draft.customer_email = customer_email
        draft.payment_intent_id = payment_intent_id

    def mark_expired_after_payment(self, draft_id: str) -> None:
        draft = self._drafts.get(draft_id)
        if draft is None:
            return
        draft.status = "expired_after_payment"

    def mark_generation_result(self, draft_id: str, *, status: str) -> None:
        draft = self._drafts.get(draft_id)
        if draft is None:
            return
        draft.status = status


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
    payment_intent_id: Optional[str] = None


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
    # `payment_intent`はmode="payment"のCheckout Session完了イベントに含まれる文字列ID。
    # ttl-expiry-result-delivery-refund-design.mdフェーズ12 3-2節の返金フローが対象にする
    # キーのため、checkout_session_idとは別に取り出しておく(本関数は返金自体は行わない、
    # 呼び出し側〈generation_retry_and_refund.py〉の責務)。
    payment_intent = data_object.get("payment_intent")

    resolved_checkout_session_id = (
        checkout_session_id if isinstance(checkout_session_id, str) else None
    )
    resolved_customer_email = (
        customer_email if isinstance(customer_email, str) else None
    )
    resolved_payment_intent_id = payment_intent if isinstance(payment_intent, str) else None

    store.mark_payment_confirmed(
        draft_id,
        checkout_session_id=resolved_checkout_session_id,
        customer_email=resolved_customer_email,
        payment_intent_id=resolved_payment_intent_id,
    )

    return CheckoutCompletionResult(
        draft_id=draft_id,
        outcome="proceed_to_generation",
        customer_email=resolved_customer_email,
        checkout_session_id=resolved_checkout_session_id,
        payment_intent_id=resolved_payment_intent_id,
    )


@dataclass
class StripeWebhookReceiverResult:
    """receive_stripe_webhook()の結果。"""

    status_code: int
    checkout_result: Optional[CheckoutCompletionResult] = None
    error: Optional[str] = None
    duplicate: bool = False
    ignored_type: Optional[str] = None
    # outcome="proceed_to_generation"かつgenerate_fn等が呼び出し側から渡された場合のみ
    # 設定される(generation_retry_and_refund.process_generation_after_payment()の結果)。
    # generate_fn省略時(フェーズ99までの既存呼び出し側)やoutcomeがproceed_to_generation
    # 以外の場合はNoneのまま(後方互換、design フェーズ100「次回候補(2)」参照)。
    generation_outcome: Optional[GenerationOutcome] = None


def receive_stripe_webhook(
    body: bytes,
    signature_header: Optional[str],
    webhook_secret: str,
    *,
    draft_store: OneTimeDraftStoreProtocol,
    event_id_store: Optional[StripeEventIdStoreProtocol] = None,
    now: Optional[datetime] = None,
    generate_fn: Optional[GenerationFn] = None,
    refund_client: Optional[RefundClientProtocol] = None,
    email_sender: Optional[EmailSenderProtocol] = None,
    retry_url: str = "",
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
    - `handle_checkout_session_completed()`がoutcome="proceed_to_generation"を
      返し、かつ`generate_fn`・`refund_client`・`email_sender`の3つ全てが
      呼び出し側から渡されている場合のみ、`generation_retry_and_refund.
      process_generation_after_payment()`へ結線し、生成リトライ・失敗時の自動返金まで
      同期的に実行する(design フェーズ100「次回候補(2)」)。3つのうち1つでも欠けている
      場合は結線せず`generation_outcome=None`のまま返す(フェーズ99までの既存呼び出し側・
      生成処理を非同期キュー等に委ねたい将来の呼び出し側との後方互換を優先するための
      意図的な分岐、3つの一部だけを渡すことを禁止するものではない機能フラグ的な設計)。
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

    generation_outcome: Optional[GenerationOutcome] = None
    if (
        checkout_result.outcome == "proceed_to_generation"
        and generate_fn is not None
        and refund_client is not None
        and email_sender is not None
    ):
        generation_outcome = process_generation_after_payment(
            checkout_result,
            generate_fn,
            draft_store,
            refund_client,
            email_sender,
            retry_url=retry_url,
        )

    return StripeWebhookReceiverResult(
        status_code=200,
        checkout_result=checkout_result,
        generation_outcome=generation_outcome,
    )


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
