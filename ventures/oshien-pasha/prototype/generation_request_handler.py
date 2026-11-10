#!/usr/bin/env python3
"""
result-display-page-generation-request-design.md(フェーズ102)2節で設計された基本形
(月額フリーパス`fan_pass`のみを正として扱う暫定版)に、one-time-plan-access-token-design.md
(フェーズ104)4節で設計された都度プラン(`one_time_pass`)側の403(`already_consumed`)・
404(`expiresAt`超過時は`unknown_access_token`と同一に扱う)分岐を統合し、
`receive_generation_request()`を新規実コード化したもの(フェーズ107、フェーズ106次回候補(1)
に対応)。

位置づけ:
- フェーズ102のdesignは「都度プラン対応は次回候補」として月額フリーパスのみの暫定実装に
  留めており、フェーズ104のdesignも「具体的な分岐コード(isinstance相当の判定か、
  PassLookupResultにplan_typeフィールドを持たせるか)は次回以降のプロトタイプ実コード化時に
  確定する」としていた(いずれも未着手)。本モジュールでは、access_tokenを
  `fan_pass_store`→`one_time_pass_store`の順で問い合わせ、最初に見つかったストアの種別で
  分岐する方式を採用した(`CombinedPassLookupProtocol`〈checkout_result_page_handler.py〉は
  Checkout SessionのmodeフィールドというStripe側の情報を前提にしており、本関数は
  access_tokenのみを受け取るため同じ仕組みは使えない)。
- 実LLM呼び出し・実Firestore接続はいずれもオーナー承認待ちの範囲(pending-approval.md参照)
  のため、本モジュールでもProtocol/Callableで差し替え可能にし、検証用の偽実装のみ用意する
  (checkout_result_page_handler.pyと同じ考え方)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from fan_pass_store import FanPass
from one_time_pass_store import OneTimePass


class _FanPassAccessTokenLookupProtocol(Protocol):
    def get_by_access_token(self, access_token: str) -> "FanPass | None": ...


class _OneTimePassAccessTokenLookupProtocol(Protocol):
    def get_by_access_token(self, access_token: str) -> "OneTimePass | None": ...

    def mark_consumed(self, internal_id: str, *, consumed_at: int) -> None: ...


class LlmGenerationClientProtocol(Protocol):
    def generate(self, raw_input: dict) -> dict:
        """schema/output.schema.json形式のレスポンス本体(status分岐込み)を返す。
        本フェーズではProtocolの入出力形だけを確定し、リトライ・エラーハンドリングの詳細は
        llm-quality-verification-plan.md側の既存論点として引き続き未設計のままとする
        (result-display-page-generation-request-design.md 4節)。"""
        ...


class GenerationLogProtocol(Protocol):
    def record(self, internal_id: str) -> None:
        """generation-count-design.md 2節。月額フリーパスのケースのみ呼び出す
        (都度プランは1回使用後に失効するため、月次カウントの対象外)。"""
        ...


@dataclass(frozen=True)
class GenerationHttpResult:
    status_code: int
    output: Optional[dict] = None
    error: Optional[str] = None


def receive_generation_request(
    fan_pass_store: _FanPassAccessTokenLookupProtocol,
    one_time_pass_store: _OneTimePassAccessTokenLookupProtocol,
    generation_log: GenerationLogProtocol,
    llm_client: LlmGenerationClientProtocol,
    access_token: Optional[str],
    raw_input: dict,
    *,
    now: int,
) -> GenerationHttpResult:
    """result-display-page-generation-request-design.md 2節(基本形)・
    one-time-plan-access-token-design.md 4節(都度プランの403/404分岐)を統合した処理順序。

    `now`は`consumedAt`書き込み時刻・`expiresAt`判定基準時刻として呼び出し元が明示的に渡す
    (fan_pass_store.pyの`event_time`引数と同じ、`time.time()`呼び出し自体は本モジュールの
    責務外とする方針を踏襲)。
    """

    if access_token is None or not access_token.strip():
        return GenerationHttpResult(status_code=400, error="missing_access_token")

    fan_pass = fan_pass_store.get_by_access_token(access_token)
    if fan_pass is not None:
        if fan_pass.subscription_status == "canceled":
            return GenerationHttpResult(status_code=403, error="subscription_canceled")

        output = llm_client.generate(raw_input)
        generation_log.record(fan_pass.internal_id)
        return GenerationHttpResult(status_code=200, output=output)

    one_time_pass = one_time_pass_store.get_by_access_token(access_token)
    if one_time_pass is not None:
        # design.md 4節の順序どおり、expiresAt超過はconsumedAtの状態によらず404として扱う
        # (期限切れと「そもそも存在しない」を呼び出し側から区別させないため、consumedAtの
        # 判定より先に判定する)。
        if now >= one_time_pass.expires_at:
            return GenerationHttpResult(status_code=404, error="unknown_access_token")
        if one_time_pass.consumed_at is not None:
            return GenerationHttpResult(status_code=403, error="already_consumed")

        output = llm_client.generate(raw_input)
        # design.md 4節: 「生成成功を確認してから消費済みにする」順序を厳守する
        # (LLM呼び出し成功確認後にのみmark_consumed()を呼ぶ)。
        one_time_pass_store.mark_consumed(one_time_pass.internal_id, consumed_at=now)
        return GenerationHttpResult(status_code=200, output=output)

    return GenerationHttpResult(status_code=404, error="unknown_access_token")
