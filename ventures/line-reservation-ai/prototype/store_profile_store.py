#!/usr/bin/env python3
"""checkout-initiation-flow-design.md(フェーズ続き139)「残課題」の店舗プロフィールストア
(`stripe_customer_id`保持用)を実装する。

位置づけ:
- firestore-data-model.md 1節`stores/{storeId}`ドキュメントに`stripeCustomerId`フィールドを
  追加する形を想定した`StoreProfileStoreProtocol`と、その場しのぎ検証用の
  `InMemoryStoreProfileStore`を提供する。
- course-set-pasha/stripe-customer-id-linking-design.mdの`UserProfileStoreProtocol`拡張
  (`set_stripe_customer_id`/逆引き)と同じ考え方だが、本venture(line-reservation-ai)では
  逆引き(`stripe_customer_id → user_id`)はcheckout-initiation-flow-design.mdの範囲では
  不要(Webhookディスパッチのresolve_user_id側は本ventureでは別課題として未着手)なため、
  順引き(`user_id → stripe_customer_id`)の2メソッドのみを持たせる薄いスコープとする。
- 実Firestore接続(GCPプロジェクト設定を伴う)はオーナー承認待ちのため、本モジュールは
  実HTTPリクエスト・実DB接続なしで検証可能な範囲(Protocol定義・InMemory実装・
  `build_checkout_session_params()`との結線ヘルパー)にとどめる。
- `handle_checkout_session_completed()`(2026-08-28追記): checkout-initiation-flow-design.md
  「残課題」に残っていた、`checkout.session.completed`イベント受信時に
  `store.set_stripe_customer_id()`を呼ぶWebhookハンドラ本体
  (course-set-pasha/stripe_webhook.pyの`handle_checkout_session_completed()`相当)。
  本ventureはupgraded_at相当のフィールドを持たない(有料転換の判定は
  cloud_function_subscription_activated_webhook.pyがsuspension_reasonの書き換えで別途
  担当する)ため、`usage_counter`引数は持たせず、customer_idの紐付けのみを行う薄い版とする。
- `evaluate_onboarding_completion_message_dispatch()`(2026-08-30追記):
  onboarding-completion-message-design.md「残課題」に残っていた、「MVPの最低限必須項目
  (onboarding-guide.mdステップ3: 営業曜日・営業時間・予約枠の間隔・同時受付可能数・
  メニュー一覧最低1件)が今回の保存で初めて全て揃ったか」を判定し、初めて揃った場合のみ
  一度だけTrueを返す判定本体。first-booking-self-check-notification-design.mdの
  `consume_first_booking_self_check()`と同じ「店舗全体で最初の1回のみ」パターンを、
  `ConversationFlowStateMachine`側ではなく店舗プロフィールストア側(owner-settings-
  wireframe.mdのフォーム保存処理から呼ばれる想定)に実装したもの。
- `get_store_id_by_stripe_customer_id()`・`make_resolve_store_id_by_customer()`
  (2026-08-31追記): stripe-webhook-event-dispatch-design.md 5節・stripe-customer-id-
  reverse-lookup-design.md「残課題」に残っていた、`route_stripe_event()`
  (stripe_webhook.py)が`invoice.payment_succeeded`/`invoice.payment_failed`受信時に
  必要とする`resolve_store_id_by_customer`(`customer → store_id`逆引き)の実装本体。
  course-set-pasha/stripe-customer-id-linking-design.mdの
  `get_user_id_by_stripe_customer_id`と同じ考え方だが、本ventureは`user_id`をそのまま
  `store_id`として扱う(2節参照)ため、逆引き専用のメソッド名は`store_id`呼称に揃える。
- `get_owner_user_id()`/`set_owner_user_id()`(2026-09-02追記): checkout-initiation-flow-
  design.md 9節・store-id-resolution-and-owner-identity-design.md「残課題」に残っていた
  認可チェック(`stores/{store_id}.owner_user_id`と検証済み個人`user_id`の一致確認)の
  参照元を実装した。`checkout_session.py`の`verify_checkout_authorization()`から呼ばれる。
- `get_owner_is_following()`/`set_owner_is_following()`・`get_suspension_reason()`/
  `set_suspension_reason()`・`all_store_ids()`(2026-09-02追記、フェーズ続き176):
  blocked-but-billing-detection-design.md 1節・3節で設計した、オーナー自身の
  ブロック状態(`ownerIsFollowing`)と契約状態(`suspensionReason`)を店舗単位で
  追跡するための最小インターフェース。いずれも`stores/{storeId}`の同一ドキュメント上の
  フィールド(firestore-data-model.md)に対応する。`prototype/
  blocked_but_billing_candidates.py`の候補抽出ロジックから参照される。
- `get_owner_email()`/`set_owner_email()`・
  `get_blocked_but_billing_owner_notified_at()`/
  `set_blocked_but_billing_owner_notified_at()`(2026-09-03追記、フェーズ続き177):
  blocked-but-billing-owner-email-notification-design.md 1節・3節で設計した、
  ブロック中かつ契約継続中の店舗オーナーへメール通知するための送信先
  (`ownerEmail`)と冪等性フラグ(`blockedButBillingOwnerNotifiedAt`)。いずれも
  `stores/{storeId}`の同一ドキュメント上のフィールド。`prototype/
  blocked_but_billing_owner_email_notification.py`から参照される。
- `PLAN_MONTHLY_BOOKING_LIMITS`・`get_plan()`/`set_plan()`(2026-09-03追記、
  フェーズ続き181): checkout-session-plan-selection-design.mdで設計した、
  `checkout.session.completed`受信時に購入プラン(pricing-plan.mdの3プラン)を
  記録するための保持先。フェーズ続き180(monthly-booking-limit-notification-design.md)が
  「次回以降の課題」として残した「store_profile_store.pyに契約プランを保持する
  フィールドが無い」ギャップに対応する(course-set-pashaがフェーズ152で同種の
  ギャップに対応したcheckout-session-plan-selection-design.mdの横展開)。
- `resolve_monthly_booking_limit()`(2026-09-03追記、フェーズ続き182):
  checkout-session-plan-selection-design.md「残課題」に残っていた、
  `ConversationFlowStateMachine`構築時に`store.get_plan(store_id)`から
  `monthly_booking_limit`引数へ渡す値を求める結線ヘルパー。
  `resolve_existing_stripe_customer_id()`と同じ位置づけ。
- `build_conversation_flow_state_machine_for_store()`(2026-09-04追記、フェーズ続き187):
  conversation-flow-construction-design.mdで設計した、`resolve_monthly_booking_limit()`が
  求めた値を実際に`ConversationFlowStateMachine`(engine.py)のコンストラクタへ渡す構築
  ヘルパー。会話状態(`_states`)自体の永続化・復元方式(実Firestore接続後の課題)は
  対象外で、構築時の引数組み立てのみを切り出す。

設計の参照元: checkout-initiation-flow-design.md 3節・9節・10節・残課題、
firestore-data-model.md 1節、onboarding-completion-message-design.md 残課題、
stripe-webhook-event-dispatch-design.md 5節、stripe-customer-id-reverse-lookup-design.md、
blocked-but-billing-detection-design.md 1節・3節、checkout-session-plan-selection-design.md、
conversation-flow-construction-design.md
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Protocol

sys.path.insert(0, str(Path(__file__).parent))

from engine import (  # noqa: E402
    BookingSlotManager,
    ConversationFlowStateMachine,
    EscalationConsolidator,
    InMemoryBookingRecordStore,
    NotificationLogAggregator,
)

# checkout-session-plan-selection-design.md(フェーズ続き181): pricing-plan.mdが定める
# 3プラン名をキーとする月間予約件数上限。course-set-pasha/cloud_function_webhook.py の
# PLAN_MONTHLY_LIMITSと同じ位置づけで、本venture(line-reservation-ai)にはPLAN定数を
# 置く既存の一元管理場所(cloud_function_webhook.py相当)が無いため、店舗プロフィールを
# 扱う本モジュールを単一の正とする。checkout_session.py・engine.pyの双方から参照する。
PLAN_MONTHLY_BOOKING_LIMITS = {
    "スタータープラン": 50,
    "スタンダードプラン": 150,
    "プロプラン": 300,
}


class StoreProfileStoreProtocol(Protocol):
    """`stores/{storeId}`ドキュメントの`stripeCustomerId`フィールドを読み書きするための
    最小インターフェース(firestore-data-model.md 1節)。"""

    def get_stripe_customer_id(self, user_id: str) -> Optional[str]:
        ...

    def set_stripe_customer_id(self, user_id: str, stripe_customer_id: str) -> None:
        ...

    def get_store_id_by_stripe_customer_id(
        self, stripe_customer_id: str
    ) -> Optional[str]:
        ...

    def is_onboarding_completion_message_sent(self, user_id: str) -> bool:
        ...

    def mark_onboarding_completion_message_sent(self, user_id: str) -> None:
        ...

    def get_owner_user_id(self, store_id: str) -> Optional[str]:
        ...

    def set_owner_user_id(self, store_id: str, owner_user_id: str) -> None:
        ...

    def get_owner_is_following(self, store_id: str) -> bool:
        ...

    def set_owner_is_following(self, store_id: str, is_following: bool) -> None:
        ...

    def get_suspension_reason(self, store_id: str) -> Optional[str]:
        ...

    def set_suspension_reason(self, store_id: str, suspension_reason: Optional[str]) -> None:
        ...

    def get_owner_email(self, store_id: str) -> Optional[str]:
        ...

    def set_owner_email(self, store_id: str, owner_email: str) -> None:
        ...

    def get_blocked_but_billing_owner_notified_at(self, store_id: str) -> Optional[str]:
        ...

    def set_blocked_but_billing_owner_notified_at(
        self, store_id: str, value: Optional[str]
    ) -> None:
        ...

    def get_plan(self, store_id: str) -> Optional[str]:
        ...

    def set_plan(self, store_id: str, plan: str) -> None:
        ...

    def all_store_ids(self):
        ...


class InMemoryStoreProfileStore:
    """実Firestore接続前の検証用スタブ。プロセス内の`dict`に保持するのみで、
    course-set-pasha/stripe_webhook.pyの`InMemoryUserProfileStore`と同様、
    呼び出しをまたいだ永続化(実Cloud Functions環境でのコールドスタート間保持)は
    保証しない暫定実装。"""

    def __init__(self) -> None:
        self._stripe_customer_ids: dict[str, str] = {}
        self._store_ids_by_stripe_customer_id: dict[str, str] = {}
        self._onboarding_completion_message_sent: set[str] = set()
        self._owner_user_ids: dict[str, str] = {}
        self._owner_is_following: dict[str, bool] = {}
        self._suspension_reasons: dict[str, Optional[str]] = {}
        self._owner_emails: dict[str, str] = {}
        self._blocked_but_billing_owner_notified_at: dict[str, Optional[str]] = {}
        self._plans: dict[str, str] = {}
        self._known_store_ids: set[str] = set()

    def get_stripe_customer_id(self, user_id: str) -> Optional[str]:
        return self._stripe_customer_ids.get(user_id)

    def set_stripe_customer_id(self, user_id: str, stripe_customer_id: str) -> None:
        if not user_id:
            raise ValueError("user_id must be a non-empty string")
        if not stripe_customer_id:
            raise ValueError("stripe_customer_id must be a non-empty string")
        previous_stripe_customer_id = self._stripe_customer_ids.get(user_id)
        if (
            previous_stripe_customer_id is not None
            and previous_stripe_customer_id != stripe_customer_id
        ):
            # 同一user_idに別のstripe_customer_idが再紐付けされた場合、逆引き辞書に
            # 古いcustomer_idのエントリが残ると別ユーザーへの誤解決につながるため除去する
            # (通常はresolve_existing_stripe_customer_id()で既存customerが再利用されるため
            # 起こらない想定だが、防御的に対応する)。
            self._store_ids_by_stripe_customer_id.pop(previous_stripe_customer_id, None)
        self._stripe_customer_ids[user_id] = stripe_customer_id
        self._store_ids_by_stripe_customer_id[stripe_customer_id] = user_id

    def get_store_id_by_stripe_customer_id(
        self, stripe_customer_id: str
    ) -> Optional[str]:
        return self._store_ids_by_stripe_customer_id.get(stripe_customer_id)

    def is_onboarding_completion_message_sent(self, user_id: str) -> bool:
        return user_id in self._onboarding_completion_message_sent

    def mark_onboarding_completion_message_sent(self, user_id: str) -> None:
        if not user_id:
            raise ValueError("user_id must be a non-empty string")
        self._onboarding_completion_message_sent.add(user_id)

    def get_owner_user_id(self, store_id: str) -> Optional[str]:
        return self._owner_user_ids.get(store_id)

    def set_owner_user_id(self, store_id: str, owner_user_id: str) -> None:
        if not store_id:
            raise ValueError("store_id must be a non-empty string")
        if not owner_user_id:
            raise ValueError("owner_user_id must be a non-empty string")
        self._owner_user_ids[store_id] = owner_user_id
        self._known_store_ids.add(store_id)

    def get_owner_is_following(self, store_id: str) -> bool:
        # blocked-but-billing-detection-design.md 1節: 未設定の間は安全側で
        # 「フォロー中」として扱う(値が確定するのはfollow/unfollowイベントを
        # 一度でも受信した後のみ)。
        return self._owner_is_following.get(store_id, True)

    def set_owner_is_following(self, store_id: str, is_following: bool) -> None:
        if not store_id:
            raise ValueError("store_id must be a non-empty string")
        self._owner_is_following[store_id] = bool(is_following)
        self._known_store_ids.add(store_id)

    def get_suspension_reason(self, store_id: str) -> Optional[str]:
        return self._suspension_reasons.get(store_id)

    def set_suspension_reason(self, store_id: str, suspension_reason: Optional[str]) -> None:
        if not store_id:
            raise ValueError("store_id must be a non-empty string")
        self._suspension_reasons[store_id] = suspension_reason
        self._known_store_ids.add(store_id)

    def get_owner_email(self, store_id: str) -> Optional[str]:
        return self._owner_emails.get(store_id)

    def set_owner_email(self, store_id: str, owner_email: str) -> None:
        if not store_id:
            raise ValueError("store_id must be a non-empty string")
        if not owner_email:
            raise ValueError("owner_email must be a non-empty string")
        self._owner_emails[store_id] = owner_email
        self._known_store_ids.add(store_id)

    def get_blocked_but_billing_owner_notified_at(self, store_id: str) -> Optional[str]:
        return self._blocked_but_billing_owner_notified_at.get(store_id)

    def set_blocked_but_billing_owner_notified_at(
        self, store_id: str, value: Optional[str]
    ) -> None:
        if not store_id:
            raise ValueError("store_id must be a non-empty string")
        self._blocked_but_billing_owner_notified_at[store_id] = value
        self._known_store_ids.add(store_id)

    def get_plan(self, store_id: str) -> Optional[str]:
        return self._plans.get(store_id)

    def set_plan(self, store_id: str, plan: str) -> None:
        if not store_id:
            raise ValueError("store_id must be a non-empty string")
        if plan not in PLAN_MONTHLY_BOOKING_LIMITS:
            raise ValueError(f"unknown plan: {plan!r}")
        self._plans[store_id] = plan
        self._known_store_ids.add(store_id)

    def all_store_ids(self):
        # blocked-but-billing-detection-design.md 3節: MVPでは既知のstore_id
        # (いずれかのsetterが一度でも呼ばれたstore)を昇順で線形走査する。将来
        # Firestoreの複合クエリに置き換える際もこのメソッドのシグネチャは
        # そのまま流用できる想定(aircon-pasha/blocked_but_billing_candidates.py
        # の`all_user_ids()`と同じ考え方)。
        return sorted(self._known_store_ids)


def resolve_existing_stripe_customer_id(
    user_id: str, store: StoreProfileStoreProtocol
) -> Optional[str]:
    """checkout-initiation-flow-design.md 3節手順3
    (`build_checkout_session_params()`呼び出し前に既存customerの有無を確認する処理)に対応する
    薄いヘルパー。`store.get_stripe_customer_id()`をそのまま呼ぶだけだが、呼び出し元
    (Checkout Session作成エンドポイント予定地)で`store`の型を意識せず
    `StoreProfileStoreProtocol`のみに依存させるための結線点として切り出す。
    """
    if not user_id:
        raise ValueError("user_id must be a non-empty string")
    return store.get_stripe_customer_id(user_id)


def make_resolve_store_id_by_customer(
    store: StoreProfileStoreProtocol,
) -> Callable[[str], Optional[str]]:
    """stripe-webhook-event-dispatch-design.md 5節で残課題だった、
    `route_stripe_event()`の`resolve_store_id_by_customer`引数の実装本体。
    `store.get_store_id_by_stripe_customer_id`をそのまま返す薄いファクトリ
    (course-set-pasha/stripe-customer-id-linking-design.mdの
    `make_resolve_user_id()`と同じ考え方)。
    """
    return store.get_store_id_by_stripe_customer_id


def resolve_monthly_booking_limit(
    store_id: str, store: StoreProfileStoreProtocol
) -> Optional[int]:
    """checkout-session-plan-selection-design.md 1節手順5・「残課題」で設計した、
    `ConversationFlowStateMachine`(engine.py)を構築する際に`monthly_booking_limit`引数へ
    渡すべき値を`store.get_plan(store_id)`から求めるヘルパー(フェーズ続き182)。

    店舗がまだプランを購入していない(トライアル中で`store.get_plan()`がNoneを返す)場合は
    Noneを返す。`ConversationFlowStateMachine.__init__`はmonthly_booking_limit未指定(None)を
    「機能無効」として扱う既定動作(monthly-booking-limit-notification-design.md準拠)のため、
    このNoneをそのまま`monthly_booking_limit`引数へ渡せば意図通り機能が無効のままになる
    (checkout-session-plan-selection-design.md「残課題」に記載していた想定通り)。

    `store.set_plan()`が`PLAN_MONTHLY_BOOKING_LIMITS`にないプラン名をそもそも拒否する
    (ValueError)ため、`store.get_plan()`が返す値は常にNoneかこの辞書の既知キーのいずれかで
    あり、ここでの`.get()`が未知のキーに当たることは想定していない(防御的に`.get()`を使う)。

    `resolve_existing_stripe_customer_id()`/`make_resolve_store_id_by_customer()`と同じ、
    店舗プロフィールストアと呼び出し元(engine.py)との結線点を切り出すヘルパー関数という
    位置づけ。実際に`ConversationFlowStateMachine`のコンストラクタへこの値を渡す配線は
    `build_conversation_flow_state_machine_for_store()`(フェーズ続き187、下記)が担う。
    """
    if not store_id:
        raise ValueError("store_id must be a non-empty string")
    plan = store.get_plan(store_id)
    if plan is None:
        return None
    return PLAN_MONTHLY_BOOKING_LIMITS.get(plan)


def build_conversation_flow_state_machine_for_store(
    store_id: str,
    store: StoreProfileStoreProtocol,
    *,
    slots: Optional[BookingSlotManager] = None,
    consolidator: Optional[EscalationConsolidator] = None,
    logs: Optional[NotificationLogAggregator] = None,
    record_store: Optional[InMemoryBookingRecordStore] = None,
) -> ConversationFlowStateMachine:
    """conversation-flow-construction-design.mdで設計した、`resolve_monthly_booking_limit()`
    (フェーズ続き182)が求めた値を実際に`ConversationFlowStateMachine`(engine.py)の
    コンストラクタへ渡す構築ヘルパー(フェーズ続き187)。

    `slots`・`consolidator`は未指定時それぞれ新規`BookingSlotManager()`・
    `EscalationConsolidator()`を生成する。既存インスタンスを再利用したい呼び出し側
    (例: テストで内部状態を検査したい場合)は明示的に渡せる。`logs`・`record_store`は
    そのまま`ConversationFlowStateMachine`へ透過する(未指定時は従来通り機能しない
    後方互換)。

    位置づけの範囲(conversation-flow-construction-design.md 4節参照): 本関数が担うのは
    「構築時に`monthly_booking_limit`引数へ渡す値の組み立て」のみ。この関数を実際に
    どこから(Cloud Function Bの初回リクエスト時か、店舗単位のキャッシュ層か)呼ぶかという
    配線、および会話状態(`_states`)自体をFirestoreドキュメントとの間でhydrate/dehydrate
    する方式は、実Firestore接続後の課題として引き続き別途残る(cloud_function_process_event.py
    の`ConversationEventProcessor`docstring参照)。

    `store_id`が空文字列の場合は`resolve_monthly_booking_limit()`と同じ`ValueError`が
    そのまま送出される。
    """
    monthly_booking_limit = resolve_monthly_booking_limit(store_id, store)
    return ConversationFlowStateMachine(
        slots if slots is not None else BookingSlotManager(),
        consolidator if consolidator is not None else EscalationConsolidator(),
        logs=logs,
        record_store=record_store,
        monthly_booking_limit=monthly_booking_limit,
    )


@dataclass
class CheckoutSessionLinkResult:
    """`handle_checkout_session_completed()`の結果
    (checkout-initiation-flow-design.md 残課題)。"""

    linked: bool
    user_id: Optional[str] = None
    stripe_customer_id: Optional[str] = None
    plan_written: bool = False


def handle_checkout_session_completed(
    event: dict, store: StoreProfileStoreProtocol
) -> CheckoutSessionLinkResult:
    """`checkout.session.completed`イベントから`client_reference_id`(=user_id)と
    `customer`(=stripe_customer_id)を取り出し、`store`に紐付けを書き込む
    (course-set-pasha/stripe_webhook.pyの`handle_checkout_session_completed()`と同じ考え方)。
    いずれかが欠落・非文字列・空文字列の場合は何も書き込まない(安全側。
    `resolve_existing_stripe_customer_id()`が引き続きNoneを返すだけで実害はなく、次回の
    Checkout Session作成では既存customerが無いものとして新規customerが作られるのみ)。

    `plan`(checkout-session-plan-selection-design.md、フェーズ続き181で追加)は、
    `checkout_session.build_checkout_session_params()`がCheckout Session作成時に設定した
    `metadata.plan`から取り出す。`PLAN_MONTHLY_BOOKING_LIMITS`にある既知の値のみ
    `store.set_plan(user_id, plan)`で書き込み、`metadata`欠落・`plan`欠落・未知の値の
    場合は何も書き込まない(安全側。古いCheckout Session実装〈metadata省略〉からの
    イベントでも紐付け自体は従来通り行える)。
    """
    data_object = event.get("data", {}).get("object", {})
    user_id = data_object.get("client_reference_id")
    stripe_customer_id = data_object.get("customer")

    if (
        not isinstance(user_id, str)
        or not user_id
        or not isinstance(stripe_customer_id, str)
        or not stripe_customer_id
    ):
        return CheckoutSessionLinkResult(linked=False)

    store.set_stripe_customer_id(user_id, stripe_customer_id)

    plan_written = False
    metadata = data_object.get("metadata")
    plan = metadata.get("plan") if isinstance(metadata, dict) else None
    if isinstance(plan, str) and plan in PLAN_MONTHLY_BOOKING_LIMITS:
        store.set_plan(user_id, plan)
        plan_written = True

    return CheckoutSessionLinkResult(
        linked=True,
        user_id=user_id,
        stripe_customer_id=stripe_customer_id,
        plan_written=plan_written,
    )


def evaluate_onboarding_completion_message_dispatch(
    user_id: str,
    *,
    business_hours_configured: bool,
    slot_interval_minutes: Optional[int],
    concurrent_capacity: Optional[int],
    menu_count: int,
    store: StoreProfileStoreProtocol,
) -> bool:
    """onboarding-guide.mdステップ3のフォーム保存処理から都度呼ばれる想定の判定関数
    (onboarding-completion-message-design.md 残課題)。

    「MVPの最低限必須項目」(営業曜日・営業時間・予約枠の間隔・同時受付可能数・
    メニュー一覧最低1件)が今回の保存で初めて全て揃ったかを判定し、初めて揃った場合の
    みTrueを返す(呼び出し元はTrueが返った時のみ`render_onboarding_completion_message()`
    を送信する)。営業曜日・営業時間は既存のバリデーション(availability-closed-weekday-
    support.md・business-hours-lunch-break.md)を通過済みの値である前提のため、ここでは
    単純に「1件以上設定されているか」の`business_hours_configured`のみを受け取る。

    既に送信済み(`store.is_onboarding_completion_message_sent()`がTrue)の店舗では、
    2回目以降の設定変更・再編集のたびに毎回Falseを返す(何度も送ると煩わしい通知になる
    ため、first-booking-self-check-notification-design.mdと同じ「店舗全体で1回のみ」方針)。
    """
    if not user_id:
        raise ValueError("user_id must be a non-empty string")
    if store.is_onboarding_completion_message_sent(user_id):
        return False

    required_fields_present = (
        business_hours_configured
        and slot_interval_minutes is not None
        and slot_interval_minutes > 0
        and concurrent_capacity is not None
        and concurrent_capacity > 0
        and menu_count >= 1
    )
    if not required_fields_present:
        return False

    store.mark_onboarding_completion_message_sent(user_id)
    return True
