# LLM API / LINE Reply API呼び出し自体の失敗時のハンドリング設計(2026-08-18時点)

## 背景
これまでの`process_memo_event()`の検討は「LLM応答は返ったが構造化出力(JSON)の検証に
失敗する」場合のリトライ(同一入力で1回だけ再生成)にとどまっており、「LLM API呼び出し
自体が失敗する(タイムアウト・5xxエラー・レート制限429・ネットワーク断)」「LINE Reply
API呼び出し自体が失敗する」というケースは明示的に検討されていなかった。
course-set-pasha/api-call-failure-handling.mdと同じ論点であり、本ventureも
course-set-pashaと同様に会話状態マシン・Cloud Tasksを持たない単発リクエスト/レスポンス型
(tech-stack.md)のため、対応方針もcourse-set-pashaをそのまま踏襲できると判断した。

## course-set-pashaとの前提の一致・相違
1. **Push APIではなくReply APIのみを使う**(tech-stack.md「想定コンポーネント1」)。
   Reply APIは`replyToken`が1回限り・Webhook受信から短時間で失効する制約があり、
   Cloud Tasks等の非同期リトライ基盤を持たないため、リトライは即時1回のみに限定する
   (course-set-pashaと同一の制約)。
2. **送信者=事業者本人(エアコンクリーニング業者)であり、顧客対応ではない**
   (README概要「業者本人が使う入力チャネル」)。返信が届かなかった場合の実害は
   「業者本人が気づいてメモを再送する」だけで済み、本ventureは状態変更(hold/confirm等)を
   一切持たない単発の文章生成ツールのため二重実行のリスクも無い(course-set-pashaと同一の
   位置づけ)。
3. **相違点**: 本ventureは`llm_call.generate()`に`has_photo`引数を持たない(mvp-flow-draft.md
   で写真は「任意添付」の扱いにとどまり、出力スキーマにhasPhoto相当のフィールドが無いため。
   course-set-pashaのtext-image-bundling-design.md相当の対応を見送っている点はREADME
   「次にやること」に既述の通り)。このためリトライ関数のシグネチャは`has_photo`を含まない
   簡略版とする。

## 想定される失敗パターン
1. LLM API呼び出しが失敗する(タイムアウト・5xx・429・ネットワーク断)。
   `llm_call.generate()`が例外を送出するケース。JSON検証失敗
   (`validate_llm_output()`がエラーを返すケース)とは異なり、応答自体を受け取れていない。
2. LINE Reply API呼び出しが失敗する(5xx・429・ネットワーク断)。
   `reply_client.reply()`が例外を送出するケース。

## 方針1: LLM API呼び出し失敗時
- Cloud Tasksが無いため、`process_memo_event()`内で**同期的に**限定回数のリトライを行う。
- Webhook応答はLINE Platformへできる限り速やかに200を返すべきという制約と、Reply APIトークンの
  短い有効期限を踏まえ、リトライは「即時1回のみ・待機なし」に限定する。
  - 既存のJSON検証失敗時リトライ(同一入力で1回だけ再生成)とは目的も発生層も異なる
    別処理のため、合計の`llm_call.generate()`呼び出し回数の上限
    (API呼び出し失敗時リトライ1回 × 検証失敗時リトライ1回 = 最大4回)がWebhookの
    タイムアウト時間内に収まるかは、実LLM接続後にレイテンシ実測値で要検証(未検証事項として
    下記に残す)。
- 即時リトライも失敗した場合、`VALIDATION_FAILURE_FALLBACK_MESSAGE`と同様の位置づけで
  `API_FAILURE_FALLBACK_MESSAGE`(「只今混み合っております。少し時間をおいて同じ内容を
  もう一度送ってください。」)を、まだ有効なはずの`reply_token`を使って返す。
  `MemoProcessResult`に`api_failure: bool`フィールドを新設し、検証失敗の`validation_errors`とは
  別カウントで集計できるようにした。
- course-set-pashaと同様、本ventureにもオーナー・業者へのエスカレーション通知の仕組みは
  現時点で存在しない。送信者本人が返信の有無を直接確認でき、失敗時は「もう一度メモを送る」
  という状態変更を伴わない安全な再試行が可能なため、MVPではこのフォールバック文言のみで
  足りると判断する。

## 方針2: LINE Reply API呼び出し失敗時
- `reply_token`は1回限り使用可能という制約があるため、`reply_client.reply()`が例外を
  送出した場合の即時リトライは、course-set-pashaと同じ理由(実装によっては失敗した呼び出し
  自体がトークンを消費してしまっている可能性があるが、LINE Platform側の挙動の一次情報は
  未確認)により、リトライの安全性は完全には保証できない前提としつつも、Reply API以外に
  代替の送達手段を持たないMVPでは「即時1回のみリトライを試み、それでも失敗した場合は
  諦める」方針を採用する。
- いずれにせよ再試行に失敗した(またはトークン失効が確定した)場合、Reply APIには代替の
  送達手段が無い(Push APIは導入していない、tech-stack.md「想定コンポーネント1」)。この場合、
  そのメモへの応答は失われるが、方針1と同じ理由(状態変更を伴わない・送信者本人が気づいて
  再送できる)により、事業影響は軽微と判断し、Push API導入(ユーザーIDの保存・追加のAPI
  スコープ取得が必要)は現時点では見送る。

## 既存設計との役割分担の整理
- `validate_llm_output()`によるリトライ(既存): LLM応答は得られたが中身(JSON)が
  不正・矛盾する場合 → 応答内容に対するリトライ・フォールバック
- 本ドキュメント: LLM/LINE Reply APIへの外向き呼び出し自体が失敗する場合 →
  呼び出し層の即時リトライ回数・失敗時のフォールバック文言・Reply APIトークンの
  制約に起因する再試行不可のケースの扱い

## 実装状況(2026-08-18時点)
- `LlmApiError`/`ReplyApiError`例外・`_generate_with_api_retry()`/`_reply_with_retry()`
  (即時1回のみリトライ)・`API_FAILURE_FALLBACK_MESSAGE`・`MemoProcessResult.api_failure`を
  `prototype/cloud_function_webhook.py`に実装した。`FlakyOnceLlmClient`/
  `AlwaysFailingLlmClient`/`FlakyOnceReplyClient`/`AlwaysFailingReplyClient`スタブを
  `prototype/test_cloud_function_webhook.py`に追加し、(1)LLM API呼び出し失敗→即時リトライで
  成功、(2)2回とも失敗→API_FAILURE_FALLBACK_MESSAGEで返信、(3)Reply API呼び出し失敗→
  即時リトライで成功、(4)2回とも失敗→reply_sent=Falseで例外を投げずに諦める、の4パターンを
  テストで確認した(全45件パス)。実クラウド接続なしで机上完結する範囲はこの設計ドキュメントの
  範囲で対応済みとなる。

## 未検証・要検討事項
- Reply APIトークンの失効後・使用済み後の消費有無(失敗レスポンス時にトークン自体が消費済み
  扱いになるか)は、course-set-pashaと同様WebFetchのegress制約によりLINE公式ドキュメントの
  一次情報で確認できていない。実LINE接続後に必ず一次情報で再確認する。
- `llm_call.generate()`の合計呼び出し回数上限(最大4回)がWebhookタイムアウト時間内に
  収まるかは、実LLM接続後のレイテンシ実測待ち。
- 実LLM/実LINE API接続自体がオーナー承認待ちのため(pending-approval.md参照)、実クライアント
  接続後にこの設計・実装が想定通り機能するかの再検証が引き続き必要。
