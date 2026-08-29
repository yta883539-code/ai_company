# BookingSlotManager 実装メモ(2026-07-31 18:58 UTC新規作成)

## 位置づけ
README.mdの「次にやること」で挙げていた「会話フロー本体を実際のコードに落とし込む」の
第一歩として、double-booking-prevention.mdで設計した「仮押さえ(pending)→確定(confirmed)の
2段階予約枠管理」を`prototype/engine.py`の`BookingSlotManager`クラスとして実装した。

## 実装した挙動
- `hold(slot_key, user_id, now)`: 枠を仮押さえ。既に他ユーザーが押さえ済み(タイムアウト前)なら失敗。
- `confirm(slot_key, user_id, now)`: 仮押さえ済みの枠を確定。タイムアウト済み・別ユーザーの場合は失敗。
- タイムアウトは`HOLD_TIMEOUT = 5分`固定(double-booking-prevention.mdの「未検証の仮説」に挙げられていた
  5分という値をそのまま採用。実測データによる見直しは今後の課題として残る)。
- `release()`: 明示的な解放(キャンセル等、呼び出し側の判断で使用)。

## 設計md通りに実装した点・簡略化した点
- 「読み込み→空きチェック→書き込み」を単一シリアル実行することを前提としたモデル(スプレッドシート+
  キュー処理によるMVP段階の簡易排他制御に対応)。真の並行アクセス(マルチプロセス・マルチスレッド)には
  未対応で、double-booking-prevention.mdが「データストアをスプレッドシートから軽量DBに移行するタイミングで
  一意制約による本格的な排他制御に切り替える」としていた将来課題はそのまま残っている。
- 確定操作自体が競合するケース(ごく稀、doubled-booking-prevention.md「3. 競合時のリカバリー」)は、
  今回のconfirm()実装では「別ユーザーのpending中にconfirmしようとしたら単純に失敗を返す」形に
  とどめており、md記載の「後着の予約をpending状態に戻してオーナー通知」という復旧アクションの発火は
  呼び出し側(会話フロー本体)の実装時に組み込む必要がある。

## デモ結果
`python3 engine.py`のデモに以下シナリオを追加し、想定通りの挙動を確認した:
1. 田中さんが枠をhold → 成功
2. 直後に鈴木さんが同じ枠をhold → 失敗(競合)
3. 田中さんが3分後にconfirm → 成功
4. 佐藤さんがhold後7分放置(タイムアウト5分超過)→ statusはNoneに解放
5. タイムアウト後、高橋さんが同じ枠をhold → 成功(再提示可能であることの確認)
6. 佐藤さんがタイムアウト後にconfirmを試みる → 失敗(安全側)

## 今後の課題
- (解消済み: 会話フロー本体(conversation-flow.mdの「候補提示→確定」の2ステップ、氏名・
  メニュー確定までのやり取り)とBookingSlotManagerを接続する状態遷移コードは、
  `prototype/engine.py`の`ConversationFlowStateMachine`として実装済み。詳細は同クラスの
  docstring参照)
- (解消済み: 確定操作自体の競合時のリカバリーは`ConversationFlowStateMachine`の
  `provide_details()`(confirm()失敗時の分岐)として呼び出し側に実装済み。ただし当初本docが
  想定していた「後着の予約をpending状態に戻す」形とは異なり、競合時にこのユーザーが保留して
  いたはずの枠は既に手元に無い(タイムアウト済みか別ユーザーに上書きされた)ため明示的な
  slot操作(release等)は行わず、このユーザーの会話状態をcandidates_presentedへ差し戻して
  新しい空き枠を再提示する設計に変更した。EscalationConsolidator経由でオーナーへの即時通知も
  行う。詳細は`ConversationFlowStateMachine`docstringおよびengine.pyデモの佐藤さんシナリオ参照)
- 実LLM呼び出しでの動作確認はオーナー承認後(pending-approval.md参照)。
- タイムアウト`HOLD_TIMEOUT = 5分`固定値の実測データによる見直しは、実運用開始後の課題として
  引き続き残る。
