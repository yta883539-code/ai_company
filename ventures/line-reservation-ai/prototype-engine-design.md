# prototype/engine.py 設計メモ(2026-07-31 17:58 UTC)

## 位置づけ
schema/validate_test_cases.py で「期待JSON出力同士の構造的整合性」を机上検証した次の一歩として、
これまで文章(md)でのみ記述してきた下記3つのロジックを、初めて**実行可能なコード**に落とし込んだ。

- json-output-retry-fallback.md → `RetryFallbackProcessor`(`process_llm_output`関数)
- escalation-consolidation-logic.md → `EscalationConsolidator`
- duplicate-topic-notification-log-rule.md / notification-log-classification-labels.md
  → `NotificationLogAggregator`

実LLM呼び出しは行っていない。LLM呼び出し箇所は `llm_call: Callable[[], dict]` として
差し替え可能なスタブにしてあるため、オーナー承認・APIキー取得後は
「実際にLINE Messaging APIやClaude APIを叩く関数」を注入するだけで動作する設計。
そのため今回の作業はpending-approval.mdの承認状況に関わらず実施できる範囲(支払い・アカウント作成・
外部送信を伴わないコード試作)にとどめている。

## 実装して分かったこと・設計上の判断

1. **EscalationConsolidatorのウィンドウ管理は「開始時刻固定」で実装した。**
   escalation-consolidation-logic.mdの文章では「5分ウィンドウ」「再発火」を概念的に記述していたが、
   実装するにあたり「ウィンドウの起点をイベントごとにスライドさせるか、固定するか」という
   未決定だった実装詳細を決める必要があった。今回は「ウィンドウ開始時刻固定(直近イベント時刻ではなく
   ウィンドウが開いた時刻から5分)」を採用した。理由: スライド式(直近イベントから毎回5分延長)だと
   短時間の連投が続く限り通知が無限に遅延しうり、「初回は即時、追加分はまとめて」という原設計の
   意図(通知の速報性を損なわない)に反するため。

2. **`flush_due_windows`を呼ぶタイミングは呼び出し側(スケジューラ)に委ねる設計にした。**
   実装を素朴に「時間が来たら自動で発火する」形にすると、この段階ではまだ選定していない
   非同期実行基盤(cron/ジョブキュー等)への依存が生まれてしまう。そのため本プロトタイプでは
   時刻を明示的に受け取る純粋関数として実装し、実運用時のスケジューリング方式(技術構成)は
   tech-stack.mdの検討課題として切り出した(下記「次の課題」参照)。

3. **NotificationLogAggregatorの集計はカウンタでなくset()によるユニーク化で実装した。**
   (日付, userId, topic)の組をsetに入れることで、md設計で言葉としては明確だった
   「ユニーク化」を素直にコード化できることを確認した。実装上の懸念点は特になかった。

## 動作確認
`python3 ventures/line-reservation-ai/prototype/engine.py` でデモシナリオ(同一顧客の連続
エスカレーション集約、未解決FAQの重複排除、リトライ成功/フォールバックの両ケース)を実行し、
設計md通りの挙動になることを確認済み。

## 次の課題
- ~~上記1で決めた「ウィンドウ開始時刻固定」方式は今回のコード化で新たに確定させた実装判断のため、
  escalation-consolidation-logic.md側にも明記して整合を取る必要がある(次回以降で反映)。~~ →
  解消済み(2026-11-04追記、フェーズ続き367で発見)。escalation-consolidation-logic.md
  「追記(2026-07-31 17:58 UTC): 実装(prototype/engine.py)で確定した詳細」節に、本ファイルと
  同日(2026-07-31)付で既に反映されていたことを確認した。本「次の課題」欄のみが未反映のまま
  3か月以上残っていた記載漏れだった。
- ~~`flush_due_windows`の呼び出しタイミング(スケジューリング方式)をtech-stack.mdで具体化する
  必要がある。~~ → 解消済み(2026-11-04追記、フェーズ続き367で発見)。escalation-consolidation-
  logic.md「未検討・要検討事項」節(2026-09-08追記)で、tech-stack.mdではなく
  escalation-digest-flush-trigger-design.mdとして別ドキュメント化する形で具体化されていた
  (idle-conversation-trigger-design.mdと同じ「Webhook便乗方式」、
  `ConversationEventProcessor.maybe_run_escalation_flush()`、間引き間隔1分。実Cloud Scheduler
  接続時は`flush_escalation_windows()`を直接呼び出すだけで移行可能)。tech-stack.md側への
  個別追記は不要と判断し、本欄を解消済みに更新した。
- 実LLM呼び出し関数の注入・自動テスト化はオーナー承認後(pending-approval.md参照)。
