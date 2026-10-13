#!/usr/bin/env python3
"""
data-retention-policy.md「削除候補化後の最終確認」節で方針のみ整理していた、削除候補
(`deletion_candidate.list_deletion_candidates()`が返すuser_id一覧)に対する最終確認の
判定・送信ロジックを、実行可能なコードに落とし込んだもの(aircon-pasha/deletion_candidate_
final_confirmation.pyの横展開)。

位置づけ:
- data-retention-policy.mdは最終確認の経路を「主経路: LINE公式アカウントからのpush送信
  (ただしunfollow〈ブロック〉済みの場合は送達できない)」「代替経路: 申込フォームで収集した
  `user_profile.email`による送信(実際の送信には送信用サービスのアカウント作成が必要で
  オーナー承認待ち)」の2段構成としていた。本モジュールは主経路(LINE push)のみを実装対象
  とし、代替経路(実メール送信)は同ドキュメントの記載どおり引き続きオーナー承認待ちの範囲
  として一切実装しない(新規の承認待ち事項ではない、既存記載の範囲)。
- 本venture(course-set-pasha)はStripe Webhookディスパッチ上、削除候補の状態
  (`deletion_candidate_at`等、deletion_candidate.py)と`is_following`
  (application_form_submission_flow.UserProfileStoreProtocol)を別々のstoreオブジェクトに
  分けて扱っている(stripe_webhook.dispatch_stripe_event()が`store`〈削除候補用〉と
  `user_profile_store`〈is_following等〉を別引数として受け取る構成)。aircon-pashaが
  単一の`UserProfile`に両方を統合しているのとは異なるため、本モジュールは`deletion_store`
  (`ProfileDeletionCandidateStoreProtocol`+送達状態2フィールド)と`profile_store`
  (`is_following`読み取り)の2引数を受け取る構成とする(本venture自身の既存アーキテクチャに
  合わせた適応で、aircon-pashaとの機能差はない)。
- `is_following=False`(ブロック済み、代替のメール経路は上記のとおり承認待ちで未実装)の
  場合、data-retention-policy.mdの「連絡不能」フラグに相当する状態として
  `deletion_confirmation_unreachable_at`を記録するのみに留め、削除そのものへは一切
  進めない(design「連絡不能ケースは自動削除には進まず(中略)オーナーが対話セッションで
  個別に削除可否を判断する運用とする」をそのままコード化)。
- `LinePushClient`・`LinePushDeliveryError`はtrial_end_scheduler.pyで既に定義済みのものを
  そのまま再利用する(payment_suspension_owner_notification.py等と同じ方針、本モジュールで
  重複定義しない)。本ventureはこれまでFlex Messageを使わず`send_message(user_id, text)`の
  プレーンテキストのみで通知を送っているため(payment_suspension_owner_notification.py等と
  同じ)、本モジュールもFlex Messageは使わない。

設計の参照元: data-retention-policy.md「削除候補化後の最終確認」節, deletion_candidate.py,
application_form_submission_flow.py(`is_following`)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Iterable, Optional, Protocol, Sequence

import deletion_candidate
from trial_end_scheduler import LinePushClient, LinePushDeliveryError

DELETION_CANDIDATE_FINAL_CONFIRMATION_MESSAGE = (
    "【コースセットパシャッと】データ保有についてのご案内\n"
    "\n"
    "ご契約終了から一定期間が経過したため、プライバシーポリシーに基づき、"
    "お預かりしている情報(登録ジム・エリア情報等)の保有継続について確認の"
    "ご連絡です。\n"
    "\n"
    "引き続き保有をご希望の場合や、サービスの再開をご希望の場合は、このメッセージへの"
    "ご返信、または改めてのお申し込みにてご連絡ください。\n"
    "特にご連絡がない場合、当社の定めるデータ保存期間ポリシーに従って取り扱います。"
)


def render_deletion_candidate_final_confirmation_message() -> str:
    """文言をそのまま返す(日付・URL等の差し込みが無いため引数なし、aircon-pashaの
    `render_deletion_candidate_final_confirmation_message()`と同じ、具体的な削除予定日には
    言及しない方針)。"""
    return DELETION_CANDIDATE_FINAL_CONFIRMATION_MESSAGE


# deletion-candidate-unreachable-owner-review-design.mdの「次回候補」であった連絡不能の
# 理由区分(line-reservation-aiフェーズ続き320・aircon-pashaフェーズ313の横展開)。本venture
# も経路判定がis_followingのみに基づくため(route_deletion_candidate_confirmation()参照、
# push送信失敗時は`failed`に積むだけで即時には連絡不能化しない、aircon-pashaと同じ)、
# 理由コードは1種のみで足りる。
UNREACHABLE_REASON_NOT_FOLLOWING = "not_following"

_UNREACHABLE_REASON_LABELS = {
    UNREACHABLE_REASON_NOT_FOLLOWING: "LINE公式アカウントをブロック中",
}
_UNREACHABLE_REASON_UNKNOWN_LABEL = "不明(本フィールド追加前に記録された候補)"


class DeletionCandidateConfirmationRoute(Enum):
    """data-retention-policy.md「削除候補化後の最終確認」節の経路判定結果。"""

    LINE_PUSH = "line_push"
    MARK_UNREACHABLE = "mark_unreachable"


def route_deletion_candidate_confirmation(
    is_following: bool,
) -> DeletionCandidateConfirmationRoute:
    """design記載の経路判定をそのままコード化する。`is_following`がFalse(LINEブロック
    済み)の場合、代替のメール経路は本モジュールでは実装しない(モジュールdocstring
    参照)ため、直ちに「連絡不能」相当のMARK_UNREACHABLEへ倒す。"""
    if is_following:
        return DeletionCandidateConfirmationRoute.LINE_PUSH
    return DeletionCandidateConfirmationRoute.MARK_UNREACHABLE


@dataclass(frozen=True)
class DeletionCandidateConfirmationUserState:
    """本モジュールが参照する、削除候補1件分の状態。

    `user_id`は`deletion_candidate.list_deletion_candidates()`が返す一覧の要素を想定。
    `is_following`はapplication_form_submission_flow.UserProfileStoreProtocol.
    get_is_following()をそのまま反映する。`deletion_confirmation_sent_at`が設定済みの
    場合は最終確認の送達に成功済みのため、再送の対象から除外する(下記select_due参照)。"""

    user_id: str
    is_following: bool
    deletion_confirmation_sent_at: Optional[datetime] = None


def select_due_deletion_candidate_final_confirmations(
    users: Sequence[DeletionCandidateConfirmationUserState],
) -> list[DeletionCandidateConfirmationUserState]:
    """`deletion_confirmation_sent_at`が未設定の候補のみを返す(入力順を維持)。

    一度LINE pushでの最終確認が届いた候補は再送しない。一方、`MARK_UNREACHABLE`に
    倒れた候補(ブロック中で送達できなかった候補)は`deletion_confirmation_sent_at`が
    設定されないため、毎回の実行で対象に残り続ける(ブロック解除〈再フォロー〉後に
    自動的にLINE push経路へ切り替わり、最終確認を送達できる機会を残すための意図的な
    挙動、aircon-pashaの同名関数と同じ設計判断)。
    """
    return [user for user in users if user.deletion_confirmation_sent_at is None]


class DeletionConfirmationStateWriter(Protocol):
    """本モジュールが実際に使う2メソッドのみを要求する最小限のProtocol
    (payment_suspension_owner_notification.PaymentSuspensionOwnerNotifiedAtWriterと
    同じ考え方)。本venture側では`InMemoryProfileDeletionCandidateStore`
    (deletion_candidate.py)がこれを満たす。"""

    def set_deletion_confirmation_sent_at(
        self, user_id: str, value: Optional[datetime]
    ) -> None:
        ...

    def set_deletion_confirmation_unreachable_at(
        self, user_id: str, value: Optional[datetime]
    ) -> None:
        ...

    def set_deletion_confirmation_unreachable_reason(
        self, user_id: str, value: Optional[str]
    ) -> None:
        """line-reservation-aiフェーズ続き320・aircon-pashaフェーズ313が発見した
        「連絡不能の理由が未記録」という既知の限界を受けて追加した書き込みメソッド。
        本venture唯一の連絡不能経路(ブロック中)の理由コードを記録する。"""
        ...


class DeletionConfirmationSentAtReader(Protocol):
    """`build_deletion_candidate_confirmation_states()`が`deletion_confirmation_sent_at`を
    読み取る際に要求する最小限のProtocol(`DeletionConfirmationStateWriter`と対になる
    読み取り側)。"""

    def get_deletion_confirmation_sent_at(self, user_id: str) -> Optional[datetime]:
        ...


class IsFollowingReader(Protocol):
    """`build_deletion_candidate_confirmation_states()`が`is_following`を読み取る際に
    要求する最小限のProtocol。本venture側では`application_form_submission_flow.
    InMemoryUserProfileStore`がこれを満たす。"""

    def get_is_following(self, user_id: str) -> bool:
        ...


def build_deletion_candidate_confirmation_states(
    candidate_user_ids: Sequence[str],
    deletion_store: DeletionConfirmationSentAtReader,
    profile_store: IsFollowingReader,
) -> list[DeletionCandidateConfirmationUserState]:
    """`deletion_candidate.list_deletion_candidates()`が返すuser_id一覧から、
    `deletion_store`の`deletion_confirmation_sent_at`・`profile_store`の`is_following`を
    読み取って`DeletionCandidateConfirmationUserState`一覧を組み立てる(呼び出し順=入力順を
    維持)。本venture固有の2store構成(モジュールdocstring参照)のため、aircon-pashaの
    同名関数と異なり読み取り元を2引数に分けている。"""
    return [
        DeletionCandidateConfirmationUserState(
            user_id=user_id,
            is_following=profile_store.get_is_following(user_id),
            deletion_confirmation_sent_at=deletion_store.get_deletion_confirmation_sent_at(
                user_id
            ),
        )
        for user_id in candidate_user_ids
    ]


@dataclass
class SendDeletionCandidateFinalConfirmationsResult:
    """1回のバッチ実行での処理結果(呼び出し側のログ・監視用、他スケジューラの
    SendResultと対称)。"""

    sent: list[str] = field(default_factory=list)  # LINE push送達成功
    marked_unreachable: list[str] = field(default_factory=list)  # ブロック中、連絡不能扱い
    failed: list[str] = field(default_factory=list)  # push送達失敗(次回起動時に再試行)


def send_deletion_candidate_final_confirmations(
    users: Sequence[DeletionCandidateConfirmationUserState],
    now: datetime,
    state_store: DeletionConfirmationStateWriter,
    push_client: LinePushClient,
) -> SendDeletionCandidateFinalConfirmationsResult:
    """data-retention-policy.md「削除候補化後の最終確認」節の本体。

    引数のusersは呼び出し元でFirestoreから読み取った削除候補一覧
    (`deletion_candidate.list_deletion_candidates()`の結果に`is_following`等を
    付加したもの)を想定し、実際の絞り込みはselect_due_deletion_candidate_final_
    confirmations()が行う。候補ごとにroute_deletion_candidate_confirmation()で
    経路を判定し、LINE_PUSHならプレーンテキスト送信を試みて成功時のみ
    `deletion_confirmation_sent_at`を書き込み、MARK_UNREACHABLEなら送信を試みず
    `deletion_confirmation_unreachable_at`のみ更新する(design「オーナーが対話
    セッションで個別に削除可否を判断する運用」のための状態記録)。
    """
    result = SendDeletionCandidateFinalConfirmationsResult()

    for user in select_due_deletion_candidate_final_confirmations(users):
        route = route_deletion_candidate_confirmation(user.is_following)
        if route is DeletionCandidateConfirmationRoute.MARK_UNREACHABLE:
            state_store.set_deletion_confirmation_unreachable_at(user.user_id, now)
            state_store.set_deletion_confirmation_unreachable_reason(
                user.user_id, UNREACHABLE_REASON_NOT_FOLLOWING
            )
            result.marked_unreachable.append(user.user_id)
            continue

        try:
            push_client.send_message(
                user.user_id, render_deletion_candidate_final_confirmation_message()
            )
        except LinePushDeliveryError:
            result.failed.append(user.user_id)
            continue
        state_store.set_deletion_confirmation_sent_at(user.user_id, now)
        result.sent.append(user.user_id)

    return result


class DeletionCandidateFinalConfirmationStore(
    deletion_candidate.ProfileDeletionCandidateStoreProtocol,
    DeletionConfirmationSentAtReader,
    DeletionConfirmationStateWriter,
    Protocol,
):
    """`run_due_deletion_candidate_final_confirmations()`の`deletion_store`引数が要求する、
    削除候補一覧の取得(`deletion_candidate.list_deletion_candidates()`が要求する既存
    Protocol)・送達状態の読み書き2メソッドを合わせた構造的Protocol。本venture側では
    `InMemoryProfileDeletionCandidateStore`(deletion_candidate.py)が単独でこれを満たす。"""


def run_due_deletion_candidate_final_confirmations(
    deletion_store: DeletionCandidateFinalConfirmationStore,
    profile_store: IsFollowingReader,
    now: datetime,
    push_client: LinePushClient,
) -> SendDeletionCandidateFinalConfirmationsResult:
    """data-retention-policy.md「削除候補化後の最終確認」節が「呼び出し側(Cloud
    Scheduler経由の月次バッチ)が行う想定」としていたstore wiringを実装したもの
    (他venture〈aircon-pasha〉の`run_due_deletion_candidate_final_confirmations()`の
    横展開)。`deletion_candidate.list_deletion_candidates()`で削除候補user_id一覧を取得し、
    `build_deletion_candidate_confirmation_states()`で状態を組み立てた上で
    `send_deletion_candidate_final_confirmations()`に委譲する。実Cloud Scheduler接続・
    実LINE Push API接続・実Firestore接続はいずれも引き続きオーナー承認待ちのため、呼び出し元
    での配線(get_runtime_dependencies()相当への追加)は別途残す。"""
    candidate_user_ids = deletion_candidate.list_deletion_candidates(deletion_store, now)
    states = build_deletion_candidate_confirmation_states(
        candidate_user_ids, deletion_store, profile_store
    )
    return send_deletion_candidate_final_confirmations(
        states, now, deletion_store, push_client
    )


@dataclass(frozen=True)
class UnreachableDeletionCandidate:
    """deletion-candidate-unreachable-owner-review-design.md 4節の読み取り専用レポート行
    (aircon-pashaフェーズ311の横展開)。オーナーが対話セッションで個別に削除可否を判断
    するための一覧表示にのみ使う(削除実行・自動送信は一切行わない)。"""

    user_id: str
    deletion_confirmation_unreachable_at: datetime
    days_since_unreachable: int
    unreachable_reason: Optional[str] = None

    @property
    def unreachable_reason_label(self) -> str:
        """理由コードを対話セッション表示用の日本語ラベルに変換する。本フィールド追加前に
        連絡不能と記録された候補はunreachable_reasonがNoneのままなので、line-reservation-ai
        フェーズ続き320・aircon-pashaフェーズ313と同じ方針で「不明」として表示する。"""
        if self.unreachable_reason is None:
            return _UNREACHABLE_REASON_UNKNOWN_LABEL
        return _UNREACHABLE_REASON_LABELS.get(self.unreachable_reason, self.unreachable_reason)


class UnreachableDeletionCandidateReader(Protocol):
    """`list_unreachable_deletion_candidates()`が要求する最小限のProtocol。本venture側では
    `InMemoryProfileDeletionCandidateStore`(deletion_candidate.py)が既存メソッド
    (`all_user_ids`・`get_deletion_confirmation_unreachable_at`・
    `get_deletion_confirmation_unreachable_reason`)でそのまま構造的に満たす
    (`is_following`等を扱う`profile_store`ではなく、`deletion_store`を渡す想定)。"""

    def all_user_ids(self) -> Iterable[str]:
        ...

    def get_deletion_confirmation_unreachable_at(self, user_id: str) -> Optional[datetime]:
        ...

    def get_deletion_confirmation_unreachable_reason(self, user_id: str) -> Optional[str]:
        ...


def list_unreachable_deletion_candidates(
    store: UnreachableDeletionCandidateReader, now: datetime,
) -> list[UnreachableDeletionCandidate]:
    """deletion-candidate-unreachable-owner-review-design.md 4節の選定ロジック
    (aircon-pashaの同名関数の横展開)。

    `store.all_user_ids()`が返す全user_idのうち、`deletion_confirmation_unreachable_at`
    が設定済みのものをuser_id昇順で一覧化する。本関数は読み取り専用で、削除実行や通知
    送信は行わない。
    """
    candidates = [
        UnreachableDeletionCandidate(
            user_id=user_id,
            deletion_confirmation_unreachable_at=unreachable_at,
            days_since_unreachable=(now - unreachable_at).days,
            unreachable_reason=store.get_deletion_confirmation_unreachable_reason(user_id),
        )
        for user_id in store.all_user_ids()
        if (unreachable_at := store.get_deletion_confirmation_unreachable_at(user_id))
        is not None
    ]
    return sorted(candidates, key=lambda candidate: candidate.user_id)


def render_unreachable_deletion_candidates_report(
    candidates: Sequence[UnreachableDeletionCandidate],
) -> str:
    """deletion-candidate-unreachable-owner-review-design.md 5節のレポート文言
    (aircon-pashaの同名関数と同一の文言方針)。オーナーとの対話セッション内で表示する
    ことを想定し(外部への自動送信は行わない)、自動削除の対象ではないこと・個別判断が
    必要であることを明示する。
    """
    if not candidates:
        return "連絡不能の削除候補ユーザーはいません。"

    lines = [
        f"連絡不能の削除候補ユーザー: {len(candidates)}件(オーナーによる個別確認が必要)",
        "",
    ]
    for candidate in candidates:
        lines.append(
            f"- {candidate.user_id}: 連絡不能判定から{candidate.days_since_unreachable}日経過"
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
    from trial_end_scheduler import InMemoryLinePushClient

    now = datetime(2026, 10, 12, 18, 0, 0)
    users = [
        # 削除候補・フォロー中: LINE pushを試みる
        DeletionCandidateConfirmationUserState(user_id="u1", is_following=True),
        # 削除候補・ブロック中: 連絡不能扱い
        DeletionCandidateConfirmationUserState(user_id="u2", is_following=False),
        # 既に最終確認送達済み: 対象外
        DeletionCandidateConfirmationUserState(
            user_id="u3", is_following=True, deletion_confirmation_sent_at=now
        ),
    ]
    due = select_due_deletion_candidate_final_confirmations(users)
    print([u.user_id for u in due])

    store = deletion_candidate.InMemoryProfileDeletionCandidateStore()
    push = InMemoryLinePushClient()
    result = send_deletion_candidate_final_confirmations(users, now, store, push)
    print(
        f"sent={result.sent}, marked_unreachable={result.marked_unreachable}, "
        f"failed={result.failed}"
    )
    print(f"push count: {len(push.sent)}")


if __name__ == "__main__":
    _demo()
