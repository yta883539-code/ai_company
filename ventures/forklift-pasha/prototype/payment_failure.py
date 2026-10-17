#!/usr/bin/env python3
"""payment-failure-dunning-design.md(フェーズ167)3〜5節で設計した、決済失敗検知〜
猶予期間〜制限モードの状態遷移のうち、Stripe Webhook(`invoice.payment_failed`・
`invoice.payment_succeeded`)受信時に`fleet_operator`の状態を更新する部分を実行可能な
コードに落とし込んだもの。

本venture(forklift-pasha)は`subscription_status`列挙値を持たず、既存の
`is_trial_period_over`・`is_generation_paused`・`is_subscription_canceled`
(trial_management.py)と同じく、タイムスタンプ(`payment_failure_detected_at`)からの
都度計算で状態を表現する(design 1節)。判定対象は有料転換済み(`upgraded_at`設定済み)
かつ未解約(`canceled_at`未設定)の事業者のみとし、解約済みの場合は常に
`is_subscription_canceled()`側が優先する(design 3節)。

リマインド送信スケジューラ・運営者向け通知・実メール送信配線は本モジュールの対象外
(design 6節「残課題」)。実Stripe接続・実メール送信サービス接続は引き続きオーナー
承認待ち(pending-approval.md参照)。
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional, Protocol

PAYMENT_FAILURE_GRACE_PERIOD_DAYS = 7  # design 3節、他venture4件と同じ暫定値


class PaymentFailureStoreProtocol(Protocol):
    """`fleet_operator`ドキュメントのうち`payment_failure_detected_at`・
    `upgraded_at`・`canceled_at`の3フィールドを対象にした薄いインターフェース
    (aircon-pasha/payment_failure.pyの`PaymentFailureStoreProtocol`と同じ位置づけ)。
    専用のInMemoryスタブは新設せず、`trial_management.InMemoryFleetOperatorStore`が
    構造的に(duck typing)本Protocolを満たす形にする。"""

    def get_payment_failure_detected_at(self, internal_id: str) -> Optional[datetime]:
        ...

    def set_payment_failure_detected_at(
        self, internal_id: str, value: Optional[datetime]
    ) -> None:
        ...

    def get_upgraded_at(self, internal_id: str) -> Optional[datetime]:
        ...

    def get_canceled_at(self, internal_id: str) -> Optional[datetime]:
        ...


def mark_payment_failure_detected(
    store: PaymentFailureStoreProtocol, internal_id: str, event_time: datetime,
) -> datetime:
    """design 4・5節「決済失敗検知時(猶予期間開始)」: `invoice.payment_failed`受信時
    (`stripe_customer_id → internal_id`の逆引き後)に呼ぶ。Stripeスマートリトライによる
    複数回の失敗連続通知(design 2節)でも、既に設定済みなら最新の失敗日時で上書きする
    (aircon-pashaのmark_payment_failure_detected()と同じ「安全側」判断)。書き込んだ値を
    返す。
    """
    store.set_payment_failure_detected_at(internal_id, event_time)
    return event_time


def clear_payment_failure_on_success(
    store: PaymentFailureStoreProtocol, internal_id: str,
) -> bool:
    """design 4・5節「決済成功による復旧時」: `invoice.payment_succeeded`受信時
    (逆引き後)に呼ぶ。`payment_failure_detected_at`が未設定(通常の毎月課金成功)の場合は
    何もせず`False`を返す。設定済みの場合はクリアして`True`を返す(呼び出し側で
    `classify_payment_recovery()`による文言出し分けと組み合わせる)。
    """
    if store.get_payment_failure_detected_at(internal_id) is None:
        return False
    store.set_payment_failure_detected_at(internal_id, None)
    return True


def is_payment_suspended(
    internal_id: str,
    now: datetime,
    store: PaymentFailureStoreProtocol,
) -> bool:
    """design 3節の制限モード判定(段階3)。`payment_failure_detected_at`が設定済みで
    経過日数が`PAYMENT_FAILURE_GRACE_PERIOD_DAYS`以上の場合のみTrue。トライアル中
    (`upgraded_at`未設定)・解約済み(`canceled_at`設定済み)の場合は、決済失敗の状態が
    意味を持たないため常にFalse(design 3節「呼び出し側での優先順位」、
    `is_subscription_canceled()`側を先に判定する想定)。
    """
    if store.get_upgraded_at(internal_id) is None:
        return False
    if store.get_canceled_at(internal_id) is not None:
        return False
    detected_at = store.get_payment_failure_detected_at(internal_id)
    if detected_at is None:
        return False
    return now >= detected_at + timedelta(days=PAYMENT_FAILURE_GRACE_PERIOD_DAYS)


def classify_payment_recovery(
    detected_at: datetime,
    succeeded_at: datetime,
) -> str:
    """design 4節「決済成功による復旧時」の2分岐判定。`clear_payment_failure_on_success()`
    でクリアする"前"の`detected_at`を使って判定すること(呼び出し順序は
    `handle_invoice_payment_succeeded()`参照)。戻り値は"recovered_from_suspension"
    (制限モードからの復旧、通知あり)または"resolved_within_grace_period"
    (猶予期間中の解消、通知なし)。
    """
    if succeeded_at >= detected_at + timedelta(days=PAYMENT_FAILURE_GRACE_PERIOD_DAYS):
        return "recovered_from_suspension"
    return "resolved_within_grace_period"


# design 4節「決済失敗検知時(猶予期間開始)」。
PAYMENT_FAILURE_DETECTED_EMAIL_NOTICE = (
    "【フォークリフトパシャっと】お支払いの確認をお願いします\n\n"
    "いつもご利用ありがとうございます。\n"
    "今回のお支払い手続きが完了できませんでした(カードの有効期限切れ・利用限度額等が"
    "考えられます)。\n\n"
    "現在、点検記録簿の整形・期限リマインドの生成は通常どおりご利用いただけます。\n"
    "7日以内にお支払い方法をご確認・更新いただけますようお願いします(ご契約時に"
    "ご案内した画面からご確認いただけます)。"
)

# design 4節「制限モード移行時」。生成リクエストへの応答として返す文言。
PAYMENT_SUSPENDED_NOTICE = (
    "お支払い手続きが確認できないため、点検記録簿の整形・期限リマインドの生成を"
    "一時停止しています。お支払い方法をご確認いただければ、確認完了後に自動で"
    "生成を再開します。"
)

# design 4節「決済成功による復旧時」。"recovered_from_suspension"の場合のみ送信する。
PAYMENT_RECOVERED_EMAIL_NOTICE = (
    "【フォークリフトパシャっと】お支払いを確認しました\n\n"
    "お支払い手続きが完了しました。ご不便をおかけしました。\n"
    "点検記録簿の整形・期限リマインドの生成を再開しましたので、引き続きよろしく"
    "お願いします。"
)
