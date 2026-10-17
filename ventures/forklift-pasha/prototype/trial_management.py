#!/usr/bin/env python3
"""trial-end-condition-design.md(フェーズ118)で設計した無料トライアル終了判定を
純粋関数として実装する。pricing-plan.md「無料トライアル条件(仮)」の「生成5回到達、
または初回生成から30日、いずれか早い方」をそのまま判定する(due_date_logic.py等と同じ
pure stdlib方針、実LLM呼び出し・外部サービス接続は行わない)。
"""

from datetime import datetime, timedelta

TRIAL_PERIOD_DAYS = 30  # pricing-plan.md「無料トライアル条件(仮)」確定値
TRIAL_GENERATION_LIMIT = 5  # 同上、course-set-pashaと同じ基準


class FleetOperatorStoreProtocol:
    """fleet_operatorドキュメントのトライアル関連フィールドの読み書きを模したProtocol
    (trial-end-condition-design.md「3. 追加フィールド」「6. 今後の課題」)。実際のFirestore
    接続は未実装で、本venture内ではInMemoryFleetOperatorStoreのみを実装として用意する。
    """

    def get_trial_start_at(self, internal_id: str) -> "datetime | None":
        raise NotImplementedError

    def set_trial_start_at(self, internal_id: str, value: datetime) -> None:
        """既に設定済みの場合は上書きしない(firestore-data-model.mdの設計通り、
        初回生成時に1回だけ設定・以降不変)。"""
        raise NotImplementedError

    def get_trial_generation_count(self, internal_id: str) -> int:
        raise NotImplementedError

    def increment_trial_generation_count(self, internal_id: str) -> "tuple[int, int]":
        """1回分の生成を加算し、(加算前カウント, 加算後カウント)を返す。"""
        raise NotImplementedError

    def get_trial_end_notified_at(self, internal_id: str) -> "datetime | None":
        raise NotImplementedError

    def set_trial_end_notified_at(self, internal_id: str, value: datetime) -> None:
        """trial-end-notification-design.md 2節・5節。いずれか早い方の経路で1回だけ
        設定し、以降は上書きしない(set_trial_start_atと同じ「初回のみ設定」方針)。"""
        raise NotImplementedError

    def get_upgraded_at(self, internal_id: str) -> "datetime | None":
        raise NotImplementedError

    def set_upgraded_at(self, internal_id: str, value: datetime) -> None:
        """trial-end-notification-design.md 4節。有料転換時に設定する(本venture未設計
        だったStripe決済導線の完了処理からの書き込みを想定、呼び出し配線は次回以降の課題)。
        aircon-pasha/user_id_linking.pyのset_upgraded_at()と同じく上書き可(set_trial_
        start_at等と異なり「初回のみ」の制約は設けない)。"""
        raise NotImplementedError

    def get_plan_id(self, internal_id: str) -> "str | None":
        """stripe-checkout-plan-id-design.md 2節。overage_notifications.PLAN_VEHICLE_
        LIMIT等のキー("light"/"standard"/"fleet")と同一の値を保持する。未契約(初回
        登録直後・トライアル中)はNone。"""
        raise NotImplementedError

    def set_plan_id(self, internal_id: str, value: str) -> None:
        """同上。上書き可(plan変更時に何度でも書き換える、set_upgraded_atと同じ方針)。"""
        raise NotImplementedError

    def get_email(self, internal_id: str) -> "str | None":
        """フェーズ125 README「次回候補(2)」。Webフォーム送信時に取得したメール
        アドレス(checkout-session作成時の`customer_email`等に用いる)。未設定はNone。"""
        raise NotImplementedError

    def set_email(self, internal_id: str, value: str) -> None:
        """同上。上書き可(set_plan_idと同じく、再登録等での書き換えを許容する)。"""
        raise NotImplementedError

    def get_stripe_customer_id(self, internal_id: str) -> "str | None":
        """aircon-pasha/user_id_linking.pyのUserProfileStoreProtocolと同じ役割。
        Checkout Session完了時にStripeが発行するCustomer IDを保持する。未契約は
        None。"""
        raise NotImplementedError

    def set_stripe_customer_id(self, internal_id: str, value: str) -> None:
        """同上。上書き可。`get_internal_id_by_stripe_customer_id`の逆引きが常に
        最新の対応関係を指すよう、実装側で古い対応を解消すること
        (aircon-pasha/user_id_linking.pyのInMemory実装と同じ方針)。"""
        raise NotImplementedError

    def get_internal_id_by_stripe_customer_id(
        self, stripe_customer_id: str
    ) -> "str | None":
        """Webhook受信エントリポイント(次回候補(3)、`checkout.session.completed`等)が
        `stripe_customer_id`のみを受け取った場合の逆引き用。未知のIDはNone。"""
        raise NotImplementedError

    def get_canceled_at(self, internal_id: str) -> "datetime | None":
        """subscription-canceled-immediate-block-design.md相当(フェーズ129)。
        `customer.subscription.deleted`受信時に設定する解約確定時刻。未解約はNone。"""
        raise NotImplementedError

    def set_canceled_at(self, internal_id: str, value: "datetime | None") -> None:
        """同上。上書き可(`None`を渡すことで再契約時のクリアにも使う、
        set_upgraded_atと同じ「上書き可」方針)。"""
        raise NotImplementedError

    def all_internal_ids(self) -> "list[str]":
        """trial-end-notification-design.md 5節(B)経路・フェーズ133で追加。(B)経路の日次
        スケジューラ(trial_end_email_scheduler.py)が対象事業者を列挙するために使う。
        payment-identity-verification-design.md 39〜44行目の通り、メールアドレスは
        Webフォーム初回登録時に必ず入力されるため、registered済みの全事業者を指す
        識別子として`_email`のキー集合を返す(実Firestore接続後はコレクションクエリ
        相当になる想定)。"""
        raise NotImplementedError

    def get_deletion_confirmation_sent_at(self, internal_id: str) -> "datetime | None":
        """deletion-candidate-design.md(フェーズ152)。削除候補の最終確認メールを
        送信済みの日時。未送信はNone(再送しないための冪等ガード)。"""
        raise NotImplementedError

    def set_deletion_confirmation_sent_at(self, internal_id: str, value: datetime) -> None:
        raise NotImplementedError

    def get_deletion_confirmation_unreachable_at(self, internal_id: str) -> "datetime | None":
        """同上。最終確認メールの送達に失敗した(email未設定含む)と判定した日時。
        未判定はNone。"""
        raise NotImplementedError

    def set_deletion_confirmation_unreachable_at(
        self, internal_id: str, value: datetime
    ) -> None:
        raise NotImplementedError

    def get_deletion_confirmation_unreachable_reason(self, internal_id: str) -> "str | None":
        """aircon-pasha・course-set-pasha・kura-pashaが既に持つ
        `unreachable_reason`フィールド(連絡不能の理由コード)を本venture用に追加する
        (deletion-candidate-unreachable-reason-design.md)。未判定、または本フィールド
        追加前に記録された候補はNone。"""
        raise NotImplementedError

    def set_deletion_confirmation_unreachable_reason(
        self, internal_id: str, value: "str | None"
    ) -> None:
        raise NotImplementedError

    def get_payment_failure_detected_at(self, internal_id: str) -> "datetime | None":
        """payment-failure-dunning-design.md(フェーズ167)。`invoice.payment_failed`
        受信時に設定する決済失敗検知時刻(猶予期間の起点)。未検知・解消済みはNone。"""
        raise NotImplementedError

    def set_payment_failure_detected_at(
        self, internal_id: str, value: "datetime | None"
    ) -> None:
        """同上。上書き可(`None`渡しでクリア、`set_canceled_at`と同じ方針)。"""
        raise NotImplementedError


class InMemoryFleetOperatorStore(FleetOperatorStoreProtocol):
    """fleet_operatorドキュメントのトライアル関連フィールドを模したInMemory実装
    (Firestore接続は未実装のまま)。"""

    def __init__(self) -> None:
        self._trial_start_at: "dict[str, datetime]" = {}
        self._trial_generation_count: "dict[str, int]" = {}
        self._trial_end_notified_at: "dict[str, datetime]" = {}
        self._upgraded_at: "dict[str, datetime]" = {}
        self._plan_id: "dict[str, str]" = {}
        self._email: "dict[str, str]" = {}
        self._stripe_customer_id: "dict[str, str]" = {}
        self._internal_ids_by_stripe_customer_id: "dict[str, str]" = {}
        self._canceled_at: "dict[str, datetime]" = {}
        self._deletion_confirmation_sent_at: "dict[str, datetime]" = {}
        self._deletion_confirmation_unreachable_at: "dict[str, datetime]" = {}
        self._deletion_confirmation_unreachable_reason: "dict[str, str | None]" = {}
        self._payment_failure_detected_at: "dict[str, datetime]" = {}

    def get_trial_start_at(self, internal_id: str) -> "datetime | None":
        return self._trial_start_at.get(internal_id)

    def set_trial_start_at(self, internal_id: str, value: datetime) -> None:
        if internal_id in self._trial_start_at:
            return
        self._trial_start_at[internal_id] = value

    def get_trial_generation_count(self, internal_id: str) -> int:
        return self._trial_generation_count.get(internal_id, 0)

    def increment_trial_generation_count(self, internal_id: str) -> "tuple[int, int]":
        before = self._trial_generation_count.get(internal_id, 0)
        after = before + 1
        self._trial_generation_count[internal_id] = after
        return before, after

    def get_trial_end_notified_at(self, internal_id: str) -> "datetime | None":
        return self._trial_end_notified_at.get(internal_id)

    def set_trial_end_notified_at(self, internal_id: str, value: datetime) -> None:
        if internal_id in self._trial_end_notified_at:
            return
        self._trial_end_notified_at[internal_id] = value

    def get_upgraded_at(self, internal_id: str) -> "datetime | None":
        return self._upgraded_at.get(internal_id)

    def set_upgraded_at(self, internal_id: str, value: datetime) -> None:
        self._upgraded_at[internal_id] = value

    def get_plan_id(self, internal_id: str) -> "str | None":
        return self._plan_id.get(internal_id)

    def set_plan_id(self, internal_id: str, value: str) -> None:
        self._plan_id[internal_id] = value

    def get_email(self, internal_id: str) -> "str | None":
        return self._email.get(internal_id)

    def set_email(self, internal_id: str, value: str) -> None:
        self._email[internal_id] = value

    def get_stripe_customer_id(self, internal_id: str) -> "str | None":
        return self._stripe_customer_id.get(internal_id)

    def set_stripe_customer_id(self, internal_id: str, value: str) -> None:
        old_value = self._stripe_customer_id.get(internal_id)
        if old_value is not None:
            self._internal_ids_by_stripe_customer_id.pop(old_value, None)
        self._stripe_customer_id[internal_id] = value
        self._internal_ids_by_stripe_customer_id[value] = internal_id

    def get_internal_id_by_stripe_customer_id(
        self, stripe_customer_id: str
    ) -> "str | None":
        return self._internal_ids_by_stripe_customer_id.get(stripe_customer_id)

    def get_canceled_at(self, internal_id: str) -> "datetime | None":
        return self._canceled_at.get(internal_id)

    def set_canceled_at(self, internal_id: str, value: "datetime | None") -> None:
        if value is None:
            self._canceled_at.pop(internal_id, None)
            return
        self._canceled_at[internal_id] = value

    def all_internal_ids(self) -> "list[str]":
        return list(self._email.keys())

    def get_deletion_confirmation_sent_at(self, internal_id: str) -> "datetime | None":
        return self._deletion_confirmation_sent_at.get(internal_id)

    def set_deletion_confirmation_sent_at(self, internal_id: str, value: datetime) -> None:
        self._deletion_confirmation_sent_at[internal_id] = value

    def get_deletion_confirmation_unreachable_at(self, internal_id: str) -> "datetime | None":
        return self._deletion_confirmation_unreachable_at.get(internal_id)

    def set_deletion_confirmation_unreachable_at(
        self, internal_id: str, value: datetime
    ) -> None:
        self._deletion_confirmation_unreachable_at[internal_id] = value

    def get_deletion_confirmation_unreachable_reason(self, internal_id: str) -> "str | None":
        return self._deletion_confirmation_unreachable_reason.get(internal_id)

    def set_deletion_confirmation_unreachable_reason(
        self, internal_id: str, value: "str | None"
    ) -> None:
        if value is None:
            self._deletion_confirmation_unreachable_reason.pop(internal_id, None)
        else:
            self._deletion_confirmation_unreachable_reason[internal_id] = value

    def get_payment_failure_detected_at(self, internal_id: str) -> "datetime | None":
        return self._payment_failure_detected_at.get(internal_id)

    def set_payment_failure_detected_at(
        self, internal_id: str, value: "datetime | None"
    ) -> None:
        if value is None:
            self._payment_failure_detected_at.pop(internal_id, None)
            return
        self._payment_failure_detected_at[internal_id] = value


def is_trial_period_over(
    internal_id: str,
    now: datetime,
    operator_store: FleetOperatorStoreProtocol,
) -> bool:
    """trial-end-condition-design.md 4節: 「生成5回到達、または初回生成から30日、
    いずれか早い方」の論理和。trialStartAtが未設定(初回生成前)の場合は常にトライアル中。
    """
    trial_start_at = operator_store.get_trial_start_at(internal_id)
    if trial_start_at is None:
        return False
    if operator_store.get_trial_generation_count(internal_id) >= TRIAL_GENERATION_LIMIT:
        return True
    return now >= trial_start_at + timedelta(days=TRIAL_PERIOD_DAYS)


def record_generation_for_trial(
    operator_store: FleetOperatorStoreProtocol, internal_id: str, now: datetime
) -> None:
    """生成成功時の呼び出し側配線(design 6節「今後の課題」1点目)。初回生成時に
    trialStartAtを設定し(2回目以降は既存値を保持)、trialGenerationCountを1加算する。
    呼び出し順序はtrialStartAt設定を先に行う(カウント加算前に起点が必ず存在する状態にする)。
    """
    operator_store.set_trial_start_at(internal_id, now)
    operator_store.increment_trial_generation_count(internal_id)


def should_notify_trial_end(
    internal_id: str,
    now: datetime,
    operator_store: FleetOperatorStoreProtocol,
) -> bool:
    """trial-end-notification-design.md 2節「いずれか早い方で1回のみ送信」の判定。
    is_trial_period_over()が真で、かつtrialEndNotifiedAtが未設定の場合のみTrue。
    (A)経路(生成完了時の返却テキスト追記)・(B)経路(日次スケジューラのメール送信)の
    いずれの呼び出し元からも、送信前にこの関数で判定した上でset_trial_end_notified_at()
    を呼ぶ想定(実際の呼び出し配線はWebフォーム処理・日次スケジューラ共に未実装のため次回
    以降の課題)。"""
    if operator_store.get_trial_end_notified_at(internal_id) is not None:
        return False
    return is_trial_period_over(internal_id, now, operator_store)


# trial-end-notification-design.md 3節「(A) 生成回数到達時: 返却テキストへの追記文」。
TRIAL_END_RETURN_TEXT_NOTICE = (
    "※無料トライアルの生成回数(5回)に達しました。引き続きご利用いただくには、登録時にお送りした"
    "アクセスURLからプランをお選びください。このまま何もしなければ自動課金は発生せず、生成のみ"
    "一時停止となります。"
)


def record_generation_and_get_trial_end_notice(
    operator_store: FleetOperatorStoreProtocol, internal_id: str, now: datetime
) -> "str | None":
    """(A)経路の呼び出し配線(design 5節2点目)。record_generation_for_trial()で生成を
    記録した直後に、ちょうどトライアル終了条件に達したかをshould_notify_trial_end()で
    判定し、達していればtrialEndNotifiedAtを設定して返却テキストへの追記文を返す
    (overage_notifications.pyのrecord_generation_and_get_usage_notice()と同型:
    加算と通知判定を1回のWebフォーム送信処理の中で呼び出せるようにまとめる)。
    (B)経路(期間到達、日次スケジューラ)とは別経路のため、ここで消費した場合は
    trialEndNotifiedAtが設定済みとなり(B)経路側では再通知されない。
    """
    record_generation_for_trial(operator_store, internal_id, now)
    if not should_notify_trial_end(internal_id, now, operator_store):
        return None
    operator_store.set_trial_end_notified_at(internal_id, now)
    return TRIAL_END_RETURN_TEXT_NOTICE


# trial-end-notification-design.md 4節「トライアル終了後(未アップグレード)の挙動」。
GENERATION_PAUSED_NOTICE = (
    "現在、無料トライアルが終了しているため記録の整形を一時停止しています。引き続き"
    "ご利用いただくには、登録時にお送りしたアクセスURLからプランをお選びください。"
)


def is_generation_paused(
    internal_id: str,
    operator_store: FleetOperatorStoreProtocol,
) -> bool:
    """trial-end-notification-design.md 4節の一時停止判定。aircon-pasha/
    cloud_function_webhook.pyの`_is_generation_paused()`と同じ契約: `trialEndNotifiedAt`
    (条件A/Bいずれの経路でもrecord_generation_and_get_trial_end_notice()等が設定済み)が
    設定済みで、かつ`upgradedAt`が未設定(有料転換前)の場合のみ一時停止対象とする。
    Webフォーム送信処理本体(mvp-flow-draft.md)からの実際の呼び出し配線(この関数が
    Trueを返した場合にGENERATION_PAUSED_NOTICEを返して記録整形自体をスキップする分岐)は
    本venture未実装のため次回以降の課題のまま。"""
    if operator_store.get_trial_end_notified_at(internal_id) is None:
        return False
    return operator_store.get_upgraded_at(internal_id) is None


# subscription-canceled-immediate-block-design.md相当(フェーズ129)。
CANCELED_NOTICE = (
    "ご契約が解約済みのため記録の整形を停止しています。再度ご利用いただくには、"
    "登録時にお送りしたアクセスURLからプランを選び直してください。"
)


def is_subscription_canceled(
    internal_id: str,
    operator_store: FleetOperatorStoreProtocol,
) -> bool:
    """kura-pasha/course-set-pasha/aircon-pashaで発見された欠落
    (`subscription_status == "canceled"`相当が専用分岐を持たず、有料転換済み
    〈upgraded_atが非null〉のユーザーが解約後も`is_generation_paused()`の対象に
    ならず無期限に生成を使い続けられてしまう)が本venture自体にも存在することを確認し、
    同型の修正として追加した判定。`canceled_at`が設定済みであれば、トライアル進捗・
    `upgraded_at`の値によらず常にTrueを返す(呼び出し側で`is_generation_paused()`より
    先に判定する想定、design「3. 修正内容」のaircon-pasha方針と同じ優先順位)。"""
    return operator_store.get_canceled_at(internal_id) is not None
