# Webhook受信〜LLM呼び出し〜返信のバックエンド処理フロー設計

tech-stack.mdの「次のステップ候補」に残っていた、line-reservation-aiの
prototype/cloud_function_webhook.py相当のバックエンド処理フローの設計・試作に対応する。

## 前提(line-reservation-aiとの違い)

line-reservation-aiは「Webhook即時ACK → Cloud Tasksへenqueue → 非同期でLLM呼び出し・
会話状態更新」という2段構成(Cloud Function A/B分離)だったが、これは複数ユーザーの
会話状態を長時間(仮押さえタイムアウト・前日リマインド等)にわたって管理する必要が
あったための設計だった。本ventureはtech-stack.mdの通り会話状態マシンを持たない
単発リクエスト/レスポンス型(1メモ受信→LLM呼び出し→3出力生成→即時返信)のため、
Cloud Function A/Bの分離やCloud Tasksは不要と判断し、1つの処理フローに統合する。

ただし「LINE PlatformへのWebhook応答はできる限り速やかに200を返すべき」という制約自体は
共通のため、実クラウド接続時(オーナー承認後)にはLLM呼び出しの待ち時間をどう扱うか
(即時ACK+reply APIではなくpush APIを使う等)が別途課題になる。この点は実装方針のみ
ここで整理し、実クラウド接続自体は引き続き未着手とする。

## 処理フロー

1. **署名検証**: line-reservation-aiのverify_line_signature()と同じHMAC-SHA256検証を流用する
   (Python標準ライブラリのみで完結するため実装済み)。
2. **メッセージ種別の判定**: LINEのmessageイベントのうち`message.type == "text"`のみを
   本フローの対象とする。`message.type == "image"`単体のイベント(テキストなしで画像のみ
   送信された場合)は、本ステップでは「メモ本文が無いため処理対象外」として素通り
   (reply_client.reply()を呼ばず何もしない)扱いとする。
   - 理由: mvp-flow-draft.mdの入力仕様は「メモ本文+任意の画像」を前提としており、
     画像単体では厳守事項1(実際の課題設定内容の判断は行わない)の判断材料である
     テキスト情報が無いため、そもそもLLM入力を構成できない。
   - 残課題: 同一送信操作でテキスト+画像が別イベントとして届く場合の「同一メモとして
     束ねる」処理(束ねる基準・タイムアウト)は、tech-stack.mdの「次のステップ候補」に
     引き続き残す(LINE Messaging APIの画像コンテンツ取得API仕様確認と合わせて次回以降)。
     本フローでは`has_photo`をイベント側の付随情報(呼び出し側が別途解決した前提の
     真偽値引数)として受け取る形にとどめ、その解決方法自体は範囲外とする。
3. **LLM入力の構成**: メモ本文(`message.text`)と`has_photo`(呼び出し側から渡される)を
   `llm_call`(差し替え可能なProtocol、line-reservation-aiのllm_callスタブと同じ位置づけ)に渡す。
   llm-system-prompt-draft.mdの厳守事項に沿ったシステムプロンプトを付与するのは実LLM接続後の
   課題とし、本フローではllm_callの入出力インターフェースの確定のみを行う。
4. **構造化出力の検証**: schema/validate_test_cases.pyの`validate_against_schema()`・
   `validate_cross_field_rules()`をそのまま再利用してJSON Schema適合性とクロスフィールド
   ルールを検証する。status=="generated"の場合のみ、追加でprototype/post_generation_checks.py
   の`run_all_checks()`(厳守事項2・3・4・5・7・9のヒューリスティックチェック)を実行する。
5. **検証失敗時のリトライ・フォールバック**(2026-08-09 23:00 UTC追記): 検証エラーが
   1件でもあれば、line-reservation-aiのjson-output-retry-fallback.mdと同じ「同一入力で
   1回だけ再生成」方針で`llm_call.generate()`を`retry_context`(検証エラー概要)付きで
   再度呼び出す。再生成後も検証エラーが残る場合のみ安全側に倒し、定型の再送依頼文言を
   返す(＝insufficient_inputと同様の扱い)。本ventureには`confirmed`のような確定状態
   フィールドが無いため、line-reservation-ai側の「フォールバック経路はconfirmedを常に
   false扱いにする」に相当する分岐は不要。詳細はprototype/cloud_function_webhook.pyの
   `process_memo_event()`参照。
6. **返信本文の組み立て**: statusに応じて分岐する。
   - `generated`: 出力1(sns_post.body+hashtags)・出力2(line_web_notice.body)・
     出力3(history_rowsをhistory_export.history_rows_to_csv_text()でCSVテキスト化)の
     3つを、見出し付きで1通のテキストメッセージにまとめて返す(README冒頭の
     「3つをまとめて生成するサービス」という位置づけに合わせ、返信も1通にまとめる)。
   - `out_of_scope`: out_of_scope_messageをそのまま返す。
   - `insufficient_input`: missing_fields_requestをそのまま返す。
   - 検証失敗時(上記5): 定型の再送依頼文言を返す。
7. **送信**: line-reservation-aiと同様、reply_client(差し替え可能なProtocol)経由で送信する。
   実LINE API接続(reply API呼び出し)自体はオーナー承認待ちのため、本フローでは
   `InMemoryReplyClient`(送信内容を記録するだけのスタブ)のみを実装する。

## 実装

`prototype/cloud_function_webhook.py`に上記フローを実装した
(`process_memo_event()`が本体、`verify_line_signature()`はline-reservation-aiから移植)。
テストは`prototype/test_cloud_function_webhook.py`(generated/out_of_scope/
insufficient_input/検証失敗フォールバック/画像単体イベントの素通り、の各ケースをカバー)。

## 残課題

- (解消済み 2026-08-10 07:00 UTC: テキスト+画像が別イベントで届く場合の束ね方を
  text-image-bundling-design.mdで設計した。同一Webhookリクエスト内で束ねる
  「ケースA」は`merge_text_and_photo_events()`として実装済み。別リクエストに
  分かれる「ケースB」は、本ventureが意図的に会話状態マシンを持たない設計方針
  (tech-stack.md)であることを踏まえ、実測データが得られるまで実装を見送る判断とした)
- (解消済み 2026-08-09 23:00 UTC: 検証失敗時のリトライ機構を上記5に実装した)
- 実LLM呼び出し・実LINE API接続(オーナー承認待ち)。
