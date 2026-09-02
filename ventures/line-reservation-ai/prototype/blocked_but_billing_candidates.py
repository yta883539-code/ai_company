#!/usr/bin/env python3
"""
blocked-but-billing-detection-design.md(フェーズ続き176)で設計した、「オーナー自身が
店舗の公式LINEアカウントをブロック(unfollow)しているにもかかわらず契約(サブスクリプション)
が継続している」店舗を洗い出す候補検知ロジックを実装したもの。

位置づけ:
- follow-unfollow-event-handling-design.md「残課題」に残っていた、aircon-pashaフェーズ167
  相当(能動検知バッチ)の要否検討に対する最初の一歩(design 1節)。
- 本モジュールが行うのは「候補store_idの洗い出し」のみで、洗い出した候補への実際の通知
  (オーナーへのメール送信等)は行わない。aircon-pasha/blocked_but_billing_candidates.pyの
  `list_deletion_candidates()`と同じ「読み出し専用の候補リスト関数」という位置づけ
  (design 3節)。
- aircon-pasha/course-set-pashaと異なり、本venture固有の事情(オーナー自身がブロックした
  対象そのもの)によりLINE経由でオーナーへ通知することが原理的にできない
  (follow-unfollow-event-handling-design.md 3節)。候補一覧を実際に届ける手段(メール等の
  代替チャネル)の設計・実装は次回以降の課題として残る(design 4節)。

設計の参照元: blocked-but-billing-detection-design.md
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Protocol

# blocked-but-billing-detection-design.md 2節: これらの契約状態では実質的に課金関係が
# 継続していない(cancelled=契約終了済み、trial_unselected=有料転換前に休止した=そもそも
# 課金が発生していない)ため、候補から除外する。
_EXCLUDED_SUSPENSION_REASONS = frozenset({"cancelled", "trial_unselected"})


class BlockedButBillingCandidateStoreProtocol(Protocol):
    """`stores/{storeId}`ドキュメントのうち`ownerIsFollowing`・`suspensionReason`
    フィールドのみを対象にした薄いインターフェース(design 2節)。aircon-pasha/
    blocked_but_billing_candidates.pyの`BlockedButBillingCandidateStoreProtocol`と
    同じ構成。`store_profile_store.StoreProfileStoreProtocol`(ひいては
    `InMemoryStoreProfileStore`)はこれらのメソッドを既に持つため、構造的に
    (duck typing)本Protocolを満たす。
    """

    def get_owner_is_following(self, store_id: str) -> bool:
        ...

    def get_suspension_reason(self, store_id: str) -> Optional[str]:
        ...

    def all_store_ids(self) -> Iterable[str]:
        ...


def list_blocked_but_billing_candidates(
    store: BlockedButBillingCandidateStoreProtocol,
) -> List[str]:
    """design 2節: `owner_is_following`が`False`、かつ`suspension_reason`が
    `_EXCLUDED_SUSPENSION_REASONS`に含まれない(=`None`〈通常課金中〉・
    `"payment_failed"`〈猶予期間中〉・`"payment_suspended"`〈制限モード〉のいずれか)
    `store_id`の一覧を返す。

    MVPでは`InMemoryStoreProfileStore.all_store_ids()`による線形走査で代替する
    (aircon-pasha版と同じ、将来Firestoreの複合クエリ〈`ownerIsFollowing == false AND
    suspensionReason NOT IN ("cancelled", "trial_unselected")`〉にそのまま
    対応させられる形を想定、design 3節)。結果はstore_id昇順で返す(呼び出し順の
    非決定性を避けるため)。
    """
    return sorted(
        store_id
        for store_id in store.all_store_ids()
        if not store.get_owner_is_following(store_id)
        and store.get_suspension_reason(store_id) not in _EXCLUDED_SUSPENSION_REASONS
    )
