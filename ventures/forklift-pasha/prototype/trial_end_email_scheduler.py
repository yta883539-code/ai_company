#!/usr/bin/env python3
"""trial-end-notification-design.md 1節(B)経路・6節「今後の課題」で机上設計のみに留めていた
日次スケジューラ本体(期間到達によるトライアル終了メール通知)を実行可能なコードに落とし込んだもの
(README.mdフェーズ132「次回候補(2)」)。

位置づけ:
- 実際のCloud Scheduler実行環境の構築(GCPプロジェクトの課金設定を伴う)・実際のメール送信
  (送信元ドメイン・SMTP/メールAPIの選定を含む外部への送信行為)はいずれもオーナーの許可が
  必要なアクションに該当し、既にpending-approval.md(2026-10-10 18:00 UTC記載)に記録済みの
  承認待ち事項である。本モジュールはそれとは別に、kura-pasha/prototype/daily_scheduler.py・
  course-set-pasha/prototype/payment_failure_reminder_scheduler.pyと同じ位置づけで、
  「いつ・どの事業者にメール通知を送るべきか」の判定ロジック(design 2節(B)経路)、メール
  文面の組み立て(design 3節(B))、送信配線(実メール送信クライアントなしで検証可能な
  Protocol越しの呼び出し)を実クラウド接続なしで実装したもの。
- README.mdフェーズ132の設計指針どおり、`trial_management.is_subscription_canceled()`を
  他の全判定(トライアル終了判定等)より最優先で評価し、解約済みの事業者は即時除外する
  (course-set-pasha・kura-pasha・aircon-pashaで発生した「解約確定が既存の複数独立フラグに
  紛れて専用分岐を持たない」欠落の再発を防ぐための事前申し送りを実装に反映したもの)。
- アクセスURL(メール本文中の「▼ アクセスURL」)は、payment-identity-verification-design.md
  (フェーズ95)が定めるサーバー発行のランダムなアクセストークンから組み立てる想定だが、
  当該トークンの読み書きを行うストア自体が本venture未実装のため、本モジュールでは
  course-set-pasha/payment_failure_reminder_scheduler.pyのPortalLinkProvider/
  PORTAL_LINK_UNAVAILABLE_FALLBACKと同じ考え方の`AccessUrlProvider`(未接続時はNone)で
  抽象化し、未接続時は案内文をサポート窓口への問い合わせに差し替える安全側のフォールバックと
  する(次回候補に実ストア接続を残す)。

設計の参照元: trial-end-notification-design.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Protocol, Sequence

from trial_management import (
    TRIAL_PERIOD_DAYS,
    FleetOperatorStoreProtocol,
    is_subscription_canceled,
)

# ---------------------------------------------------------------------------
# 抽出ロジック (design 2節(B)経路)
# ---------------------------------------------------------------------------


def is_trial_end_email_due(
    internal_id: str,
    now: datetime,
    operator_store: FleetOperatorStoreProtocol,
    trial_period_days: int = TRIAL_PERIOD_DAYS,
) -> bool:
    """design 1節(B)「対象者(`trialStartAt`から30日経過かつ`trialEndNotifiedAt`未設定の
    `fleet_operator`)を抽出」をそのままコード化したもの。

    以下すべてを満たす場合のみTrueを返す(フェーズ132の設計指針どおり、解約済み判定を
    他の全判定より先に評価する)。
    - `is_subscription_canceled()`がFalse(解約済み事業者は即時除外、他の判定より最優先)
    - `trial_start_at`が設定済み(初回生成前の事業者は対象外)
    - `trial_end_notified_at`が未設定((A)経路〈生成回数到達〉で既に通知済みの場合は
      (B)経路側では再通知しない、`should_notify_trial_end()`と同じ「いずれか早い方で
      1回のみ」の方針)
    - `now - trial_start_at >= trial_period_days`日(「ちょうど」ではなく「以上」の範囲
      条件とし、日次実行の遅延・欠落に自然に耐える、kura-pasha/daily_scheduler.pyの
      `is_trial_end_report_due()`と同じ考え方)
    """

    if is_subscription_canceled(internal_id, operator_store):
        return False
    trial_start_at = operator_store.get_trial_start_at(internal_id)
    if trial_start_at is None:
        return False
    if operator_store.get_trial_end_notified_at(internal_id) is not None:
        return False
    return now >= trial_start_at + timedelta(days=trial_period_days)


def select_due_trial_end_emails(
    internal_ids: Sequence[str],
    now: datetime,
    operator_store: FleetOperatorStoreProtocol,
    trial_period_days: int = TRIAL_PERIOD_DAYS,
) -> list[str]:
    """internal_idsのうち`is_trial_end_email_due()`がTrueのものだけを、入力順を維持して
    返す。"""

    return [
        internal_id
        for internal_id in internal_ids
        if is_trial_end_email_due(internal_id, now, operator_store, trial_period_days)
    ]


# ---------------------------------------------------------------------------
# メッセージ整形 (design 3節(B))
# ---------------------------------------------------------------------------

EMAIL_SUBJECT = "【フォークリフトパシャっと】無料トライアル終了のお知らせ"

ACCESS_URL_UNAVAILABLE_FALLBACK = (
    "▼ アクセスURL\n"
    "お手数ですが、サポート窓口へアクセスURLの再発行をご依頼ください。"
)


class AccessUrlProvider(Protocol):
    """payment-identity-verification-design.mdが定めるサーバー発行のアクセストークンから
    `https://<ドメイン>/f/{accessToken}`形式のURLを組み立てる実装を想定したProtocol
    (course-set-pasha/cloud_function_webhook.PortalLinkProviderと同じ「未接続時はNoneを
    返す」契約)。当該トークンの読み書きを行う実ストア自体が本venture未実装のため、
    現時点では具象実装を持たない(次回候補)。"""

    def get_access_url(self, internal_id: str) -> "str | None":
        ...


def render_trial_end_email_body(
    generation_count: int,
    internal_id: str,
    access_url_provider: Optional[AccessUrlProvider],
) -> str:
    """design 3節(B)のメール本文草案をそのまま組み立てる。`access_url_provider`が未指定、
    またはURL取得自体に失敗した場合は、壊れたURLをそのまま顧客に見せず
    `ACCESS_URL_UNAVAILABLE_FALLBACK`へ差し替える(course-set-pasha/
    render_payment_failure_reminder_message()と同じ安全側のフォールバック方針)。"""

    url = None
    if access_url_provider is not None:
        url = access_url_provider.get_access_url(internal_id)
    access_url_section = f"▼ アクセスURL\n{url}" if url else ACCESS_URL_UNAVAILABLE_FALLBACK
    return (
        "いつもフォークリフトパシャっとをご利用いただきありがとうございます。\n"
        "本日で無料トライアル期間(30日間)が終了しました。\n"
        "\n"
        f"これまでの点検記録整形実績: {generation_count}回\n"
        "\n"
        "引き続きご利用いただく場合は、以下のアクセスURLからプランをお選びください。\n"
        "このまま何もしなければ自動課金は発生せず、生成のみ一時停止となります。\n"
        "\n"
        f"{access_url_section}"
    )


# ---------------------------------------------------------------------------
# 実送信配線 ((B)経路本体)
# ---------------------------------------------------------------------------


class EmailDeliveryError(Exception):
    """実メール送信クライアントが送信失敗を表すために投げる想定の例外
    (course-set-pasha/trial_end_scheduler.LinePushDeliveryErrorのメール版)。"""


class EmailSenderClient(Protocol):
    def send_email(self, to_email: str, subject: str, body: str) -> None:
        ...


class InMemoryEmailSenderClient:
    """実メール送信クライアント接続前の検証用実装(`InMemoryLinePushClient`のメール版)。
    送信内容を`sent`に積むのみで、実際の配信は行わない。"""

    def __init__(self) -> None:
        self.sent: "list[tuple[str, str, str]]" = []  # (to_email, subject, body)

    def send_email(self, to_email: str, subject: str, body: str) -> None:
        self.sent.append((to_email, subject, body))


@dataclass
class SendTrialEndEmailsResult:
    """1回のスケジューラ起動での送信結果(呼び出し側のログ・監視用、
    course-set-pasha/SendPaymentFailureRemindersResultと対称)。"""

    sent: "list[str]" = field(default_factory=list)  # internal_id
    failed: "list[str]" = field(default_factory=list)  # internal_id(送信失敗、次回起動時に再試行)
    skipped_no_email: "list[str]" = field(default_factory=list)  # internal_id(emailが未設定)


def send_trial_end_emails(
    internal_ids: Sequence[str],
    now: datetime,
    operator_store: FleetOperatorStoreProtocol,
    email_client: EmailSenderClient,
    access_url_provider: Optional[AccessUrlProvider] = None,
    trial_period_days: int = TRIAL_PERIOD_DAYS,
) -> SendTrialEndEmailsResult:
    """design 1節(B)経路の全体構成における本体。引数の`internal_ids`は呼び出し元で
    Firestoreから読み取った対象一覧を想定し(実際の絞り込みは`select_due_trial_end_emails()`
    が行う)、送信成功時のみ`operator_store.set_trial_end_notified_at()`を書き込む
    (送信失敗時は書き込まず、次回起動時に自然に再試行対象として残る。course-set-pasha/
    send_payment_failure_reminders()と同じ冪等性設計)。`email`が未設定の事業者
    (本来はpayment-identity-verification-design.mdの初回登録フローで必ず設定される想定だが、
    テストデータ不備等への安全策として)はスキップし`skipped_no_email`に記録する。"""

    result = SendTrialEndEmailsResult()
    for internal_id in select_due_trial_end_emails(
        internal_ids, now, operator_store, trial_period_days
    ):
        to_email = operator_store.get_email(internal_id)
        if not to_email:
            result.skipped_no_email.append(internal_id)
            continue
        body = render_trial_end_email_body(
            operator_store.get_trial_generation_count(internal_id),
            internal_id,
            access_url_provider,
        )
        try:
            email_client.send_email(to_email, EMAIL_SUBJECT, body)
        except EmailDeliveryError:
            result.failed.append(internal_id)
            continue
        operator_store.set_trial_end_notified_at(internal_id, now)
        result.sent.append(internal_id)
    return result


def run_due_trial_end_emails(
    operator_store: FleetOperatorStoreProtocol,
    now: datetime,
    email_client: EmailSenderClient,
    access_url_provider: Optional[AccessUrlProvider] = None,
    trial_period_days: int = TRIAL_PERIOD_DAYS,
) -> SendTrialEndEmailsResult:
    """design 6節が「呼び出し側(Cloud Scheduler経由の日次バッチ)が行う想定」として残していた、
    `operator_store.all_internal_ids()`による全事業者列挙→`send_trial_end_emails()`の
    store wiringを実装したもの(course-set-pasha/run_due_payment_failure_reminders()と対称)。
    """

    return send_trial_end_emails(
        operator_store.all_internal_ids(),
        now,
        operator_store,
        email_client,
        access_url_provider,
        trial_period_days,
    )


def _demo() -> None:
    from trial_management import InMemoryFleetOperatorStore

    store = InMemoryFleetOperatorStore()
    now = datetime(2026, 10, 12, 7, 0, 0)
    store.set_email("fo_1", "owner1@example.com")
    store.set_trial_start_at("fo_1", now - timedelta(days=31))
    store.increment_trial_generation_count("fo_1")
    store.increment_trial_generation_count("fo_1")

    email_client = InMemoryEmailSenderClient()
    result = run_due_trial_end_emails(store, now, email_client)
    print(f"sent={result.sent} failed={result.failed} skipped_no_email={result.skipped_no_email}")
    print(f"delivered={email_client.sent}")


if __name__ == "__main__":
    _demo()
