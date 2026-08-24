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
- intent: "change" の場合、change-intent-handling-design.md準拠でConversationFlowStateMachine.
  change_booking()を呼び、cancelと同じ分岐で旧枠を解放・confirmed分のみオーナー通知した後、
  同じLLM出力(requested_date_range/time_of_day_preference/menu)を使って_start_new_booking()と
  同じ新規候補検索・present_candidates()へそのまま接続し、同じ会話の中で新しい日時の予約フローを
  開始する(「変更 = 旧予約の解放 + 新規予約フローの開始」という設計)。

- reminder-scheduler-design.mdの残課題だった「確定後の顧客からの返信検知の配線」を実装した
  (customer-reply-detection-design.md参照)。confirmed状態の会話へメッセージが届いた事実を、
  内容を問わず`ConfirmedReplyRecorder`プロトコル経由で記録する(未指定時は何もしない)。

- owner-notification-channel-design.mdの残課題だった「EscalationConsolidator/
  NotificationLogAggregatorが返す通知を実際にオーナーへpushする配線」を実装した。
  これまで`consolidator.on_event()`の戻り値(即時通知すべきアクション一覧)は全ての呼び出し箇所で
  破棄されており、エスカレーション等が発生してもオーナーへの実送信は一切行われていなかった。
  `_notify_owner()`ヘルパーに集約し、escalation-notification-templates.md準拠の
  `format_escalation_notification()`(engine.py新規追加)で整形して`owner_user_id`へ`_send()`する。
  また、5分ウィンドウで貯まったまとめ通知(`EscalationConsolidator.flush_due_windows()`)を
  取り出してオーナーへpushする`flush_escalation_windows()`を新設した。これはCloud Scheduler等の
  定期実行トリガーから呼び出す想定(reminder_scheduler.pyの前日リマインド判定と同じ位置づけ)で、
  実際のCloud Scheduler設定自体は「アカウント作成」に該当するため引き続きオーナー承認待ち
  (呼び出しロジック自体は実クラウド接続なしで検証可能)。

- escalation-notification-templates.md「次のステップ候補」準拠。上記の残課題だった
  `ConversationFlowStateMachine`内部(engine.py)から発火するシステムイベント
  (booking_conflict/candidate_selection_unresolved/booking_cancelled/booking_change_started)の
  伝播を実装した。engine.pyはLINE Push等のI/Oを持たない純粋ロジック層のままとし、
  `select_slot_from_reply()`/`provide_details()`/`cancel_booking()`/`change_booking()`の
  戻り値に`owner_notify_actions`フィールドを追加(`provide_details()`は戻り値をbool単体から
  `ProvideDetailsResult`に変更)して、Flow側が既に呼び済みの`consolidator.on_event()`の
  戻り値をそのまま呼び出し側へ運ぶ設計とした。Cloud Function B側は新設の
  `_dispatch_flow_notify_actions()`でこれを受け取りpushする(`_notify_owner()`と異なり
  `consolidator.on_event()`を再度呼ばない。二重に呼ぶとウィンドウ状態が二重更新されるため)。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional, Protocol

sys.path.insert(0, str(Path(__file__).parent))

from engine import (  # noqa: E402
    AvailabilitySearcher,
    BookingSlotManager,
    CONVERSATION_IDLE_TIMEOUT,
    ConversationFlowStateMachine,
    EscalationConsolidator,
    NotificationLogAggregator,
    format_candidates_message,
    format_cancel_confirmed_message,
    format_cancel_not_found_message,
    format_cancel_pending_message,
    format_change_not_found_message,
    format_change_started_message,
    format_confirmation_message,
    format_escalation_digest_message,
    format_escalation_notification,
    format_faq_address_message,
    is_escalation_event_owner_notable,
    format_faq_hours_message,
    format_faq_hours_message_weekly,
    format_faq_parking_message,
    format_faq_payment_message,
    format_faq_unregistered_message,
    format_first_booking_self_check_message,
    format_hold_message,
    label_from_slot_key,
    process_llm_output,
    resolve_candidate_selection,
    search_candidates_from_llm_output,
)


# ---------------------------------------------------------------------------
# LINE Push Message APIクライアントのプロトコル(実クライアントとInMemory版の共通インターフェース)
# ---------------------------------------------------------------------------

class LinePushDeliveryError(Exception):
    """api-call-failure-handling.md「方針2」準拠。send_message()が5xx・レート制限429・
    ネットワーク断等、送信自体の失敗(応答は届いたが中身が不正、ではなく呼び出しそのものの失敗)を
    表現するために送出する想定の例外。実クライアントに差し替える際は、line-bot-sdk等が送出する
    APIエラーをこの例外に変換して送出する(またはこの例外のサブクラスにする)ことで、
    ConversationEventProcessor._send()側のリトライ・オーナー通知ロジックをそのまま流用できる。
    """


class LinePushClient(Protocol):
    def send_message(self, user_id: str, text: str) -> None:
        """送信に失敗した場合はLinePushDeliveryErrorを送出する想定。"""
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
# change-intent-handling-design.md「残る課題」準拠。change後の新規候補検索が0件だった場合、
# 単純なREASK_DATE_RANGE_MESSAGEだけでは「以前の予約は既に取り消し済みである」ことを
# 顧客が失念しうるため、change専用に出し分ける。
CHANGE_NO_CANDIDATES_MESSAGE = (
    "当店: 大変申し訳ございません、ご希望の期間に日時変更後の空きが見つかりませんでした。"
    "以前のご予約は取り消し済みですので、改めてご希望の日時を教えていただけますか?"
    "(例:「来週土曜の午後」「8/9の午前中」)"
)
REASK_NAME_MENU_MESSAGE = "当店: お名前とご希望のメニューを教えていただけますか?"
# menu-unmentioned-vs-unregistered-design.md準拠。新規予約開始ターンでメニューが
# 未言及(LLM出力のmenuがNone)の場合に、検索前に聞き返す文言。
REASK_MENU_MESSAGE = "当店: ご希望のメニューを教えていただけますか?"
# menu-unmentioned-vs-unregistered-design.md「既知の限界・今回のスコープ外」準拠。change経由で
# _start_new_booking()に入りメニュー未言及だった場合、CHANGE_NO_CANDIDATES_MESSAGEと同様に
# 「以前のご予約は取り消し済み」である旨を含めないと顧客が失念しうるため専用文言を用意する。
CHANGE_REASK_MENU_MESSAGE = (
    "当店: 日時変更を承りました(以前のご予約は取り消し済みです)。"
    "変更後のご希望のメニューを教えていただけますか?"
)
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

    menu-unmentioned-vs-unregistered-design.md準拠。`menu_name`が未言及(None・空文字列)の
    ケースと、言及されたが店舗未登録のケースは呼び出し側(_start_new_booking())で区別しており、
    未言及の場合はこの関数を呼ばずに聞き返しへ倒す。この関数がNoneを返しうるのは主に
    「言及されたが未登録」の場合のみだが、menu_name未指定で呼ばれた場合も後方互換のため
    従来通りNoneを返す。
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
        owner_user_id: Optional[str] = None,
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
        # owner-notification-channel-design.md準拠。オーナー自身のLINE userId
        # (onboarding-guide.mdステップ4のテストメッセージ経由で取得する想定)。
        # 未設定(オンボーディング未完了等)の場合はオーナー宛の直接送信を静かにスキップする。
        self._owner_user_id = owner_user_id
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
        # menu-unmentioned-vs-unregistered-design.md準拠。新規予約開始ターンでメニューが
        # 未言及だったためREASK_MENU_MESSAGEで聞き返した際の、その時点のLLM出力(日時範囲等)。
        # stageはNoneのままのため次ターンも_start_new_booking()に落ちてくる。そこで
        # requested_date_range/time_of_day_preferenceのうち今回の出力に無い項目だけを
        # ここから補って引き継ぐ(_carried_over_menu()と対称の設計)。
        # pending-new-booking-context-ttl-design.md準拠。値は(output, set_at)のタプルで、
        # set_atはこのエントリを書き込んだ時点のnow。_merge_pending_new_booking_context()で
        # CONVERSATION_IDLE_TIMEOUT(30分)以上経過していれば期限切れとして破棄する
        # (present_candidates()未実行のためこのユーザーは_flow._statesにエントリを
        # 持たず、engine.py側のrelease_idle_conversations()では救えないケース)。
        self._pending_new_booking_context_by_user: dict[str, tuple[dict, datetime]] = {}
        # escalation-digest-flush-trigger-design.md準拠。Webhook便乗トリガー
        # (maybe_run_escalation_flush())の前回実行時刻。
        self._last_escalation_flush_at: Optional[datetime] = None

    def _send(self, user_id: str, text: str, now: datetime) -> None:
        """LINE Push Message API送信のラッパー。api-call-failure-handling.md「方針2」準拠。

        この時点で呼び出し元の`ConversationFlowStateMachine`/`BookingSlotManager`の状態遷移
        (hold/confirm等)は既に成功しているため、送信失敗時にタスク全体を失敗させて
        Cloud Tasksに再実行させると状態変更処理が二重に走ってしまう(二重予約防止ロジック・
        通知ログ集計の二重カウントを招く)。そのため送信失敗はここで完結させ、例外を外へは
        伝播させない。「LINE送信部分のみ」を対象にした即時1回のみのリトライに留め、それでも
        失敗すれば`system_event_counts`の`line_push_failed`として記録した上でオーナーへ
        即時通知する(顧客への配信自体はここで諦める)。
        """
        for _attempt in range(2):
            try:
                self._push.send_message(user_id, text)
                return
            except LinePushDeliveryError:
                continue
        event = {"needs_owner_check": True, "escalation_reason": "line_push_failed"}
        self._logs.record(user_id, event, now)
        if user_id == self._owner_user_id:
            # オーナー自身への送信が失敗した場合、これ以上オーナーへpushで通知しようがないため
            # 集約状態の記録のみ行い実送信は諦める(_notify_owner()を呼ぶと再度_send()を
            # 呼び出し同じ送信先への無限再帰になるため、ここでは直接on_event()に留める)。
            self._consolidator.on_event(user_id, event, now)
            return
        self._notify_owner(user_id, event, now)

    def _notify_owner(
        self, user_id: str, output: dict, now: datetime, reply_text: Optional[str] = None
    ) -> None:
        """owner-notification-channel-design.md準拠。EscalationConsolidator.on_event()を呼び、
        返ってきた即時通知アクション(("immediate"|"immediate_refire", event))があれば
        format_escalation_notification()で整形して`owner_user_id`へ実際にpushする。
        ウィンドウ内に貯まった分(まとめ通知)はここでは送らず、flush_escalation_windows()の
        領分とする。owner_user_id未設定時は集約状態の記録のみ行い、送信は静かにスキップする
        (first-booking-self-check-notification-design.md等と同じ安全側フォールバック)。

        このメソッドはLLM構造化出力(=Cloud Function B自身がintentを判定したイベント)向け。
        `ConversationFlowStateMachine`のメソッド(select_slot_from_reply/provide_details/
        cancel_booking/change_booking)が内部で発火するシステムイベント(booking_conflict等)は
        Flow側が既にconsolidator.on_event()を呼び済みで戻り値(owner_notify_actions)として
        返してくるため、ここではなく`_dispatch_flow_notify_actions()`を使う
        (on_event()を二重に呼ぶとEscalationConsolidatorのウィンドウ状態が二重更新されてしまうため)。

        reply_textはこのイベントの元になった顧客の生メッセージ本文(process()のevent.message.text)。
        escalation-notification-templates.md「次のステップ候補」の会話要約フィールド検討の結論により、
        LLMに要約させず生のメッセージ本文をそのまま「内容」欄に引用する
        (engine.py _escalation_detail_text()参照)。cancel_not_found/change_not_found/
        unregistered_menuのようにこのメソッドが合成したイベント向けにも同じreply_textを渡してよい
        (顧客の直近メッセージという点は変わらないため)。
        """
        actions = self._consolidator.on_event(user_id, output, now)
        customer_label = f"{output.get('name')}様" if output.get("name") else "お客様"
        self._dispatch_notify_actions(actions, customer_label, now, reply_text)

    def _dispatch_flow_notify_actions(self, actions: list, now: datetime) -> None:
        """escalation-notification-templates.md「次のステップ候補」準拠。
        `ConversationFlowStateMachine`内部(engine.py)から発火するシステムイベント
        (booking_conflict/candidate_selection_unresolved/booking_cancelled/
        booking_change_started)は、engine.py自体がLINE Push等のI/Oを持たない純粋ロジック層のため、
        Flow側の各メソッドの戻り値(owner_notify_actions)経由でこちらへ伝播してくる。
        Flow側で既にEscalationConsolidator.on_event()を呼び済みのため、ここでは
        `_notify_owner()`と異なりon_event()を再度呼ばず、渡されたactionsをそのままpushするだけに留める
        (再度呼ぶとウィンドウ状態が二重に進んでしまう)。

        reply_textを渡さない(=常にLINEトーク画面参照の案内文言になる)のは意図的な設計。
        これらのシステムイベントは「顧客の1メッセージに対する応答」ではなく状態遷移の結果
        (確定操作が競合した、再確認ループが上限を超えた等)であり、直近のreply_textを引用しても
        イベントの内容(何が起きたか)を説明したことにはならないため、_escalation_type_label()の
        種別ラベルで十分と判断した(会話要約フィールド検討の結論、escalation-notification-
        templates.md参照)。
        """
        for kind, event in actions:
            customer_label = f"{event.get('name')}様" if event.get("name") else "お客様"
            self._dispatch_notify_actions([(kind, event)], customer_label, now)

    def _dispatch_notify_actions(
        self, actions: list, customer_label: str, now: datetime, reply_text: Optional[str] = None
    ) -> None:
        """(kind, event)のリストをformat_escalation_notification()で整形してオーナーへpushする
        共通処理。owner_user_id未設定時は静かにスキップする。
        """
        if not self._owner_user_id:
            return
        for _kind, event in actions:
            if not is_escalation_event_owner_notable(event):
                # needs_owner_check: falseのイベント(例: E6の雑談・9b)はEscalationConsolidator
                # 自体のウィンドウ管理対象にはなるが、オーナーへの実push対象ではないためスキップする。
                continue
            self._send(
                self._owner_user_id,
                format_escalation_notification(customer_label, event, now, reply_text),
                now,
            )

    def flush_escalation_windows(self, now: datetime) -> int:
        """Cloud Scheduler等、定期実行のトリガーから呼び出す想定の関数
        (reminder_scheduler.pyのsend_reminders相当)。EscalationConsolidator.flush_due_windows()で
        ウィンドウ(5分)が経過し未送信のまとめ通知があるユーザー分を取り出し、
        format_escalation_digest_message()で1通にまとめてオーナーへpushする。
        実際のCloud Scheduler設定自体は「アカウント作成」に該当するため引き続き
        オーナー承認待ち(pending-approval.md参照)。戻り値は実際に送信した件数
        (テスト・デモでの確認用)。
        """
        if not self._owner_user_id:
            return 0
        sent = 0
        for _user_id, events in self._consolidator.flush_due_windows(now):
            notable = [e for e in events if is_escalation_event_owner_notable(e)]
            if not notable:
                # ウィンドウ内が全てneeds_owner_check: false(9b雑談等)だった場合、
                # ウィンドウ自体は消費済み扱いとしつつオーナーへの実pushは行わない。
                continue
            first_name = next((e.get("name") for e in notable if e.get("name")), None)
            customer_label = f"{first_name}様" if first_name else "お客様"
            self._send(self._owner_user_id, format_escalation_digest_message(customer_label, notable, now), now)
            sent += 1
        return sent

    # idle-conversation-trigger-design.mdの「Webhook便乗トリガー」と同じ考え方を
    # flush_escalation_windows()にも適用したもの(escalation-digest-flush-trigger-design.md参照)。
    ESCALATION_FLUSH_MIN_INTERVAL = timedelta(minutes=1)

    def maybe_run_escalation_flush(self, now: datetime) -> Optional[int]:
        """Webhook受信時に呼び出す想定の便乗トリガー。前回実行からESCALATION_FLUSH_MIN_INTERVAL
        (1分)未満の場合は間引いてNoneを返す。実Cloud Scheduler接続後は、flush_escalation_windows()
        を専用トリガーから直接呼ぶ運用に切り替えられる(本メソッドの設計変更は不要)。
        maybe_run_idle_cleanup()/maybe_run_archive()と同様、process()からの自動呼び出しは
        今回は行わない(実Cloud Functionsエントリポイント確定時に配線する)。
        """
        if (
            self._last_escalation_flush_at is not None
            and now - self._last_escalation_flush_at < self.ESCALATION_FLUSH_MIN_INTERVAL
        ):
            return None
        self._last_escalation_flush_at = now
        return self.flush_escalation_windows(now)

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
        if self._flow.stage(user_id) == "confirmed":
            if self._confirmed_reply_recorder is not None:
                self._confirmed_reply_recorder.record(user_id, now)
            # record_storeが保持する予約レコードのreminder_replied(no-show-handling.mdの
            # 「事前リマインドへの返信有無」表示元)も同じ事実で更新する。confirmed_reply_recorder
            # (Firestore向け、オーナー承認待ち)とは独立して、GCP接続無しでも動作する
            # (booking-record-store-design.md「MVPスコープの範囲外として残す点」の解消)。
            self._flow.record_reminder_reply(user_id)

        llm_result = process_llm_output(llm_call)
        output = llm_result.output
        intent = output.get("intent")

        if intent == "new_booking" and output.get("needs_owner_check"):
            # new-booking-needs-owner-check-notification-design.md準拠。E8(自然文とJSONの矛盾)
            # 相当のケースはintentがnew_bookingのまま安全側でconfirmed=False・
            # needs_owner_check=Trueだけが上書きされるため、放置すると_notify_owner()にも
            # NotificationLogAggregatorの集計にもつながらず実質無視されてしまう
            # (発見の経緯は同mdの「背景・発見の経緯」参照)。現行のllm-system-prompt-draft.md
            # ではLLMがintent: new_bookingのままescalation_reasonを付与することは無いため
            # (rule10のunimplemented_feature等は必ずintent: escalationにする)、常に
            # output_contradictionとして合成してよい。システム内部イベントとしてオーナーへ
            # 通知しつつ、顧客向けの処理(このあと続くstage分岐による通常の予約フロー)は
            # 変更しない。
            output = {**output, "escalation_reason": "output_contradiction"}
            self._notify_owner(user_id, output, now, reply_text)

        self._logs.record(user_id, output, now)

        if intent == "faq" and output.get("faq_segments"):
            return self._handle_faq(user_id, output, now, tone, reply_text)
        if intent == "escalation":
            return self._handle_escalation(user_id, output, now, tone, reply_text)
        if intent == "cancel":
            return self._handle_cancel(user_id, now, tone, reply_text)
        if intent == "change":
            return self._handle_change(user_id, output, now, tone, reply_text)
        if intent != "new_booking":
            # intent-to-flow-mapping.md: faq_segments無しのfaq(9b雑談等・レガシー出力)・
            # その他は予約フロー外のため ConversationFlowStateMachineは呼ばず、
            # オーナーへの転送のみ行う(単一項目9a FAQがここに落ちない理由は
            # モジュールdocstring「実装範囲」参照。cancel/changeはそれぞれの設計md準拠で
            # 上記の_handle_cancel/_handle_changeへ分岐済みのためここには来ない)。
            self._notify_owner(user_id, output, now, reply_text)
            return DispatchResult(action="forwarded_to_owner", detail=intent or "unknown")

        stage = self._flow.stage(user_id)
        if stage in (None, "confirmed"):
            return self._start_new_booking(user_id, output, now, reply_text=reply_text)
        if stage == "candidates_presented":
            return self._handle_candidate_selection(user_id, reply_text, output, now, tone)
        if stage == "awaiting_details":
            return self._handle_details(user_id, output, now, tone)

        # ここに到達するのはstageがawaiting_details/candidates_presented/confirmed/None
        # のいずれでもない場合で、ConversationFlowStateMachineの実装上通常発生しないが、
        # 安全側でオーナーへ転送する。
        self._notify_owner(user_id, output, now, reply_text)
        return DispatchResult(action="forwarded_to_owner", detail=f"unexpected_stage:{stage}")

    def _start_new_booking(
        self,
        user_id: str,
        output: dict,
        now: datetime,
        *,
        change_context: bool = False,
        reply_text: Optional[str] = None,
    ) -> DispatchResult:
        output = self._merge_pending_new_booking_context(user_id, output, now)
        menu_name = output.get("menu")
        if not menu_name:
            # menu-unmentioned-vs-unregistered-design.md準拠(オプションb採用)。「メニュー
            # 未言及」は「メニュー未登録」とは区別し、その場でオーナー転送にはせず、検索前に
            # 聞き返す。日時範囲等の既出情報は_pending_new_booking_context_by_userに保持し
            # 次ターンへ引き継ぐ(オーナーへの人手対応を減らす狙い)。
            # change経由(旧予約を解放済み)の場合はCHANGE_NO_CANDIDATES_MESSAGEと対称に、
            # 「以前のご予約は取り消し済み」である旨を含む専用文言を送る(menu-unmentioned-vs-
            # unregistered-design.md「既知の限界」準拠)。
            # pending-new-booking-context-ttl-design.md準拠。書き込み時刻(now)をあわせて
            # 保持し、次回読み出し時にCONVERSATION_IDLE_TIMEOUTを超えていれば破棄する。
            self._pending_new_booking_context_by_user[user_id] = (output, now)
            message = CHANGE_REASK_MENU_MESSAGE if change_context else REASK_MENU_MESSAGE
            self._send(user_id, message, now)
            detail = "menu_not_mentioned_change" if change_context else "menu_not_mentioned"
            return DispatchResult(action="reask", detail=detail)
        self._pending_new_booking_context_by_user.pop(user_id, None)

        menu_minutes = resolve_menu_duration(menu_name, self._menu_durations)
        if menu_minutes is None:
            self._notify_owner(
                user_id, {**output, "escalation_reason": "unregistered_menu"}, now, reply_text
            )
            return DispatchResult(action="forwarded_to_owner", detail="unregistered_menu")

        candidates = search_candidates_from_llm_output(
            self._searcher, self._booking_slots, self._store_id, output, menu_minutes, now
        )
        if not candidates:
            # change-intent-handling-design.md準拠。change経由の場合は旧予約を既に解放済みである
            # ことを顧客が失念しないよう、その旨を含めた専用文言を送る(呼び出し元の
            # format_change_started_message()は解放"直後"の案内のみでこの後続には触れないため)。
            if change_context:
                self._send(user_id, CHANGE_NO_CANDIDATES_MESSAGE, now)
                return DispatchResult(action="reask", detail="no_date_range_or_no_candidates_change")
            self._send(user_id, REASK_DATE_RANGE_MESSAGE, now)
            return DispatchResult(action="reask", detail="no_date_range_or_no_candidates")

        # 確定操作競合時の再検索(_represent_candidates_after_conflict)用に検索条件を保持する。
        self._search_context_by_user[user_id] = (output, menu_minutes)
        self._flow.present_candidates(user_id, candidates, now=now)
        self._candidates_by_user[user_id] = candidates
        self._send(user_id, format_candidates_message(candidates), now)
        return DispatchResult(action="candidates_presented", detail=str(len(candidates)))

    def _handle_candidate_selection(
        self, user_id: str, reply_text: str, output: dict, now: datetime, tone: str
    ) -> DispatchResult:
        candidates = self._candidates_by_user.get(user_id, [])
        select_result = self._flow.select_slot_from_reply(user_id, reply_text, now)
        if not select_result.success:
            # candidate_selection_unresolved(再確認上限超過)の場合、Flow側が既に
            # consolidator.on_event()を呼び済みでowner_notify_actionsに積んで返している。
            # 再確認継続中(まだ上限に達していない)はowner_notify_actionsが空のため何もしない。
            self._dispatch_flow_notify_actions(select_result.owner_notify_actions, now)
            self._send(user_id, select_result.message, now)
            return DispatchResult(action="reask", detail="candidate_selection_pending")

        # select_slot_from_reply()はcandidatesを内部(Flowのprivate state)に保持するのみで
        # 選ばれたslot_keyやlabelを戻り値に含まないため、同じ入力(reply_text, candidates)から
        # 決定的に同じ結果を返すresolve_candidate_selection()をここでも呼び、
        # 案内文言に使うlabelだけを取り出す(副作用はなく、Flow側の判定とは独立)。
        slot_key = resolve_candidate_selection(reply_text, candidates)
        label = next((c.label for c in candidates if c.slot_key == slot_key), "")
        self._held_label_by_user[user_id] = label

        menu = output.get("menu") or self._carried_over_menu(user_id) or ""
        emoji_allowed = self._flow.consume_casual_emoji_allowance(user_id)
        self._send(user_id, format_hold_message(label, menu, tone, emoji_allowed=emoji_allowed), now)
        return DispatchResult(action="held")

    def _carried_over_menu(self, user_id: str) -> Optional[str]:
        """llm-turn-context-design.md準拠。候補提示・詳細確認の各ターンでLLMに渡す入力は
        当該メッセージ単体であり会話履歴を含めない設計のため、顧客が「1番で」「山田です」の
        ように1ターン目で伝えたメニューを再度明示しない返信をした場合、LLM構造化出力の
        `menu`がNoneになりうる。その場合は`_start_new_booking()`が検索直前に
        `_search_context_by_user`へキャッシュした1ターン目確定分のメニュー名を引き継ぐ
        (サーバー側の構造的な引き継ぎであり、LLMの記憶に依存しない)。
        """
        context = self._search_context_by_user.get(user_id)
        return context[0].get("menu") if context else None

    def _merge_pending_new_booking_context(self, user_id: str, output: dict, now: datetime) -> dict:
        """直前ターンでメニュー未言及のためREASK_MENU_MESSAGEを送った場合、当該ターンの
        requested_date_range/time_of_day_preferenceを次ターンへ引き継ぐ(_carried_over_menu()の
        逆方向)。今回の出力に無い項目のみ補う(今回の発言で日時が更新された場合はそちらを優先)。

        pending-new-booking-context-ttl-design.md準拠。保持しているのが
        CONVERSATION_IDLE_TIMEOUT(30分)以上前のものであれば、顧客がその場を離れた後に
        全く無関係な要件で話しかけてきた可能性が高いとみなし、期限切れとしてマージせずに
        エントリを破棄する(古い日時条件を誤って引き継がないため)。
        """
        entry = self._pending_new_booking_context_by_user.get(user_id)
        if not entry:
            return output
        pending, set_at = entry
        if now - set_at >= CONVERSATION_IDLE_TIMEOUT:
            self._pending_new_booking_context_by_user.pop(user_id, None)
            return output
        merged = dict(output)
        for key in ("requested_date_range", "time_of_day_preference"):
            if not merged.get(key):
                merged[key] = pending.get(key)
        return merged

    def _handle_details(self, user_id: str, output: dict, now: datetime, tone: str) -> DispatchResult:
        name = output.get("name")
        menu = output.get("menu") or self._carried_over_menu(user_id)
        if not name or not menu:
            self._send(user_id, REASK_NAME_MENU_MESSAGE, now)
            return DispatchResult(action="reask", detail="missing_name_or_menu")

        details_result = self._flow.provide_details(user_id, name, menu, now)
        if not details_result.confirmed:
            # provide_details()失敗時はConversationFlowStateMachineが内部で
            # EscalationConsolidator.on_event()を既に呼んでいるため、ここでon_event()を再度呼ぶ
            # 二重通知はしない。返ってきたowner_notify_actionsをそのままpushするだけに留める。
            self._dispatch_flow_notify_actions(details_result.owner_notify_actions, now)
            return self._represent_candidates_after_conflict(user_id, now)

        label = self._held_label_by_user.pop(user_id, "")
        emoji_allowed = self._flow.consume_casual_emoji_allowance(user_id)
        self._send(
            user_id,
            format_confirmation_message(
                candidate_label=label, menu=menu, customer_name=name, tone=tone, emoji_allowed=emoji_allowed
            ),
            now,
        )
        # first-booking-self-check-notification-design.md / owner-notification-channel-design.md準拠。
        # 店舗全体で最初の確定の場合のみ、EscalationConsolidator/NotificationLogAggregatorを経由せず
        # オーナー自身のuserIdへ直接1回だけ追加送信する。owner_user_id未設定時は静かにスキップする
        # (通知を諦めるだけで、顧客への確定処理・確定メッセージ送信自体は失敗させない)。
        if self._flow.consume_first_booking_self_check() and self._owner_user_id:
            self._send(
                self._owner_user_id,
                format_first_booking_self_check_message(
                    candidate_label=label, menu=menu, customer_name=name
                ),
                now,
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
            self._send(user_id, BOOKING_CONFLICT_MESSAGE, now)
            return DispatchResult(action="booking_conflict", detail="no_alternative_forwarded_to_owner")

        self._flow.present_candidates(user_id, candidates, now=now)
        self._candidates_by_user[user_id] = candidates
        self._send(user_id, BOOKING_CONFLICT_RETRY_MESSAGE, now)
        self._send(user_id, format_candidates_message(candidates), now)
        return DispatchResult(action="booking_conflict", detail=f"represented_{len(candidates)}_candidates")

    def _handle_faq(
        self, user_id: str, output: dict, now: datetime, tone: str, reply_text: Optional[str] = None
    ) -> DispatchResult:
        """複合FAQ質問(faq_segments、json-schema-multi-intent-extension.md)への顧客向け返信。
        faq-response-templates.mdの「1メッセージ1用件」原則に従い、項目ごとに1通ずつ送信する。
        """
        segments = output["faq_segments"]
        for seg in segments:
            self._send(user_id, self._render_faq_segment(seg["topic"], seg["resolved"], tone), now)
        # 通知ログ集計(未解決topicのユニーク集計)・resolved:false項目のオーナー通知は
        # 既存のEscalationConsolidator/NotificationLogAggregatorに委ねる(全体のoutputを渡す)。
        self._notify_owner(user_id, output, now, reply_text)
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
        if topic == "hours" and self._store_faq_info.get("hours"):
            hours = self._store_faq_info["hours"]
            # 曜日別営業時間・複数区間(昼休憩等)を使う「複雑な店舗」は"default_ranges"/
            # "weekday_ranges"キーを持つ形式で渡される(hours-other-faq-topic-resolution.mdの
            # 「決定1」参照)。単一区間のみの「シンプルな店舗」は従来通りopen_minutes/close_minutes形式。
            if "default_ranges" in hours or "weekday_ranges" in hours:
                return format_faq_hours_message_weekly(
                    hours.get("default_ranges", []),
                    hours.get("weekday_ranges", {}),
                    hours.get("closed_weekdays", frozenset()), tone,
                )
            return format_faq_hours_message(
                hours["open_minutes"], hours["close_minutes"],
                hours.get("closed_weekdays", frozenset()), tone,
            )
        # topic: "other"は店舗FAQ情報欄に対応する登録項目が無いため常にこのフォールバックに落ちる
        # (hours-other-faq-topic-resolution.md参照、意図的な設計でありバグではない)。
        # resolved: trueだがstore_faq_infoに該当する登録値が無い(店舗設定と構造化出力の
        # 不整合)場合は、誤った断定回答を避けるため保留文言に安全側フォールバックする。
        return format_faq_unregistered_message(tone)

    def _handle_escalation(
        self, user_id: str, output: dict, now: datetime, tone: str, reply_text: Optional[str] = None
    ) -> DispatchResult:
        """厳守事項6(予約以外の相談)・10(未実装機能問い合わせ)発生時の顧客への一次応答。
        faq-response-templates.mdの共通保留文言を即時送信し、詳細な対応はオーナーに委ねる。
        """
        self._send(user_id, format_faq_unregistered_message(tone), now)
        self._notify_owner(user_id, output, now, reply_text)
        return DispatchResult(action="escalation_replied", detail=output.get("escalation_reason") or "consultation")

    def _handle_cancel(
        self, user_id: str, now: datetime, tone: str, reply_text: Optional[str] = None
    ) -> DispatchResult:
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
            # system-event-log-gap-fix.md準拠。EscalationConsolidatorとNotificationLogAggregatorの
            # 両方に記録する(ConversationFlowStateMachine._notify_system_event()と同じ理由で、
            # ここもflow内部から発火するイベントではないため個別に両方呼ぶ必要がある)。
            not_found_event = {
                "intent": "cancel", "needs_owner_check": True, "escalation_reason": "cancel_not_found",
            }
            self._notify_owner(user_id, not_found_event, now, reply_text)
            self._logs.record(user_id, not_found_event, now)
            self._send(user_id, format_cancel_not_found_message(tone), now)
            return DispatchResult(action="forwarded_to_owner", detail="cancel_not_found")

        if result.stage == "confirmed":
            # booking_cancelledはcancel_booking()内部で既にconsolidator.on_event()済みのため、
            # 返ってきたowner_notify_actionsをそのままpushする(_notify_owner()は使わない)。
            self._dispatch_flow_notify_actions(result.owner_notify_actions, now)
            label = label_from_slot_key(result.slot_key)
            self._send(
                user_id, format_cancel_confirmed_message(label, result.menu or "", tone), now
            )
            return DispatchResult(action="cancelled", detail="confirmed")

        self._send(user_id, format_cancel_pending_message(tone), now)
        return DispatchResult(action="cancelled", detail=result.stage)

    def _handle_change(
        self, user_id: str, output: dict, now: datetime, tone: str, reply_text: Optional[str] = None
    ) -> DispatchResult:
        """change-intent-handling-design.md準拠。intent: "change"の一次処理。
        ConversationFlowStateMachine.change_booking()にcancelと同じ分岐(stageに応じたrelease()・
        confirmed分のみオーナー通知)を委ね、found=Trueの場合は同じLLM出力を使って
        _start_new_booking()と同じ新規候補検索へそのまま接続する(旧予約があった場合のみ、
        先に「取り消した」旨の案内を送ってから新しい候補を提示する)。
        """
        result = self._flow.change_booking(user_id, now)
        self._candidates_by_user.pop(user_id, None)
        self._held_label_by_user.pop(user_id, None)
        self._search_context_by_user.pop(user_id, None)

        if not result.found:
            # cancelの安全側フォールバックと同じ考え方(_handle_cancelのcancel_not_found参照)。
            # change_booking()自身は状態が無い場合オーナー通知を行わないため、ここで行う。
            # system-event-log-gap-fix.md準拠でNotificationLogAggregatorにも記録する。
            not_found_event = {
                "intent": "change", "needs_owner_check": True, "escalation_reason": "change_not_found",
            }
            self._notify_owner(user_id, not_found_event, now, reply_text)
            self._logs.record(user_id, not_found_event, now)
            self._send(user_id, format_change_not_found_message(tone), now)
            return DispatchResult(action="forwarded_to_owner", detail="change_not_found")

        # booking_change_startedはchange_booking()内部で既にconsolidator.on_event()済みのため、
        # 返ってきたowner_notify_actionsをそのままpushする(_notify_owner()は使わない。
        # confirmed以外はresult.owner_notify_actionsが空リストのため何もしない)。
        self._dispatch_flow_notify_actions(result.owner_notify_actions, now)

        # 実際に旧予約を解放した(=顧客に「取り消した」旨を伝えた)場合のみ、以降の0件時文言を
        # change専用に出し分ける。candidates_presentedだった場合は解放すべき実体が無く
        # 「取り消した」旨の案内もしていないため、通常のnew_bookingと同じ文言で聞き直す。
        released_old_booking = result.stage in ("awaiting_details", "confirmed")
        if released_old_booking:
            label = label_from_slot_key(result.slot_key)
            self._send(
                user_id, format_change_started_message(label, result.menu or "", tone), now
            )

        return self._start_new_booking(
            user_id, output, now, change_context=released_old_booking, reply_text=reply_text
        )


def _demo() -> None:
    from datetime import date, timedelta

    # system-event-log-gap-fix.md準拠。logsをflow・processorの両方に渡すことで、
    # booking_conflict/booking_cancelled/booking_change_started等のシステム内部イベントが
    # NotificationLogAggregator.system_event_countsにも記録されるようにする。
    logs = NotificationLogAggregator()
    flow = ConversationFlowStateMachine(BookingSlotManager(), EscalationConsolidator(), logs=logs)
    booking_slots = flow._slots  # デモ用に同一インスタンスを共有(本番はDIで渡す)
    searcher = AvailabilitySearcher(business_hours=(9 * 60, 18 * 60), slot_interval_minutes=30)
    consolidator = flow._consolidator
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
        owner_user_id="U-owner",
        store_faq_info={
            "address": "○○駅から徒歩5分",
            "parking": {"available": True, "capacity": "3"},
            "payment_methods": ["現金", "クレジットカード"],
            "hours": {"open_minutes": 10 * 60, "close_minutes": 19 * 60, "closed_weekdays": frozenset({6})},
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
    # owner-notification-channel-design.md: 店舗全体で最初の確定なので、顧客への確定メッセージに
    # 続けてowner_user_id宛のセルフチェック促し通知が1件追加送信されているはず(pushの最後の1件)。
    print(f"   push(customer): {push.sent[-2][1]}")
    print(f"   push(owner): {[t for uid, t in push.sent if uid == 'U-owner']}")

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

    # 4c) 営業時間FAQ(E17相当、2026-08-03新規)
    def llm_call_4c() -> dict:
        return {
            "intent": "faq", "name": None, "menu": None, "datetime_candidate": None,
            "confirmed": False, "needs_owner_check": False,
            "faq_segments": [{"topic": "hours", "resolved": True}],
        }

    event4c = {"source": {"userId": "U5"}, "message": {"text": "営業時間を教えてください"}}
    r4c = processor.process(event4c, llm_call_4c, now, tone="standard")
    print(f"4c) action={r4c.action} detail={r4c.detail}")
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

    # 6) cancel(予約なし): system-event-log-gap-fix.mdの修正確認。cancel_not_foundが
    # NotificationLogAggregator.system_event_countsにも記録されることを示す。
    def llm_call_6() -> dict:
        return {
            "intent": "cancel", "name": None, "menu": None, "datetime_candidate": None,
            "confirmed": False, "needs_owner_check": True,
        }

    event6 = {"source": {"userId": "U5"}, "message": {"text": "予約キャンセルします"}}
    r6 = processor.process(event6, llm_call_6, now, tone="standard")
    print(f"6) action={r6.action} detail={r6.detail}")
    print(f"   push: {push.sent[-1][1]}")
    print(f"   system_event_counts: {logs.system_event_counts} (合計{logs.system_event_total()}件)")


if __name__ == "__main__":
    _demo()
