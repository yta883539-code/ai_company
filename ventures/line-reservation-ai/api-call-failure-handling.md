# LLM API / LINE API呼び出し自体の失敗時のハンドリング設計(2026-08-04時点)

## 背景
json-output-retry-fallback.mdは「LLMは応答を返したが、その中身(JSON)が
不正・矛盾する」場合のリトライ・フォールバックを扱っている。
webhook-async-processing-design.mdは、Webhook応答の遅延対策とLINE側の
イベント再送に伴う二重処理対策(Cloud Tasksの決定的タスク名・
`isRedelivery`早期スキップ)を扱っている。

しかしいずれも「LLM API呼び出し自体が失敗する(タイムアウト・5xxエラー・
レート制限超過・ネットワーク断)」「LINE Push Message API呼び出し自体が
失敗する(5xx・レート制限・一時的なネットワーク断)」というケースは
明示的に検討されていなかった。これは応答の中身の問題ではなく、
外部サービスへの呼び出しそのものが完了しないケースであり、
`process_conversation_event`(Cloud Function B)の実装時に必要になる
設計のため、実LLM/実LINE API接続自体はオーナー承認待ちだが、
方針は先行して机上設計しておく。

## 想定される失敗パターン
1. LLM API呼び出しが失敗する(タイムアウト、5xx、レート制限429、
   ネットワーク断)。JSON応答自体を受け取れていない点で、
   json-output-retry-fallback.mdが扱う「応答は返ったが中身が不正」とは異なる。
2. LINE Push Message API呼び出しが失敗する(5xx、レート制限429、
   ネットワーク断)。この場合、`ConversationFlowStateMachine`側の状態遷移
   (hold/confirm等)は既に成功しているのに、顧客への通知だけが届かない
   「状態とメッセージ送達のズレ」が起きうる点が独自の問題。

## 方針1: LLM API呼び出し失敗時
- Cloud Tasks自体がタスク失敗時に指数バックオフで再試行する仕組みを
  標準で持つため、`process_conversation_event`内でLLM呼び出しが例外
  (タイムアウト・5xx・429)を投げた場合は、独自リトライループを実装せず
  例外をそのまま再送出してタスクを失敗させ、Cloud Tasks側の再試行に委ねる
  (json-output-retry-fallback.mdの「同一入力で1回だけ再生成」は応答が
  返った上でのJSON不正時の話であり、呼び出し自体の失敗はこの層より前で
  切り分ける)。
- Cloud Tasksの最大試行回数(タスクキュー設定で上限を設ける、暫定案:
  最大5回・最大リトライ期間30分)を超えて失敗し続けた場合のみ、
  最終フォールバックとして顧客に定型の待機メッセージ
  (「只今混み合っております。少々お待ちください。」)をpush送信し、
  `EscalationConsolidator`経由でオーナーに「LLM応答不能」の内部イベント
  として通知する(`escalation_reason`は`system_event_counts`の
  `SYSTEM_ESCALATION_REASONS`に`llm_unavailable`を新規追加する想定)。
- 再試行が積み重なる間、顧客には一切通知が行かない空白時間が生じる点は
  UX上のトレードオフとして残る。初回リトライ(数秒〜数十秒程度)までは
  無通知を許容し、それを超えて長引く場合のみ待機メッセージを送る
  「猶予時間つきの通知」も選択肢だが、猶予時間の具体値は実測データが
  無い現時点では決め切れないため、まずは「最終失敗時のみ通知」という
  シンプルな方針をMVPとして採用し、実LLM検証(オーナー承認後)の際に
  再試行の実測所要時間を見て猶予時間つき方式への切り替えを検討する。

## 方針2: LINE Push API呼び出し失敗時
- LLM呼び出し・`ConversationFlowStateMachine`の状態遷移が既に成功した
  「後」の失敗であるため、方針1のように処理全体を再試行(タスク失敗として
  Cloud Tasksに再実行させる)すると、`hold()`/`confirm()`等の状態変更処理
  を再度実行してしまい、二重予約防止ロジック(double-booking-prevention.md)
  や通知ログ集計(notification-log-classification-labels.md)の二重カウント
  を引き起こすリスクがある。そのため送信失敗時はタスク全体を失敗させず、
  「LINE送信部分のみ」を対象にした限定的なリトライ(即時1回のみ)に留める。
- 即時リトライでも失敗した場合、状態(hold/confirm等)は既に確定している
  ため予約データとしては正しい状態のまま、顧客への通知だけが欠落する。
  この状態を放置すると顧客が予約結果を知らないまま来店予定日を迎える
  重大な事業リスクになるため、送信失敗を検知した時点で
  `NotificationLogAggregator`に`system_event_counts`の新区分
  `line_push_failed`として即時記録し、`EscalationConsolidator`経由で
  オーナーに「顧客への自動通知が届いていない可能性があるため手動で
  確認・連絡してほしい」という文面で即時通知する(集約ウィンドウ(5分)を
  待たず、booking_conflict等と同様に即時通知扱いとする)。
- 将来的な改善案として、送信失敗が検知された会話について、次回
  Webhook受信(=顧客からの何らかのアクション)時に未送信メッセージの
  再送を試みる「次回接点での再送」も考えられるが、実装が複雑になるため
  MVPでは見送り、オーナーへの通知一本化に留める。

## 既存設計との役割分担の整理
- json-output-retry-fallback.md: LLM応答は得られたが中身(JSON)が
  不正・矛盾する場合 → 応答内容に対するリトライ・フォールバック
- webhook-async-processing-design.md: LINEからのWebhookイベント自体の
  重複受信・遅延 → イベント受信側の重複排除・非同期化
- 本ドキュメント: LLM/LINE Push APIへの外向き呼び出し自体が失敗する場合
  → 呼び出し層のリトライ回数・失敗時のオーナー通知・状態とメッセージ
  送達のズレの扱い

## 未検証・要検討事項
- Cloud Tasksの最大試行回数・最大リトライ期間の具体値(暫定5回・30分)は
  仮置きであり、実測(LLM APIの実際の障害頻度・復旧時間)を見て調整する。
- LLM呼び出し失敗時の「猶予時間つき通知」への切り替え要否は、
  実LLM検証(オーナー承認後)で再試行の実測所要時間を確認してから判断する。
- `llm_unavailable`/`line_push_failed`という新しい`system_event_counts`
  区分を実際に`prototype/cloud_function_process_event.py`に実装する作業は
  未着手(実LLM/実LINE API接続自体がオーナー承認待ちのため、コード上の
  差し込み口の用意のみ先行して次回以降検討する)。

## 次のステップ候補
- `NotificationLogAggregator`の`SYSTEM_ESCALATION_REASONS`に
  `llm_unavailable`/`line_push_failed`を追加する実装(コード変更は
  クラウド接続なしでも机上テスト可能なため、承認不要で着手できる)。
- owner-settings-wireframe.mdの通知ログ集計画面「システム内部イベント」欄に
  上記2区分の表示を追記する。
