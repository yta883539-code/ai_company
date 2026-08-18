#!/usr/bin/env python3
"""
webhook-processing-flow-design.mdで設計した、Webhook受信〜LLM呼び出し〜返信の
バックエンド処理フローを実行可能なコードに落とし込んだもの。

位置づけ:
- 実際のGCPプロジェクト作成・Cloud Functionsのデプロイ、実LLM API・LINE Messaging API
  への接続は「アカウント作成」「支払い」に該当し、引き続きオーナー承認待ち
  (pending-approval.md参照)。本モジュールはそれとは別に、「受信したメモをどう解釈し、
  どのタイミングで何を検証し、どう返信文を組み立てるか」という処理ロジック自体を
  実クラウド接続なしで検証可能にしたもの(line-reservation-aiのengine.py・
  cloud_function_webhook.pyと同じ位置づけ)。
- LLM呼び出し(llm_call)・LINE返信送信(reply_client)はいずれも差し替え可能なProtocolとし、
  承認後は実クライアントに差し替えるだけで動作させられるように設計している。

設計の参照元: webhook-processing-flow-design.md
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "schema"))

from history_export import history_rows_to_csv_text  # noqa: E402
from post_generation_checks import run_all_checks  # noqa: E402
from validate_test_cases import (  # noqa: E402
    SCHEMA,
    validate_against_schema,
    validate_cross_field_rules,
)


# ---------------------------------------------------------------------------
# 署名検証(line-reservation-ai/prototype/cloud_function_webhook.pyから移植、変更なし)
# ---------------------------------------------------------------------------

def verify_line_signature(body: bytes, signature_header: Optional[str], channel_secret: str) -> bool:
    """X-Line-Signatureの検証(HMAC-SHA256 + Base64)。channel_secretの取得自体は
    LINE公式アカウント開設(オーナー承認待ち)後に得られる値のため、実際の検証はその後に行う。
    """
    import base64
    import hashlib
    import hmac

    if not signature_header:
        return False
    computed = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    computed_b64 = base64.b64encode(computed).decode("utf-8")
    return hmac.compare_digest(computed_b64, signature_header)


# ---------------------------------------------------------------------------
# LLM呼び出し・返信送信のProtocol(実クライアントとスタブ版の共通インターフェース)
# ---------------------------------------------------------------------------

class LlmApiError(Exception):
    """llm_call.generate()自体が失敗した(タイムアウト・5xx・429・ネットワーク断等)ことを
    表す例外。応答は得られたが中身(JSON)が不正な場合(validate_llm_outputのエラー)とは
    別層のエラーとして区別する(api-call-failure-handling.md方針1)。実クライアント側は
    この例外を送出する契約とする。"""


class ReplyApiError(Exception):
    """reply_client.reply()自体が失敗したことを表す例外(api-call-failure-handling.md方針2)。"""


class LlmCallClient(Protocol):
    def generate(self, memo_text: str, has_photo: bool, retry_context: Optional[str] = None) -> dict:
        """schema/output.schema.jsonに準拠した構造化出力(dict)を返す想定。

        retry_contextが渡された場合(1回目の検証エラー後の再生成時)、直前の出力の
        何が不正だったか(検証エラーの概要)を実LLM接続後にプロンプトへ添える想定
        (json-output-retry-fallback.mdの「同一入力で1回だけ再生成」方針に準拠)。
        呼び出し自体が失敗した場合はLlmApiErrorを送出する契約とする。
        """
        ...


class ReplyClient(Protocol):
    def reply(self, reply_token: str, message_text: str) -> None:
        """呼び出し自体が失敗した場合はReplyApiErrorを送出する契約とする。"""
        ...


class InMemoryReplyClient:
    """実LINE API接続の代わりに送信内容を記録するだけの検証用クライアント。"""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def reply(self, reply_token: str, message_text: str) -> None:
        self.sent.append((reply_token, message_text))


# ---------------------------------------------------------------------------
# 月間生成回数カウント・上限接近通知
# (limit-approaching-notification-design.md 5節、
#  notification-threshold-per-plan-review.md 4節で設計した「プラン→閾値」マッピングの実装)
# ---------------------------------------------------------------------------

class UsageCounterProtocol(Protocol):
    def get_count(self, user_id: str, month: str) -> int:
        ...

    def increment(self, user_id: str, month: str) -> int:
        """インクリメント後のカウント値を返す契約とする。"""
        ...


class InMemoryUsageCounter:
    """実Firestore接続の代わりにdictでカウントを保持する検証用スタブ。"""

    def __init__(self) -> None:
        self._counts: dict[tuple[str, str], int] = {}

    def get_count(self, user_id: str, month: str) -> int:
        return self._counts.get((user_id, month), 0)

    def increment(self, user_id: str, month: str) -> int:
        key = (user_id, month)
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]


# ---------------------------------------------------------------------------
# 初回生成確認案内(onboarding-settings-and-self-check-design.md、
# first-generation-notice-implementation-design.mdで設計した「そのユーザーにとって生涯で
# 最初の生成成功時のみ1回だけ末尾に付記する」確認案内の実装)
# ---------------------------------------------------------------------------

FIRST_GENERATION_NOTICE_BODY = (
    "【ご確認のお願い】これが最初の生成です。ジム名・地域名の表示やハッシュタグが意図通りか、"
    "この機会にご確認ください。設定を直したい場合は申込内容の変更フォームからどうぞ。"
    "問題がなければ今後この案内はありません。"
)
FIRST_GENERATION_NOTICE_AREA_UNCONFIGURED_SUFFIX = (
    "ジム名・地域名が未設定です。ハッシュタグ精度を上げたい場合は設定をご検討ください。"
)


class FirstGenerationNoticeStoreProtocol(Protocol):
    """usage_counterのmonthly count(月次でリセットされる)とは独立したライフサイクルを持つ、
    「生涯で最初の確認案内を送信済みか」を保持するProtocol
    (first-generation-notice-implementation-design.md 1節参照)。"""

    def has_sent(self, user_id: str) -> bool:
        ...

    def mark_sent(self, user_id: str) -> None:
        ...


class InMemoryFirstGenerationNoticeStore:
    """実Firestore接続の代わりにsetで送信済みユーザーを保持する検証用スタブ。"""

    def __init__(self) -> None:
        self._sent: set[str] = set()

    def has_sent(self, user_id: str) -> bool:
        return user_id in self._sent

    def mark_sent(self, user_id: str) -> None:
        self._sent.add(user_id)


def append_first_generation_notice(reply_text: str, gym_area_configured: bool) -> str:
    """確認案内本文を返信の末尾に追記する。ジム名・地域名が未設定の場合は追加の一文も付記する
    (onboarding-settings-and-self-check-design.md「確認案内の文面案」準拠)。"""
    notice = FIRST_GENERATION_NOTICE_BODY
    if not gym_area_configured:
        notice = f"{notice}\n{FIRST_GENERATION_NOTICE_AREA_UNCONFIGURED_SUFFIX}"
    return f"{reply_text}\n\n{notice}"


class GymAreaConfigStoreProtocol(Protocol):
    """`gym_area_configured`(申込フォームでジム名・地域名を入力済みか)の実データ参照経路
    (first-generation-notice-implementation-design.md 5節参照)。申込フォーム提出時に
    書き込まれる`user_profile/{user_id}.gym_area_pairs`(onboarding-settings-and-
    self-check-design.md 1節、カンマ区切りの自由記述文字列)の有無を表す。書き込みは
    申込フォーム提出フロー(本モジュールの対象外)の責務であり、本Protocolは読み取り専用とする。
    """

    def is_configured(self, user_id: str) -> bool:
        ...


class InMemoryGymAreaConfigStore:
    """実Firestore接続の代わりにdictで設定有無を保持する検証用スタブ。
    未登録ユーザー(申込フォーム提出前、または`gym_area_pairs`が空欄のまま提出)は
    `is_configured`が既定でFalseを返す(実データ不在=未設定という素直な対応)。"""

    def __init__(self, configured_user_ids: Optional[set] = None) -> None:
        self._configured_user_ids: set = set(configured_user_ids or ())

    def is_configured(self, user_id: str) -> bool:
        return user_id in self._configured_user_ids

    def set_configured(self, user_id: str, configured: bool = True) -> None:
        if configured:
            self._configured_user_ids.add(user_id)
        else:
            self._configured_user_ids.discard(user_id)


# ---------------------------------------------------------------------------
# 解約・ダウングレード案内(subscription-cancellation-flow-design.md、
# schema/output.schema.jsonのsubscription_procedure_notice、フェーズ54で追加した
# status=cancellation_intent/downgrade_intent/cancellation_unclearの返信組み立て)
# ---------------------------------------------------------------------------

# schema/validate_test_cases.py CI1・CI2のbody文言に埋め込まれている、Stripeカスタマー
# ポータルの実URLへ置き換えるべき箇所を示す目印(LLM出力にはこの文字列がそのまま含まれる)。
PORTAL_LINK_PLACEHOLDER = "{Stripeカスタマーポータル URL}"

# ポータルURLを取得できなかった場合(provider未接続・API呼び出し失敗)の安全側フォールバック。
# 壊れたプレースホルダ文字列をそのまま顧客に見せることは避け、問い合わせ導線へ差し替える。
PORTAL_LINK_UNAVAILABLE_FALLBACK = (
    "現在、お手続きページの発行に失敗しました。お手数ですが、しばらく経ってから再度"
    "このメッセージを送信いただくか、店舗まで直接ご連絡ください。"
)


class PortalLinkProvider(Protocol):
    """Stripe Billing Portalのセッション作成(顧客ごとに都度発行される一時URL)を表す
    差し替え可能なProtocol。実装時はuser_id(LINEの顧客識別子)からStripe顧客IDを引き、
    `stripe.billing_portal.Session.create()`相当のAPI呼び出しでURLを取得する想定だが、
    実Stripe接続はオーナー承認待ちのため本モジュールではProtocol化のみ行う
    (llm_call・reply_clientと同じ位置づけ)。取得できない場合はNoneを返す契約とする。"""

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
    subscription_procedure_notice.bodyを実際の返信文へ組み立てる。

    - includes_portal_link=Falseの場合(cancellation_unclear)はbodyをそのまま返す
      (厳守事項7a(iv)準拠、ポータルリンク・手続き完了前提の文言を含めない)。
    - includes_portal_link=Trueの場合はPORTAL_LINK_PLACEHOLDERを実URLへ置換する。
      providerが未接続(None)、またはuser_id不明、またはURL取得自体に失敗した場合は、
      プレースホルダをそのまま顧客に見せる(壊れたテンプレート文字列の露出)を避けるため、
      PORTAL_LINK_UNAVAILABLE_FALLBACKへ全文差し替える
      (api-call-failure-handling.mdの「呼び出し失敗時は安全側の定型文言」と同じ考え方)。
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


# pricing-plan.md「料金プラン」表準拠
PLAN_MONTHLY_LIMITS = {"ライト": 8, "スタンダード": 15, "セッター複数": 30}
PLAN_OVERAGE_UNIT_PRICE_JPY = {"ライト": 150, "スタンダード": 120, "セッター複数": 100}
# notification-threshold-per-plan-review.md 4節: 実測データが取れるまでは全プラン
# 「残り2回」を維持(案B暫定採用)しつつ、単一定数ではなく「プラン→閾値」マッピングとして
# 外だしし、セッター複数プランのみ引き上げ(案A)が必要になった場合も設定値変更のみで
# 対応できるようにする。
PLAN_NOTICE_THRESHOLDS = {"ライト": 2, "スタンダード": 2, "セッター複数": 2}


def current_month_jst() -> str:
    """JST基準の暦月をYYYY-MM形式で返す(limit-approaching-notification-design.md 2節、
    月の区切りはJST基準の暦月とする方針に準拠)。"""
    from datetime import datetime, timedelta, timezone

    return datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m")


def build_usage_notice(plan: str, count_after_increment: int) -> Optional[str]:
    """limit-approaching-notification-design.md 3〜4節の通知文言を、該当条件のときのみ返す
    (残り2回に達した生成完了時、または上限を超えた生成完了時)。それ以外はNoneを返す。
    """
    limit = PLAN_MONTHLY_LIMITS[plan]
    threshold = PLAN_NOTICE_THRESHOLDS[plan]
    unit_price = PLAN_OVERAGE_UNIT_PRICE_JPY[plan]

    if count_after_increment > limit:
        return f"※今月の無料生成回数の上限を超えたため、本回は追加料金{unit_price}円が発生します"
    if limit - count_after_increment == threshold:
        return (
            f"※今月の生成回数は残り{threshold}回です"
            f"(上限到達後は1回あたり{unit_price}円の追加料金がかかります)"
        )
    return None


# ---------------------------------------------------------------------------
# 返信本文の組み立て(status別)
# ---------------------------------------------------------------------------

VALIDATION_FAILURE_FALLBACK_MESSAGE = (
    "内容の確認中に問題が発生しました。お手数ですが、もう一度メモを送り直してください。"
)

API_FAILURE_FALLBACK_MESSAGE = (
    "只今混み合っております。少し時間をおいて同じ内容をもう一度送ってください。"
)


def format_generated_reply(instance: dict) -> str:
    """status=generatedの構造化出力を、出力1・出力2・出力3をまとめた1通の返信文に組み立てる。"""
    sns_post = instance["sns_post"]
    line_web_notice = instance["line_web_notice"]
    history_rows = instance["history_rows"]

    sns_body = sns_post["body"]
    hashtags_line = " ".join(sns_post["hashtags"])
    csv_text = history_rows_to_csv_text(history_rows)

    parts = [
        "【SNS投稿文の下書き】",
        sns_body if not hashtags_line else f"{sns_body}\n{hashtags_line}",
        "",
        "【LINE/Web告知文の下書き】",
        line_web_notice["body"],
        "",
        "【更新履歴(スプレッドシート転記用)】",
        csv_text.rstrip("\n"),
    ]
    return "\n".join(parts)


def format_reply_text(
    instance: dict,
    *,
    portal_link_provider: Optional[PortalLinkProvider] = None,
    user_id: Optional[str] = None,
) -> str:
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
    raise ValueError(f"unexpected status: {status!r}")


# ---------------------------------------------------------------------------
# 構造化出力の検証(スキーマ適合性・クロスフィールドルール・後処理ヒューリスティック)
# ---------------------------------------------------------------------------

def validate_llm_output(instance: dict) -> list[str]:
    """3段階の検証をまとめて行い、エラーメッセージのリストを返す(空リスト=検証OK)。"""
    errors = validate_against_schema(instance, SCHEMA)
    if errors:
        # スキーマ自体に適合しない場合、cross-fieldや後処理チェックはstatus等の前提が
        # 崩れているため実行しない(line-reservation-aiのjson-output-retry-fallback.mdの
        # 「構文崩れは一律escalation合成」と同じ考え方で、以降の詳細検証をスキップする)。
        return errors

    errors += validate_cross_field_rules(instance)
    if instance.get("status") == "generated":
        errors += run_all_checks(instance)
    return errors


# ---------------------------------------------------------------------------
# 1メモ単位の処理結果
# ---------------------------------------------------------------------------

@dataclass
class MemoProcessResult:
    handled: bool  # False=画像単体イベント等、本フローの処理対象外だったため何もしなかった
    reply_sent: bool
    reply_text: Optional[str]
    validation_errors: list = field(default_factory=list)
    retried: bool = False  # True=1回目の検証エラー後、再生成を1回試みた
    api_failure: bool = False  # True=LLM API呼び出し自体が即時リトライ後も失敗した


def _summarize_errors_for_retry(errors: list[str]) -> str:
    """再生成プロンプトに添える検証エラーの短い概要(実LLM接続後に使用)。"""
    return "; ".join(errors[:3])


def _generate_with_api_retry(
    llm_call: LlmCallClient,
    memo_text: str,
    has_photo: bool,
    retry_context: Optional[str] = None,
) -> dict:
    """LLM API呼び出し自体の失敗(LlmApiError)に対し、即時1回のみリトライする
    (api-call-failure-handling.md方針1)。Cloud Tasks等の非同期再試行基盤を持たない
    同期処理のため、待機を挟まず即時1回に限定する。2回とも失敗した場合はLlmApiErrorを
    そのまま呼び出し元へ伝播させる。"""
    try:
        return llm_call.generate(memo_text, has_photo, retry_context=retry_context)
    except LlmApiError:
        return llm_call.generate(memo_text, has_photo, retry_context=retry_context)


def _reply_with_retry(reply_client: ReplyClient, reply_token: str, message_text: str) -> bool:
    """Reply API呼び出し自体の失敗(ReplyApiError)に対し、即時1回のみリトライする
    (api-call-failure-handling.md方針2)。reply_tokenは1回限り有効なため、2回とも
    失敗した場合はPush API等の代替送達手段を持たず(tech-stack.mdの方針)、これ以上は
    何もできない。呼び出し元がreply_sent=Falseとして結果を扱えるようbool を返す
    (例外は外へ伝播させない)。"""
    try:
        reply_client.reply(reply_token, message_text)
        return True
    except ReplyApiError:
        pass
    try:
        reply_client.reply(reply_token, message_text)
        return True
    except ReplyApiError:
        return False


def merge_text_and_photo_events(events: list[dict]) -> list[dict]:
    """同一Webhookリクエスト内の`events`配列を`source.userId`単位でグルーピングし、
    テキストイベント1件+画像イベント0件以上のグループを`hasPhoto`付きの単一メモ
    イベントへ統合する(text-image-bundling-design.md「ケースA」の実装)。

    テキストイベントが0件または2件以上のグループは誤統合を避けるため統合せず、
    元の順序のままそれぞれ個別のイベントとして結果に含める(呼び出し側で従来通り
    process_memo_event()を1件ずつ適用すればよい)。userIdが取得できないイベント
    (source.userIdが無い等)もグルーピング対象外とし、そのまま個別に扱う。
    """
    groups: dict[str, list[dict]] = {}
    ungrouped: list[dict] = []
    order: list[str] = []

    for event in events:
        user_id = event.get("source", {}).get("userId")
        if not user_id:
            ungrouped.append(event)
            continue
        if user_id not in groups:
            groups[user_id] = []
            order.append(user_id)
        groups[user_id].append(event)

    merged: list[dict] = []
    for user_id in order:
        group = groups[user_id]
        text_events = [e for e in group if e.get("message", {}).get("type") == "text"]
        photo_events = [e for e in group if e.get("message", {}).get("type") == "image"]

        if len(text_events) == 1 and len(text_events) + len(photo_events) == len(group):
            merged_event = dict(text_events[0])
            merged_event["hasPhoto"] = bool(photo_events)
            merged.append(merged_event)
        else:
            merged.extend(group)

    return merged + ungrouped


def process_memo_event(
    event: dict,
    llm_call: LlmCallClient,
    reply_client: ReplyClient,
    *,
    usage_counter: Optional[UsageCounterProtocol] = None,
    plan: Optional[str] = None,
    month: Optional[str] = None,
    portal_link_provider: Optional[PortalLinkProvider] = None,
    first_generation_notice_store: Optional[FirstGenerationNoticeStoreProtocol] = None,
    gym_area_config_store: Optional[GymAreaConfigStoreProtocol] = None,
) -> MemoProcessResult:
    """LINEのmessageイベント1件を処理する(署名検証済みの前提)。

    設計上の判断(webhook-processing-flow-design.md準拠):
    1. message.type != "text" のイベント(画像単体送信等)は本フローの対象外とし、
       返信を送らずhandled=Falseで返す。
    2. has_photoはイベント側の付随情報として受け取る(束ね方自体は残課題、
       webhook-processing-flow-design.md「残課題」参照)。
    3. LLM呼び出し結果を検証し、エラーがあれば同一入力で1回だけ再生成をリクエストする
       (json-output-retry-fallback.mdの「同一入力で1回だけ」方針をline-reservation-aiと
       同じ形で採用。再生成後もエラーが残る場合は安全側に倒し、定型の再送依頼文言を返す)。
    4. usage_counter・planが渡された場合のみ、月間生成回数カウント・上限接近通知
       (limit-approaching-notification-design.md)を行う。カウント対象はstatus=="generated"の
       場合のみとし、返信本文組み立て直後(2節の方針通り)にインクリメントする。
       usage_counterがNoneの場合(未接続時)はカウント処理自体をスキップする。
    5. status=cancellation_intent/downgrade_intent/cancellation_unclearの場合、
       portal_link_providerが渡されていればsubscription_procedure_notice.body中の
       ポータルURLプレースホルダを実URLへ置換する(subscription-cancellation-flow-design.md、
       render_subscription_procedure_notice参照)。未接続時は安全側フォールバック文言を返す。
    6. usage_counter・first_generation_notice_storeが渡された場合のみ、そのユーザーにとって
       最初の生成成功時(status=="generated"かつusage_counterのカウントが増分前0)に限り、
       確認案内を返信の末尾に1回だけ付記する(onboarding-settings-and-self-check-design.md、
       first-generation-notice-implementation-design.md参照)。increment前のカウントで
       判定するため、この判定は5.のカウント増分ブロックより前に行う必要がある。
       ジム名・地域名設定有無(gym_area_configured)はgym_area_config_storeが渡された場合のみ
       store.is_configured(user_id)から取得し、未接続時(None)は従来通り「設定済み」を
       既定値として扱う(未接続時に誤って未設定の注意喚起を出さない安全側の挙動、
       first-generation-notice-implementation-design.md 5節参照)。
    """
    message = event.get("message", {})
    if message.get("type") != "text":
        return MemoProcessResult(handled=False, reply_sent=False, reply_text=None)

    reply_token = event["replyToken"]
    memo_text = message["text"]
    has_photo = bool(event.get("hasPhoto", False))

    try:
        instance = _generate_with_api_retry(llm_call, memo_text, has_photo)
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
                llm_call, memo_text, has_photo, retry_context=_summarize_errors_for_retry(errors)
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
        instance,
        portal_link_provider=portal_link_provider,
        user_id=event.get("source", {}).get("userId"),
    )
    if (
        instance["status"] == "generated"
        and usage_counter is not None
        and first_generation_notice_store is not None
    ):
        user_id = event.get("source", {}).get("userId")
        if user_id:
            is_first_generation = usage_counter.get_count(user_id, month or current_month_jst()) == 0
            if is_first_generation and not first_generation_notice_store.has_sent(user_id):
                gym_area_configured = (
                    True if gym_area_config_store is None
                    else gym_area_config_store.is_configured(user_id)
                )
                reply_text = append_first_generation_notice(reply_text, gym_area_configured)
                first_generation_notice_store.mark_sent(user_id)

    if instance["status"] == "generated" and usage_counter is not None and plan is not None:
        user_id = event.get("source", {}).get("userId")
        if user_id:
            count = usage_counter.increment(user_id, month or current_month_jst())
            notice = build_usage_notice(plan, count)
            if notice:
                reply_text = f"{reply_text}\n\n{notice}"

    reply_sent = _reply_with_retry(reply_client, reply_token, reply_text)
    return MemoProcessResult(
        handled=True, reply_sent=reply_sent, reply_text=reply_text if reply_sent else None, retried=retried
    )


def _demo() -> None:
    class StubLlmClient:
        """schema/validate_test_cases.pyのG1フィクスチャ相当を返す固定スタブ。"""

        def generate(self, memo_text: str, has_photo: bool, retry_context: Optional[str] = None) -> dict:
            return {
                "status": "generated",
                "out_of_scope_message": None,
                "missing_fields_request": None,
                "sns_post": {
                    "body": "【課題入れ替えのお知らせ】エリアAに新着課題8本追加しました。",
                    "hashtags": ["#ボルダリング", "#新着課題"],
                    "mentions_photo": has_photo,
                },
                "line_web_notice": {"body": "エリアA:新着8本(黄テープ帯)を追加しました。"},
                "history_rows": [
                    {
                        "revision_date": "2026-08-09",
                        "area": "エリアA",
                        "tape_color_or_grade_band": "黄テープ",
                        "count": 8,
                        "feature_keywords": ["ダイナミック"],
                    },
                ],
                "unchanged_areas": [],
                "subscription_procedure_notice": None,
            }

    class StubCancellationLlmClient:
        """schema/validate_test_cases.pyのCI1(cancellation_intent)フィクスチャ相当を返す
        固定スタブ。ポータルURLプレースホルダの置換動作を確認するためのデモ用。"""

        def generate(self, memo_text: str, has_photo: bool, retry_context: Optional[str] = None) -> dict:
            return {
                "status": "cancellation_intent",
                "out_of_scope_message": None,
                "missing_fields_request": None,
                "sns_post": None,
                "line_web_notice": None,
                "history_rows": None,
                "unchanged_areas": [],
                "subscription_procedure_notice": {
                    "kind": "cancellation_intent",
                    "body": (
                        "解約をご希望とのことで承知しました。下記リンクから"
                        f"お手続きください。▼ {PORTAL_LINK_PLACEHOLDER}"
                    ),
                    "includes_portal_link": True,
                },
            }

    reply_client = InMemoryReplyClient()
    event = {
        "replyToken": "demo-reply-token",
        "message": {"type": "text", "text": "エリアA 黄テープ 8本新規、2026/8/9改訂"},
        "hasPhoto": False,
    }
    result = process_memo_event(event, StubLlmClient(), reply_client)
    print(f"handled={result.handled} reply_sent={result.reply_sent}")
    print(result.reply_text)

    image_only_event = {"replyToken": "demo-reply-token-2", "message": {"type": "image"}}
    result2 = process_memo_event(image_only_event, StubLlmClient(), reply_client)
    print(f"\n[image-only event] handled={result2.handled}")

    cancellation_event = {
        "replyToken": "demo-reply-token-3",
        "message": {"type": "text", "text": "解約したいです"},
        "source": {"userId": "demo-user-1"},
    }
    result3 = process_memo_event(
        cancellation_event, StubCancellationLlmClient(), reply_client,
        portal_link_provider=InMemoryPortalLinkProvider(),
    )
    print(f"\n[cancellation, provider接続あり] handled={result3.handled}")
    print(result3.reply_text)

    result4 = process_memo_event(
        cancellation_event, StubCancellationLlmClient(), reply_client,
        portal_link_provider=None,
    )
    print(f"\n[cancellation, provider未接続] handled={result4.handled}")
    print(result4.reply_text)


if __name__ == "__main__":
    _demo()
