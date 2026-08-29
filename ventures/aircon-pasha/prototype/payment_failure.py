#!/usr/bin/env python3
"""
payment-failure-dunning-design.md(フェーズ139)3・6節で設計した、決済失敗検知〜猶予期間
〜制限モードの状態遷移のうち、Stripe Webhook(`invoice.payment_failed`・
`invoice.payment_succeeded`)受信時に`user_profile`の状態を更新する部分を実行可能な
コードに落とし込んだもの。

位置づけ:
- 猶予期間(7日)終了後に制限モード(`payment_suspended_at`)へ自動移行させるスケジューラ
  (design 6節「残課題」)、および`_is_generation_paused()`の判定条件拡張・制限モード
  専用メッセージの`process_memo_event()`への配線(design 3節)はいずれも本モジュールの
  対象外で、次回以降の課題として残る。猶予期間終了直前リマインドの送信は
  payment_failure_reminder_scheduler.py(フェーズ143)で対応済みで、本モジュールの
  `clear_payment_failure_on_success()`はそのリマインド送信済みフラグ
  (`payment_failure_reminder_sent_at`)もあわせてクリアする(次回の決済失敗検知時に
  再びリマインド対象となるようにするため)。design 4節末尾で触れた「猶予期間中に決済が
  成功した場合の
  復旧通知の3分岐(制限モードからの復旧/猶予期間中の完了通知/状態リセットのみ)」の
  文言出し分けも、実際のWebhook受信配線(LINE通知送信)実装時の課題として本モジュールでは
  扱わない。
- deletion_candidate.pyと同じ位置づけで、Webhookイベント種別を受け取った"後"に呼ばれる
  中身の判断・データ更新ロジックのみを、実Firestore接続なしで検証可能な純粋関数として
  実装する。`PaymentFailureStoreProtocol`はdeletion_candidate.pyの
  `ProfileDeletionCandidateStoreProtocol`と同じ「`user_profile`の一部フィールドのみを
  対象にした薄いインターフェース」で、design 6節の「`UserProfile`・
  `UserProfileStoreProtocol`への状態フィールド追加」方針に沿い、専用のInMemoryスタブは
  新設せずuser_id_linking.pyの`InMemoryUserProfileStore`が構造的に(duck typing)本
  Protocolを満たす形にした(deletion_candidate.pyのように別系統のdictを持つ専用ストアを
  新設すると、実Firestore接続時に同一`user_profile`ドキュメントのフィールドが2つの
  ストアオブジェクトに分裂して見える設計になってしまうため)。
- `handle_payment_failure_detected()`(フェーズ147追加)は、design 6節に残っていた
  「決済失敗検知時(段階1)通知の実送信配線」に対応したもの。design 4節「決済失敗検知時
  (猶予期間開始)」の文言をpayment_failure_reminder_scheduler.pyと同じFlex Message形式
  (UPDATE_PAYMENT_METHOD_BUTTON_LABEL/POSTBACK_DATAのボタン付き)で組み立て、送信成功時
  のみ`mark_payment_failure_detected()`を呼ぶ(handle_payment_succeeded()と対称に、
  送信失敗時は状態を変更せずWebhookリトライに委ねる設計)。`invoice.payment_succeeded`側の
  `handle_payment_succeeded()`(payment_recovery_notification.py、フェーズ146)は、
  モジュールごとに`LinePushDeliveryError`を別クラスとして定義している既存の慣習上、本
  モジュールの`LinePushDeliveryError`とは別クラスのままである点に注意(1回の
  `dispatch_stripe_event()`呼び出しではイベント種別ごとにどちらか一方のみが実行される
  ため実害はないが、将来的に両者を1つの実push_clientへ統合する際は例外クラスの
  共通化を検討する必要がある)。

設計の参照元: payment-failure-dunning-design.md 3・4・6節
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol

from cloud_function_webhook import (  # noqa: E402
    UPDATE_PAYMENT_METHOD_BUTTON_LABEL,
    UPDATE_PAYMENT_METHOD_POSTBACK_DATA,
)


class PaymentFailureStoreProtocol(Protocol):
    """`user_profile/{user_id}`ドキュメントのうち`payment_failure_detected_at`・
    `payment_suspended_at`・`payment_failure_reminder_sent_at`(フェーズ143追加)の
    3フィールドのみを対象にした薄いインターフェース。"""

    def get_payment_failure_detected_at(self, user_id: str) -> Optional[datetime]:
        ...

    def set_payment_failure_detected_at(
        self, user_id: str, value: Optional[datetime]
    ) -> None:
        ...

    def get_payment_suspended_at(self, user_id: str) -> Optional[datetime]:
        ...

    def set_payment_suspended_at(self, user_id: str, value: Optional[datetime]) -> None:
        ...

    def get_payment_failure_reminder_sent_at(self, user_id: str) -> Optional[datetime]:
        ...

    def set_payment_failure_reminder_sent_at(
        self, user_id: str, value: Optional[datetime]
    ) -> None:
        ...


def mark_payment_failure_detected(
    store: PaymentFailureStoreProtocol, user_id: str, event_time: datetime,
) -> datetime:
    """design 3・4節「決済失敗検知時(猶予期間開始)」: `invoice.payment_failed`受信時
    (`stripe_customer_id → user_id`の逆引き後)に呼ぶ。猶予期間の起点として`event_time`を
    そのまま`payment_failure_detected_at`へ書き込む(猶予期間7日の判定自体は次回以降の
    スケジューラ側で行う想定で、本関数は起点日時の記録のみを担う)。Stripeスマートリトライに
    よる複数回の失敗連続通知(design 2節)でも、既に設定済みなら最新の失敗日時で上書きする
    (deletion_candidate.pyのmark_deletion_candidate_on_subscription_deleted()と同じ
    「安全側」判断)。`payment_suspended_at`には触れない(猶予期間中の再失敗で制限モードへ
    飛び級させない)。書き込んだ値を返す。
    """
    store.set_payment_failure_detected_at(user_id, event_time)
    return event_time


def clear_payment_failure_on_success(
    store: PaymentFailureStoreProtocol, user_id: str,
) -> bool:
    """design 4節「決済成功による復旧時」: `invoice.payment_succeeded`受信時
    (逆引き後)に呼ぶ。`payment_failure_detected_at`・`payment_suspended_at`・
    `payment_failure_reminder_sent_at`(フェーズ143追加)の3フィールドすべてをクリア
    する(段階を問わず通常運用へ復帰させ、次回の決済失敗検知時に再びリマインド対象と
    なるようにする)。いずれか1つでも設定済みだった場合に`True`を返す
    (deletion_candidate.pyのclear_deletion_candidate_on_subscription_reactivated()と
    同じ、呼び出し側がログ確認できる冪等設計)。すべて未設定(決済失敗を検知したことが
    一度もない通常のユーザー)の場合は何もせず`False`を返す。
    """
    was_failure_detected = store.get_payment_failure_detected_at(user_id) is not None
    was_suspended = store.get_payment_suspended_at(user_id) is not None
    was_reminder_sent = (
        store.get_payment_failure_reminder_sent_at(user_id) is not None
    )
    if not was_failure_detected and not was_suspended and not was_reminder_sent:
        return False
    store.set_payment_failure_detected_at(user_id, None)
    store.set_payment_suspended_at(user_id, None)
    store.set_payment_failure_reminder_sent_at(user_id, None)
    return True


# ---------------------------------------------------------------------------
# 決済失敗検知時(段階1)の実送信配線(design 4・6節、フェーズ147追加)
# ---------------------------------------------------------------------------


class LinePushDeliveryError(Exception):
    """LINE Push Message API呼び出し失敗(タイムアウト・5xx・429等)を表す。
    他モジュール(payment_failure_reminder_scheduler等)のLinePushDeliveryErrorと対称の
    位置づけ(モジュールごとに別クラスとする既存の慣習を踏襲、本ファイル冒頭のdocstring
    参照)。"""


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


PAYMENT_FAILURE_DETECTED_ALT_TEXT = "[エアコンパシャッと] お支払いの確認をお願いします"

# design 4節「決済失敗検知時(猶予期間開始)」の文言。GENERATION_PAUSED_MESSAGE等と同じく
# 本文中に生URLを埋め込まずボタン(postback)を別途添付する形に揃える。
PAYMENT_FAILURE_DETECTED_BODY_TEXT = (
    "いつもご利用ありがとうございます。今回のお支払い手続きが完了できませんでした"
    "(カードの有効期限切れ・利用限度額等が考えられます)。\n\n"
    "現在、作業完了報告・お手入れ案内の生成は通常どおりご利用いただけます。"
    "7日以内にお支払い方法をご確認・更新いただけますようお願いします。"
)


def build_payment_failure_detected_flex_message() -> dict:
    """design 4節の文言をFlex Messageのボタン込みで組み立てる
    (payment_failure_reminder_scheduler.build_payment_failure_reminder_flex_message()と
    同じ構成)。ボタンのlabel・postbackデータはcloud_function_webhook.pyの
    UPDATE_PAYMENT_METHOD_BUTTON_LABEL・UPDATE_PAYMENT_METHOD_POSTBACK_DATAをそのまま
    再利用する。"""
    return {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": PAYMENT_FAILURE_DETECTED_ALT_TEXT,
                    "wrap": True,
                    "weight": "bold",
                },
                {
                    "type": "text",
                    "text": PAYMENT_FAILURE_DETECTED_BODY_TEXT,
                    "wrap": True,
                    "margin": "md",
                },
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "action": {
                        "type": "postback",
                        "label": UPDATE_PAYMENT_METHOD_BUTTON_LABEL,
                        "data": UPDATE_PAYMENT_METHOD_POSTBACK_DATA,
                    },
                }
            ],
        },
    }


@dataclass
class PaymentFailureDetectionResult:
    """1回の`invoice.payment_failed`処理の結果(呼び出し側のログ・HTTPステータス判断用、
    payment_recovery_notification.PaymentRecoveryResultと対称)。

    `notified=False`の場合(送信失敗)、`payment_failure_detected_at`は変更されていない
    ため呼び出し側は5xxを返してWebhookのリトライに委ねる(次の再送で送信・状態書き込みが
    セットで再試行される)。"""

    notified: bool
    event_time: Optional[datetime] = None


def handle_payment_failure_detected(
    store: PaymentFailureStoreProtocol,
    user_id: str,
    event_time: datetime,
    push_client: LinePushClient,
) -> PaymentFailureDetectionResult:
    """design 4・6節「決済失敗検知時(段階1)通知の実送信配線」本体。
    `invoice.payment_failed`受信時(`stripe_customer_id → user_id`逆引き後)に呼ぶ。

    通知の送信に成功した場合のみ`mark_payment_failure_detected()`で状態を書き込む
    (handle_payment_succeeded()と対称に、送信失敗時は状態を一切変更せず
    `PaymentFailureDetectionResult(notified=False)`を返す。呼び出し側がHTTP 5xxを返して
    Webhookリトライに委ねれば、次の再送で送信・状態書き込みが再試行される)。"""
    contents = build_payment_failure_detected_flex_message()
    try:
        push_client.send_flex_message(user_id, PAYMENT_FAILURE_DETECTED_ALT_TEXT, contents)
    except LinePushDeliveryError:
        return PaymentFailureDetectionResult(notified=False)

    mark_payment_failure_detected(store, user_id, event_time)
    return PaymentFailureDetectionResult(notified=True, event_time=event_time)
