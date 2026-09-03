#!/usr/bin/env python3
"""
subscription-cancellation-flow-design.mdで設計した、オーナー自らの意思による解約
(Stripeカスタマーポータル経由の解約操作)を扱うWebhookハンドラ。

位置づけ:
- 実際のStripeアカウント接続・Webhookエンドポイント公開・LINE Push Message API接続は
  「アカウント作成」「支払い」に該当し、引き続きオーナー承認待ち(pending-approval.md参照)。
  本モジュールは実クラウド接続なしで検証可能な「判断・整形ロジック自体」のみを実装する。
- 解約には2種類のStripe Webhookイベントが関わる(design 1節)。
  1. `customer.subscription.updated`(`cancel_at_period_end`の変化) →
     `handle_subscription_updated()`。サービス継続中のため`suspension_reason`は変更しない。
  2. `customer.subscription.deleted`(実際の契約終了) → `handle_subscription_deleted()`。
     ここで初めて`suspension_reason`を`"cancelled"`に書き換える。

`cloud_function_payment_webhook.py`・`cloud_function_subscription_activated_webhook.py`
との役割分担:
- 両モジュールとも「自分が担当しないsuspension_reasonの値には触れない」設計を踏襲する。
  本モジュールは`suspension_reason == "payment_failed"`(dunning側が担当)の店舗には
  一切書き込みを行わない。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cloud_function_process_event import (  # noqa: E402
    LinePushClient,
    LinePushDeliveryError,
)

# classify_subscription_update()が返す分類。
OUTCOME_CANCELLATION_SCHEDULED = "cancellation_scheduled"
OUTCOME_CANCELLATION_RESCHEDULED = "cancellation_rescheduled"
OUTCOME_NO_CHANGE = "no_change"

# classify_subscription_deleted()が返す分類。
OUTCOME_CANCELLED = "cancelled"
OUTCOME_ALREADY_CANCELLED = "already_cancelled"
OUTCOME_OUT_OF_SCOPE_PAYMENT_FAILED = "out_of_scope_payment_failed"

# handle_*()のみが返す、送信失敗を表す分類(design 5節)。
OUTCOME_SEND_FAILED = "send_failed"

MESSAGE_TONES = ("formal", "standard", "casual")


@dataclass
class StoreSubscriptionState:
    """1店舗ぶんの契約状態(cloud_function_subscription_activated_webhook.pyの
    同名クラスと同型。suspension_reasonは同じFirestoreフィールドを指す)。

    `blocked_but_billing_owner_notified_at`(2026-09-03追記、フェーズ続き178)は
    blocked-but-billing-owner-email-notification-design.md 5節「クリア配線」対応。
    呼び出し元がFirestoreから読み込んだ現在値を渡し、`handle_subscription_deleted()`が
    解約確定時にクリアする(値そのものはメール送信時刻の文字列表現だが、本モジュールは
    内容を解釈せず「設定済みかどうか」だけを見る)。
    """

    store_id: str
    owner_line_user_id: str
    plan_name: str
    period_end_date: str
    portal_url: str
    message_tone: str = "standard"
    suspension_reason: str | None = None
    blocked_but_billing_owner_notified_at: str | None = None


@dataclass
class SubscriptionCancellationUpdateResult:
    """`customer.subscription.updated`(cancel_at_period_end変化)処理の結果。"""

    outcome: str
    notified: bool = False


@dataclass
class SubscriptionCancellationResult:
    """`customer.subscription.deleted`処理の結果。

    outcomeがOUTCOME_SEND_FAILEDの場合、状態は変更されていないため呼び出し側は
    5xxを返してWebhookのリトライに委ねる(既存2モジュールと同じ方針)。

    `blocked_but_billing_owner_notified_at_cleared`(2026-09-03追記、フェーズ続き178)は
    blocked-but-billing-owner-email-notification-design.md 5節「クリア配線」対応。
    解約確定時に`state.blocked_but_billing_owner_notified_at`をクリアした(=クリア前に
    設定済みだった)場合のみ`True`。
    """

    outcome: str
    notified: bool = False
    state_changed: bool = False
    blocked_but_billing_owner_notified_at_cleared: bool = False


def classify_subscription_update(
    cancel_at_period_end_before: bool,
    cancel_at_period_end_after: bool,
    suspension_reason: str | None,
) -> str:
    """`customer.subscription.updated`受信時、cancel_at_period_endの変化をどう扱うか判定する。

    design 5節の通り、suspension_reasonが"payment_failed"(dunning側が担当する猶予期間・
    制限モード)の店舗には触れない。
    """
    if suspension_reason == "payment_failed":
        return OUTCOME_NO_CHANGE
    if not cancel_at_period_end_before and cancel_at_period_end_after:
        return OUTCOME_CANCELLATION_SCHEDULED
    if cancel_at_period_end_before and not cancel_at_period_end_after:
        return OUTCOME_CANCELLATION_RESCHEDULED
    return OUTCOME_NO_CHANGE


def classify_subscription_deleted(suspension_reason: str | None) -> str:
    """`customer.subscription.deleted`受信時、店舗の現在の状態からどう扱うか判定する。"""
    if suspension_reason == "cancelled":
        return OUTCOME_ALREADY_CANCELLED
    if suspension_reason == "payment_failed":
        return OUTCOME_OUT_OF_SCOPE_PAYMENT_FAILED
    return OUTCOME_CANCELLED


def _render_by_tone(tone: str, variants: dict) -> str:
    """未知のtone値はstandardにフォールバックする(既存モジュールと同じ安全側の挙動)。"""
    return variants.get(tone, variants["standard"])


def render_cancellation_scheduled_message(
    plan_name: str, period_end_date: str, portal_url: str, tone: str = "standard"
) -> str:
    """design 3節「解約予約受理時の案内メッセージ」をトーン別に整形する。"""
    variants = {
        "formal": f"""【予約とれる君】解約のお手続きを承りました

解約のお手続きを承りました。以下の点をご確認くださいませ。

・現在のご契約: {plan_name}
・ご利用は今回の請求期間の終了日({period_end_date})まで通常通り継続いたします
  (新規のご予約受付も含め、機能の制限はございません)
・終了日以降は新規のご予約受付を停止し、その時点で確定済みのご予約と
  前日リマインドのみ引き続き対応いたします
・日割りでの返金は行っておりません

解約をお取り消しになりたい場合は、終了日より前であれば下記から「更新を再開」の
お手続きが可能です。

▼ お手続きはこちら
{portal_url}

またのご利用をお待ち申し上げております。""",
        "standard": f"""【予約とれる君】解約のお手続きを承りました

解約のお手続きを承りました。以下の点をご確認ください。

・現在のご契約: {plan_name}
・ご利用は今回の請求期間の終了日({period_end_date})まで通常通り継続します
  (新規のご予約受付も含め、機能の制限はありません)
・終了日以降は新規のご予約受付を停止し、その時点で確定済みのご予約と
  前日リマインドのみ引き続き対応します
・日割りでの返金は行っておりません

解約を取り消したい場合は、終了日より前であれば下記から「更新を再開」の
お手続きが可能です。

▼ お手続きはこちら
{portal_url}

またのご利用をお待ちしております。""",
        "casual": f"""【予約とれる君】解約のお手続き、承りました

解約の手続きを承りました。

・現在のご契約: {plan_name}
・今回の請求期間の終了日({period_end_date})までは今まで通り使えます
  (新規の予約受付もOKです)
・終了日以降は新規の予約受付を停止して、確定済みの予約と前日リマインドだけ
  引き続き対応します
・日割り返金はありません

やっぱり続けたい場合は、終了日より前なら下記から「更新を再開」できます。

▼ こちら
{portal_url}

またのご利用をお待ちしています。""",
    }
    return _render_by_tone(tone, variants)


def render_cancellation_rescheduled_message(
    plan_name: str, period_end_date: str, tone: str = "standard"
) -> str:
    """design 3.1節「解約取り消し時の案内メッセージ」をトーン別に整形する。"""
    variants = {
        "formal": f"""【予約とれる君】解約のお取り消しを承りました

解約のお取り消しを承りました。引き続き{plan_name}をご利用いただけます。
次回請求日: {period_end_date}

ご不明な点がございましたら、このトークルームへご返信くださいませ。""",
        "standard": f"""【予約とれる君】解約のお取り消しを承りました

解約のお取り消しを承りました。引き続き{plan_name}をご利用いただけます。
次回請求日: {period_end_date}

ご不明点はこのトークルームにご返信ください。""",
        "casual": f"""【予約とれる君】解約の取り消し、承りました!

解約の取り消しを承りました。引き続き{plan_name}が使えます。
次回請求日: {period_end_date}

わからないことがあればこのトークルームに返信してください。""",
    }
    return _render_by_tone(tone, variants)


def render_cancellation_completed_message(tone: str = "standard") -> str:
    """design 4節「解約確定(契約終了)時の案内メッセージ」をトーン別に整形する。"""
    variants = {
        "formal": """【予約とれる君】ご契約が終了しました

ご契約が終了いたしました。これまでご利用いただき誠にありがとうございました。

・新規のご予約受付は停止いたしました(お客様には自動で受付停止中の旨をご案内いたします)
・現時点で確定済みのご予約と前日リマインドは、実施日まで引き続き通常通り対応いたします

またのご利用を心よりお待ち申し上げております。再開をご希望の際は、いつでも
新規契約と同じお手続きでお申し込みいただけます。""",
        "standard": """【予約とれる君】ご契約が終了しました

ご契約が終了しました。ご利用ありがとうございました。

・新規のご予約受付は停止しました(お客様には自動で受付停止中の旨をご案内します)
・現時点で確定済みのご予約と前日リマインドは、実施日まで引き続き通常通り対応します

またのご利用をお待ちしております。再開をご希望の際は、いつでも新規契約と
同じお手続きでお申し込みいただけます。""",
        "casual": """【予約とれる君】ご契約が終了しました

ご契約が終了しました。今までありがとうございました!

・新規の予約受付は停止しました(お客様には自動で受付停止中の旨を案内します)
・すでに確定してる予約と前日リマインドは、当日まで引き続き対応します

またのご利用をお待ちしています。再開したくなったら、いつでも新規契約と
同じ手続きで申し込めます。""",
    }
    return _render_by_tone(tone, variants)


def handle_subscription_updated(
    state: StoreSubscriptionState,
    cancel_at_period_end_before: bool,
    cancel_at_period_end_after: bool,
    push_client: LinePushClient,
) -> SubscriptionCancellationUpdateResult:
    """`customer.subscription.updated`(cancel_at_period_end変化)受信時の処理本体。

    design 1節の通り、この時点では契約は継続中のためsuspension_reasonは変更しない。
    """
    outcome = classify_subscription_update(
        cancel_at_period_end_before, cancel_at_period_end_after, state.suspension_reason
    )

    if outcome == OUTCOME_NO_CHANGE:
        return SubscriptionCancellationUpdateResult(outcome=outcome)

    if outcome == OUTCOME_CANCELLATION_SCHEDULED:
        text = render_cancellation_scheduled_message(
            state.plan_name, state.period_end_date, state.portal_url, state.message_tone
        )
    else:
        text = render_cancellation_rescheduled_message(
            state.plan_name, state.period_end_date, state.message_tone
        )

    try:
        push_client.send_message(state.owner_line_user_id, text)
    except LinePushDeliveryError:
        return SubscriptionCancellationUpdateResult(outcome=OUTCOME_SEND_FAILED)

    return SubscriptionCancellationUpdateResult(outcome=outcome, notified=True)


def handle_subscription_deleted(
    state: StoreSubscriptionState, push_client: LinePushClient
) -> SubscriptionCancellationResult:
    """`customer.subscription.deleted`受信時の処理本体。

    引数のstateは呼び出し元でFirestoreから読み取った当該店舗の状態を想定し、
    本関数は必要な通知送信と状態の書き換えを行う(実際のFirestore書き戻しは呼び出し側)。
    """
    outcome = classify_subscription_deleted(state.suspension_reason)

    if outcome in (OUTCOME_ALREADY_CANCELLED, OUTCOME_OUT_OF_SCOPE_PAYMENT_FAILED):
        return SubscriptionCancellationResult(outcome=outcome)

    text = render_cancellation_completed_message(state.message_tone)

    try:
        push_client.send_message(state.owner_line_user_id, text)
    except LinePushDeliveryError:
        return SubscriptionCancellationResult(outcome=OUTCOME_SEND_FAILED)

    state.suspension_reason = "cancelled"

    # blocked-but-billing-owner-email-notification-design.md 5節「クリア配線」
    # (フェーズ続き178)。「設定済みの場合のみクリアしTrue/Falseを返す」ロジックを、
    # blocked_but_billing_owner_email_notification.clear_blocked_but_billing_owner_
    # notified_at()と同じ考え方で`state`属性の書き換えとしてインライン実装する
    # (本モジュールはstore_id keyed Protocolではなく1件ぶんのstateを直接扱う設計のため、
    # 同関数はそのままでは呼べない。理由の詳細は同関数のdocstring参照)。
    cleared = state.blocked_but_billing_owner_notified_at is not None
    if cleared:
        state.blocked_but_billing_owner_notified_at = None

    return SubscriptionCancellationResult(
        outcome=outcome,
        notified=True,
        state_changed=True,
        blocked_but_billing_owner_notified_at_cleared=cleared,
    )


def _demo() -> None:
    from cloud_function_process_event import InMemoryLinePushClient

    push = InMemoryLinePushClient()

    store = StoreSubscriptionState(
        store_id="store-5",
        owner_line_user_id="owner-line-5",
        plan_name="スタンダードプラン",
        period_end_date="2026-09-14",
        portal_url="https://example.com/billing/portal",
    )

    print("1) 解約操作直後:", handle_subscription_updated(store, False, True, push))
    print("2) 解約取り消し:", handle_subscription_updated(store, True, False, push))
    print("3) Webhook再送(変化なし):", handle_subscription_updated(store, False, False, push))

    print("4) 請求期間終了・契約実終了:", handle_subscription_deleted(store, push))
    print("  状態:", store.suspension_reason)
    print("5) Webhook再送(冪等性):", handle_subscription_deleted(store, push))

    suspended = StoreSubscriptionState(
        store_id="store-6",
        owner_line_user_id="owner-line-6",
        plan_name="スタンダードプラン",
        period_end_date="2026-09-20",
        portal_url="https://example.com/billing/portal",
        suspension_reason="payment_failed",
    )
    print("6) 決済失敗で制限モード中の店舗への誤配信:", handle_subscription_deleted(suspended, push))
    print("  状態:", suspended.suspension_reason)

    print("送信済みログ件数:", len(push.sent))
    for _, text in push.sent:
        print("---")
        print(text)


if __name__ == "__main__":
    _demo()
