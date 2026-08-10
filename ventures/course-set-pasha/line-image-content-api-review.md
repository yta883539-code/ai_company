# LINE Messaging API画像メッセージ仕様の確認(コンテンツ取得API要否・複数画像添付時の扱い)

tech-stack.md・webhook-processing-flow-design.mdで「次回以降の課題」として残っていた、
LINE Messaging APIの画像メッセージ受信時のコンテンツ取得API仕様確認・複数画像添付時の扱いに
ついて、WebSearchで得られる公開情報と既存実装(prototype/cloud_function_webhook.py)を
突き合わせて整理する。

## 1. コンテンツ取得API(GET /v2/bot/message/{messageId}/content)は本ventureでは不要

LINE Messaging APIには、画像・動画・音声等のメッセージ本文(バイナリデータ)を取得する
専用エンドポイント(コンテンツ取得API)が存在する。しかし、tech-stack.md「想定コンポーネント」
4.で既に整理した通り、本ventureは画像そのものの内容解析(色・ホールド形状の自動認識等)を
行わない設計であり、LLMに渡すのも「画像が添付されたか否か」という有無フラグ(`hasPhoto`)
のみである。

merge_text_and_photo_events()(prototype/cloud_function_webhook.py)を確認すると、画像の
判定はWebhookイベント本体の`message.type == "image"`フィールドのみで行っており、
messageId自体はhasPhoto判定に使用していない。したがって、コンテンツ取得API(バイナリ
ダウンロード)は本ventureのMVPスコープでは呼び出す必要がない、という結論になる
(tech-stack.md「画像の一時保存」の想定通りだが、コンテンツ取得API自体を明示的に「不要」と
確認したのは今回が初めて)。

将来的に画像内容の自動解析(ホールド色・エリア自動認識等)を追加する場合にのみ、コンテンツ
取得API呼び出し・一時ストレージ設計(Cloud Storage等)の検討が必要になる。現時点ではMVP
スコープ外のため、tech-stack.md「次のステップ候補」からは除外してよい。

## 2. 複数画像添付時の扱いは既存のhasPhoto方式で対応済み

WebSearchで確認した範囲(LINE Developers公式ドキュメントの日本語解説記事等、Sources参照)
では、LINEアプリから複数枚の画像をまとめて送信した場合、画像1枚ごとに独立したメッセージ
イベント(それぞれ別のmessageId)としてWebhookに届くという扱いが一般的であり、1回の
Webhookリクエストに複数のイベントが含まれるケース自体はLINE Messaging APIの仕様として
想定されている(events配列で複数件を受け取る設計)。

これはtext-image-bundling-design.md「ケースA」(同一Webhookリクエスト内で複数イベントが
届く場合)の前提と一致する。merge_text_and_photo_events()は`photo_events`をリストとして
収集した上で`hasPhoto = bool(photo_events)`という有無判定のみを行うため、画像が1枚でも
複数枚でも同じ扱いになり、追加の実装変更は不要と確認できた。

- 本ventureの出力(SNS投稿文・告知文)は「画像の有無」にしか言及せず、画像の枚数や個々の
  内容には言及しない設計(llm-system-prompt-draft.md)のため、複数枚の画像を区別して扱う
  必要性自体がない。
- 例外的に、テキストメモが1件もなく画像イベントのみが複数件届いた場合(text_events数が0)は、
  merge_text_and_photo_events()の統合条件(`len(text_events) == 1`)を満たさず統合されないが、
  この場合は個々の画像イベントがprocess_memo_event()の「image-only event」処理(デモ済み、
  cloud_function_webhook.py末尾の`_demo()`参照)でそのまま素通りされるため、想定外の挙動には
  ならない。

## 結論

- コンテンツ取得API(バイナリダウンロード)は本ventureのMVPスコープでは不要と確認。
  tech-stack.md「次のステップ候補」の「画像コンテンツ取得API仕様確認」は解消済みとする。
- 複数画像添付時の扱いは、既存のhasPhoto(有無判定)方式で対応済みであり追加実装は不要。
- 残る不確定要素は、LINE公式ドキュメントの一次情報(developers.line.biz)がWebFetchで
  ネットワークegressプロキシによりブロックされ直接確認できなかった点(他ventureと同様の
  制約)。WebSearchのスニペット・二次情報源による整理にとどまるため、実LINE接続後に
  公式ドキュメントの一次情報で最終確認することが望ましい。

Sources:
- [メッセージ（Webhook）を受信する | LINE Developers](https://developers.line.biz/ja/docs/messaging-api/receiving-messages/)
- [Messaging APIリファレンス | LINE Developers](https://developers.line.biz/ja/reference/messaging-api/)
