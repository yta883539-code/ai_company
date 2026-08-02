# Webhook応答遅延対策・非同期処理設計

## 背景
hosting-platform-selection.mdの「未確定・今後の課題」に残っていた
「Cloud FunctionsからLINE Messaging API・LLM APIへの外向き通信のタイムアウト設計
(LLM応答待ちでWebhook応答が遅延した場合の挙動)は未検討」に対応する。

実際のGCPプロジェクト作成・Cloud Functionsのデプロイは「アカウント作成」に該当し
オーナー承認待ちのため、本ドキュメントは処理方式の机上設計に留める。

## 問題の整理
- LINE Platformは、Webhookイベント送信後にBotサーバーからの応答(HTTP 200)を
  一定時間内に受け取れないと、そのイベントを再送する場合がある(タイムアウト値は
  LINE側の実装依存で公開ドキュメント上も明確な秒数保証はないため、こちらで
  「遅くとも数秒台で200を返す」ことを設計上の目標とする)。応答が遅れて再送が
  発生すると、`ConversationFlowStateMachine`側で同一イベントを二重処理して
  しまうリスクがある。
- 顧客への実際の返信文言(会話フローのメッセージ)は、LLM構造化出力
  (llm-system-prompt-draft.md)を得てから`intent-to-flow-mapping.md`の対応表に
  従って`select_slot_from_reply()`等を呼び出し、`_render_by_tone()`経由で
  整形される。実LLM呼び出しは数百ms〜数秒、混雑時はさらに長くなりうる不確実な
  待ち時間であり、Webhookの200応答をこの処理完了まで待ってから返すのは
  遅延の原因になる。
- LINEの「応答メッセージ(reply API)」は、Webhookイベントに同梱される
  `replyToken`を使って送るワンタイムトークンであり、有効期限が短く
  (公式にも「速やかに」の利用が推奨されている)、LLM処理の完了を待ってから
  reply APIを呼ぶ設計は失敗時(トークン失効)のリカバリが難しい。

## 採用方式: Webhook即時ACK + 非同期処理 + プッシュメッセージ応答
1. Cloud Functionsのエントリポイントは、LINEの署名検証(`X-Line-Signature`)と
   イベントの構造チェックのみを同期的に行い、**LLM呼び出し・会話フロー処理を
   待たずにHTTP 200を返す**(reply APIは使わない方針とする)。
2. 署名検証後、イベント本体(`userId`・`replyToken`は使わず`userId`のみ)を
   Cloud Tasksキューに積んで即座に処理を終える。Cloud Tasksを使う理由は、
   Cloud Functions単体の「バックグラウンド処理継続」に制約がある
   (レスポンス送信後の処理継続はランタイム保証がない)ため、確実に非同期実行
   したい処理は別関数呼び出しとして再度キューイングする方が信頼性が高いため。
3. キューから起動される第2の関数(`process_conversation_event`相当)が、
   実際のLLM呼び出し・`ConversationFlowStateMachine`の状態遷移・
   `_render_by_tone()`によるメッセージ整形を行い、完了したら
   **LINEのプッシュメッセージAPI(`/v2/bot/message/push`)** で`userId`宛てに
   送信する。reply APIではなくpush APIを使うことで、処理時間がLLM待ちで
   数秒〜十数秒かかっても失効の心配がない(push APIは月間無料メッセージ数の
   対象でありline-api-pricing.mdの料金枠内で扱う)。
4. 上記2段構成により、Webhook自体の応答時間はLLM呼び出しの遅延から完全に
   切り離され、LINE側の再送(=イベント二重発火)リスクを実質的に解消できる。

```
LINE Platform
   │ Webhook (event)
   ▼
[Cloud Function A: receive_webhook]
   - 署名検証
   - イベント構造チェック
   - Cloud Tasksへenqueue
   - 200 OK を即返却  ← ここでLLM処理を待たない
   │
   ▼ (Cloud Tasks経由で非同期起動)
[Cloud Function B: process_conversation_event]
   - LLM呼び出し(llm_call、現状はスタブ)
   - ConversationFlowStateMachineの状態遷移
   - _render_by_tone()でメッセージ整形
   - LINE Push Message APIで送信
```

## 二重処理対策
- 3.の設計だけではLINE側の再送(まれに発生しうる)によりCloud Function Aが
  同一イベントで2回起動するケースは残る。Cloud Tasksのタスク名に
  `userId + イベントのタイムスタンプ(またはLINEの`webhookEventId`相当)`から
  導出した決定的なIDを指定することで、Cloud Tasks側の重複排除
  (同名タスクは一定期間再エンキューされない)を利用し、Aが2回起動しても
  Bの実処理は1回に抑えられる設計とする。
- `idle-conversation-trigger-design.md`の「Webhook便乗トリガー」
  (`maybe_run_idle_cleanup()`/`maybe_run_archive()`)は、Cloud Function A側
  (即時ACKする方)で引き続き便乗させる。これらは読み取り主体で処理が軽く、
  Aの応答時間に大きな影響を与えないため、Bへ分離する必要はないと判断する。

## 既存設計への影響
- `intent-to-flow-mapping.md`・`llm-system-prompt-draft.md`等の会話フロー
  ロジック自体(engine.py側)への変更は不要。今回はロジックの「呼び出され方」
  (同期Webhookハンドラ内 → 非同期タスクハンドラ内)が変わるだけで、
  `ConversationFlowStateMachine`のインターフェースはそのまま利用できる。
- `replyToken`をそのまま使う設計ではなくなるため、将来「候補提示直後のような
  低レイテンシで返せるケースだけreply APIで即答し、LLM待ちが発生するケースのみ
  push APIに回す」ハイブリッド化も選択肢としてはあり得るが、経路が2つに
  分岐する分だけ実装・テストが複雑になるため、MVPでは全件push API方式に統一し
  シンプルさを優先する。

## 残課題
- Cloud Tasksの導入自体もGCPの追加サービスであり、実際のキュー作成・
  デプロイはGCPプロジェクト作成(オーナー承認待ち)後の課題として残す。
- push APIはLINE公式アカウントの無料メッセージ数枠の対象となるため、
  line-api-pricing.md・firestore-traffic-cost-estimate.mdで試算済みの
  メッセージ通数試算に「reply APIではなくpush APIを使う」前提が反映されて
  いるかの整合確認は未着手(現状の試算はメッセージ通数ベースのため大きな
  差異は出ない見込みだが、要再確認)。
- タスク名の重複排除キーの具体的な生成方法(LINEのWebhookイベントに含まれる
  一意なイベントIDの有無の確認)はLINE Messaging APIドキュメントの
  詳細調査が必要で未着手。
