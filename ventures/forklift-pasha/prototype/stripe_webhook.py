#!/usr/bin/env python3
"""Stripe Webhookの署名検証・HTTPエントリポイント(stripe-webhook-entry-point-design.md
フェーズ127)。

実Stripeアカウント接続(オーナー承認待ち)なしでも検証できる、`Stripe-Signature`ヘッダの
検証ロジックと`checkout.session.completed`受信時の紐付け処理のみを切り出したモジュール
(aircon-pasha/course-set-pashaのprototype/stripe_webhook.pyと同じ位置づけ)。

フェーズ127時点では`checkout.session.completed`の受信・署名検証のみに限定していたが、
フェーズ128で`customer.subscription.updated`受信時のplan_id同期
(`handle_customer_subscription_updated()`、stripe-subscription-updated-dispatch-
design.md)を追加し、フェーズ129で`customer.subscription.deleted`受信時の
`canceled_at`書き込み(`handle_customer_subscription_deleted()`、
subscription-canceled-immediate-block-design.md相当)を追加した。フェーズ130で
`customer.subscription.created`(再契約)受信時の`canceled_at`クリア
(`handle_customer_subscription_created()`)を追加し、解約済みユーザーが再契約しても
永久ブロックされたままになる欠落を解消した。フェーズ167で`invoice.payment_failed`/
`invoice.payment_succeeded`受信時の決済失敗検知・復旧クリア(`payment_failure.py`、
payment-failure-dunning-design.md)を追加した。解約完了案内の送信等はまだ一切存在
しないため、それ以外のイベント種別は常に200(受理・無視)を返す。

フェーズ215で`event_id_store`(stripe-event-idempotency-design.md、kura-pashaの
横断棚卸しで発見)を追加した。Stripeは同一イベントを複数回配信することがある
(at least once配信)が、本venture唯一の非べき等な副作用である
`handle_invoice_payment_failed()`の`payment_failure_detected_at`上書きは、従来
`receive_stripe_webhook()`に重複排除の仕組みが一切なく、同一の`invoice.payment_failed`
が再配信されるたびに猶予期間の起算点が後ろへずれ続ける欠落があった(aircon-pasha
フェーズ177・kura-pashaフェーズ77と同型)。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from payment_failure import (
    clear_payment_failure_on_success,
    classify_payment_recovery,
    mark_payment_failure_detected,
)
from plan_id_resolution import (
    sync_plan_id_on_subscription_event,
    write_plan_id_from_checkout_session_metadata,
)
from trial_management import FleetOperatorStoreProtocol, InMemoryFleetOperatorStore


class StripeEventIdStoreProtocol:
    """stripe-event-idempotency-design.md 2節: `event.id`単位の処理済み記録を保持する
    ストアのインターフェース(aircon-pasha/kura-pashaと同一設計)。`internal_id`単位の
    `FleetOperatorStoreProtocol`とはキーの性質が異なるため独立させた。"""

    def has_processed(self, event_id: str) -> bool:
        raise NotImplementedError

    def mark_processed(self, event_id: str) -> None:
        raise NotImplementedError


class InMemoryStripeEventIdStore:
    """design 3節: 検証用のインメモリ実装。プロセス起動ごとに初期化されるため、実Cloud
    Functions環境では呼び出しをまたいで保持されない(他venture・既存の各種InMemoryストアと
    同じ既知の限界)。"""

    def __init__(self) -> None:
        self._processed_event_ids: set = set()

    def has_processed(self, event_id: str) -> bool:
        return event_id in self._processed_event_ids

    def mark_processed(self, event_id: str) -> None:
        self._processed_event_ids.add(event_id)


def verify_stripe_signature(
    payload: bytes,
    sig_header: Optional[str],
    webhook_secret: str,
    *,
    tolerance_seconds: int = 300,
    now: Optional[float] = None,
) -> bool:
    """`Stripe-Signature`ヘッダを検証する(aircon-pasha/course-set-pashaの
    verify_stripe_signature()と同一のアルゴリズム、design 2節)。

    - `sig_header`が無い/空文字列、または`t`・`v1`を含まない不正な形式なら`False`。
    - `v1`が複数含まれる場合(シークレットローテーション中)、いずれか1つでも一致すれば
      検証成功とする。`v0`(旧方式)は一切参照しない。
    - 署名が一致してもタイムスタンプが`tolerance_seconds`(デフォルト300秒)の許容範囲外
      なら`False`とする(リプレイ攻撃対策)。
    """
    if not sig_header:
        return False

    timestamp: Optional[str] = None
    v1_signatures: List[str] = []
    for item in sig_header.split(","):
        if "=" not in item:
            continue
        key, _, value = item.partition("=")
        key = key.strip()
        value = value.strip()
        if key == "t":
            timestamp = value
        elif key == "v1":
            v1_signatures.append(value)

    if timestamp is None or not v1_signatures:
        return False

    try:
        timestamp_int = int(timestamp)
    except ValueError:
        return False

    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    expected = hmac.new(
        webhook_secret.encode("utf-8"), signed_payload, hashlib.sha256
    ).hexdigest()

    signature_matches = any(
        hmac.compare_digest(expected, candidate) for candidate in v1_signatures
    )
    if not signature_matches:
        return False

    resolved_now = now if now is not None else time.time()
    if abs(resolved_now - timestamp_int) > tolerance_seconds:
        return False

    return True


def _is_stale_checkout_session_completed_event(
    store: FleetOperatorStoreProtocol,
    internal_id: str,
    event_time: Optional[datetime],
) -> bool:
    """checkout-session-completed-event-order-guard-design.md(aircon-pashaフェーズ287・
    kura-pashaの横展開、本ventureはフェーズ213で追加)。`event_time`が`None`、または
    `store`が新メソッド未対応、または記録済みevent_timeが未設定の場合は「判定不能」として
    `False`(常に適用、既存事業者への後方互換)。今回のevent_timeが記録済みのevent_time
    「以下」であれば`True`(stale、同時刻は既に処理済みとして再適用しない)。"""
    if event_time is None:
        return False
    getter = getattr(store, "get_checkout_session_completed_event_time", None)
    if getter is None:
        return False
    recorded = getter(internal_id)
    if recorded is None:
        return False
    return event_time <= recorded


def _record_checkout_session_completed_event_time(
    store: FleetOperatorStoreProtocol,
    internal_id: str,
    event_time: Optional[datetime],
) -> None:
    """同上。`event_time`が`None`、または`store`が新メソッド未対応の場合は何もしない。"""
    if event_time is None:
        return
    setter = getattr(store, "set_checkout_session_completed_event_time", None)
    if setter is None:
        return
    setter(internal_id, event_time)


@dataclass
class CheckoutSessionLinkResult:
    """handle_checkout_session_completed()の結果(design 3節)。"""

    linked: bool
    internal_id: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    error: Optional[str] = None
    plan_id_written: bool = False
    upgraded_at_written: bool = False
    stale: bool = False


def handle_checkout_session_completed(
    event: dict,
    store: FleetOperatorStoreProtocol,
    *,
    now: Optional[datetime] = None,
    event_time: Optional[datetime] = None,
) -> CheckoutSessionLinkResult:
    """`checkout.session.completed`イベントから`client_reference_id`(= `internal_id`、
    checkout_session.build_checkout_session_params()が設定した値)・`customer`
    (= `stripe_customer_id`)・`metadata.plan`を取り出し、`store`へ書き込む
    (stripe-webhook-entry-point-design.md 3節)。

    aircon-pashaと異なり、対応する`fleet_operator`の事前存在チェックは行わない
    (design 3節「本venture固有の設計判断」参照)。`internal_id`・`stripe_customer_id`の
    いずれかが欠落・非文字列・空文字列の場合のみ異常系として書き込みを行わない。

    (フェーズ213、checkout-session-completed-event-order-guard-design.md)
    `stripe_customer_id`の書き込みは`event_time`ベースの配信順序入れ替わりガードの対象で、
    記録済みの`checkout_session_completed_event_time`以下(同時刻含む)の場合はスキップし
    `stale=True`を返す(`plan_id`・`upgraded_at`は従来通りガード対象外、`upgraded_at`は
    「一度きり」判定を維持)。`event_time`省略時・store未対応・未記録時は従来通り無条件
    適用する(他ガードと同じ後方互換)。
    """
    data_object = event.get("data", {}).get("object", {})
    internal_id = data_object.get("client_reference_id")
    stripe_customer_id = data_object.get("customer")

    if (
        not isinstance(internal_id, str)
        or not internal_id
        or not isinstance(stripe_customer_id, str)
        or not stripe_customer_id
    ):
        return CheckoutSessionLinkResult(linked=False, error="missing_fields")

    stale = _is_stale_checkout_session_completed_event(store, internal_id, event_time)
    if not stale:
        store.set_stripe_customer_id(internal_id, stripe_customer_id)
        _record_checkout_session_completed_event_time(store, internal_id, event_time)

    plan_id_written = write_plan_id_from_checkout_session_metadata(
        store, internal_id, data_object.get("metadata", {})
    )

    upgraded_at_written = False
    if store.get_upgraded_at(internal_id) is None:
        resolved_now = now if now is not None else datetime.now(timezone.utc)
        store.set_upgraded_at(internal_id, resolved_now)
        upgraded_at_written = True

    return CheckoutSessionLinkResult(
        linked=True,
        internal_id=internal_id,
        stripe_customer_id=stripe_customer_id,
        plan_id_written=plan_id_written,
        upgraded_at_written=upgraded_at_written,
        stale=stale,
    )


@dataclass
class SubscriptionUpdatedSyncResult:
    """handle_customer_subscription_updated()の結果
    (stripe-subscription-updated-dispatch-design.md 2節)。"""

    synced: bool
    internal_id: Optional[str] = None
    plan_id_written: bool = False
    error: Optional[str] = None
    stale: bool = False


def _event_time_from_created(event: dict) -> Optional[datetime]:
    """イベント全体のトップレベル`created`(Unixタイムスタンプ)を`datetime`へ変換する
    (subscription-updated-event-order-guard-design.md、kura-pashaフェーズ194の
    `_event_time_from_created()`と同一の変換ルール)。欠落・非数値の場合は`None`
    (判定不能として常に適用、後方互換)。"""
    created = event.get("created")
    if not isinstance(created, (int, float)):
        return None
    return datetime.fromtimestamp(created, tz=timezone.utc)


def _is_stale_subscription_updated_event(
    store: FleetOperatorStoreProtocol,
    internal_id: str,
    event_time: Optional[datetime],
) -> bool:
    """subscription-updated-event-order-guard-design.md(kura-pashaフェーズ198・
    course-set-pasha/line-reservation-aiの横展開、本venture分)。`event_time`が
    `None`、または`store`が新メソッド未対応、または記録済みevent_timeが未設定の場合は
    「判定不能」として`False`(常に適用、既存事業者への後方互換)。今回のevent_timeが
    記録済みのevent_time「以下」であれば`True`(stale、同時刻は既に処理済みとして
    再適用しない)。"""
    if event_time is None:
        return False
    getter = getattr(store, "get_subscription_updated_event_time", None)
    if getter is None:
        return False
    recorded = getter(internal_id)
    if recorded is None:
        return False
    return event_time <= recorded


def _record_subscription_updated_event_time(
    store: FleetOperatorStoreProtocol,
    internal_id: str,
    event_time: Optional[datetime],
) -> None:
    """同上。`event_time`が`None`、または`store`が新メソッド未対応の場合は何もしない。"""
    if event_time is None:
        return
    setter = getattr(store, "set_subscription_updated_event_time", None)
    if setter is None:
        return
    setter(internal_id, event_time)


def handle_customer_subscription_updated(
    event: dict,
    store: FleetOperatorStoreProtocol,
    event_time: Optional[datetime] = None,
) -> SubscriptionUpdatedSyncResult:
    """`customer.subscription.updated`イベントからplan_idの同期のみを行う
    (stripe-subscription-updated-dispatch-design.md 2節)。

    `customer`(= `stripe_customer_id`)を取り出し、
    `store.get_internal_id_by_stripe_customer_id()`で`internal_id`を逆引きする
    (checkout.session.completed受信時にstripe_webhook.handle_checkout_session_completed()
    が書き込んだ逆引きインデックスに依存する)。逆引きできない場合(未知の
    stripe_customer_id、または本venture未着手のCustomer Portal経由のプラン変更以外の
    経路で作成されたcustomer)は`error="unknown_customer"`として同期を行わない。

    `event_time`(subscription-updated-event-order-guard-design.md、kura-pashaフェーズ
    198・course-set-pasha/line-reservation-aiの横展開として本フェーズで追加)は、Stripe
    カスタマーポータル経由で短期間に複数回プラン変更が行われた場合の遅延配信対策。
    記録済みのevent_time「以下」のevent_timeが渡された場合、plan_id同期を一切行わず
    `stale=True`を返す(他venture同様「stale全体スキップ」方針)。stale判定を通過した
    場合はplan_id同期の成否にかかわらずevent_timeを記録する(course-set-pashaの
    `_record_subscription_updated_event_time()`と同じ「結果にかかわらず記録」方針)。
    `event_time`省略時(`None`)は従来通りこのチェック・記録のいずれも行わない
    (既存呼び出し経路への後方互換措置)。

    plan_idの解決・差分書き込み自体は`plan_id_resolution.sync_plan_id_on_subscription_
    event()`にそのまま委譲する(lookup_keyが未知・欠落、または既存値と同一の場合は
    `plan_id_written=False`)。
    """
    data_object = event.get("data", {}).get("object", {})
    stripe_customer_id = data_object.get("customer")

    if not isinstance(stripe_customer_id, str) or not stripe_customer_id:
        return SubscriptionUpdatedSyncResult(synced=False, error="missing_customer")

    internal_id = store.get_internal_id_by_stripe_customer_id(stripe_customer_id)
    if internal_id is None:
        return SubscriptionUpdatedSyncResult(synced=False, error="unknown_customer")

    if _is_stale_subscription_updated_event(store, internal_id, event_time):
        return SubscriptionUpdatedSyncResult(
            synced=False, internal_id=internal_id, error="stale_event", stale=True
        )

    plan_id_written = sync_plan_id_on_subscription_event(store, internal_id, data_object)
    _record_subscription_updated_event_time(store, internal_id, event_time)

    return SubscriptionUpdatedSyncResult(
        synced=True, internal_id=internal_id, plan_id_written=plan_id_written
    )


def _is_stale_subscription_lifecycle_event(
    store: FleetOperatorStoreProtocol,
    internal_id: str,
    event_time: Optional[datetime],
) -> bool:
    """subscription-lifecycle-event-order-guard-design.md(フェーズ214、フェーズ213
    次回候補(1))。`customer.subscription.deleted`と`customer.subscription.created`は
    どちらも`canceled_at`を書き換えるため、同一の`subscription_lifecycle_event_time`を
    共有キーとして判定する(解約直後の再契約で配信順序が入れ替わり、古い`deleted`が
    新しい`created`より後に届いた場合でも、再契約を表す新しい方のevent_timeが既に
    記録されていればこの古い`deleted`をstaleとして無視できるようにするため)。
    `event_time`が`None`、または`store`が新メソッド未対応、または記録済みevent_timeが
    未設定の場合は「判定不能」として`False`(常に適用、既存事業者への後方互換)。
    今回のevent_timeが記録済みのevent_time「以下」であればTrue(stale)。"""
    if event_time is None:
        return False
    getter = getattr(store, "get_subscription_lifecycle_event_time", None)
    if getter is None:
        return False
    recorded = getter(internal_id)
    if recorded is None:
        return False
    return event_time <= recorded


def _record_subscription_lifecycle_event_time(
    store: FleetOperatorStoreProtocol,
    internal_id: str,
    event_time: Optional[datetime],
) -> None:
    """同上。`event_time`が`None`、または`store`が新メソッド未対応の場合は何もしない。"""
    if event_time is None:
        return
    setter = getattr(store, "set_subscription_lifecycle_event_time", None)
    if setter is None:
        return
    setter(internal_id, event_time)


@dataclass
class SubscriptionDeletedResult:
    """handle_customer_subscription_deleted()の結果
    (subscription-canceled-immediate-block-design.md相当、フェーズ129)。"""

    canceled: bool
    internal_id: Optional[str] = None
    error: Optional[str] = None
    stale: bool = False


def handle_customer_subscription_deleted(
    event: dict,
    store: FleetOperatorStoreProtocol,
    *,
    now: Optional[datetime] = None,
    event_time: Optional[datetime] = None,
) -> SubscriptionDeletedResult:
    """`customer.subscription.deleted`イベントから`canceled_at`を書き込む。

    kura-pasha/course-set-pasha/aircon-pashaで発見された欠落(有料転換済み
    〈upgraded_atが非null〉のユーザーが解約後も`is_generation_paused()`の対象に
    ならず無期限に生成を使い続けられる)が本venture自体にも存在することを確認し、
    同型の修正として追加した。`handle_customer_subscription_updated()`と同じく
    `customer`から`internal_id`を逆引きする。決済失敗の有無によらず常に`canceled_at`
    を書き込む(aircon-pashaのdesign「3. 修正内容」と同じ方針)。逆引きできない場合は
    `error="unknown_customer"`として書き込みを行わない。

    `event_time`(subscription-lifecycle-event-order-guard-design.md、フェーズ214で
    追加)は、解約直後に即再契約した場合の配信順序入れ替わり対策。古い`deleted`が
    `created`より後に遅延配信された場合、記録済みのevent_time「以下」であれば
    `canceled_at`の書き込みを一切行わず`stale=True`を返す(他venture同様
    「stale全体スキップ」方針)。stale判定を通過した場合は書き込みの成否にかかわらず
    event_timeを記録する。`event_time`省略時(`None`)は従来通りこのチェック・記録の
    いずれも行わない(既存呼び出し経路への後方互換措置)。
    """
    data_object = event.get("data", {}).get("object", {})
    stripe_customer_id = data_object.get("customer")

    if not isinstance(stripe_customer_id, str) or not stripe_customer_id:
        return SubscriptionDeletedResult(canceled=False, error="missing_customer")

    internal_id = store.get_internal_id_by_stripe_customer_id(stripe_customer_id)
    if internal_id is None:
        return SubscriptionDeletedResult(canceled=False, error="unknown_customer")

    if _is_stale_subscription_lifecycle_event(store, internal_id, event_time):
        return SubscriptionDeletedResult(
            canceled=False, internal_id=internal_id, error="stale_event", stale=True
        )

    resolved_now = now if now is not None else datetime.now(timezone.utc)
    store.set_canceled_at(internal_id, resolved_now)
    _record_subscription_lifecycle_event_time(store, internal_id, event_time)

    return SubscriptionDeletedResult(canceled=True, internal_id=internal_id)


@dataclass
class SubscriptionCreatedResult:
    """handle_customer_subscription_created()の結果
    (subscription-canceled-immediate-block-design.md「6. 再契約時のcanceled_atクリア」
    フェーズ130)。"""

    cleared: bool
    internal_id: Optional[str] = None
    error: Optional[str] = None
    stale: bool = False


def handle_customer_subscription_created(
    event: dict,
    store: FleetOperatorStoreProtocol,
    *,
    event_time: Optional[datetime] = None,
) -> SubscriptionCreatedResult:
    """`customer.subscription.created`イベントから`canceled_at`のクリアのみを行う。

    フェーズ129の残課題(aircon-pashaのdesign「3. 修正内容」最終段と同じ論点:
    `customer.subscription.created`〈再契約〉受信時に`canceled_at`をクリアしないと、
    一度解約した`internal_id`が再契約してもis_subscription_canceled()が永久にTrueを
    返し続ける別の欠落になる)に対応する。`handle_customer_subscription_updated()`・
    `handle_customer_subscription_deleted()`と同じく`customer`から`internal_id`を
    逆引きする。逆引きできない場合は`error="unknown_customer"`としてクリアを行わない。
    `canceled_at`が元々未設定(初回契約、解約を経ていない)の場合もstore.set_canceled_at()
    をNoneで呼ぶのみでcleared=Trueを返す(冪等、kura-pasha等のset_canceled_at(None)の
    "pop"実装と同じく無害)。plan_id・upgraded_atの同期は本関数の対象外
    (`customer.subscription.updated`側の既存配線にそのまま委ねる)。

    `event_time`(subscription-lifecycle-event-order-guard-design.md、フェーズ214で
    追加)は`handle_customer_subscription_deleted()`と同一の`subscription_lifecycle_
    event_time`キーを共有する。記録済みのevent_time「以下」であれば`canceled_at`の
    クリアを行わず`stale=True`を返す。これにより、再契約〈`created`〉を処理した後に
    その契約より前の解約〈`deleted`〉が遅延配信されても誤って`canceled_at`を再設定
    させない(本関数側のガードはその逆方向、`created`自体が古い場合の保護)。
    """
    data_object = event.get("data", {}).get("object", {})
    stripe_customer_id = data_object.get("customer")

    if not isinstance(stripe_customer_id, str) or not stripe_customer_id:
        return SubscriptionCreatedResult(cleared=False, error="missing_customer")

    internal_id = store.get_internal_id_by_stripe_customer_id(stripe_customer_id)
    if internal_id is None:
        return SubscriptionCreatedResult(cleared=False, error="unknown_customer")

    if _is_stale_subscription_lifecycle_event(store, internal_id, event_time):
        return SubscriptionCreatedResult(
            cleared=False, internal_id=internal_id, error="stale_event", stale=True
        )

    store.set_canceled_at(internal_id, None)
    _record_subscription_lifecycle_event_time(store, internal_id, event_time)

    return SubscriptionCreatedResult(cleared=True, internal_id=internal_id)


@dataclass
class InvoicePaymentFailedResult:
    """handle_invoice_payment_failed()の結果(payment-failure-dunning-design.md
    5節、フェーズ167)。"""

    detected: bool
    internal_id: Optional[str] = None
    error: Optional[str] = None


def handle_invoice_payment_failed(
    event: dict,
    store: FleetOperatorStoreProtocol,
    *,
    now: Optional[datetime] = None,
) -> InvoicePaymentFailedResult:
    """`invoice.payment_failed`イベントから`payment_failure_detected_at`を記録する
    (payment-failure-dunning-design.md 5節)。`customer`から`internal_id`を逆引きする
    (既存3ハンドラと同じパターン)。逆引きできない場合は`error="unknown_customer"`として
    記録を行わない。実メール送信配線は本フェーズの対象外(design 6節「残課題」)。
    """
    data_object = event.get("data", {}).get("object", {})
    stripe_customer_id = data_object.get("customer")

    if not isinstance(stripe_customer_id, str) or not stripe_customer_id:
        return InvoicePaymentFailedResult(detected=False, error="missing_customer")

    internal_id = store.get_internal_id_by_stripe_customer_id(stripe_customer_id)
    if internal_id is None:
        return InvoicePaymentFailedResult(detected=False, error="unknown_customer")

    resolved_now = now if now is not None else datetime.now(timezone.utc)
    mark_payment_failure_detected(store, internal_id, resolved_now)

    return InvoicePaymentFailedResult(detected=True, internal_id=internal_id)


@dataclass
class InvoicePaymentSucceededResult:
    """handle_invoice_payment_succeeded()の結果(payment-failure-dunning-design.md
    5節、フェーズ167)。"""

    cleared: bool
    internal_id: Optional[str] = None
    recovery_kind: Optional[str] = None
    error: Optional[str] = None


def handle_invoice_payment_succeeded(
    event: dict,
    store: FleetOperatorStoreProtocol,
    *,
    now: Optional[datetime] = None,
) -> InvoicePaymentSucceededResult:
    """`invoice.payment_succeeded`イベントから`payment_failure_detected_at`をクリアする
    (payment-failure-dunning-design.md 5節)。`payment_failure_detected_at`が未設定
    (通常の毎月課金成功)の場合は`cleared=False`・`recovery_kind=None`のまま何もしない。
    設定済みの場合は`clear_payment_failure_on_success()`でクリアする前に
    `classify_payment_recovery()`で2分岐(design 4節)を判定してから書き込む
    (判定には消去前の`detected_at`が必要なため、クリアより先に呼ぶ順序を守る)。
    実メール送信配線は本フェーズの対象外(design 6節「残課題」)。
    """
    data_object = event.get("data", {}).get("object", {})
    stripe_customer_id = data_object.get("customer")

    if not isinstance(stripe_customer_id, str) or not stripe_customer_id:
        return InvoicePaymentSucceededResult(cleared=False, error="missing_customer")

    internal_id = store.get_internal_id_by_stripe_customer_id(stripe_customer_id)
    if internal_id is None:
        return InvoicePaymentSucceededResult(cleared=False, error="unknown_customer")

    detected_at = store.get_payment_failure_detected_at(internal_id)
    if detected_at is None:
        return InvoicePaymentSucceededResult(cleared=False, internal_id=internal_id)

    resolved_now = now if now is not None else datetime.now(timezone.utc)
    recovery_kind = classify_payment_recovery(detected_at, resolved_now)
    cleared = clear_payment_failure_on_success(store, internal_id)

    return InvoicePaymentSucceededResult(
        cleared=cleared, internal_id=internal_id, recovery_kind=recovery_kind
    )


@dataclass
class StripeWebhookReceiverResult:
    """receive_stripe_webhook()の結果(design 1節)。"""

    status_code: int
    checkout_link_result: Optional[CheckoutSessionLinkResult] = None
    subscription_updated_result: Optional[SubscriptionUpdatedSyncResult] = None
    subscription_deleted_result: Optional[SubscriptionDeletedResult] = None
    subscription_created_result: Optional[SubscriptionCreatedResult] = None
    invoice_payment_failed_result: Optional[InvoicePaymentFailedResult] = None
    invoice_payment_succeeded_result: Optional[InvoicePaymentSucceededResult] = None
    error: Optional[str] = None
    # フェーズ215追加: event_id_store指定時、`event.id`が処理済みのためハンドラを
    # 呼び出さずに200を返した場合True(aircon-pasha/kura-pashaと同一フィールド名)。
    duplicate: bool = False


def receive_stripe_webhook(
    body: bytes,
    signature_header: Optional[str],
    webhook_secret: str,
    *,
    store: FleetOperatorStoreProtocol,
    event_id_store: Optional[StripeEventIdStoreProtocol] = None,
    now: Optional[datetime] = None,
) -> StripeWebhookReceiverResult:
    """Cloud Functionの本体エントリポイント。生のリクエストボディ(bytes)を受け取り、
    署名検証(verify_stripe_signature)・JSONパース・`checkout.session.completed`の
    振り分けまでを行う(design 1節、本venture未着手のイベント種別は常に200で無視する)。

    - 署名検証に失敗した場合は401相当を返し、JSONパース以降の配線を一切行わない。
    - 署名検証後にbodyをJSONとしてパースする。パース失敗、またはパース結果がdictでない
      場合は400相当を返す。
    - イベント種別が`checkout.session.completed`の場合のみ
      `handle_checkout_session_completed()`へ振り分ける。それ以外のイベント種別は
      Stripe側の再送ループを避けるため200(受理・無視)として扱う。

    `event_id_store`(stripe-event-idempotency-design.md、フェーズ215追加、
    aircon-pashaフェーズ177・kura-pashaフェーズ77と同一設計)は指定時、パース済み
    イベントの`id`が既に処理済みであればいずれのハンドラも呼び出さず、
    `duplicate=True`とともに200を返す(副作用ゼロ)。`id`が欠落・非文字列の場合は
    チェックをスキップし従来通り処理する(安全側)。省略時(`None`)はべき等性チェックを
    一切行わない(既存呼び出し経路への後方互換措置)。本venture未着手のイベント種別
    (いずれのハンドラも呼ばれない分岐)は処理済み記録を行わない(aircon-pashaと同じ
    「ハンドラ呼び出し後にのみmark_processed()する」方針)。
    """
    resolved_now = now if now is not None else datetime.now(timezone.utc)
    if not verify_stripe_signature(
        body, signature_header, webhook_secret, now=resolved_now.timestamp()
    ):
        return StripeWebhookReceiverResult(status_code=401, error="invalid_signature")

    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return StripeWebhookReceiverResult(status_code=400, error="invalid_json")

    if not isinstance(parsed, dict):
        return StripeWebhookReceiverResult(status_code=400, error="invalid_event")

    event_id = parsed.get("id")
    check_idempotency = event_id_store is not None and isinstance(event_id, str)
    if check_idempotency and event_id_store.has_processed(event_id):
        return StripeWebhookReceiverResult(status_code=200, duplicate=True)

    event_type = parsed.get("type")

    if event_type == "checkout.session.completed":
        checkout_link_result = handle_checkout_session_completed(
            parsed, store, now=resolved_now, event_time=_event_time_from_created(parsed)
        )
        if check_idempotency:
            event_id_store.mark_processed(event_id)
        return StripeWebhookReceiverResult(
            status_code=200, checkout_link_result=checkout_link_result
        )

    if event_type == "customer.subscription.updated":
        subscription_updated_result = handle_customer_subscription_updated(
            parsed, store, event_time=_event_time_from_created(parsed)
        )
        if check_idempotency:
            event_id_store.mark_processed(event_id)
        return StripeWebhookReceiverResult(
            status_code=200, subscription_updated_result=subscription_updated_result
        )

    if event_type == "customer.subscription.deleted":
        subscription_deleted_result = handle_customer_subscription_deleted(
            parsed, store, now=resolved_now, event_time=_event_time_from_created(parsed)
        )
        if check_idempotency:
            event_id_store.mark_processed(event_id)
        return StripeWebhookReceiverResult(
            status_code=200, subscription_deleted_result=subscription_deleted_result
        )

    if event_type == "customer.subscription.created":
        subscription_created_result = handle_customer_subscription_created(
            parsed, store, event_time=_event_time_from_created(parsed)
        )
        if check_idempotency:
            event_id_store.mark_processed(event_id)
        return StripeWebhookReceiverResult(
            status_code=200, subscription_created_result=subscription_created_result
        )

    if event_type == "invoice.payment_failed":
        invoice_payment_failed_result = handle_invoice_payment_failed(
            parsed, store, now=resolved_now
        )
        if check_idempotency:
            event_id_store.mark_processed(event_id)
        return StripeWebhookReceiverResult(
            status_code=200, invoice_payment_failed_result=invoice_payment_failed_result
        )

    if event_type == "invoice.payment_succeeded":
        invoice_payment_succeeded_result = handle_invoice_payment_succeeded(
            parsed, store, now=resolved_now
        )
        if check_idempotency:
            event_id_store.mark_processed(event_id)
        return StripeWebhookReceiverResult(
            status_code=200,
            invoice_payment_succeeded_result=invoice_payment_succeeded_result,
        )

    return StripeWebhookReceiverResult(status_code=200)


def get_stripe_runtime_dependencies() -> dict:
    """receive_stripe_webhook()に渡す依存関係一式を組み立てるファクトリ
    (aircon-pasha/course-set-pashaのget_stripe_runtime_dependencies()と同じ位置づけ)。

    `store`: `InMemoryFleetOperatorStore()`を1つ生成する。プロセス起動ごとに初期化
    されるため、実Cloud Functions環境では呼び出しをまたいで紐付け・plan_id・
    upgraded_atが保持されない(他ventureと同じ既知の限界、実Firestore接続後に解消)。

    `event_id_store`(フェーズ215追加): `InMemoryStripeEventIdStore()`を`store`とは
    独立に1つ生成する(stripe-event-idempotency-design.md 2節、`event_id`と
    `internal_id`はキーの性質が異なるため使い回さない、aircon-pashaと同じ理由)。
    """
    return {"store": InMemoryFleetOperatorStore(), "event_id_store": InMemoryStripeEventIdStore()}


def main(request, *, runtime_dependencies: Optional[dict] = None):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定)。

    実リクエストオブジェクトからのbody(`request.get_data()`)・署名ヘッダ
    (`request.headers.get("Stripe-Signature")`)取り出し配線のみを行い、
    receive_stripe_webhook()に委譲する。`webhook_secret`は環境変数
    `STRIPE_WEBHOOK_SECRET`から取得する。

    `runtime_dependencies`省略時は`get_stripe_runtime_dependencies()`の戻り値
    (呼び出しごとに新規のInMemoryストア)を使うため、実Cloud Functions環境・既存呼び出し元の
    挙動は変わらない。checkout_session.main()(フェーズ146)と同じ依存注入パターンにより、
    事前に紐付け済みの`store`をテスト・簡易ローカルサーバーから注入できるようにした。
    """
    body = request.get_data()
    signature_header = request.headers.get("Stripe-Signature")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    result = receive_stripe_webhook(
        body,
        signature_header,
        webhook_secret,
        **(runtime_dependencies if runtime_dependencies is not None else get_stripe_runtime_dependencies()),
    )

    if result.status_code == 200:
        return "OK", 200
    return (result.error or "error"), result.status_code


def _demo() -> None:
    secret = "whsec_demo_secret"
    payload = b'{"id":"evt_demo","type":"customer.subscription.deleted"}'
    timestamp = int(time.time())
    signed_payload = f"{timestamp}.{payload.decode('utf-8')}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    header = f"t={timestamp},v1={sig}"
    print("valid signature ->", verify_stripe_signature(payload, header, secret))
    print("missing header ->", verify_stripe_signature(payload, None, secret))


if __name__ == "__main__":
    _demo()
