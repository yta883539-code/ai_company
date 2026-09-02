#!/usr/bin/env python3
"""
blocked-but-billing-detection-design.md(フェーズ142)で設計した、「LINEをブロック
(unfollow)しているにもかかわらずStripe決済が継続している(解約が確認されていない)」
ユーザーを洗い出す候補検知ロジックを実装したもの。

位置づけ:
- unfollow-billing-faq.md「今後の課題」に残っていた「本サービス側から能動的に
  『ブロック中かつ契約継続中』のユーザーを検知するプロアクティブな通知バッチの要否・設計は
  未着手」に対する最初の一歩(design 3節)。aircon-pashaのblocked_but_billing_candidates.py
  と同じ位置づけだが、本ventureは`current_plan_id`フィールドを持たないため、
  `application_form_submission_flow.UserProfileStoreProtocol`の`is_following`/
  `stripe_customer_id`と、`deletion_candidate.ProfileDeletionCandidateStoreProtocol`の
  `deletion_candidate_at`を組み合わせて判定する(design 2節)。
- 本モジュールが行うのは「候補user_idの洗い出し」のみで、洗い出した候補への実際の通知
  (オーナーへのメール送信等)は行わない。deletion_candidate.pyの
  `list_deletion_candidates()`と同じ「読み出し専用の候補リスト関数」という位置づけ。

設計の参照元: blocked-but-billing-detection-design.md
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, List, Optional, Protocol


class BlockedButBillingProfileStoreProtocol(Protocol):
    """`user_profile/{user_id}`ドキュメントのうち`is_following`・`stripe_customer_id`
    フィールドのみを対象にした薄いインターフェース(design 3節)。
    `application_form_submission_flow.UserProfileStoreProtocol`
    (ひいては`InMemoryUserProfileStore`)は既にこれらのメソッドを持つため、
    構造的に(duck typing)本Protocolを満たす。
    """

    def get_is_following(self, user_id: str) -> bool:
        ...

    def get_stripe_customer_id(self, user_id: str) -> Optional[str]:
        ...

    def all_user_ids(self) -> Iterable[str]:
        ...


class BlockedButBillingDeletionStoreProtocol(Protocol):
    """`deletion_candidate_at`フィールドのみを対象にした薄いインターフェース。
    `deletion_candidate.ProfileDeletionCandidateStoreProtocol`
    (ひいては`InMemoryProfileDeletionCandidateStore`)は既にこのメソッドを持つ。
    """

    def get_deletion_candidate_at(self, user_id: str) -> Optional[datetime]:
        ...


def list_blocked_but_billing_candidates(
    profile_store: BlockedButBillingProfileStoreProtocol,
    deletion_store: BlockedButBillingDeletionStoreProtocol,
) -> List[str]:
    """design 2節: `is_following`が`False`、かつ`stripe_customer_id`が設定されている
    (=Stripe Checkoutを一度でも完了している)、かつ`deletion_candidate_at`が`None`
    (=`customer.subscription.deleted`をまだ受信していない=解約が確認されていない)
    `user_id`の一覧を返す。

    走査対象は`profile_store.all_user_ids()`(`is_following`/`stripe_customer_id`いずれかの
    記録がある全user_id)とし、`deletion_store`へは各user_idについて1回だけ問い合わせる。
    MVPでは`InMemoryUserProfileStore`による線形走査で代替する(deletion_candidate.pyの
    `list_deletion_candidates()`と同じ、将来Firestoreの複合クエリにそのまま対応させられる
    形を想定、design 3節)。結果はuser_id昇順で返す(呼び出し順の非決定性を避けるため)。
    """
    return sorted(
        user_id
        for user_id in profile_store.all_user_ids()
        if not profile_store.get_is_following(user_id)
        and profile_store.get_stripe_customer_id(user_id) is not None
        and deletion_store.get_deletion_candidate_at(user_id) is None
    )
