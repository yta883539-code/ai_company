#!/usr/bin/env python3
"""
stripe-cancellation-deletion-candidate-trigger-design.md(フェーズ123)で設計した、
Stripe解約webhookを起点とする削除候補洗い出しロジックを実行可能なコードに落とし込んだもの。

位置づけ:
- 実際のStripe Webhook受信エンドポイント(署名検証・イベント種別ディスパッチ)自体は
  design 5節「未解決事項・次の課題」のとおり本ventureにまだ存在せず、実Stripeアカウント
  接続後の課題として引き続き残す。本モジュールはWebhookイベント種別を受け取った"後"に
  呼ばれる中身の判断・データ更新ロジックのみを、実Firestore接続なしで検証可能な純粋関数と
  して実装する(user_id_linking.pyのInMemoryの各種ストアと同じ位置づけ)。
- course-set-pasha/prototype/deletion_candidate.py(フェーズ91)と判定ロジックは同一
  (design冒頭のとおり同構成を踏襲)。本venture固有の差異は受信口側(Checkout Session作成時に
  user_idが既知なためcheckout.session.completedの逆引きが不要)にあり、本モジュールが扱う
  customer.subscription.*系イベントの処理自体には差異がない(design 4節)。

設計の参照元: stripe-cancellation-deletion-candidate-trigger-design.md
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable, List, Optional, Protocol

# design 3節: 解約日から削除候補化までの猶予期間(data-retention-policy.mdの保存期間ポリシー)
_DELETION_CANDIDATE_DELAY = timedelta(days=365)


class ProfileDeletionCandidateStoreProtocol(Protocol):
    """`user_profile/{user_id}`ドキュメントのうち`deletion_candidate_at`フィールドのみを
    対象にした薄いインターフェース(design 2節)。他フィールド(business_name・
    current_plan_id等、user-account-linking-design.md 5節のスキーマ)は
    user_id_linking.pyが別途扱うため、本モジュールは関知しない。
    """

    def get_deletion_candidate_at(self, user_id: str) -> Optional[datetime]:
        ...

    def set_deletion_candidate_at(self, user_id: str, value: Optional[datetime]) -> None:
        ...

    def all_user_ids(self) -> Iterable[str]:
        """`list_deletion_candidates()`の走査対象になる全user_idを列挙する。"""
        ...

    def get_deletion_candidate_state_event_time(self, user_id: str) -> Optional[datetime]:
        """subscription-event-out-of-order-guard-design.md(本フェーズ)対応。
        `deletion_candidate_at`を最後に実際に反映した(mark/clearを問わない)イベントの
        `event.created`を返す。未反映(呼び出し自体が一度もない)ならNone。"""
        ...

    def set_deletion_candidate_state_event_time(self, user_id: str, value: datetime) -> None:
        ...


class InMemoryProfileDeletionCandidateStore:
    """実Firestore接続の代わりにdictで`deletion_candidate_at`フィールドを保持する検証用スタブ。"""

    def __init__(self) -> None:
        self._values: dict[str, Optional[datetime]] = {}
        self._state_event_times: dict[str, datetime] = {}

    def get_deletion_candidate_at(self, user_id: str) -> Optional[datetime]:
        return self._values.get(user_id)

    def set_deletion_candidate_at(self, user_id: str, value: Optional[datetime]) -> None:
        if value is None:
            self._values.pop(user_id, None)
        else:
            self._values[user_id] = value

    def all_user_ids(self) -> Iterable[str]:
        return list(self._values.keys())

    def get_deletion_candidate_state_event_time(self, user_id: str) -> Optional[datetime]:
        return self._state_event_times.get(user_id)

    def set_deletion_candidate_state_event_time(self, user_id: str, value: datetime) -> None:
        self._state_event_times[user_id] = value


def _is_stale_deletion_candidate_event(
    store: ProfileDeletionCandidateStoreProtocol, user_id: str, event_time: Optional[datetime],
) -> bool:
    """subscription-event-out-of-order-guard-design.md(本フェーズ)対応。今回のイベントより
    後の時刻のイベントが既に反映済みなら`True`(stale、適用をスキップすべき)を返す。
    `event_time`が渡されない(呼び出し側が未対応)、または`store`が
    `get_deletion_candidate_state_event_time`に対応していない場合は判定不能として常に
    `False`を返す(従来通り適用する、既存呼び出し経路・テストとの後方互換)。"""
    if event_time is None:
        return False
    getter = getattr(store, "get_deletion_candidate_state_event_time", None)
    if getter is None:
        return False
    recorded_event_time = getter(user_id)
    if recorded_event_time is None:
        return False
    return event_time <= recorded_event_time


def _record_deletion_candidate_state_event_time(
    store: ProfileDeletionCandidateStoreProtocol, user_id: str, event_time: Optional[datetime],
) -> None:
    if event_time is None:
        return
    setter = getattr(store, "set_deletion_candidate_state_event_time", None)
    if setter is None:
        return
    setter(user_id, event_time)


def mark_deletion_candidate_on_subscription_deleted(
    store: ProfileDeletionCandidateStoreProtocol, user_id: str, event_time: datetime,
) -> Optional[datetime]:
    """design 3節: `customer.subscription.deleted`受信時(stripe_customer_id →
    user_idの逆引き後)に呼ぶ。`event_time + 365日`を`deletion_candidate_at`として
    書き込む(既に設定済みの場合も最新の解約日を基準に上書きする、design記載の
    「安全側」判断)。書き込んだ値を返す。

    subscription-event-out-of-order-guard-design.md(本フェーズ)対応: `event_time`が、
    既に反映済みのより新しいイベントの時刻以前(stale)であれば書き込みをスキップし、
    現在store上の値をそのまま返す(解約→即再契約のケースで、Webhookリトライにより遅延
    した古いdeletedイベントが新しいcreatedの反映を上書きしてしまうのを防ぐ)。
    """
    if _is_stale_deletion_candidate_event(store, user_id, event_time):
        return store.get_deletion_candidate_at(user_id)
    deletion_candidate_at = event_time + _DELETION_CANDIDATE_DELAY
    store.set_deletion_candidate_at(user_id, deletion_candidate_at)
    _record_deletion_candidate_state_event_time(store, user_id, event_time)
    return deletion_candidate_at


def clear_deletion_candidate_on_subscription_reactivated(
    store: ProfileDeletionCandidateStoreProtocol,
    user_id: str,
    event_time: Optional[datetime] = None,
) -> bool:
    """design 3節: `customer.subscription.created`、またはstatusが`active`/`trialing`に
    戻った`updated`受信時(逆引き後)に呼ぶ。設定済みなら削除し`True`を返す。未設定なら
    何もせず`False`を返す(冪等。design 5節のとおり初回契約時に誤って呼ばれても実害が
    ないことを、この戻り値で呼び出し側がログ確認できるようにした)。

    subscription-event-out-of-order-guard-design.md(本フェーズ)対応: `event_time`を
    渡した場合、既に反映済みのより新しいイベントの時刻以前(stale)であれば削除をスキップし
    `False`を返す(初回createdのリトライが、後続のdeletedより後に届き誤って削除候補を
    消してしまうのを防ぐ)。`event_time`省略時は従来通りの無条件クリアとして扱う
    (既存呼び出し経路・テストとの後方互換)。
    """
    if _is_stale_deletion_candidate_event(store, user_id, event_time):
        return False
    if store.get_deletion_candidate_at(user_id) is None:
        _record_deletion_candidate_state_event_time(store, user_id, event_time)
        return False
    store.set_deletion_candidate_at(user_id, None)
    _record_deletion_candidate_state_event_time(store, user_id, event_time)
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
