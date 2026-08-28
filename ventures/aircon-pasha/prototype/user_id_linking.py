#!/usr/bin/env python3
"""
user-account-linking-design.mdで設計した「申込フォーム送信完了時に発行された連携コードを、
LINE友だち追加後の最初のトークで受信し、user_idへ解決してuser_profileを新規作成する」フローを
実行可能なコードに落とし込んだもの。

位置づけ:
- 本ventureはcourse-set-pasha(line-user-id-linking-design.md)と紐付けの向きが逆
  (design 1節: 本ventureは「フォーム送信 → LINE友だち追加」の順序)。連携コードは
  フォーム送信完了時点(まだuser_idは判明していない)で発行され`pending_links/{code}`へ
  保存される。LINE側で連携コードを受信して初めてuser_idが判明するため、本モジュールの
  `resolve_linking_code()`はcourse-set-pasha版(`code → user_id`を返すだけ)と異なり、
  `code + user_id`を受け取ってuser_profileそのものを確定させる。
- 実際のGoogleフォーム作成・GAS Webhookデプロイ・LINE公式アカウント接続・実Firestore接続は
  いずれも「アカウント作成」「外部サービスへの公開」に該当し、オーナー承認待ち
  (pending-approval.md参照)。本モジュールはコード発行・解決ロジック自体を実接続なしで
  検証可能にしたもの(course-set-pasha/prototype/user_id_linking.pyと同じ位置づけ)。

設計の参照元: user-account-linking-design.md 2〜3節・5節
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional, Protocol, Tuple

# design 2節: course-set-pashaのline-user-id-linking-design.md「3. コード仕様」と同じ
# 文字種・視認性除外ルール(0/O、1/I/Lを除く)を採用。
_CODE_ALPHABET = "".join(
    c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" if c not in "0O1IL"
)
_CODE_LENGTH = 6
_LINK_TTL = timedelta(hours=24)
_MAX_GENERATION_ATTEMPTS = 5


@dataclass
class PendingLink:
    """`pending_links/{code}`ドキュメント1件(design 5節)。"""

    form_submission_id: str
    business_name: str
    business_type: str
    email: str
    issued_at: datetime


class LinkingCodeStoreProtocol(Protocol):
    """`pending_links/{code}`ドキュメントへの読み書きを表す(design 5節)。"""

    def save(self, code: str, entry: PendingLink) -> None:
        ...

    def get(self, code: str) -> Optional[PendingLink]:
        ...

    def delete(self, code: str) -> None:
        ...

    def items(self) -> Iterable[Tuple[str, PendingLink]]:
        """全エントリを`(code, entry)`で列挙する(期限切れパージのため)。"""
        ...


class InMemoryLinkingCodeStore:
    """実Firestore接続の代わりにdictで`pending_links`ドキュメントを保持する検証用スタブ。"""

    def __init__(self) -> None:
        self._entries: dict[str, PendingLink] = {}

    def save(self, code: str, entry: PendingLink) -> None:
        self._entries[code] = entry

    def get(self, code: str) -> Optional[PendingLink]:
        return self._entries.get(code)

    def delete(self, code: str) -> None:
        self._entries.pop(code, None)

    def items(self) -> Iterable[Tuple[str, PendingLink]]:
        # スナップショットを返す(パージ中の削除でイテレータが壊れないようにする)。
        return list(self._entries.items())


class RandomChoiceSource(Protocol):
    """`random.Random`と同じ`choice()`インターフェースを想定(テストで決定的な値を注入するため)。"""

    def choice(self, seq):
        ...


def _generate_candidate_code(rng: RandomChoiceSource) -> str:
    return "".join(rng.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


def issue_linking_code_on_form_submission(
    form_submission_id: str,
    business_name: str,
    business_type: str,
    email: str,
    store: LinkingCodeStoreProtocol,
    now: datetime,
    rng: RandomChoiceSource,
) -> str:
    """design 2節: 申込フォーム送信完了時(GAS Webhook側)に呼ばれる想定。重複しないコードを
    発行・保存し、コード文字列を返す(呼び出し側がサンクスページ表示・確認メール本文へ
    埋め込む想定だが、実フォーム・実メール送信はいずれもオーナー承認待り)。
    """
    for _ in range(_MAX_GENERATION_ATTEMPTS):
        code = _generate_candidate_code(rng)
        if store.get(code) is None:
            store.save(
                code,
                PendingLink(
                    form_submission_id=form_submission_id,
                    business_name=business_name,
                    business_type=business_type,
                    email=email,
                    issued_at=now,
                ),
            )
            return code
    raise RuntimeError(
        f"linking code generation collided {_MAX_GENERATION_ATTEMPTS} times in a row"
    )


@dataclass
class UserProfile:
    """`user_profile/{user_id}`ドキュメント(design 5節)。

    `trial_start_at`・`trial_end_notified_at`・`upgraded_at`は
    trial-end-notification-design.md 5節・trial-end-scheduler-design.md(フェーズ133)で
    予告されていた3フィールド(フェーズ134で追加)。course-set-pashaの
    `InMemoryUsageCounter`/`user_profile`設計と同じ位置づけで、いずれも一度設定されたら
    以降不変(`trial_start_at`は初回生成成功時、`trial_end_notified_at`は
    トライアル終了通知送信時、`upgraded_at`は有料転換時にそれぞれ1回だけ書き込む)。"""

    business_name: str
    business_type: str
    email: str
    linked_at: datetime
    stripe_customer_id: Optional[str] = None
    current_plan_id: Optional[str] = None
    trial_start_at: Optional[datetime] = None
    trial_end_notified_at: Optional[datetime] = None
    upgraded_at: Optional[datetime] = None


class UserProfileStoreProtocol(Protocol):
    """`user_profile/{user_id}`ドキュメントへの読み書きを表す(design 5節)。

    `set_stripe_customer_id`/`get_user_id_by_stripe_customer_id`は
    checkout-session-completed-handling-design.mdで追加した、`stripe_customer_id`
    (StripeカスタマーオブジェクトのID)と`user_id`の紐付けを表す。本ventureは
    `client_reference_id`に既知の`user_id`をそのまま設定できる(design 4節)ため
    `set_stripe_customer_id`は書き込み専用(順引きの`get_stripe_customer_id`は
    現時点でどこからも呼ばれないため未追加)、`get_user_id_by_stripe_customer_id`は
    `customer.subscription.*`系イベントの`resolve_user_id(stripe_customer_id) -> user_id`
    変換をこの逆引きで実現するために使う(course-set-pashaの
    `get_user_id_by_stripe_customer_id`と同じ位置づけ)。

    `set_trial_start_at`/`set_trial_end_notified_at`/`set_upgraded_at`は
    trial-end-scheduler-design.md(フェーズ133)向けにフェーズ134で追加した3フィールドの
    書き込み専用メソッド(いずれも未知の`user_id`に対しては何もしない、
    `set_stripe_customer_id`と同じno-op方針)。"""

    def save(self, user_id: str, profile: UserProfile) -> None:
        ...

    def get(self, user_id: str) -> Optional[UserProfile]:
        ...

    def exists(self, user_id: str) -> bool:
        ...

    def set_stripe_customer_id(self, user_id: str, stripe_customer_id: str) -> None:
        ...

    def get_user_id_by_stripe_customer_id(
        self, stripe_customer_id: str
    ) -> Optional[str]:
        ...

    def set_trial_start_at(self, user_id: str, at: datetime) -> None:
        ...

    def set_trial_end_notified_at(self, user_id: str, notified_at: datetime) -> None:
        ...

    def set_upgraded_at(self, user_id: str, at: datetime) -> None:
        ...


class InMemoryUserProfileStore:
    """実Firestore接続の代わりにdictで`user_profile`ドキュメントを保持する検証用スタブ。

    `stripe_customer_id → user_id`の逆引き用に別辞書も保持する(実Firestoreでは
    `user_profile`コレクションへの単一フィールド書き込み+別コレクション
    `stripe_customer_index/{stripe_customer_id}`への逆引きドキュメント書き込みに
    対応する想定、course-set-pashaの`InMemoryUserProfileStore`と同じ設計)。"""

    def __init__(self) -> None:
        self._profiles: dict[str, UserProfile] = {}
        self._user_ids_by_stripe_customer_id: dict[str, str] = {}

    def save(self, user_id: str, profile: UserProfile) -> None:
        self._profiles[user_id] = profile

    def get(self, user_id: str) -> Optional[UserProfile]:
        return self._profiles.get(user_id)

    def exists(self, user_id: str) -> bool:
        return user_id in self._profiles

    def set_stripe_customer_id(self, user_id: str, stripe_customer_id: str) -> None:
        profile = self._profiles.get(user_id)
        if profile is None:
            return
        old_stripe_customer_id = profile.stripe_customer_id
        if old_stripe_customer_id is not None:
            self._user_ids_by_stripe_customer_id.pop(old_stripe_customer_id, None)
        profile.stripe_customer_id = stripe_customer_id
        self._user_ids_by_stripe_customer_id[stripe_customer_id] = user_id

    def get_user_id_by_stripe_customer_id(
        self, stripe_customer_id: str
    ) -> Optional[str]:
        return self._user_ids_by_stripe_customer_id.get(stripe_customer_id)

    def set_trial_start_at(self, user_id: str, at: datetime) -> None:
        profile = self._profiles.get(user_id)
        if profile is None:
            return
        profile.trial_start_at = at

    def set_trial_end_notified_at(self, user_id: str, notified_at: datetime) -> None:
        profile = self._profiles.get(user_id)
        if profile is None:
            return
        profile.trial_end_notified_at = notified_at

    def set_upgraded_at(self, user_id: str, at: datetime) -> None:
        profile = self._profiles.get(user_id)
        if profile is None:
            return
        profile.upgraded_at = at


@dataclass
class LinkingResolution:
    """`resolve_linking_code()`の結果。"""

    ok: bool
    error: Optional[str] = None


def resolve_linking_code(
    text: str,
    user_id: str,
    linking_store: LinkingCodeStoreProtocol,
    profile_store: UserProfileStoreProtocol,
    now: datetime,
) -> LinkingResolution:
    """design 3節: 受信テキストが「英大文字・数字混在、6文字、かつ`pending_links`に存在する
    コードと完全一致」する場合のみ連携コードとして扱う(正規表現の形式一致のみでは連携コードと
    判定しない、辞書引き一致を必須とする)。一致し、かつ期限切れでなければ`user_profile`を
    新規作成して使い切る(course-set-pashaと同じ24時間・one-time useの方針)。

    形式チェックを先に行わない理由: 施工メモの書き出し文言が偶然6文字の英数字混在に
    一致する可能性はごく低いが皆無ではないため、辞書引き(store.get)の成否のみを判定根拠とする
    (design 3節の「正規表現の形式一致のみでは連携コードと判定しない」方針に厳密に従う)。
    """
    if not isinstance(text, str):
        return LinkingResolution(ok=False, error="text is not a string")

    normalized_code = text.strip().upper()
    entry = linking_store.get(normalized_code)
    if entry is None:
        return LinkingResolution(
            ok=False,
            error="linking_code not found (not a code, already used, expired and purged, or never issued)",
        )

    if now - entry.issued_at > _LINK_TTL:
        linking_store.delete(normalized_code)
        return LinkingResolution(ok=False, error="linking_code expired")

    linking_store.delete(normalized_code)
    profile_store.save(
        user_id,
        UserProfile(
            business_name=entry.business_name,
            business_type=entry.business_type,
            email=entry.email,
            linked_at=now,
        ),
    )
    return LinkingResolution(ok=True)


def purge_expired_links(store: LinkingCodeStoreProtocol, now: datetime) -> int:
    """course-set-pasha/prototype/user_id_linking.pyのpurge_expired_links()と同じ位置づけ
    (FirestoreネイティブのTTL自動削除は最大24〜72時間遅延しうるため、スケジューラ発火型
    Cloud Function等から明示的に掃く経路も併せて持てるようにする定期パージ用の決定的ロジック)。
    有効期限(24時間)を過ぎたエントリを削除し、削除件数を返す。"""
    expired_codes = [
        code for code, entry in store.items() if now - entry.issued_at > _LINK_TTL
    ]
    for code in expired_codes:
        store.delete(code)
    return len(expired_codes)
