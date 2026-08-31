#!/usr/bin/env python3
"""
blocked-but-billing-detection-design.md(フェーズ167)で設計した、「LINEをブロック
(unfollow)しているにもかかわらず契約(サブスクリプション)が継続している」業者を
洗い出す候補検知ロジックを実装したもの。

位置づけ:
- unfollow-billing-faq.md「今後の課題」に残っていた「本サービス側から能動的に
  『ブロック中かつ契約継続中』の業者を検知するプロアクティブな通知バッチの要否・設計は
  未着手」に対する最初の一歩(design 1節)。
- 本モジュールが行うのは「候補user_idの洗い出し」のみで、洗い出した候補への実際の通知
  (オーナーへのメール送信・Slack通知等)は行わない。deletion_candidate.pyの
  `list_deletion_candidates()`と同じ「読み出し専用の候補リスト関数」という位置づけ
  (design 3節)。
- 通知先はunfollow-billing-faq.mdの問い合わせ対応テンプレートとは異なり、業者本人ではなく
  オーナー自身を想定する(design 2節「通知対象」)。LINEをブロックした業者にLINE経由で
  再度連絡することはできない(送達不可、follow-unfollow-event-handling-design.md 2節)ため、
  「オーナーが候補一覧を見て、必要であればメール等の別チャネルで個別対応する」運用を想定した
  設計とした。

設計の参照元: blocked-but-billing-detection-design.md
"""

from __future__ import annotations

from typing import Iterable, List, Protocol


class BlockedButBillingCandidateStoreProtocol(Protocol):
    """`user_profile/{user_id}`ドキュメントのうち`is_following`・`current_plan_id`
    フィールドのみを対象にした薄いインターフェース(design 2節)。
    deletion_candidate.pyの`ProfileDeletionCandidateStoreProtocol`と同じ構成。
    `user_id_linking.UserProfileStoreProtocol`(ひいては`InMemoryUserProfileStore`)は
    これらのメソッドを既に持つため、構造的に(duck typing)本Protocolを満たす。
    """

    def get_is_following(self, user_id: str) -> bool:
        ...

    def get_current_plan_id(self, user_id: str) -> "str | None":
        ...

    def all_user_ids(self) -> Iterable[str]:
        ...


def list_blocked_but_billing_candidates(
    store: BlockedButBillingCandidateStoreProtocol,
) -> List[str]:
    """design 2節: `is_following`が`False`、かつ`current_plan_id`が設定されている
    (`None`でない=有料プラン契約中、トライアル中いずれか)`user_id`の一覧を返す。

    `current_plan_id`を「契約継続中」の判定根拠に使うのは、フェーズ161で確立した
    「`customer.subscription.deleted`受信時に`current_plan_id`をNoneへ戻す」配線
    (`subscription_plan_sync.clear_current_plan_on_subscription_deleted()`)を
    そのまま流用できるため(design 2節「判定条件」)。解約済み(=もう課金されていない)
    業者を誤って候補に含めないための安全側の判定でもある。

    MVPでは`InMemoryUserProfileStore.all_user_ids()`による線形走査で代替する
    (deletion_candidate.pyの`list_deletion_candidates()`と同じ、将来Firestoreの
    複合クエリ〈`is_following == False AND current_plan_id != null`〉にそのまま
    対応させられる形を想定、design 3節)。結果はuser_id昇順で返す
    (呼び出し順の非決定性を避けるため)。
    """
    return sorted(
        user_id
        for user_id in store.all_user_ids()
        if not store.get_is_following(user_id)
        and store.get_current_plan_id(user_id) is not None
    )
