#!/usr/bin/env python3
"""
payment-failure-dunning-design.md 4節末尾で先行して書き残していた「猶予期間中に決済が
成功した場合の復旧通知の3分岐(制限モードからの復旧/猶予期間中の完了通知/状態リセットのみ)」
を、`invoice.payment_succeeded`受信時の実送信配線として実装したもの(フェーズ146)。

line-reservation-aiのフェーズ続き115(payment-failure-dunning-design.md、
prototype/cloud_function_payment_webhook.py)が同種の3分岐を`classify_payment_succeeded()`
として実装済みで、本モジュールはその考え方を本ventureの状態モデルに合わせて移植する。

line-reservation-aiとの違い(移植にあたっての設計判断):
- line-reservation-aiは`suspension_reason`(文字列、"payment_failed"/"trial_unselected"等
  複数の休止要因を区別する)と`sent_event_keys`(検知通知・リマインド等、送信済み通知の
  集合)を持つが、本ventureはpayment-failure-dunning-design.md 1節で確認済みの通り
  「制限モード」以外の休止理由が存在しないため、`payment_suspended_at`(設定有無のみの
  2値)と`payment_failure_reminder_sent_at`(リマインド1通のみの送信済みフラグ)という
  単純な状態しか持たない。`suspension_reason`のような複数要因区別は不要。
- line-reservation-aiは猶予期間中の「検知通知」自体を送信する経路
  (cloud_function_send_dunning_notifications.py)を既に持ち、`sent_event_keys`に
  "detected"が記録されるため、それを「猶予期間中に一度でも通知済みか」の判定に使えた。
  一方、本ventureはdesign 4節「決済失敗検知時」の通知を実際に送信する配線がまだ
  実装されておらず(design 6節「残課題」参照、次回以降の課題のまま)、
  `payment_failure_detected_at`が設定されていても業者はまだ何も知らされていない
  可能性が高い。したがって本モジュールでは「猶予期間中に一度でも通知済みか」の判定を
  `payment_failure_reminder_sent_at`の設定有無のみで行う(現時点で本venture唯一の
  送信済みフラグのため)。これはline-reservation-aiより単純化したというより、検知時
  通知の送信配線自体が本venture側でまだ存在しないという実装状況をそのまま反映した
  結果であり、検知時通知の送信配線が実装された際は、その送信済みを示す新規フラグも
  この判定に含める拡張が必要になる(下記「今後の課題」参照)。

位置づけ:
- 実際のWebhook受信・LINE Push Message APIでの送信・決済代行サービスとの契約はいずれも
  オーナー承認待ち(pending-approval.md参照)。本モジュールはそれとは別に、「決済成功時に
  どの通知を送るべきか(あるいは送らないべきか)」の判定ロジックと、送信・状態リセットの
  配線を実クラウド接続なしで検証可能にしたもの。
- `PaymentFailureReminderUserState`(payment_failure_reminder_scheduler.py)をそのまま
  入力状態として再利用する(同じ3フィールド(payment_failure_detected_at・
  payment_suspended_at・payment_failure_reminder_sent_at)を参照するだけのため、
  新規dataclassは起こさない)。
- 状態リセット自体はpayment_failure.pyの`clear_payment_failure_on_success()`をそのまま
  呼び出す(3フィールドを一括でクリアする既存の冪等ロジックを再利用し、本モジュールでは
  独自にクリア処理を書かない)。

今後の課題:
- design 4節「決済失敗検知時」の通知を実際に送信する配線(段階1)自体が本venture未実装の
  ままであり、実装された場合は「送信済みか」を示す新規フラグをOUTCOME_CONFIRMED_IN_GRACE
  判定に含める拡張が必要になる(上記説明参照)。
- 実際のStripe Webhook `invoice.payment_succeeded`受信エンドポイントからの呼び出し配線
  (stripe_dispatch.pyのdispatch_stripe_event()への接続、あるいは専用のCloud Function化)
  は本モジュールの対象外で次回以降の課題として残る。

設計の参照元: payment-failure-dunning-design.md 4節,
line-reservation-ai prototype/cloud_function_payment_webhook.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from payment_failure import PaymentFailureStoreProtocol, clear_payment_failure_on_success
from payment_failure_reminder_scheduler import PaymentFailureReminderUserState

# classify_payment_recovery()が返す分類。line-reservation-aiのOUTCOME_*と対称の命名。
OUTCOME_RECOVERED_FROM_SUSPENSION = "recovered_from_suspension"
OUTCOME_CONFIRMED_IN_GRACE = "confirmed_in_grace"
OUTCOME_SILENT_RESET = "silent_reset"
OUTCOME_NO_DUNNING = "no_dunning"

# handle_payment_succeeded()のみが返す、送信失敗を表す分類。
OUTCOME_SEND_FAILED = "send_failed"


def classify_payment_recovery(state: PaymentFailureReminderUserState) -> str:
    """`invoice.payment_succeeded`受信時、状態から4種類のいずれに該当するかを判定する。

    - `payment_suspended_at`が設定済み → 制限モード(段階3)からの復旧。
      「生成を再開しました」と案内する(PAYMENT_RECOVERED_MESSAGE)。
    - `payment_failure_detected_at`が未設定 → そもそも決済失敗を検知したことがない
      通常の毎月課金成功。通知不要(OUTCOME_NO_DUNNING)。
    - 上記いずれでもなく`payment_failure_reminder_sent_at`が設定済み → 猶予期間中
      (段階2)にリマインドを受け取った後の決済成功。生成は止まっていないため「再開」とは
      書かず「解消しました」と案内する(PAYMENT_CONFIRMED_IN_GRACE_MESSAGE)。
    - 上記いずれでもない(検知はされているがリマインド未送信) → 本ventureにはまだ
      当該ユーザーへ届いた通知が(現状の実装上)存在しないため、通知せず状態のみ
      リセットする(OUTCOME_SILENT_RESET)。
    """
    if state.payment_suspended_at is not None:
        return OUTCOME_RECOVERED_FROM_SUSPENSION
    if state.payment_failure_detected_at is None:
        return OUTCOME_NO_DUNNING
    if state.payment_failure_reminder_sent_at is not None:
        return OUTCOME_CONFIRMED_IN_GRACE
    return OUTCOME_SILENT_RESET


# ---------------------------------------------------------------------------
# メッセージ文言(design 4節)
# ---------------------------------------------------------------------------

PAYMENT_RECOVERY_ALT_TEXT = "[エアコンパシャッと] お支払いを確認しました"

# design 4節「決済成功による復旧時」の文言をそのまま使う(制限モードから復旧した場合のみ)。
PAYMENT_RECOVERED_MESSAGE = (
    "お支払いを確認しました。\n\n"
    "お支払い手続きが完了しました。作業完了報告・お手入れ案内の生成を再開しましたので、"
    "引き続きよろしくお願いします。"
)

# 猶予期間中(まだ生成は止まっていない)にリマインドを受け取った後、決済が成功した場合専用の
# 文言。GENERATION_PAUSED_MESSAGE等と同じ「実際には止まっていないものを止まっていたかの
# ように書かない」という配慮から、PAYMENT_RECOVERED_MESSAGEの「再開しました」ではなく
# 「解消されました」と表現を分ける(line-reservation-aiのrender_payment_confirmed_in_
# grace_message()と同じ考え方)。
PAYMENT_CONFIRMED_IN_GRACE_MESSAGE = (
    "お支払いを確認しました。\n\n"
    "先日ご案内したお支払いに関するご確認事項は解消されました。作業完了報告・お手入れ案内は"
    "引き続きご利用いただけますので、このままご利用ください。"
)


def _build_flex_message(body_text: str) -> dict:
    """design 4節の文言をFlex Message化する。他の段階(検知時・リマインド・制限モード
    移行時)と異なりCTAボタンは付けない(design 4節の該当文言自体にボタンの案内がなく、
    支払いが解決した後に案内すべき操作が存在しないため)。footerを持たないbubbleのみの
    シンプルな構成とする。"""
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


def build_payment_recovered_flex_message() -> dict:
    """OUTCOME_RECOVERED_FROM_SUSPENSION向けのFlex Message。"""
    return _build_flex_message(PAYMENT_RECOVERED_MESSAGE)


def build_payment_confirmed_in_grace_flex_message() -> dict:
    """OUTCOME_CONFIRMED_IN_GRACE向けのFlex Message。"""
    return _build_flex_message(PAYMENT_CONFIRMED_IN_GRACE_MESSAGE)


# ---------------------------------------------------------------------------
# 実送信配線
# ---------------------------------------------------------------------------


class LinePushDeliveryError(Exception):
    """LINE Push Message API呼び出し失敗(タイムアウト・5xx・429等)を表す。
    他スケジューラのLinePushDeliveryErrorと対称の位置づけ。"""


class LinePushClient(Protocol):
    def send_flex_message(self, user_id: str, alt_text: str, contents: dict) -> None:
        ...


class InMemoryLinePushClient:
    """実LINE Push Message API接続の代わりに送信内容を記録するだけの検証用クライアント
    (他スケジューラのInMemoryLinePushClientと同じ位置づけ)。"""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, dict]] = []

    def send_flex_message(self, user_id: str, alt_text: str, contents: dict) -> None:
        self.sent.append((user_id, alt_text, contents))


@dataclass
class PaymentRecoveryResult:
    """1回の`invoice.payment_succeeded`処理の結果(呼び出し側のログ・HTTPステータス
    判断用、line-reservation-aiのPaymentSucceededResultと対称)。

    outcomeがOUTCOME_SEND_FAILEDの場合、状態は変更されていないため呼び出し側は
    5xxを返してWebhookのリトライに委ねる。"""

    outcome: str
    notified: bool = False
    state_reset: bool = False


def handle_payment_succeeded(
    state: PaymentFailureReminderUserState,
    store: PaymentFailureStoreProtocol,
    push_client: LinePushClient,
) -> PaymentRecoveryResult:
    """`invoice.payment_succeeded`受信時(`stripe_customer_id → user_id`逆引き後)に呼ぶ
    処理本体。引数のstateは呼び出し元でFirestoreから読み取った当該ユーザーの現在状態を
    想定する(実際の書き戻しはstore経由で本関数が行う)。

    送信に失敗した場合は状態を一切変更せずにOUTCOME_SEND_FAILEDを返す。呼び出し側が
    HTTP 5xxを返してWebhookリトライに委ねれば、次の再送で同じ分岐に入り再送信される
    (line-reservation-aiのhandle_payment_succeeded()と同じ設計)。Webhook再送時は
    状態リセット済みのためOUTCOME_NO_DUNNINGに落ち、通知が二重に届かない冪等性が
    状態そのものから自然に担保される点も同じ。
    """
    outcome = classify_payment_recovery(state)

    if outcome == OUTCOME_NO_DUNNING:
        return PaymentRecoveryResult(outcome=outcome)

    if outcome == OUTCOME_SILENT_RESET:
        clear_payment_failure_on_success(store, state.user_id)
        return PaymentRecoveryResult(outcome=outcome, state_reset=True)

    contents = (
        build_payment_recovered_flex_message()
        if outcome == OUTCOME_RECOVERED_FROM_SUSPENSION
        else build_payment_confirmed_in_grace_flex_message()
    )

    try:
        push_client.send_flex_message(state.user_id, PAYMENT_RECOVERY_ALT_TEXT, contents)
    except LinePushDeliveryError:
        return PaymentRecoveryResult(outcome=OUTCOME_SEND_FAILED)

    clear_payment_failure_on_success(store, state.user_id)
    return PaymentRecoveryResult(outcome=outcome, notified=True, state_reset=True)


def _demo() -> None:
    from datetime import datetime, timezone

    from user_id_linking import InMemoryUserProfileStore, UserProfile

    _EVENT_TIME = datetime(2026, 8, 28, 9, 0, 0, tzinfo=timezone.utc)
    push = InMemoryLinePushClient()

    def _store_with_user(user_id: str, **overrides) -> InMemoryUserProfileStore:
        store = InMemoryUserProfileStore()
        store.save(
            user_id,
            UserProfile(
                business_name="テスト洗浄社",
                business_type="独立系",
                email="test@example.com",
                linked_at=_EVENT_TIME,
                **overrides,
            ),
        )
        return store

    # 1) 制限モードからの復旧: 「再開しました」の案内が届き、状態が初期化される。
    store1 = _store_with_user(
        "u1",
        payment_failure_detected_at=_EVENT_TIME,
        payment_suspended_at=_EVENT_TIME,
    )
    state1 = PaymentFailureReminderUserState(
        user_id="u1",
        payment_failure_detected_at=_EVENT_TIME,
        payment_suspended_at=_EVENT_TIME,
    )
    print("1) 制限モードからの復旧:", handle_payment_succeeded(state1, store1, push))

    # 2) 猶予期間中(リマインド送信済み)の決済成功: 「解消されました」の案内が届く。
    store2 = _store_with_user(
        "u2",
        payment_failure_detected_at=_EVENT_TIME,
        payment_failure_reminder_sent_at=_EVENT_TIME,
    )
    state2 = PaymentFailureReminderUserState(
        user_id="u2",
        payment_failure_detected_at=_EVENT_TIME,
        payment_failure_reminder_sent_at=_EVENT_TIME,
    )
    print("2) 猶予期間中(リマインド後)の決済成功:", handle_payment_succeeded(state2, store2, push))

    # 3) 猶予期間中(まだ何も送信していない)の決済成功: 通知せず状態のみリセット。
    store3 = _store_with_user("u3", payment_failure_detected_at=_EVENT_TIME)
    state3 = PaymentFailureReminderUserState(
        user_id="u3", payment_failure_detected_at=_EVENT_TIME
    )
    print("3) 猶予期間中(未通知)の決済成功:", handle_payment_succeeded(state3, store3, push))

    # 4) 決済失敗を検知したことがない通常の課金成功: 何もしない。
    store4 = _store_with_user("u4")
    state4 = PaymentFailureReminderUserState(user_id="u4", payment_failure_detected_at=None)
    print("4) 通常の課金成功:", handle_payment_succeeded(state4, store4, push))

    print("送信済みログ件数:", len(push.sent))
    for _, alt_text, contents in push.sent:
        print("---", alt_text)
        print(contents["body"]["contents"][0]["text"])


if __name__ == "__main__":
    _demo()
