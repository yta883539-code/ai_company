#!/usr/bin/env python3
"""
stripe-cancellation-deletion-candidate-trigger-design.md(フェーズ91)で設計した、
Stripe解約webhookを起点とする削除候補洗い出しロジックを実行可能なコードに落とし込んだもの。

位置づけ:
- 実際のStripe Webhook受信エンドポイント(署名検証・イベント種別ディスパッチ)自体は
  design 4節「未解決事項」のとおり本ventureにまだ存在せず、実Stripeアカウント接続後の
  課題として引き続き残す。本モジュールはWebhookイベント種別を受け取った"後"に呼ばれる
  中身の判断・データ更新ロジックのみを、実Firestore接続なしで検証可能な純粋関数として
  実装する(user_id_linking.pyのLinkingCodeStoreProtocol/InMemoryLinkingCodeStoreと
  同じ位置づけ)。

設計の参照元: stripe-cancellation-deletion-candidate-trigger-design.md
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable, List, Optional, Protocol

# design 3節: 解約日から削除候補化までの猶予期間(data-retention-policy.mdの保存期間ポリシー)
_DELETION_CANDIDATE_DELAY = timedelta(days=365)


class ProfileDeletionCandidateStoreProtocol(Protocol):
    """`user_profile/{user_id}`ドキュメントのうち`deletion_candidate_at`フィールドのみを
    対象にした薄いインターフェース(design 2節)。他フィールド(gym_area_pairs等)は
    application_form_submission_flow.UserProfileStoreProtocolが別途扱うため、本モジュールは
    関知しない。
    """

    def get_deletion_candidate_at(self, user_id: str) -> Optional[datetime]:
        ...

    def set_deletion_candidate_at(self, user_id: str, value: Optional[datetime]) -> None:
        ...

    def all_user_ids(self) -> Iterable[str]:
        """`list_deletion_candidates()`の走査対象になる全user_idを列挙する。"""
        ...


class InMemoryProfileDeletionCandidateStore:
    """実Firestore接続の代わりにdictで`deletion_candidate_at`フィールドを保持する検証用スタブ。"""

    def __init__(self) -> None:
        self._values: dict[str, Optional[datetime]] = {}

    def get_deletion_candidate_at(self, user_id: str) -> Optional[datetime]:
        return self._values.get(user_id)

    def set_deletion_candidate_at(self, user_id: str, value: Optional[datetime]) -> None:
        if value is None:
            self._values.pop(user_id, None)
        else:
            self._values[user_id] = value

    def all_user_ids(self) -> Iterable[str]:
        return list(self._values.keys())


def mark_deletion_candidate_on_subscription_deleted(
    store: ProfileDeletionCandidateStoreProtocol, user_id: str, event_time: datetime,
) -> datetime:
    """design 3節: `customer.subscription.deleted`受信時に呼ぶ。
    `event_time + 365日`を`deletion_candidate_at`として書き込む(既に設定済みの場合も
    最新の解約日を基準に上書きする、design記載の「安全側」判断)。書き込んだ値を返す。
    """
    deletion_candidate_at = event_time + _DELETION_CANDIDATE_DELAY
    store.set_deletion_candidate_at(user_id, deletion_candidate_at)
    return deletion_candidate_at


def clear_deletion_candidate_on_subscription_reactivated(
    store: ProfileDeletionCandidateStoreProtocol, user_id: str,
) -> bool:
    """design 3節: `customer.subscription.created`、またはstatusが`active`/`trialing`に
    戻った`updated`受信時に呼ぶ。設定済みなら削除し`True`を返す。未設定なら何もせず`False`を
    返す(冪等。design 4節のとおり初回契約時に誤って呼ばれても実害がないことを、この戻り値で
    呼び出し側がログ確認できるようにした)。
    """
    if store.get_deletion_candidate_at(user_id) is None:
        return False
    store.set_deletion_candidate_at(user_id, None)
    return True


def list_deletion_candidates(
    store: ProfileDeletionCandidateStoreProtocol, now: datetime,
) -> List[str]:
    """design 3節: `deletion_candidate_at`が`now`以前に設定されているuser_idの一覧を返す
    (data-retention-policy.md「削除の実行方法(MVP)」の月次バッチから呼ばれる想定の
    読み出し専用関数。削除・通知そのものは行わない)。

    MVPのInMemoryProfileDeletionCandidateStoreでは単純な線形走査で代替する(design 3節の
    「実装時、Firestoreの範囲クエリにそのまま対応させられる形を想定」に沿い、呼び出し側は
    ここが将来クエリに置き換わってもインターフェースを変えずに済む)。結果はuser_id昇順で
    返す(呼び出し順の非決定性を避けるため)。
    """
    return sorted(
        user_id
        for user_id in store.all_user_ids()
        if (candidate_at := store.get_deletion_candidate_at(user_id)) is not None
        and candidate_at <= now
    )
