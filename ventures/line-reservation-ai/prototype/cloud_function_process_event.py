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
(曖昧な日時→候補提示、候補選択→hold、氏名/メニュー確定→confirm)。
escalation/faq/その他の行はEscalationConsolidator/NotificationLogAggregatorへの
転送のみを行い、FAQ本文の組み立て(faq_segments、faq-response-templates.md)との
統合は未実装のまま残す(下記「未実装のまま残るもの」参照)。
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
    format_confirmation_message,
    format_hold_message,
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


@dataclass
class DispatchResult:
    action: str
    # "candidates_presented" | "held" | "confirmed" | "booking_conflict" |
    # "reask" | "forwarded_to_owner"
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
    ) -> None:
        self._flow = flow
        self._searcher = searcher
        self._booking_slots = booking_slots
        self._consolidator = consolidator
        self._logs = logs
        self._push = push_client
        self._store_id = store_id
        self._menu_durations = menu_durations
        self._candidates_by_user: dict[str, list] = {}
        self._held_label_by_user: dict[str, str] = {}

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

        llm_result = process_llm_output(llm_call)
        output = llm_result.output
        self._logs.record(user_id, output, now)

        intent = output.get("intent")
        if intent != "new_booking":
            # intent-to-flow-mapping.md: escalation/faq/その他は予約フロー外のため
            # ConversationFlowStateMachineは呼ばず、オーナーへの転送のみ行う。
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
            # 新しい空き枠の再提示(booking-slot-manager-design.mdの今後の課題)は未実装のため、
            # 当面は案内文言のみを送る。
            self._push.send_message(user_id, BOOKING_CONFLICT_MESSAGE)
            return DispatchResult(action="booking_conflict")

        label = self._held_label_by_user.pop(user_id, "")
        self._push.send_message(
            user_id,
            format_confirmation_message(candidate_label=label, menu=menu, customer_name=name, tone=tone),
        )
        return DispatchResult(action="confirmed")


def _demo() -> None:
    from datetime import date, timedelta

    flow = ConversationFlowStateMachine(BookingSlotManager(), EscalationConsolidator())
    booking_slots = flow._slots  # デモ用に同一インスタンスを共有(本番はDIで渡す)
    searcher = AvailabilitySearcher(business_hours=(9 * 60, 18 * 60), slot_interval_minutes=30)
    consolidator = flow._consolidator
    logs = NotificationLogAggregator()
    push = InMemoryLinePushClient()
    processor = ConversationEventProcessor(
        flow=flow,
        searcher=searcher,
        booking_slots=booking_slots,
        consolidator=consolidator,
        logs=logs,
        push_client=push,
        store_id="store-1",
        menu_durations={"カット": 30},
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


if __name__ == "__main__":
    _demo()
