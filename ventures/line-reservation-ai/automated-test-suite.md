# prototype/engine.py の自動テストスイート化

## 背景
これまで`prototype/engine.py`の動作確認は`_demo()`関数(print文中心、要所にassert)の
実行結果を目視するのみで、以下の課題があった。

- 何が壊れたかを判定するには出力全体を読む必要があり、CI等での自動判定に使えない。
- assertは一部の重要な分岐(AvailabilitySearcherのバリデーション等)にしか付いておらず、
  BookingSlotManager・ConversationFlowStateMachine・EscalationConsolidator・
  NotificationLogAggregator・resolve_candidate_selection等の主要ロジックは
  print結果を目で追う以外の回帰検知手段がなかった。
- 今後もプロトタイプへの機能追加(実LLM接続など)を重ねていく前提のため、
  変更のたびに既存の振る舞いが壊れていないかを機械的に確認できる土台が必要。

## やったこと
`prototype/test_engine.py`を新規作成し、`unittest`(標準ライブラリのみ、追加依存なし)ベースの
テストスイートとして以下を整理した。

- ProcessLlmOutputTest: リトライ後成功・リトライ枯渇後の安全側フォールバック
- EscalationConsolidatorTest: 初回即時通知→ウィンドウ内キュー→まとめ通知、再発火3回目での
  都度通知切り替え、30分無音でのリセット
- NotificationLogAggregatorTest: 同日内重複topicのユニーク化、未実装機能問い合わせ・
  一般相談・システム内部イベントの集計区分の独立性
- BookingSlotManagerTest: hold/confirmの成功・競合、タイムアウトによる自動解放
- ConversationFlowStateMachineTest: 正常系(候補提示→確定)、select_slot()自体の競合、
  confirm()競合時のcandidates_presentedへの差し戻し(横取りした側の確定は維持される)、
  再確認ループ上限超過時のエスカレーション、想定外ステージでの呼び出し時の例外送出、
  release_idle_conversations()のconfirmed除外、archive_completed_conversations()の
  来店日+1日の猶予、maybe_run_idle_cleanup()の間引き
- AvailabilitySearcherTest: 確定済み枠の除外、定休日除外、曜日別営業時間の上書き、
  昼休憩区間の除外、区間の重複・逆転バリデーション(隣接は許可)
- SearchCandidatesFromLlmOutputTest: requested_date_range無しでNoneを返す経路、
  LLM出力→AvailabilitySearcher接続の正常系
- ResolveCandidateSelectionTest: 半角数字・全角助数詞・漢数字・自然文(日付×時刻)・
  曜日表記の有無・特定不能時のNone
- ToneRenderingTest: 既知トーンでの文言切り替え、未知トーン値のstandardへのフォールバック

全31件、`python3 -m unittest test_engine -v`で実行可能・全件パスを確認済み
(`prototype/`ディレクトリ内で実行するか、`test_engine.py`冒頭で`sys.path`に
自身のディレクトリと`schema/`を追加済みのためリポジトリルートからでも
`python3 -m unittest ventures/line-reservation-ai/prototype/test_engine.py`で実行可能)。

## 位置づけ・スコープ外としたこと
- `_demo()`は読み物・動作イメージ確認用として引き続き残し、置き換えていない
  (テストスイートと役割が重複する部分はあるが、_demo()は「一連の流れが通しで動く」ことを
  示す目的、test_engine.pyは「個々の振る舞いが壊れていないか」を機械的に検知する目的で
  棲み分ける)。
- 実LLM呼び出しのテストは含まない(APIキー・課金が必要でオーナー承認待ち、
  pending-approval.md参照)。process_llm_output()等はモックの`llm_call`のみで検証している。
- CI(GitHub Actions等)への組み込みは、ホスティング基盤自体が未確定なため今回は行っていない
  (tech-stack.mdのホスティング検討と合わせて今後の課題)。

## 次の課題
- 実装が進むごとにこのテストファイルへケースを追加していく運用とする。
- ホスティング基盤(tech-stack.md)が固まった段階で、CIでの自動実行(push時等)を検討する。
