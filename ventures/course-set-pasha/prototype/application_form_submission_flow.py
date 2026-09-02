#!/usr/bin/env python3
"""
application-form-submission-flow-design.mdで設計した、申込フォーム提出時の
`user_profile/{user_id}.gym_area_pairs`書き込みフローを実行可能なコードに落とし込んだもの。

位置づけ:
- 実際のGoogleフォーム作成・Google Apps Script(GAS)配置、実Firestore接続は
  「外部サービスへの実設定」「アカウント作成」に該当し、引き続きオーナー承認待ち
  (pending-approval.md参照)。本モジュールはそれとは別に、GAS Webhookから届く想定の
  ペイロードをどう検証・正規化し、どう`user_profile`ドキュメントへ書き込むかという
  処理ロジック自体を実クラウド接続なしで検証可能にしたもの
  (cloud_function_webhook.pyと同じ位置づけ)。
- `GymAreaConfigStoreProtocol`(cloud_function_webhook.py、読み取り専用)とは責務が異なる
  別モジュールとし、Webhook本体(生成フロー)への依存を増やさない。

設計の参照元: application-form-submission-flow-design.md
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional, Protocol


class UserProfileStoreProtocol(Protocol):
    """`user_profile/{user_id}`ドキュメントの`gym_area_pairs`フィールドへの読み書きを表す
    (application-form-submission-flow-design.md 4節)。書き込みは全体上書き
    (追記ではない、3節)。

    `set_stripe_customer_id`/`get_user_id_by_stripe_customer_id`は
    stripe-customer-id-linking-design.md(フェーズ97)で追加した、`stripe_customer_id`
    (StripeカスタマーオブジェクトのID)と`user_id`の相互紐付けを表す。Stripe Webhookの
    `resolve_user_id(stripe_customer_id) -> user_id`変換をこの逆引きで実現する。

    `get_stripe_customer_id`(順引き)は checkout-initiation-flow-design.md(フェーズ98)で
    追加した。Checkout Session作成時に、既存のStripe顧客(過去に決済経験がある解約・再契約
    ユーザー等)を再利用するかどうかの判定に使う。

    `set_email`/`get_email`はcontact-email-field-design.md(フェーズ139)で追加した。
    申込フォームで収集する連絡先メールアドレス(onboarding-guide.md 1.)を
    `user_profile/{user_id}.email`として保持する。

    `set_is_following`/`get_is_following`/`all_user_ids`はblocked-but-billing-detection-
    design.mdで追加した。`user_profile/{user_id}.is_following`(LINE公式アカウントを
    フォロー中かどうか、aircon-pashaの`UserProfile.is_following`と同じ考え方)を保持する。
    未記録のuser_id(followイベントを一度も受けていない等)は`True`(フォロー中)として
    扱う(aircon-pashaの`is_following: bool = True`のデフォルトと同じ安全側の初期値)。
    """

    def set_gym_area_pairs(self, user_id: str, raw_value: str) -> None:
        ...

    def get_gym_area_pairs(self, user_id: str) -> str:
        ...

    def set_email(self, user_id: str, email: str) -> None:
        ...

    def get_email(self, user_id: str) -> Optional[str]:
        ...

    def set_stripe_customer_id(self, user_id: str, stripe_customer_id: str) -> None:
        ...

    def get_stripe_customer_id(self, user_id: str) -> Optional[str]:
        ...

    def get_user_id_by_stripe_customer_id(
        self, stripe_customer_id: str
    ) -> Optional[str]:
        ...

    def set_is_following(self, user_id: str, is_following: bool) -> None:
        ...

    def get_is_following(self, user_id: str) -> bool:
        ...

    def all_user_ids(self) -> Iterable[str]:
        ...


class InMemoryUserProfileStore:
    """実Firestore接続の代わりにdictで`user_profile`ドキュメントを保持する検証用スタブ。
    `is_configured()`は`GymAreaConfigStoreProtocol`(cloud_function_webhook.py)互換の
    読み取り専用メソッドとして提供し、`gym_area_pairs`が非空かどうかで判定する
    (design 4節: 実Firestore接続後は単一のFirestoreUserProfileStoreが両Protocolを
    満たす設計を見越したスタブ)。

    `stripe_customer_id`は`user_id → stripe_customer_id`の順引き辞書と別に
    `stripe_customer_id → user_id`の逆引き辞書も保持する(フェーズ97、
    stripe-customer-id-linking-design.md 2節。実Firestoreでは
    `user_profile`コレクションへの単一フィールド書き込み+別コレクション
    `stripe_customer_index/{stripe_customer_id}`への逆引きドキュメント書き込みに
    対応する想定)。
    """

    def __init__(self) -> None:
        self._profiles: dict[str, str] = {}
        self._emails: dict[str, str] = {}
        self._stripe_customer_ids: dict[str, str] = {}
        self._user_ids_by_stripe_customer_id: dict[str, str] = {}
        self._is_following: dict[str, bool] = {}

    def set_gym_area_pairs(self, user_id: str, raw_value: str) -> None:
        self._profiles[user_id] = raw_value

    def get_gym_area_pairs(self, user_id: str) -> str:
        return self._profiles.get(user_id, "")

    def set_email(self, user_id: str, email: str) -> None:
        self._emails[user_id] = email

    def get_email(self, user_id: str) -> Optional[str]:
        return self._emails.get(user_id)

    def is_configured(self, user_id: str) -> bool:
        return bool(self._profiles.get(user_id, ""))

    def set_stripe_customer_id(self, user_id: str, stripe_customer_id: str) -> None:
        self._stripe_customer_ids[user_id] = stripe_customer_id
        self._user_ids_by_stripe_customer_id[stripe_customer_id] = user_id

    def get_stripe_customer_id(self, user_id: str) -> Optional[str]:
        return self._stripe_customer_ids.get(user_id)

    def get_user_id_by_stripe_customer_id(
        self, stripe_customer_id: str
    ) -> Optional[str]:
        return self._user_ids_by_stripe_customer_id.get(stripe_customer_id)

    def set_is_following(self, user_id: str, is_following: bool) -> None:
        self._is_following[user_id] = is_following

    def get_is_following(self, user_id: str) -> bool:
        return self._is_following.get(user_id, True)

    def all_user_ids(self) -> Iterable[str]:
        # design: is_following/gym_area_pairs/stripe_customer_idいずれかの記録がある
        # user_idを漏れなく列挙する(blocked_but_billing_candidates.list_...()の走査対象)。
        return sorted(
            set(self._profiles)
            | set(self._emails)
            | set(self._stripe_customer_ids)
            | set(self._is_following)
        )


# design 2節: 連続カンマのみ等、要素がすべて空になる入力を「実質空」とみなすための判定に使う。
_EMPTY_ELEMENT_PATTERN = re.compile(r"^\s*$")


def normalize_gym_area_pairs_raw(raw_value: Optional[str]) -> str:
    """application-form-submission-flow-design.md 2節の正規化ルールを実装する。

    - 前後の空白除去。
    - カンマ区切りの各要素も前後の空白を除去した上で、カンマ区切りの1つの文字列として
      再結合する(構造化データへの分解はしない。llm-system-prompt-draft.mdがこの文字列を
      そのままLLMシステムプロンプトへ渡す設計のため)。
    - 全要素が空(例: 空文字列・空白のみ・`,,,`のみ)の場合は空文字列に落とし込む。
    """
    if raw_value is None:
        return ""

    elements = [element.strip() for element in raw_value.split(",")]
    non_empty_elements = [
        element for element in elements if not _EMPTY_ELEMENT_PATTERN.match(element)
    ]
    return ", ".join(non_empty_elements)


@dataclass
class FormSubmissionResult:
    """`handle_form_submission()`の結果。design 4節のエントリポイントの戻り値。"""

    ok: bool
    user_id: Optional[str] = None
    normalized_gym_area_pairs: Optional[str] = None
    email: Optional[str] = None
    error: Optional[str] = None


def handle_form_submission(
    payload: dict,
    store: UserProfileStoreProtocol,
) -> FormSubmissionResult:
    """design 2節・3節・4節に沿って、GAS Webhookペイロードを検証・正規化し、
    `user_profile/{user_id}.gym_area_pairs`・`user_profile/{user_id}.email`へ書き込む
    (gym_area_pairsは全体上書き、emailも同様に最新提出内容で上書きする)。

    想定ペイロード: {"user_id": "...", "gym_area_pairs_raw": "...", "email": "..."}
    `email`はonboarding-guide.md 1.の通り申込フォームの必須項目(contact-email-field-design.md
    フェーズ139)であり、`gym_area_pairs_raw`と異なり欠落・空文字列はエラーとする。
    """
    user_id = payload.get("user_id")
    if not isinstance(user_id, str) or not user_id.strip():
        return FormSubmissionResult(
            ok=False, error="user_id is missing or not a non-empty string"
        )

    email = payload.get("email")
    if not isinstance(email, str) or not email.strip():
        return FormSubmissionResult(
            ok=False, error="email is missing or not a non-empty string"
        )

    raw_value = payload.get("gym_area_pairs_raw", "")
    if raw_value is not None and not isinstance(raw_value, str):
        return FormSubmissionResult(
            ok=False, error="gym_area_pairs_raw must be a string or absent"
        )

    normalized_email = email.strip()
    normalized = normalize_gym_area_pairs_raw(raw_value)
    store.set_gym_area_pairs(user_id, normalized)
    store.set_email(user_id, normalized_email)

    return FormSubmissionResult(
        ok=True,
        user_id=user_id,
        normalized_gym_area_pairs=normalized,
        email=normalized_email,
    )
