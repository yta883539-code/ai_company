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
from datetime import datetime, timedelta
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


@dataclass
class SelectSlotResult:
    success: bool
    message: Optional[str] = None  # 失敗時のみ、顧客への案内文言(呼び出し側でそのまま送信可能)


@dataclass
class _ConversationState:
    stage: str  # "candidates_presented" | "awaiting_details" | "confirmed"
    slot_key: Optional[tuple] = None
    name: Optional[str] = None
    menu: Optional[str] = None


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

    def present_candidates(self, user_id: str) -> None:
        """候補日時を提示した時点で呼ぶ。新規会話・再提示のいずれでも状態を初期化する。"""
        self._states[user_id] = _ConversationState(stage="candidates_presented")

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
            return SelectSlotResult(success=True)
        message = SLOT_CONFLICT_MESSAGE_TEMPLATE.format(
            slot_label=slot_label, alt_candidates=alt_candidates
        )
        return SelectSlotResult(success=False, message=message)

    def provide_details(self, user_id: str, name: str, menu: str, now: datetime) -> bool:
        """氏名・メニューが揃った時点で呼ぶ。confirm()成功ならconfirmedへ進む。
        失敗(確定操作自体の競合)時はcandidates_presentedへ差し戻し、オーナーへ通知する。
        """
        state = self._states.get(user_id)
        if state is None or state.stage != "awaiting_details":
            raise ConversationFlowError(f"unexpected stage for provide_details: {state}")
        state.name = name
        state.menu = menu
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


# ---------------------------------------------------------------------------
# デモ: 上記5コンポーネントを1本のパイプラインとして通しで動かす
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
    flow.present_candidates("user_tanaka")
    print(f"田中さん枠選択: {flow.select_slot('user_tanaka', slot_89_1400, t0)}")
    print(f"田中さん詳細確定: "
          f"{flow.provide_details('user_tanaka', '田中', 'カット', t0 + timedelta(minutes=2))}")
    print(f"田中さんの状態: {flow.stage('user_tanaka')}")

    # select_slot()自体の競合系: 山田さんが、田中さんが確定済みの枠を選ぼうとして失敗する。
    # pending-timeout-ux.mdの文言案4を接続した案内メッセージが返る(呼び出し側はそのまま送信可能)。
    flow.present_candidates("user_yamada")
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
    flow.present_candidates("user_sato")
    print(f"佐藤さん枠選択: {flow.select_slot('user_sato', slot_89_1600, t0)}")

    flow.present_candidates("user_takahashi")
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


if __name__ == "__main__":
    _demo()
