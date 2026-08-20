#!/usr/bin/env python3
"""
line-user-id-linking-design.mdで設計した、LINE友だち追加(follow event)時に発行する
連携コードでuser_idを紐付けるフローを実行可能なコードに落とし込んだもの。

位置づけ:
- 一般のLINEユーザーはアプリUI上から自分のuser_idを確認できないため、フェーズ76の
  「申込フォームにuser_idを手入力する」設計は運用として成立しない。本モジュールは
  friend追加時に発行した短い連携コードを申込フォームへ入力してもらい、GAS Webhook側で
  user_idへ解決してからapplication_form_submission_flow.handle_form_submission()へ
  委譲する橋渡し役を担う。
- 実際のfollowイベント受信・ウェルカムメッセージ返信・実Firestore接続はいずれも実LINE
  Messaging API/GCP接続が必要でオーナー承認待ち(pending-approval.md参照)。本モジュールは
  コード発行・解決ロジック自体を実接続なしで検証可能にしたもの。

設計の参照元: line-user-id-linking-design.md
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional, Protocol, Tuple

from application_form_submission_flow import (
    FormSubmissionResult,
    UserProfileStoreProtocol,
    handle_form_submission,
)

# design 3節: 視認性の低い文字(0/O、1/I/L)を除いた31種
_CODE_ALPHABET = "".join(
    c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" if c not in "0O1IL"
)
_CODE_LENGTH = 6
_LINK_TTL = timedelta(hours=24)
_MAX_GENERATION_ATTEMPTS = 5


class LinkingCodeStoreProtocol(Protocol):
    """`pending_links/{code}`ドキュメントへの読み書きを表す(design 5節)。"""

    def save(self, code: str, user_id: str, issued_at: datetime) -> None:
        ...

    def get(self, code: str) -> Optional[Tuple[str, datetime]]:
        ...

    def delete(self, code: str) -> None:
        ...

    def items(self) -> Iterable[Tuple[str, str, datetime]]:
        """全エントリを`(code, user_id, issued_at)`で列挙する(期限切れパージのため)。"""
        ...


class InMemoryLinkingCodeStore:
    """実Firestore接続の代わりにdictで`pending_links`ドキュメントを保持する検証用スタブ。"""

    def __init__(self) -> None:
        self._entries: dict[str, Tuple[str, datetime]] = {}

    def save(self, code: str, user_id: str, issued_at: datetime) -> None:
        self._entries[code] = (user_id, issued_at)

    def get(self, code: str) -> Optional[Tuple[str, datetime]]:
        return self._entries.get(code)

    def delete(self, code: str) -> None:
        self._entries.pop(code, None)

    def items(self) -> Iterable[Tuple[str, str, datetime]]:
        # スナップショットを返す(パージ中の削除でイテレータが壊れないようにする)。
        return [
            (code, user_id, issued_at)
            for code, (user_id, issued_at) in list(self._entries.items())
        ]


class RandomChoiceSource(Protocol):
    """`random.Random`と同じ`choice()`インターフェースを想定(テストで決定的な値を注入するため)。"""

    def choice(self, seq):
        ...


def _generate_candidate_code(rng: RandomChoiceSource) -> str:
    return "".join(rng.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


def issue_linking_code_on_follow(
    user_id: str,
    store: LinkingCodeStoreProtocol,
    now: datetime,
    rng: RandomChoiceSource,
) -> str:
    """design 5節: `follow`イベント受信時に呼ばれる想定。重複しないコードを発行・保存し、
    コード文字列を返す(呼び出し側がこれをウェルカムメッセージへ埋め込んで返信する)。
    """
    for _ in range(_MAX_GENERATION_ATTEMPTS):
        code = _generate_candidate_code(rng)
        if store.get(code) is None:
            store.save(code, user_id, now)
            return code
    raise RuntimeError(
        f"linking code generation collided {_MAX_GENERATION_ATTEMPTS} times in a row"
    )


@dataclass
class LinkingResolution:
    """`resolve_linking_code()`の結果(design 5節)。"""

    ok: bool
    user_id: Optional[str] = None
    error: Optional[str] = None


def resolve_linking_code(
    code: Optional[str],
    store: LinkingCodeStoreProtocol,
    now: datetime,
) -> LinkingResolution:
    """design 3節: 存在確認・期限切れ判定・使い切り(one-time use)を行う。
    期限切れの場合もエントリを削除する(再利用不可のまま残さない)。
    """
    if not isinstance(code, str) or not code.strip():
        return LinkingResolution(
            ok=False, error="linking_code is missing or not a non-empty string"
        )

    normalized_code = code.strip().upper()
    entry = store.get(normalized_code)
    if entry is None:
        return LinkingResolution(
            ok=False,
            error="linking_code not found (already used, expired and purged, or never issued)",
        )

    user_id, issued_at = entry
    if now - issued_at > _LINK_TTL:
        store.delete(normalized_code)
        return LinkingResolution(ok=False, error="linking_code expired")

    store.delete(normalized_code)
    return LinkingResolution(ok=True, user_id=user_id)


def handle_form_submission_with_linking_code(
    payload: dict,
    profile_store: UserProfileStoreProtocol,
    linking_store: LinkingCodeStoreProtocol,
    now: datetime,
) -> FormSubmissionResult:
    """design 5節: GAS Webhookペイロードが`user_id`ではなく`linking_code`を持つ場合の
    エントリポイント。連携コードをuser_idへ解決してから既存の
    application_form_submission_flow.handle_form_submission()へ委譲する。
    """
    resolution = resolve_linking_code(payload.get("linking_code"), linking_store, now)
    if not resolution.ok:
        return FormSubmissionResult(ok=False, error=resolution.error)

    inner_payload = {
        "user_id": resolution.user_id,
        "gym_area_pairs_raw": payload.get("gym_area_pairs_raw", ""),
    }
    return handle_form_submission(inner_payload, profile_store)


class LinkingCodePurgeThrottle:
    """purge_expired_links()の呼び出し頻度を間引く便乗トリガー
    (linking-code-purge-trigger-design.md参照)。

    line-reservation-aiのConversationFlowStateMachine.maybe_run_idle_cleanup()と同じ
    「前回実行からMIN_INTERVAL未満ならスキップ」方式を、状態を持たない関数群である
    本モジュールに導入するための薄いラッパー。cloud_function_webhook.pyのprocess_memo_event()
    (生成依頼Webhookのたびに発火する、本ventureで最も高頻度なエントリポイント)から便乗で
    呼び出す想定。
    """

    MIN_INTERVAL = timedelta(hours=1)

    def __init__(self) -> None:
        self._last_purge_at: Optional[datetime] = None

    def maybe_run(self, store: LinkingCodeStoreProtocol, now: datetime) -> Optional[int]:
        """前回実行からMIN_INTERVAL未満の場合は何もせずNoneを返す(スキップしたことを
        呼び出し側が「対象0件だった」場合の`0`と区別できるようにするため)。"""
        if (
            self._last_purge_at is not None
            and now - self._last_purge_at < self.MIN_INTERVAL
        ):
            return None
        self._last_purge_at = now
        return purge_expired_links(store, now)


def purge_expired_links(store: LinkingCodeStoreProtocol, now: datetime) -> int:
    """design 残課題「`pending_links`の期限切れドキュメントの定期パージ」の決定的ロジック。

    本番では Firestore ネイティブ TTL ポリシーで自動削除する想定(オーナー承認・実接続後)
    だが、TTL の削除は最大 24〜72 時間遅延しうるため、スケジューラ発火型の Cloud Function や
    follow イベント便乗で明示的に掃く経路も併せて持てるよう、掃除ロジック自体を実接続なしで
    検証可能にした(line-reservation-ai の release_idle_conversations() と同じ位置づけ)。

    有効期限(24時間)を過ぎたエントリを削除し、削除件数を返す。resolve 側の遅延削除と
    冪等に共存する(既に消えたコードの再削除は no-op)。
    """
    expired_codes = [
        code
        for code, _user_id, issued_at in store.items()
        if now - issued_at > _LINK_TTL
    ]
    for code in expired_codes:
        store.delete(code)
    return len(expired_codes)
