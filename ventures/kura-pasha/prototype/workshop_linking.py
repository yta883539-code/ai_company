#!/usr/bin/env python3
"""
craftsman-account-linking-design.md(フェーズ25、フェーズ66追記)2〜3節で設計した、
LINE友だち追加(follow event)時に発行する連携コードでworkshop(工房)を新規作成する
フローを実行可能なコードに落とし込んだもの。

位置づけ:
- course-set-pasha/prototype/user_id_linking.pyの連携コード発行(`issue_linking_code_on_
  follow`)・パージ(`purge_expired_links`/`delete_pending_links_for_user`)ロジックを
  ほぼそのまま踏襲する(コード仕様・24時間TTL・使い切り一回限りが同一のため)。解決先のみ
  本venture固有の差分で、course-set-pashaは申込フォーム送信(`handle_form_submission`)へ
  委譲するのに対し、本ventureは申込フォーム自体を持たないため
  `craftsman_workshop`の新規作成(design 2〜3節)へ差し替えている。
- 実際のfollowイベント受信・ウェルカムメッセージ返信・実Firestore接続はいずれも実LINE
  Messaging API/GCP接続が必要でオーナー承認待ち(pending-approval.md参照)。本モジュールは
  コード発行・解決・workshop作成ロジック自体を実接続なしで検証可能にしたもの。
- design 7節(フェーズ66追記)の通り、workshop新規作成時のplan_idは暫定的に最安プラン
  `"light"`で仮設定する(Checkout完了時に実際に選ばれたプランで上書きする想定、
  上書き処理自体は本ファイル未着手で次の課題)。
- 5節の招待コード(`pending_workshop_invites`、既存workshopへのメンバー追加)、4節の
  Stripe Checkout連携(`client_reference_id`=workshop_id)は本ファイル未着手のため
  引き続き次の課題として残す。

設計の参照元: craftsman-account-linking-design.md(フェーズ25、フェーズ66追記)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Iterable, Optional, Protocol, Tuple

from usage_counter_workshop import UserProfileStoreProtocol, WorkshopStoreProtocol

# design 2節: course-set-pasha/line-user-id-linking-design.mdと同一のコード仕様
# (視認性の低い0/O、1/I/Lを除いた31種、6文字、24時間有効・使い切り一回限り)。
_CODE_ALPHABET = "".join(
    c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" if c not in "0O1IL"
)
_CODE_LENGTH = 6
_LINK_TTL = timedelta(hours=24)
_MAX_GENERATION_ATTEMPTS = 5

# design 7節(フェーズ66追記): workshop新規作成時の暫定plan_id。
PROVISIONAL_PLAN_ID_ON_CREATION = "light"


class LinkingCodeStoreProtocol(Protocol):
    """`pending_links/{code}`ドキュメントへの読み書きを表す(design 2節)。"""

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
    """design 2節: `follow`イベント受信時に呼ばれる想定。重複しないコードを発行・保存し、
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
    """`resolve_linking_code()`の結果(design 2節)。"""

    ok: bool
    user_id: Optional[str] = None
    error: Optional[str] = None


def resolve_linking_code(
    code: Optional[str],
    store: LinkingCodeStoreProtocol,
    now: datetime,
) -> LinkingResolution:
    """design 2節: 存在確認・期限切れ判定・使い切り(one-time use)を行う。
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


@dataclass
class WorkshopCreationResult:
    """`create_workshop_from_linking_code()`の結果。"""

    ok: bool
    workshop_id: Optional[str] = None
    already_linked: bool = False
    error: Optional[str] = None


def create_workshop_from_linking_code(
    code: Optional[str],
    linking_store: LinkingCodeStoreProtocol,
    user_profile_store: UserProfileStoreProtocol,
    workshop_store: WorkshopStoreProtocol,
    now: datetime,
    *,
    workshop_id_factory: Optional[Callable[[], str]] = None,
) -> WorkshopCreationResult:
    """design 2〜3節: LINEトーク上で職人が連携コードを送信した際のエントリポイント。

    1. `resolve_linking_code()`でコードをuser_idへ解決する(失敗時はそのままエラーを返す)。
    2. 解決したuser_idが既にworkshopへ所属済み(`user_profile.workshop_id`設定済み)の
       場合は新規作成せず`already_linked=True`で既存workshop_idを返す(design自体は
       この重複ケースを明記していないが、コード自体は使い切り一回限りのため通常は
       発生しない防御的分岐。二重タップ等でコード解決後にハンドラが再実行された場合の
       誤って2つ目のworkshopが作られる事態を防ぐ)。
    3. 新規`workshop_id`を発行し(`workshop_id_factory`未指定時は`uuid.uuid4().hex`、
       実Firestoreでは`collection.document()`の自動採番に相当)、design 3節の通り
       解決したuser_idを`contractor_user_id`かつ唯一の`member_user_ids`とする
       1人だけのworkshopを作成する。design 7節(フェーズ66追記)の通りplan_idは
       暫定的に`PROVISIONAL_PLAN_ID_ON_CREATION`(`"light"`)で仮設定し、
       trial_start_atをnowで設定、subscription_statusを`"trialing"`で明示的に
       設定する(InMemoryWorkshopStoreは未設定時に`"trialing"`を返す既定値を持つが、
       実Firestoreへ移行した際に既定値に頼らず済むよう明示的に書き込む)。
    4. `user_profile.workshop_id`を新規workshop_idへリンクする。
    """
    resolution = resolve_linking_code(code, linking_store, now)
    if not resolution.ok:
        return WorkshopCreationResult(ok=False, error=resolution.error)

    user_id = resolution.user_id
    existing_workshop_id = user_profile_store.get_workshop_id(user_id)
    if existing_workshop_id is not None:
        return WorkshopCreationResult(
            ok=True, workshop_id=existing_workshop_id, already_linked=True
        )

    factory = workshop_id_factory or (lambda: uuid.uuid4().hex)
    workshop_id = factory()

    workshop_store.set_members(workshop_id, contractor_user_id=user_id, member_user_ids=[user_id])
    workshop_store.set_plan(workshop_id, PROVISIONAL_PLAN_ID_ON_CREATION)
    workshop_store.set_trial_start_at(workshop_id, now)
    workshop_store.set_subscription_status(workshop_id, "trialing")
    user_profile_store.link(user_id, workshop_id)

    return WorkshopCreationResult(ok=True, workshop_id=workshop_id, already_linked=False)


class LinkingCodePurgeThrottle:
    """purge_expired_links()の呼び出し頻度を間引く便乗トリガー
    (course-set-pasha/user_id_linking.LinkingCodePurgeThrottleと同じ位置づけ)。
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


def delete_pending_links_for_user(user_id: str, store: LinkingCodeStoreProtocol) -> int:
    """unfollow時等、ブロックされたuser_id宛の未使用連携コードを有効期限を待たずに
    即時削除する(course-set-pashaのunfollow-event-handling-design.md論点2と同じ位置づけ)。
    削除件数を返す(該当コードが無ければ0)。
    """
    target_codes = [
        code for code, entry_user_id, _issued_at in store.items() if entry_user_id == user_id
    ]
    for code in target_codes:
        store.delete(code)
    return len(target_codes)


def purge_expired_links(store: LinkingCodeStoreProtocol, now: datetime) -> int:
    """有効期限(24時間)を過ぎたエントリを削除し、削除件数を返す。resolve側の遅延削除と
    冪等に共存する(既に消えたコードの再削除はno-op)。
    """
    expired_codes = [
        code
        for code, _user_id, issued_at in store.items()
        if now - issued_at > _LINK_TTL
    ]
    for code in expired_codes:
        store.delete(code)
    return len(expired_codes)
