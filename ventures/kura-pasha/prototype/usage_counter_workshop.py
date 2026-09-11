#!/usr/bin/env python3
"""
usage-counter-workshop-key-design.md(フェーズ26)2節で確定した、生成リクエスト受信時の
月間生成回数カウント処理(user_id→workshop_id→usage_counter参照の3ステップ)を
実行可能なコードに落とし込んだもの。

位置づけ:
- README.md「次にやること」1点目(本venture未着手だった生成リクエスト処理の
  プロトタイプコード)に対応する、本venture初のprototype/コード。
- course-set-pasha/prototype/post_generation_checks.py・
  aircon-pasha同等モジュールと同じ位置づけで、実Firestore接続なしにロジックのみを
  検証可能にする。実LINE Messaging API・実Firestore・実Stripe接続はいずれもオーナー
  承認待ちの範囲(pending-approval.md参照)で、本モジュールでは行わない。
- craftsman-account-linking-design.md(フェーズ25)で確定した`craftsman_workshop`・
  `user_profile.workshop_id`・usage-counter-workshop-key-design.md(フェーズ26)で
  確定した`usage_counter/{workshop_id}`のデータ構造を前提とする。
- 未検証・残課題(usage-counter-workshop-key-design.md末尾)だった
  「`user_profile.workshop_id`が未設定(workshop未作成)のエッジケース」は、本モジュールで
  `WorkshopNotLinkedError`として明示的に扱う形で解消した。
- フェーズ30: downgrade-excess-member-handling-design.md(フェーズ28)「3. 確定する
  設計」の`pending_member_reduction_effective_at`都度チェック処理、および
  member-retention-notice-design.md(フェーズ29)「4. 未検証・残課題」1点目だった
  `specified_member_name`と表示名の突き合わせロジックを追加した
  (`check_and_apply_pending_member_reduction`・`ensure_member_is_active`)。
  縮小後に除外されたメンバーからの生成リクエストを検知する`MemberRemovedError`も
  あわせて追加した(`WorkshopNotLinkedError`相当の扱い)。
- フェーズ31: フェーズ30末尾の残課題だった、`check_and_apply_pending_member_reduction`→
  `ensure_member_is_active`→`check_and_increment_usage`の呼び出し順序を実際の生成
  リクエスト処理フローとして統合する`process_generation_request`を追加した。
- フェーズ35: contractor-transfer-design.md(フェーズ33・schema反映はフェーズ34)の
  「4. 未検証・残課題」に残っていた、`craftsman_workshop`データ構造側の契約者譲渡
  確定処理(`contractor_user_id`更新)のプロトタイプコード化に対応した
  (`resolve_contractor_transfer_target`・`apply_contractor_transfer`)。契約者からの
  再確認応答(「はい」等の自由記述)自体の検知プロンプト設計は引き続き次の課題として
  残す。
- フェーズ38: contractor-transfer-confirmation-detection-design.md(フェーズ36・
  schema反映はフェーズ37)「5. 未検証・残課題」に残っていた、
  `pending_contractor_transfer`一時状態の読み書き(`WorkshopStoreProtocol`への追加、
  `apply_contractor_transfer`呼び出し時・キャンセル時・期限切れ時の削除処理)を
  プロトタイプコード化した(`start_pending_contractor_transfer`・
  `is_contractor_transfer_confirmation_context`・`cancel_pending_contractor_transfer`・
  `check_and_expire_pending_contractor_transfer`)。期限切れ後の案内文言自体の
  schema・プロンプト設計(同ファイル5節1点目)は引き続き次の課題として残す。
- フェーズ40: contractor-transfer-expired-notice-design.md(フェーズ39、schema反映も
  本フェーズ)「4. 未検証・残課題」2点目に残っていた、`check_and_expire_pending_
  contractor_transfer`の呼び出し元への配線・文脈注入条件の実装に対応した
  (`get_contractor_transfer_expired_notice_context`)。design.md1節は
  `is_contractor_transfer_confirmation_context`と対になる関数名(`is_`接頭辞)を例示
  していたが、本関数はbool単体ではなくLLMへ転記するcandidate_member_nameを含む
  `PendingContractorTransfer`自体を返す必要があるため、`is_`ではなく`get_`接頭辞とした
  (契約者以外からのメッセージの場合はcheck_and_expire自体を呼ばずNoneを返す)。
- フェーズ44: message-context-selection-design.md(フェーズ43)3節の残課題だった、
  4段階の優先順位((a)期限切れ案内→(b)契約者譲渡再確認応答→(c)残すメンバー連絡→
  (d)通常の生成リクエスト)を1箇所に統合する`select_message_context`を追加した。
  同design.md1節の通り(a)は送信者を問わず`check_and_expire_pending_contractor_transfer`
  を直接呼び出す(契約者限定の`get_contractor_transfer_expired_notice_context`は
  使わない)。(d)のみ内部で既存の`process_generation_request`をそのまま呼び出し、
  既存関数のシグネチャ・挙動は変更していない。
- フェーズ47: trial-end-condition-design.md「4. 判定関数」で設計した、無料トライアル
  終了判定(`is_trial_period_over`)をプロトタイプコード化した。同design.md 2節の通り、
  他venture(起点=初回生成成功時)とは異なり`trial_start_at`の起点をworkshop作成時と
  確定したうえで、「生成成功1回」または「30日経過」いずれか早い方でトライアル終了と
  判定する。`trial_generation_used`フラグの書き込み処理・生成リクエスト処理への組み込み
  自体は同design.md「6. 今後の課題」の通り引き続き次の課題として残す。
- フェーズ48: trial-end-condition-design.md「6. 今後の課題」1点目のうち、
  `trial_generation_used`を生成成功時にTrueへ更新する書き込み処理を実装した
  (`WorkshopStoreProtocol.set_trial_generation_used`追加、`process_generation_request`が
  `check_and_increment_usage`成功後に未設定であれば1回だけTrueへ更新)。同課題の
  もう一方(`is_trial_period_over`をトライアル終了後の生成一時停止に組み込む配線)は
  意図的に見送った。理由は、`WorkshopStoreProtocol`にはまだ`subscription_status`
  相当の有償契約判定手段が存在せず(subscription-billing-data-model-design.md
  フェーズ46「未検証・残課題」1点目のCheckout Session・Stripe Webhook実装が未着手の
  ため)、この状態で`is_trial_period_over`の結果だけを使って生成を止めると、30日経過後に
  Stripeで正規に有償契約した利用者まで永久に生成できなくなってしまう(トライアル終了
  判定と有償契約済み判定を混同するバグを自ら作り込むことになる)ため。生成一時停止の
  配線は、有償契約判定手段(`get_subscription_status`等)が実装された後にまとめて
  対応する方が安全と判断し、trial-end-condition-design.md「6. 今後の課題」を更新して
  明記した。
- フェーズ49: subscription-billing-data-model-design.md(フェーズ46)「4. 未検証・
  残課題」1点目のうち、`WorkshopStoreProtocol`への`get_stripe_customer_id`/
  `set_stripe_customer_id`/`get_subscription_status`/`set_subscription_status`
  メソッド追加を行った(同design.md1節で確定した`craftsman_workshop`側フィールド配置を
  そのまま反映)。`subscription_status`は未契約(トライアル中)workshopの初期値を
  `"trialing"`とし、design.mdが列挙した4値("trialing"/"active"/"past_due"/
  "canceled")以外を`set_subscription_status`に渡した場合は
  `InvalidSubscriptionStatusError`を送出してデータ不整合を早期検知する。Checkout
  Session発行フロー・Stripe Webhookの署名検証・イベントディスパッチの実装、および
  フェーズ48で見送った`is_trial_period_over`の生成一時停止への配線は、引き続き次の
  課題として残す(`current_period_end`フィールドの読み書きも未着手)。
- フェーズ52: checkout-initiation-flow-design.md(フェーズ50)・
  stripe-webhook-checkout-completed-design.md(フェーズ51)によりStripe Webhook受信時に
  `set_subscription_status(workshop_id, "active")`が実際に書き込まれるようになった
  ことで、フェーズ48が見送っていた`is_trial_period_over`の生成一時停止への配線が
  安全に行えるようになったため実装した。`process_generation_request`に
  `ensure_member_is_active`成功後・`check_and_increment_usage`実行前の段階で、
  `is_trial_period_over(workshop_id, now, workshop_store)`が真かつ
  `get_subscription_status(workshop_id) != "active"`の場合に`TrialPeriodOverError`を
  送出する判定を追加した(`WorkshopNotLinkedError`・`MemberRemovedError`と同様、
  呼び出し側は`TRIAL_PERIOD_OVER_NOTICE`の文言に変換して返す想定)。`"past_due"`
  (決済失敗ダニング)も本フェーズでは`"active"`ではない値として一律ブロック対象とし、
  ダニング固有の猶予期間の扱いは「次にやること」候補2点目
  (`invoice.payment_failed`対応)に委ねる。ブロック時は`check_and_increment_usage`・
  `trial_generation_used`の更新いずれにも到達しないため、月間カウントもトライアル
  消費フラグも変化しない。
- フェーズ56: payment-failure-dunning-design.md(新規)で、フェーズ52が意図的に見送っていた
  「`subscription_status="past_due"`になった瞬間に猶予期間なく生成が止まる」という既知の
  制約を解消した。`WorkshopStoreProtocol`へ`get_payment_failure_detected_at`/
  `set_payment_failure_detected_at`/`clear_payment_failure_detected_at`を追加し、
  `is_payment_suspended()`(検知時刻からPAYMENT_FAILURE_GRACE_PERIOD_DAYS=7日以上経過したかを
  都度算出、別立ての状態フラグは追加しない設計。is_trial_period_overと同じスタイル)を新設した。
  `process_generation_request()`の判定を、`subscription_status == "past_due"`の場合は
  `is_payment_suspended()`のみで生成可否を決める専用分岐に切り出し、既存の`is_trial_period_over`
  分岐とは独立させた(design 3節「修正するバグ」参照)。
- フェーズ60: trial-end-notification-design.md(フェーズ59)「5. 実装への影響メモ」1点目・
  2点目に対応し、(A)生涯最初の生成完了経路の通知要否判定を実装した。`WorkshopStoreProtocol`へ
  `get_trial_end_notified_at`/`set_trial_end_notified_at`を追加し(命名は
  `get_payment_failure_detected_at`と同スタイル)、`process_generation_request()`内で
  `trial_generation_used`が今回の呼び出しで初めてFalse→Trueになった場合に限り
  `GenerationRequestResult.trial_end_notification_due`をTrueにして`trial_end_notified_at`を
  書き込む(二重送信防止、design 2節)。(B)期間到達経路は本venture未着手の日次スケジューラが
  前提のため引き続き次の課題として残す。
- フェーズ66: workshop_linking.py(新規)がfollowイベント経由の新規workshop作成処理から
  呼び出せるよう、`UserProfileStoreProtocol`へ`link(user_id, workshop_id)`を追加した
  (`InMemoryUserProfileStore.link()`自体はフェーズ26から既存)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional, Protocol


# pricing-plan.md確定値(プラン名→月間生成回数上限・超過分の従量単価)。
PLAN_LIMITS = {
    "light": {"monthly_limit": 3, "overage_price_jpy": 250},
    "standard": {"monthly_limit": 8, "overage_price_jpy": 200},
    "multi_craftsman": {"monthly_limit": 20, "overage_price_jpy": 150},
}


class WorkshopNotLinkedError(Exception):
    """送信元user_idにworkshop_idが未設定(workshop未作成)の場合に送出する。

    craftsman-account-linking-design.md 2節の通り、LINE友だち追加時点ではまだ
    連携コードが未解決でworkshopが作られていない状態がありうる。呼び出し側は
    この例外を「まだ新規契約フローが完了していません」という案内に変換する想定。
    """


class UnknownPlanError(Exception):
    """workshopのplan_idがPLAN_LIMITSに存在しない場合に送出する(データ不整合)。"""


class InvalidSubscriptionStatusError(Exception):
    """`subscription_status`にSUBSCRIPTION_STATUSES以外の値を設定しようとした場合に
    送出する(データ不整合の早期検知)。
    """


class MemberRemovedError(Exception):
    """downgrade-excess-member-handling-design.md 3節の縮小処理によって
    member_user_idsから除外されたuser_idから生成リクエストが来た場合に送出する。

    WorkshopNotLinkedError相当の扱いとし、呼び出し側はREMOVED_MEMBER_NOTICEの文言に
    変換して返す想定(prototype/usage_counter_workshop.pyの既存例外設計の拡張)。
    """


class PaymentSuspendedError(Exception):
    """`subscription_status="past_due"`かつ決済失敗検知時刻から
    PAYMENT_FAILURE_GRACE_PERIOD_DAYS以上経過した(猶予期間終了後も未解消の)workshopから
    生成リクエストが来た場合に送出する(フェーズ56、payment-failure-dunning-design.md 3節)。

    WorkshopNotLinkedError・TrialPeriodOverError相当の扱いとし、呼び出し側は
    PAYMENT_SUSPENDED_NOTICEの文言に変換して返す想定。
    """


class TrialPeriodOverError(Exception):
    """無料トライアル終了後(is_trial_period_over=True)かつ有償契約未確認
    (subscription_status != "active")のworkshopから生成リクエストが来た場合に
    送出する(フェーズ52)。

    WorkshopNotLinkedError・MemberRemovedError相当の扱いとし、呼び出し側は
    TRIAL_PERIOD_OVER_NOTICEの文言に変換して返す想定。
    """


REMOVED_MEMBER_NOTICE = (
    "所属していたworkshopのプラン変更により、現在はご利用いただけません。"
    "利用を続けるには契約者様に新規のworkshopへの再招待をご依頼ください。"
)

TRIAL_PERIOD_OVER_NOTICE = (
    "無料トライアル期間(生成1回、または30日間のいずれか早い方)が終了しているため、"
    "受注内容整理メモ・納品案内・お手入れ案内の生成を一時停止しています。\n"
    "引き続きご利用いただくには、有料プランへのお申し込みをお願いします。"
)

# payment-failure-dunning-design.md(フェーズ56)4節「制限モード移行時」。
PAYMENT_SUSPENDED_NOTICE = (
    "お支払い手続きが確認できないため、受注内容整理メモ・納品案内・お手入れ案内の生成を"
    "一時停止しています。\n"
    "お支払い方法をご確認いただければ、確認完了後に自動で生成を再開します。"
)


# contractor-transfer-confirmation-detection-design.md(フェーズ36)1節: requested_at+24時間。
PENDING_CONTRACTOR_TRANSFER_EXPIRY_HOURS = 24

# trial-end-condition-design.md(フェーズ47)確定値。pricing-plan.md「無料トライアル条件(仮)」。
TRIAL_PERIOD_DAYS = 30

# subscription-billing-data-model-design.md(フェーズ46)1節で確定した
# `craftsman_workshop.subscription_status`の許容値。
SUBSCRIPTION_STATUSES = ("trialing", "active", "past_due", "canceled")

# payment-failure-dunning-design.md(フェーズ56)3節確定値。他venture3件と同じ暫定値。
PAYMENT_FAILURE_GRACE_PERIOD_DAYS = 7


@dataclass
class PendingContractorTransfer:
    """`craftsman_workshop/{workshop_id}.pending_contractor_transfer`の机上表現。

    contractor-transfer-confirmation-detection-design.md 1節で確定したフィールド構成
    (candidate_user_id/candidate_member_name/requested_at/expires_at)にそのまま対応する。
    """

    candidate_user_id: str
    candidate_member_name: str
    requested_at: datetime
    expires_at: datetime


class UserProfileStoreProtocol(Protocol):
    """`user_profile/{user_id}.workshop_id`への読み書きを表す。"""

    def get_workshop_id(self, user_id: str) -> Optional[str]:
        ...

    def link(self, user_id: str, workshop_id: str) -> None:
        """フェーズ66: workshop_linking.pyの新規workshop作成処理から呼び出される
        書き込み処理。InMemoryUserProfileStoreは既存実装(フェーズ26)をそのまま使う。
        """
        ...

    def get_is_following(self, user_id: str) -> bool:
        """フェーズ80: blocked-but-billing-detection-design.md 1節。
        プロフィール未作成のuser_idに対してはTrue(未フォロー状態は存在しない)を返す。
        """
        ...

    def set_is_following(self, user_id: str, is_following: bool) -> None:
        ...


class WorkshopStoreProtocol(Protocol):
    """`craftsman_workshop/{workshop_id}`への読み取りを表す(plan_id・複数職人プラン
    関連フィールドを含む、同一Firestoreドキュメントの各フィールド)。
    """

    def get_plan_id(self, workshop_id: str) -> str:
        ...

    def set_plan(self, workshop_id: str, plan_id: str) -> None:
        """checkout.session.completed受信時、workshop作成時に暫定設定した仮のplan_id
        (craftsman-account-linking-design.md フェーズ66追記7節)を実際に選ばれたプランへ
        上書きする書き込み処理。
        """
        ...

    def get_contractor_user_id(self, workshop_id: str) -> str:
        ...

    def all_workshop_ids(self) -> Iterable[str]:
        """blocked-but-billing-detection-design.md 3節の候補走査対象を列挙する
        (aircon-pashaのUserProfileStoreProtocol.all_user_ids()相当、本ventureは
        workshop単位契約のためworkshop_idを列挙する)。"""
        ...

    def get_member_user_ids(self, workshop_id: str) -> list[str]:
        ...

    def get_member_display_name(self, workshop_id: str, user_id: str) -> Optional[str]:
        ...

    def get_pending_reduction_effective_at(self, workshop_id: str) -> Optional[datetime]:
        ...

    def get_specified_retention_member_name(self, workshop_id: str) -> Optional[str]:
        ...

    def apply_member_reduction(self, workshop_id: str, retained_user_ids: list[str]) -> None:
        """member_user_idsを置き換え、pending_member_reduction_effective_atをクリアする。"""
        ...

    def set_contractor_user_id(self, workshop_id: str, user_id: str) -> None:
        """contractor-transfer-design.md 3節の確定処理でcontractor_user_idを更新する。"""
        ...

    def get_pending_contractor_transfer(self, workshop_id: str) -> Optional[PendingContractorTransfer]:
        """`pending_contractor_transfer`を返す(未設定ならNone)。"""
        ...

    def set_pending_contractor_transfer(
        self, workshop_id: str, pending: PendingContractorTransfer
    ) -> None:
        ...

    def clear_pending_contractor_transfer(self, workshop_id: str) -> None:
        """確定処理実行時・キャンセル時・期限切れ時のいずれでも呼び出される削除処理。"""
        ...

    def get_trial_start_at(self, workshop_id: str) -> Optional[datetime]:
        """trial-end-condition-design.md 2節: workshop作成時に1回だけ設定される起点。"""
        ...

    def get_trial_generation_used(self, workshop_id: str) -> bool:
        """trial-end-condition-design.md 3節: 生涯最初の生成成功時に1回だけTrueになる
        一度切りのフラグ(月次リセットされるusage_counterとは独立)。
        """
        ...

    def set_trial_generation_used(self, workshop_id: str, used: bool = True) -> None:
        """trial-end-condition-design.md「6. 今後の課題」1点目: 生涯最初の生成成功時に
        1回だけTrueへ更新する書き込み処理。
        """
        ...

    def get_stripe_customer_id(self, workshop_id: str) -> Optional[str]:
        """subscription-billing-data-model-design.md 1節: 未契約(トライアル中含む)は
        Noneを返す。
        """
        ...

    def set_stripe_customer_id(self, workshop_id: str, stripe_customer_id: str) -> None:
        """Checkout Session完了時にStripe顧客IDをworkshop側へ紐付ける書き込み処理。"""
        ...

    def get_workshop_id_by_stripe_customer_id(self, stripe_customer_id: str) -> Optional[str]:
        """subscription-canceled-webhook-design.md 1節: `customer.subscription.deleted`等、
        `client_reference_id`を持たないイベントがworkshop_idを解決するための逆引き。
        紐付けが無いstripe_customer_idにはNoneを返す(aircon-pasha/course-set-pashaの
        `get_user_id_by_stripe_customer_id`と同じ位置づけ)。
        """
        ...

    def get_subscription_status(self, workshop_id: str) -> str:
        """subscription-billing-data-model-design.md 1節: SUBSCRIPTION_STATUSESの
        いずれかを返す(未契約・トライアル中のworkshopは"trialing")。
        """
        ...

    def set_subscription_status(self, workshop_id: str, status: str) -> None:
        """Stripe Webhookのイベントディスパッチから呼び出される想定の更新処理。
        statusがSUBSCRIPTION_STATUSESに含まれない場合はInvalidSubscriptionStatusErrorを
        送出する。
        """
        ...

    def get_payment_failure_detected_at(self, workshop_id: str) -> Optional[datetime]:
        """payment-failure-dunning-design.md(フェーズ56)3節: `invoice.payment_failed`受信
        時刻。未検知(通常運用中、または既に解消済み)の場合はNoneを返す。
        """
        ...

    def set_payment_failure_detected_at(self, workshop_id: str, detected_at: datetime) -> None:
        """`invoice.payment_failed`受信時に書き込む。"""
        ...

    def clear_payment_failure_detected_at(self, workshop_id: str) -> None:
        """`invoice.payment_succeeded`受信時に解消済みとして削除する。"""
        ...

    def get_trial_end_notified_at(self, workshop_id: str) -> Optional[datetime]:
        """trial-end-notification-design.md(フェーズ59)2節: トライアル終了通知を
        (A)(B)いずれかの経路で送信済みの時刻。未送信の場合はNoneを返す(二重送信防止用)。
        """
        ...

    def set_trial_end_notified_at(self, workshop_id: str, notified_at: datetime) -> None:
        """(A)または(B)経路で通知を送信した時点で1回だけ書き込む。"""
        ...

    def get_blocked_but_billing_owner_notified_at(self, workshop_id: str) -> Optional[datetime]:
        """blocked-but-billing-owner-notification-design.md(フェーズ81)4節: 当該workshopの
        「ブロック中かつ契約継続中」候補をオーナーへ通知済みの時刻。未通知(または既に
        クリア済み)の場合はNoneを返す(二重通知防止用)。`list_blocked_but_billing_
        candidates()`の返り値がworkshop_id単位であるため、本フィールドも`user_profile`
        ではなく`craftsman_workshop`側に持たせる(get_trial_end_notified_atと同じ理由)。
        """
        ...

    def set_blocked_but_billing_owner_notified_at(
        self, workshop_id: str, notified_at: Optional[datetime]
    ) -> None:
        """送信成功時に1回だけ書き込む。クリア配線(design 6節)は`None`を渡すことで表現する
        (payment_failure_detected_atのset/clearを2メソッドに分けた方式とは異なり、
        trial_end_notified_at同様1メソッドに統一する)。
        """
        ...


class UsageCounterStoreProtocol(Protocol):
    """`usage_counter/{workshop_id}`(month・count)への読み書きを表す。"""

    def get(self, workshop_id: str) -> Optional[tuple[str, int]]:
        """(month, count)を返す。ドキュメント未作成の場合はNone。"""
        ...

    def set(self, workshop_id: str, month: str, count: int) -> None:
        ...


class InMemoryUserProfileStore:
    def __init__(self) -> None:
        self._workshop_id_by_user: dict[str, str] = {}
        self._is_following_by_user: dict[str, bool] = {}

    def link(self, user_id: str, workshop_id: str) -> None:
        self._workshop_id_by_user[user_id] = workshop_id

    def get_workshop_id(self, user_id: str) -> Optional[str]:
        return self._workshop_id_by_user.get(user_id)

    def get_is_following(self, user_id: str) -> bool:
        return self._is_following_by_user.get(user_id, True)

    def set_is_following(self, user_id: str, is_following: bool) -> None:
        self._is_following_by_user[user_id] = is_following


class InMemoryWorkshopStore:
    def __init__(self) -> None:
        self._plan_id_by_workshop: dict[str, str] = {}
        self._contractor_by_workshop: dict[str, str] = {}
        self._member_user_ids_by_workshop: dict[str, list[str]] = {}
        self._display_names_by_workshop: dict[str, dict[str, str]] = {}
        self._pending_reduction_effective_at_by_workshop: dict[str, datetime] = {}
        self._specified_retention_name_by_workshop: dict[str, str] = {}
        self._pending_contractor_transfer_by_workshop: dict[str, PendingContractorTransfer] = {}
        self._trial_start_at_by_workshop: dict[str, datetime] = {}
        self._trial_generation_used_by_workshop: dict[str, bool] = {}
        self._stripe_customer_id_by_workshop: dict[str, str] = {}
        self._workshop_id_by_stripe_customer_id: dict[str, str] = {}
        self._subscription_status_by_workshop: dict[str, str] = {}
        self._payment_failure_detected_at_by_workshop: dict[str, datetime] = {}
        self._trial_end_notified_at_by_workshop: dict[str, datetime] = {}
        self._blocked_but_billing_owner_notified_at_by_workshop: dict[str, datetime] = {}

    def set_plan(self, workshop_id: str, plan_id: str) -> None:
        self._plan_id_by_workshop[workshop_id] = plan_id

    def get_plan_id(self, workshop_id: str) -> str:
        return self._plan_id_by_workshop[workshop_id]

    def set_members(
        self,
        workshop_id: str,
        contractor_user_id: str,
        member_user_ids: list[str],
        display_names: Optional[dict[str, str]] = None,
    ) -> None:
        """contractor_user_idはmember_user_idsに含めても含めなくてもよい
        (get_member_user_idsは常に契約者を含む一覧を返す)。
        """
        self._contractor_by_workshop[workshop_id] = contractor_user_id
        all_ids = [contractor_user_id] + [
            uid for uid in member_user_ids if uid != contractor_user_id
        ]
        self._member_user_ids_by_workshop[workshop_id] = all_ids
        self._display_names_by_workshop[workshop_id] = dict(display_names or {})

    def get_contractor_user_id(self, workshop_id: str) -> str:
        return self._contractor_by_workshop[workshop_id]

    def all_workshop_ids(self) -> Iterable[str]:
        return list(self._contractor_by_workshop.keys())

    def get_member_user_ids(self, workshop_id: str) -> list[str]:
        return list(self._member_user_ids_by_workshop.get(workshop_id, []))

    def get_member_display_name(self, workshop_id: str, user_id: str) -> Optional[str]:
        return self._display_names_by_workshop.get(workshop_id, {}).get(user_id)

    def set_pending_reduction_effective_at(self, workshop_id: str, effective_at: datetime) -> None:
        self._pending_reduction_effective_at_by_workshop[workshop_id] = effective_at

    def get_pending_reduction_effective_at(self, workshop_id: str) -> Optional[datetime]:
        return self._pending_reduction_effective_at_by_workshop.get(workshop_id)

    def set_specified_retention_member_name(self, workshop_id: str, name: str) -> None:
        self._specified_retention_name_by_workshop[workshop_id] = name

    def get_specified_retention_member_name(self, workshop_id: str) -> Optional[str]:
        return self._specified_retention_name_by_workshop.get(workshop_id)

    def apply_member_reduction(self, workshop_id: str, retained_user_ids: list[str]) -> None:
        self._member_user_ids_by_workshop[workshop_id] = list(retained_user_ids)
        self._pending_reduction_effective_at_by_workshop.pop(workshop_id, None)

    def set_contractor_user_id(self, workshop_id: str, user_id: str) -> None:
        self._contractor_by_workshop[workshop_id] = user_id

    def get_pending_contractor_transfer(self, workshop_id: str) -> Optional[PendingContractorTransfer]:
        return self._pending_contractor_transfer_by_workshop.get(workshop_id)

    def set_pending_contractor_transfer(
        self, workshop_id: str, pending: PendingContractorTransfer
    ) -> None:
        self._pending_contractor_transfer_by_workshop[workshop_id] = pending

    def clear_pending_contractor_transfer(self, workshop_id: str) -> None:
        self._pending_contractor_transfer_by_workshop.pop(workshop_id, None)

    def set_trial_start_at(self, workshop_id: str, trial_start_at: datetime) -> None:
        self._trial_start_at_by_workshop[workshop_id] = trial_start_at

    def get_trial_start_at(self, workshop_id: str) -> Optional[datetime]:
        return self._trial_start_at_by_workshop.get(workshop_id)

    def set_trial_generation_used(self, workshop_id: str, used: bool = True) -> None:
        self._trial_generation_used_by_workshop[workshop_id] = used

    def get_trial_generation_used(self, workshop_id: str) -> bool:
        return self._trial_generation_used_by_workshop.get(workshop_id, False)

    def get_stripe_customer_id(self, workshop_id: str) -> Optional[str]:
        return self._stripe_customer_id_by_workshop.get(workshop_id)

    def set_stripe_customer_id(self, workshop_id: str, stripe_customer_id: str) -> None:
        self._stripe_customer_id_by_workshop[workshop_id] = stripe_customer_id
        self._workshop_id_by_stripe_customer_id[stripe_customer_id] = workshop_id

    def get_workshop_id_by_stripe_customer_id(self, stripe_customer_id: str) -> Optional[str]:
        return self._workshop_id_by_stripe_customer_id.get(stripe_customer_id)

    def get_subscription_status(self, workshop_id: str) -> str:
        return self._subscription_status_by_workshop.get(workshop_id, "trialing")

    def set_subscription_status(self, workshop_id: str, status: str) -> None:
        if status not in SUBSCRIPTION_STATUSES:
            raise InvalidSubscriptionStatusError(
                f"unknown subscription_status: {status!r} (expected one of {SUBSCRIPTION_STATUSES})"
            )
        self._subscription_status_by_workshop[workshop_id] = status

    def get_payment_failure_detected_at(self, workshop_id: str) -> Optional[datetime]:
        return self._payment_failure_detected_at_by_workshop.get(workshop_id)

    def set_payment_failure_detected_at(self, workshop_id: str, detected_at: datetime) -> None:
        self._payment_failure_detected_at_by_workshop[workshop_id] = detected_at

    def clear_payment_failure_detected_at(self, workshop_id: str) -> None:
        self._payment_failure_detected_at_by_workshop.pop(workshop_id, None)

    def get_trial_end_notified_at(self, workshop_id: str) -> Optional[datetime]:
        return self._trial_end_notified_at_by_workshop.get(workshop_id)

    def set_trial_end_notified_at(self, workshop_id: str, notified_at: datetime) -> None:
        self._trial_end_notified_at_by_workshop[workshop_id] = notified_at

    def get_blocked_but_billing_owner_notified_at(self, workshop_id: str) -> Optional[datetime]:
        return self._blocked_but_billing_owner_notified_at_by_workshop.get(workshop_id)

    def set_blocked_but_billing_owner_notified_at(
        self, workshop_id: str, notified_at: Optional[datetime]
    ) -> None:
        if notified_at is None:
            self._blocked_but_billing_owner_notified_at_by_workshop.pop(workshop_id, None)
        else:
            self._blocked_but_billing_owner_notified_at_by_workshop[workshop_id] = notified_at


class InMemoryUsageCounterStore:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[str, int]] = {}

    def get(self, workshop_id: str) -> Optional[tuple[str, int]]:
        return self._entries.get(workshop_id)

    def set(self, workshop_id: str, month: str, count: int) -> None:
        self._entries[workshop_id] = (month, count)


def _current_month_key(now: datetime) -> str:
    return now.strftime("%Y-%m")


@dataclass
class UsageCheckResult:
    workshop_id: str
    plan_id: str
    month: str
    count_after_increment: int
    monthly_limit: int
    within_limit: bool
    overage_price_jpy: int


def check_and_increment_usage(
    user_id: str,
    now: datetime,
    user_profile_store: UserProfileStoreProtocol,
    workshop_store: WorkshopStoreProtocol,
    usage_counter_store: UsageCounterStoreProtocol,
) -> UsageCheckResult:
    """usage-counter-workshop-key-design.md 2節の3ステップを実行する。

    1. user_id→workshop_idを引く(未設定ならWorkshopNotLinkedError)。
    2. usage_counter/{workshop_id}を読み、monthが当月でなければcount=0でリセットしてから
       加算する(subscription-cancellation-flow-design.mdが踏襲済みのダウングレード時の
       count維持方針とは独立に、月替わりのリセットのみここで扱う)。
    3. plan_idをcraftsman_workshopから取得し、pricing-plan.mdの上限と突き合わせて
       上限超過(従量課金要否)を判定する。
    """
    workshop_id = user_profile_store.get_workshop_id(user_id)
    if workshop_id is None:
        raise WorkshopNotLinkedError(
            f"user_id={user_id!r}にworkshop_idが未設定です(新規契約フロー未完了)"
        )

    plan_id = workshop_store.get_plan_id(workshop_id)
    if plan_id not in PLAN_LIMITS:
        raise UnknownPlanError(f"workshop_id={workshop_id!r}のplan_id={plan_id!r}が不明です")

    current_month = _current_month_key(now)
    existing = usage_counter_store.get(workshop_id)
    if existing is None or existing[0] != current_month:
        count_before = 0
    else:
        count_before = existing[1]

    count_after = count_before + 1
    usage_counter_store.set(workshop_id, current_month, count_after)

    limits = PLAN_LIMITS[plan_id]
    return UsageCheckResult(
        workshop_id=workshop_id,
        plan_id=plan_id,
        month=current_month,
        count_after_increment=count_after,
        monthly_limit=limits["monthly_limit"],
        within_limit=count_after <= limits["monthly_limit"],
        overage_price_jpy=limits["overage_price_jpy"],
    )


def is_trial_period_over(
    workshop_id: str,
    now: datetime,
    workshop_store: WorkshopStoreProtocol,
) -> bool:
    """trial-end-condition-design.md「4. 判定関数」。

    pricing-plan.md「無料トライアル条件(仮)」の「初回の生成成功から1回無料、または30日間の
    いずれか早い方まで」を、(1)生涯最初の生成が既に完了しているか、(2)`trial_start_at`
    (workshop作成時に設定、他venture〈起点=初回生成成功時〉とは異なる)から30日経過したか、
    の論理和として判定する。`trial_start_at`が未設定(データ不整合・移行中)の場合は安全側に
    倒しFalse(トライアル終了とは判定しない)を返す。
    """
    trial_start_at = workshop_store.get_trial_start_at(workshop_id)
    if trial_start_at is None:
        return False
    if workshop_store.get_trial_generation_used(workshop_id):
        return True
    return now >= trial_start_at + timedelta(days=TRIAL_PERIOD_DAYS)


def is_payment_suspended(
    workshop_id: str,
    now: datetime,
    workshop_store: WorkshopStoreProtocol,
) -> bool:
    """payment-failure-dunning-design.md(フェーズ56)3節「制限モード」の判定。

    `payment_failure_detected_at`が未設定(決済失敗を検知したことがない)場合はFalseを
    返す。設定済みの場合、検知時刻からPAYMENT_FAILURE_GRACE_PERIOD_DAYS(7日)以上
    経過していれば制限モードに該当する(is_trial_period_overと同じ、別立ての状態フラグを
    持たず都度算出する設計)。
    """
    detected_at = workshop_store.get_payment_failure_detected_at(workshop_id)
    if detected_at is None:
        return False
    return now >= detected_at + timedelta(days=PAYMENT_FAILURE_GRACE_PERIOD_DAYS)


@dataclass
class MemberReductionResult:
    workshop_id: str
    applied: bool
    retained_user_id: Optional[str]
    removed_user_ids: list[str]
    specified_member_matched: bool
    note: Optional[str]


def check_and_apply_pending_member_reduction(
    workshop_id: str,
    now: datetime,
    workshop_store: WorkshopStoreProtocol,
) -> Optional[MemberReductionResult]:
    """downgrade-excess-member-handling-design.md「3. 確定する設計」の都度チェック処理。

    生成リクエスト受信のたびに(check_and_increment_usageの前段として)呼び出す想定。
    `pending_member_reduction_effective_at`が未設定、または猶予期間中(now未到達)の
    場合はNoneを返し何もしない。
    """
    effective_at = workshop_store.get_pending_reduction_effective_at(workshop_id)
    if effective_at is None or now < effective_at:
        return None

    member_user_ids = workshop_store.get_member_user_ids(workshop_id)
    contractor_user_id = workshop_store.get_contractor_user_id(workshop_id)

    if len(member_user_ids) <= 1:
        # 既に縮小済み(または元々1名)。pending_member_reduction_effective_atだけを
        # クリアする。
        workshop_store.apply_member_reduction(workshop_id, member_user_ids)
        return MemberReductionResult(
            workshop_id=workshop_id,
            applied=False,
            retained_user_id=member_user_ids[0] if member_user_ids else None,
            removed_user_ids=[],
            specified_member_matched=False,
            note=None,
        )

    specified_name = workshop_store.get_specified_retention_member_name(workshop_id)
    specified_matched = False
    note = None
    if specified_name is not None:
        # member-retention-notice-design.md「4. 未検証・残課題」1点目の突き合わせ。
        # downgrade-excess-member-handling-design.md「3. 確定する設計」の通り、上限は
        # 契約者1名のみ(契約者譲渡機能はMVP範囲外)であるため、契約者以外を指した
        # 指定は反映できずデフォルトルールを適用し、noteに記録するのみとする。
        contractor_display_name = workshop_store.get_member_display_name(
            workshop_id, contractor_user_id
        )
        if contractor_display_name is not None and contractor_display_name == specified_name:
            specified_matched = True
        else:
            note = (
                f"契約者から指定された残留希望者名({specified_name!r})は契約者本人と"
                "一致しない(契約者以外を指した指定は契約者譲渡機能がMVP範囲外のため"
                "反映できない)ため、デフォルトルール(契約者のみ残す)を適用した"
            )

    removed_user_ids = [uid for uid in member_user_ids if uid != contractor_user_id]
    workshop_store.apply_member_reduction(workshop_id, [contractor_user_id])

    return MemberReductionResult(
        workshop_id=workshop_id,
        applied=True,
        retained_user_id=contractor_user_id,
        removed_user_ids=removed_user_ids,
        specified_member_matched=specified_matched,
        note=note,
    )


def ensure_member_is_active(
    user_id: str,
    workshop_id: str,
    workshop_store: WorkshopStoreProtocol,
) -> None:
    """user_idがworkshopの契約者、または現在のmember_user_idsに含まれることを検証する。

    downgrade-excess-member-handling-design.md「3. 確定する設計」の通り、縮小処理
    (check_and_apply_pending_member_reduction)によって除外されたメンバーからの
    生成リクエストをMemberRemovedErrorとして検知する。呼び出し順序は
    (1) check_and_apply_pending_member_reduction → (2) 本関数 → (3)
    check_and_increment_usage を想定するが、その統合自体は本モジュール未着手で
    次の課題として残す。
    """
    if user_id == workshop_store.get_contractor_user_id(workshop_id):
        return
    if user_id in workshop_store.get_member_user_ids(workshop_id):
        return
    raise MemberRemovedError(
        f"user_id={user_id!r}はworkshop_id={workshop_id!r}のメンバーから除外済みです"
    )


@dataclass
class GenerationRequestResult:
    usage: UsageCheckResult
    member_reduction: Optional[MemberReductionResult]
    trial_end_notification_due: bool = False


def process_generation_request(
    user_id: str,
    now: datetime,
    user_profile_store: UserProfileStoreProtocol,
    workshop_store: WorkshopStoreProtocol,
    usage_counter_store: UsageCounterStoreProtocol,
) -> GenerationRequestResult:
    """生成リクエスト受信時に呼び出す統合エントリポイント。

    フェーズ30時点では3関数がそれぞれ独立して呼び出し可能なだけで、実際の
    呼び出し順序(ensure_member_is_activeのdocstring記載)が統合されていなかった。
    本関数で (1) check_and_apply_pending_member_reduction → (2)
    ensure_member_is_active → (3) check_and_increment_usage の順に実行する。

    (1)を先に行うのは、契約者が縮小猶予期間の到達後に最初に生成リクエストを
    送ってきた場合、その1回のリクエストで縮小を確定させたうえで(2)の判定に
    反映させるため(縮小と除外検知が同一リクエスト内で整合する必要がある)。
    """
    workshop_id = user_profile_store.get_workshop_id(user_id)
    if workshop_id is None:
        raise WorkshopNotLinkedError(
            f"user_id={user_id!r}にworkshop_idが未設定です(新規契約フロー未完了)"
        )

    member_reduction = check_and_apply_pending_member_reduction(
        workshop_id, now, workshop_store
    )
    ensure_member_is_active(user_id, workshop_id, workshop_store)
    # フェーズ52: トライアル終了かつ有償契約未確認(activeでない)の場合は
    # usage_counterへの加算・trial_generation_usedの更新いずれにも到達させず
    # 生成を一時停止する(subscription-billing-data-model-design.mdフェーズ46・49で
    # 実装済みのget_subscription_statusと、フェーズ50・51のStripe Webhook配線により
    # "active"への更新が実際に行われるようになったため、フェーズ48で見送っていた
    # この配線が安全に行えるようになった)。
    # フェーズ56: "past_due"(決済失敗ダニング)は、フェーズ52時点では"active"以外の
    # 値として上記条件に一律含めていたため猶予期間なく即座にブロックされていた
    # (payment-failure-dunning-design.md 3節「修正するバグ」)。"past_due"の場合は
    # is_trial_period_overを経由せず、is_payment_suspended()(検知時刻から7日間の猶予)
    # のみで生成可否を判定する専用分岐に切り出す。
    subscription_status = workshop_store.get_subscription_status(workshop_id)
    if subscription_status == "past_due":
        if is_payment_suspended(workshop_id, now, workshop_store):
            raise PaymentSuspendedError(
                f"workshop_id={workshop_id!r}は決済失敗の猶予期間(7日)を超えたため"
                "生成を一時停止します"
            )
    elif is_trial_period_over(workshop_id, now, workshop_store) and subscription_status != "active":
        raise TrialPeriodOverError(
            f"workshop_id={workshop_id!r}はトライアル終了済みかつ有償契約未確認のため"
            "生成を一時停止します"
        )
    usage = check_and_increment_usage(
        user_id, now, user_profile_store, workshop_store, usage_counter_store
    )
    # trial-end-condition-design.md「6. 今後の課題」1点目: 生成が実際に成功した
    # (usage_counterへの加算まで到達した)場合に限り、trial_generation_usedを1回だけ
    # Trueへ更新する。既にTrueの場合は再書き込みしない(冪等だが不要なストア書き込みを
    # 避けるため明示的にガードする)。
    # フェーズ60: trial-end-notification-design.md 2節(A)経路。今回の呼び出しで
    # trial_generation_usedが初めてFalse→Trueになった、かつまだ(A)(B)いずれの経路でも
    # 通知未送信(trial_end_notified_atが未設定)の場合に限り通知要と判定し、
    # 二重送信防止のためtrial_end_notified_atを即座に書き込む。
    trial_end_notification_due = False
    if not workshop_store.get_trial_generation_used(workshop_id):
        workshop_store.set_trial_generation_used(workshop_id, True)
        if workshop_store.get_trial_end_notified_at(workshop_id) is None:
            trial_end_notification_due = True
            workshop_store.set_trial_end_notified_at(workshop_id, now)
    return GenerationRequestResult(
        usage=usage,
        member_reduction=member_reduction,
        trial_end_notification_due=trial_end_notification_due,
    )


class ContractorTransferTargetNotFoundError(Exception):
    """契約者譲渡の確定処理を、既存メンバーに含まれないuser_idに対して呼び出した場合に
    送出する(contractor-transfer-design.md 2節のスコープ限定違反)。呼び出し側は本来
    resolve_contractor_transfer_targetがNoneを返した時点でcontractor_transfer_unclearの
    案内に切り替える想定であり、本例外はその前段チェックを取りこぼした場合の防御用。
    """


@dataclass
class ContractorTransferResult:
    workshop_id: str
    previous_contractor_user_id: str
    new_contractor_user_id: str
    matched_display_name: str


def resolve_contractor_transfer_target(
    workshop_id: str,
    specified_member_name: str,
    workshop_store: WorkshopStoreProtocol,
) -> Optional[str]:
    """contractor-transfer-design.md 3節: 契約者のメッセージ中で名指しされた相手が、
    workshopの既存メンバー(契約者自身を除く)の表示名と一致するかを判定する。

    一致するuser_idを返す(status=contractor_transfer_selectionに対応)。一致しない
    場合はNoneを返し、呼び出し側でstatus=contractor_transfer_unclearの案内文言
    (「先に招待コードでworkshopへ加わっていただいてから」)に切り替える想定。
    """
    contractor_user_id = workshop_store.get_contractor_user_id(workshop_id)
    for member_user_id in workshop_store.get_member_user_ids(workshop_id):
        if member_user_id == contractor_user_id:
            continue
        display_name = workshop_store.get_member_display_name(workshop_id, member_user_id)
        if display_name is not None and display_name == specified_member_name:
            return member_user_id
    return None


def apply_contractor_transfer(
    workshop_id: str,
    new_contractor_user_id: str,
    workshop_store: WorkshopStoreProtocol,
) -> ContractorTransferResult:
    """contractor-transfer-design.md 3節の確定処理。契約者からの再確認応答(「はい」等)を
    受けた後に呼び出す想定(再確認応答自体の検知プロンプト設計は次の課題として残す)。

    new_contractor_user_idは事前にresolve_contractor_transfer_targetで既存メンバーと
    確認済みであることを前提とするが、本関数でも再度member_user_ids所属を検証する
    (2節のスコープ限定: workshop外の第三者への直接譲渡は不可)。旧契約者は
    member_user_idsから自動的には外さない(3節の方針通り、脱退は別途本人の意思表示に
    委ねる)。usage_counter/{workshop_id}はworkshop_id不変のため影響を受けない。
    """
    if new_contractor_user_id not in workshop_store.get_member_user_ids(workshop_id):
        raise ContractorTransferTargetNotFoundError(
            f"user_id={new_contractor_user_id!r}はworkshop_id={workshop_id!r}の"
            "既存メンバーに含まれていません(workshop外への直接譲渡はスコープ外)"
        )
    previous_contractor_user_id = workshop_store.get_contractor_user_id(workshop_id)
    matched_display_name = workshop_store.get_member_display_name(
        workshop_id, new_contractor_user_id
    )
    workshop_store.set_contractor_user_id(workshop_id, new_contractor_user_id)
    # contractor-transfer-confirmation-detection-design.md 1節: 確定処理実行時に
    # pending_contractor_transferを削除する。
    workshop_store.clear_pending_contractor_transfer(workshop_id)
    return ContractorTransferResult(
        workshop_id=workshop_id,
        previous_contractor_user_id=previous_contractor_user_id,
        new_contractor_user_id=new_contractor_user_id,
        matched_display_name=matched_display_name or "",
    )


def start_pending_contractor_transfer(
    workshop_id: str,
    candidate_user_id: str,
    candidate_member_name: str,
    now: datetime,
    workshop_store: WorkshopStoreProtocol,
    expiry_hours: int = PENDING_CONTRACTOR_TRANSFER_EXPIRY_HOURS,
) -> PendingContractorTransfer:
    """contractor-transfer-confirmation-detection-design.md 1節: status=
    contractor_transfer_selectionの確認文言生成(resolve_contractor_transfer_targetが
    一致を返した時点)と同時に、アプリケーション側でpending_contractor_transferを
    書き込む。expires_atはrequested_at(=now)+expiry_hoursとする。
    """
    pending = PendingContractorTransfer(
        candidate_user_id=candidate_user_id,
        candidate_member_name=candidate_member_name,
        requested_at=now,
        expires_at=now + timedelta(hours=expiry_hours),
    )
    workshop_store.set_pending_contractor_transfer(workshop_id, pending)
    return pending


def is_contractor_transfer_confirmation_context(
    user_id: str,
    workshop_id: str,
    now: datetime,
    workshop_store: WorkshopStoreProtocol,
) -> bool:
    """contractor-transfer-confirmation-detection-design.md 2節: メッセージ送信者が
    contractor_user_idと一致し、かつpending_contractor_transferが存在しexpires_at
    以内である場合に限りTrueを返す。呼び出し側はTrueのときのみ「契約者交代の確認待ち」
    という文脈をプロンプトへ埋め込んだ上でLLMを呼び出す想定(3節の3パターン判定)。
    """
    if user_id != workshop_store.get_contractor_user_id(workshop_id):
        return False
    pending = workshop_store.get_pending_contractor_transfer(workshop_id)
    if pending is None:
        return False
    return now <= pending.expires_at


def cancel_pending_contractor_transfer(
    workshop_id: str,
    workshop_store: WorkshopStoreProtocol,
) -> None:
    """contractor-transfer-confirmation-detection-design.md 3節:
    kind=contractor_transfer_cancelledのとき、pending_contractor_transferを削除する
    のみでcontractor_user_idは更新しない。
    """
    workshop_store.clear_pending_contractor_transfer(workshop_id)


def check_and_expire_pending_contractor_transfer(
    workshop_id: str,
    now: datetime,
    workshop_store: WorkshopStoreProtocol,
) -> Optional[PendingContractorTransfer]:
    """contractor-transfer-confirmation-detection-design.md 4節: expires_atを過ぎた
    pending_contractor_transferを削除する。期限切れであった場合はその(削除前の)値を
    返し、呼び出し側で受動的な案内文言への切り替え判定に使えるようにする
    (案内文言自体のschema・プロンプト設計は5節の残課題として本関数では扱わない)。
    期限内、または未設定の場合はNoneを返し何もしない。
    """
    pending = workshop_store.get_pending_contractor_transfer(workshop_id)
    if pending is None or now <= pending.expires_at:
        return None
    workshop_store.clear_pending_contractor_transfer(workshop_id)
    return pending


def get_contractor_transfer_expired_notice_context(
    user_id: str,
    workshop_id: str,
    now: datetime,
    workshop_store: WorkshopStoreProtocol,
) -> Optional[PendingContractorTransfer]:
    """contractor-transfer-expired-notice-design.md 1節: メッセージ送信者がcontractor_
    user_idと一致する場合に限りcheck_and_expire_pending_contractor_transferを呼び出し、
    期限切れが検出された場合はその(削除前の)値を返す。呼び出し側はNone以外が返った
    場合のみstatus=contractor_transfer_expired_notice文脈をLLM呼び出しに注入し、返り値の
    candidate_member_nameをcontractor_transfer_expired_notice.candidate_member_nameへ
    そのまま転記する(is_contractor_transfer_confirmation_contextとは排他的、同design.md
    1節)。契約者以外からのメッセージの場合はcheck_and_expire自体を呼び出さず(2節
    「受信メッセージの本来の用件は今回処理しない」の前提となる契約者限定のスコープを
    踏襲)、Noneを返す。
    """
    if user_id != workshop_store.get_contractor_user_id(workshop_id):
        return None
    return check_and_expire_pending_contractor_transfer(workshop_id, now, workshop_store)


# message-context-selection-design.md(フェーズ43)1節の優先順位に対応するkind定数。
MESSAGE_CONTEXT_CONTRACTOR_TRANSFER_EXPIRED_NOTICE = "contractor_transfer_expired_notice"
MESSAGE_CONTEXT_CONTRACTOR_TRANSFER_CONFIRMATION = "contractor_transfer_confirmation"
MESSAGE_CONTEXT_MEMBER_RETENTION_NOTICE = "member_retention_notice"
MESSAGE_CONTEXT_GENERATION_REQUEST = "generation_request"


@dataclass
class MessageContext:
    """select_message_contextの戻り値。`kind`がLLM呼び出し前に注入すべき文脈を表す。

    (a)(b)(c)はLLM呼び出し前のアプリケーション側の文脈選択結果であり、実際の構造化
    出力(status enum)はLLMが後続で決定する(message-context-selection-design.md
    2節「両者を混同しないよう」の通り、本クラスはLLM出力のstatusそのものではない)。
    """

    kind: str
    workshop_id: str
    expired_transfer: Optional[PendingContractorTransfer] = None
    generation_result: Optional[GenerationRequestResult] = None


def select_message_context(
    user_id: str,
    now: datetime,
    user_profile_store: UserProfileStoreProtocol,
    workshop_store: WorkshopStoreProtocol,
    usage_counter_store: UsageCounterStoreProtocol,
) -> MessageContext:
    """message-context-selection-design.md(フェーズ43)1節の4段階の優先順位
    (先勝ち・排他)を1つの関数に統合する。

    (a) check_and_expire_pending_contractor_transferが非Noneを返した場合
        (送信者を問わない。同design.md1節(a)の通り、契約者以外からのメッセージでも
        期限切れ検出自体は行う)
        → contractor_transfer_expired_notice文脈を返す。
    (b) 送信者が契約者本人かつis_contractor_transfer_confirmation_contextが真
        → contractor_transfer_confirmation文脈を返す。
    (c) 送信者が契約者本人かつpending_member_reduction_effective_atが設定済み
        → member_retention_notice文脈を返す。
    (d) いずれにも該当しない
        → process_generation_requestをそのまま呼び出し、generation_request文脈で
          その結果を包んで返す(既存関数のシグネチャ・挙動は変更しない)。
    """
    workshop_id = user_profile_store.get_workshop_id(user_id)
    if workshop_id is None:
        raise WorkshopNotLinkedError(
            f"user_id={user_id!r}にworkshop_idが未設定です(新規契約フロー未完了)"
        )

    expired = check_and_expire_pending_contractor_transfer(workshop_id, now, workshop_store)
    if expired is not None:
        return MessageContext(
            kind=MESSAGE_CONTEXT_CONTRACTOR_TRANSFER_EXPIRED_NOTICE,
            workshop_id=workshop_id,
            expired_transfer=expired,
        )

    if is_contractor_transfer_confirmation_context(user_id, workshop_id, now, workshop_store):
        return MessageContext(
            kind=MESSAGE_CONTEXT_CONTRACTOR_TRANSFER_CONFIRMATION,
            workshop_id=workshop_id,
        )

    is_contractor = user_id == workshop_store.get_contractor_user_id(workshop_id)
    if is_contractor and workshop_store.get_pending_reduction_effective_at(workshop_id) is not None:
        return MessageContext(
            kind=MESSAGE_CONTEXT_MEMBER_RETENTION_NOTICE,
            workshop_id=workshop_id,
        )

    result = process_generation_request(
        user_id, now, user_profile_store, workshop_store, usage_counter_store
    )
    return MessageContext(
        kind=MESSAGE_CONTEXT_GENERATION_REQUEST,
        workshop_id=workshop_id,
        generation_result=result,
    )
