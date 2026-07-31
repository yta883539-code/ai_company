# 会話フロー本体とBookingSlotManagerの接続設計(2026-07-31 19:58 UTC新規作成)

## 位置づけ
README.mdの「次にやること」で挙げていた、conversation-flow.mdの「候補提示→確定」の2ステップを
BookingSlotManager(booking-slot-manager-design.md)へ接続する状態遷移コードを、
`prototype/engine.py`に`ConversationFlowStateMachine`クラスとして実装した。
併せて、booking-slot-manager-design.mdが呼び出し側の課題として残していた
「確定操作自体が競合した場合のpending差し戻し+オーナー通知」もここで実装した。

## 実装した状態遷移
- `candidates_presented`(候補提示済み) → `select_slot()`で`BookingSlotManager.hold()`を呼ぶ →
  成功なら`awaiting_details`(氏名・メニュー確認待ち)へ。
- `awaiting_details` → `provide_details()`で`BookingSlotManager.confirm()`を呼ぶ →
  成功なら`confirmed`へ。
- `select_slot()`が失敗(他ユーザーとの競合)した場合は`candidates_presented`のまま
  (呼び出し側で「ちょうど埋まってしまいました」+直近の空き枠再提示を行う想定、
  double-booking-prevention.md「3. 競合時のリカバリー」前段に対応)。

## 確定操作自体の競合時のリカバリーで判断したこと(設計の変更点)
booking-slot-manager-design.mdの記述は「後着の予約をpending状態に戻し、オーナーへ通知する」
だったが、実装時に次の点を確認し、**「pending状態への差し戻し(release()呼び出し)は行わない」**
方針に変更した。

理由: `BookingSlotManager.confirm()`が失敗するのは、(1)自分の保留がタイムアウト済みで
枠から消えている、または(2)枠が既に別ユーザーの保留/確定に上書きされている、のいずれかのみ
(confirm()自身の実装が`existing.user_id != user_id`等を厳格にチェックしているため)。
(2)のケースで無条件に`release(slot_key)`を呼ぶと、**既に確定済みの別ユーザーの正当な予約を
誤って消してしまう**バグになる(デモの佐藤さん/高橋さんシナリオで検証)。
そのため「差し戻す」対象は実質的に存在せず、正しい実装は
「このユーザーの会話状態をcandidates_presentedに戻し、オーナーへ通知するのみ」であると判断した。

## 未解決の課題(今後の検討事項)
- 通知イベントの`escalation_reason='booking_conflict'`は、現行の
  `schema/booking_output.schema.json`のenum(`consultation`/`unimplemented_feature`)には
  未追加。この通知はLLM構造化出力ではなくシステム内部(BookingSlotManagerとの接続層)で
  生成するイベントのため、現時点ではJSON Schema検証の対象外としている。
  NotificationLogAggregatorの集計に含める場合はenum拡張(またはシステム内部イベント用の
  別集計軸の新設)が必要になる。
- 現在のデモでは`select_slot()`失敗時(候補選択時点での競合)の顧客向けメッセージ生成・
  再提示ロジックはBookingSlotManagerの戻り値(bool)を確認するのみで、実際の会話文言
  (「ちょうど埋まってしまいました」+新しい候補提示)はまだ接続していない。
  pending-timeout-ux.mdの文言設計と接続するのは次のステップ候補。
- `select_slot()`/`provide_details()`はいずれも呼び出し順序が不正だと`ConversationFlowError`
  を送出する設計にしたが、実際のLLM会話エンジンからどのタイミングでこれらを呼び出すか
  (LLMの構造化出力`intent`/`confirmed`フィールドとの対応付け)はまだ未設計。

## デモ結果
`python3 engine.py`のデモに以下シナリオを追加し、想定通りの挙動を確認した:
1. 田中さんが候補提示→枠選択(hold成功)→氏名・メニュー確定(confirm成功)→`confirmed`。
2. 佐藤さんが枠を選択したまま7分放置(タイムアウト)、高橋さんが同じ枠を選択→確定まで完了。
3. 佐藤さんが遅れて氏名・メニューを送信→`confirm()`失敗→`candidates_presented`へ差し戻し+
   オーナー通知イベント発火。この間、高橋さんの確定済み予約(`confirmed`)は維持されたままである
   ことを確認(release()を呼ばない設計が正しく機能している)。
