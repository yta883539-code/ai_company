#!/usr/bin/env python3
"""
mvp-flow-draft.mdで整理した「作業後メモ→LLM呼び出し→3種類の下書き生成→返信」という
単方向バッチ処理のフローを実行可能なコードに落とし込んだもの。

位置づけ:
- 実際のGCPプロジェクト作成・Cloud Functionsのデプロイ、実LLM API・LINE公式アカウント等
  への接続は「アカウント作成」「支払い」に該当し、引き続きオーナー承認待ち
  (pending-approval.md参照)。本モジュールはそれとは別に、「受信したメモをどう解釈し、
  どのタイミングで何を検証し、どう返信文を組み立てるか」という処理ロジック自体を
  実クラウド接続なしで検証可能にしたもの(course-set-pasha・line-reservation-aiの
  prototype/cloud_function_webhook.pyと同じ位置づけ)。
- LLM呼び出し(llm_call)・返信送信(reply_client)はいずれも差し替え可能なProtocolとし、
  承認後は実クライアントに差し替えるだけで動作させられるように設計している。
- course-set-pashaとの主な差異: 本ventureのhistory_rowsは配列だが(同一訪問先で2台以上を
  同時に分解洗浄するケースが一般的、2026-08-21改訂・schema/output.schema.json参照)、
  スプレッドシート転記用の表現はCSV化ではなく項目名付きの箇条書きテキストのままとした
  (course-set-pashaのhistory_export.pyのようなCSV変換モジュールは導入せず、
  format_history_rows_text()で1件ずつ整形して連結する)。テキスト・画像の束ね方
  (text-image-bundling-design.md相当)も、mvp-flow-draft.mdで写真は「任意添付」の
  扱いにとどまり出力スキーマにhasPhoto相当のフィールドが無いため、本モジュールでは
  対応を見送った(必要になった場合の課題としてREADME.mdの「次にやること」に残す)。

設計の参照元: mvp-flow-draft.md, llm-system-prompt-draft.md, schema/output.schema.json
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Protocol

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "schema"))

from checkout_session import (  # noqa: E402
    START_CHECKOUT_POSTBACK_DATA,
    build_checkout_session_params,
)
from post_generation_checks import LENGTH_LIMIT_ERROR_PREFIX, run_all_checks  # noqa: E402
from user_id_linking import (  # noqa: E402
    LinkingCodeStoreProtocol,
    UserProfileStoreProtocol,
    resolve_linking_code,
)
from validate_test_cases import (  # noqa: E402
    SCHEMA,
    validate_against_schema,
    validate_cross_field_rules,
)


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
    def generate(self, memo_text: str, retry_context: Optional[str] = None) -> dict:
        """schema/output.schema.jsonに準拠した構造化出力(dict)を返す想定。

        retry_contextが渡された場合(1回目の検証エラー後の再生成時)、直前の出力の
        何が不正だったか(検証エラーの概要)を実LLM接続後にプロンプトへ添える想定
        (course-set-pasha/line-reservation-aiのjson-output-retry-fallback.mdの
        「同一入力で1回だけ再生成」方針に準拠)。
        呼び出し自体が失敗した場合はLlmApiErrorを送出する契約とする。
        """
        ...


class ReplyClient(Protocol):
    def reply(self, reply_token: str, message_text: str) -> None:
        """呼び出し自体が失敗した場合はReplyApiErrorを送出する契約とする。"""
        ...


class InMemoryReplyClient:
    """実LINE API/フォーム通知接続の代わりに送信内容を記録するだけの検証用クライアント。"""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def reply(self, reply_token: str, message_text: str) -> None:
        self.sent.append((reply_token, message_text))


class CheckoutSessionClient(Protocol):
    """Stripe Checkout Session作成API呼び出しを表す差し替え可能なProtocol
    (checkout-initiation-flow-design.md 3節手順5、llm_call/reply_clientと同じ位置づけ)。
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
        self.calls: list[dict] = []

    def create(self, params: dict) -> str:
        self.calls.append(params)
        return self._url


# ---------------------------------------------------------------------------
# follow/unfollowイベント処理
# (follow-unfollow-event-handling-design.mdの実装。course-set-pashaのFollowProcessResult/
#  process_follow_event/UnfollowProcessResult/process_unfollow_eventと構成をそろえたが、
#  本ventureは「フォーム送信 → LINE友だち追加」の順序が確定しているため、followイベント
#  自体では連携コードを発行しない〈design 1節〉。そのためlinking_store・rng・nowの引数は
#  不要で、course-set-pasha版より単純な実装になっている。)
# ---------------------------------------------------------------------------

APPLICATION_FORM_URL_PLACEHOLDER = "{お申込みフォーム URL}"


class ApplicationFormLinkProvider(Protocol):
    """申込フォームの共有URL取得を表す差し替え可能なProtocol(course-set-pashaと同じ位置づけ)。
    取得できない場合はNoneを返す契約とする。"""

    def get_form_url(self) -> Optional[str]:
        ...


class InMemoryApplicationFormLinkProvider:
    """実フォームURL確定前の代わりに固定URL(またはNone)を返す検証用スタブ。"""

    def __init__(self, url: Optional[str] = "https://forms.gle/stub-application-form") -> None:
        self._url = url

    def get_form_url(self) -> Optional[str]:
        return self._url


def format_welcome_message(form_link_provider: Optional[ApplicationFormLinkProvider]) -> str:
    """design 1節のウェルカムメッセージ本文を組み立てる。本ventureはfollow時点でコードを
    発行しないため、course-set-pashaのformat_welcome_message()と異なり連携コードの差し込みは
    行わない(固定テンプレート)。form_link_providerが未接続(None)、またはURL取得自体に
    失敗した場合はプレースホルダのまま返す(design 1節と同じ考え方)。"""
    form_url = APPLICATION_FORM_URL_PLACEHOLDER
    if form_link_provider is not None:
        fetched = form_link_provider.get_form_url()
        if fetched:
            form_url = fetched

    return (
        "エアコンパシャッと 友だち追加ありがとうございます!\n\n"
        "このサービスは、エアコンクリーニング作業後の簡単なメモを送るだけで、依頼者向け完了報告・"
        "お手入れ案内・作業記録の下書きをまとめて生成するツールです。\n\n"
        "お申込みフォームで発行された連携コード(6文字)をお持ちの方は、そのままこのトークに"
        "コードを送信してください。\n\n"
        "まだお申込みがお済みでない方は、下記フォームからお申込みください。\n"
        f"{form_url}"
    )


@dataclass
class FollowProcessResult:
    """process_follow_event()の結果(design 1節)。コード発行を伴わないため
    course-set-pasha版のlinking_codeフィールドは持たない。"""

    handled: bool
    reply_sent: bool


def process_follow_event(
    event: dict,
    reply_client: ReplyClient,
    *,
    form_link_provider: Optional[ApplicationFormLinkProvider] = None,
) -> FollowProcessResult:
    """LINEの`follow`イベント1件を処理する(署名検証済みの前提、design 1節)。"""
    if event.get("type") != "follow":
        return FollowProcessResult(handled=False, reply_sent=False)

    user_id = event.get("source", {}).get("userId")
    if not user_id:
        return FollowProcessResult(handled=True, reply_sent=False)

    message_text = format_welcome_message(form_link_provider)
    reply_sent = _reply_with_retry(reply_client, event["replyToken"], message_text)
    return FollowProcessResult(handled=True, reply_sent=reply_sent)


@dataclass
class UnfollowProcessResult:
    """process_unfollow_event()の結果(design 2節「決定のまとめ」)。"""

    handled: bool


def process_unfollow_event(event: dict) -> UnfollowProcessResult:
    """LINEの`unfollow`イベント1件を処理する(署名検証済みの前提、design 2節)。

    design 2節「決定のまとめ」の通り、本ventureはunfollow時に一切のデータ変更を行わない
    (`pending_links`はuser_idと紐付かないため検索不能・24時間の自然失効に委ねる、
    `user_profile`・`usage_counter`は再フォロー時の手間を省くため保持)。LINEへの返信も
    行わない(ブロックされているため送達不可)。course-set-pasha版と異なりlinking_store
    引数を持たない(削除対象となるデータが存在しないため)。
    """
    if event.get("type") != "unfollow":
        return UnfollowProcessResult(handled=False)
    return UnfollowProcessResult(handled=True)


# ---------------------------------------------------------------------------
# 月間生成回数カウント・上限接近通知
# (limit-approaching-notification-design.md 2〜5節の実装。course-set-pashaの
#  UsageCounterProtocol/InMemoryUsageCounter/build_usage_noticeと同じ構成だが、
#  本ventureは3プランとも閾値「残り5回」で固定〈設計2節〉のため、
#  course-set-pashaのPLAN_NOTICE_THRESHOLDSに相当するプラン別マッピングは持たない。)
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


# pricing-plan.md「料金プラン」表準拠
PLAN_MONTHLY_LIMITS = {"スモール": 40, "スタンダード": 90, "繁忙期対応": 150}
PLAN_OVERAGE_UNIT_PRICE_JPY = {"スモール": 60, "スタンダード": 50, "繁忙期対応": 40}
# limit-approaching-notification-design.md 2節: 3プラン共通で「残り5回」固定
# (日次件数の上振れ〈繁忙期含む〉をカバーできる最大値として採用、プラン別の使い分けは見送り)。
NOTICE_THRESHOLD = 5


def current_month_jst() -> str:
    """JST基準の暦月をYYYY-MM形式で返す(limit-approaching-notification-design.md 3節、
    月の区切りはJST基準の暦月とする方針に準拠)。"""
    from datetime import datetime, timedelta, timezone

    return datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m")


def build_usage_notice(plan: str, count_after_increment: int) -> Optional[str]:
    """limit-approaching-notification-design.md 4節の通知文言を、該当条件のときのみ返す
    (残り5回に達した生成完了時、または上限を超えた生成完了時)。それ以外はNoneを返す。
    """
    limit = PLAN_MONTHLY_LIMITS[plan]
    unit_price = PLAN_OVERAGE_UNIT_PRICE_JPY[plan]

    if count_after_increment > limit:
        return f"※今月の無料生成回数の上限を超えたため、本回は追加料金{unit_price}円が発生します"
    if limit - count_after_increment == NOTICE_THRESHOLD:
        return (
            f"※今月の生成回数は残り{NOTICE_THRESHOLD}回です"
            f"(上限到達後は1回あたり{unit_price}円の追加料金がかかります)"
        )
    return None


# ---------------------------------------------------------------------------
# 解約・プラン変更案内(subscription_procedure_notice)の返信組み立て
# (schema/output.schema.jsonのstatus=cancellation_intent/downgrade_intent/
#  cancellation_unclear対応。course-set-pasha/prototype/cloud_function_webhook.pyの
#  PortalLinkProvider/render_subscription_procedure_noticeと同じ構成。)
# ---------------------------------------------------------------------------

# schema/validate_test_cases.py CI1・CI2のbody文言に埋め込まれている、Stripeカスタマー
# ポータルの実URLへ置き換えるべき箇所を示す目印(LLM出力にはこの文字列がそのまま含まれる)。
PORTAL_LINK_PLACEHOLDER = "{Stripeカスタマーポータル URL}"

# ポータルURLを取得できなかった場合(provider未接続・API呼び出し失敗)の安全側フォールバック。
# 壊れたプレースホルダ文字列をそのまま顧客(業者本人)に見せることは避け、問い合わせ導線へ
# 差し替える。
PORTAL_LINK_UNAVAILABLE_FALLBACK = (
    "現在、お手続きページの発行に失敗しました。お手数ですが、しばらく経ってから再度"
    "このメッセージを送信いただくか、サポート窓口まで直接ご連絡ください。"
)


class PortalLinkProvider(Protocol):
    """Stripe Billing Portalのセッション作成(顧客ごとに都度発行される一時URL)を表す
    差し替え可能なProtocol。実装時はuser_id(LINEの業者識別子)からStripe顧客IDを引き、
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
      (厳守事項6a(iv)準拠、ポータルリンク・手続き完了前提の文言を含めない)。
    - includes_portal_link=Trueの場合はPORTAL_LINK_PLACEHOLDERを実URLへ置換する。
      providerが未接続(None)、またはuser_id不明、またはURL取得自体に失敗した場合は、
      プレースホルダをそのまま業者に見せる(壊れたテンプレート文字列の露出)を避けるため、
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


# ---------------------------------------------------------------------------
# 返信本文の組み立て(status別)
# ---------------------------------------------------------------------------

VALIDATION_FAILURE_FALLBACK_MESSAGE = (
    "内容の確認中に問題が発生しました。お手数ですが、もう一度メモを送り直してください。"
)

API_FAILURE_FALLBACK_MESSAGE = (
    "只今混み合っております。少し時間をおいて同じ内容をもう一度送ってください。"
)

# character-limit-fallback-design.md準拠。依頼者へ転送される文面がLINE文字数上限を
# 超えた場合専用のフォールバック通知(業者向け、固定文言・LLM生成物ではない)。
# 汎用のVALIDATION_FAILURE_FALLBACK_MESSAGEとは文面を区別する(原因を業者が把握し、
# 入力メモを短くして再送するという具体的な次のアクションを示すため)。
LENGTH_LIMIT_FALLBACK_MESSAGE = (
    "生成結果が長くなりすぎたため、報告文を作成できませんでした。"
    "恐れ入りますが、入力メモを少し短くして再度お送りください。"
)


def _is_length_limit_error(errors: list[str]) -> bool:
    """検証エラーの中にLINE文字数上限超過(character-limit-fallback-design.md)が
    含まれているかを判定する。"""
    return any(error.startswith(LENGTH_LIMIT_ERROR_PREFIX) for error in errors)


def format_history_row_text(history_row: dict, index: Optional[int] = None) -> str:
    """history_rows内の1台分を表1行分の読みやすいテキストに整形する。
    course-set-pashaのhistory_rows_to_csv_text()相当だが、本ventureはCSV化ではなく
    項目名付きの箇条書きとした(スプレッドシートへの手動転記を想定、
    mvp-flow-draft.md「出力3」参照)。indexが指定された場合(2台以上のとき)は
    先頭に「n台目」の見出しを付ける(2026-08-21改訂、history_rows配列化対応)。"""
    labels = [
        ("施工日", history_row.get("work_date")),
        ("機種系統・号数", history_row.get("model_type_and_capacity")),
        ("汚れ状況", history_row.get("dirt_condition")),
        ("追加施工", history_row.get("additional_treatment")),
        ("次回推奨時期", history_row.get("next_recommended_date")),
    ]
    body = "\n".join(f"{label}: {value if value is not None else '(未記載)'}" for label, value in labels)
    if index is None:
        return body
    return f"[{index}台目]\n{body}"


def format_history_rows_text(history_rows: list) -> str:
    """history_rows(配列)を、台数分のテキストに整形して連結する。1件のみの場合は
    従来通り台数見出し無しの表記のまま(返信文言・既存テストとの後方互換)、2件以上の
    場合は「[1台目]」「[2台目]」の見出しで区切る(2026-08-21改訂、market-research.md
    調査で同一訪問先の複数台同時分解洗浄が業界で一般的と判明したことに対応)。"""
    if len(history_rows) == 1:
        return format_history_row_text(history_rows[0])
    return "\n\n".join(
        format_history_row_text(row, index=i + 1) for i, row in enumerate(history_rows)
    )


def format_generated_reply(instance: dict) -> str:
    """status=generatedの構造化出力を、出力1・出力2・出力3をまとめた1通の返信文に組み立てる。"""
    parts = [
        "【作業完了報告メッセージの下書き】",
        instance["completion_report"]["body"],
        "",
        "【お手入れ案内の下書き】",
        instance["care_guide"]["body"],
        "",
        "【作業履歴記録(スプレッドシート転記用)】",
        format_history_rows_text(instance["history_rows"]),
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
        # 崩れているため実行しない(course-set-pasha/line-reservation-aiと同じ考え方)。
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
    handled: bool  # False=テキスト以外の単体イベント等、本フローの処理対象外だったため何もしなかった
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
    retry_context: Optional[str] = None,
) -> dict:
    """LLM API呼び出し自体の失敗(LlmApiError)に対し、即時1回のみリトライする
    (api-call-failure-handling.md方針1)。Cloud Tasks等の非同期再試行基盤を持たない
    同期処理のため、待機を挟まず即時1回に限定する。2回とも失敗した場合はLlmApiErrorを
    そのまま呼び出し元へ伝播させる。"""
    try:
        return llm_call.generate(memo_text, retry_context=retry_context)
    except LlmApiError:
        return llm_call.generate(memo_text, retry_context=retry_context)


def _reply_with_retry(reply_client: ReplyClient, reply_token: str, message_text: str) -> bool:
    """Reply API呼び出し自体の失敗(ReplyApiError)に対し、即時1回のみリトライする
    (api-call-failure-handling.md方針2)。reply_tokenは1回限り有効なため、2回とも
    失敗した場合はPush API等の代替送達手段を持たず(tech-stack.mdの方針)、これ以上は
    何もできない。呼び出し元がreply_sent=Falseとして結果を扱えるようboolを返す
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


def process_memo_event(
    event: dict,
    llm_call: LlmCallClient,
    reply_client: ReplyClient,
    *,
    usage_counter: Optional[UsageCounterProtocol] = None,
    plan: Optional[str] = None,
    month: Optional[str] = None,
    portal_link_provider: Optional[PortalLinkProvider] = None,
) -> MemoProcessResult:
    """テキストメモ1件を処理する(署名検証等の受信基盤側の処理は別モジュールの前提)。

    設計上の判断(mvp-flow-draft.md準拠):
    1. message.type != "text" のイベント(画像単体送信等)は本フローの対象外とし、
       返信を送らずhandled=Falseで返す。
    2. LLM呼び出し結果を検証し、エラーがあれば同一入力で1回だけ再生成をリクエストする
       (course-set-pasha/line-reservation-aiのjson-output-retry-fallback.mdの
       「同一入力で1回だけ」方針を踏襲。再生成後もエラーが残る場合は安全側に倒し、
       定型の再送依頼文言を返す)。
    3. usage_counter・planが渡された場合のみ、月間生成回数カウント・上限接近通知
       (limit-approaching-notification-design.md)を行う。カウント対象はstatus=="generated"の
       場合のみとし、返信本文組み立て直後にインクリメントする。
       usage_counterがNoneの場合(未接続時)はカウント処理自体をスキップする。
    4. status=cancellation_intent/downgrade_intent/cancellation_unclearの場合、
       portal_link_providerが渡されていればsubscription_procedure_notice.body中の
       ポータルURLプレースホルダを実URLへ置換する(subscription-cancellation-flow-design.md、
       render_subscription_procedure_notice参照)。未接続時は安全側フォールバック文言を返す。
       これら3つのstatusは厳守事項6a準拠でusage_counterの対象外(status=="generated"の
       ときのみカウントする既存方針は変更しない)。
    """
    message = event.get("message", {})
    if message.get("type") != "text":
        return MemoProcessResult(handled=False, reply_sent=False, reply_text=None)

    reply_token = event["replyToken"]
    memo_text = message["text"]

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
        fallback_message = (
            LENGTH_LIMIT_FALLBACK_MESSAGE if _is_length_limit_error(errors)
            else VALIDATION_FAILURE_FALLBACK_MESSAGE
        )
        reply_sent = _reply_with_retry(reply_client, reply_token, fallback_message)
        return MemoProcessResult(
            handled=True, reply_sent=reply_sent,
            reply_text=fallback_message if reply_sent else None,
            validation_errors=errors, retried=retried,
        )

    reply_text = format_reply_text(
        instance,
        portal_link_provider=portal_link_provider,
        user_id=event.get("source", {}).get("userId"),
    )
    if instance["status"] == "generated" and usage_counter is not None and plan is not None:
        user_id = event.get("source", {}).get("userId")
        if user_id:
            count = usage_counter.increment(user_id, month or current_month_jst())
            notice = build_usage_notice(plan, count)
            if notice:
                reply_text = f"{reply_text}\n\n{notice}"

    reply_sent = _reply_with_retry(reply_client, reply_token, reply_text)
    return MemoProcessResult(
        handled=True, reply_sent=reply_sent, reply_text=reply_text if reply_sent else None, retried=retried,
    )


# ---------------------------------------------------------------------------
# messageイベントの入口(連携コード判定 vs 施工メモ)
# (user-account-linking-design.md 3節の実装。フェーズ111・112で実装したfollow/unfollowに
#  続き、フェーズ107設計で「未実装のまま残る」としていたもう一方の残課題。)
# ---------------------------------------------------------------------------

LINKING_SUCCESS_MESSAGE = "連携が完了しました。テスト送信をお試しください。"

# design 3節「解決失敗時の案内文言は次回以降の課題」の通り確定文言ではない。ここでは
# 「連携コード自体が見つからない(未連携・期限切れ・入力ミス等)」と「未連携のまま施工メモを
# 送った」を区別せず同一の案内に倒す(design 3節の通り、正規表現の形式一致のみでは連携コードと
# 判定しないため、この2つのケースをこの時点で区別する手段が無い)。
LINKING_REQUIRED_MESSAGE = (
    "先に連携コードの送信が必要です。お申込みフォーム送信完了画面またはメール記載の"
    "6文字の連携コードを、このトークにそのまま送信してください。"
)


@dataclass
class MessageEventResult:
    """process_message_event()の結果。"""

    handled: bool
    reply_sent: bool
    reply_text: Optional[str]
    linked_now: bool = False  # True=本イベントで新規に連携が完了した


def process_message_event(
    event: dict,
    llm_call: LlmCallClient,
    reply_client: ReplyClient,
    profile_store: UserProfileStoreProtocol,
    linking_store: LinkingCodeStoreProtocol,
    now: datetime,
    **memo_kwargs,
) -> MessageEventResult:
    """LINEの`message`イベント(テキスト)を受け取った際の入口。design 3節の通り、
    まず送信元user_idが`user_profile`に連携済みかどうかで処理を分岐する。

    - 連携済み(profile_store.exists(user_id)): 通常の施工メモ生成フロー
      (process_memo_event、mvp-flow-draft.md)へそのまま委譲する。
    - 未連携: 受信テキストが`pending_links`の連携コードと完全一致するかのみを判定根拠とする
      (resolve_linking_code、design 3節「辞書引き一致を必須とし、正規表現の形式一致のみでは
      連携コードと判定しない」)。一致すればuser_profileを新規作成して連携完了を案内し、
      一致しなければ(誤入力・期限切れ・施工メモの先送り送信のいずれであっても)連携コード
      送信を促す案内を返す。この間、mvp-flow-draft.mdの生成フロー(process_memo_event)へは
      一切進めない(design 3節「連携未完了のまま施工メモを送信された場合」の方針通り、
      未連携user_idの利用回数カウントは発生させない)。
    - user_idが取得できないイベント(通常発生しない想定)は安全側に倒し連携コード送信を
      促す案内を返す。
    """
    message = event.get("message", {})
    if message.get("type") != "text":
        return MessageEventResult(handled=False, reply_sent=False, reply_text=None)

    reply_token = event["replyToken"]
    user_id = event.get("source", {}).get("userId")

    if user_id and profile_store.exists(user_id):
        memo_result = process_memo_event(event, llm_call, reply_client, **memo_kwargs)
        return MessageEventResult(
            handled=memo_result.handled,
            reply_sent=memo_result.reply_sent,
            reply_text=memo_result.reply_text,
        )

    if not user_id:
        reply_sent = _reply_with_retry(reply_client, reply_token, LINKING_REQUIRED_MESSAGE)
        return MessageEventResult(
            handled=True, reply_sent=reply_sent,
            reply_text=LINKING_REQUIRED_MESSAGE if reply_sent else None,
        )

    resolution = resolve_linking_code(message["text"], user_id, linking_store, profile_store, now)
    if resolution.ok:
        reply_sent = _reply_with_retry(reply_client, reply_token, LINKING_SUCCESS_MESSAGE)
        return MessageEventResult(
            handled=True, reply_sent=reply_sent,
            reply_text=LINKING_SUCCESS_MESSAGE if reply_sent else None, linked_now=True,
        )

    reply_sent = _reply_with_retry(reply_client, reply_token, LINKING_REQUIRED_MESSAGE)
    return MessageEventResult(
        handled=True, reply_sent=reply_sent,
        reply_text=LINKING_REQUIRED_MESSAGE if reply_sent else None,
    )


# ---------------------------------------------------------------------------
# postbackイベント処理(決済導線)
# (checkout-initiation-flow-design.md フェーズ131「残課題」1点目の実装。トライアル終了
#  通知のFlex Messageボタン(postbackアクション、data="action=start_checkout")がタップ
#  された際の入口。design 2節手順1〜3(postback data判定→user_id取得→user_profile確認)に
#  4節のbuild_checkout_session_params()呼び出しと、実Stripe接続後に差し替える
#  CheckoutSessionClient.create()呼び出しを組み合わせる。)
# ---------------------------------------------------------------------------

def format_checkout_reply_message(checkout_url: str) -> str:
    """design 3節手順5「呼び出し後に得られるURLをLINEへのreplyメッセージとして返す処理」の
    文面。プレーンテキストでURLを案内する(Flex Message化は本フェーズの対応範囲外)。"""
    return (
        "お支払い手続きへのリンクをご案内します。下記URLからお進みください。\n"
        f"{checkout_url}"
    )


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
    profile_store: UserProfileStoreProtocol,
) -> PostbackEventResult:
    """LINEの`postback`イベント1件を処理する(署名検証済みの前提、design 2〜3節)。

    `data`が`action=start_checkout`以外のpostback(本venture未着手の将来アクション、
    design 2節「将来別アクションを追加する場合」)は`handled=False`として素通りする。
    user_idが取得できない、またはuser_profileが未連携(design 3節手順3の異常系)の場合は
    user_id_linking.pyの既存の未連携案内文言(LINKING_REQUIRED_MESSAGE)を返す。
    """
    if event.get("postback", {}).get("data") != START_CHECKOUT_POSTBACK_DATA:
        return PostbackEventResult(handled=False, reply_sent=False)

    reply_token = event["replyToken"]
    user_id = event.get("source", {}).get("userId")
    profile = profile_store.get(user_id) if user_id else None

    if profile is None:
        reply_sent = _reply_with_retry(reply_client, reply_token, LINKING_REQUIRED_MESSAGE)
        return PostbackEventResult(handled=True, reply_sent=reply_sent)

    params = build_checkout_session_params(user_id, profile.stripe_customer_id)
    checkout_url = checkout_session_client.create(params)
    reply_sent = _reply_with_retry(
        reply_client, reply_token, format_checkout_reply_message(checkout_url)
    )
    return PostbackEventResult(handled=True, reply_sent=reply_sent, checkout_url=checkout_url)


# ---------------------------------------------------------------------------
# Webhook本体のイベント種別ディスパッチ
# (フェーズ111・112(follow/unfollow)・フェーズ113(message)で実装した3つのイベント処理
#  関数を、実際のWebhookリクエストの`events`配列から呼び分ける入口。フェーズ107設計時点の
#  「残課題」3点のうち最後まで残っていたもの。course-set-pasha/webhook-event-dispatch-design.md
#  の`dispatch_webhook_events()`と同じ位置づけだが、本ventureはtext-image束ね
#  (merge_text_and_photo_events()相当)を持たないため対応する処理は行わない。)
# ---------------------------------------------------------------------------

@dataclass
class DispatchResult:
    """dispatch_webhook_events()の結果。"""

    follow_results: list = field(default_factory=list)
    message_results: list = field(default_factory=list)
    unfollow_results: list = field(default_factory=list)
    postback_results: list = field(default_factory=list)
    ignored_types: list = field(default_factory=list)


def dispatch_webhook_events(
    events: list[dict],
    *,
    reply_client: Optional[ReplyClient] = None,
    llm_call: Optional[LlmCallClient] = None,
    profile_store: Optional[UserProfileStoreProtocol] = None,
    linking_store: Optional[LinkingCodeStoreProtocol] = None,
    form_link_provider: Optional[ApplicationFormLinkProvider] = None,
    portal_link_provider: Optional[PortalLinkProvider] = None,
    usage_counter: Optional[UsageCounterProtocol] = None,
    plan: Optional[str] = None,
    month: Optional[str] = None,
    now: Optional[datetime] = None,
    checkout_session_client: Optional[CheckoutSessionClient] = None,
) -> DispatchResult:
    """署名検証済みのWebhookリクエストの`events`配列を、`event["type"]`ごとに
    `process_follow_event()`/`process_message_event()`/`process_unfollow_event()`/
    `process_postback_event()`へ振り分ける。

    - "follow": 1件ずつ`process_follow_event()`へ渡す。`reply_client`が未接続の場合は
      該当イベントを処理せず素通りする。
    - "message": 1件ずつ`process_message_event()`へ渡す(連携コード判定と施工メモ生成の
      両方を内包する入口、design 3節参照)。`reply_client`・`llm_call`・`profile_store`・
      `linking_store`・`now`のいずれかが未接続の場合は素通りする(連携済みか未連携かの
      判定自体に`profile_store`が必須のため、course-set-pashaと異なりmessageイベントの
      処理条件にlinking_store・profile_storeも含める)。
    - "unfollow": 1件ずつ`process_unfollow_event()`へ渡す(design 2節の通りdata store類は
      不要なため、他の種別と異なり未接続でも常に処理する)。
    - "postback": 1件ずつ`process_postback_event()`へ渡す(checkout-initiation-flow-design.md
      2〜3節)。`reply_client`・`profile_store`・`checkout_session_client`のいずれかが
      未接続の場合は素通りする(user_profile確認にprofile_storeが必須、URL取得に
      checkout_session_clientが必須のため)。
    - それ以外の種別(join等)は無視し、`ignored_types`に種別名のみ記録する。
    """
    result = DispatchResult()

    for event in events:
        event_type = event.get("type")
        if event_type not in ("follow", "message", "unfollow", "postback"):
            result.ignored_types.append(event_type or "unknown")

    follow_events = [e for e in events if e.get("type") == "follow"]
    if follow_events and reply_client is not None:
        for event in follow_events:
            result.follow_results.append(
                process_follow_event(event, reply_client, form_link_provider=form_link_provider)
            )

    message_events = [e for e in events if e.get("type") == "message"]
    if (
        message_events
        and reply_client is not None
        and llm_call is not None
        and profile_store is not None
        and linking_store is not None
        and now is not None
    ):
        for event in message_events:
            result.message_results.append(
                process_message_event(
                    event,
                    llm_call,
                    reply_client,
                    profile_store,
                    linking_store,
                    now,
                    usage_counter=usage_counter,
                    plan=plan,
                    month=month,
                    portal_link_provider=portal_link_provider,
                )
            )

    unfollow_events = [e for e in events if e.get("type") == "unfollow"]
    for event in unfollow_events:
        result.unfollow_results.append(process_unfollow_event(event))

    postback_events = [e for e in events if e.get("type") == "postback"]
    if (
        postback_events
        and reply_client is not None
        and profile_store is not None
        and checkout_session_client is not None
    ):
        for event in postback_events:
            result.postback_results.append(
                process_postback_event(event, checkout_session_client, reply_client, profile_store)
            )

    return result


# ---------------------------------------------------------------------------
# 署名検証 + HTTPエントリポイント
# (webhook-http-entry-point-design.md フェーズ115。実HTTPリクエストの署名ヘッダ付き
#  JSONボディを受け取り、署名検証を通してからdispatch_webhook_events()へ渡す入口。)
# ---------------------------------------------------------------------------

def verify_line_signature(body: bytes, signature_header: Optional[str], channel_secret: str) -> bool:
    """X-Line-Signatureの検証(HMAC-SHA256 + Base64)。channel_secretの実際の値は
    LINE公式アカウント開設(オーナー承認待ち)後に得られるため、実際の検証はその後に行う。"""
    import base64
    import hashlib
    import hmac

    if not signature_header:
        return False
    computed = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    computed_b64 = base64.b64encode(computed).decode("utf-8")
    return hmac.compare_digest(computed_b64, signature_header)


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
    reply_client: Optional[ReplyClient] = None,
    llm_call: Optional[LlmCallClient] = None,
    profile_store: Optional[UserProfileStoreProtocol] = None,
    linking_store: Optional[LinkingCodeStoreProtocol] = None,
    form_link_provider: Optional[ApplicationFormLinkProvider] = None,
    portal_link_provider: Optional[PortalLinkProvider] = None,
    usage_counter: Optional[UsageCounterProtocol] = None,
    plan: Optional[str] = None,
    month: Optional[str] = None,
    now: Optional[datetime] = None,
    checkout_session_client: Optional[CheckoutSessionClient] = None,
) -> WebhookReceiverResult:
    """署名検証済みのHTTPリクエストボディ(bytes)を`dispatch_webhook_events()`まで
    橋渡しする薄いエントリポイント(webhook-http-entry-point-design.md 2節)。

    1. 署名不正時はJSONパース・dispatchのいずれも行わず401を返す。
    2. JSONとしてパースできないbodyは400(error="invalid_json")。
    3. "events"キーがlistでないbodyは400(error="missing_events")。
    4. 上記を通過したら`events`をdispatch_webhook_events()にそのまま委譲する。
    """
    import json

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
        reply_client=reply_client,
        llm_call=llm_call,
        profile_store=profile_store,
        linking_store=linking_store,
        form_link_provider=form_link_provider,
        portal_link_provider=portal_link_provider,
        usage_counter=usage_counter,
        plan=plan,
        month=month,
        now=now,
        checkout_session_client=checkout_session_client,
    )
    return WebhookReceiverResult(status_code=200, dispatch_result=dispatch_result)


def get_runtime_dependencies() -> dict:
    """receive_webhook()に渡す実クライアント一式を組み立てるファクトリ。

    実LINE Messaging API・実LLM API・実ユーザープロフィール/連携コードストア接続は、いずれも
    実GCPプロジェクト作成・実LINE公式アカウント開設(オーナー承認待ち、pending-approval.md参照)
    後でなければ実クライアントを構築できないため、現時点では空の辞書(=全依存関係が未接続の
    `None`扱い)を返す(course-set-pashaのget_runtime_dependencies()と同じ設計)。
    dispatch_webhook_events()側は`reply_client`/`llm_call`等が`None`のときイベント処理を
    スキップする既存の安全側フォールバックを持つため、未接続のまま`main()`を呼び出しても
    例外にはならない。承認・実クレデンシャル取得後は、この関数の中身を実クライアントを
    返すように差し替えるだけで`main()`・`receive_webhook()`双方を変更せずに接続できる。
    """
    return {}


def main(request):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定)。

    `functions_framework`が渡す`request`はFlaskの`Request`と同じインターフェース
    (`get_data()`・`headers.get(...)`)を持つため、本関数はそのインターフェースにのみ
    依存し`functions_framework`自体をインポートしない(ローカルでの単体テスト時は同じ
    インターフェースを持つ軽量なスタブで代替できる)。

    webhook-http-entry-point-design.md「残課題」で未着手のまま残っていた、実リクエスト
    オブジェクトからの`body`(`request.get_data()`)・署名ヘッダ
    (`request.headers.get("X-Line-Signature")`)取り出し配線をここで行い、
    `receive_webhook()`に委譲する(course-set-pashaのmain()と同じ設計)。`channel_secret`は
    環境変数`LINE_CHANNEL_SECRET`から取得する(実際の値の取得・保管方法自体は実デプロイ時の
    設計課題として別途残る)。
    """
    body = request.get_data()
    signature_header = request.headers.get("X-Line-Signature")
    channel_secret = os.environ.get("LINE_CHANNEL_SECRET", "")

    result = receive_webhook(body, signature_header, channel_secret, **get_runtime_dependencies())

    if result.status_code == 200:
        return "OK", 200
    return (result.error or "error"), result.status_code


def _demo() -> None:
    class StubLlmClient:
        """schema/validate_test_cases.pyのG1_basicフィクスチャ相当を返す固定スタブ。"""

        def generate(self, memo_text: str, retry_context: Optional[str] = None) -> dict:
            return {
                "status": "generated",
                "out_of_scope_message": None,
                "missing_fields_request": None,
                "completion_report": {
                    "body": "壁掛け型2.2kWのエアコンについて、フィルター・熱交換器・送風ファンまで分解洗浄いたしました。"
                            "カビ・ホコリの汚れは中程度でしたが、洗浄後はきれいな状態になっております。防カビコートも施工いたしました。",
                    "mentions_refrigerant_or_electrical": False,
                },
                "care_guide": {
                    "body": "フィルターは月1回程度を目安に、掃除機やご自身で水洗いいただくと効果的です。"
                            "次回の分解洗浄は来年同時期を目安にご検討ください。自己分解洗浄は内部の破損・感電等のリスクが"
                            "あるため、分解を伴う清掃は専門業者へのご依頼をおすすめします。",
                    "next_recommended_date_is_estimate": False,
                },
                "history_rows": [
                    {
                        "work_date": "2026-08-09",
                        "model_type_and_capacity": "壁掛け型2.2kW",
                        "dirt_condition": "カビ・ホコリ汚れ中程度",
                        "additional_treatment": "防カビコートあり",
                        "next_recommended_date": "来年同時期",
                    },
                ],
                "subscription_procedure_notice": None,
            }

    reply_client = InMemoryReplyClient()
    event = {
        "replyToken": "demo-reply-token",
        "message": {
            "type": "text",
            "text": "壁掛け型2.2kW、フィルター・熱交換器・送風ファンまで分解洗浄、カビ・ホコリ汚れ中程度、"
                    "防カビコート施工あり、次回推奨は来年同時期",
        },
    }
    result = process_memo_event(event, StubLlmClient(), reply_client)
    print(f"handled={result.handled} reply_sent={result.reply_sent}")
    print(result.reply_text)

    image_only_event = {"replyToken": "demo-reply-token-2", "message": {"type": "image"}}
    result2 = process_memo_event(image_only_event, StubLlmClient(), reply_client)
    print(f"\n[image-only event] handled={result2.handled}")

    follow_event = {
        "type": "follow",
        "replyToken": "demo-reply-token-3",
        "source": {"userId": "demo-user-1"},
    }
    follow_result = process_follow_event(follow_event, reply_client)
    print(f"\n[follow event] handled={follow_result.handled} reply_sent={follow_result.reply_sent}")

    unfollow_event = {"type": "unfollow", "source": {"userId": "demo-user-1"}}
    unfollow_result = process_unfollow_event(unfollow_event)
    print(f"[unfollow event] handled={unfollow_result.handled}")


if __name__ == "__main__":
    _demo()
