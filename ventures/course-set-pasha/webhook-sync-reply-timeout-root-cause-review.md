# Webhook同期reply構成のタイムアウトリスク・根本対策要否の検討

## 背景

line-webhook-event-id-idempotency-design.md(フェーズ368、kura-pasha版の翻案として
本venture向けに新規作成)の「4. 未検証・残課題」に、以下が未着手事項として残っていた。

> 根本対策の要否: 本対策(べき等性チェック)は「重複実行を防ぐ」対症療法であり、
> 「2秒タイムアウトに収まるよう処理自体を非同期化する」(line-reservation-aiのCloud
> Tasksエンキューパターンへの移行)という根本対策とは別物。後者はdeployment-
> runbook.mdのFunction分割を要するアーキテクチャ変更であり、本ventureの処理量
> (月額フリーパス・都度プラン利用者向けの単発メモ処理)を踏まえると費用対効果の
> 検討が必要なため、今回は対症療法(べき等性チェック)のみを先行させる。

本フェーズ(7venture中最も更新が止まっていた本ventureの前進)は、この残課題
(根本対策の費用対効果検討)に着手する。

## 1. 現状の整理

`prototype/cloud_function_webhook.py`の`process_memo_event()`は、以下の経路をすべて
**1回のLINE Webhook受信(1回のCloud Function実行)内で同期的に**処理し、最後に
`reply_client.reply(reply_token, ...)`(replyToken方式)で返信する設計になっている
(deployment-runbook.mdステップ4準拠)。

1. (2.5節) `owner-faq-routing-design.md`準拠のFAQ固定応答(LLM呼び出しなし、
   処理は軽量)。
2. (2.6節) `intent_classifier`による自由入力テキストの意図分類(LLM呼び出しあり、
   構造化出力は`chatbot-intent-classification-llm-prompt-draft.md`準拠の単純な
   分類タスクのため応答は比較的軽量)。分類結果がFAQ系・`other_needs_human`の場合は
   ここで終了。
3. 分類結果が`post_generation_request`(通常のメモ投稿)の場合、本題のLLM呼び出し
   (`llm_system_prompt_draft.md`準拠、SNS投稿文・LINE/Web告知文・課題入れ替え履歴
   記録の3点セットを1回の構造化出力で生成)を行い、生成結果を整形して返信する。

`content-generation-time-estimate.md`の前提部分に「AIによる生成自体は数秒〜数十秒で
完了」という記述があり、これは本venture自身の既存ドキュメントが、3.の本題LLM呼び出し
がLINEの実タイムアウト(2秒、line-webhook-event-id-idempotency-design.md 1節で確認済み、
LINE公式Check webhook error statisticsの記載)を日常的に超えうることを既に示唆していた
ことになる(deployment-runbook.mdステップ4の「LLM呼び出し1回分がタイムアウト内に収まる
想定」という記述は、フェーズ368で「誤った前提」として訂正済み)。

## 2. べき等性チェック(フェーズ368)で解消済みのリスクと、残るリスクの切り分け

フェーズ368の`LineWebhookEventIdStoreProtocol`導入により、以下は解消済み。

- 同一`webhookEventId`の再送によるLLM呼び出し・`usage_counter`加算の重複実行
  (LLM APIコスト二重発生、生成回数カウントの不整合)。

一方、以下は未解消のまま残っている(べき等性チェックは「2回目以降の実行を止める」
対策であり、「1回目の実行自体がタイムアウト・reply失敗する」こと自体は防げない)。

- **reply失敗時にオーナーへ生成結果が届かないリスク**: LINEの「応答メッセージ
  (reply API)」が使う`replyToken`は有効期限が短い(LINE公式ドキュメント上も
  「速やかに」の利用が推奨されている、line-reservation-ai/webhook-async-processing-
  design.mdで確認済みの既存知見)。本題LLM呼び出し(3点セット生成、数秒〜数十秒)の
  完了を待ってから`reply_client.reply()`を呼ぶ現行設計では、LLM呼び出しが長引くと
  `replyToken`が失効し、**LLM呼び出し自体は成功していても返信が送れず、オーナーは
  課題入れ替え後に投稿文を受け取れない**(=サービスの中核価値が届かない)事故に
  直結する。これは「LLM APIコストの二重発生」のような副作用レベルの問題ではなく、
  利用者が実際に体験する機能不全であり、べき等性チェックとは独立に対処が必要。
- Webhook再送が有効化されている場合の`request_timeout`自体の記録(LINE側の
  エラー統計に残る)は実害は軽微だが、再送が無効な場合は上記のreply失敗がそのまま
  「無応答」として確定してしまう(再試行の機会がない)。

## 3. 費用対効果の検討

line-reservation-ai/webhook-async-processing-design.mdが採用した「Webhook即時ACK +
Cloud Tasksによる非同期処理 + push APIでの応答」方式を本ventureに適用する場合の
コストと効果を整理する。

**効果**: 2.で整理した「reply失効によるオーナーへの生成結果未達」事故を構造的に
解消できる(push APIはreplyTokenの失効制約を受けないため、LLM呼び出しが数秒〜
数十秒かかっても確実に送達できる)。

**コスト**:
- Cloud Functionsの2関数分割(A: 受信・署名検証・idempotency・enqueue、B: LLM呼び出し
  ・返信)、Cloud Tasksキューの新設が必要。line-reservation-aiが既に机上設計済みの
  パターンをそのまま翻案できるため、設計コスト自体は小さい(本ventureのFAQ固定応答・
  意図分類分岐も含めて、どこまでをA/Bのどちらに残すかの切り分けが主な検討事項になる
  見込み)。
- 実装・デプロイは実GCPプロジェクト作成(オーナー承認待ち)後でなければ着手できない
  点はべき等性チェックと同様。ただし**設計自体(机上設計)はGCPプロジェクト未承認の
  現時点でも進められる**(line-webhook-event-id-idempotency-design.mdと同じ位置づけ)。
- `process_memo_event()`はFAQ固定応答・意図分類分岐・本題生成の3経路を1つの関数に
  まとめているため、A/B分割時にどの経路をどちらの関数に置くかの設計判断が必要になる
  (例: FAQ固定応答はLLM呼び出しがなく処理が軽量なため、Aで即時reply APIのまま応答し
  Bへ回さない、という低レイテンシ経路と非同期経路のハイブリッド化も選択肢になる。
  line-reservation-ai/webhook-async-processing-design.md「既存設計への影響」節も
  同様のハイブリッド化を「経路が2つに分岐する分だけ実装・テストが複雑になるため、
  MVPでは見送り」と判断しており、本ventureでも同じ判断を踏襲するのが妥当と考える)。

## 4. 結論・推奨

2.で整理した「reply失効によるオーナーへの生成結果未達」は利用者が直接体験する
機能不全であり、起動後に実際に発生すれば初期の信頼を損ねかねないため、**根本対策
(Webhook即時ACK + Cloud Tasks非同期処理 + push API応答への移行)は実施すべきと判断
する**。ただし実装・デプロイは実GCPプロジェクト作成(オーナー承認待ち)後でなければ
着手できないため、本フェーズでは机上設計のみを次回候補として積み残す(line-
reservation-aiの既存設計を本venture向け〈FAQ固定応答・意図分類分岐・3点セット生成の
3経路の切り分けを含む〉に翻案する設計ドキュメントの新規作成)。

## 5. 残課題・次回候補

- 本ventureの`process_memo_event()`を、line-reservation-ai/webhook-async-processing-
  design.md準拠の2関数構成(A: 署名検証・idempotency・enqueue・即時200、
  B: LLM呼び出し・返信)に翻案する設計ドキュメントを新規作成する(FAQ固定応答・
  意図分類分岐をAに残すかBに回すかの判断を含む)。
- 設計確定後、実コード(`prototype/`配下)への反映は、Cloud Tasks自体はスタブ
  (InMemoryキュー相当)で机上検証可能なため、実GCPプロジェクト作成の承認を待たずに
  着手できる見込み(stripe_webhook.py・line_webhook_event_id_store同様、Protocol越しの
  差し替え設計とすることで検証を先行させる)。
- aircon-pasha・kura-pashaも同じ「reply API + 同期LLM呼び出し」構成であることが
  line-webhook-event-id-idempotency-design.md 1節で確認済みのため、本venture側の
  設計・実装が固まった段階で両ventureへの横展開も次回候補となる。
