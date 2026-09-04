#!/usr/bin/env python3
"""
billing-upgrade-flow-design.md 3節「決済完了後のメッセージ」を、決済代行サービスの
Webhook(初回のプラン選択・カード登録完了を通知するイベント。以下`subscription_activated`と
呼ぶ)を直接トリガーとする経路として実装したもの。

位置づけ:
- 決済代行サービスとの契約・実際のWebhookエンドポイント公開・Firestore書き込み・LINE
  Push Message APIでの送信は「アカウント作成」「支払い」に該当し、引き続きオーナー承認待ち
  (pending-approval.md参照)。本モジュールは実クラウド接続なしで検証可能な「判断・配線
  ロジック自体」のみを実装する。
- 店舗の状態は`cloud_function_send_dunning_notifications.py`の`StoreDunningState`に
  倣った専用のデータクラス(`StoreSubscriptionState`)として定義する。suspension_reasonは
  同じFirestoreフィールドを指すが、プラン名・次回請求日・マイページURLはdunning側には
  無い項目のため別クラスとした。

`cloud_function_payment_webhook.py`との役割分担(重要な設計上の判断):
- `cloud_function_payment_webhook.py`は「猶予期間中・制限モードからの決済成功」
  (suspension_reason == "payment_failed"、またはpayment_failure_detected_atありの状態)を
  扱う。本モジュールは「トライアル終了後、有料プラン未選択のまま休止モードに入っていた店舗が
  初めてプランを選択し決済を完了した」(suspension_reason == "trial_unselected")を扱う。
  billing-upgrade-flow-design.md 4節とdormant-mode-renotification-design.mdで
  suspension_reasonの値として明確に区別されている2つの休止要因に対応する形で、
  Webhookイベント自体も別種(初回のプラン登録 vs 既存契約の決済失敗からの復旧)と整理する。
- 両モジュールとも「自分が担当しないsuspension_reasonの値には触れない」設計を踏襲する
  (cloud_function_payment_webhook.pyの_clear_dunning_state()のコメント参照)。これにより、
  一方のWebhookイベントがもう一方の休止状態を誤って解除する事故を防ぐ。
- 通常の店舗(suspension_reasonが元々Noneで、既に有料契約が有効)にこのイベントが届いた
  場合(Webhook再送、または決済代行サービス側の設定ミスで無関係なイベントが送られてきた場合)は
  何もしない。二重登録完了メッセージを送らないための冪等性は、`payment_succeeded`側と同じく
  状態そのもの(suspension_reasonが既にtrial_unselectedでない)から判定する。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from cloud_function_process_event import (  # noqa: E402
    LinePushClient,
    LinePushDeliveryError,
)

# classify_subscription_activated()が返す分類。
OUTCOME_ACTIVATED = "activated"
OUTCOME_ALREADY_ACTIVE = "already_active"
OUTCOME_OUT_OF_SCOPE_PAYMENT_FAILED = "out_of_scope_payment_failed"

# handle_subscription_activated()のみが返す、送信失敗を表す分類。
OUTCOME_SEND_FAILED = "send_failed"

MESSAGE_TONES = ("formal", "standard", "casual")


@dataclass
class StoreSubscriptionState:
    """1店舗ぶんの契約状態(Firestoreのstoresドキュメントに相当する項目のみ抜粋)。

    suspension_reasonはcloud_function_send_dunning_notifications.StoreDunningStateと
    同じフィールドを指す(dormant-mode-renotification-design.mdの3分岐: なし/
    "trial_unselected"/"payment_failed")。本モジュールが読み書きの対象とするのは
    "trial_unselected"のときのみ。

    portal_url(Stripeカスタマーポータルへの一時リンク)はportal-session-provider-
    design.md(フェーズ続き192)により、stateへ保存する固定フィールドから、呼び出し時に
    都度`PortalLinkProvider.get_portal_url()`で解決する方式へ変更した(フェーズ続き193)。
    そのためstateからは削除し、`handle_subscription_activated()`の引数として渡す。
    """

    store_id: str
    owner_line_user_id: str
    plan_name: str
    next_billing_date: str
    message_tone: str = "standard"
    suspension_reason: str | None = None


@dataclass
class SubscriptionActivatedResult:
    """1回の`subscription_activated`Webhook処理の結果(呼び出し側のログ・HTTPステータス判断用)。

    outcomeがOUTCOME_SEND_FAILEDの場合、状態は変更されていないため呼び出し側は
    5xxを返してWebhookのリトライに委ねる。
    """

    outcome: str
    notified: bool = False
    state_reset: bool = False


def classify_subscription_activated(state: StoreSubscriptionState) -> str:
    """店舗の現在の状態から、`subscription_activated`Webhookをどう扱うべきか判定する。"""
    if state.suspension_reason == "payment_failed":
        # 既存契約の決済失敗からの復旧はcloud_function_payment_webhook.pyの担当。
        # 本モジュールが誤ってsuspension_reasonを解除しないよう、ここで弾く。
        return OUTCOME_OUT_OF_SCOPE_PAYMENT_FAILED
    if state.suspension_reason != "trial_unselected":
        # 既に有効な契約がある(またはそもそも休止していない)店舗への重複配信。
        return OUTCOME_ALREADY_ACTIVE
    return OUTCOME_ACTIVATED


def _render_by_tone(tone: str, variants: dict) -> str:
    """未知のtone値はstandardにフォールバックする(既存モジュールと同じ安全側の挙動)。"""
    return variants.get(tone, variants["standard"])


def render_subscription_activated_message(
    plan_name: str, next_billing_date: str, portal_url: Optional[str], tone: str = "standard"
) -> str:
    """billing-upgrade-flow-design.md 3節の「決済完了後のメッセージ」をトーン別に整形する。

    plan_name・next_billing_dateは決済代行サービスのWebhookペイロードに含まれる値を
    そのまま埋め込む想定(3節の注記通り、実装時の項目名確定は決済代行サービス選定後の
    課題として残す)。message-tone-variants.mdの規則(実質情報はトーンで変わらない)に
    従い、これらの値自体はトーンに関わらず同じ形式で埋め込む。

    portal_urlは`PortalLinkProvider.get_portal_url()`で都度解決した値を呼び出し元から
    渡す想定(portal-session-provider-design.md 4節)。取得できなかった場合(provider
    未接続・store_idにStripe顧客IDが紐付いていない・API呼び出し失敗)は`None`となり、
    「ご登録内容の確認・変更」の案内行自体を省略する安全側フォールバックとする
    (design 4節2.、壊れたURLや古いリンクを本文に残さないため)。
    """
    portal_line = f"・ご登録内容の確認・変更: {portal_url}(マイページ)\n" if portal_url else ""
    variants = {
        "formal": f"""【予約とれる君】ご登録ありがとうございます

{plan_name}へのご登録手続きが完了いたしました。
本日より正式にご利用いただけます。

・次回請求日: {next_billing_date}
{portal_line}
引き続きどうぞよろしくお願い申し上げます。""",
        "standard": f"""【予約とれる君】ご登録ありがとうございます

{plan_name}へのご登録が完了しました。
本日より正式にご利用いただけます。

・次回請求日: {next_billing_date}
{portal_line}
引き続きよろしくお願いいたします。""",
        "casual": f"""【予約とれる君】ご登録ありがとうございます🎉

{plan_name}への登録が完了しました!
本日から使えます。

・次回請求日: {next_billing_date}
{portal_line}
引き続きよろしくお願いします。""",
    }
    return _render_by_tone(tone, variants)


def handle_subscription_activated(
    state: StoreSubscriptionState,
    push_client: LinePushClient,
    portal_url: Optional[str] = None,
) -> SubscriptionActivatedResult:
    """決済代行サービスの`subscription_activated`Webhook受信時の処理本体。

    引数のstateは呼び出し元でFirestoreから読み取った当該店舗の状態を想定し、
    本関数は必要な通知送信と状態の書き換えを行う(実際のFirestore書き戻しは呼び出し側)。
    portal_urlは呼び出し元(`receive_stripe_webhook()`)が`PortalLinkProvider`から
    都度解決した値を渡す想定(portal-session-provider-design.md 4節、省略時は`None`で
    render側のフォールバックに委ねる)。
    """
    outcome = classify_subscription_activated(state)

    if outcome in (OUTCOME_ALREADY_ACTIVE, OUTCOME_OUT_OF_SCOPE_PAYMENT_FAILED):
        return SubscriptionActivatedResult(outcome=outcome)

    text = render_subscription_activated_message(
        state.plan_name, state.next_billing_date, portal_url, state.message_tone
    )

    try:
        push_client.send_message(state.owner_line_user_id, text)
    except LinePushDeliveryError:
        return SubscriptionActivatedResult(outcome=OUTCOME_SEND_FAILED)

    state.suspension_reason = None
    return SubscriptionActivatedResult(outcome=outcome, notified=True, state_reset=True)


def _demo() -> None:
    from cloud_function_process_event import InMemoryLinePushClient

    push = InMemoryLinePushClient()

    # 1) トライアル終了後、有料プラン未選択で休止モードだった店舗が初めて決済を完了。
    store = StoreSubscriptionState(
        store_id="store-3",
        owner_line_user_id="owner-line-3",
        plan_name="スタンダードプラン",
        next_billing_date="2026-09-14",
        suspension_reason="trial_unselected",
    )
    print(
        "1回目(初回登録完了):",
        handle_subscription_activated(
            store, push, portal_url="https://example.com/billing/portal"
        ),
    )
    print("  状態:", store.suspension_reason)

    # 2) Webhook再送: 既にsuspension_reasonが解除済みのため二重送信されない(冪等性の確認)。
    print("2回目(Webhook再送):", handle_subscription_activated(store, push))

    # 3) 既存契約が決済失敗で制限モード中に、無関係な`subscription_activated`が届いた場合。
    #    本モジュールはdunning側の状態(suspension_reason="payment_failed")に触れない。
    suspended = StoreSubscriptionState(
        store_id="store-4",
        owner_line_user_id="owner-line-4",
        plan_name="スタンダードプラン",
        next_billing_date="2026-09-20",
        suspension_reason="payment_failed",
    )
    result = handle_subscription_activated(suspended, push)
    print("3回目(既存契約が制限モード中):", result)
    print("  状態:", suspended.suspension_reason)

    print("送信済みログ件数:", len(push.sent))
    for _, text in push.sent:
        print("---")
        print(text)


if __name__ == "__main__":
    _demo()
