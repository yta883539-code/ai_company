"""kura-pasha LINE Messaging Webhook層の基盤部分(フェーズ62)。

trial-end-notification-design.md「6. 今後の課題」で繰り返し残っていた「本venture自体に
LINE Webhook層(cloud_function_webhook.py相当)が存在しない」というギャップに対応する
最初の一歩。aircon-pashaのwebhook-http-entry-point-design.md(フェーズ115)・
trial-end-condition-a-cta-design.md(フェーズ137)と同じ構成要素を踏襲するが、本venture側は
process_memo_event()本体(LLM呼び出し・schema/output.schema.jsonの17通りのstatus分岐を
テキスト返信へ変換する処理)がまだ存在しないため、本フェーズは以下の基盤部品のみに
スコープを絞る。

1. verify_line_signature(): 署名検証(line-reservation-ai/course-set-pasha/aircon-pashaと
   同じHMAC-SHA256実装)。
2. QuickReplyButton / ReplyClient / InMemoryReplyClient: 返信へpostbackボタンを添付する
   ための抽象化(aircon-pashaのReplyClient.quick_reply引数と同じ設計)。
3. format_trial_end_notification_message(): trial-end-notification-design.md 3節の
   通知文言を実装する(経路(A)生涯最初の生成完了時の返信への便乗、経路(B)期間到達時の
   プッシュ送信のいずれからも呼び出せる共通関数)。

process_memo_event()本体(LLM出力の17通りのstatus分岐をテキストへ変換する処理)・
receive_webhook()(HTTPエントリポイント)・dispatch_webhook_events()は本フェーズの対象外
とし、次の課題として残す(README.md参照)。実LINE Messaging API接続・実チャネルシークレット
の取得はいずれもオーナー承認待ち(pending-approval.md参照)のため、本モジュールは検証用の
InMemory実装にとどめる。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import random
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Protocol, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "schema"))

from checkout_session import (
    START_CHECKOUT_POSTBACK_DATA,
    build_checkout_session_params,
    parse_start_checkout_postback_data,
)
from payment_failure_notification import PAYMENT_SUSPENDED_NOTICE
from usage_counter_workshop import (
    PaymentSuspendedError,
    TrialPeriodOverError,
    UsageCounterStoreProtocol,
    UserProfileStoreProtocol,
    WorkshopStoreProtocol,
    process_generation_request,
)
from validate_test_cases import (  # noqa: E402
    SCHEMA,
    validate_against_schema,
    validate_cross_field_rules,
)
from workshop_linking import (  # noqa: E402
    LinkingCodeStoreProtocol,
    RandomChoiceSource,
    create_workshop_from_linking_code,
    issue_linking_code_on_follow,
)


def verify_line_signature(
    body: bytes, signature_header: Optional[str], channel_secret: str
) -> bool:
    """line-reservation-ai/course-set-pasha/aircon-pashaと同じHMAC-SHA256実装。

    - signature_headerが空(None・空文字列)の場合は即False。
    - channel_secretでのHMAC-SHA256署名をBase64エンコードした値と、
      signature_headerをhmac.compare_digest()で比較する(タイミング攻撃対策)。
    - 実際のchannel_secretの値はLINE公式アカウント開設(アカウント作成、オーナー承認待ち)
      後に得られる値のため、検証ロジック自体はここで実装するが実運用の検証はその後になる。
    """
    if not signature_header:
        return False
    digest = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature_header)


@dataclass(frozen=True)
class QuickReplyButton:
    """テキスト返信・プッシュメッセージに添付するpostbackボタン1個分
    (trial-end-notification-design.md 3節・3.1節)。aircon-pashaの同名クラスと同じ設計だが、
    本ventureは複数プランの出し分け(aircon-pashaのcheckout-session-plan-selection-
    design.md相当)を採用していないため、ボタン1個分の単純な構造にとどめる。
    """

    label: str
    postback_data: str


class ReplyClient(Protocol):
    def reply(
        self,
        reply_token: str,
        message_text: str,
        *,
        quick_reply: Optional[QuickReplyButton] = None,
    ) -> None:
        """呼び出し自体が失敗した場合は例外を送出する契約とする(実LINE API接続は
        オーナー承認待ちのため未実装)。quick_replyが渡された場合、実装側はLINE
        Messaging APIのテキストメッセージオブジェクトに`quickReply.items`として
        1件分のpostbackアクションを追加する想定。"""
        ...


class InMemoryReplyClient:
    """実LINE API接続の代わりに送信内容を記録するだけの検証用クライアント。

    `sent`は`(reply_token, message_text)`の2要素タプル、quick_replyは別属性
    `quick_replies_sent`(indexが`sent`と対応)に記録する(aircon-pashaの
    InMemoryReplyClientと同じ方針)。
    """

    def __init__(self) -> None:
        self.sent: List[Tuple[str, str]] = []
        self.quick_replies_sent: List[Optional[QuickReplyButton]] = []

    def reply(
        self,
        reply_token: str,
        message_text: str,
        *,
        quick_reply: Optional[QuickReplyButton] = None,
    ) -> None:
        self.sent.append((reply_token, message_text))
        self.quick_replies_sent.append(quick_reply)


# trial-end-notification-design.md 3節。checkout_session.START_CHECKOUT_POSTBACK_DATA
# (フェーズ61、"action=start_checkout")と揃える(プラン未指定の汎用ボタン、
# parse_start_checkout_postback_data()がDEFAULT_CHECKOUT_PLANとして解釈する)。
TRIAL_END_BUTTON_LABEL = "有料プランへ進む"
TRIAL_END_QUICK_REPLY = QuickReplyButton(
    label=TRIAL_END_BUTTON_LABEL, postback_data=START_CHECKOUT_POSTBACK_DATA
)

# content-generation-time-estimate.md(フェーズ18)「1回あたり平均20分と仮定」の仮置き値。
_MINUTES_PER_GENERATION = 20


def format_trial_end_notification_message(generation_count: int) -> str:
    """trial-end-notification-design.md 3節の通知文言を組み立てる。

    generation_count: これまでの生成実績回数。経路(A)(生涯最初の生成完了)では常に1、
    経路(B)(30日間一度も生成されないまま期間到達)では常に0として呼び出す想定(design 2節)。
    0の場合は「浮いた事務作業時間の目安」の行を省略する(design 3節: 浮いた時間が0分と
    なり訴求にならないため省略する分岐)。ボタン本体(TRIAL_END_QUICK_REPLY)はLINEの
    quickReplyとして別途添付する想定のため、本文中には実際のURLやpostbackデータそのものを
    埋め込まない(aircon-pashaと同じ方針)。
    """
    if generation_count < 0:
        raise ValueError(f"generation_count must be >= 0: {generation_count!r}")
    lines = [
        "[鞍パシャッと] 無料トライアル、お疲れさまでした!",
        "",
        "これまでの生成実績:",
        f"・受注内容整理メモ・納品案内・お手入れ案内の生成: {generation_count}回",
    ]
    if generation_count > 0:
        minutes = generation_count * _MINUTES_PER_GENERATION
        lines += [
            "",
            f"浮いた事務作業時間の目安: 約{minutes}分(1回あたり平均20分と仮定、"
            "content-generation-time-estimate.md参照)",
        ]
    lines += [
        "",
        "引き続きご利用いただく場合は、下のボタンから有料プランをお選びください。",
        "このまま何もしなければ自動課金は発生せず、生成のみ一時停止となります。",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# process_follow_event()(フェーズ68)
#
# フェーズ66「次の課題」に残っていた「process_follow_event()自体(workshop_linking.pyを
# cloud_function_webhook.pyへ配線する処理)は未着手」に着手する。craftsman-account-
# linking-design.md 2節の通り、本ventureはaircon-pashaのような申込フォーム主導ではなく
# course-set-pashaと同じ「LINE友だち追加時にコードを発行する」方式を踏襲するが、
# 解決先が申込フォームではなく本venture固有のworkshop新規作成(design 3節)である点が
# 差分となる(prototype/workshop_linking.pyのcreate_workshop_from_linking_code()参照)。
# 友だち追加直後に届いたコードを職人がトーク上に送り返した際の解決(message event側での
# ルーティング)自体は本フェーズの対象外とし、引き続き次の課題として残す(README.md参照)。
# ---------------------------------------------------------------------------

def format_follow_welcome_message(linking_code: str) -> str:
    """craftsman-account-linking-design.md 2節のウェルカムメッセージ本文を組み立てる。

    course-set-pashaのformat_welcome_message()と異なり、本ventureには申込フォームが
    存在せず連携コードはこのままLINEトーク上に送り返してもらう想定(design 1節)のため、
    フォームURLの差し込みは行わない(固定テンプレート+コード埋め込みのみ)。
    """
    return (
        "鞍パシャッと 友だち追加ありがとうございます!\n\n"
        "このサービスは、依頼内容の簡単なメモを送るだけで受注内容整理メモ・納品案内・"
        "お手入れ案内の下書きをまとめて生成するツールです。\n\n"
        "ご利用開始には、下記の連携コードをこのままこのトークに送信してください"
        "(24時間有効・1回限り)。\n\n"
        f"連携コード: {linking_code}\n\n"
        "コードの有効期限が切れた場合は、もう一度このトークを開くと新しいコードが届きます。"
    )


@dataclass
class FollowProcessResult:
    """process_follow_event()の結果(design 2節)。course-set-pashaのFollowProcessResultと
    同じ構造だが、profile_storeによるis_following復帰・purge_throttle便乗パージは
    本venture未着手(該当する設計・残課題自体が存在しない)のため対象外とする。"""

    handled: bool
    reply_sent: bool
    linking_code: Optional[str] = None


def process_follow_event(
    event: dict,
    linking_store: LinkingCodeStoreProtocol,
    reply_client: ReplyClient,
    *,
    rng: Optional[RandomChoiceSource] = None,
    now: Optional[datetime] = None,
) -> FollowProcessResult:
    """LINEの`follow`イベント1件を処理する(署名検証済みの前提、design 2節)。

    1. `event["type"] != "follow"`の場合は対象外としhandled=Falseで返す。
    2. `source.userId`が取得できない場合はhandled=Trueのまま何もせず返す
       (`workshop_linking.issue_linking_code_on_follow()`はuser_id必須のため)。
    3. 連携コードを発行し(`workshop_linking.issue_linking_code_on_follow()`、
       `rng`未指定時は`random.Random()`)、`format_follow_welcome_message()`で
       組み立てたウェルカムメッセージを返信する。
    """
    if event.get("type") != "follow":
        return FollowProcessResult(handled=False, reply_sent=False)

    user_id = event.get("source", {}).get("userId")
    if not user_id:
        return FollowProcessResult(handled=True, reply_sent=False)

    resolved_now = now if now is not None else datetime.now(timezone.utc)
    resolved_rng = rng if rng is not None else random.Random()
    linking_code = issue_linking_code_on_follow(
        user_id, linking_store, resolved_now, resolved_rng
    )
    message_text = format_follow_welcome_message(linking_code)
    reply_sent = _reply_with_retry(reply_client, event["replyToken"], message_text)
    return FollowProcessResult(handled=True, reply_sent=reply_sent, linking_code=linking_code)


@dataclass
class UnfollowProcessResult:
    """process_unfollow_event()の結果(unfollow-billing-faq.md「前提の整理」節)。"""

    handled: bool


def process_unfollow_event(event: dict) -> UnfollowProcessResult:
    """LINEの`unfollow`イベント1件を処理する(署名検証済みの前提)。

    unfollow-billing-faq.md「前提の整理」節の通り、ブロック中はLINEへの返信自体が
    送達不可であるため返信は行わない。aircon-pasha等のprocess_unfollow_event()と異なり、
    本ventureのWorkshopStoreProtocol/UserProfileStoreProtocolにはis_following相当の
    フラグが存在せず(craftsman-account-linking-design.mdにもblocked-but-billing検知
    〈他venture相当〉の設計自体がまだ無い、unfollow-billing-faq.md「今後の課題」参照)、
    契約情報(plan_id・subscription_status等)を変更する対象も無いため、本関数は
    イベント種別の判定とhandled=Trueを返すのみの受け皿にとどめる(契約情報不変という
    設計判断は他venture3件と揃っている)。
    """
    if event.get("type") != "unfollow":
        return UnfollowProcessResult(handled=False)

    return UnfollowProcessResult(handled=True)


# ---------------------------------------------------------------------------
# process_memo_event()本体(フェーズ63)
#
# README.md「次にやること」(フェーズ62)に残っていた3つの未着手項目のうち、
# process_memo_event()本体(LLM出力の17通りのstatus分岐をテキストへ変換する処理)に着手する。
# aircon-pasha/prototype/cloud_function_webhook.pyのprocess_memo_event()と同じ骨格
# (LLM呼び出し即時1回リトライ→スキーマ検証→検証エラー時は同一入力で1回だけ再生成→
# それでも検証エラーなら定型フォールバック文言)を踏襲するが、本ventureはusage_counter・
# profile_store(トライアル生成回数カウント・生成一時停止・決済失敗制限モード)を
# まだ持たないため、それらのケースは対象外とし引き続き次の課題として残す(README.md参照)。
# receive_webhook()(HTTPエントリポイント)・dispatch_webhook_events()も本フェーズの対象外。
# ---------------------------------------------------------------------------

class LlmApiError(Exception):
    """llm_call.generate()自体が失敗した(タイムアウト・5xx・429・ネットワーク断等)ことを
    表す例外。実クライアント側はこの例外を送出する契約とする
    (aircon-pasha/course-set-pashaのapi-call-failure-handling.md方針1と同じ設計)。"""


class ReplyApiError(Exception):
    """reply_client.reply()自体が失敗したことを表す例外(方針2)。"""


class LlmCallClient(Protocol):
    def generate(self, memo_text: str, retry_context: Optional[str] = None) -> dict:
        """schema/output.schema.jsonに準拠した構造化出力(dict)を返す想定。

        retry_contextが渡された場合(1回目の検証エラー後の再生成時)、直前の出力の
        何が不正だったかの概要を実LLM接続後にプロンプトへ添える想定(他ventureの
        json-output-retry-fallback.md「同一入力で1回だけ再生成」方針を踏襲)。
        呼び出し自体が失敗した場合はLlmApiErrorを送出する契約とする。
        """
        ...


VALIDATION_FAILURE_FALLBACK_MESSAGE = (
    "内容の確認中に問題が発生しました。お手数ですが、もう一度メモを送り直してください。"
)

API_FAILURE_FALLBACK_MESSAGE = (
    "只今混み合っております。少し時間をおいて同じ内容をもう一度送ってください。"
)

# subscription-cancellation-flow-design.md 「1. 解約意図検知時の案内メッセージ」記載の
# プレースホルダ文字列(aircon-pasha/course-set-pashaのPORTAL_LINK_PLACEHOLDERと同じ位置づけ)。
PORTAL_LINK_PLACEHOLDER = "{Stripeカスタマーポータル URL}"

PORTAL_LINK_UNAVAILABLE_FALLBACK = (
    "現在、お手続きページの発行に失敗しました。お手数ですが、しばらく経ってから再度"
    "このメッセージを送信いただくか、サポート窓口まで直接ご連絡ください。"
)


class PortalLinkProvider(Protocol):
    """Stripe Billing Portalのセッション作成を表す差し替え可能なProtocol
    (aircon-pasha/course-set-pashaと同じ位置づけ)。実Stripe接続はオーナー承認待ちのため
    本モジュールではProtocol化のみ行う。取得できない場合はNoneを返す契約とする。"""

    def get_portal_url(self, user_id: str) -> Optional[str]:
        ...


class InMemoryPortalLinkProvider:
    """実Stripe接続の代わりに固定URL(またはNone)を返す検証用スタブ。"""

    def __init__(self, url: Optional[str] = "https://billing.stripe.com/p/session/stub") -> None:
        self._url = url

    def get_portal_url(self, user_id: str) -> Optional[str]:
        return self._url


def render_subscription_procedure_notice(
    notice: dict,
    portal_link_provider: Optional[PortalLinkProvider],
    user_id: Optional[str],
) -> str:
    """status=cancellation_intent/downgrade_intent/cancellation_unclearの
    subscription_procedure_notice.bodyを実際の返信文へ組み立てる
    (aircon-pashaの同名関数と同じ設計)。

    includes_portal_link=Falseの場合(cancellation_unclear)はbodyをそのまま返す
    (厳守事項7a(iv)準拠)。includes_portal_link=Trueの場合はPORTAL_LINK_PLACEHOLDERを
    実URLへ置換する。providerが未接続・user_id不明・URL取得失敗のいずれかの場合は
    プレースホルダの露出を避けるためPORTAL_LINK_UNAVAILABLE_FALLBACKへ全文差し替える。
    """
    body = notice["body"]
    if not notice["includes_portal_link"]:
        return body

    url = None
    if portal_link_provider is not None and user_id:
        url = portal_link_provider.get_portal_url(user_id)

    if not url:
        return PORTAL_LINK_UNAVAILABLE_FALLBACK

    return body.replace(PORTAL_LINK_PLACEHOLDER, url)


def format_generated_reply(instance: dict) -> str:
    """status=generatedの構造化出力を、出力1・出力2・出力3をまとめた1通の返信文に組み立てる。"""
    return "\n".join(
        [
            "【受注内容整理メモ】",
            instance["order_summary"]["body"],
            "",
            "【納品案内の下書き】",
            instance["delivery_notice"]["body"],
            "",
            "【お手入れ案内の下書き】",
            instance["care_notice"],
        ]
    )


def format_reply_text(
    instance: dict,
    *,
    portal_link_provider: Optional[PortalLinkProvider] = None,
    user_id: Optional[str] = None,
) -> str:
    """schema/output.schema.jsonの17通りのstatusを、実際の返信文へ変換する。"""
    status = instance["status"]
    if status == "generated":
        return format_generated_reply(instance)
    if status == "out_of_scope":
        return instance["out_of_scope_message"]
    if status == "insufficient_input":
        return instance["missing_fields_request"]
    if status in ("cancellation_intent", "downgrade_intent", "cancellation_unclear"):
        return render_subscription_procedure_notice(
            instance["subscription_procedure_notice"], portal_link_provider, user_id
        )
    if status in ("member_retention_selection", "member_retention_unclear"):
        return instance["member_retention_notice"]["body"]
    if status in ("contractor_transfer_selection", "contractor_transfer_unclear"):
        return instance["contractor_transfer_notice"]["body"]
    if status in (
        "contractor_transfer_confirmed",
        "contractor_transfer_cancelled",
        "contractor_transfer_reconfirm_unclear",
    ):
        return instance["contractor_transfer_confirmation"]["body"]
    if status == "contractor_transfer_expired_notice":
        return instance["contractor_transfer_expired_notice"]["body"]
    if status in ("checkout_intent", "pricing_inquiry", "checkout_intent_unclear"):
        return instance["checkout_notice"]["body"]
    raise ValueError(f"unexpected status: {status!r}")


def validate_llm_output(instance: dict) -> List[str]:
    """スキーマ適合性・クロスフィールドルールをまとめて検証し、エラーメッセージの
    リストを返す(空リスト=検証OK)。schema/validate_test_cases.pyのvalidate_against_schema()・
    validate_cross_field_rules()をそのまま再利用する(他venture同様、後処理ヒューリスティック
    〈post_generation_checks相当〉は本ventureに存在しないため対象外)。"""
    errors = validate_against_schema(instance, SCHEMA)
    if errors:
        # スキーマ自体に適合しない場合、cross-fieldチェックはstatus等の前提が崩れているため
        # 実行しない(aircon-pasha/course-set-pashaと同じ考え方)。
        return errors
    return errors + validate_cross_field_rules(instance)


# trial-end-condition-design.md(フェーズ52)・payment-failure-dunning-design.md
# (フェーズ56)がそれぞれ`TrialPeriodOverError`・`PaymentSuspendedError`送出時の
# 呼び出し側文言として名指ししていた定数(README.mdフェーズ52・payment-failure-
# dunning-design.md 4節「制限モード移行時(段階3)」参照)。PAYMENT_SUSPENDED_NOTICEは
# design 4節の文言をそのまま踏襲し`payment_failure_notification.py`に定義済み(本フェーズで
# 新設)、TRIAL_PERIOD_OVER_NOTICEは対応する verbatim 文言が設計文書内に無かったため、
# aircon-pashaのGENERATION_PAUSED_MESSAGEと同じ構成(状態説明+CTA)で本フェーズ新規に
# 組み立てる。CTAボタンはTRIAL_END_QUICK_REPLY(フェーズ62で定義済み)をそのまま再利用する。
TRIAL_PERIOD_OVER_NOTICE = (
    "無料トライアル期間(初回の生成1回、またはworkshop作成から30日のいずれか早い方)が"
    "終了したため、受注内容整理メモ・納品案内・お手入れ案内の生成を一時停止しています。\n"
    "引き続きご利用いただく場合は、下のボタンから有料プランへお進みください。"
)


@dataclass
class MemoProcessResult:
    handled: bool  # False=テキスト以外の単体イベント等、本フローの処理対象外だったため何もしなかった
    reply_sent: bool
    reply_text: Optional[str]
    validation_errors: list = field(default_factory=list)
    retried: bool = False  # True=1回目の検証エラー後、再生成を1回試みた
    api_failure: bool = False  # True=LLM API呼び出し自体が即時リトライ後も失敗した
    generation_paused: bool = False  # True=トライアル終了・未アップグレードのため一時停止応答
    payment_suspended: bool = False  # True=決済失敗の猶予期間超過による制限モードの応答
    trial_end_notification_sent: bool = False  # True=今回の返信にトライアル終了通知を便乗させた


def _summarize_errors_for_retry(errors: List[str]) -> str:
    """再生成プロンプトに添える検証エラーの短い概要(実LLM接続後に使用)。"""
    return "; ".join(errors[:3])


def _generate_with_api_retry(
    llm_call: LlmCallClient,
    memo_text: str,
    retry_context: Optional[str] = None,
) -> dict:
    """LLM API呼び出し自体の失敗(LlmApiError)に対し、即時1回のみリトライする。
    2回とも失敗した場合はLlmApiErrorをそのまま呼び出し元へ伝播させる。"""
    try:
        return llm_call.generate(memo_text, retry_context=retry_context)
    except LlmApiError:
        return llm_call.generate(memo_text, retry_context=retry_context)


def _reply_with_retry(
    reply_client: ReplyClient,
    reply_token: str,
    message_text: str,
    *,
    quick_reply: Optional[QuickReplyButton] = None,
) -> bool:
    """Reply API呼び出し自体の失敗(ReplyApiError)に対し、即時1回のみリトライする。
    reply_tokenは1回限り有効なため、2回とも失敗した場合はこれ以上何もできない。
    呼び出し元がreply_sent=Falseとして結果を扱えるようboolを返す(例外は外へ伝播させない)。"""
    kwargs = {"quick_reply": quick_reply} if quick_reply is not None else {}
    try:
        reply_client.reply(reply_token, message_text, **kwargs)
        return True
    except ReplyApiError:
        pass
    try:
        reply_client.reply(reply_token, message_text, **kwargs)
        return True
    except ReplyApiError:
        return False


def process_memo_event(
    event: dict,
    llm_call: LlmCallClient,
    reply_client: ReplyClient,
    *,
    portal_link_provider: Optional[PortalLinkProvider] = None,
    user_profile_store: Optional[UserProfileStoreProtocol] = None,
    workshop_store: Optional[WorkshopStoreProtocol] = None,
    usage_counter_store: Optional[UsageCounterStoreProtocol] = None,
    now: Optional[datetime] = None,
) -> MemoProcessResult:
    """テキストメモ1件を処理する(署名検証等の受信基盤側の処理は別モジュールの前提)。

    設計上の判断(mvp-flow-draft.md準拠、aircon-pashaのprocess_memo_event()と同じ骨格):
    1. message.type != "text" のイベント(画像単体送信等)は本フローの対象外とし、
       返信を送らずhandled=Falseで返す。
    2. LLM呼び出し結果を検証し、エラーがあれば同一入力で1回だけ再生成をリクエストする。
       再生成後もエラーが残る場合は安全側に倒し、定型の再送依頼文言を返す。
    3. status=cancellation_intent/downgrade_intent/cancellation_unclearの場合、
       portal_link_providerが渡されていればsubscription_procedure_notice.body中の
       ポータルURLプレースホルダを実URLへ置換する。未接続時は安全側フォールバック文言を返す。
    4. (フェーズ64、新設) `user_profile_store`・`workshop_store`・`usage_counter_store`の
       3つ全てが渡された場合のみ、LLM呼び出しの前に`usage_counter_workshop.
       process_generation_request()`(フェーズ30〜60で実装済みの統合エントリポイント)を
       呼び出す。これは(1)`check_and_apply_pending_member_reduction`→(2)
       `ensure_member_is_active`→(3)`is_payment_suspended`/`is_trial_period_over`による
       生成可否判定→(4)`check_and_increment_usage`→(5)トライアル終了通知要否判定、の順で
       実行される(usage_counter_workshop.py参照)。`TrialPeriodOverError`・
       `PaymentSuspendedError`が送出された場合はLLM呼び出しを行わずそれぞれ
       `TRIAL_PERIOD_OVER_NOTICE`・`PAYMENT_SUSPENDED_NOTICE`を返信して即座に処理を終える
       (aircon-pashaの`_is_generation_paused()`/`_is_payment_suspended()`と同じ「LLM呼び出し
       前にブロックする」方針)。3つのうちいずれかが未接続(None)の場合は本ブロックを
       スキップし、従来通りusage_counter・トライアル判定なしで動作する(安全側デフォルト、
       本venture側にまだdispatch層〈フェーズ62・63で次の課題として残した`dispatch_webhook_
       events()`〉が無く常に連携済みuser_idのみがここへ到達する前提が確立していないため)。
       `WorkshopNotLinkedError`・`MemberRemovedError`(未連携user_id・除外済みメンバーからの
       リクエスト)はいずれもdispatch層が連携状態に応じてルーティングを振り分ける前提
       (aircon-pashaのdispatch_webhook_events()参照)で、本venture側dispatch層が未実装の
       現時点ではこの前提が保証されないため、あえて捕捉せずそのまま呼び出し元へ伝播させる
       (次の課題)。
    5. (フェーズ64、新設) 4.の`process_generation_request()`が
       `GenerationRequestResult.trial_end_notification_due=True`を返した場合(経路(A)、
       trial-end-notification-design.md 2節)、最終的な返信文の末尾に
       `format_trial_end_notification_message(1)`(経路(A)は常に実績1回、design 2節)を
       付記し、`TRIAL_END_QUICK_REPLY`を返信のquick_replyとして添付する
       (aircon-pashaのフェーズ137相当、追加のPush API呼び出し・課金を発生させない方針)。
       この付記は`process_generation_request()`がLLM呼び出し前に実行される(4.参照)ため、
       最終的なstatusがgenerated以外(out_of_scope等)であっても行われる。これは
       `trial_generation_used`自体がLLM呼び出しの成否・内容と独立して「生成リクエストを
       受け付けた時点」で確定する既存の設計(usage_counter_workshop.pyフェーズ60時点の
       実装、`process_generation_request()`のdocstring参照)をそのまま踏襲したものであり、
       本フェーズで新たな判断を加えたものではない。なお、4.の時点で`trial_end_notified_at`
       は既に書き込み済みのため、この後LLM呼び出し自体が失敗(`api_failure=True`)・
       検証エラーが2回とも解消しない(定型フォールバック文言を返す)場合、通知文言は
       ユーザーへ届かないまま「送信済み」として記録される(二重送信防止フラグが先に
       立ってしまうため、次回以降の生成でも再送されない)。発生頻度は低いと見込むが
       未解消の既知の制約として次の課題に残す。
    """
    message = event.get("message", {})
    if message.get("type") != "text":
        return MemoProcessResult(handled=False, reply_sent=False, reply_text=None)

    reply_token = event["replyToken"]
    memo_text = message["text"]
    user_id = event.get("source", {}).get("userId")

    trial_end_notification_due = False
    if (
        user_profile_store is not None
        and workshop_store is not None
        and usage_counter_store is not None
        and user_id
    ):
        resolved_now = now if now is not None else datetime.now(timezone.utc)
        try:
            generation_result = process_generation_request(
                user_id, resolved_now, user_profile_store, workshop_store, usage_counter_store,
            )
        except TrialPeriodOverError:
            reply_sent = _reply_with_retry(
                reply_client, reply_token, TRIAL_PERIOD_OVER_NOTICE, quick_reply=TRIAL_END_QUICK_REPLY,
            )
            return MemoProcessResult(
                handled=True, reply_sent=reply_sent,
                reply_text=TRIAL_PERIOD_OVER_NOTICE if reply_sent else None,
                generation_paused=True,
            )
        except PaymentSuspendedError:
            reply_sent = _reply_with_retry(reply_client, reply_token, PAYMENT_SUSPENDED_NOTICE)
            return MemoProcessResult(
                handled=True, reply_sent=reply_sent,
                reply_text=PAYMENT_SUSPENDED_NOTICE if reply_sent else None,
                payment_suspended=True,
            )
        trial_end_notification_due = generation_result.trial_end_notification_due

    try:
        instance = _generate_with_api_retry(llm_call, memo_text)
    except LlmApiError:
        reply_sent = _reply_with_retry(reply_client, reply_token, API_FAILURE_FALLBACK_MESSAGE)
        return MemoProcessResult(
            handled=True, reply_sent=reply_sent,
            reply_text=API_FAILURE_FALLBACK_MESSAGE if reply_sent else None, api_failure=True,
        )

    errors = validate_llm_output(instance)
    retried = False

    if errors:
        retried = True
        try:
            instance = _generate_with_api_retry(
                llm_call, memo_text, retry_context=_summarize_errors_for_retry(errors)
            )
        except LlmApiError:
            reply_sent = _reply_with_retry(reply_client, reply_token, API_FAILURE_FALLBACK_MESSAGE)
            return MemoProcessResult(
                handled=True, reply_sent=reply_sent,
                reply_text=API_FAILURE_FALLBACK_MESSAGE if reply_sent else None,
                retried=retried, api_failure=True,
            )
        errors = validate_llm_output(instance)

    if errors:
        reply_sent = _reply_with_retry(reply_client, reply_token, VALIDATION_FAILURE_FALLBACK_MESSAGE)
        return MemoProcessResult(
            handled=True, reply_sent=reply_sent,
            reply_text=VALIDATION_FAILURE_FALLBACK_MESSAGE if reply_sent else None,
            validation_errors=errors, retried=retried,
        )

    reply_text = format_reply_text(
        instance, portal_link_provider=portal_link_provider, user_id=user_id,
    )
    if trial_end_notification_due:
        reply_text = f"{reply_text}\n\n{format_trial_end_notification_message(1)}"
    reply_sent = _reply_with_retry(
        reply_client, reply_token, reply_text,
        quick_reply=TRIAL_END_QUICK_REPLY if trial_end_notification_due else None,
    )
    return MemoProcessResult(
        handled=True, reply_sent=reply_sent, reply_text=reply_text if reply_sent else None, retried=retried,
        trial_end_notification_sent=reply_sent and trial_end_notification_due,
    )


# ---------------------------------------------------------------------------
# process_message_event()(フェーズ69)
#
# フェーズ68「トーク上で送り返されたコードのworkshop作成への解決(message event側で
# コード形式のテキストをcreate_workshop_from_linking_code()へルーティングする処理)」を
# 次の課題として残していたのに着手する。aircon-pashaのprocess_message_event()
# (user-account-linking-design.md 3節)と同じ骨格(連携済みか否かで最初に分岐し、
# 未連携時は受信テキストが連携コードと解決できるかどうかのみを判定根拠とする、
# 「辞書引き一致を必須とし正規表現の形式一致のみでは連携コードと判定しない」方針)を
# 踏襲する。ただし本ventureはworkshop_linking.pyのcreate_workshop_from_linking_code()が
# 解決(resolve)とworkshop新規作成を1つの関数にまとめている点、および
# user_profile_store・workshop_store・linking_store3つ全てが揃わない限り連携判定
# そのものを行わない後方互換設計(フェーズ64のusage_counter連携と同じ考え方)である点が
# aircon-pasha版との差分となる。dispatch_webhook_events()側は本フェーズでmessageイベントの
# 委譲先をprocess_memo_event()からprocess_message_event()へ差し替える。
# ---------------------------------------------------------------------------

LINKING_SUCCESS_MESSAGE = (
    "連携が完了しました。依頼内容の簡単なメモを送ってください。"
)

# design自体は解決失敗時の案内文言を確定させていないため、aircon-pashaのLINKING_REQUIRED_
# MESSAGEと同じ考え方(「連携コード自体が見つからない(未連携・期限切れ・入力ミス等)」と
# 「未連携のまま依頼メモを送った」を区別せず同一の案内に倒す)で本フェーズ新規に定める。
LINKING_REQUIRED_MESSAGE = (
    "先に連携コードの送信が必要です。友だち追加時にお送りした6文字の連携コードを、"
    "このトークにそのまま送信してください。コードの有効期限が切れた場合は、もう一度"
    "このトークを開くと新しいコードが届きます。"
)


def process_message_event(
    event: dict,
    llm_call: LlmCallClient,
    reply_client: ReplyClient,
    *,
    portal_link_provider: Optional[PortalLinkProvider] = None,
    user_profile_store: Optional[UserProfileStoreProtocol] = None,
    workshop_store: Optional[WorkshopStoreProtocol] = None,
    usage_counter_store: Optional[UsageCounterStoreProtocol] = None,
    linking_store: Optional[LinkingCodeStoreProtocol] = None,
    now: Optional[datetime] = None,
) -> MemoProcessResult:
    """messageイベントの入口(dispatch_webhook_events()からの委譲先)。

    `user_profile_store`・`workshop_store`・`linking_store`の3つ全てが渡された場合のみ、
    process_memo_event()へ進む前に連携状態で分岐する。

    - message.type != "text": process_memo_event()にそのまま委譲する(process_memo_event()
      自体が非テキストをhandled=Falseとして扱う既存の分岐をそのまま利用する)。
    - 連携済み(user_idかつ`user_profile_store.get_workshop_id(user_id)`が設定済み):
      process_memo_event()へそのまま委譲する。
    - 未連携: 受信テキストを`create_workshop_from_linking_code()`へ渡す。連携コードとして
      解決・workshop新規作成に成功した場合のみLINKING_SUCCESS_MESSAGEを返す。解決できない
      場合(コード不一致・期限切れ・依頼メモの先送り送信等、いずれも区別しない)は
      LINKING_REQUIRED_MESSAGEを返す。process_memo_event()へは一切進めない(未連携user_idの
      利用回数カウントを発生させないため)。
    - user_idが取得できない未連携イベント(通常発生しない想定)も安全側に倒し
      LINKING_REQUIRED_MESSAGEを返す。
    - 3つのストアのいずれかが未接続(None)の場合は、フェーズ68以前と同じ後方互換動作として
      連携判定自体を行わずprocess_memo_event()へ直接委譲する(本venture側dispatch層が
      「process_memo_eventへ到達するのは常に連携済みuser_idのみ」という前提をまだ
      保証していないケースを含む、フェーズ64のprocess_memo_event() docstring 4.と同じ考え方)。
    """
    linking_enabled = (
        user_profile_store is not None
        and workshop_store is not None
        and linking_store is not None
    )
    message = event.get("message", {})

    if not linking_enabled or message.get("type") != "text":
        return process_memo_event(
            event, llm_call, reply_client,
            portal_link_provider=portal_link_provider,
            user_profile_store=user_profile_store,
            workshop_store=workshop_store,
            usage_counter_store=usage_counter_store,
            now=now,
        )

    user_id = event.get("source", {}).get("userId")
    if user_id and user_profile_store.get_workshop_id(user_id) is not None:
        return process_memo_event(
            event, llm_call, reply_client,
            portal_link_provider=portal_link_provider,
            user_profile_store=user_profile_store,
            workshop_store=workshop_store,
            usage_counter_store=usage_counter_store,
            now=now,
        )

    reply_token = event["replyToken"]
    if not user_id:
        reply_sent = _reply_with_retry(reply_client, reply_token, LINKING_REQUIRED_MESSAGE)
        return MemoProcessResult(
            handled=True, reply_sent=reply_sent,
            reply_text=LINKING_REQUIRED_MESSAGE if reply_sent else None,
        )

    resolved_now = now if now is not None else datetime.now(timezone.utc)
    creation = create_workshop_from_linking_code(
        message.get("text"), linking_store, user_profile_store, workshop_store, resolved_now,
    )
    if creation.ok:
        reply_sent = _reply_with_retry(reply_client, reply_token, LINKING_SUCCESS_MESSAGE)
        return MemoProcessResult(
            handled=True, reply_sent=reply_sent,
            reply_text=LINKING_SUCCESS_MESSAGE if reply_sent else None,
        )

    reply_sent = _reply_with_retry(reply_client, reply_token, LINKING_REQUIRED_MESSAGE)
    return MemoProcessResult(
        handled=True, reply_sent=reply_sent,
        reply_text=LINKING_REQUIRED_MESSAGE if reply_sent else None,
    )


# ---------------------------------------------------------------------------
# process_postback_event()(フェーズ71)
#
# フェーズ70で次の課題として残した「postback(有料プラン開始ボタン押下の処理関数)」に
# 着手する。aircon-pasha/prototype/cloud_function_webhook.pyのprocess_postback_event()・
# checkout-initiation-flow-design.md(フェーズ50)3節の`handle_checkout_intent`手順2〜7
# (手順1のLLM意図検知はpostback発火時には不要、ボタンのdata自体がstart_checkout系である
# ことで意図が既に確定しているため)と同じ骨格を、本ventureのworkshop単位の
# WorkshopStoreProtocol/UserProfileStoreProtocolへ翻案する。トライアル終了通知の
# 「▼ 有料プランへ進む」ボタン(TRIAL_END_QUICK_REPLY、フェーズ61・62で
# postback_data="action=start_checkout"を確定済み)がタップされた際の入口となる。
#
# aircon-pashaのprocess_postback_event()と異なり、本ventureにはStripe Billing Portal相当の
# `action=update_payment_method`ボタンの設計自体が無い(payment-failure-dunning-design.md
# 「1. 前提」参照、PortalLinkProviderは通知本文へのURL差し込みではなく文言案内のみで代替する
# 設計のため)。よって本フェーズはstart_checkout系postback1種類のみを対象とし、それ以外の
# `data`(未知のアクション・未知のplan_id)はhandled=Falseとして素通りする(将来別アクションを
# 追加する場合の拡張点、aircon-pashaと同じ考え方)。
# ---------------------------------------------------------------------------

CONTRACTOR_ONLY_CHECKOUT_NOTICE = (
    "有料プランのお申し込みは、契約者(工房を最初に作成した方)のみ操作できます。"
    "お手数ですが、契約者の方から改めてお申し込みください。"
)

ALREADY_SUBSCRIBED_NOTICE = (
    "既にご契約中のため、この操作は不要です。プラン変更やお手続きについてご不明な点が"
    "あれば、そのままメモとしてご質問をお送りください。"
)


def format_checkout_reply_message(checkout_url: str) -> str:
    """checkout-initiation-flow-design.md 3節手順7の文面。aircon-pashaの
    format_checkout_reply_message()と同じくプレーンテキストでURLを案内する
    (Flex Message化は本フェーズの対応範囲外)。"""
    return (
        "お支払い手続きへのリンクをご案内します。下記URLからお進みください。\n"
        f"{checkout_url}"
    )


class CheckoutSessionClient(Protocol):
    """Stripe Checkout Session作成API呼び出しを表す差し替え可能なProtocol
    (checkout-initiation-flow-design.md 3節手順6、llm_call/reply_clientと同じ位置づけ)。
    実際の`stripe.checkout.Session.create(**params)`呼び出しは実Stripeアカウント接続後
    (オーナー承認待ち)に実クライアントへ差し替える。"""

    def create(self, params: dict) -> str:
        """`params`(build_checkout_session_params()の返り値)からCheckout SessionのURLを
        返す契約とする。"""
        ...


class InMemoryCheckoutSessionClient:
    """実Stripe接続の代わりに固定のプレースホルダURLを返すだけの検証用クライアント。
    呼び出しに使われたparamsを記録し、テストで組み立て内容を検証できるようにする。"""

    def __init__(self, url: str = "https://checkout.stripe.com/stub-session") -> None:
        self._url = url
        self.calls: List[dict] = []

    def create(self, params: dict) -> str:
        self.calls.append(params)
        return self._url


@dataclass
class PostbackEventResult:
    """process_postback_event()の結果。"""

    handled: bool
    reply_sent: bool
    checkout_url: Optional[str] = None


def process_postback_event(
    event: dict,
    checkout_session_client: CheckoutSessionClient,
    reply_client: ReplyClient,
    user_profile_store: UserProfileStoreProtocol,
    workshop_store: WorkshopStoreProtocol,
) -> PostbackEventResult:
    """LINEの`postback`イベント1件を処理する(署名検証済みの前提、checkout-initiation-
    flow-design.md 3節手順2〜7)。

    1. `event["postback"]["data"]`をparse_start_checkout_postback_data()で解釈し、
       start_checkout系以外(未知のアクション・未知のplan_id)はhandled=Falseで素通りする。
    2. `user_profile_store.get_workshop_id(user_id)`でworkshopを特定する。user_id欠落・
       未連携(workshop_id未設定)の場合はLINKING_REQUIRED_MESSAGEを返す(design 3節手順2の
       異常系、craftsman-account-linking-design.mdの連携コード案内へフォールバック)。
    3. `workshop_store.get_contractor_user_id(workshop_id)`と`user_id`が一致しない場合、
       CONTRACTOR_ONLY_CHECKOUT_NOTICEを返し打ち切る(design 1節の権限モデル、design 3節
       手順3)。
    4. `workshop_store.get_subscription_status(workshop_id)`が既に`"active"`の場合、
       ALREADY_SUBSCRIBED_NOTICEを返し重複契約を防ぐ(design 3節手順4)。
    5. `workshop_store.get_stripe_customer_id(workshop_id)`(既存顧客の再利用、design 3節
       手順5)・`build_checkout_session_params()`(design 4節)・
       `checkout_session_client.create()`(design 3節手順6)でCheckout SessionのURLを取得し、
       `format_checkout_reply_message()`で返信する(design 3節手順7)。
    """
    data = event.get("postback", {}).get("data")
    plan_id = parse_start_checkout_postback_data(data)
    if plan_id is None:
        return PostbackEventResult(handled=False, reply_sent=False)

    reply_token = event["replyToken"]
    user_id = event.get("source", {}).get("userId")
    workshop_id = user_profile_store.get_workshop_id(user_id) if user_id else None

    if workshop_id is None:
        reply_sent = _reply_with_retry(reply_client, reply_token, LINKING_REQUIRED_MESSAGE)
        return PostbackEventResult(handled=True, reply_sent=reply_sent)

    if user_id != workshop_store.get_contractor_user_id(workshop_id):
        reply_sent = _reply_with_retry(reply_client, reply_token, CONTRACTOR_ONLY_CHECKOUT_NOTICE)
        return PostbackEventResult(handled=True, reply_sent=reply_sent)

    if workshop_store.get_subscription_status(workshop_id) == "active":
        reply_sent = _reply_with_retry(reply_client, reply_token, ALREADY_SUBSCRIBED_NOTICE)
        return PostbackEventResult(handled=True, reply_sent=reply_sent)

    existing_stripe_customer_id = workshop_store.get_stripe_customer_id(workshop_id)
    params = build_checkout_session_params(workshop_id, plan_id, existing_stripe_customer_id)
    checkout_url = checkout_session_client.create(params)
    reply_sent = _reply_with_retry(reply_client, reply_token, format_checkout_reply_message(checkout_url))
    return PostbackEventResult(handled=True, reply_sent=reply_sent, checkout_url=checkout_url)


# ---------------------------------------------------------------------------
# dispatch_webhook_events() + receive_webhook()(フェーズ65、フェーズ68で follow を追加、
# フェーズ69でmessageの委譲先をprocess_message_event()へ差し替え、フェーズ70で unfollow
# を追加、フェーズ71で postback を追加)
#
# README.md「次にやること」に残っていたreceive_webhook()(HTTPエントリポイント)・
# dispatch_webhook_events()に着手する。aircon-pashaのwebhook-http-entry-point-design.md
# (フェーズ115)・dispatch_webhook_events()(フェーズ111〜114)と同じ構成を踏襲する。
# フェーズ68でprocess_follow_event()を実装したため、"follow"種別もmessageと同様に
# 振り分け対象へ追加した。フェーズ69で"message"種別の委譲先をprocess_memo_event()から
# process_message_event()(連携コード判定を挟む)へ差し替えた。フェーズ70でunfollowも
# process_unfollow_event()(handled=Trueを返すのみの受け皿)へ振り分けるようにした。
# unfollowはfollow/messageと異なり依存関係の有無を問わず常に処理する(返信を伴わず、
# 未接続でも安全側にフォールバックする必要が無いため)。フェーズ71でpostbackも
# process_postback_event()へ振り分けるようにした(message/followと同様、依存する
# reply_client・user_profile_store・workshop_store・checkout_session_clientのいずれかが
# 未接続の場合はignored_typesに記録して素通りする安全側フォールバック)。
# ---------------------------------------------------------------------------

@dataclass
class DispatchResult:
    """dispatch_webhook_events()の結果。"""

    message_results: List[MemoProcessResult] = field(default_factory=list)
    follow_results: List[FollowProcessResult] = field(default_factory=list)
    unfollow_results: List[UnfollowProcessResult] = field(default_factory=list)
    postback_results: List[PostbackEventResult] = field(default_factory=list)
    ignored_types: List[str] = field(default_factory=list)


def dispatch_webhook_events(
    events: List[dict],
    *,
    llm_call: Optional[LlmCallClient] = None,
    reply_client: Optional[ReplyClient] = None,
    portal_link_provider: Optional[PortalLinkProvider] = None,
    user_profile_store: Optional[UserProfileStoreProtocol] = None,
    workshop_store: Optional[WorkshopStoreProtocol] = None,
    usage_counter_store: Optional[UsageCounterStoreProtocol] = None,
    linking_store: Optional[LinkingCodeStoreProtocol] = None,
    checkout_session_client: Optional[CheckoutSessionClient] = None,
    rng: Optional[RandomChoiceSource] = None,
    now: Optional[datetime] = None,
) -> DispatchResult:
    """署名検証済みのWebhookリクエストの`events`配列を`event["type"]`ごとに振り分ける。

    - "message": 1件ずつprocess_message_event()(フェーズ69)へ渡す。`llm_call`・
      `reply_client`のいずれかが未接続(None)の場合は該当イベントを一切処理せず素通りする。
      `user_profile_store`・`workshop_store`・`linking_store`の3つはprocess_message_event()
      自体が省略可能な設計(3つ全てが揃わない限り連携判定自体を行わない後方互換設計)のため、
      未接続でもmessageイベントの処理自体は行う(その場合連携コード判定・usage_counter連携
      なしで、フェーズ68以前と同じくprocess_memo_event()への直接委譲として動作する)。
    - "follow"(フェーズ68で追加): 1件ずつprocess_follow_event()へ渡す。`reply_client`・
      `linking_store`のいずれかが未接続(None)の場合はmessageと同様、該当イベントを
      一切処理せず`ignored_types`に記録する(安全側フォールバック)。
    - "unfollow"(フェーズ70で追加): 1件ずつprocess_unfollow_event()へ渡す。返信を伴わず
      依存する外部ストアも無いため、message/followと異なり依存関係の有無を問わず常に処理する。
    - "postback"(フェーズ71で追加): 1件ずつprocess_postback_event()へ渡す。`reply_client`・
      `user_profile_store`・`workshop_store`・`checkout_session_client`のいずれかが未接続
      (None)の場合はmessage/followと同様、該当イベントを一切処理せず`ignored_types`に記録する
      (安全側フォールバック)。
    - それ以外の種別(join等)は常に無視し、`ignored_types`に種別名のみ記録する。
    """
    result = DispatchResult()
    message_ok = llm_call is not None and reply_client is not None
    follow_ok = reply_client is not None and linking_store is not None
    postback_ok = (
        reply_client is not None
        and user_profile_store is not None
        and workshop_store is not None
        and checkout_session_client is not None
    )

    for event in events:
        event_type = event.get("type")
        if event_type == "message":
            if not message_ok:
                result.ignored_types.append(event_type)
                continue
            result.message_results.append(
                process_message_event(
                    event,
                    llm_call,
                    reply_client,
                    portal_link_provider=portal_link_provider,
                    user_profile_store=user_profile_store,
                    workshop_store=workshop_store,
                    usage_counter_store=usage_counter_store,
                    linking_store=linking_store,
                    now=now,
                )
            )
        elif event_type == "follow":
            if not follow_ok:
                result.ignored_types.append(event_type)
                continue
            result.follow_results.append(
                process_follow_event(event, linking_store, reply_client, rng=rng, now=now)
            )
        elif event_type == "unfollow":
            result.unfollow_results.append(process_unfollow_event(event))
        elif event_type == "postback":
            if not postback_ok:
                result.ignored_types.append(event_type)
                continue
            result.postback_results.append(
                process_postback_event(
                    event, checkout_session_client, reply_client, user_profile_store, workshop_store,
                )
            )
        else:
            result.ignored_types.append(event_type or "unknown")

    return result


@dataclass
class WebhookReceiverResult:
    """receive_webhook()の結果。"""

    status_code: int
    dispatch_result: Optional[DispatchResult] = None
    error: Optional[str] = None


def receive_webhook(
    body: bytes,
    signature_header: Optional[str],
    channel_secret: str,
    *,
    llm_call: Optional[LlmCallClient] = None,
    reply_client: Optional[ReplyClient] = None,
    portal_link_provider: Optional[PortalLinkProvider] = None,
    user_profile_store: Optional[UserProfileStoreProtocol] = None,
    workshop_store: Optional[WorkshopStoreProtocol] = None,
    usage_counter_store: Optional[UsageCounterStoreProtocol] = None,
    linking_store: Optional[LinkingCodeStoreProtocol] = None,
    checkout_session_client: Optional[CheckoutSessionClient] = None,
    rng: Optional[RandomChoiceSource] = None,
    now: Optional[datetime] = None,
) -> WebhookReceiverResult:
    """署名検証済みのHTTPリクエストボディ(bytes)をdispatch_webhook_events()まで橋渡しする
    薄いエントリポイント(aircon-pashaのwebhook-http-entry-point-design.md 2節と同じ設計)。

    1. 署名不正時はJSONパース・dispatchのいずれも行わず401を返す。
    2. JSONとしてパースできないbodyは400(error="invalid_json")。
    3. "events"キーがlistでないbodyは400(error="missing_events")。
    4. 上記を通過したらeventsをdispatch_webhook_events()にそのまま委譲する。
    """
    if not verify_line_signature(body, signature_header, channel_secret):
        return WebhookReceiverResult(status_code=401, error="invalid_signature")

    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return WebhookReceiverResult(status_code=400, error="invalid_json")

    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        return WebhookReceiverResult(status_code=400, error="missing_events")

    dispatch_result = dispatch_webhook_events(
        payload["events"],
        llm_call=llm_call,
        reply_client=reply_client,
        portal_link_provider=portal_link_provider,
        user_profile_store=user_profile_store,
        workshop_store=workshop_store,
        usage_counter_store=usage_counter_store,
        linking_store=linking_store,
        checkout_session_client=checkout_session_client,
        rng=rng,
        now=now,
    )
    return WebhookReceiverResult(status_code=200, dispatch_result=dispatch_result)


def get_runtime_dependencies() -> dict:
    """receive_webhook()に渡す実クライアント一式を組み立てるファクトリ。

    実LINE Messaging API・実LLM API・実Firestore接続は、いずれも実GCPプロジェクト作成・
    実LINE公式アカウント開設(オーナー承認待ち、pending-approval.md参照)後でなければ実
    クライアントを構築できないため、現時点では空の辞書(=全依存関係が未接続のNone扱い)を
    返す(aircon-pasha/course-set-pashaのget_runtime_dependencies()と同じ設計)。
    dispatch_webhook_events()側はllm_call/reply_clientがNoneのときイベント処理をスキップ
    する既存の安全側フォールバックを持つため、未接続のままmain()を呼び出しても例外には
    ならない。承認・実クレデンシャル取得後は、この関数の中身を実クライアントを返すように
    差し替えるだけでmain()・receive_webhook()双方を変更せずに接続できる。
    """
    return {}


def main(request):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定)。

    aircon-pasha/course-set-pashaのmain()と同じ設計。`functions_framework`が渡す
    `request`はFlaskの`Request`と同じインターフェース(`get_data()`・
    `headers.get(...)`)を持つため、本関数はそのインターフェースにのみ依存し
    `functions_framework`自体をインポートしない。`channel_secret`は環境変数
    `LINE_CHANNEL_SECRET`から取得する(実際の値の取得・保管方法自体は実デプロイ時の
    設計課題として別途残る)。
    """
    body = request.get_data()
    signature_header = request.headers.get("X-Line-Signature")
    channel_secret = os.environ.get("LINE_CHANNEL_SECRET", "")

    result = receive_webhook(body, signature_header, channel_secret, **get_runtime_dependencies())
    return ("", result.status_code)


def _demo() -> None:
    print(format_trial_end_notification_message(1))
    print("---")
    print(format_trial_end_notification_message(0))
    print("---quick reply---")
    print(TRIAL_END_QUICK_REPLY)


if __name__ == "__main__":
    _demo()
