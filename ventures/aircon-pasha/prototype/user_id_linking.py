#!/usr/bin/env python3
"""
user-account-linking-design.mdで設計した「申込フォーム送信完了時に発行された連携コードを、
LINE友だち追加後の最初のトークで受信し、user_idへ解決してuser_profileを新規作成する」フローを
実行可能なコードに落とし込んだもの。

位置づけ:
- 本ventureはcourse-set-pasha(line-user-id-linking-design.md)と紐付けの向きが逆
  (design 1節: 本ventureは「フォーム送信 → LINE友だち追加」の順序)。連携コードは
  フォーム送信完了時点(まだuser_idは判明していない)で発行され`pending_links/{code}`へ
  保存される。LINE側で連携コードを受信して初めてuser_idが判明するため、本モジュールの
  `resolve_linking_code()`はcourse-set-pasha版(`code → user_id`を返すだけ)と異なり、
  `code + user_id`を受け取ってuser_profileそのものを確定させる。
- 実際のGoogleフォーム作成・GAS Webhookデプロイ・LINE公式アカウント接続・実Firestore接続は
  いずれも「アカウント作成」「外部サービスへの公開」に該当し、オーナー承認待ち
  (pending-approval.md参照)。本モジュールはコード発行・解決ロジック自体を実接続なしで
  検証可能にしたもの(course-set-pasha/prototype/user_id_linking.pyと同じ位置づけ)。

設計の参照元: user-account-linking-design.md 2〜3節・5節
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Optional, Protocol, Tuple

# design 2節: course-set-pashaのline-user-id-linking-design.md「3. コード仕様」と同じ
# 文字種・視認性除外ルール(0/O、1/I/Lを除く)を採用。
_CODE_ALPHABET = "".join(
    c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" if c not in "0O1IL"
)
_CODE_LENGTH = 6
_LINK_TTL = timedelta(hours=24)
_MAX_GENERATION_ATTEMPTS = 5


@dataclass
class PendingLink:
    """`pending_links/{code}`ドキュメント1件(design 5節)。"""

    form_submission_id: str
    business_name: str
    business_type: str
    email: str
    issued_at: datetime


class LinkingCodeStoreProtocol(Protocol):
    """`pending_links/{code}`ドキュメントへの読み書きを表す(design 5節)。"""

    def save(self, code: str, entry: PendingLink) -> None:
        ...

    def get(self, code: str) -> Optional[PendingLink]:
        ...

    def delete(self, code: str) -> None:
        ...

    def items(self) -> Iterable[Tuple[str, PendingLink]]:
        """全エントリを`(code, entry)`で列挙する(期限切れパージのため)。"""
        ...


class InMemoryLinkingCodeStore:
    """実Firestore接続の代わりにdictで`pending_links`ドキュメントを保持する検証用スタブ。"""

    def __init__(self) -> None:
        self._entries: dict[str, PendingLink] = {}

    def save(self, code: str, entry: PendingLink) -> None:
        self._entries[code] = entry

    def get(self, code: str) -> Optional[PendingLink]:
        return self._entries.get(code)

    def delete(self, code: str) -> None:
        self._entries.pop(code, None)

    def items(self) -> Iterable[Tuple[str, PendingLink]]:
        # スナップショットを返す(パージ中の削除でイテレータが壊れないようにする)。
        return list(self._entries.items())


class RandomChoiceSource(Protocol):
    """`random.Random`と同じ`choice()`インターフェースを想定(テストで決定的な値を注入するため)。"""

    def choice(self, seq):
        ...


def _generate_candidate_code(rng: RandomChoiceSource) -> str:
    return "".join(rng.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))


def issue_linking_code_on_form_submission(
    form_submission_id: str,
    business_name: str,
    business_type: str,
    email: str,
    store: LinkingCodeStoreProtocol,
    now: datetime,
    rng: RandomChoiceSource,
) -> str:
    """design 2節: 申込フォーム送信完了時(GAS Webhook側)に呼ばれる想定。重複しないコードを
    発行・保存し、コード文字列を返す(呼び出し側がサンクスページ表示・確認メール本文へ
    埋め込む想定だが、実フォーム・実メール送信はいずれもオーナー承認待り)。
    """
    for _ in range(_MAX_GENERATION_ATTEMPTS):
        code = _generate_candidate_code(rng)
        if store.get(code) is None:
            store.save(
                code,
                PendingLink(
                    form_submission_id=form_submission_id,
                    business_name=business_name,
                    business_type=business_type,
                    email=email,
                    issued_at=now,
                ),
            )
            return code
    raise RuntimeError(
        f"linking code generation collided {_MAX_GENERATION_ATTEMPTS} times in a row"
    )


@dataclass
class UserProfile:
    """`user_profile/{user_id}`ドキュメント(design 5節)。

    `trial_start_at`・`trial_end_notified_at`・`upgraded_at`は
    trial-end-notification-design.md 5節・trial-end-scheduler-design.md(フェーズ133)で
    予告されていた3フィールド(フェーズ134で追加)。course-set-pashaの
    `InMemoryUsageCounter`/`user_profile`設計と同じ位置づけで、いずれも一度設定されたら
    以降不変(`trial_start_at`は初回生成成功時、`trial_end_notified_at`は
    トライアル終了通知送信時、`upgraded_at`は有料転換時にそれぞれ1回だけ書き込む)。
    `trial_generation_count`はtrial-end-notification-design.md 5節で予告されていた
    トライアル専用生成回数カウンタ(フェーズ137で追加)。月次カウンタ(`usage_counter`)とは
    別立てで、有料転換前(`upgraded_at`が未設定)の生成成功のたびに1ずつ増える
    (`trial_start_at`等と異なり不変フィールドではない)。

    `payment_failure_detected_at`・`payment_suspended_at`はpayment-failure-dunning-
    design.md 3・6節で予告されていた決済失敗(dunning)対応の2フィールド(フェーズ140で
    追加)。`trial_generation_count`と同じく不変フィールドではなく、`payment_failure.py`の
    `mark_payment_failure_detected()`/`clear_payment_failure_on_success()`により
    Stripe Webhook(`invoice.payment_failed`/`invoice.payment_succeeded`)受信のたびに
    書き換わる。`payment_suspended_at`は猶予期間(7日)終了後に制限モードへ移行した日時を
    記録する。その自動移行を行うスケジューラ`payment_suspension_scheduler.py`の
    `send_payment_suspensions()`がフェーズ145で追加され、`set_payment_suspended_at()`を
    呼ぶ経路が実装済みとなった。

    `payment_failure_reminder_sent_at`はpayment-failure-reminder-scheduler-design.md
    (フェーズ143)で追加した、猶予期間終了直前リマインド(3日前、1回のみ)の送信済み
    フラグ。`trial_end_notified_at`と同じ「一度設定されたら以降不変」フィールドで、
    `payment_failure_reminder_scheduler.py`の`send_payment_failure_reminders()`が
    送信成功時に1回だけ書き込む(`clear_payment_failure_on_success()`で決済成功が
    確認された場合はこのフラグもクリアし、次回の決済失敗検知に備える)。

    `current_plan_id`はuser-account-linking-design.md 4節で予告されていたフィールド
    (既定値`None`=未契約)で、当初から存在していたが実際に書き込む処理が長らく無いまま
    残っていた配線漏れをフェーズ161で解消した。`subscription_plan_sync.py`の
    `sync_current_plan_on_subscription_event()`/`clear_current_plan_on_subscription_
    deleted()`が、Stripe Webhookの`customer.subscription.created/updated/deleted`受信の
    たびに書き換える(`trial_generation_count`・`payment_failure_detected_at`等と同じく
    不変フィールドではない)。

    `is_following`はblocked-but-billing-detection-design.md(フェーズ167)で追加した、
    LINE公式アカウントのフォロー状態を表すフィールド(既定値`True`。連携時=フォロー中の
    前提で生成されるため)。`cloud_function_webhook.py`の`process_follow_event()`/
    `process_unfollow_event()`が、LINEの`follow`/`unfollow`イベント受信のたびに書き換える。
    unfollow時も他のフィールド(`current_plan_id`・`stripe_customer_id`等)は
    follow-unfollow-event-handling-design.md 2節の決定通り一切変更しない
    (削除・失効させない)ため、本フィールドは「保持されたままの契約情報」と「実際に
    メッセージが届くかどうか」を分離して追跡するための追加フラグという位置づけ。

    `blocked_but_billing_owner_notified_at`はblocked-but-billing-owner-notification-
    design.md(フェーズ174)で追加した、`list_blocked_but_billing_candidates()`が
    洗い出した候補について運営者(オーナー)へLINE Pushで通知済みかどうかを表す
    フラグ(既定値`None`=未通知)。`payment_failure_reminder_sent_at`と同じ「一度設定
    されたら以降不変(次にクリアされるまで)」フィールドで、
    `blocked_but_billing_owner_notification.py`の
    `send_blocked_but_billing_owner_notifications()`が送信成功時に1回だけ書き込む。
    フォロー再開(`cloud_function_webhook.process_follow_event()`)・解約確定
    (`stripe_dispatch.dispatch_stripe_event()`の`customer.subscription.deleted`分岐)の
    いずれかが起きた時点で`None`へクリアする配線をフェーズ175で実装した
    (`blocked_but_billing_owner_notification.clear_blocked_but_billing_owner_notified_at()`
    経由、design 6節参照)。"""

    business_name: str
    business_type: str
    email: str
    linked_at: datetime
    stripe_customer_id: Optional[str] = None
    current_plan_id: Optional[str] = None
    trial_start_at: Optional[datetime] = None
    trial_end_notified_at: Optional[datetime] = None
    upgraded_at: Optional[datetime] = None
    trial_generation_count: int = 0
    payment_failure_detected_at: Optional[datetime] = None
    payment_suspended_at: Optional[datetime] = None
    payment_failure_reminder_sent_at: Optional[datetime] = None
    is_following: bool = True
    blocked_but_billing_owner_notified_at: Optional[datetime] = None


class UserProfileStoreProtocol(Protocol):
    """`user_profile/{user_id}`ドキュメントへの読み書きを表す(design 5節)。

    `set_stripe_customer_id`/`get_user_id_by_stripe_customer_id`は
    checkout-session-completed-handling-design.mdで追加した、`stripe_customer_id`
    (StripeカスタマーオブジェクトのID)と`user_id`の紐付けを表す。本ventureは
    `client_reference_id`に既知の`user_id`をそのまま設定できる(design 4節)ため
    `set_stripe_customer_id`は書き込み専用として先に追加し、`get_user_id_by_stripe_
    customer_id`は`customer.subscription.*`系イベントの`resolve_user_id(stripe_
    customer_id) -> user_id`変換をこの逆引きで実現するために使う(course-set-pashaの
    `get_user_id_by_stripe_customer_id`と同じ位置づけ)。

    `get_stripe_customer_id`(順引き)はportal-session-provider-design.md(フェーズ176)で
    `StripePortalLinkProvider`(既存customerの有無判定・Billing Portalセッションパラメータ
    組み立てに使う)向けに追加した。既存の`UserProfile.stripe_customer_id`フィールドを
    そのまま読むだけの単純なgetterで、未知の`user_id`に対しては`None`を返す(他のno-op系
    getterと同じ安全側方針)。

    `set_trial_start_at`/`set_trial_end_notified_at`/`set_upgraded_at`は
    trial-end-scheduler-design.md(フェーズ133)向けにフェーズ134で追加した3フィールドの
    書き込み専用メソッド(いずれも未知の`user_id`に対しては何もしない、
    `set_stripe_customer_id`と同じno-op方針)。

    `increment_trial_generation_count`はフェーズ137で追加した、トライアル専用生成回数
    カウンタのインクリメント専用メソッド(course-set-pashaの
    `increment_trial_generation_count`と同じ位置づけ)。未知の`user_id`に対しては
    何もせず0を返す(他のno-opメソッドと同じ安全側方針)。

    `get_payment_failure_detected_at`/`set_payment_failure_detected_at`/
    `get_payment_suspended_at`/`set_payment_suspended_at`はフェーズ140で追加した、
    payment_failure.pyの`PaymentFailureStoreProtocol`(deletion_candidate.pyの
    `ProfileDeletionCandidateStoreProtocol`と同じ、`user_profile`の一部フィールドのみを
    対象にした薄いインターフェース)を本クラスが構造的に(duck typing)満たすためのメソッド。
    未知の`user_id`に対する`set_*`は他のno-opメソッドと同じ安全側方針(何もしない)。

    `get_payment_failure_reminder_sent_at`/`set_payment_failure_reminder_sent_at`は
    フェーズ143で追加した、payment_failure_reminder_scheduler.pyの
    `PaymentFailureReminderSentAtWriter`(`set_trial_end_notified_at`と同じ、送信済み
    フラグ書き込み専用の薄いProtocol)を本クラスが構造的に満たすためのメソッド。

    `get_current_plan_id`/`set_current_plan_id`はフェーズ161で追加した、
    subscription_plan_sync.pyの`CurrentPlanStoreProtocol`を本クラスが構造的に
    (duck typing)満たすためのメソッド。未知の`user_id`に対する`set_current_plan_id`は
    他のno-opメソッドと同じ安全側方針(何もしない)。

    `get_is_following`/`set_is_following`/`all_user_ids`はフェーズ167で追加した、
    blocked_but_billing_candidates.pyの`BlockedButBillingCandidateStoreProtocol`を
    本クラスが構造的に満たすためのメソッド。`get_is_following`は未知の`user_id`に対して
    `True`を返す(存在しないprofileを「フォロー中」扱いする安全側デフォルト。実際には
    連携済みprofileが存在しない`user_id`が候補判定の対象になることはない、design 2節)。
    `all_user_ids`はdeletion_candidate.pyの`ProfileDeletionCandidateStoreProtocol.
    all_user_ids`と同じ位置づけの列挙用メソッド。

    `get_blocked_but_billing_owner_notified_at`/`set_blocked_but_billing_owner_
    notified_at`はフェーズ174で追加した、blocked_but_billing_owner_notification.pyの
    `BlockedButBillingOwnerNotifiedAtReader`/`Writer`を本クラスが構造的に満たすための
    メソッド。未知の`user_id`に対する`set_*`は他のno-opメソッドと同じ安全側方針。
    `set_blocked_but_billing_owner_notified_at`の値は`payment_failure_detected_at`等と
    同じく`Optional[datetime]`(フェーズ175でクリア配線に対応するため`None`も許容する
    形へ拡張、値自体の意味は変わらない)。"""

    def save(self, user_id: str, profile: UserProfile) -> None:
        ...

    def get(self, user_id: str) -> Optional[UserProfile]:
        ...

    def exists(self, user_id: str) -> bool:
        ...

    def set_stripe_customer_id(self, user_id: str, stripe_customer_id: str) -> None:
        ...

    def get_user_id_by_stripe_customer_id(
        self, stripe_customer_id: str
    ) -> Optional[str]:
        ...

    def get_stripe_customer_id(self, user_id: str) -> Optional[str]:
        ...

    def set_trial_start_at(self, user_id: str, at: datetime) -> None:
        ...

    def set_trial_end_notified_at(self, user_id: str, notified_at: datetime) -> None:
        ...

    def set_upgraded_at(self, user_id: str, at: datetime) -> None:
        ...

    def increment_trial_generation_count(self, user_id: str) -> int:
        """インクリメント後のカウント値を返す契約とする。"""
        ...

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

    def get_current_plan_id(self, user_id: str) -> Optional[str]:
        ...

    def set_current_plan_id(self, user_id: str, plan_id: Optional[str]) -> None:
        ...

    def get_is_following(self, user_id: str) -> bool:
        ...

    def set_is_following(self, user_id: str, value: bool) -> None:
        ...

    def all_user_ids(self) -> Iterable[str]:
        ...

    def get_blocked_but_billing_owner_notified_at(self, user_id: str) -> Optional[datetime]:
        ...

    def set_blocked_but_billing_owner_notified_at(
        self, user_id: str, notified_at: Optional[datetime]
    ) -> None:
        ...


class InMemoryUserProfileStore:
    """実Firestore接続の代わりにdictで`user_profile`ドキュメントを保持する検証用スタブ。

    `stripe_customer_id → user_id`の逆引き用に別辞書も保持する(実Firestoreでは
    `user_profile`コレクションへの単一フィールド書き込み+別コレクション
    `stripe_customer_index/{stripe_customer_id}`への逆引きドキュメント書き込みに
    対応する想定、course-set-pashaの`InMemoryUserProfileStore`と同じ設計)。"""

    def __init__(self) -> None:
        self._profiles: dict[str, UserProfile] = {}
        self._user_ids_by_stripe_customer_id: dict[str, str] = {}

    def save(self, user_id: str, profile: UserProfile) -> None:
        self._profiles[user_id] = profile

    def get(self, user_id: str) -> Optional[UserProfile]:
        return self._profiles.get(user_id)

    def exists(self, user_id: str) -> bool:
        return user_id in self._profiles

    def set_stripe_customer_id(self, user_id: str, stripe_customer_id: str) -> None:
        profile = self._profiles.get(user_id)
        if profile is None:
            return
        old_stripe_customer_id = profile.stripe_customer_id
        if old_stripe_customer_id is not None:
            self._user_ids_by_stripe_customer_id.pop(old_stripe_customer_id, None)
        profile.stripe_customer_id = stripe_customer_id
        self._user_ids_by_stripe_customer_id[stripe_customer_id] = user_id

    def get_user_id_by_stripe_customer_id(
        self, stripe_customer_id: str
    ) -> Optional[str]:
        return self._user_ids_by_stripe_customer_id.get(stripe_customer_id)

    def get_stripe_customer_id(self, user_id: str) -> Optional[str]:
        profile = self._profiles.get(user_id)
        if profile is None:
            return None
        return profile.stripe_customer_id

    def set_trial_start_at(self, user_id: str, at: datetime) -> None:
        profile = self._profiles.get(user_id)
        if profile is None:
            return
        profile.trial_start_at = at

    def set_trial_end_notified_at(self, user_id: str, notified_at: datetime) -> None:
        profile = self._profiles.get(user_id)
        if profile is None:
            return
        profile.trial_end_notified_at = notified_at

    def set_upgraded_at(self, user_id: str, at: datetime) -> None:
        profile = self._profiles.get(user_id)
        if profile is None:
            return
        profile.upgraded_at = at

    def increment_trial_generation_count(self, user_id: str) -> int:
        profile = self._profiles.get(user_id)
        if profile is None:
            return 0
        profile.trial_generation_count += 1
        return profile.trial_generation_count

    def get_payment_failure_detected_at(self, user_id: str) -> Optional[datetime]:
        profile = self._profiles.get(user_id)
        return profile.payment_failure_detected_at if profile is not None else None

    def set_payment_failure_detected_at(
        self, user_id: str, value: Optional[datetime]
    ) -> None:
        profile = self._profiles.get(user_id)
        if profile is None:
            return
        profile.payment_failure_detected_at = value

    def get_payment_suspended_at(self, user_id: str) -> Optional[datetime]:
        profile = self._profiles.get(user_id)
        return profile.payment_suspended_at if profile is not None else None

    def set_payment_suspended_at(self, user_id: str, value: Optional[datetime]) -> None:
        profile = self._profiles.get(user_id)
        if profile is None:
            return
        profile.payment_suspended_at = value

    def get_payment_failure_reminder_sent_at(self, user_id: str) -> Optional[datetime]:
        profile = self._profiles.get(user_id)
        return profile.payment_failure_reminder_sent_at if profile is not None else None

    def set_payment_failure_reminder_sent_at(
        self, user_id: str, value: Optional[datetime]
    ) -> None:
        profile = self._profiles.get(user_id)
        if profile is None:
            return
        profile.payment_failure_reminder_sent_at = value

    def get_current_plan_id(self, user_id: str) -> Optional[str]:
        profile = self._profiles.get(user_id)
        return profile.current_plan_id if profile is not None else None

    def set_current_plan_id(self, user_id: str, plan_id: Optional[str]) -> None:
        profile = self._profiles.get(user_id)
        if profile is None:
            return
        profile.current_plan_id = plan_id

    def get_is_following(self, user_id: str) -> bool:
        profile = self._profiles.get(user_id)
        return profile.is_following if profile is not None else True

    def set_is_following(self, user_id: str, value: bool) -> None:
        profile = self._profiles.get(user_id)
        if profile is None:
            return
        profile.is_following = value

    def all_user_ids(self) -> Iterable[str]:
        return list(self._profiles.keys())

    def get_blocked_but_billing_owner_notified_at(self, user_id: str) -> Optional[datetime]:
        profile = self._profiles.get(user_id)
        return profile.blocked_but_billing_owner_notified_at if profile is not None else None

    def set_blocked_but_billing_owner_notified_at(
        self, user_id: str, notified_at: Optional[datetime]
    ) -> None:
        profile = self._profiles.get(user_id)
        if profile is None:
            return
        profile.blocked_but_billing_owner_notified_at = notified_at


@dataclass
class LinkingResolution:
    """`resolve_linking_code()`の結果。"""

    ok: bool
    error: Optional[str] = None


def resolve_linking_code(
    text: str,
    user_id: str,
    linking_store: LinkingCodeStoreProtocol,
    profile_store: UserProfileStoreProtocol,
    now: datetime,
) -> LinkingResolution:
    """design 3節: 受信テキストが「英大文字・数字混在、6文字、かつ`pending_links`に存在する
    コードと完全一致」する場合のみ連携コードとして扱う(正規表現の形式一致のみでは連携コードと
    判定しない、辞書引き一致を必須とする)。一致し、かつ期限切れでなければ`user_profile`を
    新規作成して使い切る(course-set-pashaと同じ24時間・one-time useの方針)。

    形式チェックを先に行わない理由: 施工メモの書き出し文言が偶然6文字の英数字混在に
    一致する可能性はごく低いが皆無ではないため、辞書引き(store.get)の成否のみを判定根拠とする
    (design 3節の「正規表現の形式一致のみでは連携コードと判定しない」方針に厳密に従う)。
    """
    if not isinstance(text, str):
        return LinkingResolution(ok=False, error="text is not a string")

    normalized_code = text.strip().upper()
    entry = linking_store.get(normalized_code)
    if entry is None:
        return LinkingResolution(
            ok=False,
            error="linking_code not found (not a code, already used, expired and purged, or never issued)",
        )

    if now - entry.issued_at > _LINK_TTL:
        linking_store.delete(normalized_code)
        return LinkingResolution(ok=False, error="linking_code expired")

    linking_store.delete(normalized_code)
    profile_store.save(
        user_id,
        UserProfile(
            business_name=entry.business_name,
            business_type=entry.business_type,
            email=entry.email,
            linked_at=now,
        ),
    )
    return LinkingResolution(ok=True)


def purge_expired_links(store: LinkingCodeStoreProtocol, now: datetime) -> int:
    """course-set-pasha/prototype/user_id_linking.pyのpurge_expired_links()と同じ位置づけ
    (FirestoreネイティブのTTL自動削除は最大24〜72時間遅延しうるため、スケジューラ発火型
    Cloud Function等から明示的に掃く経路も併せて持てるようにする定期パージ用の決定的ロジック)。
    有効期限(24時間)を過ぎたエントリを削除し、削除件数を返す。"""
    expired_codes = [
        code for code, entry in store.items() if now - entry.issued_at > _LINK_TTL
    ]
    for code in expired_codes:
        store.delete(code)
    return len(expired_codes)
