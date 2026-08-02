#!/usr/bin/env python3
"""
webhook-async-processing-design.md / intent-to-flow-mapping.mdで設計した
「Cloud Function B: process_conversation_event」を初めて実行可能なコードに落とし込んだもの。

位置づけ:
- 実LLM呼び出しは、engine.pyのllm_callスタブをそのまま利用する(実API接続は
  pending-approval.md記載のAPIキー・課金承認待ち)。
- LINE Push Message APIの送信も、Cloud Function A(cloud_function_webhook.py)の
  `TaskQueueClient`プロトコルと同じ考え方で`LinePushClient`プロトコルとして
  差し替え可能にした。承認・LINE公式アカウント開設後は`InMemoryLinePushClient`を
  実際のLINE Messaging API SDKのクライアントに差し替えるだけで動作する設計。
- Cloud Tasksから1件デキューされたペイロード(Cloud Function Aがenqueueした
  LINEイベント)を受け取り、intent-to-flow-mapping.mdの対応表に従って
  ConversationFlowStateMachineのメソッドを呼び分ける、というAとBをつなぐ
  「配線」自体がこれまで未着手だったため、その部分を実装した。

実装範囲: intent-to-flow-mapping.mdの対応表のうち new_booking 系の3行
(曖昧な日時→候補提示、候補選択→hold、氏名/メニュー確定→confirm)に加え、
webhook-function-b-implementation.mdの残課題だった(1)escalation/faq intentの
顧客向け返信、(2)確定操作競合時の新しい空き枠の再提示を実装した。
- intent: "faq" かつ `faq_segments` が付与されている場合、faq-response-templates.mdの
  項目別テンプレートに従い項目ごとに1通ずつ送信する(resolved: trueは登録値をそのまま案内、
  resolved: falseは共通の保留文言)。json-schema-multi-intent-extension.mdの
  2026-08-02改訂により、厳守事項9aに基づく回答は複合質問(2項目以上)だけでなく
  単一項目でも`faq_segments`を1要素配列で付与する方針になったため、E10・E14前半のような
  単一項目9aケースも本ルートで自動返信されるようになった(faq-escalation-customer-reply-
  implementation.mdに記載していた「単一項目FAQは自動返信できない」制約は解消)。
- intent: "escalation" の場合、faq-response-templates.mdの「未登録・一部未入力の
  ケース(共通)」の保留文言を一次応答として即時送信する。
- 厳守事項9b(雑談、E6等)のように特定の店舗FAQ項目に基づかない`faq` intentは、
  `faq_segments`が`null`のままとなる設計のため、引き続きオーナーへの転送のみ
  (顧客への自動返信なし)を安全側フォールバックとして維持する。実LLMが
  上記の改訂ルールに従わずtopicなしで単一項目FAQを返した場合も同じ経路で
  安全側に倒れる。
- 確定操作自体が競合した場合(`provide_details()`がFalseを返す、booking-slot-manager-design.md
  参照)、初回の候補提示時に使った検索条件(`requested_date_range`/`time_of_day_preference`/
  メニュー所要時間)を`_search_context_by_user`にキャッシュしておき、`now`時点で再検索して
  新しい空き枠をその場で顧客へ再提示する(奪われた枠は`BookingSlotManager`側で既に
  埋まっているため自然に候補から除外される)。再検索しても候補が0件の場合は従来通り
  謝罪文言のみを送りオーナーの人手対応に委ねる。
- intent: "cancel" の場合、cancel-intent-handling-design.md準拠でConversationFlowStateMachine.
  cancel_booking()を呼び、会話のstage(candidates_presented/awaiting_details/confirmed/状態なし)に
  応じてBookingSlotManager側の枠解放・顧客への返信・オーナー通知(confirmed分のみ)を行う。
  change intentは未実装のまま、EscalationConsolidator/NotificationLogAggregatorへの転送のみを行う
  (change/日時変更の設計はcancel-intent-handling-design.mdの残課題を参照)。

- reminder-scheduler-design.mdの残課題だった「確定後の顧客からの返信検知の配線」を実装した
  (customer-reply-detection-design.md参照)。confirmed状態の会話へメッセージが届いた事実を、
  内容を問わず`ConfirmedReplyRecorder`プロトコル経由で記録する(未指定時は何もしない)。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Protocol

sys.path.insert(0, str(Path(__file__).parent))

from engine import (  # noqa: E402
    AvailabilitySearcher,
    BookingSlotManager,
    ConversationFlowStateMachine,
    EscalationConsolidator,
    NotificationLogAggregator,
    format_candidates_message,
    format_cancel_confirmed_message,
    format_cancel_not_found_message,
    format_cancel_pending_message,
    format_confirmation_message,
    format_faq_address_message,
    format_faq_parking_message,
    format_faq_payment_message,
    format_faq_unregistered_message,
    format_hold_message,
    label_from_slot_key,
    process_llm_output,
    resolve_candidate_selection,
    search_candidates_from_llm_output,
)


# ---------------------------------------------------------------------------
# LINE Push Message APIクライアントのプロトコル(実クライアントとInMemory版の共通インターフェース)
# ---------------------------------------------------------------------------

class LinePushClient(Protocol):
    def send_message(self, user_id: str, text: str) -> None:
        ...


class InMemoryLinePushClient:
    """LINE Messaging APIのpush送信を模した検証用クライアント。
    GCPプロジェクト作成・LINE公式アカウント開設後は、実際のline-bot-sdk等のクライアントに
    差し替えるだけで動作させられる設計。
    """

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send_message(self, user_id: str, text: str) -> None:
        self.sent.append((user_id, text))


class ConfirmedReplyRecorder(Protocol):
    def record(self, user_id: str, now: datetime) -> None:
        ...


class InMemoryConfirmedReplyRecorder:
    """customer-reply-detection-design.md準拠。confirmed状態の会話にメッセージが届いた
    事実を記録する検証用クライアント。実装時はFirestoreのconversationドキュメントの
    `customerRepliedAt`フィールドを`now`で更新する処理に差し替えるだけで動作する設計。
    """

    def __init__(self) -> None:
        self.recorded: list[tuple[str, datetime]] = []

    def record(self, user_id: str, now: datetime) -> None:
        self.recorded.append((user_id, now))


# ---------------------------------------------------------------------------
# 顧客への案内文言(未実装の聞き直しパターン向けの暫定文言)
# ---------------------------------------------------------------------------

REASK_DATE_RANGE_MESSAGE = (
    "当店: ご希望の日時をもう少し詳しく教えていただけますか?"
    "(例:「来週土曜の午後」「8/9の午前中」)"
)
REASK_NAME_MENU_MESSAGE = "当店: お名前とご希望のメニューを教えていただけますか?"
BOOKING_CONFLICT_MESSAGE = (
    "当店: 大変申し訳ございません、ちょうど別のお客様のご予約と重なってしまいました。"
    "担当より改めて空き状況をご案内いたしますので少々お待ちください。"
)
BOOKING_CONFLICT_RETRY_MESSAGE = (
    "当店: 大変申し訳ございません、ちょうど別のお客様のご予約と重なってしまいました。"
    "改めて空いているお時間をご案内しますので、よろしければ番号でお選びください。"
)


@dataclass
class DispatchResult:
    action: str
    # "candidates_presented" | "held" | "confirmed" | "booking_conflict" |
    # "reask" | "forwarded_to_owner" | "cancelled" | "escalation_replied"
    detail: str = ""


def resolve_menu_duration(menu_name: Optional[str], menu_durations: dict) -> Optional[int]:
    """店舗設定のメニュー別所要時間から検索用の分数を引く。未登録メニューはNoneを返し、
    呼び出し側はオーナーへのエスカレーションに倒す(owner-settings-wireframe.mdの
    メニュー登録漏れに相当する状況のため、安全側で人間に引き継ぐ)。
    """
    if not menu_name:
        return None
    return menu_durations.get(menu_name)


class ConversationEventProcessor:
    """Cloud Function Bの本体。1店舗分の会話処理をまとめて保持する。

    user_idごとの会話状態自体はConversationFlowStateMachineが保持するが、
    「直近提示した候補一覧」「holdした枠のラベル」はBが顧客への案内文言(hold時の
    候補ラベル・confirm時の予約内容ラベル)を組み立てるためだけに必要で、
    ConversationFlowStateMachine自体の責務(hold/confirm可否の判定)には不要なため、
    Flow内部状態には追加せずこちらでキャッシュする(実装ではFirestoreの
    会話状態ドキュメントに含める想定、firestore-data-model.md参照)。
    """

    def __init__(
        self,
        *,
        flow: ConversationFlowStateMachine,
        searcher: AvailabilitySearcher,
        booking_slots: BookingSlotManager,
        consolidator: EscalationConsolidator,
        logs: NotificationLogAggregator,
        push_client: LinePushClient,
        store_id: str,
        menu_durations: dict,
        store_faq_info: Optional[dict] = None,
        confirmed_reply_recorder: Optional[ConfirmedReplyRecorder] = None,
    ) -> None:
        self._flow = flow
        self._searcher = searcher
        self._booking_slots = booking_slots
        self._consolidator = consolidator
        self._logs = logs
        self._push = push_client
        self._store_id = store_id
        self._menu_durations = menu_durations
        # customer-reply-detection-design.md準拠。未指定(None)の場合は何もしない。
        self._confirmed_reply_recorder = confirmed_reply_recorder
        # 店舗FAQ情報(owner-settings-wireframe.mdの「店舗FAQ情報」入力欄に対応)。
        # 例: {"address": "○○駅から徒歩5分", "parking": {"available": True, "capacity": "3"},
        #      "payment_methods": ["現金", "クレジットカード"]}
        # 未登録の項目はキー自体を省略してよい(その場合topic該当時もresolved扱いにしない)。
        self._store_faq_info = store_faq_info or {}
        self._candidates_by_user: dict[str, list] = {}
        self._held_label_by_user: dict[str, str] = {}
        # 直近の空き枠検索に使ったLLM出力とメニュー所要時間。確定操作競合時
        # (_represent_candidates_after_conflict)に同じ条件で再検索するために保持する。
        self._search_context_by_user: dict[str, tuple[dict, int]] = {}

    def process(
        self,
        event: dict,
        llm_call: Callable[[], dict],
        now: datetime,
        tone: str = "standard",
    ) -> DispatchResult:
        """Cloud Tasksから1件デキューされたイベント(Cloud Function Aのenqueueペイロード)を処理する。"""
        user_id = event.get("source", {}).get("userId")
        if not user_id:
            raise ValueError("event is missing required field 'source.userId'")
        reply_text = event.get("message", {}).get("text", "")

        # customer-reply-detection-design.md準拠。LLM呼び出し・intent判定より前に、
        # confirmed状態の会話へメッセージが届いた事実そのものを記録する(内容は問わない)。
        # 複数回返信があっても呼ぶたびに最新の時刻で上書きする。
        if self._confirmed_reply_recorder is not None and self._flow.stage(user_id) == "confirmed":
            self._confirmed_reply_recorder.record(user_id, now)

        llm_result = process_llm_output(llm_call)
        output = llm_result.output
        self._logs.record(user_id, output, now)

        intent = output.get("intent")
        if intent == "faq" and output.get("faq_segments"):
            return self._handle_faq(user_id, output, now, tone)
        if intent == "escalation":
            return self._handle_escalation(user_id, output, now, tone)
        if intent == "cancel":
            return self._handle_cancel(user_id, now, tone)
        if intent != "new_booking":
            # intent-to-flow-mapping.md: faq_segments無しのfaq(9b雑談等・レガシー出力)・
            # change・その他は予約フロー外のため ConversationFlowStateMachineは呼ばず、
            # オーナーへの転送のみ行う(単一項目9a FAQがここに落ちない理由は
            # モジュールdocstring「実装範囲」参照。cancelはcancel-intent-handling-design.md準拠で
            # 上記の_handle_cancelへ分岐済みのためここには来ない)。
            self._consolidator.on_event(user_id, output, now)
            return DispatchResult(action="forwarded_to_owner", detail=intent or "unknown")

        stage = self._flow.stage(user_id)
        if stage in (None, "confirmed"):
            return self._start_new_booking(user_id, output, now)
        if stage == "candidates_presented":
            return self._handle_candidate_selection(user_id, reply_text, output, now, tone)
        if stage == "awaiting_details":
            return self._handle_details(user_id, output, now, tone)

        # ここに到達するのはstageがawaiting_details/candidates_presented/confirmed/None
        # のいずれでもない場合で、ConversationFlowStateMachineの実装上通常発生しないが、
        # 安全側でオーナーへ転送する。
        self._consolidator.on_event(user_id, output, now)
        return DispatchResult(action="forwarded_to_owner", detail=f"unexpected_stage:{stage}")

    def _start_new_booking(self, user_id: str, output: dict, now: datetime) -> DispatchResult:
        menu_minutes = resolve_menu_duration(output.get("menu"), self._menu_durations)
        if menu_minutes is None:
            self._consolidator.on_event(
                user_id, {**output, "escalation_reason": "unregistered_menu"}, now
            )
            return DispatchResult(action="forwarded_to_owner", detail="unregistered_menu")

        candidates = search_candidates_from_llm_output(
            self._searcher, self._booking_slots, self._store_id, output, menu_minutes, now
        )
        if not candidates:
            self._push.send_message(user_id, REASK_DATE_RANGE_MESSAGE)
            return DispatchResult(action="reask", detail="no_date_range_or_no_candidates")

        # 確定操作競合時の再検索(_represent_candidates_after_conflict)用に検索条件を保持する。
        self._search_context_by_user[user_id] = (output, menu_minutes)
        self._flow.present_candidates(user_id, candidates, now=now)
        self._candidates_by_user[user_id] = candidates
        self._push.send_message(user_id, format_candidates_message(candidates))
        return DispatchResult(action="candidates_presented", detail=str(len(candidates)))

    def _handle_candidate_selection(
        self, user_id: str, reply_text: str, output: dict, now: datetime, tone: str
    ) -> DispatchResult:
        candidates = self._candidates_by_user.get(user_id, [])
        select_result = self._flow.select_slot_from_reply(user_id, reply_text, now)
        if not select_result.success:
            self._push.send_message(user_id, select_result.message)
            return DispatchResult(action="reask", detail="candidate_selection_pending")

        # select_slot_from_reply()はcandidatesを内部(Flowのprivate state)に保持するのみで
        # 選ばれたslot_keyやlabelを戻り値に含まないため、同じ入力(reply_text, candidates)から
        # 決定的に同じ結果を返すresolve_candidate_selection()をここでも呼び、
        # 案内文言に使うlabelだけを取り出す(副作用はなく、Flow側の判定とは独立)。
        slot_key = resolve_candidate_selection(reply_text, candidates)
        label = next((c.label for c in candidates if c.slot_key == slot_key), "")
        self._held_label_by_user[user_id] = label

        menu = output.get("menu") or ""
        self._push.send_message(user_id, format_hold_message(label, menu, tone))
        return DispatchResult(action="held")

    def _handle_details(self, user_id: str, output: dict, now: datetime, tone: str) -> DispatchResult:
        name, menu = output.get("name"), output.get("menu")
        if not name or not menu:
            self._push.send_message(user_id, REASK_NAME_MENU_MESSAGE)
            return DispatchResult(action="reask", detail="missing_name_or_menu")

        confirmed = self._flow.provide_details(user_id, name, menu, now)
        if not confirmed:
            # provide_details()失敗時はConversationFlowStateMachineが内部で
            # EscalationConsolidator.on_event()を既に呼んでいるため、ここでの二重通知はしない。
            return self._represent_candidates_after_conflict(user_id, now)

        label = self._held_label_by_user.pop(user_id, "")
        self._push.send_message(
            user_id,
            format_confirmation_message(candidate_label=label, menu=menu, customer_name=name, tone=tone),
        )
        return DispatchResult(action="confirmed")

    def _represent_candidates_after_conflict(self, user_id: str, now: datetime) -> DispatchResult:
        """booking-slot-manager-design.mdの今後の課題だった、確定操作競合時の新しい空き枠の
        再提示。初回の候補提示時にキャッシュしておいた検索条件(_search_context_by_user)で
        `now`時点の空き状況を再検索し、奪われた枠を除いた候補をその場で顧客へ提示する
        (`ConversationFlowStateMachine.provide_details()`が既にstageをcandidates_presentedへ
        差し戻しているため、`present_candidates()`で状態を上書きするだけでよい)。
        検索条件が見つからない、または再検索しても候補が0件の場合(混雑等で近日中に空きが無い)は
        従来通り謝罪文言のみを送り、オーナーの人手対応に委ねる。
        """
        context = self._search_context_by_user.get(user_id)
        candidates = None
        if context is not None:
            original_output, menu_minutes = context
            candidates = search_candidates_from_llm_output(
                self._searcher, self._booking_slots, self._store_id, original_output, menu_minutes, now
            )
        if not candidates:
            self._push.send_message(user_id, BOOKING_CONFLICT_MESSAGE)
            return DispatchResult(action="booking_conflict", detail="no_alternative_forwarded_to_owner")

        self._flow.present_candidates(user_id, candidates, now=now)
        self._candidates_by_user[user_id] = candidates
        self._push.send_message(user_id, BOOKING_CONFLICT_RETRY_MESSAGE)
        self._push.send_message(user_id, format_candidates_message(candidates))
        return DispatchResult(action="booking_conflict", detail=f"represented_{len(candidates)}_candidates")

    def _handle_faq(self, user_id: str, output: dict, now: datetime, tone: str) -> DispatchResult:
        """複合FAQ質問(faq_segments、json-schema-multi-intent-extension.md)への顧客向け返信。
        faq-response-templates.mdの「1メッセージ1用件」原則に従い、項目ごとに1通ずつ送信する。
        """
        segments = output["faq_segments"]
        for seg in segments:
            self._push.send_message(user_id, self._render_faq_segment(seg["topic"], seg["resolved"], tone))
        # 通知ログ集計(未解決topicのユニーク集計)・resolved:false項目のオーナー通知は
        # 既存のEscalationConsolidator/NotificationLogAggregatorに委ねる(全体のoutputを渡す)。
        self._consolidator.on_event(user_id, output, now)
        unresolved = sum(1 for seg in segments if not seg["resolved"])
        return DispatchResult(action="faq_replied", detail=f"{len(segments)}_segments_{unresolved}_unresolved")

    def _render_faq_segment(self, topic: str, resolved: bool, tone: str) -> str:
        if not resolved:
            return format_faq_unregistered_message(tone)
        if topic == "parking" and self._store_faq_info.get("parking"):
            return format_faq_parking_message(self._store_faq_info["parking"].get("capacity", ""), tone)
        if topic == "access" and self._store_faq_info.get("address"):
            return format_faq_address_message(self._store_faq_info["address"], tone)
        if topic == "payment" and self._store_faq_info.get("payment_methods"):
            return format_faq_payment_message(self._store_faq_info["payment_methods"], tone)
        # resolved: trueだがstore_faq_infoに該当する登録値が無い(店舗設定と構造化出力の
        # 不整合)場合は、誤った断定回答を避けるため保留文言に安全側フォールバックする。
        return format_faq_unregistered_message(tone)

    def _handle_escalation(self, user_id: str, output: dict, now: datetime, tone: str) -> DispatchResult:
        """厳守事項6(予約以外の相談)・10(未実装機能問い合わせ)発生時の顧客への一次応答。
        faq-response-templates.mdの共通保留文言を即時送信し、詳細な対応はオーナーに委ねる。
        """
        self._push.send_message(user_id, format_faq_unregistered_message(tone))
        self._consolidator.on_event(user_id, output, now)
        return DispatchResult(action="escalation_replied", detail=output.get("escalation_reason") or "consultation")

    def _handle_cancel(self, user_id: str, now: datetime, tone: str) -> DispatchResult:
        """cancel-intent-handling-design.md準拠。intent: "cancel"の一次処理。
        ConversationFlowStateMachine.cancel_booking()にstageに応じたrelease()・オーナー通知
        (confirmed分のみ)を委ね、ここでは顧客への返信文言の出し分けとローカルキャッシュの
        後始末のみを行う。
        """
        result = self._flow.cancel_booking(user_id, now)
        self._candidates_by_user.pop(user_id, None)
        self._held_label_by_user.pop(user_id, None)
        self._search_context_by_user.pop(user_id, None)

        if not result.found:
            # このエンジンの会話メモリだけでは実在の予約有無を確定できないため、安全側でオーナーに転送する
            # (cancel_booking()自身は状態が無い場合オーナー通知を行わないため、ここで行う)。
            self._consolidator.on_event(
                user_id,
                {"intent": "cancel", "needs_owner_check": True, "escalation_reason": "cancel_not_found"},
                now,
            )
            self._push.send_message(user_id, format_cancel_not_found_message(tone))
            return DispatchResult(action="forwarded_to_owner", detail="cancel_not_found")

        if result.stage == "confirmed":
            label = label_from_slot_key(result.slot_key)
            self._push.send_message(
                user_id, format_cancel_confirmed_message(label, result.menu or "", tone)
            )
            return DispatchResult(action="cancelled", detail="confirmed")

        self._push.send_message(user_id, format_cancel_pending_message(tone))
        return DispatchResult(action="cancelled", detail=result.stage)


def _demo() -> None:
    from datetime import date, timedelta

    flow = ConversationFlowStateMachine(BookingSlotManager(), EscalationConsolidator())
    booking_slots = flow._slots  # デモ用に同一インスタンスを共有(本番はDIで渡す)
    searcher = AvailabilitySearcher(business_hours=(9 * 60, 18 * 60), slot_interval_minutes=30)
    consolidator = flow._consolidator
    logs = NotificationLogAggregator()
    push = InMemoryLinePushClient()
    confirmed_replies = InMemoryConfirmedReplyRecorder()
    processor = ConversationEventProcessor(
        flow=flow,
        searcher=searcher,
        booking_slots=booking_slots,
        consolidator=consolidator,
        logs=logs,
        push_client=push,
        confirmed_reply_recorder=confirmed_replies,
        store_id="store-1",
        menu_durations={"カット": 30},
        store_faq_info={
            "address": "○○駅から徒歩5分",
            "parking": {"available": True, "capacity": "3"},
            "payment_methods": ["現金", "クレジットカード"],
        },
    )

    now = datetime(2026, 8, 3, 10, 0)  # 月曜
    event = {"source": {"userId": "U1"}, "message": {"text": "来週土曜カットでお願いします"}}

    def llm_call_1() -> dict:
        return {
            "intent": "new_booking",
            "name": None,
            "menu": "カット",
            "datetime_candidate": "来週土曜の空き候補",
            "confirmed": False,
            "needs_owner_check": False,
            "requested_date_range": {
                "start": (now.date() + timedelta(days=(5 - now.weekday()) % 7 or 7)).isoformat(),
                "end": (now.date() + timedelta(days=(5 - now.weekday()) % 7 or 7)).isoformat(),
            },
        }

    r1 = processor.process(event, llm_call_1, now, tone="standard")
    print(f"1) action={r1.action} detail={r1.detail}")
    print(f"   push: {push.sent[-1][1]}")

    def llm_call_2() -> dict:
        return {
            "intent": "new_booking", "name": None, "menu": "カット",
            "datetime_candidate": "1番目の候補", "confirmed": False, "needs_owner_check": False,
        }

    event2 = {"source": {"userId": "U1"}, "message": {"text": "1番で"}}
    r2 = processor.process(event2, llm_call_2, now, tone="standard")
    print(f"2) action={r2.action} detail={r2.detail}")
    print(f"   push: {push.sent[-1][1]}")

    def llm_call_3() -> dict:
        return {
            "intent": "new_booking", "name": "山田", "menu": "カット",
            "datetime_candidate": "確定", "confirmed": True, "needs_owner_check": False,
        }

    event3 = {"source": {"userId": "U1"}, "message": {"text": "山田です、カットでお願いします"}}
    r3 = processor.process(event3, llm_call_3, now, tone="standard")
    print(f"3) action={r3.action} detail={r3.detail}")
    print(f"   push: {push.sent[-1][1]}")

    # 3b) confirmed後の返信検知(customer-reply-detection-design.md): 前日リマインド後に
    # 顧客から何かしら返信が来たことを、内容を問わずConfirmedReplyRecorderへ記録する。
    def llm_call_3b() -> dict:
        return {
            "intent": "faq", "name": None, "menu": None, "datetime_candidate": None,
            "confirmed": False, "needs_owner_check": False,
            "faq_segments": [{"topic": "parking", "resolved": True}],
        }

    event3b = {"source": {"userId": "U1"}, "message": {"text": "駐車場ありますか"}}
    reminder_reply_time = now + timedelta(days=1, hours=8)
    r3b = processor.process(event3b, llm_call_3b, reminder_reply_time, tone="standard")
    print(f"3b) action={r3b.action} detail={r3b.detail}")
    print(f"    customer_replied_at recorded: {confirmed_replies.recorded}")

    # 4) 複合FAQ(E13b相当): 駐車場は登録済み(resolved: true)、電子マネーは未チェック(resolved: false)
    def llm_call_4() -> dict:
        return {
            "intent": "faq", "name": None, "menu": None, "datetime_candidate": None,
            "confirmed": False, "needs_owner_check": True,
            "faq_segments": [{"topic": "parking", "resolved": True}, {"topic": "payment", "resolved": False}],
        }

    event4 = {"source": {"userId": "U2"}, "message": {"text": "駐車場ある?電子マネーは使える?"}}
    r4 = processor.process(event4, llm_call_4, now, tone="standard")
    print(f"4) action={r4.action} detail={r4.detail}")
    for text in [t for uid, t in push.sent if uid == "U2"]:
        print(f"   push: {text}")

    # 4b) 単一項目FAQ(E10相当、2026-08-02改訂: 単一項目でもfaq_segmentsを1要素配列で付与)
    def llm_call_4b() -> dict:
        return {
            "intent": "faq", "name": None, "menu": None, "datetime_candidate": None,
            "confirmed": False, "needs_owner_check": False,
            "faq_segments": [{"topic": "parking", "resolved": True}],
        }

    event4b = {"source": {"userId": "U4"}, "message": {"text": "駐車場はありますか"}}
    r4b = processor.process(event4b, llm_call_4b, now, tone="standard")
    print(f"4b) action={r4b.action} detail={r4b.detail}")
    print(f"   push: {push.sent[-1][1]}")

    # 5) escalation(厳守事項6、予約以外の相談)
    def llm_call_5() -> dict:
        return {
            "intent": "escalation", "name": None, "menu": None, "datetime_candidate": None,
            "confirmed": False, "needs_owner_check": True,
        }

    event5 = {"source": {"userId": "U3"}, "message": {"text": "施術で肌荒れしたんですが大丈夫でしょうか"}}
    r5 = processor.process(event5, llm_call_5, now, tone="standard")
    print(f"5) action={r5.action} detail={r5.detail}")
    print(f"   push: {push.sent[-1][1]}")


if __name__ == "__main__":
    _demo()
