#!/usr/bin/env python3
"""
data-retention-policy.md「削除候補化後の最終確認」節で方針のみ整理していた、削除候補
(`deletion_candidate.list_deletion_candidates()`が返すuser_id一覧)に対する最終確認の
判定・送信ロジックを、実行可能なコードに落とし込んだもの。

位置づけ:
- data-retention-policy.mdは最終確認の経路を「主経路: LINE公式アカウントからのpush送信
  (ただしブロック済みの場合は送達できない)」「代替経路: 申込フォームで収集したemailに
  よる送信(実際の送信には送信用サービスのアカウント作成が必要でオーナー承認待ち)」の
  2段構成としていた。本モジュールは主経路(LINE push)のみを実装対象とし、代替経路
  (実メール送信)は同ドキュメントの記載どおり引き続きオーナー承認待ちの範囲として
  一切実装しない(新規の承認待ち事項ではない、既存記載の範囲)。
- follow-unfollow-event-handling-design.md・blocked-but-billing-detection-design.md
  (フェーズ167)で`user_profile.is_following`が既に追跡されているため、本モジュールは
  それを読み取るだけで「LINE pushが送達できるか」を判定できる(design記載の「ブロック
  済みの場合は送達できない」をそのままコード化)。
- `is_following=False`(ブロック済み、代替のメール経路は上記のとおり承認待ちで未実装)の
  場合、data-retention-policy.mdの「連絡不能」フラグに相当する状態として
  `deletion_confirmation_unreachable_at`を記録するのみに留め、削除そのものへは一切
  進めない(design「連絡不能ケースは自動削除には進まず(中略)オーナーが対話セッションで
  個別に削除可否を判断する運用とする」をそのままコード化)。
- 対象を絞り込むためのuser_id一覧(`list_deletion_candidates()`の戻り値)・`is_following`
  の実際の読み取りはいずれも呼び出し側(Cloud Scheduler経由の月次バッチ、design「削除の
  実行方法(MVP)」)が行う想定で、本モジュールはFirestore等への実接続なしで検証可能な
  純粋関数のみを提供する(他スケジューラ・通知モジュールと同じ位置づけ)。
- `LinePushClient`・`LinePushDeliveryError`はtrial_end_scheduler.pyで既に定義済みの
  ものをそのまま再利用する(payment_suspension_owner_notification.py・
  blocked_but_billing_owner_notification.pyと同じ方針、本モジュールで重複定義しない)。
- `run_due_deletion_candidate_final_confirmations()`(フェーズ307で追加)は、上記で
  「呼び出し側が行う想定」としていたstore wiring(`deletion_candidate.list_deletion_
  candidates()`で削除候補user_id一覧を取得し、各user_idの`is_following`・
  `deletion_confirmation_sent_at`を読み取ってDeletionCandidateConfirmationUserStateを
  組み立てる処理)を実装したもの。`user_id_linking.UserProfile`に対応する
  `deletion_confirmation_sent_at`・`deletion_confirmation_unreachable_at`の2フィールドが
  フェーズ307で追加され、`InMemoryUserProfileStore`が`DeletionConfirmationStateWriter`を
  構造的に満たすようになったため、実Cloud Scheduler接続自体はオーナー承認待ちのままだが、
  実行可能な1本の関数として検証できる状態になった(他スケジューラの`send_*`本体と同じ、
  実クラウド接続なしで検証可能な構成)。

設計の参照元: data-retention-policy.md「削除候補化後の最終確認」節,
deletion_candidate.py, follow-unfollow-event-handling-design.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Protocol, Sequence

import deletion_candidate
from trial_end_scheduler import LinePushClient, LinePushDeliveryError

DELETION_CANDIDATE_FINAL_CONFIRMATION_ALT_TEXT = (
    "【エアコンパシャッと】データ保有についてのご案内"
)

# design「削除候補化後の最終確認」節。実際の削除実行バッチ(Cloud Scheduler、実装自体は
# オーナー承認待ち)がまだ存在しないため、具体的な削除予定日には言及せず、保存期間
# ポリシーに基づく取り扱いを案内するに留める(実装が追いつく前に案内内容が先行しない
# ようにするための、本フェーズでの意図的な書き方)。
DELETION_CANDIDATE_FINAL_CONFIRMATION_MESSAGE = (
    "ご契約終了から一定期間が経過したため、プライバシーポリシーに基づき、"
    "お預かりしている情報(屋号・メールアドレス等)の保有継続について確認の"
    "ご連絡です。\n"
    "\n"
    "引き続き保有をご希望の場合や、サービスの再開をご希望の場合は、このメッセージへの"
    "ご返信、または改めてのお申し込みにてご連絡ください。\n"
    "特にご連絡がない場合、当社の定めるデータ保存期間ポリシーに従って取り扱います。"
)


def render_deletion_candidate_final_confirmation_message() -> str:
    """文言をそのまま返す(日付・URL等の差し込みが無いため引数なし、design記載の
    「具体的な削除予定日には言及しない」方針に合わせている)。"""
    return DELETION_CANDIDATE_FINAL_CONFIRMATION_MESSAGE


def build_deletion_candidate_final_confirmation_flex_message() -> dict:
    """subscription_cancellation_notification._build_flex_message()と同じ、ボタンを
    持たないテキストのみのbubble形式(design記載のとおりCTAリンクを持たない案内文の
    ため、他モジュールのようなFlexボタンは付けない)。"""
    return {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": render_deletion_candidate_final_confirmation_message(),
                    "wrap": True,
                },
            ],
        },
    }


# deletion-candidate-unreachable-owner-review-design.mdの「次回候補」であった連絡不能の
# 理由区分(line-reservation-aiフェーズ続き320の横展開)。本ventureは経路判定が
# is_followingのみに基づくため(モジュールdocstring参照、push送信失敗時は即時には連絡不能
# 化しない)、理由コードは1種のみで足りる。
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
    `is_following`はuser_id_linking.UserProfile.is_followingをそのまま反映する。
    `deletion_confirmation_sent_at`が設定済みの場合は最終確認の送達に成功済みのため、
    再送の対象から除外する(下記select_due参照)。"""

    user_id: str
    is_following: bool
    deletion_confirmation_sent_at: Optional[datetime] = None


def select_due_deletion_candidate_final_confirmations(
    users: Sequence[DeletionCandidateConfirmationUserState],
) -> list[DeletionCandidateConfirmationUserState]:
    """`deletion_confirmation_sent_at`が未設定の候補のみを返す(入力順を維持)。

    一度LINE pushでの最終確認が届いた候補は再送しない。一方、`MARK_UNREACHABLE`に
    倒れた候補(ブロック中で送達できなかった候補)は`deletion_confirmation_sent_at`が
    設定されないため、毎回の実行で対象に残り続ける。これは意図的な挙動で、ブロック
    解除(再フォロー)後に自動的にLINE push経路へ切り替わり、最終確認を送達できる
    機会を残すため(design「削除候補化後の最終確認」節に明示のフォールバック経路の
    切り替えはないが、is_followingの変化に追随できる設計の方が安全側と判断した)。
    """
    return [user for user in users if user.deletion_confirmation_sent_at is None]


class DeletionConfirmationStateWriter(Protocol):
    """user_id_linking.UserProfileStoreProtocolを直接拡張せず、本モジュールが実際に
    使う2メソッドのみを要求する最小限のProtocol(payment_suspension_owner_
    notification.PaymentSuspensionOwnerNotifiedAtWriterと同じ考え方)。"""

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
        """line-reservation-aiフェーズ続き320が発見した3venture共通の既知の限界
        (連絡不能の理由が未記録)を受けて追加した書き込みメソッド。本venture唯一の
        連絡不能経路(ブロック中)の理由コードを記録する。"""
        ...


class DeletionCandidateConfirmationStateReader(Protocol):
    """フェーズ307: `build_deletion_candidate_confirmation_states()`が削除候補user_idから
    `DeletionCandidateConfirmationUserState`を組み立てる際に読み取る2メソッドのみを要求する
    最小限のProtocol(`DeletionConfirmationStateWriter`と対になる読み取り側)。"""

    def get_is_following(self, user_id: str) -> bool:
        ...

    def get_deletion_confirmation_sent_at(self, user_id: str) -> Optional[datetime]:
        ...


def build_deletion_candidate_confirmation_states(
    candidate_user_ids: Sequence[str],
    store: DeletionCandidateConfirmationStateReader,
) -> list[DeletionCandidateConfirmationUserState]:
    """`deletion_candidate.list_deletion_candidates()`が返すuser_id一覧から、
    `store`の`is_following`・`deletion_confirmation_sent_at`を読み取って
    `DeletionCandidateConfirmationUserState`一覧を組み立てる(呼び出し順=入力順を維持)。"""
    return [
        DeletionCandidateConfirmationUserState(
            user_id=user_id,
            is_following=store.get_is_following(user_id),
            deletion_confirmation_sent_at=store.get_deletion_confirmation_sent_at(user_id),
        )
        for user_id in candidate_user_ids
    ]


class DeletionCandidateFinalConfirmationStore(
    DeletionCandidateConfirmationStateReader,
    DeletionConfirmationStateWriter,
    Protocol,
):
    """フェーズ307: `run_due_deletion_candidate_final_confirmations()`が要求する、
    読み取り2メソッド・書き込み2メソッドを合わせた構造的Protocol。
    `deletion_candidate.ProfileDeletionCandidateStoreProtocol`(`all_user_ids`・
    `get_deletion_candidate_at`)は`deletion_candidate.list_deletion_candidates()`が
    別途要求するため、ここには含めない(呼び出し元で`store`を1つ渡せば両方を
    構造的に満たす、`InMemoryUserProfileStore`が想定する使い方)。"""


def run_due_deletion_candidate_final_confirmations(
    store: DeletionCandidateFinalConfirmationStore,
    now: datetime,
    push_client: LinePushClient,
) -> "SendDeletionCandidateFinalConfirmationsResult":
    """data-retention-policy.md「削除候補化後の最終確認」節が「呼び出し側(Cloud
    Scheduler経由の月次バッチ)が行う想定」としていたstore wiringを実装したもの
    (フェーズ307)。`deletion_candidate.list_deletion_candidates()`で削除候補user_id
    一覧を取得し、`build_deletion_candidate_confirmation_states()`で状態を組み立てた上で
    `send_deletion_candidate_final_confirmations()`に委譲する。実Cloud Scheduler接続・
    実LINE Push API接続はいずれも引き続きオーナー承認待ちのため、呼び出し元での配線
    (get_runtime_dependencies()相当への追加)は別途残す。"""
    candidate_user_ids = deletion_candidate.list_deletion_candidates(store, now)
    states = build_deletion_candidate_confirmation_states(candidate_user_ids, store)
    return send_deletion_candidate_final_confirmations(states, now, store, push_client)


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
    経路を判定し、LINE_PUSHならFlex Message送信を試みて成功時のみ
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
            push_client.send_flex_message(
                user.user_id,
                DELETION_CANDIDATE_FINAL_CONFIRMATION_ALT_TEXT,
                build_deletion_candidate_final_confirmation_flex_message(),
            )
        except LinePushDeliveryError:
            result.failed.append(user.user_id)
            continue
        state_store.set_deletion_confirmation_sent_at(user.user_id, now)
        result.sent.append(user.user_id)

    return result


@dataclass(frozen=True)
class UnreachableDeletionCandidate:
    """deletion-candidate-unreachable-owner-review-design.md 4節の読み取り専用レポート行。
    オーナーが対話セッションで個別に削除可否を判断するための一覧表示にのみ使う
    (削除実行・自動送信は一切行わない)。"""

    user_id: str
    deletion_confirmation_unreachable_at: datetime
    days_since_unreachable: int
    unreachable_reason: Optional[str] = None

    @property
    def unreachable_reason_label(self) -> str:
        """理由コードを対話セッション表示用の日本語ラベルに変換する。本フィールド追加前に
        連絡不能と記録された候補はunreachable_reasonがNoneのままなので、line-reservation-ai
        フェーズ続き320と同じ方針で「不明」として表示する。"""
        if self.unreachable_reason is None:
            return _UNREACHABLE_REASON_UNKNOWN_LABEL
        return _UNREACHABLE_REASON_LABELS.get(self.unreachable_reason, self.unreachable_reason)


class UnreachableDeletionCandidateReader(Protocol):
    """`list_unreachable_deletion_candidates()`が要求する最小限のProtocol。
    `InMemoryUserProfileStore`は既存メソッド(`all_user_ids`・
    `get_deletion_confirmation_unreachable_at`・
    `get_deletion_confirmation_unreachable_reason`)でそのまま構造的に満たす。"""

    def all_user_ids(self) -> "Iterable[str]":
        ...

    def get_deletion_confirmation_unreachable_at(self, user_id: str) -> Optional[datetime]:
        ...

    def get_deletion_confirmation_unreachable_reason(self, user_id: str) -> Optional[str]:
        ...


def list_unreachable_deletion_candidates(
    store: UnreachableDeletionCandidateReader, now: datetime,
) -> list[UnreachableDeletionCandidate]:
    """deletion-candidate-unreachable-owner-review-design.md 4節の選定ロジック。

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
    """deletion-candidate-unreachable-owner-review-design.md 5節のレポート文言。
    オーナーとの対話セッション内で表示することを想定し(外部への自動送信は行わない)、
    自動削除の対象ではないこと・個別判断が必要であることを明示する。
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

    now = datetime(2026, 9, 27, 4, 0, 0)
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

    class _StateStoreStub:
        def __init__(self) -> None:
            self.sent_at: dict[str, Optional[datetime]] = {}
            self.unreachable_at: dict[str, Optional[datetime]] = {}
            self.unreachable_reason: dict[str, Optional[str]] = {}

        def set_deletion_confirmation_sent_at(
            self, user_id: str, value: Optional[datetime]
        ) -> None:
            self.sent_at[user_id] = value

        def set_deletion_confirmation_unreachable_at(
            self, user_id: str, value: Optional[datetime]
        ) -> None:
            self.unreachable_at[user_id] = value

        def set_deletion_confirmation_unreachable_reason(
            self, user_id: str, value: Optional[str]
        ) -> None:
            self.unreachable_reason[user_id] = value

    store = _StateStoreStub()
    push = InMemoryLinePushClient()
    result = send_deletion_candidate_final_confirmations(users, now, store, push)
    print(f"sent={result.sent}, marked_unreachable={result.marked_unreachable}, failed={result.failed}")
    print(f"push count: {len(push.sent)}")


if __name__ == "__main__":
    _demo()
