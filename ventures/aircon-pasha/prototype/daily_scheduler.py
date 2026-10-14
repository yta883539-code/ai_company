#!/usr/bin/env python3
"""
フェーズ314(README.md)「次回候補(2)」で指摘された欠落への対応(フェーズ315)。

trial_end_scheduler.py(Cloud Function E)・payment_failure_reminder_scheduler.py
(Cloud Function F)・payment_suspension_scheduler.py(Cloud Function G)の3モジュールは
いずれも選定ロジック・送信配線本体(各design該当節)は実装済みだったが、実際にCloud
Scheduler(日次)から起動する薄いエントリポイントが本venture単体では一度も実装されて
いなかった(trial-end-scheduler-design.md 1節・payment-failure-reminder-scheduler-
design.md 1節はいずれも「同一ジョブから続けて呼び出す想定」「既存のCloud Function Eと
同一関数にまとめるか...は実インフラ構築時にコスト・運用面から判断すればよい」と記して
おり、3モジュールを1つの日次ジョブにまとめることを最初から想定していた)。本ファイルは
その欠落を埋める、kura-pasha/prototype/daily_scheduler.pyと対称の結合層。

位置づけ:
- payment_failure_reminder_scheduler.PaymentFailureReminderUserState・
  payment_suspension_scheduler.PaymentSuspensionUserStateの2モジュールは、
  trial_end_scheduler.build_trial_user_states()に相当する「UserProfileStoreProtocolから
  全ユーザーを読み取ってstateを組み立てる」関数を持たない(各モジュールの_demo()・テストで
  手動構築されるのみ)ため、本ファイルでbuild_payment_failure_reminder_states()・
  build_payment_suspension_states()を新設する(kura-pasha daily_scheduler.
  build_trial_end_states()・build_payment_failure_states()と同じ「全ユーザーからstateを
  組み立てる」役割)。
- 3モジュールの`LinePushClient`Protocol・`InMemoryLinePushClient`はいずれも
  `send_flex_message(user_id, alt_text, contents) -> None`という同一の構造を持つ
  (cloud_function_send_deletion_candidate_final_confirmations.pyが既にtrial_end_
  scheduler.InMemoryLinePushClientを別モジュール〈deletion_candidate_final_
  confirmation.py〉に流用しているのと同じ前例)。Protocolは実行時には構造的ダック
  タイピングで満たされるため、本ファイルでは1個のInMemoryLinePushClientインスタンスを
  3モジュール共通で渡す。
- user_id(user_profile)の抽出順はsorted(profile_store.all_user_ids())に揃え、呼び出し順
  の非決定性を避ける(kura-pasha daily_scheduler.build_trial_end_states()と同じ方針)。
- 本ファイルでは既存のdeletion_candidate_final_confirmation.py(フェーズ308で別個の月次
  Cloud Scheduler・cloud_function_send_deletion_candidate_final_confirmations.pyとして
  既に実装・デプロイ設計済み)は対象外とする。周期(日次 vs 月次)が異なるためあえて統合
  しない(次回候補参照)。

設計の参照元: trial-end-scheduler-design.md, payment-failure-reminder-scheduler-design.md,
kura-pasha/prototype/daily_scheduler.py(横展開元)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List

from payment_failure_reminder_scheduler import (
    DEFAULT_GRACE_PERIOD_DAYS as PAYMENT_FAILURE_REMINDER_GRACE_PERIOD_DAYS,
    DEFAULT_REMINDER_DAYS_BEFORE_END,
    PaymentFailureReminderUserState,
    SendPaymentFailureRemindersResult,
    send_payment_failure_reminders,
)
from payment_suspension_scheduler import (
    DEFAULT_GRACE_PERIOD_DAYS as PAYMENT_SUSPENSION_GRACE_PERIOD_DAYS,
    PaymentSuspensionUserState,
    SendPaymentSuspensionsResult,
    send_payment_suspensions,
)
from trial_end_scheduler import (
    DEFAULT_TRIAL_PERIOD_DAYS,
    SendTrialEndNotificationsResult,
    build_trial_user_states,
    send_trial_end_notifications,
)
from user_id_linking import UserProfileStoreProtocol


def build_payment_failure_reminder_states(
    profile_store: UserProfileStoreProtocol,
) -> List[PaymentFailureReminderUserState]:
    """全user_idから、payment_failure_reminder_scheduler.select_due_payment_failure_
    reminders()が参照するフィールドを組み立てる(user_id昇順)。"""

    return [
        PaymentFailureReminderUserState(
            user_id=user_id,
            payment_failure_detected_at=profile_store.get_payment_failure_detected_at(user_id),
            payment_suspended_at=profile_store.get_payment_suspended_at(user_id),
            payment_failure_reminder_sent_at=(
                profile_store.get_payment_failure_reminder_sent_at(user_id)
            ),
        )
        for user_id in sorted(profile_store.all_user_ids())
    ]


def build_payment_suspension_states(
    profile_store: UserProfileStoreProtocol,
) -> List[PaymentSuspensionUserState]:
    """全user_idから、payment_suspension_scheduler.select_due_payment_suspensions()が
    参照するフィールドを組み立てる(user_id昇順)。"""

    return [
        PaymentSuspensionUserState(
            user_id=user_id,
            payment_failure_detected_at=profile_store.get_payment_failure_detected_at(user_id),
            payment_suspended_at=profile_store.get_payment_suspended_at(user_id),
        )
        for user_id in sorted(profile_store.all_user_ids())
    ]


@dataclass
class RunDailyChecksResult:
    """1回のCloud Scheduler起動での3系統それぞれの結果一式(kura-pasha
    RunDailyWorkshopChecksResultと対称)。"""

    trial_end_notifications: SendTrialEndNotificationsResult
    payment_failure_reminders: SendPaymentFailureRemindersResult
    payment_suspensions: SendPaymentSuspensionsResult


def run_daily_checks(
    now: datetime,
    profile_store: UserProfileStoreProtocol,
    push_client,
    trial_period_days: int = DEFAULT_TRIAL_PERIOD_DAYS,
    payment_failure_reminder_grace_period_days: int = PAYMENT_FAILURE_REMINDER_GRACE_PERIOD_DAYS,
    reminder_days_before_end: int = DEFAULT_REMINDER_DAYS_BEFORE_END,
    payment_suspension_grace_period_days: int = PAYMENT_SUSPENSION_GRACE_PERIOD_DAYS,
) -> RunDailyChecksResult:
    """design該当3節が想定する日次ジョブ本体。trial_end→payment_suspension→
    payment_failure_reminderの順に実行する。

    payment_suspension→payment_failure_reminderの順序は意図的なもので、両モジュールを
    単独でしか動かしていなかった間は気づかれていなかった相互作用がある:
    payment_failure_reminder_scheduler.select_due_payment_failure_reminders()は
    「猶予期間(7日)を過ぎていないか」の上限チェックを持たず(kura-pasha daily_scheduler.
    is_payment_failure_reminder_due()は`payment_suspended_at`相当のフラグを持たないため
    上限チェックで代用しているが、本venture側は`payment_suspended_at is None`のみで
    足りる設計、payment-failure-reminder-scheduler-design.md 3節)、「ちょうど制限モード
    移行対象になった(7日以上経過・まだpayment_suspended_at未設定)」ユーザーは
    payment_failure_reminder側の抽出条件(`payment_suspended_at is None`)にも同時に
    合致してしまう。payment_suspensionを先に実行して`payment_suspended_at`を書き込んで
    おけば、続くpayment_failure_reminder側の抽出でそのユーザーは`payment_suspended_at`
    設定済みとして自然に除外され、「制限モード移行の通知」と「まもなく期限のリマインド」が
    同一ユーザーに同一バッチ内で二重送信されることを避けられる(設計変更ではなく、本ファイル
    で両者を初めて同じバッチ内で呼び合わせたことで発覚した実行順序の要件)。"""

    trial_user_ids = sorted(profile_store.all_user_ids())
    trial_states = build_trial_user_states(profile_store, trial_user_ids)
    trial_result = send_trial_end_notifications(
        trial_states, now, profile_store, push_client, trial_period_days
    )

    suspension_states = build_payment_suspension_states(profile_store)
    suspension_result = send_payment_suspensions(
        suspension_states, now, profile_store, push_client, payment_suspension_grace_period_days
    )

    reminder_states = build_payment_failure_reminder_states(profile_store)
    reminder_result = send_payment_failure_reminders(
        reminder_states,
        now,
        profile_store,
        push_client,
        payment_failure_reminder_grace_period_days,
        reminder_days_before_end,
    )

    return RunDailyChecksResult(
        trial_end_notifications=trial_result,
        payment_failure_reminders=reminder_result,
        payment_suspensions=suspension_result,
    )


def _demo() -> None:
    from trial_end_scheduler import InMemoryLinePushClient
    from user_id_linking import InMemoryUserProfileStore

    now = datetime(2026, 10, 14, 4, 0, 0)
    store = InMemoryUserProfileStore()
    push_client = InMemoryLinePushClient()
    result = run_daily_checks(now, store, push_client)
    print(result)


if __name__ == "__main__":
    _demo()
