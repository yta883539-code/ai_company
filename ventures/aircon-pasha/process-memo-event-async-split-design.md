# process_memo_event() のWebhook即時ACK・2関数構成への翻案設計

## 背景

line-webhook-event-id-idempotency-design.md(フェーズ379)で、本ventureが
course-set-pasha・kura-pashaと同じ「reply API + 同期LLM呼び出し」構成であることを
確認し、course-set-pashaのFunction A/B分割設計(process-memo-event-async-split-design.md、
course-set-pashaフェーズ370〜372で設計・実装済み)をmessageイベントのみ対象にそのまま
翻案可能と判断した(フェーズ379「次回候補(1)」)。本書はその翻案設計を行う。
実装・デプロイは実GCPプロジェクト作成(オーナー承認待ち、pending-approval.md参照)後の
課題として残し、本書は机上設計のみ行う。

## 現状の分岐構造(process_memo_event()、prototype/cloud_function_webhook.py:925)

1. `message.type != "text"` → 対象外、返信なし。
1.5. 本文が「FAQ」または「Q1」〜「Q7」に一致 → LLM呼び出しなし、
   `owner_faq_router.py`の固定文言を即返信して終了。
1.6. `intent_classifier`接続時: 自由入力の意図分類(`classify()`自体がLLM呼び出し)を行い、
   `faq_guidance_candidate`・`other_needs_human`は`route_chatbot_intent()`に委譲して終了
   (後者は`escalation_push_client`経由で運営者への即時通知も伴う)。
   `completion_report_request`、または分類失敗時は下の生成フローへフォールスルー。
2. 上記いずれにも当たらない場合 → `llm_call`で完了報告・お手入れ案内・作業履歴の3点セットを
   生成(`_generate_with_api_retry()`) → 検証・1回だけ再生成 → 月間カウント・初回生成
   セルフチェック案内・トライアル終了通知・解約/決済手続き案内等の後処理 → 返信。

course-set-pashaの経路構成(FAQ固定応答/意図分類/投稿文生成)と経路の数・性質は一致している。
本ventureに固有の差異は、経路2(生成本体)の後処理が多い点(月間生成回数カウント・
トライアル終了通知・決済失敗/解約ブロック判定・postback誘導のquick_reply添付)だが、
これらはいずれも`llm_call`完了後の後処理であり、経路の同期/非同期振り分け判定自体には
影響しない(course-set-pasha「既存コードへの影響」節と同じ理由で、`process_memo_event()`
本体のロジックは変更不要という結論に変わりはない)。

## 経路ごとのレイテンシ特性の整理

- 経路1.5(FAQ固定応答)はLLM呼び出しを一切含まず、文字列比較のみで完結するため、
  reply API(`replyToken`使用)で即時返信してもタイムアウトリスクはない。
- 経路1.6(意図分類)は`classify()`自体がLLM呼び出しであるため、
  course-set-pashaの経路3と同様に非同期化の対象に含める必要がある
  (`other_needs_human`時の運営者即時通知`send_chatbot_escalation_notification()`は
  push_client経由で既に非同期的な送達手段を使っているが、契約者への応答自体は
  現状`reply_client`経由のまま)。
- 経路2(生成本体)は従来から非同期化の主対象。

結論: **経路1.5のみ同期reply、経路1.6・2はまとめて非同期push**という2分岐で
Function A/Bを設計する(course-set-pashaと同じく、FAQ固定応答だけが「LLM呼び出しを
伴わない」唯一の例外であるため)。

## 採用方式

```
LINE Platform
   │ Webhook (event)
   ▼
[Cloud Function A: receive_webhook (本venture既存のエントリポイント)]
   - 署名検証(既存)
   - webhookEventId べき等性チェック(line-webhook-event-id-idempotency-design.md、
     フェーズ379実装済み、そのまま流用)
   - message.type=="text" かつ本文が「FAQ」/「Q1」〜「Q7」に一致する場合のみ、
     owner_faq_router.pyの固定文言をその場で組み立て、reply API
     (replyToken使用)で即時返信してこのイベントの処理を終える(LLM呼び出しなし)
   - 上記に該当しないtext/message系イベントは、イベント本体
     (userId・message本文・webhookEventId、replyTokenは使わない)を
     Cloud Tasksキューへenqueueし、200 OKを即返却する
   - follow/unfollow/postbackイベントは既存通り同期処理のまま(LLM呼び出しを含まないため
     非同期化の対象外。process_follow_event()/process_unfollow_event()/
     process_postback_event()は変更なし。postbackはCheckout Session発行等のStripe API
     呼び出しを伴うが、本設計の対象であるLLM呼び出し由来のreply token失効リスクとは
     別種の課題のため、本書のスコープ外とする)
   │
   ▼ (Cloud Tasks経由で非同期起動)
[Cloud Function B: process_memo_event_async (新設、既存process_memo_event()の
 「経路1.6・2相当」部分をそのまま呼び出す後継)]
   - intent_classifier.classify()呼び出し(接続時)→ completion_report_request以外は
     route_chatbot_intent()相当の処理を行い、結果をpush APIで送信
   - completion_report_request(または未接続時の既存フロー) → llm_call呼び出し →
     月間カウント・初回生成セルフチェック案内・トライアル終了通知・決済失敗/解約
     ブロック判定等の既存後処理 → push APIで送信(quick_replyのpostbackボタンも
     push APIのメッセージオブジェクトに同様に添付可能、line-reservation-ai既存設計で
     確認済みのpush API仕様に準拠)
```

## 既存コードへの影響

- `process_memo_event()`本体のロジック(経路1〜2の分岐・後処理・リトライ方針)は
  変更不要。Function Bからの呼び出され方(関数シグネチャはそのまま、`reply_client`の
  代わりに`push_client`を渡す形)に差し替えるだけで流用できる見込み
  (course-set-pashaフェーズ371の`PushBackedReplyClient`と同じアダプタパターンを
  そのまま翻案できる)。
- `dispatch_webhook_events()`は、イベントを「経路1.5相当(FAQ固定応答、同期)」と
  「それ以外(非同期キュー行き)」に振り分ける前処理を追加する必要がある。
  振り分け判定自体はFAQキーワード(「FAQ」/「Q1」〜「Q7」)の文字列比較のみでよく、
  既存の依存関係ガード(フェーズ260のintent_classifier関連ガード等)より前に行う。
- `webhook_event_id_store`によるべき等性チェック(フェーズ379)はFunction A側で
  従来通り適用する。Cloud Tasksのタスク名導出(`f"aircon-pasha-event-{webhook_event_id}"`等)
  についてはcourse-set-pashaフェーズ372の`make_memo_task_name()`パターンをそのまま
  流用できる。

## 残課題・次回候補

- ~~(1) Function Bの実装(`process_memo_event_async()`・`PushBackedReplyClient`、
  course-set-pashaフェーズ371相当の翻案、`prototype/cloud_function_webhook.py`)。
  InMemoryスタブでの机上検証が可能なため、実GCPプロジェクト作成の承認を待たずに
  着手できる。~~
  (解消済み 2026-11-13フェーズ381: README.md参照。)
- ~~(2) `dispatch_webhook_events()`へのFAQ/非FAQ振り分け前処理の実コード反映
  (`is_sync_faq_memo_event()`・`TaskQueueClient`/`InMemoryTaskQueueClient`の新設、
  course-set-pashaフェーズ372相当の翻案)。~~
  (解消済み 2026-11-13フェーズ382: 実装の過程で、本書「現状の分岐構造」節が
  `process_memo_event()`内部の経路1〜2のみを記述し、その手前の`process_message_event()`
  の連携判定(未連携ユーザーはLLM呼び出し不要)を見落としていたことが判明。
  `is_sync_faq_memo_event()`は「text以外」「未連携ユーザー」「FAQ一致」の3パターンを
  まとめて同期継続対象とするよう設計・実装し、このギャップを是正した。詳細は
  README.mdフェーズ382参照。)
- (3) Cloud Tasksキュー・Function Bの実デプロイは実GCPプロジェクト作成
  (オーナー承認待ち、pending-approval.md参照)後の課題として残る。
- ~~(4) event-komiguai-pasha・forklift-pasha・oshien-pashaの3ventureはまだ本横展開の
  検討対象になっていないため、べき等性対策の横展開(aircon-pashaフェーズ379
  「次回候補(3)」)と合わせて、それぞれが選ばれた回での検討対象とする。~~
  (対象外と確定 2026-11-14フェーズ383: 3venture各々のtech-stack.md(event-komiguai-pasha
  14〜20行目・forklift-pasha16〜30行目・oshien-pasha5〜7行目)を確認した結果、3venture
  いずれも入力チャネルがLINE非依存の汎用Webフォームであり、本書が対象とする
  `process_message_event()`/`process_memo_event()`のようなLINE Messaging API経由の
  自由入力メッセージ受信・FAQ/非FAQ振り分けという処理自体が存在しない(各venture
  prototype/配下にLINE Webhook関連ファイルがなく、`stripe_webhook.py`のみ)ことを確認
  した。したがって本横展開(FAQ/非FAQ振り分け・Function A/B分割)は3venture全てに
  ついて適用対象が存在せず、今回「検討対象として残す」ではなく対象外と確定する。
  なお、Stripe Webhookイベント単位のべき等性対策(aircon-pashaフェーズ379「次回候補(3)」
  = stripe-event-idempotency-design.md相当)は別軸の話であり、本書の対象外判断は
  そちらには影響しない(forklift-pashaフェーズ222で3venture個別に検討済み、既存の
  判断を参照)。)
