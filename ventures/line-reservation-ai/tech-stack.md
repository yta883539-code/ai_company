# 技術構成案(初回メモ)

## 全体構成イメージ
LINE公式アカウント(Messaging API) ⇄ Webhookサーバー ⇄ LLM(予約意図の解釈) ⇄ 予約データストア(空き枠・予約台帳)

## 想定コンポーネント
1. **LINE Messaging API**
   - 顧客とのトーク送受信の入口。Webhookでメッセージを受信し、返信APIで応答する。
2. **Webhook / バックエンド**
   - サーバーレス関数(例: Cloud Functions / Lambda相当)を想定。低トラフィックなので従量課金で初期コストを抑えられる。
   - 2026-08-01 21:00 UTC時点でGCP Cloud Functions (Python) + Firestoreを第一候補として選定済み(hosting-platform-selection.md参照。AWS Lambda/DynamoDB・Cloudflare Workers・Fly.io等のコンテナ常駐PaaSと比較し、prototype/engine.pyのPython資産をそのまま活かせる点と無料枠の手厚さを決め手とした)。実際のGCPプロジェクト作成・請求先設定は着手時にオーナー承認が必要。
3. **LLM(自然文解釈)**
   - 顧客の自然文メッセージ→「希望日時・メニュー・氏名」等の構造化データに変換。
   - 空き枠候補の提示文言や、キャンセル・変更の意図分類もLLMに担わせる。
4. **予約データストア**
   - 事業者ごとの営業時間・メニュー・既存予約を保持する軽量DB(スプレッドシート的なシンプルさを重視)。
   - MVP段階では1シート=1店舗のスプレッドシート運用でも良い(開発コスト最小化)。
5. **管理画面(オーナー向け)**
   - 営業時間・メニュー・休業日の登録、予約一覧の確認用の簡易画面。MVPでは後回しにし、まずスプレッドシート直編集でも代替可能。

## MVPスコープ(最小構成)
- 対応メニューは1店舗あたり数種類まで
- 予約枠は「日付+時間帯」の固定スロット制(細かい時間指定は後回し)
- キャンセル・変更は簡易対応(LLMが意図検知→人間(オーナー)に通知して手動確認、を初期は許容)

## 初期投資・ランニングコストの目安
- 開発: 既存クラウドサービス・LLM APIの組み合わせのみで、専用インフラ購入は不要。
- ランニング: LINE Messaging APIの無料枠(月200通まで無料等、要最新料金確認)+ LLM API従量課金。
- 顧客数が少ない立ち上げ期は限界費用がほぼゼロに近い設計とする。

## 次のステップ候補
- ~~予約フローの会話サンプル(顧客⇄AI)を具体的に書き出す~~ → conversation-flow.md・conversation-samples-test-cases.md にて設計済み
- ~~二重予約防止のロジック設計~~ → double-booking-prevention.md・BookingSlotManager(prototype/engine.py)にて設計・実装済み
- ~~LINE Messaging APIの最新の料金・利用規約の確認(要web調査)~~ → line-api-pricing.md にて調査済み
- ~~ホスティング基盤の具体的な選定~~ → hosting-platform-selection.md にてGCP Cloud Functions + Firestoreを選定済み
- Firestoreのデータモデル(会話状態・予約枠・通知ログのコレクション設計)の具体化(未着手)
