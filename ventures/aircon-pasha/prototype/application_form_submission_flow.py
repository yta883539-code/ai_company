#!/usr/bin/env python3
"""
user-account-linking-design.md 2節で設計した「申込フォーム送信完了時にCloud Function側
(GAS Webhook経由)が連携コードを発行する」処理を実行可能なコードに落とし込んだもの。

位置づけ:
- 実際のGoogleフォーム作成・GAS Webhookデプロイ・実Firestore接続はいずれも「外部サービスへの
  公開」「アカウント作成」に該当し、オーナー承認待ち(pending-approval.md参照)。本モジュールは
  それとは別に、GAS Webhookから届く想定のペイロードをどう検証し、
  `issue_linking_code_on_form_submission()`(prototype/user_id_linking.py)へどう委譲するかという
  処理ロジック自体を実クラウド接続なしで検証可能にしたもの
  (course-set-pasha/prototype/application_form_submission_flow.pyと同じ位置づけ)。
- user_id_linking.pyの`issue_linking_code_on_form_submission()`は定義済み・単体テスト済み
  だったが、それを実際に呼び出す「GAS Webhookエントリポイント」側の処理自体が
  一度も実装されていなかった(kura-pashaフェーズ192で発見された
  `resolve_checkout_intent()`/`resolve_workshop_invite_request()`の非対称な抜けと同種の、
  「発行契機の意図検知はあるが実際の発行呼び出しが無い」パターン)。本モジュールでこの抜けを
  解消する。

設計の参照元: user-account-linking-design.md 2節・5節
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from user_id_linking import (
    LinkingCodeStoreProtocol,
    RandomChoiceSource,
    issue_linking_code_on_form_submission,
)

# design 5節: pending_linksドキュメントの必須フィールド(いずれも空文字列・欠落はエラー)。
_REQUIRED_STRING_FIELDS = ("form_submission_id", "business_name", "business_type", "email")


@dataclass
class FormSubmissionResult:
    """`handle_form_submission()`の結果。design 2節のエントリポイントの戻り値。

    `linking_code`は呼び出し側(サンクスページ表示・確認メール本文への埋め込み、
    design 2節)がそのまま使う想定だが、実フォーム・実メール送信はいずれもオーナー承認待ちの
    ため、本モジュールはコード文字列を返すところまでに留める。
    """

    ok: bool
    linking_code: Optional[str] = None
    error: Optional[str] = None


def handle_form_submission(
    payload: dict,
    store: LinkingCodeStoreProtocol,
    now: datetime,
    rng: RandomChoiceSource,
) -> FormSubmissionResult:
    """design 2節・5節に沿って、GAS Webhookペイロードを検証し、
    `issue_linking_code_on_form_submission()`へ委譲して連携コードを発行する。

    想定ペイロード: {"form_submission_id": "...", "business_name": "...",
                     "business_type": "...", "email": "..."}
    いずれも`pending_links`ドキュメントの必須フィールド(design 5節)であり、
    欠落・非文字列・空文字列はエラーとする(course-set-pashaのemail必須チェックと同じ方針を
    4フィールド全てに適用する)。
    """
    values: dict[str, str] = {}
    for field in _REQUIRED_STRING_FIELDS:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            return FormSubmissionResult(
                ok=False, error=f"{field} is missing or not a non-empty string"
            )
        values[field] = value.strip()

    linking_code = issue_linking_code_on_form_submission(
        form_submission_id=values["form_submission_id"],
        business_name=values["business_name"],
        business_type=values["business_type"],
        email=values["email"],
        store=store,
        now=now,
        rng=rng,
    )

    return FormSubmissionResult(ok=True, linking_code=linking_code)
