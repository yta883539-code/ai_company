#!/usr/bin/env python3
"""
ttl-expiry-result-delivery-refund-design.md(フェーズ12)3-2節「決済完了後に生成処理
(LLM API呼び出し)が失敗する場合」の挙動を実装するモジュール。

README.mdフェーズ99時点では、stripe_webhook.handle_checkout_session_completed()が
outcome="proceed_to_generation"を返すところまでは実装済みだったが、そこから実際の
生成呼び出し・リトライ・失敗時の全額自動返金・通知メール送信までを一本につなぐ処理が
欠けていた(フェーズ99「次回候補(2)」)。本モジュールはそのギャップを埋める。

位置づけ:
- `checkout.session.completed`受信により`CheckoutCompletionResult(outcome=
  "proceed_to_generation")`が得られた後の処理を担う。outcome がそれ以外
  (already_processed/expired/draft_not_found/missing_fields)の場合は本モジュールの
  対象外であり、呼び出し側(Cloud Function本体)が別途ハンドリング済みという前提に立つ
  (design 2節のガードを重複実装しない)。
- 実際のLLM呼び出しはmock_llm_client.run_form_submission_pipeline()相当を想定するが、
  本モジュールは特定の生成関数実装に依存しないよう`GenerationFn`として抽象化する
  (他venture同様、呼び出し側が実LLM/モックいずれも差し替え可能にするため)。
- Stripe Refund API・メール送信は、他venture(各種*StoreProtocol)と同じ考え方でProtocol
  として抽象化し、実際のAPIキー・送信手段接続はオーナー承認待ちの範囲のまま、本モジュールは
  机上のオーケストレーションロジックとインメモリ記録用スタブのみを提供する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional, Protocol

# design 3-2節1.「最大2回までリトライする」= 初回呼び出し1回+リトライ2回の計3回まで試行する。
MAX_ATTEMPTS = 3


class GenerationError(Exception):
    """生成処理(LLM呼び出し・机上検証)が失敗したことを表す。一時的なLLM API障害のほか、
    validate_llm_output()の検証エラーも本モジュールの観点では「生成失敗」として同列に
    扱う(いずれの場合も主催者に不完全な出力を返さず、リトライまたは返金に倒すため)。"""


class GenerationFn(Protocol):
    def __call__(self, draft_id: str) -> dict:
        """draft_idに対応する入力から構造化出力(dict)を生成して返す。失敗時は
        GenerationErrorを送出する契約(呼び出し側が通常の例外をGenerationErrorへ
        変換する想定、design上は一時的なLLM API障害を主因として想定)。"""
        ...


class RefundClientProtocol(Protocol):
    def create_refund(self, payment_intent_id: str) -> dict:
        """Stripe Refund API(`refunds.create`)相当。design 5節残課題(返金可能期間
        〈通常180日〉超過等)でStripe側がエラーを返す場合は例外を送出する契約とする。"""
        ...


class EmailSenderProtocol(Protocol):
    def send(self, *, to: str, template_key: str, **template_vars: str) -> None:
        """operational_message_templates.TEMPLATESのキーとプレースホルダ変数を渡して
        送信する(実際の送信手段接続はオーナー承認待ちの範囲、design 2節参照)。"""
        ...


class InMemoryRefundClient:
    """検証用のインメモリ実装。呼び出し引数を記録し、テストから検証できるようにする。"""

    def __init__(self) -> None:
        self.calls: List[str] = []

    def create_refund(self, payment_intent_id: str) -> dict:
        self.calls.append(payment_intent_id)
        return {"id": f"re_demo_{payment_intent_id}", "status": "succeeded"}


class InMemoryEmailSender:
    """検証用のインメモリ実装。送信内容を記録するだけで実際の送信は行わない。"""

    def __init__(self) -> None:
        self.sent: List[dict] = []

    def send(self, *, to: str, template_key: str, **template_vars: str) -> None:
        self.sent.append({"to": to, "template_key": template_key, **template_vars})


@dataclass
class GenerationOutcome:
    """process_generation_after_payment()の結果。README・design文書の記述と揃えるため、
    outcomeは日本語の設計文書中の表現にできるだけ対応させた英語の識別子とする。"""

    # "not_applicable" | "generated" | "refunded" | "refund_failed"
    outcome: str
    attempts: int = 0
    output: Optional[dict] = None
    refund_response: Optional[dict] = None
    warnings: List[str] = field(default_factory=list)


def process_generation_after_payment(
    checkout_result,
    generate_fn: GenerationFn,
    draft_store,
    refund_client: RefundClientProtocol,
    email_sender: EmailSenderProtocol,
    *,
    retry_url: str = "",
    max_attempts: int = MAX_ATTEMPTS,
) -> GenerationOutcome:
    """design 3-2節の処理フロー本体。

    1. draft_idに対するgenerate_fn()を、成功するか`max_attempts`回(既定3回=初回+
       リトライ2回)試行し尽くすまで呼び出す。
    2. 成功した場合、出力のstatus(generated/out_of_scope/insufficient_input)で
       draft_store.mark_generation_result()を呼び、outcome="generated"を返す
       (この時点ではメール送信・返金は行わない。結果到達〈completion_email〉は
       2節の責務であり本モジュールの対象外)。
    3. `max_attempts`回とも失敗した場合、draft_store.mark_generation_result()で
       まず"generation_failed"に更新し、payment_intent_idが取得できていれば
       refund_client.create_refund()を呼ぶ。成功すれば"refunded"に更新し、
       customer_emailが取得できていれば"generation_failed_refund_email"
       テンプレートで通知する。
    4. payment_intent_idが欠落している場合(想定外の入力)は返金を試みず、警告を
       記録してoutcome="refunded"ではなく"refund_failed"として返す(design上は
       発生しない想定だが、防御的に扱う)。
    5. refund_client.create_refund()自体が例外を送出した場合(design 5節残課題、
       Stripe側の返金可能期間超過等)、draft_storeの状態は"generation_failed"の
       ままとし、outcome="refund_failed"・warningsに例外メッセージを記録して返す
       (inquiry-handling-design.mdフェーズ15の個別対応フローへ引き継ぐ想定、本
       モジュールはクラッシュさせずに呼び出し側へ状況を返すところまでが責務)。
    """
    if checkout_result.outcome != "proceed_to_generation":
        return GenerationOutcome(
            outcome="not_applicable",
            warnings=[
                f"outcome={checkout_result.outcome!r}はproceed_to_generation以外のため、"
                "本モジュールの対象外(呼び出し側で別途ハンドリング済みの前提)"
            ],
        )

    draft_id = checkout_result.draft_id
    attempts = 0
    last_error: Optional[Exception] = None

    while attempts < max_attempts:
        attempts += 1
        try:
            output = generate_fn(draft_id)
        except GenerationError as exc:
            last_error = exc
            continue
        draft_store.mark_generation_result(draft_id, status=output.get("status", "generated"))
        return GenerationOutcome(outcome="generated", attempts=attempts, output=output)

    # ここに到達するのはmax_attempts回すべて失敗した場合のみ。
    draft_store.mark_generation_result(draft_id, status="generation_failed")
    warnings: List[str] = []
    if last_error is not None:
        warnings.append(f"{max_attempts}回の試行すべてが失敗: {last_error}")

    payment_intent_id = checkout_result.payment_intent_id
    if not payment_intent_id:
        warnings.append(
            "payment_intent_idが未取得のため返金処理を実行できません"
            "(想定外。オーナーへの個別対応が必要、inquiry-handling-design.md参照)"
        )
        return GenerationOutcome(
            outcome="refund_failed", attempts=attempts, warnings=warnings
        )

    try:
        refund_response = refund_client.create_refund(payment_intent_id)
    except Exception as exc:  # noqa: BLE001 - design 5節: Stripe側エラーを握りつぶさず返す
        warnings.append(f"返金API呼び出しが失敗しました: {exc}")
        return GenerationOutcome(
            outcome="refund_failed", attempts=attempts, warnings=warnings
        )

    draft_store.mark_generation_result(draft_id, status="refunded")

    customer_email = checkout_result.customer_email
    if customer_email:
        email_sender.send(
            to=customer_email,
            template_key="generation_failed_refund_email",
            retry_url=retry_url,
        )
    else:
        warnings.append(
            "customer_emailが未取得のため返金完了メールを送信できませんでした"
        )

    return GenerationOutcome(
        outcome="refunded",
        attempts=attempts,
        refund_response=refund_response,
        warnings=warnings,
    )
