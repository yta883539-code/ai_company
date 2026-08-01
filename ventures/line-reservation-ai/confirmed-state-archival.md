# confirmed状態の予約アーカイブ処理設計

作成日: 2026-08-01

## 目的
conversation-state-cleanup.mdの「今後の課題」に残っていた
「`confirmed`状態も、来店日を過ぎたあとは通知ログ集計等の対象から外すためのアーカイブ処理が
将来的に必要になる可能性がある」を具体化する。

release_idle_conversations()(無応答離脱の失効)は`confirmed`状態を明示的に対象外としており、
前日リマインド送信(reminder-timing-and-resend-rules.md)や無断キャンセル判定
(no-show-handling.md)で参照されるため、来店日までは`_states`に残り続ける設計だった。
一方、来店日を過ぎてもなお残り続けると、`ConversationFlowStateMachine._states`が
無制限に肥大化し、会話状態を毎回全走査する`release_idle_conversations()`等の処理コストが
運用が長引くほど増えていく問題がある。

## 前提の整理:「アーカイブ」の対象は会話メモリであって予約記録ではない

まず区別すべき点として、`ConversationFlowStateMachine._states`はあくまで
「進行中・直近の会話のやりとりを追跡するための一時メモリ」であり、
予約そのものの正式な記録(店舗の予約台帳、no-show-handling.mdが参照する
「累計予約数・無断キャンセル確定数」等の顧客ごとの永続履歴)は、
tech-stack.mdが想定するスプレッドシート等の永続ストレージ側に別途記録される
(この永続ストレージの具体的なスキーマ・書き込みタイミングは本ドキュメントの範囲外で、
実装フェーズで確定する)。

したがって本ドキュメントが設計する「アーカイブ」は、
**`_states`からの間引き(会話メモリのクリーンアップ)** を指し、
予約履歴そのものの削除・改変は一切行わない。この区別を明確にすることで、
conversation-state-cleanup.mdで曖昧だった「アーカイブ=履歴も消える」という誤解を防ぐ。

## 猶予期間: 来店日+1日

来店日当日中はまだ以下の処理が`state.slot_key`(来店日時)を参照する可能性があるため、
即座にはアーカイブしない。

- no-show-handling.mdの無断キャンセル判定(来店予定日当日の来店有無の確認)
- reminder-timing-and-resend-rules.mdの前日リマインド再送判定

来店日を1日(`ARCHIVE_AFTER_VISIT = timedelta(days=1)`)過ぎた時点で、
上記の参照はいずれも完了している前提のためアーカイブ対象とする。
1日という値は保守的な目安であり、実運用でno-show判定の確定タイミングが
より遅いことが分かれば延長を検討する(閾値は仮の値、今後の課題として残す)。

## 実行トリガー

conversation-state-cleanup.mdのスイープ処理(`release_idle_conversations`)と同様、
実行トリガー(cron/バッチ間隔、Webhook受信時の副作用実行)は実際のホスティング基盤が
決まった時点で確定する。1日1回程度の低頻度実行で十分なため、
`release_idle_conversations`(30分間隔目安)とは別のより粗い間隔のジョブとして
分離してよい。

## 挙動

1. `_states`内の`stage == "confirmed"`かつ`slot_key`を持つ会話を走査する。
2. `slot_key`の日付部分(`slot_key[1]`、ISO形式)をパースし、
   `now.date() - visit_date >= ARCHIVE_AFTER_VISIT`(=1日以上経過)であれば削除する。
3. `BookingSlotManager`側の予約枠ステータス(`confirmed`)には一切触れない。
   予約の一次記録として、解放せずそのまま残す
   (double-booking-prevention.mdの2段階管理はあくまで「重複予約の防止」が目的であり、
   来店済みの枠を再度他人に開放する必要はないため)。
4. エスカレーション通知は送らない(通常のクリーンアップ処理であり、
   release_idle_conversations()と同様に都度通知するとオーナーの確認負荷を上げるだけのため)。

## 実装

`prototype/engine.py`の`ConversationFlowStateMachine`に反映済み:

- `ARCHIVE_AFTER_VISIT = timedelta(days=1)`定数を追加。
- `archive_completed_conversations(now)`メソッドを追加し、上記の挙動を実装。
- デモに、来店日当日はまだアーカイブされない顧客(佐藤さん)、来店日から2日後に
  アーカイブされる顧客(佐藤さん)、来店日がまだ先でアーカイブ対象外の顧客(山本さん)の
  3パターンを追加し、`BookingSlotManager`側の`confirmed`ステータスがアーカイブ後も
  変更されず残ることもあわせて確認した。

## 今後の課題

- 実際のジョブスケジューリング実装方式(tech-stack.md側で別途検討、
  conversation-state-cleanup.mdの実行トリガー未確定と同じ論点)。
- 永続ストレージ(スプレッドシート等)側の予約履歴レコードのアーカイブ・保存期間方針
  (個人情報保護の観点からの保存期間上限の要否)は本ドキュメントの範囲外。
  実装フェーズで永続ストレージのスキーマを確定する際にあわせて検討する。
- `ARCHIVE_AFTER_VISIT`(1日)の妥当性は、実運用でのno-show判定・リマインド再送の
  確定タイミングの実績が取れてから見直す。
