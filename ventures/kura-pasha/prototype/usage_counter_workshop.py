#!/usr/bin/env python3
"""
usage-counter-workshop-key-design.md(フェーズ26)2節で確定した、生成リクエスト受信時の
月間生成回数カウント処理(user_id→workshop_id→usage_counter参照の3ステップ)を
実行可能なコードに落とし込んだもの。

位置づけ:
- README.md「次にやること」1点目(本venture未着手だった生成リクエスト処理の
  プロトタイプコード)に対応する、本venture初のprototype/コード。
- course-set-pasha/prototype/post_generation_checks.py・
  aircon-pasha同等モジュールと同じ位置づけで、実Firestore接続なしにロジックのみを
  検証可能にする。実LINE Messaging API・実Firestore・実Stripe接続はいずれもオーナー
  承認待ちの範囲(pending-approval.md参照)で、本モジュールでは行わない。
- craftsman-account-linking-design.md(フェーズ25)で確定した`craftsman_workshop`・
  `user_profile.workshop_id`・usage-counter-workshop-key-design.md(フェーズ26)で
  確定した`usage_counter/{workshop_id}`のデータ構造を前提とする。
- 未検証・残課題(usage-counter-workshop-key-design.md末尾)だった
  「`user_profile.workshop_id`が未設定(workshop未作成)のエッジケース」は、本モジュールで
  `WorkshopNotLinkedError`として明示的に扱う形で解消した。
- フェーズ30: downgrade-excess-member-handling-design.md(フェーズ28)「3. 確定する
  設計」の`pending_member_reduction_effective_at`都度チェック処理、および
  member-retention-notice-design.md(フェーズ29)「4. 未検証・残課題」1点目だった
  `specified_member_name`と表示名の突き合わせロジックを追加した
  (`check_and_apply_pending_member_reduction`・`ensure_member_is_active`)。
  縮小後に除外されたメンバーからの生成リクエストを検知する`MemberRemovedError`も
  あわせて追加した(`WorkshopNotLinkedError`相当の扱い)。
- フェーズ31: フェーズ30末尾の残課題だった、`check_and_apply_pending_member_reduction`→
  `ensure_member_is_active`→`check_and_increment_usage`の呼び出し順序を実際の生成
  リクエスト処理フローとして統合する`process_generation_request`を追加した。
- フェーズ35: contractor-transfer-design.md(フェーズ33・schema反映はフェーズ34)の
  「4. 未検証・残課題」に残っていた、`craftsman_workshop`データ構造側の契約者譲渡
  確定処理(`contractor_user_id`更新)のプロトタイプコード化に対応した
  (`resolve_contractor_transfer_target`・`apply_contractor_transfer`)。契約者からの
  再確認応答(「はい」等の自由記述)自体の検知プロンプト設計は引き続き次の課題として
  残す。
- フェーズ38: contractor-transfer-confirmation-detection-design.md(フェーズ36・
  schema反映はフェーズ37)「5. 未検証・残課題」に残っていた、
  `pending_contractor_transfer`一時状態の読み書き(`WorkshopStoreProtocol`への追加、
  `apply_contractor_transfer`呼び出し時・キャンセル時・期限切れ時の削除処理)を
  プロトタイプコード化した(`start_pending_contractor_transfer`・
  `is_contractor_transfer_confirmation_context`・`cancel_pending_contractor_transfer`・
  `check_and_expire_pending_contractor_transfer`)。期限切れ後の案内文言自体の
  schema・プロンプト設計(同ファイル5節1点目)は引き続き次の課題として残す。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Protocol


# pricing-plan.md確定値(プラン名→月間生成回数上限・超過分の従量単価)。
PLAN_LIMITS = {
    "light": {"monthly_limit": 3, "overage_price_jpy": 250},
    "standard": {"monthly_limit": 8, "overage_price_jpy": 200},
    "multi_craftsman": {"monthly_limit": 20, "overage_price_jpy": 150},
}


class WorkshopNotLinkedError(Exception):
    """送信元user_idにworkshop_idが未設定(workshop未作成)の場合に送出する。

    craftsman-account-linking-design.md 2節の通り、LINE友だち追加時点ではまだ
    連携コードが未解決でworkshopが作られていない状態がありうる。呼び出し側は
    この例外を「まだ新規契約フローが完了していません」という案内に変換する想定。
    """


class UnknownPlanError(Exception):
    """workshopのplan_idがPLAN_LIMITSに存在しない場合に送出する(データ不整合)。"""


class MemberRemovedError(Exception):
    """downgrade-excess-member-handling-design.md 3節の縮小処理によって
    member_user_idsから除外されたuser_idから生成リクエストが来た場合に送出する。

    WorkshopNotLinkedError相当の扱いとし、呼び出し側はREMOVED_MEMBER_NOTICEの文言に
    変換して返す想定(prototype/usage_counter_workshop.pyの既存例外設計の拡張)。
    """


REMOVED_MEMBER_NOTICE = (
    "所属していたworkshopのプラン変更により、現在はご利用いただけません。"
    "利用を続けるには契約者様に新規のworkshopへの再招待をご依頼ください。"
)


# contractor-transfer-confirmation-detection-design.md(フェーズ36)1節: requested_at+24時間。
PENDING_CONTRACTOR_TRANSFER_EXPIRY_HOURS = 24


@dataclass
class PendingContractorTransfer:
    """`craftsman_workshop/{workshop_id}.pending_contractor_transfer`の机上表現。

    contractor-transfer-confirmation-detection-design.md 1節で確定したフィールド構成
    (candidate_user_id/candidate_member_name/requested_at/expires_at)にそのまま対応する。
    """

    candidate_user_id: str
    candidate_member_name: str
    requested_at: datetime
    expires_at: datetime


class UserProfileStoreProtocol(Protocol):
    """`user_profile/{user_id}.workshop_id`への読み取りを表す。"""

    def get_workshop_id(self, user_id: str) -> Optional[str]:
        ...


class WorkshopStoreProtocol(Protocol):
    """`craftsman_workshop/{workshop_id}`への読み取りを表す(plan_id・複数職人プラン
    関連フィールドを含む、同一Firestoreドキュメントの各フィールド)。
    """

    def get_plan_id(self, workshop_id: str) -> str:
        ...

    def get_contractor_user_id(self, workshop_id: str) -> str:
        ...

    def get_member_user_ids(self, workshop_id: str) -> list[str]:
        ...

    def get_member_display_name(self, workshop_id: str, user_id: str) -> Optional[str]:
        ...

    def get_pending_reduction_effective_at(self, workshop_id: str) -> Optional[datetime]:
        ...

    def get_specified_retention_member_name(self, workshop_id: str) -> Optional[str]:
        ...

    def apply_member_reduction(self, workshop_id: str, retained_user_ids: list[str]) -> None:
        """member_user_idsを置き換え、pending_member_reduction_effective_atをクリアする。"""
        ...

    def set_contractor_user_id(self, workshop_id: str, user_id: str) -> None:
        """contractor-transfer-design.md 3節の確定処理でcontractor_user_idを更新する。"""
        ...

    def get_pending_contractor_transfer(self, workshop_id: str) -> Optional[PendingContractorTransfer]:
        """`pending_contractor_transfer`を返す(未設定ならNone)。"""
        ...

    def set_pending_contractor_transfer(
        self, workshop_id: str, pending: PendingContractorTransfer
    ) -> None:
        ...

    def clear_pending_contractor_transfer(self, workshop_id: str) -> None:
        """確定処理実行時・キャンセル時・期限切れ時のいずれでも呼び出される削除処理。"""
        ...


class UsageCounterStoreProtocol(Protocol):
    """`usage_counter/{workshop_id}`(month・count)への読み書きを表す。"""

    def get(self, workshop_id: str) -> Optional[tuple[str, int]]:
        """(month, count)を返す。ドキュメント未作成の場合はNone。"""
        ...

    def set(self, workshop_id: str, month: str, count: int) -> None:
        ...


class InMemoryUserProfileStore:
    def __init__(self) -> None:
        self._workshop_id_by_user: dict[str, str] = {}

    def link(self, user_id: str, workshop_id: str) -> None:
        self._workshop_id_by_user[user_id] = workshop_id

    def get_workshop_id(self, user_id: str) -> Optional[str]:
        return self._workshop_id_by_user.get(user_id)


class InMemoryWorkshopStore:
    def __init__(self) -> None:
        self._plan_id_by_workshop: dict[str, str] = {}
        self._contractor_by_workshop: dict[str, str] = {}
        self._member_user_ids_by_workshop: dict[str, list[str]] = {}
        self._display_names_by_workshop: dict[str, dict[str, str]] = {}
        self._pending_reduction_effective_at_by_workshop: dict[str, datetime] = {}
        self._specified_retention_name_by_workshop: dict[str, str] = {}
        self._pending_contractor_transfer_by_workshop: dict[str, PendingContractorTransfer] = {}

    def set_plan(self, workshop_id: str, plan_id: str) -> None:
        self._plan_id_by_workshop[workshop_id] = plan_id

    def get_plan_id(self, workshop_id: str) -> str:
        return self._plan_id_by_workshop[workshop_id]

    def set_members(
        self,
        workshop_id: str,
        contractor_user_id: str,
        member_user_ids: list[str],
        display_names: Optional[dict[str, str]] = None,
    ) -> None:
        """contractor_user_idはmember_user_idsに含めても含めなくてもよい
        (get_member_user_idsは常に契約者を含む一覧を返す)。
        """
        self._contractor_by_workshop[workshop_id] = contractor_user_id
        all_ids = [contractor_user_id] + [
            uid for uid in member_user_ids if uid != contractor_user_id
        ]
        self._member_user_ids_by_workshop[workshop_id] = all_ids
        self._display_names_by_workshop[workshop_id] = dict(display_names or {})

    def get_contractor_user_id(self, workshop_id: str) -> str:
        return self._contractor_by_workshop[workshop_id]

    def get_member_user_ids(self, workshop_id: str) -> list[str]:
        return list(self._member_user_ids_by_workshop.get(workshop_id, []))

    def get_member_display_name(self, workshop_id: str, user_id: str) -> Optional[str]:
        return self._display_names_by_workshop.get(workshop_id, {}).get(user_id)

    def set_pending_reduction_effective_at(self, workshop_id: str, effective_at: datetime) -> None:
        self._pending_reduction_effective_at_by_workshop[workshop_id] = effective_at

    def get_pending_reduction_effective_at(self, workshop_id: str) -> Optional[datetime]:
        return self._pending_reduction_effective_at_by_workshop.get(workshop_id)

    def set_specified_retention_member_name(self, workshop_id: str, name: str) -> None:
        self._specified_retention_name_by_workshop[workshop_id] = name

    def get_specified_retention_member_name(self, workshop_id: str) -> Optional[str]:
        return self._specified_retention_name_by_workshop.get(workshop_id)

    def apply_member_reduction(self, workshop_id: str, retained_user_ids: list[str]) -> None:
        self._member_user_ids_by_workshop[workshop_id] = list(retained_user_ids)
        self._pending_reduction_effective_at_by_workshop.pop(workshop_id, None)

    def set_contractor_user_id(self, workshop_id: str, user_id: str) -> None:
        self._contractor_by_workshop[workshop_id] = user_id

    def get_pending_contractor_transfer(self, workshop_id: str) -> Optional[PendingContractorTransfer]:
        return self._pending_contractor_transfer_by_workshop.get(workshop_id)

    def set_pending_contractor_transfer(
        self, workshop_id: str, pending: PendingContractorTransfer
    ) -> None:
        self._pending_contractor_transfer_by_workshop[workshop_id] = pending

    def clear_pending_contractor_transfer(self, workshop_id: str) -> None:
        self._pending_contractor_transfer_by_workshop.pop(workshop_id, None)


class InMemoryUsageCounterStore:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[str, int]] = {}

    def get(self, workshop_id: str) -> Optional[tuple[str, int]]:
        return self._entries.get(workshop_id)

    def set(self, workshop_id: str, month: str, count: int) -> None:
        self._entries[workshop_id] = (month, count)


def _current_month_key(now: datetime) -> str:
    return now.strftime("%Y-%m")


@dataclass
class UsageCheckResult:
    workshop_id: str
    plan_id: str
    month: str
    count_after_increment: int
    monthly_limit: int
    within_limit: bool
    overage_price_jpy: int


def check_and_increment_usage(
    user_id: str,
    now: datetime,
    user_profile_store: UserProfileStoreProtocol,
    workshop_store: WorkshopStoreProtocol,
    usage_counter_store: UsageCounterStoreProtocol,
) -> UsageCheckResult:
    """usage-counter-workshop-key-design.md 2節の3ステップを実行する。

    1. user_id→workshop_idを引く(未設定ならWorkshopNotLinkedError)。
    2. usage_counter/{workshop_id}を読み、monthが当月でなければcount=0でリセットしてから
       加算する(subscription-cancellation-flow-design.mdが踏襲済みのダウングレード時の
       count維持方針とは独立に、月替わりのリセットのみここで扱う)。
    3. plan_idをcraftsman_workshopから取得し、pricing-plan.mdの上限と突き合わせて
       上限超過(従量課金要否)を判定する。
    """
    workshop_id = user_profile_store.get_workshop_id(user_id)
    if workshop_id is None:
        raise WorkshopNotLinkedError(
            f"user_id={user_id!r}にworkshop_idが未設定です(新規契約フロー未完了)"
        )

    plan_id = workshop_store.get_plan_id(workshop_id)
    if plan_id not in PLAN_LIMITS:
        raise UnknownPlanError(f"workshop_id={workshop_id!r}のplan_id={plan_id!r}が不明です")

    current_month = _current_month_key(now)
    existing = usage_counter_store.get(workshop_id)
    if existing is None or existing[0] != current_month:
        count_before = 0
    else:
        count_before = existing[1]

    count_after = count_before + 1
    usage_counter_store.set(workshop_id, current_month, count_after)

    limits = PLAN_LIMITS[plan_id]
    return UsageCheckResult(
        workshop_id=workshop_id,
        plan_id=plan_id,
        month=current_month,
        count_after_increment=count_after,
        monthly_limit=limits["monthly_limit"],
        within_limit=count_after <= limits["monthly_limit"],
        overage_price_jpy=limits["overage_price_jpy"],
    )


@dataclass
class MemberReductionResult:
    workshop_id: str
    applied: bool
    retained_user_id: Optional[str]
    removed_user_ids: list[str]
    specified_member_matched: bool
    note: Optional[str]


def check_and_apply_pending_member_reduction(
    workshop_id: str,
    now: datetime,
    workshop_store: WorkshopStoreProtocol,
) -> Optional[MemberReductionResult]:
    """downgrade-excess-member-handling-design.md「3. 確定する設計」の都度チェック処理。

    生成リクエスト受信のたびに(check_and_increment_usageの前段として)呼び出す想定。
    `pending_member_reduction_effective_at`が未設定、または猶予期間中(now未到達)の
    場合はNoneを返し何もしない。
    """
    effective_at = workshop_store.get_pending_reduction_effective_at(workshop_id)
    if effective_at is None or now < effective_at:
        return None

    member_user_ids = workshop_store.get_member_user_ids(workshop_id)
    contractor_user_id = workshop_store.get_contractor_user_id(workshop_id)

    if len(member_user_ids) <= 1:
        # 既に縮小済み(または元々1名)。pending_member_reduction_effective_atだけを
        # クリアする。
        workshop_store.apply_member_reduction(workshop_id, member_user_ids)
        return MemberReductionResult(
            workshop_id=workshop_id,
            applied=False,
            retained_user_id=member_user_ids[0] if member_user_ids else None,
            removed_user_ids=[],
            specified_member_matched=False,
            note=None,
        )

    specified_name = workshop_store.get_specified_retention_member_name(workshop_id)
    specified_matched = False
    note = None
    if specified_name is not None:
        # member-retention-notice-design.md「4. 未検証・残課題」1点目の突き合わせ。
        # downgrade-excess-member-handling-design.md「3. 確定する設計」の通り、上限は
        # 契約者1名のみ(契約者譲渡機能はMVP範囲外)であるため、契約者以外を指した
        # 指定は反映できずデフォルトルールを適用し、noteに記録するのみとする。
        contractor_display_name = workshop_store.get_member_display_name(
            workshop_id, contractor_user_id
        )
        if contractor_display_name is not None and contractor_display_name == specified_name:
            specified_matched = True
        else:
            note = (
                f"契約者から指定された残留希望者名({specified_name!r})は契約者本人と"
                "一致しない(契約者以外を指した指定は契約者譲渡機能がMVP範囲外のため"
                "反映できない)ため、デフォルトルール(契約者のみ残す)を適用した"
            )

    removed_user_ids = [uid for uid in member_user_ids if uid != contractor_user_id]
    workshop_store.apply_member_reduction(workshop_id, [contractor_user_id])

    return MemberReductionResult(
        workshop_id=workshop_id,
        applied=True,
        retained_user_id=contractor_user_id,
        removed_user_ids=removed_user_ids,
        specified_member_matched=specified_matched,
        note=note,
    )


def ensure_member_is_active(
    user_id: str,
    workshop_id: str,
    workshop_store: WorkshopStoreProtocol,
) -> None:
    """user_idがworkshopの契約者、または現在のmember_user_idsに含まれることを検証する。

    downgrade-excess-member-handling-design.md「3. 確定する設計」の通り、縮小処理
    (check_and_apply_pending_member_reduction)によって除外されたメンバーからの
    生成リクエストをMemberRemovedErrorとして検知する。呼び出し順序は
    (1) check_and_apply_pending_member_reduction → (2) 本関数 → (3)
    check_and_increment_usage を想定するが、その統合自体は本モジュール未着手で
    次の課題として残す。
    """
    if user_id == workshop_store.get_contractor_user_id(workshop_id):
        return
    if user_id in workshop_store.get_member_user_ids(workshop_id):
        return
    raise MemberRemovedError(
        f"user_id={user_id!r}はworkshop_id={workshop_id!r}のメンバーから除外済みです"
    )


@dataclass
class GenerationRequestResult:
    usage: UsageCheckResult
    member_reduction: Optional[MemberReductionResult]


def process_generation_request(
    user_id: str,
    now: datetime,
    user_profile_store: UserProfileStoreProtocol,
    workshop_store: WorkshopStoreProtocol,
    usage_counter_store: UsageCounterStoreProtocol,
) -> GenerationRequestResult:
    """生成リクエスト受信時に呼び出す統合エントリポイント。

    フェーズ30時点では3関数がそれぞれ独立して呼び出し可能なだけで、実際の
    呼び出し順序(ensure_member_is_activeのdocstring記載)が統合されていなかった。
    本関数で (1) check_and_apply_pending_member_reduction → (2)
    ensure_member_is_active → (3) check_and_increment_usage の順に実行する。

    (1)を先に行うのは、契約者が縮小猶予期間の到達後に最初に生成リクエストを
    送ってきた場合、その1回のリクエストで縮小を確定させたうえで(2)の判定に
    反映させるため(縮小と除外検知が同一リクエスト内で整合する必要がある)。
    """
    workshop_id = user_profile_store.get_workshop_id(user_id)
    if workshop_id is None:
        raise WorkshopNotLinkedError(
            f"user_id={user_id!r}にworkshop_idが未設定です(新規契約フロー未完了)"
        )

    member_reduction = check_and_apply_pending_member_reduction(
        workshop_id, now, workshop_store
    )
    ensure_member_is_active(user_id, workshop_id, workshop_store)
    usage = check_and_increment_usage(
        user_id, now, user_profile_store, workshop_store, usage_counter_store
    )
    return GenerationRequestResult(usage=usage, member_reduction=member_reduction)


class ContractorTransferTargetNotFoundError(Exception):
    """契約者譲渡の確定処理を、既存メンバーに含まれないuser_idに対して呼び出した場合に
    送出する(contractor-transfer-design.md 2節のスコープ限定違反)。呼び出し側は本来
    resolve_contractor_transfer_targetがNoneを返した時点でcontractor_transfer_unclearの
    案内に切り替える想定であり、本例外はその前段チェックを取りこぼした場合の防御用。
    """


@dataclass
class ContractorTransferResult:
    workshop_id: str
    previous_contractor_user_id: str
    new_contractor_user_id: str
    matched_display_name: str


def resolve_contractor_transfer_target(
    workshop_id: str,
    specified_member_name: str,
    workshop_store: WorkshopStoreProtocol,
) -> Optional[str]:
    """contractor-transfer-design.md 3節: 契約者のメッセージ中で名指しされた相手が、
    workshopの既存メンバー(契約者自身を除く)の表示名と一致するかを判定する。

    一致するuser_idを返す(status=contractor_transfer_selectionに対応)。一致しない
    場合はNoneを返し、呼び出し側でstatus=contractor_transfer_unclearの案内文言
    (「先に招待コードでworkshopへ加わっていただいてから」)に切り替える想定。
    """
    contractor_user_id = workshop_store.get_contractor_user_id(workshop_id)
    for member_user_id in workshop_store.get_member_user_ids(workshop_id):
        if member_user_id == contractor_user_id:
            continue
        display_name = workshop_store.get_member_display_name(workshop_id, member_user_id)
        if display_name is not None and display_name == specified_member_name:
            return member_user_id
    return None


def apply_contractor_transfer(
    workshop_id: str,
    new_contractor_user_id: str,
    workshop_store: WorkshopStoreProtocol,
) -> ContractorTransferResult:
    """contractor-transfer-design.md 3節の確定処理。契約者からの再確認応答(「はい」等)を
    受けた後に呼び出す想定(再確認応答自体の検知プロンプト設計は次の課題として残す)。

    new_contractor_user_idは事前にresolve_contractor_transfer_targetで既存メンバーと
    確認済みであることを前提とするが、本関数でも再度member_user_ids所属を検証する
    (2節のスコープ限定: workshop外の第三者への直接譲渡は不可)。旧契約者は
    member_user_idsから自動的には外さない(3節の方針通り、脱退は別途本人の意思表示に
    委ねる)。usage_counter/{workshop_id}はworkshop_id不変のため影響を受けない。
    """
    if new_contractor_user_id not in workshop_store.get_member_user_ids(workshop_id):
        raise ContractorTransferTargetNotFoundError(
            f"user_id={new_contractor_user_id!r}はworkshop_id={workshop_id!r}の"
            "既存メンバーに含まれていません(workshop外への直接譲渡はスコープ外)"
        )
    previous_contractor_user_id = workshop_store.get_contractor_user_id(workshop_id)
    matched_display_name = workshop_store.get_member_display_name(
        workshop_id, new_contractor_user_id
    )
    workshop_store.set_contractor_user_id(workshop_id, new_contractor_user_id)
    # contractor-transfer-confirmation-detection-design.md 1節: 確定処理実行時に
    # pending_contractor_transferを削除する。
    workshop_store.clear_pending_contractor_transfer(workshop_id)
    return ContractorTransferResult(
        workshop_id=workshop_id,
        previous_contractor_user_id=previous_contractor_user_id,
        new_contractor_user_id=new_contractor_user_id,
        matched_display_name=matched_display_name or "",
    )


def start_pending_contractor_transfer(
    workshop_id: str,
    candidate_user_id: str,
    candidate_member_name: str,
    now: datetime,
    workshop_store: WorkshopStoreProtocol,
    expiry_hours: int = PENDING_CONTRACTOR_TRANSFER_EXPIRY_HOURS,
) -> PendingContractorTransfer:
    """contractor-transfer-confirmation-detection-design.md 1節: status=
    contractor_transfer_selectionの確認文言生成(resolve_contractor_transfer_targetが
    一致を返した時点)と同時に、アプリケーション側でpending_contractor_transferを
    書き込む。expires_atはrequested_at(=now)+expiry_hoursとする。
    """
    pending = PendingContractorTransfer(
        candidate_user_id=candidate_user_id,
        candidate_member_name=candidate_member_name,
        requested_at=now,
        expires_at=now + timedelta(hours=expiry_hours),
    )
    workshop_store.set_pending_contractor_transfer(workshop_id, pending)
    return pending


def is_contractor_transfer_confirmation_context(
    user_id: str,
    workshop_id: str,
    now: datetime,
    workshop_store: WorkshopStoreProtocol,
) -> bool:
    """contractor-transfer-confirmation-detection-design.md 2節: メッセージ送信者が
    contractor_user_idと一致し、かつpending_contractor_transferが存在しexpires_at
    以内である場合に限りTrueを返す。呼び出し側はTrueのときのみ「契約者交代の確認待ち」
    という文脈をプロンプトへ埋め込んだ上でLLMを呼び出す想定(3節の3パターン判定)。
    """
    if user_id != workshop_store.get_contractor_user_id(workshop_id):
        return False
    pending = workshop_store.get_pending_contractor_transfer(workshop_id)
    if pending is None:
        return False
    return now <= pending.expires_at


def cancel_pending_contractor_transfer(
    workshop_id: str,
    workshop_store: WorkshopStoreProtocol,
) -> None:
    """contractor-transfer-confirmation-detection-design.md 3節:
    kind=contractor_transfer_cancelledのとき、pending_contractor_transferを削除する
    のみでcontractor_user_idは更新しない。
    """
    workshop_store.clear_pending_contractor_transfer(workshop_id)


def check_and_expire_pending_contractor_transfer(
    workshop_id: str,
    now: datetime,
    workshop_store: WorkshopStoreProtocol,
) -> Optional[PendingContractorTransfer]:
    """contractor-transfer-confirmation-detection-design.md 4節: expires_atを過ぎた
    pending_contractor_transferを削除する。期限切れであった場合はその(削除前の)値を
    返し、呼び出し側で受動的な案内文言への切り替え判定に使えるようにする
    (案内文言自体のschema・プロンプト設計は5節の残課題として本関数では扱わない)。
    期限内、または未設定の場合はNoneを返し何もしない。
    """
    pending = workshop_store.get_pending_contractor_transfer(workshop_id)
    if pending is None or now <= pending.expires_at:
        return None
    workshop_store.clear_pending_contractor_transfer(workshop_id)
    return pending
