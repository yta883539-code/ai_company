# process_memo_event() のWebhook即時ACK・2関数構成への翻案設計

## 背景
webhook-sync-reply-timeout-root-cause-review.md(フェーズ369)の結論を受け、
line-reservation-ai/webhook-async-processing-design.mdの「Webhook即時ACK+
Cloud Tasks非同期処理+Push API応答」パターンを、本venture固有の
`process_memo_event()`(prototype/cloud_function_webhook.py:1248)の実際の
分岐構造に合わせて翻案する。実装・デプロイは実GCPプロジェクト作成
(オーナー承認待ち、pending-approval.md参照)後の課題として残し、本書は
机上設計のみ行う。

## 現状の分岐構造(process_memo_event()、フェーズ368時点)
1. `message.type != "text"` → 対象外、返信なし
2. FAQ固定応答(本文が「FAQ」または「Q1」〜「Q6」) → LLM呼び出しなし、
   固定文言を即返信して終了(owner-faq-routing-design.md 2.5)
3. `intent_classifier`接続時: 自由入力の意図分類を行い、
   `post_generation_request`以外(FAQ 3分類・`other_needs_human`)は
   `route_chatbot_intent()`に委譲して終了。`classify()`自体がLLM呼び出しである点に注意。
4. 上記いずれにも当たらない場合(`post_generation_request`または
   `intent_classifier`未接続時の既存フロー) → `llm_call`で投稿文生成 → 月間カウント・
   初回生成案内・解約手続き案内等の後処理 → 返信

## 経路ごとのレイテンシ特性の整理
- 経路2(FAQ固定応答)はLLM呼び出しを一切含まず、文字列比較のみで完結するため、
  reply API(`replyToken`使用)で即時返信してもタイムアウトリスクはない。
- 経路3(意図分類)は`classify()`自体がLLM呼び出しであるため、
  webhook-sync-reply-timeout-root-cause-review.mdが指摘した
  「2秒タイムアウトに収まらない可能性」が経路4と同様に当てはまる。
  FAQ固定応答(経路2)とは異なり、非同期化の対象に含める必要がある。
- 経路4(投稿文生成本体)は従来から非同期化の主対象。

結論: **経路2のみ同期reply、経路3・4はまとめて非同期push**という2分岐で
Function A/Bを設計する(FAQ固定応答だけが「LLM呼び出しを伴わない」という
唯一の例外であるため)。

## 採用方式

```
LINE Platform
   │ Webhook (event)
   ▼
[Cloud Function A: receive_webhook (course-set-pasha既存のエントリポイント)]
   - 署名検証(既存)
   - webhookEventId べき等性チェック(line-webhook-event-id-idempotency-design.md、
     フェーズ368実装済み、そのまま流用)
   - message.type=="text" かつ本文が「FAQ」/「Q1」〜「Q6」に一致する場合のみ、
     owner-faq-routing-design.mdの固定文言をその場で組み立て、reply API
     (replyToken使用)で即時返信してこのイベントの処理を終える(LLM呼び出しなし)
   - 上記に該当しないtext/message系イベントは、イベント本体
     (userId・message本文・webhookEventId、replyTokenは使わない)を
     Cloud Tasksキューへenqueueし、200 OKを即返却する
   - follow/unfollowイベントは既存通り同期処理のまま(LLM呼び出しを含まないため
     非同期化の対象外。process_follow_event()/process_unfollow_event()は変更なし)
   │
   ▼ (Cloud Tasks経由で非同期起動)
[Cloud Function B: process_memo_event_async (新設、既存process_memo_event()の
 「経路3・4相当」部分をそのまま呼び出す後継)]
   - intent_classifier.classify()呼び出し(接続時)→ post_generation_request以外は
     route_chatbot_intent()相当の処理を行い、結果をpush APIで送信
   - post_generation_request(または未接続時の既存フロー) → llm_call呼び出し →
     月間カウント・初回生成案内・解約手続き案内等の既存後処理 → push APIで送信
```

## 既存コードへの影響
- `process_memo_event()`本体のロジック(経路1〜4の分岐・後処理・リトライ方針)は
  変更不要。Function Bからの呼び出され方(関数シグネチャはそのまま、
  `reply_client`の代わりに`push_client`を渡す形)に差し替えるだけで流用できる
  見込み(line-reservation-aiの既存設計と同じく、ロジック本体ではなく
  「呼び出され方」のみが変わる)。
- `dispatch_webhook_events()`は、イベントを「経路2相当(FAQ固定応答、同期)」と
  「それ以外(非同期キュー行き)」に振り分ける前処理を追加する必要がある。
  振り分け判定自体はFAQキーワードの文字列比較のみでよく、既存の
  `merge_text_and_photo_events()`によるテキスト・画像の束ね処理より前に
  行う(画像付きイベントはFAQ対象外と確定しているため)。
- `webhook_event_id_store`によるべき等性チェック(フェーズ368)はFunction A側で
  従来通り適用する。Cloud Tasksのタスク名導出(`f"course-set-pasha-event-
  {webhook_event_id}"`等)についてはline-reservation-ai/
  webhook-async-processing-design.md「二重処理対策」節の設計をそのまま流用できる。

## 残課題・次回候補
- (1) 【実装済み・フェーズ371】Function Bの実装(`process_memo_event_async()`・
  `PushBackedReplyClient`、prototype/cloud_function_webhook.py)。`process_memo_event()`
  本体は無変更のまま、`reply_client`を`PushBackedReplyClient`(push_client+固定user_idで
  `ReplyClient`プロトコルを満たすアダプタ)に差し替えるだけで流用できることを確認した。
  Cloud Tasksでは`replyToken`が伝播されない前提のため、`event`にそのキーが無くても動作する
  ことも確認済み。新規テスト4件(push送信への差し替え・replyTokenキー欠落時の動作・
  push失敗時の1回リトライ・FAQ固定応答経路の動作)を追加、既存882件と合わせ全886件パス
  (回帰なし)。
- (2) `dispatch_webhook_events()`へのFAQ/非FAQ振り分け前処理の実コード反映
  (新規テスト追加を含む)。
- (3) 設計確定後、aircon-pashaの同種部分(process_memo_event相当の同期実装)への
  横展開はcourse-set-pasha・kura-pasha・line-reservation-aiの状況を踏まえて
  別途検討する(aircon-pashaはpostbackアクション中心でFAQキーワード一致方式を
  採用していない可能性があるため、横展開前に各venture側の経路構造を
  個別確認する必要がある)。
- (4) Cloud Tasksキュー・Function Bの実デプロイは実GCPプロジェクト作成
  (オーナー承認待ち、pending-approval.md 2026-09-27 03・07時UTC・
  2026-09-28 20時UTC・2026-10-24 09時UTC記載分、および2026-11-08 08:00 UTC記載の
  運営方針確認依頼)後の課題として残る。
