# 確定後の顧客返信検知(`customerRepliedAt`)の配線設計

## 位置づけ
reminder-scheduler-design.md「未解決のまま残る課題」の1点目、「顧客からの返信検知の配線」を解消する。
`select_due_resends()`(prototype/reminder_scheduler.py)は`customer_replied_at`が設定されている
予約を当日朝の再送対象から除外する前提だが、confirmed状態の会話にどこで・どうやってこの値を
書き込むかがこれまで未設計だった。

## 設計判断

### 1. 「返信内容の解釈」ではなく「メッセージが届いた事実」で判定する
select_due_resends()の目的は、当日朝の再送メッセージが「何かしら返信して生存確認が取れた顧客」に
重ねて送られるのを防ぐことであり、返信内容の意味解釈(出席の意思表示か、キャンセル依頼か、
単なる「ありがとうございます」か)は不要。したがって、confirmed状態の会話に対してLINEから
何らかのメッセージイベントが届いたこと自体をもって`customerRepliedAt`を記録する
(intentがfaq/escalation/new_booking等いずれであっても区別しない)。

返信内容に応じた後続対応(キャンセル・変更intentの実処理)は、intent-to-flow-mapping.mdの
対応表で行自体は既に定義されているが実装は別課題として引き続き残す(本設計のスコープ外)。

### 2. 記録タイミングはCloud Function B(process_conversation_event)の`process()`冒頭
LLM呼び出し・intent判定より前に、`user_id`を取得した直後に`flow.stage(user_id)`を確認し、
`"confirmed"`であれば記録する。理由:
- LLM呼び出し自体が失敗・リトライされる場合でも「メッセージが届いた」という事実は変わらないため、
  LLM結果(process_llm_output()の成否)に依存させたくない。
- 後続のintentごとの分岐(faq/escalation/new_booking/その他)いずれの経路でも一律に記録する
  必要があり、分岐の後ろに置くと経路によって記録漏れが生じうる。分岐前に置くのが最も漏れがない。

### 3. Firestore接続とは切り離した「配線」として注入する
既存のLinePushClient/TaskQueueClientプロトコルと同じ設計方針で、`ConfirmedReplyRecorder`という
小さいプロトコル(`record(user_id, now) -> None`)を`ConversationEventProcessor`にオプション注入する。
- プロトタイプでは`InMemoryConfirmedReplyRecorder`(呼び出し履歴を`list[tuple[str, datetime]]`で
  保持するだけ)を用意し、テスト・デモで動作確認する。
- 実装時(GCPプロジェクト作成・Firestore接続後、いずれもオーナー承認待ち)は、該当
  conversationドキュメントの`customerRepliedAt`フィールドを`now`で更新する処理に差し替えるだけで
  動作する設計とする。
- 未指定(`None`)の場合は何もしない(既存のテスト・デモを壊さないためのデフォルト)。

### 4. stageがconfirmed以外なら何もしない
candidates_presented/awaiting_details/None(会話履歴なし)の各状態は前日リマインド・再送の
対象外(reminder-scheduler-design.mdはconfirmed済み予約のみを扱う)であり、`customerRepliedAt`と
無関係のため記録しない。

### 5. 記録後も通常のintent分岐は継続する
`customerRepliedAt`の記録は「副作用の追加」であり、既存のintentごとの分岐処理
(faq返信・escalation一次応答・新規予約フロー開始等)を変更・スキップするものではない。
confirmed状態からの`new_booking` intentは「別日の再訪希望」の可能性があるため、現状通り
`_start_new_booking()`(新規予約フローの開始)に進む(意図的な既存仕様。返信内容による
「これは再訪希望か、単なる相槌か」の判別は本設計のスコープ外とする)。

### 6. 複数回返信があった場合は毎回最新の時刻で上書きする
「初回の返信のみ記録」ではなく、confirmed状態でメッセージを受け取るたびに`record()`を呼び、
常に最新の返信時刻で上書きする方針とする。理由: 将来的にno-show-handling.mdのような
「直近の反応時刻」を判断材料に使う可能性があり、初回のみの記録だと情報が古くなるため。
select_due_resends()側は「`customer_replied_at is not None`か」しか見ないため、この方針変更は
既存の再送判定ロジックに影響しない。

## 実装(`prototype/cloud_function_process_event.py`)
- `ConfirmedReplyRecorder`(Protocol、`record(user_id, now) -> None`)と
  `InMemoryConfirmedReplyRecorder`(検証用実装)を追加。
- `ConversationEventProcessor.__init__`に`confirmed_reply_recorder: Optional[ConfirmedReplyRecorder] = None`
  を追加。
- `process()`冒頭、`user_id`取得直後・LLM呼び出し前に、stageがconfirmedであれば記録するよう配線。

## 残る課題
- Firestore書き込み処理自体の実装(GCPプロジェクト作成・Firestore接続後、オーナー承認待ち)。
- (解消済み 2026-08-04 04:00 UTC: cancel/change intentの実処理はcancel-intent-handling-design.md・
  change-intent-handling-design.mdで設計・実装済み)。
- (解消済み 2026-08-04 04:00 UTC: confirmed状態からの`new_booking` intentが「別日の再訪希望」か
  「リマインドへの相槌」かの判別は、llm-system-prompt-draft.mdの厳守事項11としてプロンプトレベルの
  判定基準(明確な予約要求の言い回し、または独立した具体的日時の言及がなければ9b雑談扱いとする)を
  新設して対応した。バックエンド側の分岐(`_start_new_booking()`)自体は変更していないため、
  LLMがこの基準通りに安定して分類できるかは実LLM検証(オーナー承認待ち、pending-approval.md参照)
  で確認する必要がある)。
