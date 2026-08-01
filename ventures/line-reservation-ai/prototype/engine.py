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

class NotificationLogAggregator:
    """オーナー向け通知ログ集計画面(スプレッドシート版MVP相当)の集計ロジック。

    ルール:
      - resolved:false の faq_segments を対象に、(日付, userId, topic) でユニーク化してカウントする
        (duplicate-topic-notification-log-rule.md準拠。日をまたげば別カウント、同日内の連投は1件扱い)。
      - escalation_reason='unimplemented_feature' は「未実装機能問い合わせ件数」として内訳を別集計する
        (notification-log-classification-labels.md準拠)。
      - escalation_reason が上記以外/未設定(=一般相談)の件数も参考値として集計する。
    """

    def __init__(self) -> None:
        self._seen_topics: set[tuple[str, str, str]] = set()
        self.unimplemented_feature_count = 0
        self.consultation_count = 0

    def record(self, user_id: str, output: dict, now: datetime) -> None:
        date_key = now.date().isoformat()
        for seg in (output.get("faq_segments") or []):
            if seg.get("resolved") is False:
                self._seen_topics.add((date_key, user_id, seg["topic"]))

        if output.get("intent") == "escalation" and output.get("needs_owner_check"):
            reason = output.get("escalation_reason")
            if reason == "unimplemented_feature":
                self.unimplemented_feature_count += 1
            else:
                self.consultation_count += 1

    def unique_unresolved_topic_count(self) -> int:
        return len(self._seen_topics)


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
      - EscalationConsolidator経由でオーナーへ通知し、このユーザーの会話状態は
        candidates_presentedに戻す(呼び出し側で新しい空き枠を再提示する想定)。
      - 通知イベントのescalation_reason='booking_conflict'は現行のbooking_output.schema.jsonの
        enum(consultation/unimplemented_feature)には未追加。この通知はLLM構造化出力ではなく
        システム内部で生成するイベントのため現時点ではスキーマ検証の対象外としているが、
        通知ログ集計(NotificationLogAggregator)へ将来含める場合はenum拡張が必要になる
        (今後の課題として残す)。
    """

    def __init__(self, slots: BookingSlotManager, consolidator: EscalationConsolidator) -> None:
        self._slots = slots
        self._consolidator = consolidator
        self._states: dict[str, _ConversationState] = {}

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
                self._consolidator.on_event(
                    user_id,
                    {
                        "intent": "escalation",
                        "needs_owner_check": True,
                        "escalation_reason": "candidate_selection_unresolved",
                    },
                    now,
                )
                state.reconfirm_count = 0
                return SelectSlotResult(success=False, message=ESCALATION_HANDOFF_MESSAGE)
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

    def provide_details(self, user_id: str, name: str, menu: str, now: datetime) -> bool:
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
            return True

        self._consolidator.on_event(
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
        return False

    def stage(self, user_id: str) -> Optional[str]:
        state = self._states.get(user_id)
        return state.stage if state else None

    def release_idle_conversations(self, now: datetime) -> list[str]:
        """conversation-state-cleanup.md準拠。last_activity_atからCONVERSATION_IDLE_TIMEOUT
        (30分)以上経過した会話状態を失効させる。confirmed状態は対象外(前日リマインド等で
        後から参照されるため保持し続ける)。awaiting_detailsで止まっていた場合は、対応する
        枠のholdも明示的に解放する(既にBookingSlotManager側のHOLD_TIMEOUTで解放済みでも、
        release()自体は無害なため呼び出し順序に依存しない)。エスカレーション通知は送らない
        (無応答離脱は日常的に発生するため、都度通知すると通知過多になる)。
        戻り値: 失効させたuser_idのリスト(呼び出し側のログ・監視用)。
        """
        released: list[str] = []
        for user_id, state in list(self._states.items()):
            if state.stage == "confirmed":
                continue
            if state.last_activity_at is None or now - state.last_activity_at < CONVERSATION_IDLE_TIMEOUT:
                continue
            if state.stage == "awaiting_details" and state.slot_key is not None:
                self._slots.release(state.slot_key)
            del self._states[user_id]
            released.append(user_id)
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
        business_hours: tuple[int, int],  # (開始, 終了) を24時間表記の時刻(分)で指定
        slot_interval_minutes: int = 30,
        closed_weekdays: frozenset = frozenset(),  # date.weekday()準拠(月=0〜日=6)、定休日
    ) -> None:
        self._open_min, self._close_min = business_hours
        self._interval = slot_interval_minutes
        self._closed_weekdays = closed_weekdays

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
        pref_start, pref_end = _TIME_OF_DAY_RANGES.get(
            time_of_day_preference, (self._open_min, self._close_min)
        )
        pref_end = self._close_min if pref_end is None else min(pref_end, self._close_min)
        pref_start = max(pref_start, self._open_min)

        candidates: list[_Candidate] = []
        start_date, end_date = date_range
        day = start_date
        while day <= end_date and len(candidates) < max_candidates:
            if day.weekday() in self._closed_weekdays:
                day += timedelta(days=1)
                continue
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
    return None


def _label_date_and_time_in_reply(label: str, normalized_reply: str) -> bool:
    date_part, _, time_part = label.partition(" ")
    date_part = date_part.partition("(")[0]  # "8/9(土)" -> "8/9"。曜日抜きの返信でも一致させる
    time_part = time_part.rstrip("〜")
    return bool(date_part) and bool(time_part) and date_part in normalized_reply and time_part in normalized_reply


# ---------------------------------------------------------------------------
# デモ: 上記8コンポーネントを1本のパイプラインとして通しで動かす
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
    print(f"31分後にrelease_idle_conversations()で失効した顧客: {released}")
    print(f"中村さんの会話ステージ(失効後、状態が削除されNoneになる): {idle_flow.stage('user_nakamura')}")
    print(f"中村さんが選んだ枠の状態(release_idle_conversations()のrelease()は無害な冪等呼び出し): "
          f"{idle_slots.status(slot_89_1830, t0 + timedelta(minutes=31))}")
    print(f"小林さんの会話ステージ(confirmed済みは対象外のまま残る): "
          f"{idle_flow.stage('user_kobayashi')}")

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


if __name__ == "__main__":
    _demo()
