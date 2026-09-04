#!/usr/bin/env python3
"""
subscription-cancellation-notification-design.md(フェーズ184)の実送信配線。

course-set-pashaのsubscription-cancelled-notification-design.md(フェーズ155)・
subscription-cancellation-scheduled-notification-design.md(フェーズ156)を本ventureへ
横展開したもの。`customer.subscription.deleted`(契約終了)受信時の解約完了案内と、
`customer.subscription.updated`受信時の`cancel_at_period_end`変化(解約予約受理・
解約取り消し)案内の両方を1モジュールにまとめる(course-set-pashaは2フェーズに分けて
実装したが、本ventureでは横展開時にまとめて1フェーズで実装する)。

本ventureの既存通知モジュール(payment_failure.py・payment_recovery_notification.py等)は
一貫して`LinePushClient.send_flex_message(user_id, alt_text, contents)`によるFlex
Message送信のみを使う(course-set-pashaのようなプレーンテキストの`send_message()`は
使わない)ため、本モジュールも`payment_recovery_notification._build_flex_message()`と
同じ「bodyテキストのみのシンプルなbubble」形式を踏襲する。design 2節参照。

位置づけ: 実際のWebhook受信・LINE Push Message API・実Stripeアカウント接続はいずれも
オーナー承認待ち(pending-approval.md参照)。本モジュールはそれとは別に、通知内容の
組み立てロジックと送信配線を実クラウド接続なしで検証可能にしたもの。

フェーズ185: subscription-cancellation-scheduled-message-suspension-consistency-
design.md対応(course-set-pashaフェーズ157の横展開)。`_is_payment_suspended_now()`を
新設し、`render_subscription_cancellation_scheduled_message()`/
`handle_subscription_cancellation_update()`に`payment_store`引数を配線した。詳細は
同ドキュメント参照。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, Protocol

from cloud_function_webhook import (
    PORTAL_LINK_PLACEHOLDER,
    PORTAL_LINK_UNAVAILABLE_FALLBACK,
    PortalLinkProvider,
)
from payment_failure import PaymentFailureStoreProtocol

_JST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# 送信基盤(他モジュールと同じ「モジュールごとに専用クラスを持つ」既存の慣習を踏襲)
# ---------------------------------------------------------------------------


class LinePushDeliveryError(Exception):
    """LINE Push Message API呼び出し失敗(タイムアウト・5xx・429等)を表す。
    他モジュールのLinePushDeliveryErrorと対称の位置づけ。"""


class LinePushClient(Protocol):
    def send_flex_message(self, user_id: str, alt_text: str, contents: dict) -> None:
        ...


class InMemoryLinePushClient:
    """実LINE Push Message API接続の代わりに送信内容を記録するだけの検証用クライアント
    (他モジュールのInMemoryLinePushClientと同じ位置づけ)。"""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, dict]] = []

    def send_flex_message(self, user_id: str, alt_text: str, contents: dict) -> None:
        self.sent.append((user_id, alt_text, contents))


def _build_flex_message(body_text: str) -> dict:
    """payment_recovery_notification._build_flex_message()と同じ構成。CTAボタンは
    付けない、footerを持たないbubbleのみのシンプルな構成とする。"""
    return {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": body_text,
                    "wrap": True,
                },
            ],
        },
    }


# ---------------------------------------------------------------------------
# customer.subscription.deleted(契約終了)向け(design 4節)
# ---------------------------------------------------------------------------

SUBSCRIPTION_CANCELLED_ALT_TEXT = "[エアコンパシャッと] ご契約が終了しました"

# design 4節。course-set-pashaのSUBSCRIPTION_CANCELLED_MESSAGEを、本venture固有の
# 業務内容(「投稿文の生成」→「作業完了報告・お手入れ案内の生成」)に翻案した。
SUBSCRIPTION_CANCELLED_MESSAGE = (
    "ご契約が終了しました。ご利用ありがとうございました。\n"
    "本日以降、作業完了報告・お手入れ案内の生成はご利用いただけません。\n"
    "\n"
    "またのご利用をお待ちしております。再開をご希望の際は、いつでも新規契約と"
    "同じお手続きでお申し込みいただけます。"
)


def render_subscription_cancelled_message() -> str:
    """design 4節の文言をそのまま返す(日付・URL等の差し込みが無いため引数なし)。"""
    return SUBSCRIPTION_CANCELLED_MESSAGE


def build_subscription_cancelled_flex_message() -> dict:
    return _build_flex_message(render_subscription_cancelled_message())


@dataclass
class SubscriptionCancelledNotificationResult:
    """1回の`customer.subscription.deleted`通知送信の結果。design 5節のとおり、
    本モジュールは送信成否のみを報告する。削除候補化等の状態変更は呼び出し側
    (`dispatch_stripe_event()`)が送信成否と独立して行う。"""

    notified: bool


def handle_subscription_cancelled(
    user_id: str,
    push_client: LinePushClient,
) -> SubscriptionCancelledNotificationResult:
    """`customer.subscription.deleted`受信時(`stripe_customer_id → user_id`逆引き後)に
    呼ぶ処理本体。送信失敗時も呼び出し側での状態変更(削除候補化等)をブロックしない設計の
    ため、本関数自体は例外を外へ漏らさず`notified=False`を返すのみで完結する。"""
    try:
        push_client.send_flex_message(
            user_id,
            SUBSCRIPTION_CANCELLED_ALT_TEXT,
            build_subscription_cancelled_flex_message(),
        )
    except LinePushDeliveryError:
        return SubscriptionCancelledNotificationResult(notified=False)
    return SubscriptionCancelledNotificationResult(notified=True)


# ---------------------------------------------------------------------------
# customer.subscription.updated(cancel_at_period_end変化)向け(design 3・4節)
# ---------------------------------------------------------------------------

# classify_cancel_at_period_end_change()が返す分類。course-set-pasha・line-reservation-ai
# のOUTCOME_*と対称の命名。
OUTCOME_CANCELLATION_SCHEDULED = "cancellation_scheduled"
OUTCOME_CANCELLATION_RESCHEDULED = "cancellation_rescheduled"
OUTCOME_NO_CHANGE = "no_change"

SUBSCRIPTION_CANCELLATION_SCHEDULED_ALT_TEXT = "[エアコンパシャッと] 解約のお手続きを承りました"
SUBSCRIPTION_CANCELLATION_RESCHEDULED_ALT_TEXT = "[エアコンパシャッと] 解約のお取り消しを承りました"

# design 4節。差し込み情報なし(暫定文言、design 4節「残課題」参照)。
SUBSCRIPTION_CANCELLATION_RESCHEDULED_MESSAGE = (
    "解約のお取り消しを承りました。引き続きご利用いただけます。\n"
    "\n"
    "ご不明な点がございましたら、トライアル終了案内・生成一時停止のメッセージに記載の"
    "お問い合わせ先までご連絡ください。"
)


def classify_cancel_at_period_end_change(before: bool, after: bool) -> str:
    """design 3節。`customer.subscription.updated`受信時、`cancel_at_period_end`の
    前後比較から分類する。本ventureは`suspension_reason`相当の別立て状態を持たないため、
    line-reservation-aiの`classify_subscription_update()`と異なりガード条件を持たない
    (course-set-pashaフェーズ156と同じ)。"""
    if not before and after:
        return OUTCOME_CANCELLATION_SCHEDULED
    if before and not after:
        return OUTCOME_CANCELLATION_RESCHEDULED
    return OUTCOME_NO_CHANGE


def _format_period_end_date_jst(current_period_end: object) -> Optional[str]:
    """design 4節。`current_period_end`(Unixタイムスタンプ)をJSTの`YYYY-MM-DD`形式へ
    変換する。存在しない・数値でない・bool(intのサブクラス)の場合は`None`を返す
    (安全側フォールバック)。"""
    if not isinstance(current_period_end, (int, float)) or isinstance(current_period_end, bool):
        return None
    return datetime.fromtimestamp(current_period_end, tz=_JST).strftime("%Y-%m-%d")


def _is_payment_suspended_now(
    payment_store: Optional[PaymentFailureStoreProtocol],
    user_id: Optional[str],
) -> bool:
    """subscription-cancellation-scheduled-message-suspension-consistency-design.md
    (フェーズ185)。`cloud_function_webhook._is_payment_suspended()`と同じ判定条件
    (payment-failure-dunning-design.md 3節の段階3)を、本モジュールからも独立に評価する。

    course-set-pashaのフェーズ157版`_is_payment_suspended_now()`は猶予日数の定数
    (`PAYMENT_FAILURE_GRACE_PERIOD_DAYS`)から都度期限超過を計算するが、本ventureは
    そもそも猶予期間経過を都度計算する設計を採っておらず、`payment_suspension_
    scheduler.py`が猶予期間経過後に1回だけ書き込む`payment_suspended_at`フィールドの
    設定有無のみで判定する(`cloud_function_webhook._is_payment_suspended()`の
    docstring・stripe_dispatch.pyの`payment_store`引数と同じ既存方針)。したがって本関数は
    `now`引数を持たず、`payment_store.get_payment_suspended_at(user_id)`が非`None`かどうか
    のみを見る。`payment_store`は`invoice.payment_failed`/`invoice.payment_succeeded`
    向けに既に`stripe_dispatch.dispatch_stripe_event()`へ渡されている
    `PaymentFailureStoreProtocol`をそのまま再利用する(新規の引数・ストアを増やさない)。

    `payment_store`が`None`・`user_id`が`None`/空文字列・`payment_store`が
    `get_payment_suspended_at`に対応していない場合(将来の互換性のための安全策)は
    常に`False`を返す(安全側デフォルト、既存の`_is_payment_suspended`がprofile=Noneで
    `False`を返すのと同じ考え方)。"""
    if payment_store is None or not user_id:
        return False
    get_suspended_at = getattr(payment_store, "get_payment_suspended_at", None)
    if get_suspended_at is None:
        return False
    return get_suspended_at(user_id) is not None


def render_subscription_cancellation_scheduled_message(
    period_end_date: Optional[str],
    portal_link_provider: Optional[PortalLinkProvider],
    user_id: Optional[str],
    is_currently_suspended: bool = False,
) -> str:
    """design 4節「解約予約受理時の案内メッセージ」を組み立てる。`period_end_date`が
    `None`の場合は日付なしの表現に差し替える。URL差し込みは
    `cloud_function_webhook.format_payment_portal_reply_message()`と同じ
    `PORTAL_LINK_PLACEHOLDER`+`.replace()`方式。未接続・user_id不明・URL取得失敗時は
    `PORTAL_LINK_UNAVAILABLE_FALLBACK`へ全文差し替える(壊れたURLを顧客に見せない)。

    `is_currently_suspended`はsubscription-cancellation-scheduled-message-suspension-
    consistency-design.md(フェーズ185、course-set-pashaフェーズ157の横展開)対応。
    決済失敗の猶予期間超過により既に作業完了報告・お手入れ案内の生成が制限モードへ
    移行済みの顧客が解約予約を行った場合、従来の固定文言(「生成に制限はありません」)は
    事実と矛盾するため、`True`の場合は制限モード中である旨を案内する文言に差し替える。
    デフォルト`False`のため既存呼び出し経路への後方互換を保つ。"""
    until_phrase = (
        f"今回の請求期間の終了日({period_end_date})まで"
        if period_end_date is not None
        else "今回の請求期間の終了日まで"
    )
    if is_currently_suspended:
        usage_line = (
            f"・契約自体は{until_phrase}継続しますが、お支払い方法のご確認が必要な状態のため"
            "作業完了報告・お手入れ案内の生成は既に一時停止しています(解約予約とは別に、"
            "お支払い方法をご確認いただくまで生成は再開しません)\n"
        )
    else:
        usage_line = (
            f"・ご利用は{until_phrase}通常通り継続します"
            "(作業完了報告・お手入れ案内の生成に制限はありません)\n"
        )
    text = (
        "解約のお手続きを承りました。以下の点をご確認ください。\n"
        "\n"
        f"{usage_line}"
        "・終了日以降は作業完了報告・お手入れ案内の生成がご利用いただけなくなります\n"
        "・日割りでの返金は行っておりません\n"
        "\n"
        "解約を取り消したい場合は、終了日より前であれば下記からお手続きが可能です。\n"
        "\n"
        "▼ お手続きはこちら\n"
        f"{PORTAL_LINK_PLACEHOLDER}\n"
        "\n"
        "またのご利用をお待ちしております。"
    )

    url = None
    if portal_link_provider is not None and user_id:
        url = portal_link_provider.get_portal_url(user_id)
    if not url:
        return PORTAL_LINK_UNAVAILABLE_FALLBACK
    return text.replace(PORTAL_LINK_PLACEHOLDER, url)


def render_subscription_cancellation_rescheduled_message() -> str:
    """design 4節の文言をそのまま返す(差し込み情報なし)。"""
    return SUBSCRIPTION_CANCELLATION_RESCHEDULED_MESSAGE


@dataclass
class SubscriptionCancellationUpdateResult:
    """1回の`customer.subscription.updated`(cancel_at_period_end変化)処理の結果。
    `outcome`が`OUTCOME_NO_CHANGE`の場合、送信は行われず`notified`は常に`False`。"""

    outcome: str
    notified: bool = False


def handle_subscription_cancellation_update(
    user_id: str,
    cancel_at_period_end_before: bool,
    cancel_at_period_end_after: bool,
    current_period_end: object,
    push_client: LinePushClient,
    portal_link_provider: Optional[PortalLinkProvider] = None,
    payment_store: Optional[PaymentFailureStoreProtocol] = None,
) -> SubscriptionCancellationUpdateResult:
    """design 5節。`dispatch_stripe_event()`の`customer.subscription.updated`分岐から
    呼ばれる処理本体。本イベントは契約継続中(scheduled)または契約継続が確定した
    (rescheduled)場合のみ発火するため、削除候補管理側の状態は一切変更しない
    (呼び出し側でも変更しない)。

    `payment_store`はsubscription-cancellation-scheduled-message-suspension-
    consistency-design.md(フェーズ185)対応。`OUTCOME_CANCELLATION_SCHEDULED`の場合のみ
    `_is_payment_suspended_now()`で現在の制限モード状態を判定し、案内メッセージの内容へ
    反映する(`OUTCOME_CANCELLATION_RESCHEDULED`側のメッセージは制限モードの有無に
    関わらず文言が変わらないため参照しない)。未指定(`None`)の場合は
    `_is_payment_suspended_now()`が安全側で`False`を返すため、既存呼び出し経路への
    後方互換を保つ。"""
    outcome = classify_cancel_at_period_end_change(
        cancel_at_period_end_before, cancel_at_period_end_after
    )
    if outcome == OUTCOME_NO_CHANGE:
        return SubscriptionCancellationUpdateResult(outcome=outcome)

    if outcome == OUTCOME_CANCELLATION_SCHEDULED:
        alt_text = SUBSCRIPTION_CANCELLATION_SCHEDULED_ALT_TEXT
        text = render_subscription_cancellation_scheduled_message(
            _format_period_end_date_jst(current_period_end),
            portal_link_provider,
            user_id,
            _is_payment_suspended_now(payment_store, user_id),
        )
    else:
        alt_text = SUBSCRIPTION_CANCELLATION_RESCHEDULED_ALT_TEXT
        text = render_subscription_cancellation_rescheduled_message()

    try:
        push_client.send_flex_message(user_id, alt_text, _build_flex_message(text))
    except LinePushDeliveryError:
        return SubscriptionCancellationUpdateResult(outcome=outcome, notified=False)

    return SubscriptionCancellationUpdateResult(outcome=outcome, notified=True)


def _demo() -> None:
    from cloud_function_webhook import InMemoryPortalLinkProvider

    push = InMemoryLinePushClient()
    result = handle_subscription_cancelled("u1", push)
    print("契約終了:", result)

    provider = InMemoryPortalLinkProvider()
    scheduled = handle_subscription_cancellation_update(
        "u2",
        False,
        True,
        int(datetime(2026, 10, 1, tzinfo=timezone.utc).timestamp()),
        push,
        provider,
    )
    print("解約予約受理:", scheduled)

    rescheduled = handle_subscription_cancellation_update(
        "u3", True, False, None, push, provider
    )
    print("解約取り消し:", rescheduled)

    print("送信済みログ件数:", len(push.sent))
    for user_id, alt_text, contents in push.sent:
        print("---", user_id, alt_text)
        print(contents["body"]["contents"][0]["text"])


if __name__ == "__main__":
    _demo()
