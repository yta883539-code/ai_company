# LLM API / LINE Reply API呼び出し自体の失敗時のハンドリング設計(2026-09-11時点)

## 背景

これまでの`process_memo_event()`の検討は「LLM応答は返ったが構造化出力(JSON)の検証に
失敗する」場合のリトライ(同一入力で1回だけ再生成、`validate_llm_output()`)にとどまり、
「LLM API呼び出し自体が失敗する(タイムアウト・5xxエラー・レート制限429・ネットワーク断)」
「LINE Reply API呼び出し自体が失敗する」というケースについて、aircon-pasha/
course-set-pashaのapi-call-failure-handling.mdに相当する設計文書が本ventureには
存在しなかった(cross-venture parityのギャップ)。

`prototype/cloud_function_webhook.py`を確認したところ、`LlmApiError`・`ReplyApiError`・
`_generate_with_api_retry()`・`_reply_with_retry()`・`API_FAILURE_FALLBACK_MESSAGE`・
`MemoProcessResult.api_failure`は、いずれもフェーズ不明の時点で既に実装済みであることが
判明した(docstringに「aircon-pasha/course-set-pashaのapi-call-failure-handling.md方針1と
同じ設計」との記載があり、両venture版を踏襲して実装されたと見られる)。本ドキュメントは、
実装済みのこの挙動を初めて文書化するとともに、テストカバレッジの不足(LLM API即時
リトライ成功系・Reply API失敗系が未検証だった)を解消したものである。

## 本ventureの前提

1. **Reply APIのみを使う**(`ReplyClient` Protocol、`reply_token`は1回限り・Webhook受信
   から短時間で失効)。会話状態マシン・Cloud Tasks等の非同期リトライ基盤を持たない
   単発リクエスト/レスポンス型のため、リトライは即時1回のみに限定する
   (aircon-pasha/course-set-pashaと同一の制約)。
2. **送信者=職人本人であり、顧客対応ではない**。返信が届かなかった場合の実害は
   「職人本人が気づいてメモを再送する」だけで済み、`process_memo_event()`は状態変更
   (`usage_counter_workshop.process_generation_request()`によるカウンタ更新を除く)を
   一切持たない単発の文章生成が中心のため、二重実行のリスクも小さい。
3. **3出力を1通に連結して返信する**(`format_generated_reply()`)本venture固有の構造
   のため、character-limit-fallback-design.md(フェーズ83)と同様、本ドキュメントの
   対象も「連結後の1回の`reply()`呼び出し」を単位とする。

## 想定される失敗パターン

1. LLM API呼び出しが失敗する(タイムアウト・5xx・429・ネットワーク断)。
   `llm_call.generate()`が`LlmApiError`を送出するケース。JSON検証失敗
   (`validate_llm_output()`がエラーを返すケース)とは異なり、応答自体を受け取れて
   いない。
2. LINE Reply API呼び出しが失敗する(5xx・429・ネットワーク断)。
   `reply_client.reply()`が`ReplyApiError`を送出するケース。

## 方針1: LLM API呼び出し失敗時

- Cloud Tasksが無いため、`process_memo_event()`内で**同期的に**限定回数のリトライを
  行う(`_generate_with_api_retry()`)。
- Webhook応答はLINE Platformへできる限り速やかに200を返すべきという制約と、Reply API
  トークンの短い有効期限を踏まえ、リトライは「即時1回のみ・待機なし」に限定する。
  - 既存のJSON検証失敗時リトライ(同一入力で1回だけ再生成)とは目的も発生層も異なる
    別処理のため、合計の`llm_call.generate()`呼び出し回数の上限(API呼び出し失敗時
    リトライ1回×検証失敗時リトライ1回=最大4回)がWebhookのタイムアウト時間内に
    収まるかは、実LLM接続後にレイテンシ実測値で要検証(aircon-pasha/course-set-pasha
    と同じ未検証事項、下記に残す)。
- 即時リトライも失敗した場合、`VALIDATION_FAILURE_FALLBACK_MESSAGE`と同様の位置づけで
  `API_FAILURE_FALLBACK_MESSAGE`(「只今混み合っております。少し時間をおいて同じ内容を
  もう一度送ってください。」)を、まだ有効なはずの`reply_token`を使って返す。
  `MemoProcessResult.api_failure`により、検証失敗の`validation_errors`とは別カウントで
  集計できる。
- aircon-pasha/course-set-pashaと同様、本ventureにもオーナー・職人へのエスカレーション
  通知の仕組みは現時点で存在しない。送信者本人が返信の有無を直接確認でき、失敗時は
  「もう一度メモを送る」という状態変更を伴わない安全な再試行が可能なため、MVPでは
  このフォールバック文言のみで足りると判断する。

## 方針2: LINE Reply API呼び出し失敗時

- `reply_token`は1回限り使用可能という制約があるため、`reply_client.reply()`が
  `ReplyApiError`を送出した場合の即時リトライは、他venture同様、リトライの安全性を
  完全には保証できない前提(失敗した呼び出し自体がトークンを消費してしまっている
  可能性があるが、LINE Platform側の挙動の一次情報は未確認)としつつも、Reply API以外に
  代替の送達手段を持たないMVPでは「即時1回のみリトライを試み、それでも失敗した場合は
  諦める」方針を採用する(`_reply_with_retry()`)。
- いずれにせよ再試行に失敗した(またはトークン失効が確定した)場合、Reply APIには
  代替の送達手段が無い(本venture固有の通知フロー〈blocked-but-billing-owner-
  notification-design.md・payment-failure-dunning-design.md等〉は`workshop`単位の
  Push APIクライアントを別途持つが、`process_memo_event()`自体はPush APIへの
  フォールバックを持たない)。この場合、そのメモへの応答は失われるが、方針1と同じ理由
  (状態変更を伴わない・送信者本人が気づいて再送できる)により、事業影響は軽微と
  判断する。`_reply_with_retry()`は例外を送出せず`reply_sent=False`(`reply_text=None`)
  を呼び出し元へ返す契約であり、`process_memo_event()`はこれをそのまま`MemoProcessResult`
  に反映する。

## 既存設計との役割分担の整理

- `validate_llm_output()`によるリトライ(既存): LLM応答は得られたが中身(JSON)が
  不正・矛盾する場合 → 応答内容に対するリトライ・フォールバック。
- character-limit-fallback-design.md(フェーズ83、既存): LLM応答・検証はいずれも
  成功したが、3出力連結後のテキストがLINE文字数上限を超える場合 → 送信直前の
  文字数チェックとフォールバック。
- 本ドキュメント: LLM/LINE Reply APIへの外向き呼び出し自体が失敗する場合 →
  呼び出し層の即時リトライ回数・失敗時のフォールバック文言・Reply APIトークンの
  制約に起因する再試行不可のケースの扱い。

## 実装・テスト状況(2026-09-11時点)

- `LlmApiError`/`ReplyApiError`例外・`_generate_with_api_retry()`/`_reply_with_retry()`
  (即時1回のみリトライ)・`API_FAILURE_FALLBACK_MESSAGE`・`MemoProcessResult.api_failure`は
  `prototype/cloud_function_webhook.py`に実装済みだった。
- 本フェーズで、既存テスト(`test_process_memo_event_falls_back_after_llm_api_error_
  retried_once`、LLM API連続失敗→フォールバックのみ検証)に加え、他venture相当の
  4パターン中欠けていた3パターンをテストスタブ(`_FlakyOnceLlmCall`・
  `_FlakyOnceReplyClient`・`_AlwaysFailingReplyClient`)とともに`prototype/
  test_cloud_function_webhook.py`へ新規追加した。
  1. LLM API呼び出し失敗→即時リトライで成功(`api_failure=False`のまま処理続行)。
  2. Reply API呼び出し失敗→即時リトライで成功(`reply_sent=True`)。
  3. Reply API呼び出し2回とも失敗→例外を投げず`reply_sent=False`で諦める。
  (「LLM API呼び出し2回とも失敗→フォールバック」の4パターン目は既存テストで確認済み。)
- 新規テスト11件(check()呼び出し単位)を追加し、`test_cloud_function_webhook.py`は
  265件→276件全件・venture全体schema検証27件いずれもパスを確認した。

## 未検証・要検討事項

- Reply APIトークンの失効後・使用済み後の消費有無(失敗レスポンス時にトークン自体が
  消費済み扱いになるか)は、他venture同様WebFetchのegress制約によりLINE公式ドキュメントの
  一次情報で確認できていない。実LINE接続後に必ず一次情報で再確認する。
- `llm_call.generate()`の合計呼び出し回数上限(最大4回)がWebhookタイムアウト時間内に
  収まるかは、実LLM接続後のレイテンシ実測待ち。
- 実LLM/実LINE API接続自体がオーナー承認待ちのため(pending-approval.md参照)、実クライアント
  接続後にこの設計・実装が想定通り機能するかの再検証が引き続き必要。
