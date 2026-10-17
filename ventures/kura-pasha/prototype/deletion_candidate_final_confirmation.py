#!/usr/bin/env python3
"""
deletion-candidate-final-confirmation-design.md(フェーズ233)で設計した、削除候補
(`deletion_candidate.list_deletion_candidates()`が返すworkshop_id一覧)に対する最終確認の
判定・送信ロジック、および「連絡不能」オーナーレビュー用レポートを実行可能なコードに
落とし込んだもの。

位置づけ:
- aircon-pasha/prototype/deletion_candidate_final_confirmation.py(フェーズ167・307)と
  同じ考え方を踏襲するが、本ventureは契約単位が`craftsman_workshop/{workshop_id}`・
  送信対象が`contractor_user_id`1名に限定される構造のため、本venture既存の
  subscription_cancellation_notification.py・payment_suspension_owner_notification.pyと
  同じ「workshop_idから送信先user_idを解決する」方式を取る(design 1節)。
- 送信形式は本venture既存の全通知と同じプレーンテキスト(`LinePushClient.send_message()`)
  とし、aircon-pasha版のFlex Messageは使わない(design 1節)。
- 代替のメール経路(LINEブロック済みの場合の代替送達手段)は他venture共通の未着手課題
  のため実装しない。`is_following=False`の場合は直ちに`MARK_UNREACHABLE`へ倒す
  (design 2節)。

設計の参照元: deletion-candidate-final-confirmation-design.md, deletion_candidate.py,
data-retention-policy.md「削除候補化後の最終確認」節
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Iterable, Optional, Protocol, Sequence

import deletion_candidate
from subscription_cancellation_notification import LinePushClient, LinePushDeliveryError

# design 3節: 具体的な削除予定日には言及せず、保存期間ポリシーに基づく取り扱いを案内する
# に留める(実際の削除実行バッチがまだ存在しないため)。
DELETION_CANDIDATE_FINAL_CONFIRMATION_MESSAGE = (
    "【鞍パシャッと】データ保有についてのご案内\n"
    "\n"
    "ご契約終了から一定期間が経過したため、プライバシーポリシーに基づき、お預かりして\n"
    "いる情報(工房名・メールアドレス等)の保有継続について確認のご連絡です。\n"
    "\n"
    "引き続き保有をご希望の場合や、サービスの再開をご希望の場合は、このメッセージへの\n"
    "ご返信、または改めてのお申し込みにてご連絡ください。\n"
    "特にご連絡がない場合、当社の定めるデータ保存期間ポリシーに従って取り扱います。"
)


def render_deletion_candidate_final_confirmation_message() -> str:
    """文言をそのまま返す(日付・URL等の差し込みが無いため引数なし)。"""
    return DELETION_CANDIDATE_FINAL_CONFIRMATION_MESSAGE


# deletion-candidate-unreachable-owner-review-design.mdの「次回候補」であった連絡不能の
# 理由区分(line-reservation-aiフェーズ続き320の横展開、aircon-pashaフェーズ313・
# course-set-pashaフェーズ294に続き本ventureにも適用)。本ventureは経路判定が
# is_followingのみに基づくため(モジュールdocstring参照、push送信失敗時は即時には連絡不能
# 化しない)、理由コードは1種のみで足りる。
UNREACHABLE_REASON_NOT_FOLLOWING = "not_following"

_UNREACHABLE_REASON_LABELS = {
    UNREACHABLE_REASON_NOT_FOLLOWING: "LINE公式アカウントをブロック中",
}
_UNREACHABLE_REASON_UNKNOWN_LABEL = "不明(本フィールド追加前に記録された候補)"


class DeletionCandidateConfirmationRoute(Enum):
    """data-retention-policy.md「削除候補化後の最終確認」節の経路判定結果
    (aircon-pasha版と同一)。"""

    LINE_PUSH = "line_push"
    MARK_UNREACHABLE = "mark_unreachable"


def route_deletion_candidate_confirmation(
    is_following: bool,
) -> DeletionCandidateConfirmationRoute:
    """design 2節の経路判定をそのままコード化する。`is_following`がFalse(LINEブロック
    済み)の場合、代替のメール経路は実装しない(モジュールdocstring参照)ため、直ちに
    「連絡不能」相当のMARK_UNREACHABLEへ倒す。"""
    if is_following:
        return DeletionCandidateConfirmationRoute.LINE_PUSH
    return DeletionCandidateConfirmationRoute.MARK_UNREACHABLE


@dataclass(frozen=True)
class DeletionCandidateConfirmationWorkshopState:
    """本モジュールが参照する、削除候補workshop 1件分の状態。

    `workshop_id`は`deletion_candidate.list_deletion_candidates()`が返す一覧の要素を
    想定。`contractor_user_id`は送信先user_id、`is_following`はその
    user_profile.is_followingをそのまま反映する。`deletion_confirmation_sent_at`が
    設定済みの場合は最終確認の送達に成功済みのため、再送の対象から除外する
    (下記select_due参照)。"""

    workshop_id: str
    contractor_user_id: str
    is_following: bool
    deletion_confirmation_sent_at: Optional[datetime] = None


def select_due_deletion_candidate_final_confirmations(
    workshops: Sequence[DeletionCandidateConfirmationWorkshopState],
) -> list[DeletionCandidateConfirmationWorkshopState]:
    """`deletion_confirmation_sent_at`が未設定の候補のみを返す(入力順を維持)。

    一度LINE pushでの最終確認が届いた候補は再送しない。一方、`MARK_UNREACHABLE`に
    倒れた候補(ブロック中で送達できなかった候補)は`deletion_confirmation_sent_at`が
    設定されないため、毎回の実行で対象に残り続ける。ブロック解除(再フォロー)後に
    自動的にLINE push経路へ切り替わり、最終確認を送達できる機会を残すための意図的な
    挙動(aircon-pasha版と同じ、安全側の判断)。
    """
    return [w for w in workshops if w.deletion_confirmation_sent_at is None]


class DeletionConfirmationWorkshopStoreProtocol(Protocol):
    """本モジュールが要求する最小限のProtocol(workshop_store側)。
    `usage_counter_workshop.WorkshopStoreProtocol`/`InMemoryWorkshopStore`は構造的に
    これを満たす。"""

    def get_contractor_user_id(self, workshop_id: str) -> str:
        ...

    def get_deletion_confirmation_sent_at(self, workshop_id: str) -> Optional[datetime]:
        ...

    def set_deletion_confirmation_sent_at(
        self, workshop_id: str, sent_at: Optional[datetime]
    ) -> None:
        ...

    def set_deletion_confirmation_unreachable_at(
        self, workshop_id: str, unreachable_at: Optional[datetime]
    ) -> None:
        ...

    def set_deletion_confirmation_unreachable_reason(
        self, workshop_id: str, value: Optional[str]
    ) -> None:
        """line-reservation-aiフェーズ続き320が発見した「連絡不能の理由が未記録」という
        既知の限界を受けて追加した書き込みメソッド(aircon-pasha版と同じ)。"""
        ...


class DeletionConfirmationUnreachableAtReader(Protocol):
    """`clear_deletion_confirmation_unreachable_at()`が要求する最小限のProtocol
    (`BlockedButBillingOwnerNotifiedAtReader`と同じ考え方)。"""

    def get_deletion_confirmation_unreachable_at(self, workshop_id: str) -> Optional[datetime]:
        ...


class DeletionConfirmationUnreachableAtStoreProtocol(
    DeletionConfirmationUnreachableAtReader, DeletionConfirmationWorkshopStoreProtocol, Protocol
):
    """「クリア配線」が使う、読み書き両方を要求する合成Protocol
    (`BlockedButBillingOwnerNotifiedAtStoreProtocol`と同じ考え方)。"""


def clear_deletion_confirmation_unreachable_at(
    store: DeletionConfirmationUnreachableAtStoreProtocol, workshop_id: str,
) -> bool:
    """kura-pashaフェーズ241: aircon-pashaフェーズ320の`clear_deletion_confirmation_
    unreachable_at()`を本venture(識別子がworkshop_id起点である点が差分)に横展開する。
    aircon-pashaフェーズ322の横展開確認時、本ventureは「連絡不能概念自体を持たない」と
    誤って記録されていたが、実際には`route_deletion_candidate_confirmation()`
    (is_following=Falseで即MARK_UNREACHABLE)によりLINEブロック由来の連絡不能概念を
    aircon-pasha同様に持つことが判明したため、本クリア配線が未着手のまま残っていた
    (README.mdフェーズ241参照)。

    「フォロー再開」(is_followingがTrueに戻る)が起きた時点で呼ぶ
    (`blocked_but_billing_owner_notification.clear_blocked_but_billing_owner_notified_at()`
    と同じ「クリア配線」の考え方)。`deletion_confirmation_unreachable_at`が設定済みの
    場合のみクリアし(`unreachable_reason`も合わせてクリアする)、変更があったかどうか
    (True/False)を返す。未設定(そもそも連絡不能化されたことがない、または既にクリア済み)
    の場合は何もせず`False`を返す。

    呼び出し配線自体は本関数の対象外で、`cloud_function_webhook.process_follow_event()`
    (フォロー再開、workshop_id解決後)から呼ばれる想定
    (`clear_blocked_but_billing_owner_notified_at()`と同じ呼び出し元)。
    """
    if store.get_deletion_confirmation_unreachable_at(workshop_id) is None:
        return False
    store.set_deletion_confirmation_unreachable_at(workshop_id, None)
    store.set_deletion_confirmation_unreachable_reason(workshop_id, None)
    return True


class DeletionConfirmationUserProfileStoreProtocol(Protocol):
    """本モジュールが要求する最小限のProtocol(user_profile_store側)。
    `usage_counter_workshop.UserProfileStoreProtocol`/`InMemoryUserProfileStore`は
    構造的にこれを満たす。"""

    def get_is_following(self, user_id: str) -> bool:
        ...


def build_deletion_candidate_confirmation_states(
    candidate_workshop_ids: Sequence[str],
    workshop_store: DeletionConfirmationWorkshopStoreProtocol,
    user_profile_store: DeletionConfirmationUserProfileStoreProtocol,
) -> list[DeletionCandidateConfirmationWorkshopState]:
    """`deletion_candidate.list_deletion_candidates()`が返すworkshop_id一覧から、
    workshop_store・user_profile_storeを読み取って
    `DeletionCandidateConfirmationWorkshopState`一覧を組み立てる(呼び出し順=入力順を
    維持)。"""
    states = []
    for workshop_id in candidate_workshop_ids:
        contractor_user_id = workshop_store.get_contractor_user_id(workshop_id)
        states.append(
            DeletionCandidateConfirmationWorkshopState(
                workshop_id=workshop_id,
                contractor_user_id=contractor_user_id,
                is_following=user_profile_store.get_is_following(contractor_user_id),
                deletion_confirmation_sent_at=workshop_store.get_deletion_confirmation_sent_at(
                    workshop_id
                ),
            )
        )
    return states


@dataclass
class SendDeletionCandidateFinalConfirmationsResult:
    """1回の処理での結果(呼び出し側のログ・監視用、他送信配線のResultと対称)。"""

    sent: list[str] = field(default_factory=list)  # workshop_id、LINE push送達成功
    marked_unreachable: list[str] = field(default_factory=list)  # ブロック中、連絡不能扱い
    failed: list[str] = field(default_factory=list)  # push送達失敗(次回起動時に再試行)


def send_deletion_candidate_final_confirmations(
    workshops: Sequence[DeletionCandidateConfirmationWorkshopState],
    now: datetime,
    workshop_store: DeletionConfirmationWorkshopStoreProtocol,
    push_client: LinePushClient,
) -> SendDeletionCandidateFinalConfirmationsResult:
    """data-retention-policy.md「削除候補化後の最終確認」節の本体。

    候補ごとにroute_deletion_candidate_confirmation()で経路を判定し、LINE_PUSHなら
    メッセージ送信を試みて成功時のみ`deletion_confirmation_sent_at`を書き込み、
    MARK_UNREACHABLEなら送信を試みず`deletion_confirmation_unreachable_at`のみ更新する
    (design「オーナーが対話セッションで個別に削除可否を判断する運用」のための状態記録)。
    """
    result = SendDeletionCandidateFinalConfirmationsResult()

    for workshop in select_due_deletion_candidate_final_confirmations(workshops):
        route = route_deletion_candidate_confirmation(workshop.is_following)
        if route is DeletionCandidateConfirmationRoute.MARK_UNREACHABLE:
            workshop_store.set_deletion_confirmation_unreachable_at(workshop.workshop_id, now)
            workshop_store.set_deletion_confirmation_unreachable_reason(
                workshop.workshop_id, UNREACHABLE_REASON_NOT_FOLLOWING
            )
            result.marked_unreachable.append(workshop.workshop_id)
            continue

        try:
            push_client.send_message(
                workshop.contractor_user_id,
                render_deletion_candidate_final_confirmation_message(),
            )
        except LinePushDeliveryError:
            result.failed.append(workshop.workshop_id)
            continue
        workshop_store.set_deletion_confirmation_sent_at(workshop.workshop_id, now)
        result.sent.append(workshop.workshop_id)

    return result


def run_due_deletion_candidate_final_confirmations(
    workshop_store: DeletionConfirmationWorkshopStoreProtocol,
    user_profile_store: DeletionConfirmationUserProfileStoreProtocol,
    now: datetime,
    push_client: LinePushClient,
) -> SendDeletionCandidateFinalConfirmationsResult:
    """`deletion_candidate.list_deletion_candidates()`で削除候補workshop_id一覧を取得し、
    `build_deletion_candidate_confirmation_states()`で状態を組み立てた上で
    `send_deletion_candidate_final_confirmations()`に委譲する、store wiring込みの1本の
    関数(aircon-pasha版の`run_due_deletion_candidate_final_confirmations()`と対称)。
    `workshop_store`は`deletion_candidate.list_deletion_candidates()`が要求する
    `all_workshop_ids`/`get_deletion_candidate_at`も構造的に満たす前提
    (`InMemoryWorkshopStore`で実際にそうなっている)。
    """
    candidate_workshop_ids = deletion_candidate.list_deletion_candidates(workshop_store, now)
    states = build_deletion_candidate_confirmation_states(
        candidate_workshop_ids, workshop_store, user_profile_store
    )
    return send_deletion_candidate_final_confirmations(states, now, workshop_store, push_client)


@dataclass(frozen=True)
class UnreachableDeletionCandidate:
    """design 4節の読み取り専用レポート行。オーナーが対話セッションで個別に削除可否を
    判断するための一覧表示にのみ使う(削除実行・自動送信は一切行わない)。"""

    workshop_id: str
    deletion_confirmation_unreachable_at: datetime
    days_since_unreachable: int
    unreachable_reason: Optional[str] = None

    @property
    def unreachable_reason_label(self) -> str:
        """理由コードを対話セッション表示用の日本語ラベルに変換する。本フィールド追加前に
        連絡不能と記録された候補はunreachable_reasonがNoneのままなので、aircon-pasha版・
        line-reservation-aiフェーズ続き320と同じ方針で「不明」として表示する。"""
        if self.unreachable_reason is None:
            return _UNREACHABLE_REASON_UNKNOWN_LABEL
        return _UNREACHABLE_REASON_LABELS.get(self.unreachable_reason, self.unreachable_reason)


class UnreachableDeletionCandidateReader(Protocol):
    """`list_unreachable_deletion_candidates()`が要求する最小限のProtocol。
    `InMemoryWorkshopStore`は既存メソッド(`all_workshop_ids`・
    `get_deletion_confirmation_unreachable_at`・
    `get_deletion_confirmation_unreachable_reason`)でそのまま構造的に満たす。"""

    def all_workshop_ids(self) -> Iterable[str]:
        ...

    def get_deletion_confirmation_unreachable_at(self, workshop_id: str) -> Optional[datetime]:
        ...

    def get_deletion_confirmation_unreachable_reason(self, workshop_id: str) -> Optional[str]:
        ...


def list_unreachable_deletion_candidates(
    store: UnreachableDeletionCandidateReader, now: datetime,
) -> list[UnreachableDeletionCandidate]:
    """design 4節の選定ロジック。

    `store.all_workshop_ids()`が返す全workshop_idのうち、
    `deletion_confirmation_unreachable_at`が設定済みのものをworkshop_id昇順で一覧化する。
    本関数は読み取り専用で、削除実行や通知送信は行わない。
    """
    candidates = [
        UnreachableDeletionCandidate(
            workshop_id=workshop_id,
            deletion_confirmation_unreachable_at=unreachable_at,
            days_since_unreachable=(now - unreachable_at).days,
            unreachable_reason=store.get_deletion_confirmation_unreachable_reason(workshop_id),
        )
        for workshop_id in store.all_workshop_ids()
        if (unreachable_at := store.get_deletion_confirmation_unreachable_at(workshop_id))
        is not None
    ]
    return sorted(candidates, key=lambda candidate: candidate.workshop_id)


def render_unreachable_deletion_candidates_report(
    candidates: Sequence[UnreachableDeletionCandidate],
) -> str:
    """design 4節のレポート文言。オーナーとの対話セッション内で表示することを想定し
    (外部への自動送信は行わない)、自動削除の対象ではないこと・個別判断が必要であること
    を明示する。
    """
    if not candidates:
        return "連絡不能の削除候補工房はいません。"

    lines = [
        f"連絡不能の削除候補工房: {len(candidates)}件(オーナーによる個別確認が必要)",
        "",
    ]
    for candidate in candidates:
        lines.append(
            f"- {candidate.workshop_id}: 連絡不能判定から{candidate.days_since_unreachable}日経過"
            f"(判定日時: {candidate.deletion_confirmation_unreachable_at.isoformat()}、"
            f"理由: {candidate.unreachable_reason_label})"
        )
    lines.append("")
    lines.append(
        "本リストは自動削除の対象ではありません。オーナーが対話セッションで個別に"
        "削除可否を判断してください(data-retention-policy.md参照)。"
    )
    return "\n".join(lines)


def _demo() -> None:
    from subscription_cancellation_notification import InMemoryLinePushClient

    now = datetime(2026, 10, 13, 9, 0, 0)
    workshops = [
        # 削除候補・フォロー中: LINE pushを試みる
        DeletionCandidateConfirmationWorkshopState(
            workshop_id="w1", contractor_user_id="u1", is_following=True
        ),
        # 削除候補・ブロック中: 連絡不能扱い
        DeletionCandidateConfirmationWorkshopState(
            workshop_id="w2", contractor_user_id="u2", is_following=False
        ),
        # 既に最終確認送達済み: 対象外
        DeletionCandidateConfirmationWorkshopState(
            workshop_id="w3",
            contractor_user_id="u3",
            is_following=True,
            deletion_confirmation_sent_at=now,
        ),
    ]
    due = select_due_deletion_candidate_final_confirmations(workshops)
    print([w.workshop_id for w in due])

    class _WorkshopStoreStub:
        def __init__(self) -> None:
            self.sent_at: dict[str, Optional[datetime]] = {}
            self.unreachable_at: dict[str, Optional[datetime]] = {}
            self.unreachable_reason: dict[str, Optional[str]] = {}

        def set_deletion_confirmation_sent_at(
            self, workshop_id: str, sent_at: Optional[datetime]
        ) -> None:
            self.sent_at[workshop_id] = sent_at

        def set_deletion_confirmation_unreachable_at(
            self, workshop_id: str, unreachable_at: Optional[datetime]
        ) -> None:
            self.unreachable_at[workshop_id] = unreachable_at

        def set_deletion_confirmation_unreachable_reason(
            self, workshop_id: str, value: Optional[str]
        ) -> None:
            self.unreachable_reason[workshop_id] = value

    store = _WorkshopStoreStub()
    push = InMemoryLinePushClient()
    result = send_deletion_candidate_final_confirmations(workshops, now, store, push)
    print(
        f"sent={result.sent}, marked_unreachable={result.marked_unreachable}, "
        f"failed={result.failed}"
    )
    print(f"push count: {len(push.sent)}")


if __name__ == "__main__":
    _demo()
