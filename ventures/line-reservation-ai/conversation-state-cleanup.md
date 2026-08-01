# 会話状態のクリーンアップ(タイムアウト解放)設計

candidate-presentation-and-selection-design.md 6節の残課題「エスカレーション後、顧客が無反応のまま
会話が終了した場合の会話状態のクリーンアップ(タイムアウト解放)」を設計する。

## 1. 問題

`ConversationFlowStateMachine._states`は`present_candidates()`で作られた`_ConversationState`を
`user_id`ごとに保持し続けるが、これまで**明示的に削除する経路が無かった**。特に以下の2パターンで
不整合が生じる:

1. **`awaiting_details`のまま無応答**: `select_slot()`で`BookingSlotManager.hold()`が成功すると
   会話ステージは`awaiting_details`に進むが、顧客が氏名・メニューを送らないまま離脱すると、
   `BookingSlotManager`側は`HOLD_TIMEOUT`(5分)経過後に`_expire_if_needed()`で枠を自動解放する
   (booking-slot-manager-design.md)一方、`_ConversationState.stage`は`awaiting_details`のまま
   取り残される。この顧客が数時間後に再度メッセージを送ってきた場合、`provide_details()`が
   呼ばれると`self._slots.confirm(state.slot_key, ...)`は(枠が既に解放/他ユーザーに渡っている
   ため)失敗し、`booking_conflict`エスカレーションが発生する。技術的には安全側(誤確定は防げる)
   だが、顧客体験としては「もう空いていない枠」を延々awaiting_details扱いし続け、無駄な
   エスカレーション通知をオーナーに送ってしまう。
2. **`candidates_presented`のままエスカレーション後に無応答**: candidate-presentation-and-selection
   -design.md 6節の`ESCALATION_HANDOFF_MESSAGE`送信後、`reconfirm_count`は0にリセットされ会話
   ステージは`candidates_presented`のままだが、顧客がその後何も返信しない場合、古い`candidates`
   (提示当時の空き枠一覧)を保持したまま状態が無期限に残る。翌日以降に顧客が別件で再度メッセージを
   送った場合、`select_slot_from_reply()`が古い(既に埋まっている可能性のある)候補一覧に対して
   マッチングを試みてしまう。

いずれも「状態を保持し続けるコスト」自体は(スプレッドシートMVPの規模では)小さいが、
古い状態に基づいた誤動作・無駄な通知を防ぐため、明示的な期限切れ処理が必要。

## 2. 方針

channel-agnostic-session-id.mdで採用した「最終メッセージから30分無応答で失効」という時間感覚
(reminder-timing-and-resend-rules.md、escalation-consolidation-logic.mdの30分リセットとも整合)を
そのまま流用し、`CONVERSATION_IDLE_TIMEOUT = 30分`を会話状態全体の無応答失効時間とする。

- `_ConversationState`に`last_activity_at: datetime`を追加し、会話ステージが更新される
  (`present_candidates()` / `select_slot()`成功 / `select_slot_from_reply()`の各分岐 /
  `provide_details()`)たびに更新する。
- `BookingSlotManager._expire_if_needed()`と同様の「アクセス時に遅延評価」方式ではなく、
  こちらは**明示的なスイープ関数**`release_idle_conversations(now)`を用意する。理由:
  会話状態は`present_candidates()`等の特定の`user_id`アクセス時にしか触れられないため、
  遅延評価だけでは「一定期間まったく連絡が来ない顧客」の状態が事実上永久に残ってしまう
  (`awaiting_details`で止まったまま誰にも読まれない枠保持情報等)。EscalationConsolidator.
  flush_due_windows()と同じ「定期実行のスイープ」パターンを踏襲する。
- スイープの呼び出しタイミングはMVP段階では厳密なcronを組まず、`flush_due_windows()`と
  合わせて同じバッチ(例: 5分おきのポーリングジョブ、または次のLINE Webhook受信時に副作用として
  実行)で呼ぶ想定とする。実運用のジョブ基盤は未確定のため、本ステップでは関数の提供までとする。

## 3. `release_idle_conversations(now)`の挙動

対象: `last_activity_at`から`CONVERSATION_IDLE_TIMEOUT`(30分)以上経過した全`user_id`の状態。

- **`stage == "awaiting_details"`の場合**: `BookingSlotManager.release(state.slot_key)`を明示的に
  呼び、仮押さえを解放する。`HOLD_TIMEOUT`(5分)は既にこの30分より短いため実際には
  `_expire_if_needed()`側が先に解放済みのケースがほとんどだが、呼び出し順序への依存を避けるため
  防御的に呼ぶ(既に解放済みの`slot_key`に対する`release()`は`_slots.pop(..., None)`のため無害)。
- **`stage == "confirmed"`の場合**: 対象外とする。確定済み会話は失効させる意味が無く、
  むしろ確定情報(氏名・メニュー・slot_key)は前日リマインド送信(reminder-timing-and-resend-rules.md)
  等で後から参照される想定のため、`_states`に残しておく必要がある。
- **`stage == "candidates_presented"`の場合**: 保持している`candidates`(空き枠一覧)が古くなって
  いる可能性があるため、状態を破棄する。次に顧客からメッセージが来た場合は、通常の新規会話と
  同様に呼び出し側が`present_candidates()`から再度開始する。
- スイープ後、`awaiting_details`/`candidates_presented`だった対象は`_states`から完全に削除する
  (`confirmed`は削除しない)。

## 4. エスカレーション通知は送らない

`awaiting_details`の枠を明示解放する際も、これは「顧客が単に無応答で離脱した」通常の状態であり、
booking_conflict(他ユーザーとの競合)やcandidate_selection_unresolved(特定不能の連続)とは性質が
異なるため、EscalationConsolidator経由のオーナー通知は送らない方針とする。無応答離脱は接客業務では
日常的に発生するため、都度通知すると通知過多になりオーナーの確認負荷を上げてしまう
(escalation-consolidation-logic.mdが解決しようとした問題と同じ)。

## 5. 実装

`prototype/engine.py`の`ConversationFlowStateMachine`に反映済み:

- `_ConversationState.last_activity_at: datetime`を追加。
- `present_candidates()` / `select_slot()`(成功時) / `select_slot_from_reply()`(全分岐) /
  `provide_details()`で更新。
- `CONVERSATION_IDLE_TIMEOUT = timedelta(minutes=30)`定数を追加。
- `release_idle_conversations(now)`メソッドを追加し、上記3節の挙動を実装。
- デモに、awaiting_detailsで無応答のまま31分経過した顧客(枠が解放されること)と、confirmed済みの
  顧客(状態が残り続けること)の2パターンを追加して動作確認。

## 6. 今後の課題

- スイープの実行トリガー(cron/バッチ間隔、またはWebhook受信時の副作用実行)は、実際のホスティング
  基盤(スプレッドシート+キュー処理 or サーバーレス関数等)が決まった時点で確定する。
- `candidates_presented`失効時に「候補をご案内しましたが期限切れになりました」等のメッセージを
  能動的に送るべきか(現状は何も送らず、次回メッセージ時に自然に新規会話として再開する設計)は、
  能動送信(LINEのプッシュメッセージ課金・送信タイミング)を伴うため要検討。
- `confirmed`状態も、来店日を過ぎたあとは通知ログ集計等の対象から外すためのアーカイブ処理が
  将来的に必要になる可能性があるが、本ステップの対象外とする。
