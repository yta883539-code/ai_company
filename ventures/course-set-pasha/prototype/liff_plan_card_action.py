#!/usr/bin/env python3
"""liff-plan-selection-ui-wireframe.md「未確定・今後の課題」に残っていた、プラン変更
(アップグレード/ダウングレード)時に本画面を再利用するか専用画面を別途設けるかという
未検討事項に対応する。

設計判断: 専用画面を新設せず、既存のLIFFプラン選択画面(liff-plan-selection-ui-
wireframe.md)を再利用する。ただし各プランカードの「このプランを選ぶ」ボタンの遷移先を、
現在の契約状態(get_plan()の値)で分岐させる。

- 未契約(get_plan()未設定、トライアル中): タップしたカードのプランで
  create_checkout_session()(checkout_session.py)へ遷移する。新規契約のため既存の
  遷移・パラメータ設計(plan=<プラン名>)をそのまま使う。
- 契約中で選択カードが現在のプランと同じ: 何もする必要がない状態のため、ボタンは
  無効化し「ご利用中」ラベルに差し替える。
- 契約中で選択カードが現在のプランと異なる(アップグレード/ダウングレード):
  `mode="subscription"`のCheckout Sessionは常に新規サブスクリプションを作成するため、
  既に契約中のユーザーに使うと二重契約になってしまう。そのため
  subscription-plan-change-design.mdが既に前提とするStripeカスタマーポータル
  (create_portal_session()、portal_session.py)へ遷移する。ポータル側でのプラン切り替え後は
  `customer.subscription.updated`Webhookがsubscription-plan-change-design.mdの経路で
  `plan`を自動更新するため、本画面側で遷移先プランをポータルへパラメータとして渡す必要は
  ない(ポータルの画面上でユーザー自身が選ぶ)。

設計の参照元: liff-plan-selection-ui-wireframe.md、subscription-plan-change-design.md、
checkout-session-plan-selection-design.md。
"""

from __future__ import annotations

from typing import Literal, Optional

PlanCardAction = Literal["start_checkout", "open_portal", "current_plan"]


def resolve_plan_card_action(
    current_plan: Optional[str], card_plan: str
) -> PlanCardAction:
    """プラン選択画面の各カードの「このプランを選ぶ」ボタンをタップした際の遷移先を返す。

    `current_plan`は`UsageStatusProfileStoreProtocol.get_plan(user_id)`
    (liff_usage_status.py)の返り値をそのまま渡す想定(未契約はNone)。
    `card_plan`はカードが表す`PLAN_MONTHLY_LIMITS`のキー。
    """
    if current_plan is None:
        return "start_checkout"
    if current_plan == card_plan:
        return "current_plan"
    return "open_portal"
