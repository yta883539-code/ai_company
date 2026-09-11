#!/usr/bin/env python3
"""
blocked-but-billing-detection-design.md(フェーズ80)で設計した、「契約者(LINE)が
ブロック(unfollow)しているにもかかわらず契約(サブスクリプション)が継続している」
workshopを洗い出す候補検知ロジックを実装したもの。

位置づけ:
- unfollow-billing-faq.md「今後の課題」に残っていた「『ブロック中かつ契約継続中』契約者の
  検知手段(他venture3件のblocked-but-billing-detection-design.md相当)の設計・実装は、
  その前提となるStripe Webhook受信・`user_profile`の`is_following`相当フィールドの追加
  自体が本venture未着手のため、それらの実装後の課題として残る」に対応する最初の一歩。
  Stripe Webhook受信(stripe_webhook.py)は既に実装済みのため、本フェーズでは残る前提
  だった`is_following`フィールドの追加(usage_counter_workshop.py参照)とあわせて着手した。
- 本モジュールが行うのは「候補workshop_idの洗い出し」のみで、洗い出した候補への実際の通知
  (オーナーへのメール送信・Slack通知等)は行わない。aircon-pasha/prototype/
  blocked_but_billing_candidates.pyの`list_blocked_but_billing_candidates()`と同じ
  「読み出し専用の候補リスト関数」という位置づけ。
- aircon-pasha等(1事業者=1契約)と異なり、本ventureは契約単位が`craftsman_workshop`
  (workshop)であり、フォロー状態(`is_following`)を持つのはLINE user_id(個人)、
  契約状態(`subscription_status`)を持つのはworkshopという2段構えになる。design 2節の
  通り、通知対象・課金関連通知の宛先は常に契約者(`contractor_user_id`)に限定される
  (subscription-cancellation-notification-design.md以来の一貫した方針)ため、本検知も
  「契約者本人がブロック中かどうか」のみを判定対象とし、契約者以外のメンバーのブロック
  状態は対象外とする(design 1節)。返り値もuser_idではなくworkshop_id(通知組み立て時に
  `get_contractor_user_id()`・`get_member_display_name()`等で契約者情報を引き直せる形)
  とする。

設計の参照元: blocked-but-billing-detection-design.md
"""

from __future__ import annotations

from typing import Iterable, List, Protocol


class BlockedButBillingCandidateWorkshopStoreProtocol(Protocol):
    """`craftsman_workshop/{workshop_id}`ドキュメントのうち`contractor_user_id`・
    `subscription_status`フィールドのみを対象にした薄いインターフェース(design 2節)。
    `usage_counter_workshop.WorkshopStoreProtocol`(ひいては`InMemoryWorkshopStore`)は
    これらのメソッドを既に持つため、構造的に(duck typing)本Protocolを満たす。
    """

    def get_contractor_user_id(self, workshop_id: str) -> str:
        ...

    def get_subscription_status(self, workshop_id: str) -> str:
        ...

    def all_workshop_ids(self) -> Iterable[str]:
        ...


class BlockedButBillingCandidateProfileStoreProtocol(Protocol):
    """`user_profile/{user_id}.is_following`のみを対象にした薄いインターフェース。
    `usage_counter_workshop.UserProfileStoreProtocol`(ひいては`InMemoryUserProfileStore`)は
    このメソッドを既に持つため、構造的に(duck typing)本Protocolを満たす。
    """

    def get_is_following(self, user_id: str) -> bool:
        ...


def list_blocked_but_billing_candidates(
    workshop_store: BlockedButBillingCandidateWorkshopStoreProtocol,
    profile_store: BlockedButBillingCandidateProfileStoreProtocol,
) -> List[str]:
    """design 2節: 契約者(`contractor_user_id`)の`is_following`が`False`、かつ
    workshopの`subscription_status`が`"canceled"`ではない(=trialing/active/past_due
    いずれか、まだ何らかの形で課金対象または課金候補である)workshop_idの一覧を返す。

    `subscription_status`を「契約継続中」の判定根拠に使うのは、`plan_id`が解約後も
    workshop作成時の値のまま残り続ける(`set_plan`は`checkout.session.completed`時の
    上書き専用でクリア操作を持たない、craftsman-account-linking-design.md 7節参照)ため
    契約有無の判定に使えない一方、`subscription_status`は`customer.subscription.deleted`
    受信時に`handle_customer_subscription_deleted()`が確実に`"canceled"`へ更新する
    (stripe_webhook.py参照)ため、解約済み(=もう課金されていない)workshopを誤って
    候補に含めない安全側の判定になるため(aircon-pashaの`current_plan_id is not None`
    判定と同じ考え方を、本venture固有のデータ構造に合わせて翻案したもの)。

    MVPでは`InMemoryWorkshopStore.all_workshop_ids()`による線形走査で代替する
    (aircon-pashaの`list_blocked_but_billing_candidates()`と同じ、将来Firestoreの
    複合クエリにそのまま対応させられる形を想定)。結果はworkshop_id昇順で返す
    (呼び出し順の非決定性を避けるため)。
    """
    return sorted(
        workshop_id
        for workshop_id in workshop_store.all_workshop_ids()
        if workshop_store.get_subscription_status(workshop_id) != "canceled"
        and not profile_store.get_is_following(
            workshop_store.get_contractor_user_id(workshop_id)
        )
    )
