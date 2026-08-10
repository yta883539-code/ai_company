# 技術構成案(初回メモ)

mvp-flow-draft.md「会話フロー・技術構成に関する方針」で「技術構成の具体化は次回以降の課題」と
されていた点に対応する初回メモ。line-reservation-ai/tech-stack.mdの構成を踏襲しつつ、
本ventureは双方向の会話状態管理が不要な単方向バッチ処理である点を反映する。

## 全体構成イメージ

LINE公式アカウント(オーナー・セッター本人向け) ⇄ Webhookサーバー ⇄ LLM(3出力生成) ⇄ 返信メッセージ(下書きをそのまま返す)

line-reservation-aiと異なり、予約枠・会話状態を保持する永続データストアは不要。
「1メモ受信 → LLM呼び出し → 3種類のテキスト生成 → 返信」の単純なリクエスト/レスポンス型で完結する。

## 想定コンポーネント

1. **LINE Messaging API(入力受付・返信)**
   - オーナー・セッター本人が使う入力チャネル。顧客対応ではなく事業者本人向けの
     ツールである点がline-reservation-ai(顧客対応)と異なり、Botとの1:1トークで完結する。
   - テキストメモ+任意の画像メッセージ(1〜数枚)を受け付け、返信で3出力の下書きを
     まとめて送る。
2. **Webhook / バックエンド**
   - line-reservation-aiで選定済みのGCP Cloud Functions (Python)を第一候補として流用する
     (hosting-platform-selection.mdの比較結果を踏襲。低頻度・単発処理でサーバーレスの
     従量課金特性と相性が良い点は本ventureでも変わらない)。実際のGCPプロジェクト作成・
     請求先設定は着手時にオーナー承認が必要。
3. **LLM(3出力生成)**
   - 入力メモ(+画像有無)→ llm-system-prompt-draft.mdの厳守事項に沿って
     出力1(SNS投稿文)・出力2(LINE/Web告知文)・出力3(history_rows)をschema/output.schema.json
     の構造化出力形式で生成する。
   - 画像そのものの内容解析(色・ホールド形状の自動認識等)は行わず、「画像が添付されたか否か」
     という有無フラグ(`sns_post.mentions_photo`)のみを入力側で判定してLLMに渡す設計とする。
     line-reservation-aiが自然文の意図解釈にLLMを使うのに対し、本ventureは主に自然文生成に
     LLMを使う点が構成上の違い。
4. **画像の一時保存**
   - LINE Messaging APIの画像メッセージはコンテンツ取得API経由で一時的にダウンロード可能だが、
     本ventureでは画像自体をAIが解析・加工することはなく、あくまで「投稿時にオーナー自身が
     SNSへ添付する元データ」として使われる想定。そのため専用の永続ストレージ(Cloud Storage等)
     は不要とし、Webhook処理中の一時メモリ上の有無判定のみに用途を限定する
     (画像データ自体を保存・転送する必要が生じた場合は別途検討)。
5. **履歴記録の保存先**
   - schema/output.schema.jsonのhistory_rows配列は、prototype/history_export.pyで
     ヘッダー付きCSVテキストに変換し、LINE返信メッセージ本文の一部としてそのまま返す
     (history-export-usage-guide.md参照)。line-reservation-aiのFirestoreのような専用DBは
     持たず、オーナー・セッターがスプレッドシート等へ手動転記する運用を維持する。
   - 将来的に自動転記(スプレッドシートAPI連携等)が必要になった場合は、その時点で
     外部サービス接続としてオーナー承認を要する変更になる。

## MVPスコープ(最小構成)

- 入力は1メッセージ=1回のメモ(複数エリア同時更新はhistory_rows複数要素で対応済み、
  schema/output.schema.json・prototype/history_export.py参照)。
- 会話状態マシンは不要(line-reservation-aiのConversationFlowStateMachineに相当する
  仕組みは本ventureには存在しない)。
- 画像は「有無」のみを判定材料とし、画像内容の自動解析は範囲外。

## 初期投資・ランニングコストの目安

- 開発: 既存クラウドサービス・LLM APIの組み合わせのみで、専用インフラ購入は不要。
- ランニング: LINE Messaging APIの無料枠(最新の料金体系はline-reservation-ai/line-api-pricing.md・
  line-price-revision-2026-check.mdを参照し流用可能)+ LLM API従量課金のみ。
  永続データストアを持たない分、line-reservation-ai(Firestore利用)よりランニングコストは
  さらに低く抑えられる見込み。
- 顧客数(=導入ジム数)が少ない立ち上げ期は限界費用がほぼゼロに近い設計とする。

## 次のステップ候補

- (解消済み 2026-08-09 22:00 UTC: Webhook受信〜LLM呼び出し〜返信のバックエンド処理フローを
  webhook-processing-flow-design.md・prototype/cloud_function_webhook.pyとして設計・実装した)
- (解消済み 2026-08-10 07:00 UTC: テキスト+画像が別イベントで届く場合の束ね方を
  text-image-bundling-design.mdで設計した。同一Webhookリクエスト内で束ねる「ケースA」を
  merge_text_and_photo_events()として実装。別リクエストに分かれる「ケースB」の永続化は
  実測データが得られるまで見送り。複数画像添付時の扱い・画像コンテンツ取得API仕様確認
  自体は実LINE接続後の課題として引き続き残る)
- (解消済み 2026-08-10 11:00 UTC: 画像コンテンツ取得API仕様確認・複数画像添付時の扱いを
  line-image-content-api-review.mdで整理した。本ventureは画像内容を解析せず有無フラグのみ
  使う設計のため、コンテンツ取得API(バイナリダウンロード)自体がMVPスコープでは不要と結論。
  複数画像添付時も既存のhasPhoto方式で対応済みと確認。LINE公式ドキュメントの一次情報は
  WebFetchのegressプロキシ制約により未確認のため、実LINE接続後の最終確認は引き続き残る)
- 実LLM呼び出し・LINE公式アカウントとの実接続は、line-reservation-aiと同様に
  APIキー取得・アカウント作成が必要でありオーナー承認待ちの範囲。今回は技術構成の
  設計整理のみに留める。
