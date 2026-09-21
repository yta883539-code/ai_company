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
    faq-escalation-customer-reply-implementation.md参照)。
    (訂正 2026-09-21 19:00 UTC: 本項目は執筆当時「それ以外(単一項目faq・cancel/change等)は
    Flowを一切呼ばず転送のみ」としていたが誤り。単一項目faqは同日中にsingle-item-faq-schema-
    decision.mdの方針変更で`_handle_faq()`ルートに合流済み(下記「未実装のまま残るもの」節
    参照)。cancel/changeも同日作成のcancel-intent-handling-design.md・change-intent-
    handling-design.mdに基づき、`_handle_cancel()`/`_handle_change()`という専用ハンドラで
    `ConversationFlowStateMachine.cancel_booking()`/`change_booking()`を呼び、stageに応じた
    枠解放・オーナー通知・返信文言の出し分けまで実装済みである。本節がその後の実装反映を
    取りこぼしたまま「転送のみ」という初期設計時点の記載で残っていたcross-document parityの
    記載漏れであり、以後このファイルで「未実装」として再掲しない)。

## テスト(`prototype/test_cloud_function_process_event.py`)
(訂正 2026-09-21 19:00 UTC: 本節の「unittest 20件、合計69件」は2026-08-02執筆時点の件数の
まま更新が止まっていた記載漏れ。現時点では`test_cloud_function_process_event.py`単体128件・
`test_engine.py`135件・`test_cloud_function_webhook.py`19件〈いずれも
`python3 -m unittest discover -s prototype -p "<ファイル名>"`で個別確認、venture全体では
854件に集約〉で全件パス。以下の箇条書きは初期設計時点のテスト観点の記録として残し、cancel/
change intentの専用ハンドラに対応する現行テスト〈`CancelIntentTests`・`ChangeIntentTests`、
stageごとの解放・通知・返信を検証〉はcancel-intent-handling-design.md・change-intent-
handling-design.md側の記載を参照)。
- `resolve_menu_duration()`の登録/未登録/menu欠落
- 曖昧な日付範囲→候補提示、未登録メニュー→検索前にエスカレーション、日付の手がかりなし→聞き直し
- cancel intent(訂正 2026-09-21 19:00 UTC: 執筆当時は未実装でFlowに触れず転送するのみだったが、
  現在は`_handle_cancel()`が`ConversationFlowStateMachine.cancel_booking()`を呼び出す。
  詳細はcancel-intent-handling-design.md・`CancelIntentTests`参照)
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
- (解消済み 2026-08-02 14:00 UTC: single-item-faq-schema-decision.mdで、単一項目FAQ(E10・E14前半等、
  厳守事項9a該当分)でも`faq_segments`を1要素配列で必ず付与する方針に変更した。既存の複合質問向け
  処理ループ(`_handle_faq`)をそのまま流用でき追加分岐は不要。E10・E14前半は本ルートで自動返信
  されるようになり、「単一項目FAQは自動返信できない」制約は解消済み。厳守事項9bの雑談等、店舗FAQ項目に
  基づかない`faq` intentは引き続き`faq_segments`が`null`のままオーナー転送のみを維持。
  2026-08-09 02:00 UTC点検: 本項目が長らく「未実装のまま残るもの」節に未訂正のまま残っていたのを発見し
  訂正。以後このファイルで再掲しないこと)
- (解消済み 2026-08-02 12:00 UTC: 確定操作競合時に、初回提示時と同じ検索条件で`now`時点の
  空き枠を再検索し、奪われた枠を除いた新しい候補一覧をその場で再提示するようにした
  (`_represent_candidates_after_conflict()`)。検索条件のキャッシュが無い/再検索しても
  候補が0件の場合は従来通り謝罪文言のみのフォールバックを維持。詳細は
  booking-conflict-candidate-representation.md参照)
- (解消済み 2026-08-02〈作成同日〉、記載訂正2026-09-21 19:00 UTC: 本節にはこれまで
  cancel/change intentが「未実装のまま残るもの」として明示的には挙げられていなかったが、
  上記「実装したもの」節・「テスト」節では「Flowを一切呼ばず転送のみ」「cancel intent(未実装)」
  という記載が最近まで残っていた。実際にはcancel-intent-handling-design.md・change-intent-
  handling-design.md(いずれも本ファイルと同じ2026-08-02作成)に基づき、`_handle_cancel()`・
  `_handle_change()`という専用ハンドラが`ConversationFlowStateMachine.cancel_booking()`・
  `change_booking()`を呼び出し、stageごとの枠解放・オーナー通知・返信文言の出し分けまで
  実装・テスト済み〈`CancelIntentTests`・`ChangeIntentTests`〉であることを確認した。以後
  このファイルでcancel/changeを「未実装」として再掲しない)
- **前日リマインド(スケジューラ発火)経路との統合**: `format_reminder_message()`は
  message-tone-variants.md/`_render_by_tone()`経由で実装済みだが、Cloud Function B自体は
  Webhookイベント起点(LLM出力起点)のみを扱う設計であり、スケジューラ発火経路の呼び出し元
  (Cloud Scheduler等)は未実装のまま。
- 実際のGCPプロジェクト作成・Cloud Functions/Cloud Tasksへのデプロイ、実LLM API呼び出しへの
  接続(`llm_call`スタブの差し替え)は、いずれもpending-approval.md記載のアカウント作成・
  課金承認待ち。
- (訂正 2026-08-07 07:00 UTC: 上記の「`menu_durations`の入力欄追加は未着手」は誤り。
  owner-settings-wireframe.mdの「2. メニュー設定ページ」(メニュー名・料金・所要時間の追加/編集UI)は
  本項執筆(2026-08-02 11:00 UTC)より前の2026-08-01時点で既に存在しており、firestore-data-model.mdの
  店舗ドキュメントにも`menus: [{name, durationMinutes}, ...]`として反映済みだった。`resolve_menu_duration()`
  (`prototype/cloud_function_process_event.py`)が受け取る`menu_durations: dict`は、この`menus`配列を
  `{name: durationMinutes, ...}`へ変換するだけの一行の変換処理であり、Firestore接続実装
  (オーナー承認待ち)時にあわせて書けば足りるため、設計・UI面での残課題はない。以後このファイルで
  「残課題」として再掲しないこと。candidate-label-weekday-fix.md・pending-timeout-ux.mdと同様の
  記載ミスの訂正)。
