# LLM API / LINE Reply API呼び出し自体の失敗時のハンドリング設計(2026-08-17時点)

## 背景
webhook-processing-flow-design.mdの`process_memo_event()`は「LLM応答は返ったが
JSON検証に失敗する」場合のリトライ(同一入力で1回だけ再生成)は設計済みだが、
「LLM API呼び出し自体が失敗する(タイムアウト・5xxエラー・レート制限429・
ネットワーク断)」「LINE Reply API呼び出し自体が失敗する」というケースは
明示的に検討されていなかった。line-reservation-aiのapi-call-failure-handling.mdと
同じ論点だが、本ventureは会話状態マシン・Cloud Tasksを持たない単発リクエスト/
レスポンス型(tech-stack.md)であるため、対応方針はline-reservation-aiとは
異なる設計になる。

## line-reservation-aiとの前提の違い(重要)
1. **Push APIではなくReply APIのみを使う**(tech-stack.md「想定コンポーネント1」)。
   Reply APIは`replyToken`が1回限り・有効期限は受信から短時間(数十秒〜1分程度、
   LINE公式ドキュメントの一次情報未確認のため概数)で失効する。line-reservation-aiは
   Push APIを使うためトークン失効の制約が無く「即時ACK→非同期処理→後からPush」が
   可能だったが、本ventureは「Webhook応答の中でReply APIを呼び切る」同期処理しか
   選択肢が無い。
2. **Cloud Tasks等の非同期リトライ基盤を持たない**(webhook-processing-flow-design.md
   「前提」)。line-reservation-aiの方針1(LLM呼び出し失敗時は例外を再送出しCloud Tasksの
   再試行に委ねる)はそのまま流用できない。
3. **送信者=事業者本人(オーナー・セッター)であり、顧客対応ではない**(README概要)。
   line-reservation-aiは「顧客が予約結果を知らないまま来店予定日を迎える」という
   重大な事業リスクがあったが、本ventureは状態変更(hold/confirm等)を一切持たない
   単発の文章生成ツールのため、返信が届かなかった場合の実害は「オーナー自身が
   気づいてメモを再送する」だけで済み、二重実行のリスクも無い(履歴記録は返信本文の
   一部として都度返すのみで、サーバー側に永続化された状態を変更しないため)。

## 想定される失敗パターン
1. LLM API呼び出しが失敗する(タイムアウト・5xx・429・ネットワーク断)。
   `llm_call.generate()`が例外を送出するケース。JSON検証失敗
   (`validate_llm_output()`がエラーを返すケース)とは異なり、応答自体を受け取れていない。
2. LINE Reply API呼び出しが失敗する(5xx・429・ネットワーク断)。
   `reply_client.reply()`が例外を送出するケース。

## 方針1: LLM API呼び出し失敗時
- Cloud Tasksが無いため、line-reservation-aiのように例外を上位へ再送出して外部の
  再試行基盤に委ねることはできない。`process_memo_event()`内で**同期的に**限定回数の
  リトライを行う必要がある。
- Webhook応答はLINE Platformへできる限り速やかに200を返すべきという制約
  (webhook-processing-flow-design.md「前提」)と、Reply APIトークンの短い有効期限を
  踏まえ、リトライは「即時1回のみ・待機なし」に限定する(line-reservation-aiの
  Cloud Tasks再試行のような数分〜数十分単位の間隔は取れない)。
  - 既存のJSON検証失敗時リトライ(同一入力で1回だけ再生成)とは目的も発生層も異なる
    別処理のため、合計の`llm_call.generate()`呼び出し回数の上限
    (API呼び出し失敗時リトライ1回 × 検証失敗時リトライ1回 = 最大4回)が
    Webhookのタイムアウト時間内に収まるかは、実LLM接続後にレイテンシ実測値で
    要検証(未検証事項として下記に残す)。
- 即時リトライも失敗した場合、`VALIDATION_FAILURE_FALLBACK_MESSAGE`と同様の位置づけで
  新設する`API_FAILURE_FALLBACK_MESSAGE`(例:「只今混み合っております。少し時間を
  おいて同じ内容をもう一度送ってください。」)を、まだ有効なはずの`reply_token`を使って
  返す。JSON検証失敗時のフォールバックと同じ「安全側に倒して定型文言を返す」設計方針を
  踏襲しつつ、原因(LLM応答なし)を区別できるよう`MemoProcessResult`に
  `api_failure: bool`フィールドを新設する案とする(検証失敗の`validation_errors`とは
  別カウントで集計できるようにする狙い)。
- line-reservation-aiのようなオーナーへのエスカレーション通知(EscalationConsolidator
  相当の仕組み)は、本ventureには現時点で存在しない(owner-notification-channel-design.md
  に相当するドキュメントは未作成)。send者本人が返信の有無を直接確認でき、失敗時は
  「もう一度メモを送る」という状態変更を伴わない安全な再試行が可能なため、MVPでは
  オーナー通知の仕組みを新設せずこのフォールバック文言のみで足りると判断する
  (顧客対応であるline-reservation-aiとの本質的な違いによるもの。将来、失敗頻度が
  無視できない水準になった場合はログ集計の仕組みを別途検討する)。

## 方針2: LINE Reply API呼び出し失敗時
- `reply_token`は1回限り使用可能という制約があるため、`reply_client.reply()`が
  例外を送出した場合、line-reservation-aiのPush APIのような「即時1回のみリトライ」を
  素朴に行うと、実装によっては失敗した呼び出し自体がトークンを消費してしまっている
  可能性がある(LINE Platform側の挙動次第で、失敗レスポンスがトークン消費とみなされる
  ケースと消費されないケースが考えられるが、公開情報未確認のため次項「未検証・要検討
  事項」に残す)。そのためリトライは「トークンが確実に未消費と判定できる場合のみ
  (例:リクエスト自体がタイムアウトしLINE側に到達したか不明な場合)即時1回」に限定し、
  4xx系のエラー(トークン無効・期限切れ等、明確に「送信済み or 失効」と判断できる
  レスポンス)を受け取った場合は即座に諦める、という条件分岐が必要になる。
- いずれにせよ再試行に失敗した(またはトークン失効が確定した)場合、Reply APIには
  代替の送達手段が無い(Push APIは導入していないため)。この場合、そのメモへの応答は
  失われる。ただし方針1と同じ理由(状態変更を伴わない・送信者本人が気づいて再送できる)
  により、事業影響はline-reservation-aiの「顧客が気づけないまま来店日を迎える」ケースより
  軽微と判断し、Push API導入(ユーザーIDの保存・追加のAPIスコープ取得が必要になり、
  tech-stack.mdが意図的に避けている永続データストアの追加を招く)は現時点では見送る。
- ログの記録自体(サーバーログへの出力)は状態変更でも外部接続でもないため、実装時に
  `reply_client.reply()`呼び出しをtry/exceptで囲み失敗を記録する処理は追加してよいと
  判断する(実LINE API接続後の課題として残す)。

## 既存設計との役割分担の整理
- json-output-retry-fallback.md相当(webhook-processing-flow-design.md手順5): LLM応答は
  得られたが中身(JSON)が不正・矛盾する場合 → 応答内容に対するリトライ・フォールバック
- 本ドキュメント: LLM/LINE Reply APIへの外向き呼び出し自体が失敗する場合 →
  呼び出し層の即時リトライ回数・失敗時のフォールバック文言・Reply APIトークンの
  制約に起因する再試行不可のケースの扱い

## 未検証・要検討事項
- Reply APIのトークン有効期限の正確な値、失敗レスポンス時にトークンが消費済み扱いに
  なるかどうかは、LINE公式ドキュメントの一次情報で確認が必要(line-image-content-api-review.md
  と同様、WebFetchのegress制約により今回は未確認)。実LINE接続後に必ず一次情報で
  再確認する。
- `llm_call.generate()`の合計呼び出し回数上限(最大4回)がWebhookタイムアウト時間内に
  収まるかは、実LLM接続後のレイテンシ実測待ち。
- `API_FAILURE_FALLBACK_MESSAGE`の新設・`MemoProcessResult.api_failure`フィールドの
  追加は設計のみでコード実装は次回以降とする(実LLM/実LINE API接続自体がオーナー
  承認待りのため、`llm_call.generate()`・`reply_client.reply()`を例外送出する
  スタブに差し替えたテストケースの追加は接続前でも机上で可能であり、次の一手の候補とする)。

## 次のステップ候補
- (解消済み 2026-08-17 07:00 UTC: 「未検証・要検討事項」最後の項目だった
  `LlmApiError`/`ReplyApiError`例外・`_generate_with_api_retry()`/
  `_reply_with_retry()`(即時1回のみリトライ)・`API_FAILURE_FALLBACK_MESSAGE`・
  `MemoProcessResult.api_failure`を`prototype/cloud_function_webhook.py`に実装した。
  `FlakyOnceLlmClient`/`AlwaysFailingLlmClient`/`FlakyOnceReplyClient`/
  `AlwaysFailingReplyClient`スタブを`prototype/test_cloud_function_webhook.py`に
  追加し、(1)LLM API呼び出し失敗→即時リトライで成功、(2)2回とも失敗→
  API_FAILURE_FALLBACK_MESSAGEで返信、(3)Reply API呼び出し失敗→即時リトライで成功、
  (4)2回とも失敗→reply_sent=Falseで例外を投げずに諦める、の4パターンをテストで確認した
  (全25件パス、venture全体では82件パス)。実クラウド接続なしで机上完結する範囲は
  この設計ドキュメントの範囲で対応済みとなり、残るのは「未検証・要検討事項」の
  Reply APIトークンの一次情報確認とレイテンシ実測(いずれも実LINE/実LLM接続後、
  オーナー承認待ち)のみ)
