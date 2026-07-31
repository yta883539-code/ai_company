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
# デモ: 上記3コンポーネントを1本のパイプラインとして通しで動かす
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


if __name__ == "__main__":
    _demo()
