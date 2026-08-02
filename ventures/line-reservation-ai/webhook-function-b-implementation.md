# Cloud Function B(会話処理ハンドラ)の実装

## 位置づけ
webhook-function-a-implementation.mdの「未実装のまま残るもの」に挙げていたCloud Function B
(`process_conversation_event`)について、Aと同様に「実LLM呼び出し・実クラウド接続とは
切り離せる範囲」――**Cloud TasksからデキューされたイベントをintentごとにConversationFlowStateMachine
のメソッドへ振り分け、LINE Push Message APIへの送信文言を組み立てる配線ロジック**――を
先に実行可能なコードに落とし込んだ。engine.pyのllm_callスタブ・cloud_function_webhook.pyの
`TaskQueueClient`プロトコルと同じ考え方で、LINE送信部分は`LinePushClient`プロトコルとして
差し替え可能にしてある。

## 実装したもの(`prototype/cloud_function_process_event.py`)
- `LinePushClient`プロトコル / `InMemoryLinePushClient`: LINE Push Message APIのクライアントを
  差し替え可能にしたインターフェースと、送信内容を記録するだけの検証用実装。承認・LINE公式アカウント
  開設後は実クライアントに差し替えるだけで動作する設計。
- `resolve_menu_duration()`: LLM構造化出力の`menu`(メニュー名の自由記述)から、店舗設定の
  メニュー別所要時間(`menu_durations`辞書、店舗ごとに事前登録する想定)を引く。未登録メニューは
  `None`を返し、呼び出し側は空き枠検索を行わずオーナーへエスカレーションする(安全側)。
- `ConversationEventProcessor`: Cloud Function Bの本体。intent-to-flow-mapping.mdの対応表に
  従い、`intent: new_booking`かつ会話のstage(`ConversationFlowStateMachine.stage()`)に応じて
  次のいずれかを行う。
  1. **新規/確定後の会話**(`stage`が`None`または`confirmed`): `search_candidates_from_llm_output()`
     で空き枠候補を検索し、`present_candidates()`→`format_candidates_message()`で提示。
     日付の手がかりがない/候補ゼロの場合は聞き直し文言を送る。
  2. **候補提示済み**(`stage == "candidates_presented"`): `select_slot_from_reply()`で
     顧客の返信からslot_keyを解決し、成功時は`format_hold_message()`で仮押さえ案内を送る。
     候補ラベルは`select_slot_from_reply()`の戻り値に含まれないため、同じ入力で決定的に
     同じ結果を返す`resolve_candidate_selection()`をここでも呼び直して取り出す設計とした
     (Flow側の判定への副作用はない)。
  3. **詳細待ち**(`stage == "awaiting_details"`): 氏名・メニューが両方揃っていれば
     `provide_details()`を呼ぶ。成功時は`format_confirmation_message()`で確定案内を送る
     (候補ラベルは2.でholdした際に`ConversationEventProcessor`内にキャッシュしておいたものを
     再利用。ConversationFlowStateMachineの内部状態には手を加えない設計)。失敗(確定操作自体の
     競合)時はFlow側が既にオーナー通知済みのため二重通知はせず、顧客には謝罪文言のみ送る。
  - `intent`が`new_booking`以外の場合、`faq`(`faq_segments`付与時)は`_handle_faq()`、
    `escalation`は`_handle_escalation()`で顧客への一次返信を送ったうえで
    `EscalationConsolidator.on_event()`へ転送する(2026-08-02 11:00 UTC追加、詳細は
    faq-escalation-customer-reply-implementation.md参照)。それ以外(単一項目faq・
    cancel/change等)はFlowを一切呼ばず転送のみ(下記「未実装のまま残るもの」参照)。

## テスト(`prototype/test_cloud_function_process_event.py`)
unittest 20件、全件パス(既存のtest_engine.py 32件・test_cloud_function_webhook.py 17件も
引き続き全件パスを確認済み、合計69件。確定操作競合時の新しい空き枠の再提示に関する
テストは booking-conflict-candidate-representation.md 参照)。
- `resolve_menu_duration()`の登録/未登録/menu欠落
- 曖昧な日付範囲→候補提示、未登録メニュー→検索前にエスカレーション、日付の手がかりなし→聞き直し
- cancel intent(未実装)がFlowに触れず転送されること
- 候補選択→hold→詳細入力→confirmedまでの一連の流れ、候補ラベルがhold・confirm両方の
  案内文言に一貫して反映されること
- 特定不能な返信での再確認、氏名/メニュー不足での聞き直し
- 確定操作自体が競合するケース(`booking_conflict`)でオーナーへの二重通知が起きないこと・
  顧客への謝罪文言送信・stageが`candidates_presented`へ差し戻されること
- (2026-08-02 11:00 UTC追加)escalation intentでの保留文言即時送信・escalation_reasonの
  detail引き継ぎ、複合FAQ(faq_segments)の項目別テンプレート送信(全項目回答可/一部未登録/
  住所topic/店舗未登録時のフォールバック)、単一項目FAQ(faq_segmentsなし)は引き続き
  自動返信されないことの回帰確認

## 未実装のまま残るもの(次の課題)
- (解消済み 2026-08-02 11:00 UTC: escalation/faq intentの顧客向け返信を実装した。
  複合FAQ(`faq_segments`付与時)は項目ごとにfaq-response-templates.md準拠のテンプレート回答、
  escalation intentは共通の保留文言を即時送信する。詳細はfaq-escalation-customer-reply-implementation.md参照)
- **単一項目FAQの顧客向け返信**: `faq_segments`が付与されない単一項目FAQ(E10・E6等)は、
  構造化出力にどのFAQ項目(topic)への質問かを表す情報が無いためengine側でテンプレート回答を
  組み立てられず、引き続きオーナー転送のみ(自動返信なし)。json-schema-multi-intent-extension.mdの
  既存推奨(単一項目では`faq_segments`を省略)を見直すスキーマ変更が必要になる可能性がある。
- (解消済み 2026-08-02 12:00 UTC: 確定操作競合時に、初回提示時と同じ検索条件で`now`時点の
  空き枠を再検索し、奪われた枠を除いた新しい候補一覧をその場で再提示するようにした
  (`_represent_candidates_after_conflict()`)。検索条件のキャッシュが無い/再検索しても
  候補が0件の場合は従来通り謝罪文言のみのフォールバックを維持。詳細は
  booking-conflict-candidate-representation.md参照)
- **前日リマインド(スケジューラ発火)経路との統合**: `format_reminder_message()`は
  message-tone-variants.md/`_render_by_tone()`経由で実装済みだが、Cloud Function B自体は
  Webhookイベント起点(LLM出力起点)のみを扱う設計であり、スケジューラ発火経路の呼び出し元
  (Cloud Scheduler等)は未実装のまま。
- 実際のGCPプロジェクト作成・Cloud Functions/Cloud Tasksへのデプロイ、実LLM API呼び出しへの
  接続(`llm_call`スタブの差し替え)は、いずれもpending-approval.md記載のアカウント作成・
  課金承認待ち。
- `menu_durations`(店舗ごとのメニュー別所要時間)は現状呼び出し側が用意する前提の辞書のみで、
  owner-settings-wireframe.mdの店舗設定画面への入力欄追加は未着手。
