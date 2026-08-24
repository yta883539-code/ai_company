#!/usr/bin/env python3
"""
「予約とれる君」会話処理パイプラインのプロトタイプ実装(実装フェーズ第一歩)。

位置づけ:
- 実LLM呼び出しは行わない(APIキー取得・従量課金が発生するため、
  実行にはオーナー承認が必要。pending-approval.md参照)。
  LLM呼び出し部分は `llm_call: Callable[[], dict]` として差し替え可能なスタブにしてあり、
  承認後に実API呼び出し関数を注入するだけで動作するように設計している。
- これまで机上(文章記述)で設計してきた下記ロジックを、初めて実行可能なコードに落とし込んだもの。
    - json-output-retry-fallback.md  → RetryFallbackProcessor
    - escalation-consolidation-logic.md → EscalationConsolidator
    - duplicate-topic-notification-log-rule.md /
      notification-log-classification-labels.md → NotificationLogAggregator
- schema/validate_test_cases.py のバリデータをそのまま再利用する。
- 時刻は呼び出し側から渡す(now: datetime)。テスト・デモで時刻を自由に制御するため、
  内部で datetime.now() は呼ばない。

実行方法: python3 prototype/engine.py (デモシナリオを実行して標準出力に結果を表示)
"""

from __future__ import annotations

import csv
import io
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "schema"))
from validate_test_cases import SCHEMA, validate_against_schema, validate_cross_field_rules  # noqa: E402


# ---------------------------------------------------------------------------
# 1. json-output-retry-fallback.md: スキーマ不一致時のリトライ・フォールバック
# ---------------------------------------------------------------------------

# フォールバック方針(json-output-retry-fallback.md準拠):
# パース/スキーマ検証に最終的に失敗した場合は、安全側(オーナー通知に転送)へ倒す。
SAFE_FALLBACK_OUTPUT = {
    "intent": "escalation",
    "name": None,
    "menu": None,
    "datetime_candidate": None,
    "confirmed": False,
    "needs_owner_check": True,
    "escalation_reason": None,
}


@dataclass
class ProcessResult:
    output: dict
    used_fallback: bool
    retry_count: int


def process_llm_output(llm_call: Callable[[], dict], max_retries: int = 1) -> ProcessResult:
    """llm_call() を呼ぶたびにLLM(またはモック)からの構造化出力(dict、パース済み)を1つ受け取る。
    スキーマ不一致・依存関係ルール違反があれば max_retries 回まで再度呼び出し、
    それでも失敗すれば SAFE_FALLBACK_OUTPUT に安全側フォールバックする。
    自然文とJSONの矛盾検知(E8相当)は呼び出し側で confirmed=False / needs_owner_check=True に
    安全側上書きした上で llm_call に渡す想定のため、ここでは純粋なスキーマ・依存関係検証のみ扱う。
    """
    attempt = 0
    while attempt <= max_retries:
        instance = llm_call()
        errors = validate_against_schema(instance, SCHEMA) + validate_cross_field_rules(instance)
        if not errors:
            return ProcessResult(output=instance, used_fallback=False, retry_count=attempt)
        attempt += 1
    return ProcessResult(output=dict(SAFE_FALLBACK_OUTPUT), used_fallback=True, retry_count=attempt)


# ---------------------------------------------------------------------------
# 2. escalation-consolidation-logic.md: 連続エスカレーションの集約通知
# ---------------------------------------------------------------------------

@dataclass
class _Window:
    window_opened_at: datetime
    last_event_at: datetime
    refire_count: int = 0
    queued: list = field(default_factory=list)


class EscalationConsolidator:
    """同一顧客が短時間に複数回エスカレーションを発生させた場合の通知集約ロジック。

    ルール(escalation-consolidation-logic.md準拠):
      - ウィンドウは5分固定。初回発生時は即時個別通知し、ウィンドウを開く。
      - ウィンドウ内(5分以内)の追加分はキューに貯め、ウィンドウが閉じた時点でまとめて1通通知する。
      - ウィンドウが閉じた後の再発火(新しいウィンドウの開始)が3回目になったら、以降は都度通知に切り替える。
      - 直近イベントから30分間新規イベントが無ければ状態をリセットする(refire_countも0に戻る)。
      - 医療相談(厳守事項6-a)も例外なく本ロジックを適用する。
    """

    WINDOW = timedelta(minutes=5)
    RESET_AFTER = timedelta(minutes=30)
    REFIRE_LIMIT = 3

    def __init__(self) -> None:
        self._windows: dict[str, _Window] = {}

    def on_event(self, user_id: str, event: dict, now: datetime) -> list[tuple[str, object]]:
        """イベント発生時に即座に送るべき通知アクションを返す。
        戻り値の各要素は ("immediate", event) または ("immediate_refire", event)。
        ウィンドウ内に貯めた分は flush_due_windows() でまとめ通知として取り出す。
        """
        actions: list[tuple[str, object]] = []
        w = self._windows.get(user_id)

        if w is not None and now - w.last_event_at > self.RESET_AFTER:
            w = None  # 30分途絶えでリセット(refire_countも消える)

        if w is None:
            self._windows[user_id] = _Window(window_opened_at=now, last_event_at=now)
            actions.append(("immediate", event))
            return actions

        w.last_event_at = now
        if now - w.window_opened_at <= self.WINDOW:
            w.queued.append(event)
            return actions

        # ウィンドウが閉じた後の再発火 → 新しいウィンドウを開く
        w.refire_count += 1
        w.window_opened_at = now
        w.queued = []
        if w.refire_count >= self.REFIRE_LIMIT:
            actions.append(("immediate_refire", event))
        else:
            w.queued.append(event)
        return actions

    def flush_due_windows(self, now: datetime) -> list[tuple[str, list]]:
        """ウィンドウ(5分)が経過し、キューに未送信のまとめ通知があるユーザー分を取り出す。"""
        results: list[tuple[str, list]] = []
        for user_id, w in self._windows.items():
            if w.queued and now - w.window_opened_at > self.WINDOW:
                results.append((user_id, w.queued))
                w.queued = []
        return results


# ---------------------------------------------------------------------------
# 3. duplicate-topic-notification-log-rule.md /
#    notification-log-classification-labels.md: 通知ログ集計
# ---------------------------------------------------------------------------

# escalation_reasonのうち、LLM構造化出力のenum(consultation相当/unimplemented_feature)には
# 含まれない、システム内部(BookingSlotManager確定競合・候補選択の再確認上限超過)から発火する
# 理由の一覧。conversation-flow-state-machine-design.md・candidate-presentation-and-selection-design.mdの
# 残課題「通知ログ集計でどう扱うか」への対応として、booking_output.schema.jsonのenum拡張はせず
# (LLMが出力するフィールドではないため)、通知ログ集計側で一般相談(consultation)とは別枠に
# 振り分ける方針を採用した(2026-08-01決定)。
# booking_cancelled/cancel_not_foundはcancel-intent-handling-design.md準拠でcancel_booking()から
# 発火する(2026-08-02追加)。
# booking_change_started/change_not_foundはchange-intent-handling-design.md準拠でchange_booking()から
# 発火する(2026-08-02追加)。
SYSTEM_ESCALATION_REASONS = frozenset({
    "booking_conflict",
    "candidate_selection_unresolved",
    "booking_cancelled",
    "cancel_not_found",
    "booking_change_started",
    "change_not_found",
    # api-call-failure-handling.md: LLM/LINE Push API呼び出し自体が失敗した場合の内部イベント。
    "llm_unavailable",
    "line_push_failed",
    # new-booking-needs-owner-check-notification-design.md: E8(自然文とJSONの矛盾)相当。
    # intentがnew_bookingのままneeds_owner_check: trueだけが立つケースをサーバー側で合成する
    # escalation_reason(LLM自身は出力しない。booking_output.schema.jsonのenumには含めない)。
    "output_contradiction",
})


class NotificationLogAggregator:
    """オーナー向け通知ログ集計画面(スプレッドシート版MVP相当)の集計ロジック。

    ルール:
      - resolved:false の faq_segments を対象に、(日付, userId, topic) でユニーク化してカウントする
        (duplicate-topic-notification-log-rule.md準拠。日をまたげば別カウント、同日内の連投は1件扱い)。
      - escalation_reason='unimplemented_feature' は「未実装機能問い合わせ件数」として内訳を別集計する
        (notification-log-classification-labels.md準拠)。
      - escalation_reason が SYSTEM_ESCALATION_REASONS(システム内部イベント)に該当する場合は、
        一般相談(consultation)とは別枠のsystem_event_countsに理由別で集計する。技術的な予約競合と
        顧客対応が必要な相談をオーナーが混同しないようにするため。
      - 上記以外/未設定(=厳守事項6の一般相談)の件数はconsultation_countに参考値として集計する。
      - 分類はescalation_reasonの値(unimplemented_feature/SYSTEM_ESCALATION_REASONS該当/それ以外)を
        優先して判定し、intentが'escalation'であることまでは要求しない。cancel_booking()/
        change_booking()が発火するbooking_cancelled/booking_change_started等はintentが
        'cancel'/'change'のままシステム内部イベントとして渡ってくるため(system-event-log-gap-fix.md参照)。
        consultation_count(=厳守事項6の一般相談)のみ、明確なintent='escalation'を要求する
        (booking_output.schema.jsonのenumに含まれない未知の理由文字列を誤って一般相談扱いしないため)。
    """

    def __init__(self) -> None:
        self._seen_topics: set[tuple[str, str, str]] = set()
        self.unimplemented_feature_count = 0
        self.consultation_count = 0
        self.system_event_counts: dict[str, int] = {}
        # owner-settings-wireframe.mdの通知ログ集計画面は「未登録FAQ相談: 12件
        # 内訳: 支払い方法5/駐車場4/...」のようにtopicごとの内訳も表示する想定だが、
        # これまでunique_unresolved_topic_count()で合計しか出せなかったため新設(内訳の集計元)。
        self.topic_counts: dict[str, int] = {}
        # 同様に「未実装機能の問い合わせ: 3件 内訳: デポジット決済2/複数店舗一括予約1」の
        # feature_hint別内訳の集計元(自由記述のためカテゴリ正規化はせずテキストをそのままキーにする、
        # notification-log-classification-labels.md「未検討・要検討事項」参照)。
        self.feature_hint_counts: dict[str, int] = {}

    def record(self, user_id: str, output: dict, now: datetime) -> None:
        date_key = now.date().isoformat()
        for seg in (output.get("faq_segments") or []):
            if seg.get("resolved") is False:
                topic_key = (date_key, user_id, seg["topic"])
                if topic_key not in self._seen_topics:
                    self._seen_topics.add(topic_key)
                    self.topic_counts[seg["topic"]] = self.topic_counts.get(seg["topic"], 0) + 1

        if not output.get("needs_owner_check"):
            return
        reason = output.get("escalation_reason")
        if reason == "unimplemented_feature":
            self.unimplemented_feature_count += 1
            hint = output.get("feature_hint")
            if hint:
                self.feature_hint_counts[hint] = self.feature_hint_counts.get(hint, 0) + 1
        elif reason in SYSTEM_ESCALATION_REASONS:
            self.system_event_counts[reason] = self.system_event_counts.get(reason, 0) + 1
        elif output.get("intent") == "escalation":
            self.consultation_count += 1

    def unique_unresolved_topic_count(self) -> int:
        return len(self._seen_topics)

    def system_event_total(self) -> int:
        return sum(self.system_event_counts.values())


# escalation-notification-templates.md: FAQ topic / システム内部イベントの日本語ラベル対応表。
# format_escalation_notification()/format_escalation_digest_message()で使う。
FAQ_TOPIC_LABELS = {
    "access": "アクセス・行き方",
    "parking": "駐車場",
    "payment": "支払い方法",
    "hours": "営業時間・定休日",
    "other": "その他FAQ",
}

_SYSTEM_EVENT_LABELS = {
    "booking_conflict": "予約枠の競合(システム)",
    "candidate_selection_unresolved": "候補選択が確定しなかった(システム)",
    "booking_cancelled": "予約キャンセル(確定分)",
    "cancel_not_found": "キャンセル対象の予約が見つからない",
    "booking_change_started": "予約変更(旧予約解放)",
    "change_not_found": "変更対象の予約が見つからない",
    "llm_unavailable": "AI応答エラー(システム)",
    "line_push_failed": "LINE送信エラー(システム)",
    # SYSTEM_ESCALATION_REASONSには含まれないが、_start_new_booking()の
    # unregistered_menu(メニュー未登録)もオーナー要確認イベントのため、ここで併せてラベル付けする。
    "unregistered_menu": "未登録メニューでのご予約希望",
    "output_contradiction": "AI応答の矛盾検知(要確認)",
}


NOTIFICATION_LOG_CSV_HEADER = ["区分", "内訳", "件数"]


def format_notification_log_csv(logs: NotificationLogAggregator) -> str:
    """owner-settings-wireframe.mdの通知ログ集計画面の「[CSVで書き出す]」ボタンに相当する出力。

    MVPは専用集計バックエンドを持たずスプレッドシート集計に委ねる方針(同ファイル「実装メモ」)
    のため、このCSVはNotificationLogAggregatorの集計結果をスプレッドシートに貼り付けやすい
    テキストへ変換するだけで、独自の集計ロジックは持たない。列は「区分,内訳,件数」の3列固定。
    内訳が無い行(区分の合計行)は内訳列を空文字とする。feature_hintはLLMの自由記述で
    カンマ・改行を含みうるため、course-set-pashaのhistory_export.pyと同様にcsvモジュールで
    正しくエスケープする(素朴な文字列結合は誤ったCSVを生成しうるため避ける)。
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(NOTIFICATION_LOG_CSV_HEADER)

    writer.writerow(["未登録FAQ相談", "", logs.unique_unresolved_topic_count()])
    for topic, count in sorted(logs.topic_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        writer.writerow(["未登録FAQ相談", FAQ_TOPIC_LABELS.get(topic, topic), count])

    writer.writerow(["未実装機能の問い合わせ", "", logs.unimplemented_feature_count])
    for hint, count in sorted(logs.feature_hint_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        writer.writerow(["未実装機能の問い合わせ", hint, count])

    writer.writerow(["その他エスカレーション(6番)", "", logs.consultation_count])

    writer.writerow(["システム内部イベント", "", logs.system_event_total()])
    for reason, count in sorted(logs.system_event_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        label = _SYSTEM_EVENT_LABELS.get(reason, reason)
        writer.writerow(["システム内部イベント", label, count])

    return buf.getvalue()


@dataclass
class BookingListEntry:
    """owner-settings-wireframe.mdの予約一覧ページ1行分
    (firestore-data-model.md conversations/{sessionId}のうち、予約一覧表示に必要な
    フィールドの部分集合。予約枠そのものの排他制御はBookingSlotManagerの守備範囲であり、
    本クラスは確定済み予約の表示専用の値オブジェクト)。

    store_id/slot_keyはCSV出力(BOOKING_LIST_CSV_HEADER)には含まれない表示外の識別子で、
    「来店済み」チェック等オーナーの1タップ操作をmark_booking_visited()等でrecord_storeへ
    書き戻す際にどのレコードを更新するかを特定するために使う(booking-record-store-design.md
    「MVPスコープの範囲外として残す点」で指摘されていた配線ロジックの一部)。record_storeを
    介さず組み立てられたBookingListEntry(既存テスト等)ではNone/空文字のままでよい。
    """

    booking_date: date
    start_minutes: int  # 予約開始時刻(0時からの分)
    customer_name: str
    menu: str
    store_id: str = ""
    slot_key: Optional[tuple] = None


BOOKING_LIST_CSV_HEADER = ["日付", "曜日", "時刻", "お客様名", "メニュー"]


def format_booking_list_csv(bookings: list[BookingListEntry]) -> str:
    """owner-settings-wireframe.mdの予約一覧ページ「[今週分をCSVで書き出す]」ボタンに相当する出力。

    format_notification_log_csv()と同様、専用集計バックエンドは持たずスプレッドシートに
    貼り付けやすいテキストへ変換するのみ。列は「日付,曜日,時刻,お客様名,メニュー」の5列固定。
    「直近7日間」等の絞り込み・日時順の並び替えは呼び出し側の責務とし、本関数は渡された順の
    まま出力する。customer_name/menuは自由記述でカンマ・改行を含みうるため、
    course-set-pashaのhistory_export.py・format_notification_log_csv()と同様にcsvモジュールで
    正しくエスケープする。
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(BOOKING_LIST_CSV_HEADER)
    for booking in bookings:
        hours, minutes = divmod(booking.start_minutes, 60)
        writer.writerow([
            f"{booking.booking_date.month}/{booking.booking_date.day}",
            _WEEKDAY_JA[booking.booking_date.weekday()],
            f"{hours:02d}:{minutes:02d}",
            booking.customer_name,
            booking.menu,
        ])
    return buf.getvalue()


NO_SHOW_CONFIRMED_STATUS = "無断キャンセル確定"

# precheck-strengthening.md 案B(オーナー向け注意書き表示)の閾値。「仮で2件以上」を踏襲。
PRECHECK_STRENGTHENING_BADGE_THRESHOLD = 2


@dataclass(frozen=True)
class CustomerBookingRecord:
    """顧客ごとの過去予約1件分の永続記録(no-show-handling.mdが参照する
    累計予約数・無断キャンセル確定数等の集計元データ。archive_completed_conversations()の
    docstringが述べる通り、本エンジンの会話メモリ(_states)とは別の永続ストレージ
    (スプレッドシート等)側で保持される想定の値をそのまま受け取る値オブジェクト)。
    """

    visit_date: date
    menu: str
    status: str  # "来店済み" / NO_SHOW_CONFIRMED_STATUS / その他(キャンセル済み等)
    reminder_replied: bool  # customer-reply-detection-design.mdのcustomerRepliedAtに相当


@dataclass(frozen=True)
class CustomerDetailView:
    """owner-settings-wireframe.md「顧客詳細ページ」の表示に必要な値をまとめた表示専用オブジェクト。"""

    customer_name: str
    total_bookings: int
    no_show_confirmed_count: int
    latest_no_show_date: Optional[date]
    latest_reminder_replied: Optional[bool]  # 履歴が1件も無ければNone
    recent_history: list[CustomerBookingRecord]  # 来店日降順で最大5件
    precheck_strengthening_flag: bool  # precheck-strengthening.md案Bのバッジ表示要否


def build_customer_detail_view(customer_name: str, records: list[CustomerBookingRecord]) -> CustomerDetailView:
    """owner-settings-wireframe.md「顧客詳細ページ」ワイヤーフレームの各表示項目を、
    顧客の過去予約記録一覧から組み立てる。

    - 「累計予約数」「予約履歴(直近5件)」は記録の全件・来店日降順上位5件をそのまま使う。
    - 「無断キャンセル確定数」「直近の無断キャンセル日」はstatus == NO_SHOW_CONFIRMED_STATUSの
      記録のみを対象にする(no-show-handling.mdの通り、確定はオーナーの1タップ操作を経た記録の
      みが対象で、「未対応」段階の候補はここに含まれない前提)。
    - 「前回リマインドへの返信」は最新の予約記録(来店日が最も新しいもの)のreminder_repliedを
      そのまま使う(customer-reply-detection-design.mdの「毎回最新の時刻で上書き」方針と同じく、
      直近1件の値のみを表示対象とする)。
    - precheck_strengthening_flagはprecheck-strengthening.md案Bの「無断キャンセル確定数が
      閾値(仮2件)以上ならオーナー向け注意書きを表示」の判定結果。表示位置自体は
      owner-settings-wireframe.mdの追記時点では確保のみだったため、閾値判定ロジックの実装が
      本関数の役割。
    """
    sorted_records = sorted(records, key=lambda r: r.visit_date, reverse=True)
    no_show_records = [r for r in sorted_records if r.status == NO_SHOW_CONFIRMED_STATUS]
    latest = sorted_records[0] if sorted_records else None
    return CustomerDetailView(
        customer_name=customer_name,
        total_bookings=len(sorted_records),
        no_show_confirmed_count=len(no_show_records),
        latest_no_show_date=no_show_records[0].visit_date if no_show_records else None,
        latest_reminder_replied=latest.reminder_replied if latest is not None else None,
        recent_history=sorted_records[:5],
        precheck_strengthening_flag=len(no_show_records) >= PRECHECK_STRENGTHENING_BADGE_THRESHOLD,
    )


BOOKING_UPCOMING_STATUS = "来店予定"
CANCELLED_STATUS = "キャンセル済み"
CHANGED_STATUS = "変更済み"
VISITED_STATUS = "来店済み"


@dataclass
class _StoredBookingRecord:
    """InMemoryBookingRecordStoreが保持する確定予約1件分。予約一覧ページ(BookingListEntry)・
    顧客詳細ページ(CustomerBookingRecord)、両方の表示専用オブジェクトへの変換を持つ、
    永続ストレージ側の生レコードに相当する値オブジェクト。"""

    store_id: str
    slot_key: tuple
    booking_date: date
    start_minutes: int
    customer_name: str
    menu: str
    # cancel_booking()/change_booking()でrecord_cancelled()が呼ばれるとCANCELLED_STATUS/
    # CHANGED_STATUSが、オーナーの手動操作(record_visited()/record_no_show_confirmed())で
    # VISITED_STATUS/NO_SHOW_CONFIRMED_STATUSが入る。Noneのままなら来店予定
    # (BOOKING_UPCOMING_STATUS)のまま。
    status_override: Optional[str] = None
    # customer-reply-detection-design.mdのcustomerRepliedAtに相当。確定直後はFalseで、
    # record_reminder_replied()(ConversationFlowStateMachine.record_reminder_reply()経由)で
    # confirmed状態の会話にメッセージが届いた事実が記録されるとTrueへ更新される。
    reminder_replied: bool = False

    def to_list_entry(self) -> BookingListEntry:
        return BookingListEntry(
            booking_date=self.booking_date,
            start_minutes=self.start_minutes,
            customer_name=self.customer_name,
            menu=self.menu,
            store_id=self.store_id,
            slot_key=self.slot_key,
        )

    def to_customer_record(self) -> CustomerBookingRecord:
        return CustomerBookingRecord(
            visit_date=self.booking_date,
            menu=self.menu,
            status=self.status_override or BOOKING_UPCOMING_STATUS,
            reminder_replied=self.reminder_replied,
        )


class InMemoryBookingRecordStore:
    """firestore-data-model.mdが想定する外部永続ストレージ(Firestore等)の最小限の
    インメモリ代替実装。

    位置づけ:
    - format_booking_list_csv()・build_customer_detail_view()はいずれも「既にどこからか
      取得済みのデータ」を受け取って表示用に変換するだけの関数で、その「取得元」自体は
      README.md「次にやること」に「ホスティング基盤(Cloud Functions)接続後の課題」として
      未着手のまま残っていた。
    - 本クラスは、llm_callスタブ(実LLM呼び出しを差し替え可能にした設計)と同じ考え方で、
      「取得元」の最小インターフェース(record_confirmed / list_booking_entries /
      customer_records)をまずインメモリで実装したもの。実際のFirestore等への差し替えは、
      同じインターフェースを持つ別クラスに置き換えるだけで済むようにする狙いがあり、
      GCPプロジェクト作成・実Firestore接続そのものは行わない(オーナー承認待ち、
      pending-approval.md参照)。
    - ConversationFlowStateMachineへ渡すと、provide_details()での確定成功時に自動的に
      record_confirmed()が呼ばれる(record_storeを渡さない場合はNoneのままで、
      従来通り何もしない後方互換の任意引数)。
    - 同様にcancel_booking()/change_booking()がconfirmed状態の予約を解放した際は、
      record_cancelled()が自動的に呼ばれ、該当レコードのstatusをCANCELLED_STATUS
      (キャンセル済み)/CHANGED_STATUS(変更済み)に更新する(削除はしない。顧客詳細ページの
      来店履歴として引き続き参照できるようにするため)。list_booking_entries()(予約一覧CSV)
      からはstatus更新済みのレコードを除外し、customer_records()(顧客詳細ページ)には
      引き続き含める。
    - no-show-handling.mdが定める、オーナーの1タップ操作(予約一覧からの手動チェック)は
      record_visited()/record_no_show_confirmed()で反映する。自動断定は行わず、いずれも
      オーナー操作を起点とした呼び出しのみを想定する(ConversationFlowStateMachineからの
      自動呼び出しは無い。顧客側の会話フローではなくオーナー側設定画面の操作のため)。
    - リマインド返信検知(customer-reply-detection-design.md)は`record_reminder_replied()`で
      反映する。ConversationFlowStateMachine.record_reminder_reply()経由で、confirmed状態の
      会話にメッセージが届いた事実(内容は問わない)があった場合にTrueへ更新される
      (customer-reply-detection-design.mdの`ConfirmedReplyRecorder`と異なりFirestore接続を
      要さないため、GCPプロジェクト作成前でも動作する)。

    MVPスコープの範囲外として残す点(実ホスティング基盤への接続時に、この最小インターフェースを
    実装したFirestore版クラスへ差し替える際に併せて設計する):
    - 複数プロセス・複数インスタンス間での永続化(engine.pyの他の状態と同様、単一プロセスの
      メモリ内でのみ有効)。
    """

    def __init__(self) -> None:
        self._records: list[_StoredBookingRecord] = []

    def record_confirmed(self, store_id: str, slot_key: tuple, customer_name: str, menu: str) -> None:
        _, date_str, time_str = slot_key
        hours, minutes = (int(part) for part in time_str.split(":"))
        self._records.append(
            _StoredBookingRecord(
                store_id=store_id,
                slot_key=slot_key,
                booking_date=date.fromisoformat(date_str),
                start_minutes=hours * 60 + minutes,
                customer_name=customer_name,
                menu=menu,
            )
        )

    def list_booking_entries(self, store_id: str, start_date: date, end_date: date) -> list[BookingListEntry]:
        """owner-settings-wireframe.md予約一覧ページの「[今週分をCSVで書き出す]」ボタンが
        取得すべきデータそのもの。戻り値はformat_booking_list_csv()にそのまま渡せる。
        record_cancelled()でキャンセル・変更済みになったレコードは、来店予定の一覧としては
        不適切なため除外する(顧客詳細ページの履歴には引き続き残す。customer_records()参照)。
        """
        matched = [
            r
            for r in self._records
            if r.store_id == store_id
            and start_date <= r.booking_date <= end_date
            and r.status_override is None
        ]
        matched.sort(key=lambda r: (r.booking_date, r.start_minutes))
        return [r.to_list_entry() for r in matched]

    def customer_records(self, customer_name: str) -> list[CustomerBookingRecord]:
        """owner-settings-wireframe.md顧客詳細ページのbuild_customer_detail_view()に
        そのまま渡せる。キャンセル・変更済みのレコードもstatusを更新した上でそのまま含める
        (来店履歴として引き続き参照できるようにするため)。"""
        return [r.to_customer_record() for r in self._records if r.customer_name == customer_name]

    def record_cancelled(self, store_id: str, slot_key: tuple, status: str) -> None:
        """cancel_booking()/change_booking()がconfirmed状態の予約枠を解放した際に呼ぶ。
        店舗・slot_keyが一致するレコードのstatusをCANCELLED_STATUS/CHANGED_STATUSへ更新する
        (レコード自体の削除は行わない。理由はクラスdocstring参照)。一致するレコードが
        見つからない場合(record_store未指定のまま確定した過去データ等)は何もしない。
        """
        self._update_status(store_id, slot_key, status)

    def record_visited(self, store_id: str, slot_key: tuple) -> None:
        """no-show-handling.md 検知条件2の「来店済み」操作。owner-settings-wireframe.mdの
        予約一覧ページでオーナーが該当予約に1タップでチェックを入れた際に呼ぶ。
        該当レコードのstatusをVISITED_STATUS(来店済み)へ更新する(削除はしない)。
        """
        self._update_status(store_id, slot_key, VISITED_STATUS)

    def record_no_show_confirmed(self, store_id: str, slot_key: tuple) -> None:
        """no-show-handling.mdの「無断キャンセル候補」ダイジェスト通知を受けて、オーナーが
        予約一覧から最終的に無断キャンセルと確定した際に呼ぶ(自動断定はしない。
        該当レコードのstatusをNO_SHOW_CONFIRMED_STATUSへ更新し、build_customer_detail_view()の
        無断キャンセル確定数・直近の無断キャンセル日の集計対象になる)。
        """
        self._update_status(store_id, slot_key, NO_SHOW_CONFIRMED_STATUS)

    def record_reminder_replied(self, store_id: str, slot_key: tuple) -> None:
        """customer-reply-detection-design.md準拠。confirmed状態の会話に何らかのメッセージが
        届いた事実を反映する(内容は問わない)。ConversationFlowStateMachine.record_reminder_reply()
        から呼ばれ、build_customer_detail_view()の「前回リマインドへの返信」表示に使われる。
        一致するレコードが見つからない場合(record_store未指定のまま確定した過去データ等)は
        何もしない。statusとは独立したフラグのため_update_status()は使わない。
        """
        for record in self._records:
            if record.store_id == store_id and record.slot_key == slot_key:
                record.reminder_replied = True
                return

    def _update_status(self, store_id: str, slot_key: tuple, status: str) -> None:
        for record in self._records:
            if record.store_id == store_id and record.slot_key == slot_key:
                record.status_override = status
                return


def mark_booking_visited(record_store: InMemoryBookingRecordStore, entry: BookingListEntry) -> bool:
    """owner-settings-wireframe.md予約一覧ページの「来店済み」チェック操作から
    InMemoryBookingRecordStore.record_visited()への配線(booking-record-store-design.md
    「MVPスコープの範囲外として残す点」にあった実呼び出し配線のうち、実際の画面描画・
    クリックイベント自体を除いたロジック部分)。entry.slot_keyが無い(record_storeを介さず
    組み立てられたBookingListEntry等)場合は何もせずFalseを返す。
    """
    if entry.slot_key is None:
        return False
    record_store.record_visited(entry.store_id, entry.slot_key)
    return True


def mark_booking_no_show_confirmed(record_store: InMemoryBookingRecordStore, entry: BookingListEntry) -> bool:
    """予約一覧ページの「無断キャンセル確定」操作からrecord_no_show_confirmed()への配線。
    mark_booking_visited()と同様、entry.slot_keyが無い場合は何もせずFalseを返す。
    """
    if entry.slot_key is None:
        return False
    record_store.record_no_show_confirmed(entry.store_id, entry.slot_key)
    return True


def _escalation_type_label(event: dict) -> str:
    """escalation-notification-templates.md「種別ごとの文面」の種別ラベル部分に相当。"""
    reason = event.get("escalation_reason")
    if reason == "unimplemented_feature":
        return "未対応機能に関するお問い合わせ"
    if reason in _SYSTEM_EVENT_LABELS:
        return _SYSTEM_EVENT_LABELS[reason]
    unresolved = [seg["topic"] for seg in (event.get("faq_segments") or []) if not seg.get("resolved")]
    if unresolved:
        labels = "・".join(FAQ_TOPIC_LABELS.get(t, t) for t in unresolved)
        return f"未登録FAQへのお問い合わせ({labels})"
    return "予約以外のご相談"


def _escalation_detail_text(event: dict, reply_text: Optional[str] = None) -> str:
    """escalation-notification-templates.md「内容」部分に相当。

    会話要約フィールドの追加要否(escalation-notification-templates.md「次のステップ候補」)は
    検討の結果、構造化出力にLLM生成の要約フィールドは追加しないと結論した。理由は
    (1)医療相談・クレーム等の機微な内容をLLMが要約する過程で誤読・言い換えが混入するリスクが
    あり、オーナーが実際の顧客発言と異なる内容を信じてしまう事故につながりうること、
    (2)Cloud Function Bのprocess()は既にLINE Webhookイベントから顧客の生メッセージ本文
    (reply_text)を取得済みで、要約せずそのまま引用すれば内容欄の目的(オーナーが概要を
    即座に把握できること)を追加のLLM出力なしに満たせること、の2点による。
    feature_hint(unimplemented_feature用の自由記述)はLLMによる短い言い換えだが影響が軽微
    (機能要望の趣旨のみで機微情報を含まない)なため従来通り優先する。reply_textが空、または
    システム内部イベント(_dispatch_flow_notify_actions経由、顧客の1メッセージに1対1で
    対応しない)の場合はLINEトーク画面参照の案内に留める。
    """
    if event.get("escalation_reason") == "unimplemented_feature" and event.get("feature_hint"):
        return event["feature_hint"]
    if reply_text:
        return f"「{reply_text}」といった内容です。"
    return "詳細はLINEトーク画面で内容をご確認ください。"


def is_escalation_event_owner_notable(event: dict) -> bool:
    """EscalationConsolidator.on_event()はneeds_owner_checkの値を見ずに全イベントを
    ウィンドウ管理の対象にする(既存の集約ロジック自体は変更しない)ため、実際にオーナーへ
    pushすべきかどうかは呼び出し元でこの関数を使って別途判定する。
    `needs_owner_check`はschema/validate_test_cases.pyのクロスフィールド検証により
    「faq_segmentsにresolved:falseが含まれる場合は必ずtrue」が保証されているため、
    基本の判定に使える。システム内部イベント(_SYSTEM_EVENT_LABELS該当)はLLM構造化出力を
    経由せず`needs_owner_check`が付与されないことがあるため、escalation_reasonでも判定する。
    """
    if event.get("needs_owner_check"):
        return True
    reason = event.get("escalation_reason")
    return reason in _SYSTEM_EVENT_LABELS or reason == "unimplemented_feature"


def format_escalation_notification(
    customer_label: str, event: dict, now: datetime, reply_text: Optional[str] = None
) -> str:
    """escalation-notification-templates.md「通知文面の基本形」準拠。
    EscalationConsolidator.on_event()が返す("immediate"|"immediate_refire", event)アクションを
    実際にオーナーへpushする際に使う想定(呼び出し元はcloud_function_process_event.py)。
    reply_textはLLM構造化出力を発生させた顧客の生メッセージ本文(任意)。指定時は
    「内容」欄にそのまま引用する(_escalation_detail_text参照)。
    """
    return (
        f"【要確認】{customer_label}より{now.strftime('%H:%M')}にお問い合わせがありました。\n"
        f"種別: {_escalation_type_label(event)}\n"
        f"内容: {_escalation_detail_text(event, reply_text)}\n"
        "対応: 店舗から直接ご連絡または次回来店時にご案内をお願いします。"
    )


def format_escalation_digest_message(customer_label: str, events: list, now: datetime) -> str:
    """escalation-consolidation-logic.mdのウィンドウ集約分(EscalationConsolidator.flush_due_windows()で
    取り出した分)を1通にまとめてオーナーへ通知する際の文面。件数・種別内訳のみを示し、
    詳細はLINEトーク画面参照とする(Cloud Scheduler等の定期実行トリガーから呼び出す想定、
    reminder_scheduler.pyと同様に判定・整形ロジックのみを実クラウド接続なしで検証可能にしたもの)。
    """
    counts: dict[str, int] = {}
    for event in events:
        label = _escalation_type_label(event)
        counts[label] = counts.get(label, 0) + 1
    breakdown = "\n".join(f"  - {label}: {count}件" for label, count in counts.items())
    return (
        f"【まとめてご確認】{customer_label}より短時間に{len(events)}件のお問い合わせがありました。\n"
        f"内訳:\n{breakdown}\n"
        "対応: LINEトーク画面で内容をご確認のうえ、まとめてご対応をお願いします。"
    )


# ---------------------------------------------------------------------------
# 4. double-booking-prevention.md: 仮押さえ(pending)→確定(confirmed)の2段階予約枠管理
# ---------------------------------------------------------------------------

@dataclass
class _Slot:
    status: str  # "pending" or "confirmed"
    user_id: str
    held_at: datetime


class BookingSlotManager:
    """予約枠(店舗ID+日付+時間帯をキーとする)の仮押さえ→確定の2段階管理。

    ルール(double-booking-prevention.md準拠):
      - 顧客が枠を指定した時点でhold()し、pending状態にする。
        pendingはHOLD_TIMEOUT(5分)を過ぎると自動的に解放され、他の顧客に再提示可能になる。
      - 氏名等が揃いconfirm()を呼んだ時点でconfirmed状態にする。
        pendingがタイムアウト済み・別ユーザーに奪われている場合はconfirm()も失敗する
        (「読み込み→空きチェック→書き込み」を単一シリアル実行することを前提に、
        呼び出し側は単一プロセス・単一スレッドからの逐次呼び出しを想定している。
        MVP段階のスプレッドシート+キュー処理方式に対応する簡易モデルであり、
        真の並行アクセス(マルチプロセス)には未対応)。
      - hold()が別ユーザーのpending/confirmedと衝突した場合は失敗を返す
        (呼び出し側で「ちょうど埋まってしまいました」等の案内・直近空き枠の再提示を行う)。
    """

    HOLD_TIMEOUT = timedelta(minutes=5)

    def __init__(self) -> None:
        self._slots: dict[tuple, _Slot] = {}

    def _expire_if_needed(self, slot_key: tuple, now: datetime) -> None:
        slot = self._slots.get(slot_key)
        if slot is not None and slot.status == "pending" and now - slot.held_at > self.HOLD_TIMEOUT:
            del self._slots[slot_key]

    def hold(self, slot_key: tuple, user_id: str, now: datetime) -> bool:
        """枠の仮押さえを試みる。成功時True、既に他ユーザーに押さえられている場合False。"""
        self._expire_if_needed(slot_key, now)
        existing = self._slots.get(slot_key)
        if existing is not None and existing.user_id != user_id:
            return False
        self._slots[slot_key] = _Slot(status="pending", user_id=user_id, held_at=now)
        return True

    def confirm(self, slot_key: tuple, user_id: str, now: datetime) -> bool:
        """仮押さえ済みの枠を確定する。pendingがタイムアウト済み・別ユーザーの場合はFalse。"""
        self._expire_if_needed(slot_key, now)
        existing = self._slots.get(slot_key)
        if existing is None or existing.user_id != user_id or existing.status != "pending":
            return False
        existing.status = "confirmed"
        return True

    def release(self, slot_key: tuple) -> None:
        """明示的な解放(顧客都合でのキャンセル等、呼び出し側の判断で使用)。"""
        self._slots.pop(slot_key, None)

    def status(self, slot_key: tuple, now: datetime) -> Optional[str]:
        self._expire_if_needed(slot_key, now)
        slot = self._slots.get(slot_key)
        return slot.status if slot else None


# ---------------------------------------------------------------------------
# 5. conversation-flow.md: 会話フロー本体(候補提示→確定)とBookingSlotManagerの接続
# ---------------------------------------------------------------------------

class ConversationFlowError(Exception):
    """呼び出し順序が状態遷移ルールに反する場合に送出する(呼び出し側の実装ミス検知用)。"""


# pending-timeout-ux.mdの文言案4「保留取得に失敗した場合」をそのまま接続する。
# {slot_label}: 選ばれた枠の表示用文言(例: "8/9(土) 15:30〜")、
# {alt_candidates}: 呼び出し側が用意した代替候補の表示用文言(例: "8/9(土) 17:00 / 8/10(日) 14:00")。
# 代替候補そのものの検索(空き枠一覧の取得)は本エンジンの守備範囲外のため呼び出し側で用意する想定。
SLOT_CONFLICT_MESSAGE_TEMPLATE = (
    "大変申し訳ございません、ちょうど{slot_label}の枠が埋まってしまいました。\n"
    "近い時間ですと {alt_candidates} が空いております。いかがでしょうか?"
)

# 再確認ループの上限(candidate-presentation-and-selection-design.md 6節)。
# resolve_candidate_selection()による特定不能がこの回数を超えて連続した場合、
# 再確認メッセージの繰り返しをやめてオーナーへエスカレーションする。
RECONFIRM_MAX_ATTEMPTS = 2

ESCALATION_HANDOFF_MESSAGE = (
    "申し訳ございません、うまく聞き取れませんでした。"
    "担当より改めてご連絡いたしますので少々お待ちください。"
)


@dataclass
class SelectSlotResult:
    success: bool
    message: Optional[str] = None  # 失敗時のみ、顧客への案内文言(呼び出し側でそのまま送信可能)
    # escalation-notification-templates.md「次のステップ候補」準拠。candidate_selection_unresolved
    # 発火時のみ非空。EscalationConsolidator.on_event()が返した即時通知アクションをそのまま運ぶ
    # (engine.py自体はI/Oを持たないため、呼び出し側がformat_escalation_notification()等で
    # 整形してpushする。owner-notification-channel-design.md参照)。
    owner_notify_actions: list = field(default_factory=list)


@dataclass
class ProvideDetailsResult:
    """provide_details()の戻り値。以前はbool一つだったが、booking_conflict発火時に
    EscalationConsolidator.on_event()の戻り値(即時通知アクション)を呼び出し側へ伝播させる
    必要が生じたため、SelectSlotResultと同じ形の型に変更した(escalation-notification-templates.md
    「次のステップ候補」準拠)。
    """
    confirmed: bool
    owner_notify_actions: list = field(default_factory=list)


@dataclass
class CancelResult:
    """cancel_booking()の戻り値。cancel-intent-handling-design.md準拠。"""
    found: bool  # Falseの場合、会話メモリ上には何も無い(呼び出し側で安全側のオーナー転送を行う)
    stage: Optional[str] = None  # 取り消された時点のstage: "candidates_presented" | "awaiting_details" | "confirmed"
    slot_key: Optional[tuple] = None
    name: Optional[str] = None
    menu: Optional[str] = None
    owner_notify_actions: list = field(default_factory=list)  # SelectSlotResultと同じ位置づけ


@dataclass
class ChangeResult:
    """change_booking()の戻り値。change-intent-handling-design.md準拠。"""
    found: bool  # Falseの場合、会話メモリ上には何も無い(呼び出し側で安全側のオーナー転送を行う)
    stage: Optional[str] = None  # 取り消された時点のstage: "candidates_presented" | "awaiting_details" | "confirmed"
    slot_key: Optional[tuple] = None
    name: Optional[str] = None
    menu: Optional[str] = None
    owner_notify_actions: list = field(default_factory=list)  # SelectSlotResultと同じ位置づけ


@dataclass
class ReleasedConversation:
    """release_idle_conversations()の戻り値要素。candidates-expired-notification-design.md準拠。
    stageを含めるのは、将来candidates_presented失効時のみプッシュ通知を送るオプション機能を
    追加する際に、呼び出し側がuser_idのリストからstageを再取得しなくても済むようにするため
    (失効時点で_statesから既に削除されているため、削除後にstageを引き直すことはできない)。"""
    user_id: str
    stage: str  # 失効時点のstage: "candidates_presented" | "awaiting_details"


# conversation-state-cleanup.mdの無応答失効時間。channel-agnostic-session-id.mdの
# セッション失効(30分無応答)、escalation-consolidation-logic.mdの30分リセットと時間感覚を統一する。
CONVERSATION_IDLE_TIMEOUT = timedelta(minutes=30)


@dataclass
class _ConversationState:
    stage: str  # "candidates_presented" | "awaiting_details" | "confirmed"
    slot_key: Optional[tuple] = None
    name: Optional[str] = None
    menu: Optional[str] = None
    candidates: Optional[list] = None  # present_candidates()で提示した候補一覧(select_slot_from_reply用)
    reconfirm_count: int = 0  # select_slot_from_reply()での特定不能が連続した回数(RECONFIRM_MAX_ATTEMPTS参照)
    last_activity_at: Optional[datetime] = None  # release_idle_conversations()の失効判定に使う
    emoji_used_last: bool = False  # consume_casual_emoji_allowance()参照(絵文字頻度上限)


class ConversationFlowStateMachine:
    """conversation-flow.mdの「候補提示→確定」の2ステップをBookingSlotManagerに接続する状態遷移。

    ステージ: candidates_presented → (枠選択、hold()) → awaiting_details
              → (氏名・メニュー確定、confirm()) → confirmed

    confirm()が失敗した場合(booking-slot-manager-design.mdの「今後の課題」に残っていた、
    確定操作自体が競合するケースの呼び出し側実装):
      - この時点で失敗するのは、当該ユーザーの保留がタイムアウト済みか、既に別ユーザーの
        保留/確定に上書きされている場合のみ(BookingSlotManager.confirm()の実装上)。
        いずれの場合もこのユーザーが「保留していたはずの」枠は既に手元に無いため、
        double-booking-prevention.mdの「後着の予約をpending状態に戻す」は、別ユーザーの
        正当な保留/確定を誤って解放しないよう、ここでは明示的なslot操作を行わない
        (release()は呼ばない)。
      - EscalationConsolidator経由でオーナーへ即時通知し、logsが渡されていれば
        NotificationLogAggregatorにもescalation_reason='booking_conflict'を記録した上で、
        このユーザーの会話状態はcandidates_presentedに戻す(呼び出し側で新しい空き枠を
        再提示する想定)。この通知イベントはLLM構造化出力ではなくシステム内部で生成する
        イベントのため、booking_output.schema.jsonのescalation_reason enumには含めず
        スキーマ検証の対象外としている(system-event-log-gap-fix.md参照)。
    """

    def __init__(
        self,
        slots: BookingSlotManager,
        consolidator: EscalationConsolidator,
        logs: Optional["NotificationLogAggregator"] = None,
        record_store: Optional["InMemoryBookingRecordStore"] = None,
    ) -> None:
        """logsはsystem-event-log-gap-fix.md準拠。booking_conflict/booking_cancelled/
        booking_change_started/candidate_selection_unresolvedといったシステム内部発火の
        escalation_reasonをNotificationLogAggregator.system_event_countsにも記録したい
        呼び出し側(Cloud Function Bの本番配線)が渡す。未指定(None)の場合は
        EscalationConsolidatorへの通知のみ行い、従来通り動作する(既存の呼び出し側・
        テストへの後方互換のため)。
        record_storeはInMemoryBookingRecordStoreのdocstring準拠。渡すとprovide_details()の
        確定成功時に自動でrecord_confirmed()が呼ばれる。未指定(None)の場合は従来通り
        記録を行わない(後方互換の任意引数)。
        """
        self._slots = slots
        self._consolidator = consolidator
        self._logs = logs
        self._record_store = record_store
        self._states: dict[str, _ConversationState] = {}
        self._last_idle_cleanup_at: Optional[datetime] = None
        self._last_archive_at: Optional[datetime] = None
        self._first_booking_self_check_sent = False
        self._first_booking_self_check_pending = False

    def _notify_system_event(self, user_id: str, event: dict, now: datetime) -> list:
        """システム内部発火のescalationイベント(booking_conflict等、SYSTEM_ESCALATION_REASONS参照)を
        EscalationConsolidator(オーナーへの即時/集約通知)とNotificationLogAggregator
        (通知ログ集計画面向けのsystem_event_counts)の両方に記録する。従来はconsolidatorのみに
        通知しており、logs側には記録が届かないギャップがあった(system-event-log-gap-fix.md参照)。

        戻り値はEscalationConsolidator.on_event()が返す即時通知アクション一覧
        (`[("immediate"|"immediate_refire", event), ...]`)をそのまま返す。engine.py自体は
        LINE Push等のI/Oを持たないため、呼び出し元(各publicメソッドの戻り値の
        owner_notify_actions)を経由してCloud Function B側へ伝播させ、実際のpushは
        呼び出し側(ConversationEventProcessor)に委ねる(escalation-notification-templates.md
        「次のステップ候補」準拠)。
        """
        actions = self._consolidator.on_event(user_id, event, now)
        if self._logs is not None:
            self._logs.record(user_id, event, now)
        return actions

    def consume_casual_emoji_allowance(self, user_id: str) -> bool:
        """message-tone-variants.md「絵文字頻度上限」準拠。casualトーンの絵文字は、直前に
        このユーザーへ送った顧客向けメッセージで使用済みなら次の1通は見送り、その次でまた
        使えるようにする(直近2通に1回まで)。呼び出し側はformat_hold_message()/
        format_confirmation_message()のemoji_allowed引数へ戻り値をそのまま渡す。

        1メッセージ送信につき1回だけ呼ぶこと(呼ぶたびに状態を更新するため、べき等ではない)。
        会話状態がまだ無い場合(hold前の初回等、present_candidates()未実行)は許可する
        (この場合は状態を持たないため次回への引き継ぎはできないが、hold()実行後は
        _statesに状態が作られるため以降は正しく追跡できる)。
        """
        state = self._states.get(user_id)
        if state is None:
            return True
        allowed = not state.emoji_used_last
        state.emoji_used_last = allowed
        return allowed

    def present_candidates(self, user_id: str, candidates: Optional[list] = None, *, now: datetime) -> None:
        """候補日時を提示した時点で呼ぶ。新規会話・再提示のいずれでも状態を初期化する。
        candidatesを渡しておくと、select_slot_from_reply()で顧客の返信からslot_keyを
        自動解決できる(candidate-presentation-and-selection-design.md 4節)。
        nowはconversation-state-cleanup.mdのrelease_idle_conversations()が使う
        last_activity_atの起点として記録する。
        """
        self._states[user_id] = _ConversationState(
            stage="candidates_presented", candidates=candidates, last_activity_at=now
        )

    def select_slot(
        self,
        user_id: str,
        slot_key: tuple,
        now: datetime,
        slot_label: str = "",
        alt_candidates: str = "",
    ) -> SelectSlotResult:
        """顧客が候補から枠を選んだ時点で呼ぶ。hold()成功ならawaiting_detailsへ進む。
        失敗(他ユーザーとの競合)時はcandidates_presentedのまま、pending-timeout-ux.mdの
        文言案4を接続した案内メッセージを返す(呼び出し側はそのまま顧客へ送信できる)。
        slot_label/alt_candidatesは表示用の文言(呼び出し側で日時整形・空き枠検索を行い渡す。
        空き枠検索自体は本エンジンの範囲外で、intent-to-flow-mapping.mdの今後の課題を参照)。
        """
        state = self._states.get(user_id)
        if state is None or state.stage != "candidates_presented":
            raise ConversationFlowError(f"unexpected stage for select_slot: {state}")
        if self._slots.hold(slot_key, user_id, now):
            state.stage = "awaiting_details"
            state.slot_key = slot_key
            state.last_activity_at = now
            return SelectSlotResult(success=True)
        message = SLOT_CONFLICT_MESSAGE_TEMPLATE.format(
            slot_label=slot_label, alt_candidates=alt_candidates
        )
        return SelectSlotResult(success=False, message=message)

    def select_slot_from_reply(self, user_id: str, reply_text: str, now: datetime) -> SelectSlotResult:
        """顧客の返信テキストから直接候補を確定する高レベルAPI。present_candidates()で
        渡したcandidatesに対してresolve_candidate_selection()を適用し、特定できればselect_slot()
        へ、特定できなければformat_reconfirm_message()を案内文言として返す
        (candidate-presentation-and-selection-design.md 5節「select_slot()との接続」への対応)。
        呼び出し側でslot_keyを直接特定できている場合は、従来どおりselect_slot()を直接使う。
        """
        state = self._states.get(user_id)
        if state is None or state.stage != "candidates_presented":
            raise ConversationFlowError(f"unexpected stage for select_slot_from_reply: {state}")
        if not state.candidates:
            raise ConversationFlowError(
                "select_slot_from_reply requires candidates passed to present_candidates()"
            )
        candidates = state.candidates
        slot_key = resolve_candidate_selection(reply_text, candidates)
        state.last_activity_at = now
        if slot_key is None:
            state.reconfirm_count += 1
            if state.reconfirm_count > RECONFIRM_MAX_ATTEMPTS:
                # 再確認をRECONFIRM_MAX_ATTEMPTS回送っても特定できない場合は、案内文言を
                # 繰り返さずオーナーへ引き継ぐ(candidate-presentation-and-selection-design.md 6節)。
                # booking_conflictと同様、システム内部イベントのためbooking_output.schema.jsonの
                # escalation_reason enumには未追加(今後の課題)。
                actions = self._notify_system_event(
                    user_id,
                    {
                        "intent": "escalation",
                        "needs_owner_check": True,
                        "escalation_reason": "candidate_selection_unresolved",
                    },
                    now,
                )
                state.reconfirm_count = 0
                return SelectSlotResult(
                    success=False, message=ESCALATION_HANDOFF_MESSAGE, owner_notify_actions=actions
                )
            return SelectSlotResult(success=False, message=format_reconfirm_message(candidates))

        state.reconfirm_count = 0
        chosen = next(c for c in candidates if c.slot_key == slot_key)
        alt_labels = [c.label for c in candidates if c.slot_key != slot_key]
        return self.select_slot(
            user_id,
            slot_key,
            now,
            slot_label=chosen.label,
            alt_candidates="、".join(alt_labels) if alt_labels else "改めてご希望の日時",
        )

    def provide_details(self, user_id: str, name: str, menu: str, now: datetime) -> ProvideDetailsResult:
        """氏名・メニューが揃った時点で呼ぶ。confirm()成功ならconfirmedへ進む。
        失敗(確定操作自体の競合)時はcandidates_presentedへ差し戻し、オーナーへ通知する。
        """
        state = self._states.get(user_id)
        if state is None or state.stage != "awaiting_details":
            raise ConversationFlowError(f"unexpected stage for provide_details: {state}")
        state.name = name
        state.menu = menu
        state.last_activity_at = now
        if self._slots.confirm(state.slot_key, user_id, now):
            state.stage = "confirmed"
            if self._record_store is not None:
                self._record_store.record_confirmed(state.slot_key[0], state.slot_key, name, menu)
            if not self._first_booking_self_check_sent:
                self._first_booking_self_check_sent = True
                self._first_booking_self_check_pending = True
            return ProvideDetailsResult(confirmed=True)

        actions = self._notify_system_event(
            user_id,
            {
                "intent": "escalation",
                "needs_owner_check": True,
                "escalation_reason": "booking_conflict",
                "slot_key": state.slot_key,
            },
            now,
        )
        state.stage = "candidates_presented"
        state.slot_key = None
        return ProvideDetailsResult(confirmed=False, owner_notify_actions=actions)

    def record_reminder_reply(self, user_id: str) -> None:
        """customer-reply-detection-design.md準拠。confirmed状態の会話に何らかのメッセージが
        届いた事実を、record_storeが保持する該当予約レコードのreminder_repliedへ反映する。
        呼び出し側(Cloud Function B)がconfirmed_reply_recorder(Firestore向け)と並行して、
        stageが"confirmed"のときにこのメソッドも呼ぶ想定。record_store未指定、会話状態が無い、
        confirmed以外のstageのいずれの場合も何もしない(後方互換・安全側のfail-silent)。
        """
        if self._record_store is None:
            return
        state = self._states.get(user_id)
        if state is None or state.stage != "confirmed" or state.slot_key is None:
            return
        self._record_store.record_reminder_replied(state.slot_key[0], state.slot_key)

    def consume_first_booking_self_check(self) -> bool:
        """first-booking-self-check-notification-design.md準拠。店舗全体で最初の予約確定が
        発生した直後にTrueを一度だけ返す。呼び出し側(Cloud Function Bの本番配線)は
        provide_details()の戻り値のconfirmedがTrueだった直後にこれを呼び、Trueならformat_confirmation_message()
        とは別にformat_first_booking_self_check_message()をオーナーへ追加送信する想定。
        オーナーが実際に問題を起こしたわけではないためEscalationConsolidator/
        NotificationLogAggregator(いずれもneeds_owner_check起点の問題対応向け集計)は経由しない。
        """
        if self._first_booking_self_check_pending:
            self._first_booking_self_check_pending = False
            return True
        return False

    def stage(self, user_id: str) -> Optional[str]:
        state = self._states.get(user_id)
        return state.stage if state else None

    def cancel_booking(self, user_id: str, now: datetime) -> "CancelResult":
        """cancel-intent-handling-design.md準拠。intent: "cancel"を受けた際に呼ぶ。
        会話のstageに応じて処理を分岐する:
          - 状態なし: release()する対象が無く、エンジンの会話メモリだけでは実在の予約有無を
            確定できない(未予約、または既にarchive_completed_conversations()で間引かれた
            過去の確定予約の可能性がある)ため、found=Falseを返す(呼び出し側で安全側の
            オーナー転送を行う想定)。
          - candidates_presented: まだhold()していないため取り消す実体が無く、会話状態のみ削除する。
          - awaiting_details: pending状態のholdをrelease()し、会話状態を削除する。
          - confirmed: 確定済みの枠をrelease()し、会話状態を削除する。
        confirmed分のオーナー通知(EscalationConsolidator経由)はここで行う。
        candidates_presented/awaiting_details分はオーナー側の外部予約記録にまだ何も
        載っていない想定のため通知しない(設計の詳細はcancel-intent-handling-design.md参照)。
        """
        state = self._states.get(user_id)
        if state is None:
            return CancelResult(found=False)

        stage, slot_key, name, menu = state.stage, state.slot_key, state.name, state.menu
        if stage in ("awaiting_details", "confirmed") and slot_key is not None:
            self._slots.release(slot_key)
        del self._states[user_id]

        actions: list = []
        if stage == "confirmed":
            if self._record_store is not None and slot_key is not None:
                self._record_store.record_cancelled(slot_key[0], slot_key, CANCELLED_STATUS)
            actions = self._notify_system_event(
                user_id,
                {
                    "intent": "cancel",
                    "needs_owner_check": True,
                    "escalation_reason": "booking_cancelled",
                    "slot_key": slot_key,
                    "name": name,
                },
                now,
            )
        return CancelResult(
            found=True, stage=stage, slot_key=slot_key, name=name, menu=menu, owner_notify_actions=actions
        )

    def change_booking(self, user_id: str, now: datetime) -> "ChangeResult":
        """change-intent-handling-design.md準拠。intent: "change"を受けた際に呼ぶ。
        「旧枠の解放」部分はcancel_booking()と同じ分岐(stageに応じたrelease()・confirmed分のみ
        オーナー通知)を行うが、cancel_booking()と異なり会話を終了させない。呼び出し側は
        found=Trueの場合、続けて_start_new_booking()相当の新規候補検索・present_candidates()を
        行い、同じ会話の中で新しい日時の予約フローへそのまま入る想定(change = 「旧予約の解放」+
        「新規予約フローの開始」の合成、という考え方はcancel-intent-handling-design.mdの
        残課題に記載した方針を踏襲する)。
        """
        state = self._states.get(user_id)
        if state is None:
            return ChangeResult(found=False)

        stage, slot_key, name, menu = state.stage, state.slot_key, state.name, state.menu
        if stage in ("awaiting_details", "confirmed") and slot_key is not None:
            self._slots.release(slot_key)
        del self._states[user_id]

        actions: list = []
        if stage == "confirmed":
            if self._record_store is not None and slot_key is not None:
                self._record_store.record_cancelled(slot_key[0], slot_key, CHANGED_STATUS)
            # 確定済みだった枠を解放した事実は、cancelと同じくオーナー側の外部予約記録の
            # 更新が必要なため通知する。escalation_reasonをbooking_cancelledと分けたのは、
            # 「新しい日時への変更手続き中」であることをオーナーが区別できるようにするため
            # (単純なキャンセルと同列に扱うと、顧客対応の緊急度・後続対応の要否が変わってくる)。
            actions = self._notify_system_event(
                user_id,
                {
                    "intent": "change",
                    "needs_owner_check": True,
                    "escalation_reason": "booking_change_started",
                    "slot_key": slot_key,
                    "name": name,
                },
                now,
            )
        return ChangeResult(
            found=True, stage=stage, slot_key=slot_key, name=name, menu=menu, owner_notify_actions=actions
        )

    def release_idle_conversations(self, now: datetime) -> list[ReleasedConversation]:
        """conversation-state-cleanup.md準拠。last_activity_atからCONVERSATION_IDLE_TIMEOUT
        (30分)以上経過した会話状態を失効させる。confirmed状態は対象外(前日リマインド等で
        後から参照されるため保持し続ける)。awaiting_detailsで止まっていた場合は、対応する
        枠のholdも明示的に解放する(既にBookingSlotManager側のHOLD_TIMEOUTで解放済みでも、
        release()自体は無害なため呼び出し順序に依存しない)。エンジン自身がエスカレーション通知や
        プッシュメッセージを送ることはない(無応答離脱は日常的に発生するため、都度通知すると
        通知過多になる。candidates-expired-notification-design.md参照)。
        戻り値: 失効させた(user_id, stage)のリスト(呼び出し側のログ・監視用、および将来
        candidates_presented失効時のみ能動メッセージを送るオプション機能を追加する場合の
        フィルタ材料。stageを含める理由はReleasedConversationのdocstring参照)。
        """
        released: list[ReleasedConversation] = []
        for user_id, state in list(self._states.items()):
            if state.stage == "confirmed":
                continue
            if state.last_activity_at is None or now - state.last_activity_at < CONVERSATION_IDLE_TIMEOUT:
                continue
            if state.stage == "awaiting_details" and state.slot_key is not None:
                self._slots.release(state.slot_key)
            del self._states[user_id]
            released.append(ReleasedConversation(user_id=user_id, stage=state.stage))
        return released

    # confirmed-state-archival.md準拠。来店日を過ぎたconfirmed会話を_statesから間引く。
    ARCHIVE_AFTER_VISIT = timedelta(days=1)

    def archive_completed_conversations(self, now: datetime) -> list[str]:
        """conversation-state-cleanup.mdの「今後の課題」に残っていた、confirmed状態の
        アーカイブ処理。来店日(slot_keyの日付)からARCHIVE_AFTER_VISIT(1日)以上経過した
        confirmed会話を_statesから削除する。

        1日分の猶予を置くのは、no-show-handling.mdの無断キャンセル判定(来店予定日当日中の
        来店有無確認)や前日リマインドの再送判定が、来店日当日いっぱいはstate.slot_keyを
        参照する可能性があるため(詳細はconfirmed-state-archival.md参照)。

        注意: ここでの「アーカイブ」はあくまで本エンジンが保持する会話メモリ(_states)からの
        削除であり、予約そのものの永続記録(no-show-handling.mdが参照する累計予約数・無断
        キャンセル確定数などの履歴)は別の永続ストレージ(スプレッドシート等)側で保持される
        想定のため、本メソッドはそちらのデータには一切関与しない。BookingSlotManager側の
        confirmedステータスも、予約の一次記録として変更せずそのまま残す。
        戻り値: アーカイブしたuser_idのリスト(呼び出し側のログ用)。
        """
        archived: list[str] = []
        for user_id, state in list(self._states.items()):
            if state.stage != "confirmed" or state.slot_key is None:
                continue
            visit_date = date.fromisoformat(state.slot_key[1])
            if now.date() - visit_date < self.ARCHIVE_AFTER_VISIT:
                continue
            del self._states[user_id]
            archived.append(user_id)
        return archived

    # idle-conversation-trigger-design.md準拠。専用スケジューラ導入前のMVPでは、
    # Webhook受信のたびにclean-up関数を呼び出す「便乗トリガー」とする。ただし全リクエストで
    # 毎回全件スキャンするのは無駄なため、最小実行間隔を設けて間引く。
    IDLE_CLEANUP_MIN_INTERVAL = timedelta(minutes=5)

    def maybe_run_idle_cleanup(self, now: datetime) -> Optional[list[ReleasedConversation]]:
        """Webhook受信時に呼び出す想定の便乗トリガー。前回実行からIDLE_CLEANUP_MIN_INTERVAL
        未満の場合は何もせずNoneを返す(スキップしたことを呼び出し側が区別できるように、
        「対象0件だった」場合の空リストとは戻り値の型を分けている)。"""
        if (
            self._last_idle_cleanup_at is not None
            and now - self._last_idle_cleanup_at < self.IDLE_CLEANUP_MIN_INTERVAL
        ):
            return None
        self._last_idle_cleanup_at = now
        return self.release_idle_conversations(now)

    def maybe_run_archive(self, now: datetime) -> Optional[list[str]]:
        """maybe_run_idle_cleanup()と同じ便乗トリガー・間引き幅をarchive_completed_conversations()
        にも流用する(ARCHIVE_AFTER_VISITが1日単位のため、5分の間引きによる影響はさらに小さい)。"""
        if (
            self._last_archive_at is not None
            and now - self._last_archive_at < self.IDLE_CLEANUP_MIN_INTERVAL
        ):
            return None
        self._last_archive_at = now
        return self.archive_completed_conversations(now)


# ---------------------------------------------------------------------------
# 6. slot-search-component-design.md: datetime_candidate(自然文)からslot_keyを
#    算出するための空き枠検索(営業時間・メニュー所要時間・BookingSlotManagerとの突き合わせ)
# ---------------------------------------------------------------------------

_TIME_OF_DAY_RANGES = {
    "morning": (9 * 60, 12 * 60),
    "afternoon": (12 * 60, 17 * 60),
    "evening": (17 * 60, None),  # Noneは営業終了時刻まで
}


_WEEKDAY_JA = ["月", "火", "水", "木", "金", "土", "日"]


class BusinessHoursConfigError(ValueError):
    """営業時間の区間設定が不正(逆転・重複)な場合に送出する(business-hours-lunch-break.md残課題)。"""


def _normalize_business_hour_ranges(value) -> list[tuple[int, int]]:
    """`business_hours`/`weekday_business_hours`の値を[(開始,終了), ...]形式に正規化する
    (business-hours-lunch-break.md)。単一区間の(開始,終了)タプルと、昼休憩等で分割した
    複数区間のリストの両方を受け付け、後者は開始時刻順に並べ替えて返す。

    各区間が開始<終了であること、区間同士が重複していないことを検証し、違反時は
    BusinessHoursConfigErrorを送出する(残課題「区間同士が重複・逆転している場合の
    バリデーションは未実装」への対応)。UI側(オーナー設定画面)での保存時チェックも
    別途必要だが、エンジン側でも不正な設定を無言で受け入れず即座に検出できるようにする。
    """
    if len(value) == 2 and isinstance(value[0], int):
        ranges = [tuple(value)]
    else:
        ranges = sorted(tuple(r) for r in value)
    for open_, close_ in ranges:
        if open_ >= close_:
            raise BusinessHoursConfigError(
                f"営業時間の区間が逆転または長さ0です(開始={open_}分, 終了={close_}分)"
            )
    for (_, prev_close), (next_open, _) in zip(ranges, ranges[1:]):
        if next_open < prev_close:
            raise BusinessHoursConfigError(
                f"営業時間の区間が重複しています(前の区間の終了={prev_close}分, "
                f"次の区間の開始={next_open}分)"
            )
    return ranges


@dataclass
class _Candidate:
    slot_key: tuple
    label: str
    start_minutes: int


class AvailabilitySearcher:
    """slot-search-component-design.md準拠。自然文の解釈はLLM側(今後の課題)に委ね、
    ここでは構造化された日付範囲・時間帯希望から、営業時間・メニュー所要時間・既存予約
    (BookingSlotManager)と突き合わせて具体的な空き枠(slot_key)を決定的に算出する。
    """

    def __init__(
        self,
        business_hours,  # (開始,終了)の単一区間、または[(開始,終了), ...]の複数区間(昼休憩等)。時刻は24時間表記の分。business-hours-lunch-break.md参照
        slot_interval_minutes: int = 30,
        closed_weekdays: frozenset = frozenset(),  # date.weekday()準拠(月=0〜日=6)、定休日
        weekday_business_hours: Optional[dict] = None,  # {weekday(月=0〜日=6): 区間 or 区間リスト} 曜日別に営業時間を上書き。未指定の曜日はbusiness_hoursを使う(weekday-specific-business-hours.md)
        closed_dates: frozenset = frozenset(),  # datetime.dateの集合。祝日・臨時休業など特定日付単発の休業(ad-hoc-closed-dates-support.md)
    ) -> None:
        self._default_ranges = _normalize_business_hour_ranges(business_hours)
        self._interval = slot_interval_minutes
        self._closed_weekdays = closed_weekdays
        self._closed_dates = closed_dates
        self._weekday_business_hours = {
            weekday: _normalize_business_hour_ranges(value)
            for weekday, value in (weekday_business_hours or {}).items()
        }

    def find_candidates(
        self,
        store_id: str,
        date_range: tuple,  # (date, date) の datetime.date タプル
        time_of_day_preference: Optional[str],
        menu_duration_minutes: int,
        booking_slots: BookingSlotManager,
        now: datetime,
        max_candidates: int = 3,
    ) -> list[_Candidate]:
        candidates: list[_Candidate] = []
        start_date, end_date = date_range
        day = start_date
        while day <= end_date and len(candidates) < max_candidates:
            if day.weekday() in self._closed_weekdays or day in self._closed_dates:
                day += timedelta(days=1)
                continue
            day_ranges = self._weekday_business_hours.get(day.weekday(), self._default_ranges)
            for range_open, range_close in day_ranges:
                if len(candidates) >= max_candidates:
                    break
                pref_start, pref_end = _TIME_OF_DAY_RANGES.get(
                    time_of_day_preference, (range_open, range_close)
                )
                pref_end = range_close if pref_end is None else min(pref_end, range_close)
                pref_start = max(pref_start, range_open)
                minute = pref_start
                while minute + menu_duration_minutes <= pref_end and len(candidates) < max_candidates:
                    slot_dt = datetime(day.year, day.month, day.day) + timedelta(minutes=minute)
                    if slot_dt >= now:
                        slot_key = (store_id, day.isoformat(), f"{minute // 60:02d}:{minute % 60:02d}")
                        if booking_slots.status(slot_key, now) is None:
                            label = (
                                f"{day.month}/{day.day}({_WEEKDAY_JA[day.weekday()]}) "
                                f"{minute // 60:02d}:{minute % 60:02d}〜"
                            )
                            candidates.append(_Candidate(slot_key=slot_key, label=label, start_minutes=minute))
                    minute += self._interval
            day += timedelta(days=1)
        return candidates


# ---------------------------------------------------------------------------
# 7. intent-to-flow-mapping.md: LLM構造化出力の`requested_date_range`/
#    `time_of_day_preference`をAvailabilitySearcherの入力に接続する
# ---------------------------------------------------------------------------

# requested_date_rangeはLLMが自然文から抽出した値であり上限がないため、「今月空いてる日」
# のような広い要求がそのままFirestoreレンジクエリに渡るとfirestore-traffic-cost-estimate.mdの
# 「検索レンジ3日」という試算前提を大きく超える可能性がある(slot-search-component-design.md
# 残課題)。ここでendを`start + MAX_SEARCH_RANGE_DAYS`にクランプし、読み取り件数の上限を明示する。
MAX_SEARCH_RANGE_DAYS = 14


def search_candidates_from_llm_output(
    searcher: AvailabilitySearcher,
    booking_slots: BookingSlotManager,
    store_id: str,
    output: dict,
    menu_duration_minutes: int,
    now: datetime,
    max_candidates: int = 3,
) -> Optional[list[_Candidate]]:
    """LLM構造化出力(`requested_date_range`/`time_of_day_preference`)から
    AvailabilitySearcher.find_candidates()を呼び出す。intent-to-flow-mapping.mdの対応表
    「`datetime_candidate`が曖昧(複数候補あり得る)」行の変換処理にあたる
    (呼び出し側はこの結果を`present_candidates()`→顧客への候補提示に使う)。

    `requested_date_range`がnull(LLMが日付の手がかりを抽出できなかった場合)はNoneを返す。
    この場合の聞き直し文言設計は本関数の範囲外(intent-to-flow-mapping.mdの残課題として残す)。
    """
    date_range = output.get("requested_date_range")
    if not date_range:
        return None
    from datetime import date as _date

    start = _date.fromisoformat(date_range["start"])
    end = _date.fromisoformat(date_range["end"])
    end = min(end, start + timedelta(days=MAX_SEARCH_RANGE_DAYS))
    time_of_day_preference = output.get("time_of_day_preference") or "none"
    return searcher.find_candidates(
        store_id=store_id,
        date_range=(start, end),
        time_of_day_preference=time_of_day_preference,
        menu_duration_minutes=menu_duration_minutes,
        booking_slots=booking_slots,
        now=now,
        max_candidates=max_candidates,
    )


# ---------------------------------------------------------------------------
# 8. candidate-presentation-and-selection-design.md: 候補一覧の採番提示文言と、
#    顧客の返信(番号/自然文)からslot_keyを1件特定する処理。
#    誤爆(意図しない枠の確定)を避けるため、番号指定であることが明確なパターンのみを
#    数字として解釈し、それ以外は日付・時刻文字列の突き合わせに委ね、
#    どちらも特定できなければNoneを返して再確認文言に差し戻す(安全側)。
# ---------------------------------------------------------------------------

_KANJI_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}
_CIRCLED_DIGITS = {"①": 1, "②": 2, "③": 3, "④": 4, "⑤": 5}


def format_candidates_message(candidates: list) -> str:
    """候補一覧を番号付きで提示する文言を生成する(candidate-presentation-and-selection-design.md 1節)。"""
    lines = ["ご希望に近い空き枠はこちらです。番号でお知らせください。", ""]
    lines.extend(f"{i}. {c.label}" for i, c in enumerate(candidates, start=1))
    return "\n".join(lines)


def format_reconfirm_message(candidates: list) -> str:
    """resolve_candidate_selection()が特定不能だった場合の再確認文言を生成する(同3節)。"""
    lines = ["申し訳ございません、番号でお知らせいただけますか?", ""]
    lines.extend(f"{i}. {c.label}" for i, c in enumerate(candidates, start=1))
    return "\n".join(lines)


_SINGLE_CANDIDATE_AFFIRMATION_PHRASES = (
    "それで", "そので", "その時間で", "その日で", "その枠で", "そこで",
)
_SINGLE_CANDIDATE_NEGATION_MARKERS = (
    "ない", "無理", "難しい", "けど", "が、", "別", "他の", "違う", "だめ", "駄目",
)


def _is_single_candidate_affirmation(normalized_reply: str) -> bool:
    """候補が1件だけ提示された状態での指示語のみの返信(「その時間でお願いします」等)を
    肯定表現として検出する。候補presentation-and-selection-design.md 2節「今後の課題」・
    line-reservation-ai/multi-turn-scenario-harness-design.mdの発見への対応。
    候補が1件しかないため誤確定しても他の枠と取り違えるリスクは無いが、
    「その日は無理です」のような否定表現までは肯定と誤認しないよう、代表的な
    否定語が同時に含まれる場合は対象外とする(安全側)。
    """
    if not any(phrase in normalized_reply for phrase in _SINGLE_CANDIDATE_AFFIRMATION_PHRASES):
        return False
    return not any(marker in normalized_reply for marker in _SINGLE_CANDIDATE_NEGATION_MARKERS)


def resolve_candidate_selection(reply_text: str, candidates: list) -> Optional[tuple]:
    """顧客の返信からcandidatesのうち1件のslot_keyを特定する。特定できなければNone
    (呼び出し側はformat_reconfirm_message()の送信を想定)。判定優先順位は
    candidate-presentation-and-selection-design.md 2節を参照。
    """
    import re
    import unicodedata

    normalized = unicodedata.normalize("NFKC", reply_text)

    number = None
    for kanji, val in _KANJI_DIGITS.items():
        if kanji in reply_text:
            number = val
            break
    if number is None:
        for circled, val in _CIRCLED_DIGITS.items():
            if circled in reply_text:
                number = val
                break
    if number is None:
        m = re.search(r"(\d+)\s*番目?", normalized)
        if m:
            number = int(m.group(1))
    if number is None:
        stripped = normalized.strip(" 　.。、,")
        if stripped.isdigit():
            number = int(stripped)

    if number is not None and 1 <= number <= len(candidates):
        return candidates[number - 1].slot_key

    matched = [c for c in candidates if _label_date_and_time_in_reply(c.label, normalized)]
    if len(matched) == 1:
        return matched[0].slot_key

    if len(candidates) == 1 and _is_single_candidate_affirmation(normalized):
        return candidates[0].slot_key

    return None


def _label_date_and_time_in_reply(label: str, normalized_reply: str) -> bool:
    date_part, _, time_part = label.partition(" ")
    date_part = date_part.partition("(")[0]  # "8/9(土)" -> "8/9"。曜日抜きの返信でも一致させる
    time_part = time_part.rstrip("〜")
    return bool(date_part) and bool(time_part) and date_part in normalized_reply and time_part in normalized_reply


# ---------------------------------------------------------------------------
# 9. message-tone-variants.md: メッセージトーン(フォーマル/standard/カジュアル)の
#    出し分けを、LLM出力起点(仮押さえ直後・確定・FAQ回答)とスケジューラ発火起点
#    (前日リマインド、対応するJSON出力を経由しない)の両方の生成経路で共通利用できる
#    関数として実装できるかを検討した結果(README.md「次にやること」対応)。
#    各メッセージ関数は3トーン分の完成文言を保持し、_render_by_tone()という
#    単一のディスパッチャを経由する設計とした。前日リマインドはLLM構造化出力を
#    経由しないため関数の入力(引数)は他と異なるが、トーン適用の最終段は
#    全メッセージ関数で共通化できることを確認した。
# ---------------------------------------------------------------------------

MESSAGE_TONES = ("formal", "standard", "casual")


def _render_by_tone(tone: str, variants: dict) -> str:
    """3トーン分の完成文言({"formal": ..., "standard": ..., "casual": ...})から
    指定トーンの文言を返す共通ディスパッチャ。未知のtone値はstandardにフォールバックする(安全側)。
    """
    return variants.get(tone, variants["standard"])


def format_confirmation_message(candidate_label: str, menu: str, customer_name: str,
                                 tone: str = "standard", emoji_allowed: bool = True) -> str:
    """予約確定メッセージ(LLM出力起点、confirm成功時に送信。message-tone-variants.md準拠)。

    emoji_allowedはcasualトーンの絵文字頻度上限用(同ファイル「絵文字頻度上限」節参照)。
    呼び出し側がConversationFlowStateMachine.consume_casual_emoji_allowance()の戻り値を渡す想定で、
    未指定時(デフォルトTrue)は従来通り常に絵文字を出す。
    """
    emoji = "🙌" if emoji_allowed else ""
    variants = {
        "formal": (
            f"当店: ご予約を確定いたしました。\n"
            f"    {candidate_label} {menu} / {customer_name}様\n"
            f"    前日にご案内のご連絡を差し上げますので、当日はお気をつけてお越しくださいませ。"
        ),
        "standard": (
            f"当店: ご予約を確定いたしました。\n"
            f"    {candidate_label} {menu} / {customer_name}様\n"
            f"    前日にリマインドをお送りしますので、当日お待ちしております!"
        ),
        "casual": (
            f"当店: ご予約確定しました{emoji}\n"
            f"    {candidate_label} {menu} / {customer_name}様\n"
            f"    前日にリマインドしますね、当日お待ちしてます!"
        ),
    }
    return _render_by_tone(tone, variants)


def format_first_booking_self_check_message(candidate_label: str, menu: str, customer_name: str) -> str:
    """first-booking-self-check-notification-design.md準拠。店舗全体で最初の予約確定の直後にのみ
    オーナーへ送る一回限りのセルフチェック促し通知。escalation-notification-templates.mdの
    「主語は店ではなくシステム管理側」ルールに従いオーナー向け固定文面とし(顧客向けのような
    トーン別出し分けは行わない)、onboarding-guide.mdのステップ4(接続テスト・試験会話)を
    省略して本番投入した店舗のフォールバックとして、実際の確定内容を店舗設定と見比べる
    きっかけを提供する(問題発生の通知ではないためEscalationConsolidator/
    NotificationLogAggregatorは経由しない)。
    """
    return (
        "【ご確認のお願い】AIが最初のご予約確定を処理しました。\n"
        f"    {candidate_label} {menu} / {customer_name}様\n"
        "    営業時間・メニュー内容・所要時間などの店舗設定が意図通りかを、"
        "この機会に一度ご確認ください。\n"
        "    問題がなければ今後この通知はありません。"
    )


def format_reminder_message(candidate_label: str, menu: str, tone: str = "standard") -> str:
    """前日リマインド(スケジューラ発火起点。LLM構造化出力を経由しない点が他と異なるが、
    format_confirmation_message()と同じ_render_by_tone()を経由することで
    トーン適用ロジック自体は共通化している)。
    """
    variants = {
        "formal": (
            f"当店: 【リマインド】明日 {candidate_label} {menu}のご予約を承っております。\n"
            f"    ご都合が変わりました場合は、このトークにご返信くださいませ。キャンセル・変更を承ります。"
        ),
        "standard": (
            f"当店: 【リマインド】明日 {candidate_label} {menu}のご予約です。\n"
            f"    ご都合が変わった場合は、このトークにご返信いただければキャンセル・変更を承ります。"
        ),
        "casual": (
            f"当店: 【リマインド】明日 {candidate_label} {menu}のご予約です🙌\n"
            f"    予定変わったら、このトークに返信でキャンセル・変更できますよ!"
        ),
    }
    return _render_by_tone(tone, variants)


def format_reminder_resend_message(candidate_label: str, menu: str, tone: str = "standard") -> str:
    """当日朝の再送(reminder-timing-and-resend-rules.md ルール2準拠、
    reminder_scheduler.select_due_resends()が対象を判定する)。

    「本日」表記に切り替え、format_reminder_message()より一段簡潔にする点以外は
    _render_by_tone()を経由する共通の組み立て方に揃えた。
    """
    variants = {
        "formal": (
            f"当店: 【本日】{candidate_label} {menu}のご予約をお待ちしております。\n"
            f"    ご都合が変わりました場合は、このトークにご返信くださいませ。"
        ),
        "standard": (
            f"当店: 【本日】{candidate_label} {menu}のご予約をお待ちしております。\n"
            f"    ご都合が変わった場合は、このトークにご返信ください。"
        ),
        "casual": (
            f"当店: 【本日】{candidate_label} {menu}のご予約お待ちしてます🙌\n"
            f"    予定変わったら、このトークに返信でお願いします!"
        ),
    }
    return _render_by_tone(tone, variants)


def format_hold_message(candidate_label: str, menu: str, tone: str = "standard", emoji_allowed: bool = True) -> str:
    """仮押さえ直後の案内(LLM出力起点、pending-timeout-ux.md 1.準拠)。

    emoji_allowedはformat_confirmation_message()と同じ絵文字頻度上限用の引数。
    """
    emoji = "🙏" if emoji_allowed else ""
    variants = {
        "formal": (
            f"{candidate_label} {menu}で仮押さえいたしました。お名前を教えていただけますでしょうか。"
            f"(5分以内にご返信くださいますよう、お願い申し上げます)"
        ),
        "standard": (
            f"{candidate_label} {menu}で仮押さえいたしました。お名前を教えていただけますか?"
            f"(5分以内にご返信いただけますと確実にご予約いただけます)"
        ),
        "casual": (
            f"{candidate_label} {menu}で仮押さえしました!お名前教えてください(5分以内にお願いします{emoji})"
        ),
    }
    return _render_by_tone(tone, variants)


def label_from_slot_key(slot_key: tuple) -> str:
    """slot_key(store_id, date_iso, "HH:MM")から、AvailabilitySearcherの候補ラベルと同じ書式
    ("8/9(土) 15:30〜")を組み立てる。cancel_booking()はキャンセル時点で候補一覧・held_labelの
    キャッシュを保持していないため、slot_keyから決定的に再構築する(cancel-intent-handling-design.md準拠)。
    """
    _, date_iso, time_str = slot_key
    day = date.fromisoformat(date_iso)
    return f"{day.month}/{day.day}({_WEEKDAY_JA[day.weekday()]}) {time_str}〜"


def format_cancel_confirmed_message(candidate_label: str, menu: str, tone: str = "standard") -> str:
    """確定済み予約のキャンセル受付メッセージ(cancel-intent-handling-design.md準拠)。"""
    variants = {
        "formal": (
            f"当店: {candidate_label} {menu}のご予約、キャンセルを承りました。"
            f"またのご利用を心よりお待ちしております。"
        ),
        "standard": (
            f"当店: {candidate_label} {menu}のご予約、キャンセルを承りました。"
            f"またのご利用をお待ちしております。"
        ),
        "casual": (
            f"当店: {candidate_label} {menu}のご予約、キャンセルしました!またのご利用お待ちしてます🙌"
        ),
    }
    return _render_by_tone(tone, variants)


def format_cancel_pending_message(tone: str = "standard") -> str:
    """候補提示中/仮押さえ中(未確定)の予約手続きの取り消し受付メッセージ。"""
    variants = {
        "formal": "当店: かしこまりました、今回のご予約手続きは中止いたしました。またのご利用をお待ちしております。",
        "standard": "当店: 承知しました、今回のご予約手続きは中止しました。またのご利用をお待ちしております。",
        "casual": "当店: 了解です、今回の予約は無しにしますね!またいつでもどうぞ🙌",
    }
    return _render_by_tone(tone, variants)


def format_cancel_not_found_message(tone: str = "standard") -> str:
    """該当する予約が会話メモリ上に見つからない場合の一次応答(オーナー転送とあわせて使う安全側の文言)。"""
    variants = {
        "formal": "当店: 恐れ入ります、ご予約状況を確認できませんでしたので、担当より改めてご連絡いたします。",
        "standard": "当店: すみません、ご予約状況を確認できなかったので、担当より改めてご連絡します。",
        "casual": "当店: あれ、予約情報が見当たらないので、担当から折り返しますね!",
    }
    return _render_by_tone(tone, variants)


def format_change_started_message(candidate_label: str, menu: str, tone: str = "standard") -> str:
    """変更対象の旧予約(確定済み/仮押さえ中)を解放した直後の案内(change-intent-handling-design.md準拠)。
    この直後に呼び出し側が新しい候補一覧(format_candidates_message())を続けて送信する想定のため、
    「新しい日時をお伺いします」という前振りで終える。
    """
    variants = {
        "formal": (
            f"当店: {candidate_label} {menu}のご予約は一旦取り消しといたしました。"
            f"改めてご希望の日時を承ります。"
        ),
        "standard": (
            f"当店: {candidate_label} {menu}のご予約は一旦取り消しました。"
            f"改めてご希望の日時を教えてください。"
        ),
        "casual": (
            f"当店: {candidate_label} {menu}の予約はいったん無しにしました!"
            f"新しい希望日時、教えてください🙌"
        ),
    }
    return _render_by_tone(tone, variants)


def format_change_not_found_message(tone: str = "standard") -> str:
    """変更対象の予約が会話メモリ上に見つからない場合の一次応答(オーナー転送とあわせて使う安全側の文言)。"""
    variants = {
        "formal": "当店: 恐れ入ります、変更前のご予約状況を確認できませんでしたので、担当より改めてご連絡いたします。",
        "standard": "当店: すみません、変更前のご予約状況を確認できなかったので、担当より改めてご連絡します。",
        "casual": "当店: あれ、変更前の予約情報が見当たらないので、担当から折り返しますね!",
    }
    return _render_by_tone(tone, variants)


def format_faq_parking_message(capacity: str, tone: str = "standard") -> str:
    """FAQ回答テンプレート・駐車場ありのトーン別文例(faq-response-templates.md準拠)。
    capacityが空文字の場合は台数未入力の登録パターンとして台数表記を省く。
    """
    suffix = f"({capacity}台分)" if capacity else ""
    variants = {
        "formal": f"当店: 駐車場をご用意いたしております{suffix}。",
        "standard": f"当店: 駐車場がございます{suffix}。",
        "casual": f"当店: 駐車場ありますよ{suffix}!",
    }
    return _render_by_tone(tone, variants)


def format_faq_address_message(address_text: str, tone: str = "standard") -> str:
    """FAQ回答テンプレート・住所/アクセスのトーン別文例(faq-response-templates.md準拠)。
    登録された住所・アクセス文言をそのまま挿入するのみで、AI側での言い換えは行わない。
    """
    variants = {
        "formal": f"当店: {address_text}でございます。",
        "standard": f"当店: {address_text}です。",
        "casual": f"当店: {address_text}です!",
    }
    return _render_by_tone(tone, variants)


def format_faq_payment_message(methods: list, tone: str = "standard") -> str:
    """FAQ回答テンプレート・支払い方法のトーン別文例(faq-response-templates.md準拠)。
    チェック済みの項目のみをカンマ区切り(読点)で列挙する。
    """
    joined = "、".join(methods)
    variants = {
        "formal": f"当店: お支払い方法は{joined}がご利用いただけます。",
        "standard": f"当店: お支払い方法は{joined}がご利用いただけます。",
        "casual": f"当店: お支払いは{joined}が使えます!",
    }
    return _render_by_tone(tone, variants)


def format_faq_hours_message(open_minutes: int, close_minutes: int,
                              closed_weekdays: frozenset = frozenset(),
                              tone: str = "standard") -> str:
    """FAQ回答テンプレート・営業時間のトーン別文例(faq-response-templates.md準拠)。
    登録された開始・終了時刻(分)と定休日をそのまま組み立てるのみで、AI側での言い換えは行わない。
    曜日別営業時間・休憩時間(business-hours-lunch-break.md/weekday-specific-business-hours.md)が
    設定されている店舗は、単一の時間帯では正確に案内できないため、呼び出し側(_render_faq_segment)が
    そもそもstore_faq_infoに"hours"キーを設定しない設計とし、本関数はその判定を行わない
    (hours-other-faq-topic-resolution.md参照)。
    """
    hours_text = f"{open_minutes // 60:02d}:{open_minutes % 60:02d}〜{close_minutes // 60:02d}:{close_minutes % 60:02d}"
    if closed_weekdays:
        closed_text = "・".join(_WEEKDAY_JA[w] for w in sorted(closed_weekdays))
        closed_suffix = f"(定休日: {closed_text}曜)"
    else:
        closed_suffix = "(定休日なし)"
    variants = {
        "formal": f"当店の営業時間は{hours_text}でございます{closed_suffix}。",
        "standard": f"当店の営業時間は{hours_text}です{closed_suffix}。",
        "casual": f"営業時間は{hours_text}です{closed_suffix}!",
    }
    return _render_by_tone(tone, variants)


def format_faq_hours_message_weekly(default_ranges: list, weekday_ranges: dict,
                                     closed_weekdays: frozenset = frozenset(),
                                     tone: str = "standard") -> str:
    """FAQ回答テンプレート・曜日別営業時間+複数区間(昼休憩等)対応版の営業時間案内。
    hours-other-faq-topic-resolution.mdの「決定1」で残課題としていた、曜日別営業時間・
    休憩時間を使う店舗(format_faq_hours_messageの対象外だった「複雑な店舗」)向けの
    自然文生成ロジック。各曜日の登録区間(開始,終了)のペアをそのまま機械的に列挙するのみで、
    AI側での言い換え・推測(「休憩」等の意味付けを含む)は行わない(faq-response-templates.mdの
    基本方針を維持)。同一の区間構成が連続する曜日はまとめて「月〜金」のように範囲表記する。

    default_ranges: 曜日別上書きが無い曜日に使う既定区間 [(開始,終了), ...]。
    weekday_ranges: {weekday(月=0〜日=6): [(開始,終了), ...]} 曜日別の上書き区間
        (AvailabilitySearcherのweekday_business_hoursと同じ形式・正規化済みの値を渡す想定)。
    closed_weekdays: 定休日の曜日集合(date.weekday()準拠)。
    """
    def ranges_for(weekday: int) -> tuple:
        if weekday in closed_weekdays:
            return ()
        return tuple(weekday_ranges.get(weekday, default_ranges))

    per_day = [ranges_for(w) for w in range(7)]

    groups = []
    for w in range(7):
        if groups and groups[-1]["ranges"] == per_day[w] and groups[-1]["end"] == w - 1:
            groups[-1]["end"] = w
        else:
            groups.append({"start": w, "end": w, "ranges": per_day[w]})

    def label(g: dict) -> str:
        if g["start"] == g["end"]:
            return _WEEKDAY_JA[g["start"]]
        return f"{_WEEKDAY_JA[g['start']]}〜{_WEEKDAY_JA[g['end']]}"

    def ranges_text(ranges: tuple) -> str:
        if not ranges:
            return "定休日"
        return "、".join(
            f"{s // 60:02d}:{s % 60:02d}〜{e // 60:02d}:{e % 60:02d}" for s, e in ranges
        )

    body = "、".join(f"{label(g)}: {ranges_text(g['ranges'])}" for g in groups)

    variants = {
        "formal": f"当店の営業時間は{body}でございます。",
        "standard": f"当店の営業時間は{body}です。",
        "casual": f"営業時間は{body}です!",
    }
    return _render_by_tone(tone, variants)


def format_faq_unregistered_message(tone: str = "standard") -> str:
    """厳守事項6のエスカレーション時の保留文言(faq-response-templates.mdの
    「未登録・一部未入力のケース(共通)」準拠)。faq_segmentsのresolved:falseの項目、
    および intent: "escalation" 全般(医療・料金交渉・クレーム・未実装機能問い合わせ等)の
    顧客向け一次応答として共通利用する。
    """
    variants = {
        "formal": "当店: 恐れ入ります、その点は担当者に確認のうえ改めてご案内いたします。",
        "standard": "当店: 恐れ入ります、その点は担当者に確認のうえ改めてご案内いたします。",
        "casual": "当店: すみません、そこは担当に確認して改めてご案内します!",
    }
    return _render_by_tone(tone, variants)


# ---------------------------------------------------------------------------
# デモ: 上記9コンポーネントを1本のパイプラインとして通しで動かす
# ---------------------------------------------------------------------------

def _demo() -> None:
    from datetime import datetime as dt

    consolidator = EscalationConsolidator()
    logs = NotificationLogAggregator()

    t0 = dt(2026, 7, 31, 10, 0, 0)
    # 同一顧客(佐藤さん)が3分間隔で3回エスカレーションを起こすシナリオ
    # (escalation-consolidation-logic.mdの「ウィンドウ内追加分はまとめ通知」を再現)
    scenario = [
        ("user_sato", {"intent": "escalation", "needs_owner_check": True,
                        "escalation_reason": None}, t0),
        ("user_sato", {"intent": "escalation", "needs_owner_check": True,
                        "escalation_reason": None}, t0 + timedelta(minutes=2)),
        ("user_sato", {"intent": "escalation", "needs_owner_check": True,
                        "escalation_reason": "unimplemented_feature",
                        "feature_hint": "デポジット決済"}, t0 + timedelta(minutes=4)),
        # 未解決FAQ(駐車場)を含む応答。同日中の再質問は重複カウントしない。
        ("user_tanaka", {"intent": "faq", "needs_owner_check": True,
                          "faq_segments": [{"topic": "parking", "resolved": False}]}, t0),
        ("user_tanaka", {"intent": "faq", "needs_owner_check": True,
                          "faq_segments": [{"topic": "parking", "resolved": False}]},
         t0 + timedelta(hours=1)),
        # システム内部イベント(確定操作の競合)。一般相談(consultation_count)とは別枠で集計されることを示す。
        ("user_watanabe", {"intent": "escalation", "needs_owner_check": True,
                            "escalation_reason": "booking_conflict"}, t0 + timedelta(hours=2)),
    ]

    print("=== EscalationConsolidator / NotificationLogAggregator デモ ===")
    for user_id, event, now in scenario:
        actions = consolidator.on_event(user_id, event, now)
        logs.record(user_id, event, now)
        for kind, payload in actions:
            print(f"[{now.time()}] {user_id}: {kind} 通知 -> {payload}")

    flushed = consolidator.flush_due_windows(t0 + timedelta(minutes=6))
    for user_id, queued in flushed:
        print(f"[まとめ通知] {user_id}: {len(queued)}件をまとめて通知 -> {queued}")

    print()
    print(f"未解決FAQのユニークトピック数(日次×userId×topic): {logs.unique_unresolved_topic_count()}")
    print(f"未実装機能問い合わせ件数: {logs.unimplemented_feature_count}")
    print(f"一般相談エスカレーション件数: {logs.consultation_count}")
    print(f"システム内部イベント件数(理由別): {logs.system_event_counts} (合計{logs.system_event_total()}件)")

    print()
    print("=== RetryFallbackProcessor デモ(1回目失敗→2回目成功、全件フォールバック) ===")

    # ケースA: 1回目はスキーマ不一致(必須フィールド欠落)、2回目で正常な出力が返るモック
    attempts_a = iter([
        {"intent": "new_booking"},  # 必須フィールド不足 → NG
        {"intent": "new_booking", "name": "田中", "menu": "カット",
         "datetime_candidate": "来週土曜15時台の候補", "confirmed": False,
         "needs_owner_check": False},
    ])
    result_a = process_llm_output(lambda: next(attempts_a))
    print(f"ケースA: used_fallback={result_a.used_fallback}, retry_count={result_a.retry_count}")

    # ケースB: 2回とも壊れた出力 → 安全側フォールバック
    attempts_b = iter([
        {"intent": "unknown_intent"},  # enum不一致
        {"intent": "unknown_intent"},
    ])
    result_b = process_llm_output(lambda: next(attempts_b))
    print(f"ケースB: used_fallback={result_b.used_fallback}, output={result_b.output}")

    print()
    print("=== BookingSlotManager デモ(仮押さえ→確定、タイムアウト解放、競合) ===")

    slots = BookingSlotManager()
    slot_89_1530 = ("shop_1", "2026-08-09", "15:30")

    # 田中さんが先に仮押さえ → 成功
    print(f"田中さんhold: {slots.hold(slot_89_1530, 'user_tanaka', t0)}")
    # 直後に鈴木さんが同じ枠をhold → 失敗(競合、別の空き枠再提示が必要)
    print(f"鈴木さんhold(競合): {slots.hold(slot_89_1530, 'user_suzuki', t0 + timedelta(minutes=1))}")
    # 田中さん、氏名確認が3分で完了しconfirm → 成功
    print(f"田中さんconfirm: {slots.confirm(slot_89_1530, 'user_tanaka', t0 + timedelta(minutes=3))}")

    slot_89_1700 = ("shop_1", "2026-08-09", "17:00")
    # 佐藤さんが仮押さえしたまま7分間放置(タイムアウト5分超過)
    print(f"佐藤さんhold: {slots.hold(slot_89_1700, 'user_sato', t0)}")
    print(f"7分後のstatus(タイムアウト解放済み): {slots.status(slot_89_1700, t0 + timedelta(minutes=7))}")
    # タイムアウト後は他の顧客が同じ枠をholdできる
    print(f"高橋さんhold(タイムアウト後の再提示): "
          f"{slots.hold(slot_89_1700, 'user_takahashi', t0 + timedelta(minutes=7))}")
    # 佐藤さんが放置後に確定しようとしても失敗する(安全側)
    print(f"佐藤さんconfirm(タイムアウト後、失敗想定): "
          f"{slots.confirm(slot_89_1700, 'user_sato', t0 + timedelta(minutes=8))}")

    print()
    print("=== ConversationFlowStateMachine デモ(候補提示→確定の接続、確定競合時のリカバリー) ===")

    flow_slots = BookingSlotManager()
    flow_consolidator = EscalationConsolidator()
    flow = ConversationFlowStateMachine(flow_slots, flow_consolidator)

    # 正常系: 田中さんが候補提示→枠選択→氏名・メニュー確定まで進み、確定に成功する
    slot_89_1400 = ("shop_1", "2026-08-09", "14:00")
    flow.present_candidates("user_tanaka", now=t0)
    print(f"田中さん枠選択: {flow.select_slot('user_tanaka', slot_89_1400, t0)}")
    print(f"田中さん詳細確定: "
          f"{flow.provide_details('user_tanaka', '田中', 'カット', t0 + timedelta(minutes=2))}")
    print(f"田中さんの状態: {flow.stage('user_tanaka')}")

    # select_slot()自体の競合系: 山田さんが、田中さんが確定済みの枠を選ぼうとして失敗する。
    # pending-timeout-ux.mdの文言案4を接続した案内メッセージが返る(呼び出し側はそのまま送信可能)。
    flow.present_candidates("user_yamada", now=t0 + timedelta(minutes=1))
    yamada_select = flow.select_slot(
        "user_yamada",
        slot_89_1400,
        t0 + timedelta(minutes=1),
        slot_label="8/9(土) 14:00〜",
        alt_candidates="8/9(土) 17:00 / 8/10(日) 14:00",
    )
    print(f"山田さん枠選択(田中さん確定済み枠、失敗想定): {yamada_select}")
    print(f"山田さんの状態(候補提示のまま): {flow.stage('user_yamada')}")

    # 競合系: 佐藤さんが枠を選択(hold)したまま7分放置しタイムアウト、その間に高橋さんが
    # 同じ枠を選択→確定まで完了させてしまう。佐藤さんがタイムアウトに気づかず遅れて
    # 氏名・メニューを送ってきてもconfirm()は失敗し、候補再提示+オーナー通知に切り替わる。
    slot_89_1600 = ("shop_1", "2026-08-09", "16:00")
    flow.present_candidates("user_sato", now=t0)
    print(f"佐藤さん枠選択: {flow.select_slot('user_sato', slot_89_1600, t0)}")

    flow.present_candidates("user_takahashi", now=t0 + timedelta(minutes=7))
    takahashi_select = flow.select_slot(
        "user_takahashi", slot_89_1600, t0 + timedelta(minutes=7)
    )
    print(f"高橋さん枠選択(佐藤さんタイムアウト後、同じ枠を再提示): {takahashi_select}")
    print(f"高橋さん詳細確定: "
          f"{flow.provide_details('user_takahashi', '高橋', 'カラー', t0 + timedelta(minutes=8))}")

    print(f"佐藤さん詳細確定(枠は既に高橋さんに確定済み、失敗+オーナー通知想定): "
          f"{flow.provide_details('user_sato', '佐藤', 'パーマ', t0 + timedelta(minutes=9))}")
    print(f"佐藤さんの状態(candidates_presentedへ差し戻し): {flow.stage('user_sato')}")
    print(f"高橋さんの予約は維持されているか: {flow_slots.status(slot_89_1600, t0 + timedelta(minutes=9))}")

    print()
    print("=== AvailabilitySearcher デモ(営業時間・所要時間・既存予約との突き合わせ) ===")

    from datetime import date

    searcher = AvailabilitySearcher(business_hours=(9 * 60, 19 * 60))  # 9:00-19:00
    search_slots = BookingSlotManager()
    # 8/9 15:30は既に確定済み(ふさがっている)という前提を用意
    search_slots.hold(("shop_1", "2026-08-09", "15:30"), "user_existing", t0)
    search_slots.confirm(("shop_1", "2026-08-09", "15:30"), "user_existing", t0)

    found = searcher.find_candidates(
        store_id="shop_1",
        date_range=(date(2026, 8, 9), date(2026, 8, 10)),
        time_of_day_preference="afternoon",
        menu_duration_minutes=60,
        booking_slots=search_slots,
        now=t0,
        max_candidates=3,
    )
    print("「来週土曜のお昼くらい」(afternoon, 8/9-8/10, 60分メニュー)の空き枠候補:")
    for c in found:
        print(f"  {c.label} -> slot_key={c.slot_key}")
    assert all(c.slot_key != ("shop_1", "2026-08-09", "15:30") for c in found), (
        "確定済み枠が候補に混入してはならない"
    )

    print()
    print("=== AvailabilitySearcher デモ(定休日を除外) ===")

    # 8/9(日)を定休日に設定した店舗(owner-settings-wireframe.mdの営業曜日チェックボックス相当)
    sunday_closed_searcher = AvailabilitySearcher(
        business_hours=(9 * 60, 19 * 60), closed_weekdays=frozenset({6})  # 6=日曜
    )
    closed_day_slots = BookingSlotManager()
    found_skipping_closed = sunday_closed_searcher.find_candidates(
        store_id="shop_1",
        date_range=(date(2026, 8, 9), date(2026, 8, 10)),  # 8/9(日)定休日〜8/10(月)
        time_of_day_preference="afternoon",
        menu_duration_minutes=60,
        booking_slots=closed_day_slots,
        now=t0,
        max_candidates=3,
    )
    print("8/9(日)を定休日とした場合の空き枠候補(日曜が除外されているか):")
    for c in found_skipping_closed:
        print(f"  {c.label} -> slot_key={c.slot_key}")
    assert all(c.slot_key[1] != "2026-08-09" for c in found_skipping_closed), (
        "定休日(日曜)の枠が候補に混入してはならない"
    )

    print()
    print("=== AvailabilitySearcher デモ(曜日別営業時間: 土曜のみ短縮営業) ===")

    # 平日9:00-19:00、土曜のみ10:00-15:00の短縮営業(owner-settings-wireframe.mdの
    # 曜日別営業時間トグルON時の入力例に相当)
    saturday_short_searcher = AvailabilitySearcher(
        business_hours=(9 * 60, 19 * 60),
        weekday_business_hours={5: (10 * 60, 15 * 60)},  # 5=土曜
    )
    saturday_slots = BookingSlotManager()
    found_saturday_short = saturday_short_searcher.find_candidates(
        store_id="shop_1",
        date_range=(date(2026, 8, 8), date(2026, 8, 8)),  # 2026-08-08は土曜
        time_of_day_preference="evening",  # 平日なら18時台まで探すはずの希望
        menu_duration_minutes=60,
        booking_slots=saturday_slots,
        now=t0,
        max_candidates=5,
    )
    print("土曜(短縮営業10:00-15:00)にevening(本来18時台〜)希望を出した場合の候補(0件のはず):")
    for c in found_saturday_short:
        print(f"  {c.label} -> slot_key={c.slot_key}")
    assert found_saturday_short == [], "短縮営業時間外のevening希望では候補が出てはならない"

    found_saturday_none_pref = saturday_short_searcher.find_candidates(
        store_id="shop_1",
        date_range=(date(2026, 8, 8), date(2026, 8, 8)),
        time_of_day_preference=None,  # 時間帯希望なし→その日の営業時間全体(10:00-15:00)から検索
        menu_duration_minutes=60,
        booking_slots=saturday_slots,
        now=t0,
        max_candidates=5,
    )
    print("同じ土曜、時間帯希望なしの場合の候補(10:00-15:00の範囲内が出るはず):")
    for c in found_saturday_none_pref:
        print(f"  {c.label} -> slot_key={c.slot_key}")
    assert all(
        10 * 60 <= c.start_minutes and c.start_minutes + 60 <= 15 * 60
        for c in found_saturday_none_pref
    ), "土曜の短縮営業時間(10:00-15:00)を超える枠が候補に混入してはならない"

    print()
    print("=== AvailabilitySearcher デモ(昼休憩を挟む複数営業時間帯: 9:00-12:00, 15:00-19:00) ===")

    # business-hours-lunch-break.md: business_hoursに区間リストを渡すと昼休憩を除外して検索する。
    lunch_break_searcher = AvailabilitySearcher(
        business_hours=[(9 * 60, 12 * 60), (15 * 60, 19 * 60)],
    )
    lunch_break_slots = BookingSlotManager()
    found_lunch_break = lunch_break_searcher.find_candidates(
        store_id="shop_1",
        date_range=(date(2026, 8, 10), date(2026, 8, 10)),  # 2026-08-10は月曜
        time_of_day_preference=None,
        menu_duration_minutes=60,
        booking_slots=lunch_break_slots,
        now=t0,
        max_candidates=20,
    )
    print("昼休憩(12:00-15:00)を挟む店舗、時間帯希望なしの候補一覧:")
    for c in found_lunch_break:
        print(f"  {c.label} -> slot_key={c.slot_key}")
    assert all(
        not (12 * 60 <= c.start_minutes < 15 * 60) for c in found_lunch_break
    ), "昼休憩時間帯(12:00-15:00)に開始する枠が候補に混入してはならない"
    assert any(c.start_minutes == 11 * 60 for c in found_lunch_break), (
        "午前区間の最終候補(11:00開始、60分メニューで12:00終了ちょうど)が含まれるはず"
    )
    assert any(c.start_minutes == 15 * 60 for c in found_lunch_break), (
        "午後区間の先頭候補(15:00開始)が含まれるはず"
    )

    found_lunch_break_afternoon = lunch_break_searcher.find_candidates(
        store_id="shop_1",
        date_range=(date(2026, 8, 10), date(2026, 8, 10)),
        time_of_day_preference="afternoon",  # 12:00-17:00希望だが、昼休憩と重なる12:00-15:00は営業時間外
        menu_duration_minutes=60,
        booking_slots=lunch_break_slots,
        now=t0,
        max_candidates=20,
    )
    print("同じ店舗、afternoon(12:00-17:00)希望の候補一覧(15:00-17:00の範囲のみ出るはず):")
    for c in found_lunch_break_afternoon:
        print(f"  {c.label} -> slot_key={c.slot_key}")
    assert all(
        15 * 60 <= c.start_minutes and c.start_minutes + 60 <= 17 * 60
        for c in found_lunch_break_afternoon
    ), "afternoon希望でも、昼休憩と重ならない15:00-17:00の範囲外の枠が混入してはならない"

    print()
    print("=== AvailabilitySearcher デモ(区間の重複・逆転バリデーション) ===")

    try:
        AvailabilitySearcher(business_hours=[(9 * 60, 15 * 60), (12 * 60, 19 * 60)])
    except BusinessHoursConfigError as exc:
        print(f"  重複区間(9:00-15:00, 12:00-19:00)を拒否: {exc}")
    else:
        raise AssertionError("重複する区間はBusinessHoursConfigErrorになるはず")

    try:
        AvailabilitySearcher(business_hours=(15 * 60, 9 * 60))
    except BusinessHoursConfigError as exc:
        print(f"  逆転区間(15:00-9:00)を拒否: {exc}")
    else:
        raise AssertionError("開始>=終了の区間はBusinessHoursConfigErrorになるはず")

    try:
        AvailabilitySearcher(
            business_hours=(9 * 60, 19 * 60),
            weekday_business_hours={5: [(9 * 60, 12 * 60), (12 * 60, 15 * 60)]},
        )
    except BusinessHoursConfigError:
        raise AssertionError("隣接するだけ(重複なし)の区間は許可されるはず")

    try:
        AvailabilitySearcher(
            business_hours=(9 * 60, 19 * 60),
            weekday_business_hours={5: (10 * 60, 10 * 60)},
        )
    except BusinessHoursConfigError as exc:
        print(f"  曜日別営業時間を0分間(定休日相当)にする設定を拒否: {exc}")
    else:
        raise AssertionError(
            "weekday_business_hoursの0分間区間(開始=終了)もBusinessHoursConfigErrorになるはず"
            "(weekday-specific-business-hours.mdの残課題: closed_weekdaysとの二重表現)"
        )

    print()
    print("=== search_candidates_from_llm_output デモ(LLM構造化出力→検索→候補提示→枠選択) ===")

    # 「来週土曜のお昼くらいでカット」に相当するLLM構造化出力(スタブ)。
    llm_output_new_booking = {
        "intent": "new_booking",
        "name": None,
        "menu": "カット",
        "datetime_candidate": "来週土曜のお昼くらい",
        "confirmed": False,
        "needs_owner_check": False,
        "requested_date_range": {"start": "2026-08-09", "end": "2026-08-09"},
        "time_of_day_preference": "afternoon",
    }
    e2e_slots = BookingSlotManager()
    e2e_consolidator = EscalationConsolidator()
    e2e_flow = ConversationFlowStateMachine(e2e_slots, e2e_consolidator)

    e2e_candidates = search_candidates_from_llm_output(
        searcher=searcher,
        booking_slots=e2e_slots,
        store_id="shop_1",
        output=llm_output_new_booking,
        menu_duration_minutes=60,
        now=t0,
    )
    print(f"検索結果: {[c.label for c in e2e_candidates]}")

    e2e_flow.present_candidates("user_ito", now=t0)
    chosen = e2e_candidates[0]
    print(f"伊藤さん枠選択({chosen.label}): "
          f"{e2e_flow.select_slot('user_ito', chosen.slot_key, t0)}")

    # requested_date_rangeが無い(LLMが日付の手がかりを抽出できなかった)場合はNoneが返る
    # (聞き直し文言の設計は残課題、intent-to-flow-mapping.md参照)。
    no_range_output = {**llm_output_new_booking, "requested_date_range": None}
    print(f"requested_date_range無し: "
          f"{search_candidates_from_llm_output(searcher, e2e_slots, 'shop_1', no_range_output, 60, t0)}")

    print()
    print("=== format_candidates_message / resolve_candidate_selection デモ(番号・自然文からの特定) ===")

    print(format_candidates_message(e2e_candidates))
    print()

    # 番号指定(半角数字のみの返信) → 1番目の候補として確定
    print(f"返信『2』: {resolve_candidate_selection('2', e2e_candidates)}")
    # 「N番目」表記(全角数字)
    print(f"返信『２番目でお願いします』: "
          f"{resolve_candidate_selection('２番目でお願いします', e2e_candidates)}")
    # 漢数字
    print(f"返信『三番でお願いします』: {resolve_candidate_selection('三番でお願いします', e2e_candidates)}")
    # 日付を含むが番号指定ではない自由記述 → 「8」を候補番号と誤爆させず、
    # 日付・時刻の突き合わせで1件に特定できる場合は特定成功
    natural_reply = f"{e2e_candidates[0].label.split()[0]}の{e2e_candidates[0].label.split()[1]}でお願いします"
    print(f"返信『{natural_reply}』(自然文、番号なし): "
          f"{resolve_candidate_selection(natural_reply, e2e_candidates)}")
    # 特定不能な自由記述 → None(呼び出し側は再確認文言を送信)
    print(f"返信『午後がいいです』(特定不能想定): "
          f"{resolve_candidate_selection('午後がいいです', e2e_candidates)}")
    print(format_reconfirm_message(e2e_candidates))

    print()
    print("=== select_slot_from_reply デモ(ConversationFlowStateMachineとの接続) ===")

    # present_candidates()にcandidatesを渡しておくと、以降は顧客の返信テキストを
    # そのままselect_slot_from_reply()に渡すだけでhold()まで完了する。
    reply_flow = ConversationFlowStateMachine(e2e_slots, e2e_consolidator)
    reply_flow.present_candidates("user_suzuki", e2e_candidates, now=t0)
    print(f"鈴木さん枠選択(返信『三番でお願いします』): "
          f"{reply_flow.select_slot_from_reply('user_suzuki', '三番でお願いします', t0)}")

    # 特定不能な返信 → select_slot()は呼ばれず再確認文言が返る。stageはcandidates_presentedのまま。
    reply_flow.present_candidates("user_watanabe", e2e_candidates, now=t0)
    unresolved = reply_flow.select_slot_from_reply("user_watanabe", "午後がいいです", t0)
    print(f"渡辺さん枠選択(返信『午後がいいです』、特定不能想定): success={unresolved.success}")
    print(unresolved.message)
    print(f"渡辺さんの会話ステージ(据え置き確認): {reply_flow.stage('user_watanabe')}")

    print()
    print("=== select_slot_from_reply 再確認ループ上限デモ(RECONFIRM_MAX_ATTEMPTS超でエスカレーション) ===")

    # 特定不能な返信がRECONFIRM_MAX_ATTEMPTS(=2)回続いた後、3回目でエスカレーションに切り替わる。
    reply_flow.present_candidates("user_takahashi_r", e2e_candidates, now=t0)
    for attempt in range(1, 4):
        r = reply_flow.select_slot_from_reply("user_takahashi_r", "午後がいいです", t0)
        print(f"高橋さん{attempt}回目(特定不能想定): success={r.success}, message={r.message!r}")
    print(f"高橋さんの会話ステージ(据え置き確認): {reply_flow.stage('user_takahashi_r')}")

    print()
    print("=== release_idle_conversations デモ(conversation-state-cleanup.md、無応答離脱の失効) ===")

    idle_slots = BookingSlotManager()
    idle_flow = ConversationFlowStateMachine(idle_slots, EscalationConsolidator())

    # 中村さん: 枠を選択(hold成功)したまま、氏名・メニューを送らず離脱する。
    slot_89_1830 = ("shop_1", "2026-08-09", "18:30")
    idle_flow.present_candidates("user_nakamura", now=t0)
    print(f"中村さん枠選択: {idle_flow.select_slot('user_nakamura', slot_89_1830, t0)}")
    print(f"中村さんが選んだ枠の状態(選択直後、pending): "
          f"{idle_slots.status(slot_89_1830, t0)}")
    print(f"中村さんが選んだ枠の状態(6分後、HOLD_TIMEOUT超過で既に自動解放済み): "
          f"{idle_slots.status(slot_89_1830, t0 + timedelta(minutes=6))}")

    # 高橋さん(別人)は正常に確定まで完了させる。CONVERSATION_IDLE_TIMEOUT後も残るはず。
    slot_89_1900 = ("shop_1", "2026-08-09", "19:00")
    idle_flow.present_candidates("user_kobayashi", now=t0)
    idle_flow.select_slot("user_kobayashi", slot_89_1900, t0)
    idle_flow.provide_details("user_kobayashi", "小林", "カット", t0 + timedelta(minutes=2))

    released = idle_flow.release_idle_conversations(t0 + timedelta(minutes=31))
    print(f"31分後にrelease_idle_conversations()で失効した顧客(user_id, stage): {released}")
    print(f"中村さんの会話ステージ(失効後、状態が削除されNoneになる): {idle_flow.stage('user_nakamura')}")
    print(f"中村さんが選んだ枠の状態(release_idle_conversations()のrelease()は無害な冪等呼び出し): "
          f"{idle_slots.status(slot_89_1830, t0 + timedelta(minutes=31))}")
    print(f"小林さんの会話ステージ(confirmed済みは対象外のまま残る): "
          f"{idle_flow.stage('user_kobayashi')}")

    print()
    print("=== candidates-expired-notification-design.md デモ(stage別フィルタの動作確認) ===")

    # 田村さん: candidates_presentedのまま(枠を選ばず)無応答で離脱する。
    expiry_slots = BookingSlotManager()
    expiry_flow = ConversationFlowStateMachine(expiry_slots, EscalationConsolidator())
    expiry_flow.present_candidates("user_tamura", now=t0)
    expiry_released = expiry_flow.release_idle_conversations(t0 + timedelta(minutes=31))
    would_notify = [r.user_id for r in expiry_released if r.stage == "candidates_presented"]
    print(f"31分後の失効結果: {expiry_released}")
    print(f"MVP方針(能動通知は送らない)では、この{would_notify}宛の通知は送信しない。"
          f"将来オプション化した場合に送信対象となるuser_idの絞り込みのみデモ")

    print()
    print("=== archive_completed_conversations デモ(confirmed-state-archival.md、来店日超過後のアーカイブ) ===")

    archive_slots = BookingSlotManager()
    archive_flow = ConversationFlowStateMachine(archive_slots, EscalationConsolidator())

    # 佐藤さん: t0当日(2026-07-31)が来店日のままconfirmed済み。
    slot_today_1600 = ("shop_1", "2026-07-31", "16:00")
    archive_flow.present_candidates("user_sato", now=t0)
    archive_flow.select_slot("user_sato", slot_today_1600, t0)
    archive_flow.provide_details("user_sato", "佐藤", "カラー", t0 + timedelta(minutes=1))

    # 山本さん: 3日後(2026-08-03)が来店日でconfirmed済み。まだ来店日を迎えていない。
    slot_future_1100 = ("shop_1", "2026-08-03", "11:00")
    archive_flow.present_candidates("user_yamamoto", now=t0)
    archive_flow.select_slot("user_yamamoto", slot_future_1100, t0)
    archive_flow.provide_details("user_yamamoto", "山本", "カット", t0 + timedelta(minutes=1))

    # 来店日当日中はまだアーカイブされない(no-show判定・前日リマインド再送等が
    # slot_keyを参照しうるため)。
    same_day_archived = archive_flow.archive_completed_conversations(t0 + timedelta(hours=8))
    print(f"来店日当日(18:00時点)でアーカイブされた顧客(0件のはず): {same_day_archived}")
    print(f"佐藤さんの会話ステージ(当日中はまだ残る): {archive_flow.stage('user_sato')}")

    # 2日後、佐藤さんはARCHIVE_AFTER_VISIT(1日)を超えてアーカイブ対象になる。
    # 山本さんは来店日(3日後)がまだ先のため対象外のまま残る。
    archived = archive_flow.archive_completed_conversations(t0 + timedelta(days=2))
    print(f"来店日の2日後、archive_completed_conversations()によりアーカイブされた顧客: {archived}")
    print(f"佐藤さんの会話ステージ(アーカイブ後、状態が削除されNoneになる): "
          f"{archive_flow.stage('user_sato')}")
    print(f"佐藤さんの予約枠(BookingSlotManager側はconfirmedのまま変更されない、履歴として保持): "
          f"{archive_slots.status(slot_today_1600, t0 + timedelta(days=2))}")
    print(f"山本さんの会話ステージ(来店日がまだ先のため対象外で残る): "
          f"{archive_flow.stage('user_yamamoto')}")

    print()
    print("=== maybe_run_idle_cleanup デモ(idle-conversation-trigger-design.md、Webhook便乗トリガーの間引き) ===")

    trigger_slots = BookingSlotManager()
    trigger_flow = ConversationFlowStateMachine(trigger_slots, EscalationConsolidator())
    trigger_flow.present_candidates("user_endo", now=t0)  # 応答せず放置 → 後で失効対象になる

    # 1回目のWebhook受信(t0)で便乗トリガーを実行。まだ誰も失効していないので空リスト。
    first_run = trigger_flow.maybe_run_idle_cleanup(t0)
    print(f"1回目実行(t0、対象0件): {first_run}")

    # 2回目のWebhook受信がIDLE_CLEANUP_MIN_INTERVAL(5分)未満で連続到着 → 間引かれてNone。
    skipped = trigger_flow.maybe_run_idle_cleanup(t0 + timedelta(minutes=2))
    print(f"2回目実行(2分後、間引き対象のためNoneのはず): {skipped}")
    print(f"遠藤さんの会話ステージ(間引かれてもまだ残る): {trigger_flow.stage('user_endo')}")

    # 31分後のWebhook受信では最小実行間隔を超えているため実行され、遠藤さんが失効する。
    third_run = trigger_flow.maybe_run_idle_cleanup(t0 + timedelta(minutes=31))
    print(f"3回目実行(31分後、遠藤さんが失効): {third_run}")
    print(f"遠藤さんの会話ステージ(失効後): {trigger_flow.stage('user_endo')}")

    print()
    print("=== メッセージトーン共通関数デモ(LLM出力起点 vs スケジューラ発火起点) ===")

    label = "8/9(土) 15:30〜"
    # LLM出力起点(confirm成功時に呼ばれる想定)と、スケジューラ発火起点(前日リマインド)の
    # 2つの異なる生成経路が、同じ_render_by_tone()を経由して一貫したトーンを出力できることを確認する。
    print("[確定メッセージ/フォーマル(LLM出力起点)]")
    print(format_confirmation_message(label, "カット", "田中", tone="formal"))
    print("[前日リマインド/フォーマル(スケジューラ発火起点)]")
    print(format_reminder_message(label, "カット", tone="formal"))
    print("[確定メッセージ/カジュアル(LLM出力起点)]")
    print(format_confirmation_message(label, "カット", "田中", tone="casual"))
    print("[前日リマインド/カジュアル(スケジューラ発火起点)]")
    print(format_reminder_message(label, "カット", tone="casual"))
    print(f"[未知のtone値'loud'はstandardにフォールバック]: {format_faq_parking_message('3', tone='loud')}")

    print()
    print("=== InMemoryBookingRecordStore デモ(予約一覧CSV・顧客詳細ページの取得元配線) ===")

    # record_storeを渡しておくと、provide_details()での確定成功時に自動でrecord_confirmed()が
    # 呼ばれる。これまでformat_booking_list_csv()/build_customer_detail_view()は「既にどこかから
    # 取得済みのデータ」を渡されて動かすデモしか無かったが、確定フロー→ストア→CSV/詳細ビューまで
    # 一気通貫で確認できるようにした。
    record_store = InMemoryBookingRecordStore()
    store_flow = ConversationFlowStateMachine(BookingSlotManager(), EscalationConsolidator(), record_store=record_store)

    for user_id, slot_key, name, menu in [
        ("user_tanaka_r", ("shop_1", "2026-08-10", "11:00"), "田中", "カット"),
        ("user_sato_r", ("shop_1", "2026-08-10", "16:00"), "佐藤", "カラー"),
        ("user_suzuki_r", ("shop_1", "2026-08-11", "13:00"), "鈴木", "カット"),
    ]:
        store_flow.present_candidates(user_id, now=t0)
        store_flow.select_slot(user_id, slot_key, t0)
        store_flow.provide_details(user_id, name, menu, t0)

    week_entries = record_store.list_booking_entries("shop_1", date(2026, 8, 10), date(2026, 8, 16))
    print(f"[予約一覧ページ「今週分をCSVで書き出す」相当、{len(week_entries)}件取得]")
    print(format_booking_list_csv(week_entries))

    tanaka_view = build_customer_detail_view("田中", record_store.customer_records("田中"))
    print(f"[顧客詳細ページ(田中さん)相当]: 累計予約数={tanaka_view.total_bookings}, "
          f"直近の状態={tanaka_view.recent_history[0].status if tanaka_view.recent_history else None}")


if __name__ == "__main__":
    _demo()
