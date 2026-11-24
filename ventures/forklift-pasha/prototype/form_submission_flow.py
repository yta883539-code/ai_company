#!/usr/bin/env python3
"""
mvp-flow-draft.md「次回候補」・README フェーズ122「次回候補(2)」を受け、Webフォーム
送信処理本体を実装する(本venture未実装だった、個別モジュールを束ねるオーケストレーション
層)。trial_management.is_generation_paused()・record_generation_and_get_trial_end_notice()・
post_generation_checks.run_all_checks()という既存の個別モジュールを、1回のフォーム送信
処理としてどの順序で呼び出すかをまとめる。

- 実LLM呼び出しは行わない(APIキー取得はオーナー承認待ち、pending-approval.md参照)。
  呼び出し元が注入する`llm_generate`関数(入力メモ文字列→schema/output.schema.json準拠の
  dict)を介して構造化出力を受け取る想定のスタブとして設計した。
- overage_notifications.pyのうち保有台数プラン超過通知(record_vehicle_and_get_overage_
  notice)は、vehicle_store・vehicle_count_storeの両方が渡された場合にvehicle_registry.
  register_vehicle_from_inspection_memo()経由でフェーズ231から既に組み込み済み(本docstring
  がかつて「通知対象となるplan_idの書き込み経路が未確定のため意図的に組み込まない」として
  いたのはフェーズ231時点で解消済みにもかかわらず記載が追随していなかった陳腐化、フェーズ254
  で是正)。月間生成回数90%通知(record_generation_and_get_usage_notice)も、
  usage_counter_storeが渡された場合にフェーズ255で同様に組み込み済み(vehicle_count_store
  と同型の配線。usage-and-fleet-overage-notification-design.md 4節の表示順どおり、台数超過
  通知〈3節〉を先、生成回数90%通知〈2節〉を後に追記する)。トライアル中(operator_store.
  get_plan_id()がNoneを返す間)はプラン上限自体が存在しないため通知はスキップするが、
  vehicle_registry.register_vehicle_from_inspection_memo()のvehicleCountと同じ考え方で
  カウント自体は加算し続ける(アップグレード後に当月分の生成回数がカウント漏れにならない
  ようにする)。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "schema"))

from access_token_store import (  # noqa: E402
    AccessTokenStoreProtocol,
    InMemoryAccessTokenStore,
)
from daily_form_render import (  # noqa: E402
    render_daily_form_html,
    today_jst_date_str,
)
from daily_raw_text_assembly import (  # noqa: E402
    DAILY_CHECKLIST_ITEMS,
    assemble_daily_raw_text,
)
from overage_notifications import (  # noqa: E402
    InMemoryUsageCounterStore,
    InMemoryVehicleCountStore,
    UsageCounterStoreProtocol,
    record_generation_and_get_usage_notice,
)
from post_generation_checks import run_all_checks  # noqa: E402
from trial_management import (  # noqa: E402
    CANCELED_NOTICE,
    FleetOperatorStoreProtocol,
    GENERATION_PAUSED_NOTICE,
    InMemoryFleetOperatorStore,
    get_first_daily_generation_notice_if_due,
    is_generation_paused,
    is_subscription_canceled,
    record_generation_and_get_trial_end_notice,
)
from validate_test_cases import (  # noqa: E402
    SCHEMA,
    validate_against_schema,
    validate_cross_field_rules,
)
from vehicle_registry import (  # noqa: E402
    InMemoryVehicleStore,
    VehicleCountStoreProtocol,
    VehicleStoreProtocol,
    register_vehicle_from_inspection_memo,
)

LlmGenerateFn = Callable[[str], dict]

# daily.html/daily-empty.htmlをGETで動的に返す新規ハンドラ(design.md 4節(3))が読み込む
# テンプレートファイルの場所。両ファイルとも実HTTPデプロイ・ホスティングは未承認のまま
# (pending-approval.md参照)だが、テンプレートレンダリング処理自体は承認待ち事項の範囲外
# として先行して着手できる(design.md 4節(4))。
_WEB_FORM_MOCKUP_DIR = Path(__file__).resolve().parent.parent / "web-form-mockup"
_DAILY_HTML_PATH = _WEB_FORM_MOCKUP_DIR / "daily.html"
_DAILY_EMPTY_HTML_PATH = _WEB_FORM_MOCKUP_DIR / "daily-empty.html"


def validate_llm_output(instance: dict) -> list[str]:
    """schema適合性・クロスフィールドルール・厳守事項6/7の機械チェック
    (post_generation_checks.run_all_checks)の3段階検証をまとめて行う
    (course-set-pasha/aircon-pasha/kura-pashaのcloud_function_webhook.py内
    validate_llm_outputと同じ位置づけ。フェーズ178でprocess_form_submission()
    本体の検証経路をrun_all_checks()単独からこの3段階検証へ統合し、従来
    mock_llm_client.pyにのみ存在した同名関数と本venture本番パイプラインとの
    parityギャップ〈フェーズ177で発見・次回候補化〉を解消した)。"""
    errors = validate_against_schema(instance, SCHEMA)
    if errors:
        # スキーマ自体に適合しない場合、以降のチェックはstatus等の前提が崩れている
        # ため実行しない(course-set-pasha等と同じ考え方)。
        return errors
    errors += validate_cross_field_rules(instance)
    errors += run_all_checks(instance)
    return errors


def process_form_submission(
    raw_text: str,
    operator_id: str,
    now: datetime,
    llm_generate: LlmGenerateFn,
    operator_store: FleetOperatorStoreProtocol,
    vehicle_store: "VehicleStoreProtocol | None" = None,
    vehicle_count_store: "VehicleCountStoreProtocol | None" = None,
    usage_counter_store: "UsageCounterStoreProtocol | None" = None,
) -> dict:
    """1回のWebフォーム送信を処理する。

    呼び出し順序:
    1. is_subscription_canceled()で解約確定済みかを判定する。対象の場合はトライアル
       進捗・upgraded_atの値によらず常に最優先でLLM呼び出し自体を行わずCANCELED_NOTICEを
       返す(is_generation_paused()より先に判定する。kura-pasha/course-set-pasha/
       aircon-pashaで発見された「有料転換済みユーザーが解約後も無期限に生成を使い続け
       られる」欠落への対応、subscription-canceled-immediate-block-design.md相当)。
    2. is_generation_paused()でトライアル終了後・未アップグレードの一時停止対象かを
       判定する。対象の場合はLLM呼び出し自体を行わずGENERATION_PAUSED_NOTICEを返す
       (trial-end-notification-design.md 4節が想定していた「記録整形自体をスキップする
       分岐」)。
    3. llm_generate(raw_text)でschema/output.schema.json準拠の構造化出力(instance)を
       得る(実LLM未接続のためスタブ注入)。
    4. validate_llm_output(instance)でschema適合性・クロスフィールドルール・厳守事項
       6・7の機械チェックをまとめて行う(フェーズ178、従来はrun_all_checks()単独
       だったものを3段階検証に拡張)。エラーがあればstatus="invalid_output"として
       そのまま利用者には返さない。
    5. instanceのstatusに応じて応答テキストを組み立てる。status="generated"の場合のみ、
       get_first_daily_generation_notice_if_due()でinternal_id単位・daily区分初回の
       確認案内(first-daily-generation-confirmation-notice-design.md)を判定・付記し、
       続けてvehicle_store・vehicle_count_storeの両方が渡されていれば(フェーズ231)
       register_vehicle_from_inspection_memo()でvehicle-label-duplicate-handling-
       design.mdの重複チェック・vehicleCount加算・プラン超過通知を行い、新規車両かつ
       超過通知が発生した場合のみ追記する。最後にrecord_generation_and_get_trial_end_
       notice()でトライアル生成回数を加算し、ちょうど終了条件に達した場合は返却テキスト
       末尾に通知文を追記する(design.md「実装位置」の通り、確認案内はトライアル終了通知
       より先に追記する。台数プラン超過通知は確認案内と同種の「利用状況に応じた案内」の
       ため確認案内の直後、トライアル終了通知より先に置く)。
       vehicle_store・vehicle_count_storeのいずれかが未指定(None)の場合は車両登録自体を
       行わない(既存呼び出し元との後方互換、daily/monthly/annualいずれの区分でも同じ
       呼び出し1か所で扱うため区分による分岐はしない)。`record.get("vehicle_id")`
       (LLM出力側のフィールド名、実体は車両番号の自由記述表記)がNoneの場合も同様に
       スキップする(status=insufficient_inputに振り分けられるはずだが、念のための防御)。
       続けてusage_counter_storeが渡されていれば(フェーズ255)、月間生成回数を加算する。
       operator_store.get_plan_id()で解決したplan_idがNoneの場合(トライアル中)はカウント
       のみ加算し通知は行わない(vehicle_registryのvehicleCountと同じ考え方)。plan_idが
       設定済みの場合はrecord_generation_and_get_usage_notice()に委譲し、90%閾値を新たに
       跨いだ場合のみ通知文を付記する。usage-and-fleet-overage-notification-design.md 4節
       の表示順どおり、台数超過通知の直後・トライアル終了通知より先に置く。

    戻り値は次のキーを持つdict:
    - status: "canceled" | "paused" | "generated" | "out_of_scope"
               | "insufficient_input" | "invalid_output"
    - response_text: 利用者に返すテキスト(status="invalid_output"の場合はNone)
    - check_errors: run_all_checks()の結果(空リストなら問題なし)
    """
    if is_subscription_canceled(operator_id, operator_store):
        return {
            "status": "canceled",
            "response_text": CANCELED_NOTICE,
            "check_errors": [],
        }

    if is_generation_paused(operator_id, operator_store):
        return {
            "status": "paused",
            "response_text": GENERATION_PAUSED_NOTICE,
            "check_errors": [],
        }

    instance = llm_generate(raw_text)

    check_errors = validate_llm_output(instance)
    if check_errors:
        return {
            "status": "invalid_output",
            "response_text": None,
            "check_errors": check_errors,
        }

    status = instance.get("status")

    if status == "out_of_scope":
        return {
            "status": status,
            "response_text": instance.get("out_of_scope_message"),
            "check_errors": [],
        }

    if status == "insufficient_input":
        return {
            "status": status,
            "response_text": instance.get("missing_fields_request"),
            "check_errors": [],
        }

    # status == "generated"
    record = instance.get("inspection_record") or {}
    response_text = record.get("body") or ""
    reminder_notice = record.get("reminder_notice")
    if reminder_notice:
        response_text += "\n" + reminder_notice

    first_daily_notice = get_first_daily_generation_notice_if_due(
        operator_store, operator_id, record.get("type")
    )
    if first_daily_notice:
        response_text += "\n" + first_daily_notice

    vehicle_label = record.get("vehicle_id")
    if vehicle_store is not None and vehicle_count_store is not None and vehicle_label:
        registration = register_vehicle_from_inspection_memo(
            vehicle_store,
            vehicle_count_store,
            operator_id,
            vehicle_label,
            operator_store.get_plan_id(operator_id),
        )
        if registration.overage_notice:
            response_text += "\n" + registration.overage_notice

    if usage_counter_store is not None:
        year_month = now.strftime("%Y-%m")
        plan_id_for_usage = operator_store.get_plan_id(operator_id)
        if plan_id_for_usage is None:
            # vehicle_registry.register_vehicle_from_inspection_memo()のplan_id=None分岐
            # と同じ考え方: トライアル中はプラン上限自体が存在しないため通知対象外だが、
            # カウント自体は加算しておく(当月中にアップグレードした場合に、アップグレード
            # 前の生成分がカウント漏れにならないようにする)。
            usage_counter_store.increment_count(operator_id, year_month)
        else:
            usage_notice = record_generation_and_get_usage_notice(
                usage_counter_store, operator_id, year_month, plan_id_for_usage
            )
            if usage_notice:
                response_text += "\n" + usage_notice

    trial_end_notice = record_generation_and_get_trial_end_notice(
        operator_store, operator_id, now
    )
    if trial_end_notice:
        response_text += "\n" + trial_end_notice

    return {
        "status": status,
        "response_text": response_text,
        "check_errors": [],
    }


# ---------------------------------------------------------------------------
# daily区分: web-form-mockup/daily.html(フェーズ257)の構造化フィールド群から
# assemble_daily_raw_text()を呼び出すための変換(フェーズ258、フェーズ256次回候補(2)・
# web-form-ui-design.mdフェーズ257追記「次回候補(1)」に対応)。
# ---------------------------------------------------------------------------

_DAILY_ITEM_FIELD_SLUGS = {
    "ブレーキ": "brake",
    "警告灯": "warning_light",
    "異音": "noise_smell",
    "油圧": "hydraulic",
    "タイヤ": "tire",
    "フォーク": "fork",
}


def _resolve_daily_vehicle_label(form) -> str:
    """daily.html『1.車両選択』(`name="vehicle"`のラジオボタン。新規車両選択時の
    `value="__new__"`のみ`name="vehicle_new_label"`のテキスト欄)から、車両ラベル
    文字列を1つに解決する。"""
    vehicle = form.get("vehicle") or ""
    if vehicle == "__new__":
        return (form.get("vehicle_new_label") or "").strip()
    return vehicle


def _resolve_daily_checked_items(form) -> "list[str]":
    """daily.html『2.点検項目』のチェックボックス(`name="checked_items"`、同名
    複数値)の送信値を取得する。`functions_framework`(Flask Request)の
    `request.form.getlist("checked_items")`相当を優先し、`getlist`を持たない
    フォーム(テスト用の単純dict等、値をリストとして直接渡す場合)もフォール
    バックとして許容する(他venture同様、本番Request・テストスタブの両方を
    同じ関数で扱えるようにする)。"""
    if hasattr(form, "getlist"):
        return list(form.getlist("checked_items"))
    raw = form.get("checked_items")
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    return [raw]


def _resolve_daily_item_notes(form) -> "dict[str, str]":
    """daily.html『2.点検項目』の各異常メモ欄(`name="item_note_<slug>"`)を、
    `assemble_daily_raw_text()`が要求する項目名(日本語表記)キーのdictへ変換
    する(値が空文字列・未送信の項目はキー自体を含めない、assemble_daily_raw_text()
    側の`notes.get(item, "")`デフォルトで吸収される)。"""
    notes = {}
    for item in DAILY_CHECKLIST_ITEMS:
        slug = _DAILY_ITEM_FIELD_SLUGS.get(item)
        note = form.get(f"item_note_{slug}") if slug else None
        if note:
            notes[item] = note
    return notes


def build_daily_raw_text_from_form(form, *, date: str, inspector_name: str) -> str:
    """daily.html(`type=daily`送信時)の構造化フィールド群をform(`request.form`
    相当、`.get()`必須・`.getlist()`は任意)から取り出し、`assemble_daily_raw_text()`
    でraw_text相当の文字列へ組み立てる。

    `date`(実施日)・`inspector_name`(点検者名)は、daily.html側がフェーズ259で
    `name="date"`・`name="inspector_name"`の実際のinputを持つようになったため
    `request.form`からも取得できるが、本関数ではform経由で取得せず呼び出し元
    (`receive_form_submission()`、`request.form.get(...)`済み)から別途渡す
    構造を維持している(値が空文字列であっても、assemble_daily_raw_text()の設計
    〈docstring記載〉どおりエラーにはせず組み立てを続行し、insufficient_inputの
    判定自体はLLM側に委ねる)。

    Raises:
        ValueError: `mode`(`name="mode"`のラジオボタン)が未送信・"ok"/"ng"の
        いずれでもない場合(assemble_daily_raw_text()からそのまま伝播。呼び出し元
        〈receive_form_submission()〉がこれをフォーム不備としてHTTP 400に変換する)。
    """
    return assemble_daily_raw_text(
        vehicle_label=_resolve_daily_vehicle_label(form),
        inspector_name=inspector_name,
        date=date,
        mode=form.get("mode") or "",
        checked_items=_resolve_daily_checked_items(form),
        item_notes=_resolve_daily_item_notes(form),
    )


# ---------------------------------------------------------------------------
# Cloud Functions HTTPエントリポイント (deployment-runbook.mdステップ4「次回候補」対応)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FormSubmissionHttpResult:
    status_code: int
    response_text: Optional[str] = None
    error: Optional[str] = None


def receive_form_submission(
    access_token: "str | None",
    raw_text: "str | None",
    now: datetime,
    *,
    access_token_store: AccessTokenStoreProtocol,
    operator_store: FleetOperatorStoreProtocol,
    llm_generate: "LlmGenerateFn | None",
    vehicle_store: "VehicleStoreProtocol | None" = None,
    vehicle_count_store: "VehicleCountStoreProtocol | None" = None,
    usage_counter_store: "UsageCounterStoreProtocol | None" = None,
) -> FormSubmissionHttpResult:
    """Webフォーム送信を受け取るHTTPエントリポイントの処理本体(access_url_reissue_
    handler.receive_reissue_request()と同じ位置づけ: `process_form_submission()`の
    例外のない戻り値契約を、HTTPステータスコードベースの契約に変換する唯一の箇所とする)。

    本人特定は、他の2エントリポイント(checkout_session.create_checkout_session()・
    access_url_reissue_handler.receive_reissue_request())と同じ`access_token`機構で
    行う(`process_form_submission()`自体が要求する`operator_id`は、本関数が
    `access_token_store.get_internal_id_by_access_token()`で解決してから渡す)。

    `access_token`欠落は400(値自体が無い=クライアント側の不備)、未知の`access_token`は
    404(本人特定不能)、`raw_text`欠落・空文字列も400とする(insufficient_inputの判定は
    LLM呼び出し後に行う設計のため、本関数では「そもそも送信内容が空」という手前の防御のみ
    担う)。

    `llm_generate`が`None`の場合は、実LLM API未接続(APIキー取得がオーナー承認待ち、
    pending-approval.md参照)を意味するため、`process_form_submission()`を呼ばずに503を
    返す(aircon-pasha/course-set-pasha等のcloud_function_webhook.get_runtime_
    dependencies()が依存未接続時に空dictを返し、ハンドラ側でNoneガードする安全側
    フォールバック方針と同じ考え方)。
    """

    if not access_token:
        return FormSubmissionHttpResult(status_code=400, error="missing_access_token")
    operator_id = access_token_store.get_internal_id_by_access_token(access_token)
    if operator_id is None:
        return FormSubmissionHttpResult(status_code=404, error="unknown_access_token")
    if not raw_text or not raw_text.strip():
        return FormSubmissionHttpResult(status_code=400, error="missing_raw_text")
    if llm_generate is None:
        return FormSubmissionHttpResult(status_code=503, error="llm_not_connected")

    result = process_form_submission(
        raw_text,
        operator_id,
        now,
        llm_generate,
        operator_store,
        vehicle_store=vehicle_store,
        vehicle_count_store=vehicle_count_store,
        usage_counter_store=usage_counter_store,
    )
    if result["status"] == "invalid_output":
        # check_errorsの内容自体は利用者へ返さない(厳守事項6/7等の機械チェック詳細は
        # 内部ログ向けであり、HTTPレスポンスには最小限のエラー種別のみを返す方針)。
        return FormSubmissionHttpResult(status_code=500, error="invalid_output")
    return FormSubmissionHttpResult(status_code=200, response_text=result["response_text"])


def get_form_submission_runtime_dependencies() -> dict:
    """main()が使う依存の既定値を組み立てる(checkout_session.get_checkout_runtime_
    dependencies()と対称の構成)。

    実Firestore接続(access_token_store・operator_store・vehicle_store・
    vehicle_count_store・usage_counter_store)はいずれも実GCPプロジェクト確定後でなければ
    構築できないため、
    現時点ではInMemory実装を返す(呼び出しごとに新規生成されるため、実Cloud Functions
    環境でも呼び出しをまたいで状態が保持されない既知の限界が残る。他venture・他
    エントリポイントと同じ限界)。

    `llm_generate`は実LLM APIキー取得(オーナー承認待ち)まではNoneを返す。
    `receive_form_submission()`側がNoneガードにより503を返すため、未接続のまま
    `main()`を呼び出しても例外にはならない。
    """
    return {
        "access_token_store": InMemoryAccessTokenStore(),
        "operator_store": InMemoryFleetOperatorStore(),
        "vehicle_store": InMemoryVehicleStore(),
        "vehicle_count_store": InMemoryVehicleCountStore(),
        "usage_counter_store": InMemoryUsageCounterStore(),
        "llm_generate": None,
    }


def render_daily_form_for_get(
    access_token: "str | None",
    *,
    access_token_store: AccessTokenStoreProtocol,
    operator_store: FleetOperatorStoreProtocol,
    vehicle_count_store: "VehicleCountStoreProtocol | None" = None,
    now: "datetime | None" = None,
) -> "tuple[str, int]":
    """daily.html/daily-empty.htmlをGETリクエストに対して動的レンダリングして返す
    (inspector-name-date-prefill-design.md フェーズ261、4節(3))。

    戻り値は`main()`と同じ`(本文, status_code)`の2要素タプル契約(正常系は本文に
    レンダリング済みHTML、エラー系はエラー種別文字列)。`access_token`欠落は400、
    未知の`access_token`は404(`receive_form_submission()`と同じエラーコード方針)。

    保有車両台数(`vehicle_count_store.get_vehicle_count()`)が0の場合はdaily-empty.html、
    1台以上ならdaily.htmlを返す(READMEフェーズ230で確定したdaily-empty.htmlの適用範囲)。
    `vehicle_count_store`省略時は常に0台扱い(daily-empty.html)とする。
    """
    if not access_token:
        return "missing_access_token", 400
    operator_id = access_token_store.get_internal_id_by_access_token(access_token)
    if operator_id is None:
        return "unknown_access_token", 404

    vehicle_count = (
        vehicle_count_store.get_vehicle_count(operator_id)
        if vehicle_count_store is not None
        else 0
    )
    template_path = _DAILY_EMPTY_HTML_PATH if vehicle_count == 0 else _DAILY_HTML_PATH
    template_html = template_path.read_text(encoding="utf-8")

    inspector_name = operator_store.get_last_inspector_name(operator_id) or ""
    rendered = render_daily_form_html(
        template_html,
        date=today_jst_date_str(now),
        inspector_name=inspector_name,
    )
    return rendered, 200


def main(request, *, runtime_dependencies: Optional[dict] = None):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定、checkout_
    session.main()・access_url_reissue_handler.main()と同型)。

    GETリクエスト(`request.method == "GET"`、属性自体が無いスタブ・簡易呼び出し元との
    後方互換として既定値は`"POST"`)の場合は、`type=daily`のみ対応し
    `render_daily_form_for_get()`にそのまま委譲してdaily.html/daily-empty.htmlの動的
    レンダリング結果を返す(フェーズ263、design.md 4節(3))。`type`がdaily以外のGETは
    monthly/annual側のGET動的レンダリングが未着手のため`unsupported_get_type`で400を
    返す(次回候補として持ち越し)。

    `access_token`はアクセスURL(`https://<ドメイン>/f/{accessToken}`)経由の
    クエリパラメータ(`request.args.get("access_token")`)から取り出し
    `receive_form_submission()`に委譲する。

    daily/monthly/annualの3区分のルーティング判断(フェーズ256・257で次回候補として
    残っていたもの、web-form-ui-design.mdフェーズ257追記参照)は、同じクエリパラメータ
    区画に`type`(`request.args.get("type")`、値は`"daily"`のみ判定。アクセスURL例:
    `https://<ドメイン>/f/{accessToken}?type=daily`)を追加する方式で解決した
    (フェーズ258)。`type=daily`の場合のみ、daily.html側が送信する構造化フィールド群
    (`vehicle`・`vehicle_new_label`・`mode`・`checked_items`・`item_note_<slug>`等)を
    `request.form`から`build_daily_raw_text_from_form()`で取り出し、サーバー側の
    `daily_raw_text_assembly.assemble_daily_raw_text()`(フェーズ256)で1本の自由記述文
    (raw_text)へ組み立てる(フロントエンドJS不使用の方針〈web-form-ui-design.md〉を
    維持したまま)。`mode`が未送信・`"ok"`/`"ng"`のいずれでもない場合はフォーム不備として
    400を返す(`receive_form_submission()`より手前、`process_form_submission()`自体は
    呼ばない)。`type`が`"daily"`以外(`monthly`/`annual`、および`type`未指定という既存
    呼び出し元・テストとの後方互換)の場合は、従来どおりWebフォーム送信本文
    (`request.form.get("raw_text")`)をそのまま使う(点検者名・実施日の実input化は
    フェーズ259で対応済みだが、daily.html・daily専用の実際の`<form>`action配線自体は
    依然未着手で次回候補
    として残る)。

    正常系(status_code=200)ではレスポンス本文に`response_text`(利用者への返信文面)を
    そのまま返す。エラー系では`(エラー文字列, status_code)`を返す(他2エントリポイントと
    同じ契約)。

    `runtime_dependencies`省略時は`get_form_submission_runtime_dependencies()`の戻り値
    (呼び出しごとに新規の空ストア、`llm_generate`は常にNone)を使う。checkout_session.
    main()と同じ理由で、テスト・簡易ローカルサーバーが事前登録済みのストア・スタブ
    `llm_generate`を注入できるようにしている。

    フェーズ262: inspector-name-date-prefill-design.md(フェーズ261)4節(2)の配線。
    `type=daily`の送信が200で正常に処理された後、送信された`inspector_name`(空文字列を
    除く)を`operator_store.set_last_inspector_name()`で書き込む(daily.html/daily-empty.html
    をGETで動的に返す新規ハンドラ〈design.md 4節(3)、本フェーズ未着手〉が将来この値を
    デフォルト表示に使う想定)。
    """
    access_token = request.args.get("access_token")
    form_type = request.args.get("type")

    deps = (
        runtime_dependencies
        if runtime_dependencies is not None
        else get_form_submission_runtime_dependencies()
    )

    if getattr(request, "method", "POST") == "GET":
        if form_type != "daily":
            return "unsupported_get_type", 400
        return render_daily_form_for_get(
            access_token,
            access_token_store=deps["access_token_store"],
            operator_store=deps["operator_store"],
            vehicle_count_store=deps.get("vehicle_count_store"),
        )

    inspector_name = None
    if form_type == "daily":
        inspector_name = request.form.get("inspector_name") or ""
        try:
            raw_text = build_daily_raw_text_from_form(
                request.form,
                date=request.form.get("date") or "",
                inspector_name=inspector_name,
            )
        except ValueError:
            return "invalid_daily_mode", 400
    else:
        # monthly/annual区分、および`type`未指定(daily.html側の`<form>`に
        # action・type配線が未着手の既存呼び出し元との後方互換)は、従来どおり
        # `raw_text`フィールドをそのまま使う。
        raw_text = request.form.get("raw_text")

    http_result = receive_form_submission(access_token, raw_text, datetime.utcnow(), **deps)
    if http_result.status_code == 200:
        # inspector-name-date-prefill-design.md(フェーズ261)4節(2)。type=dailyの送信を
        # 正常(200)に処理した後、daily.html/daily-empty.html側の点検者名入力欄の次回
        # デフォルト値として、事業者単位(operator_id単位)でset_last_inspector_name()に
        # 書き込む。空文字列(未入力送信)はキャッシュを無意味に空上書きしないため対象外とする
        # (design.md 3節「直前に送信した人の名前」という意味論上、空文字列は「名前」ではない)。
        # operator_idはreceive_form_submission()内部で解決済みだが戻り値契約には含まれて
        # いないため、同じaccess_token_storeで再解決する(InMemory/Firestoreいずれも
        # 単純な読み取りのみで、二重解決による副作用はない)。
        if form_type == "daily" and inspector_name:
            operator_id = deps["access_token_store"].get_internal_id_by_access_token(
                access_token
            )
            if operator_id is not None:
                deps["operator_store"].set_last_inspector_name(
                    operator_id, inspector_name
                )
        return http_result.response_text or "", 200
    return (http_result.error or "error"), http_result.status_code
