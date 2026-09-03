#!/usr/bin/env python3
"""
blocked-but-billing-owner-email-notification-design.md(フェーズ続き177)で設計した、
「オーナー自身が店舗の公式LINEアカウントをブロック(unfollow)しているにもかかわらず
契約(サブスクリプション)が継続している」店舗のオーナーへ、LINEの代わりにメールで
通知するためのロジックを実装したもの。

位置づけ:
- blocked_but_billing_candidates.py`list_blocked_but_billing_candidates()`が洗い出した
  候補store_idのうち、まだ通知していない(かつ通知先メールアドレスが登録済みの)ものだけを
  選び、メール件名・本文を組み立て、送信結果に応じて冪等性フラグを更新するCloud Function
  本体相当。aircon-pasha/blocked_but_billing_owner_notification.pyの
  `send_blocked_but_billing_owner_notifications()`と同じ構成だが、通知チャネルがLINE
  Flex MessageではなくメールであるためEmailSenderProtocolを新設した点が異なる
  (design 0節: 本ventureはオーナー自身がブロックした対象そのものであるためLINE経由の
  通知が原理的に使えない)。
- `EmailSenderProtocol`の実装本体(実際のメール配信基盤〈SendGrid・Gmail API等〉への
  接続)は、外部サービスとの接続・実際の送信操作を伴うためオーナー承認待ちの範囲とし、
  本モジュールでは対象外とする(design 4節)。

設計の参照元: blocked-but-billing-owner-email-notification-design.md
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Protocol

from blocked_but_billing_candidates import (
    BlockedButBillingCandidateStoreProtocol,
    list_blocked_but_billing_candidates,
)


@dataclass(frozen=True)
class EmailContent:
    """design 2節の件名・本文の組み。"""

    subject: str
    body: str


def build_blocked_but_billing_owner_email(store_id: str) -> EmailContent:
    """design 2節: 件名+プレーンテキスト本文のメール内容を組み立てる。
    (1)何が起きているか、(2)何が困るか、(3)対処方法、の3点を含む。"""
    if not store_id:
        raise ValueError("store_id must be a non-empty string")

    subject = f"【要確認】店舗のLINE公式アカウントがブロックされたままです(store_id: {store_id})"
    body = (
        "この度は本サービスをご利用いただきありがとうございます。\n\n"
        "オーナー様ご自身が、店舗の公式LINEアカウントをブロック(またはフォロー解除)"
        "されたまま、ご契約が継続していることを確認いたしました。\n\n"
        "ブロック中は、予約確定・無断キャンセル確認等の業務通知がオーナー様に届かなく"
        "なっております。お心当たりがない場合は誤操作の可能性がございますので、"
        "お手数ですが公式LINEアカウントのブロックを解除いただきますようお願いいたします。\n\n"
        "ご不明点がございましたら本メールにご返信ください。"
    )
    return EmailContent(subject=subject, body=body)


class EmailOwnerNotificationStoreProtocol(BlockedButBillingCandidateStoreProtocol, Protocol):
    """`stores/{storeId}`ドキュメントのうち、候補抽出条件(親Protocol)に加えて
    送信先(`ownerEmail`)・冪等性フラグ(`blockedButBillingOwnerNotifiedAt`)を
    対象にしたインターフェース(design 1節・3節)。`store_profile_store.
    StoreProfileStoreProtocol`(ひいては`InMemoryStoreProfileStore`)はこれらの
    メソッドを既に持つため、構造的に(duck typing)本Protocolを満たす。
    """

    def get_owner_email(self, store_id: str) -> Optional[str]:
        ...

    def get_blocked_but_billing_owner_notified_at(self, store_id: str) -> Optional[str]:
        ...

    def set_blocked_but_billing_owner_notified_at(
        self, store_id: str, value: Optional[str]
    ) -> None:
        ...


def select_new_blocked_but_billing_candidates_for_email_notification(
    store: EmailOwnerNotificationStoreProtocol,
) -> List[str]:
    """design 3節: 「候補である」かつ「まだ通知していない」かつ「通知先メールアドレスが
    登録済み」のstore_idのみを返す(digest形式ではなく1店舗=1回の個別メール)。
    結果は`list_blocked_but_billing_candidates()`と同じくstore_id昇順。"""
    return [
        store_id
        for store_id in list_blocked_but_billing_candidates(store)
        if store.get_blocked_but_billing_owner_notified_at(store_id) is None
        and store.get_owner_email(store_id)
    ]


class EmailSenderProtocol(Protocol):
    """実際のメール配信基盤への接続を抽象化する薄いProtocol。design 4節の通り、
    具象実装(SendGrid・Gmail API等への接続)はオーナー承認待ちの範囲であり本モジュール
    には含まれない。呼び出し元は送信の成否のみを`bool`で受け取る。"""

    def send(self, to_email: str, subject: str, body: str) -> bool:
        ...


class BlockedButBillingOwnerNotifiedAtStoreProtocol(Protocol):
    """design 5節「クリア配線」(フェーズ続き178)が使う、
    `blocked_but_billing_owner_notified_at`の読み書き両方のみを要求する最小限の
    Protocol(aircon-pashaフェーズ175の同名Protocolと同じ考え方)。
    `store_profile_store.StoreProfileStoreProtocol`(ひいては`InMemoryStoreProfileStore`)は
    このメソッドを既に持つため、構造的に(duck typing)本Protocolを満たす。
    """

    def get_blocked_but_billing_owner_notified_at(self, store_id: str) -> Optional[str]:
        ...

    def set_blocked_but_billing_owner_notified_at(
        self, store_id: str, value: Optional[str]
    ) -> None:
        ...


def clear_blocked_but_billing_owner_notified_at(
    store: BlockedButBillingOwnerNotifiedAtStoreProtocol, store_id: str,
) -> bool:
    """design 5節「クリア配線」(フェーズ続き178): 「フォロー再開」(`owner_is_following`が
    `True`に戻る)、または「解約確定」(`customer.subscription.deleted`受信で
    `suspension_reason`が`"cancelled"`になる)のいずれかが起きた時点で呼ぶ。
    `blocked_but_billing_owner_notified_at`が設定済みの場合のみクリアし、変更があったか
    どうか(`True`/`False`)を返す(aircon-pashaフェーズ175の同名関数と同じ、呼び出し側が
    ログ確認できる冪等設計)。未設定(そもそも一度も通知対象になったことがない、または
    既にクリア済み)の場合は何もせず`False`を返す。

    フォロー再開側の呼び出し配線は`cloud_function_process_event.
    ConversationEventProcessor.process_follow_event()`から行う。解約確定側は、本venture
    の`cloud_function_subscription_cancelled_webhook.py`が`store_profile_store`のような
    store_id keyed Protocolではなく1件ぶんの`StoreSubscriptionState`(呼び出し元が既に
    Firestoreから読み込んだ状態)を直接書き換える設計のため、本関数はそちらからは呼ばず、
    `handle_subscription_deleted()`内で同じ「設定済みの場合のみクリアしTrue/Falseを返す」
    ロジックを`state`オブジェクトの属性書き換えとしてインライン実装している(design 5節)。
    """
    if store.get_blocked_but_billing_owner_notified_at(store_id) is None:
        return False
    store.set_blocked_but_billing_owner_notified_at(store_id, None)
    return True


def send_blocked_but_billing_owner_email_notifications(
    store: EmailOwnerNotificationStoreProtocol,
    email_sender: EmailSenderProtocol,
    *,
    notified_at: str,
) -> List[str]:
    """design 3節・4節のCloud Function本体相当。3節の対象store_idごとにメールを送信し、
    成功した場合のみ`blocked_but_billing_owner_notified_at`を`notified_at`で書き込む
    (送信失敗時は書き込まず次回実行時に自然に再試行対象として残る、既存の全通知バッチと
    同じ方式)。送信に成功したstore_idの一覧を返す。"""
    if not notified_at:
        raise ValueError("notified_at must be a non-empty string")

    sent_store_ids: List[str] = []
    for store_id in select_new_blocked_but_billing_candidates_for_email_notification(store):
        owner_email = store.get_owner_email(store_id)
        content = build_blocked_but_billing_owner_email(store_id)
        if email_sender.send(owner_email, content.subject, content.body):
            store.set_blocked_but_billing_owner_notified_at(store_id, notified_at)
            sent_store_ids.append(store_id)
    return sent_store_ids
