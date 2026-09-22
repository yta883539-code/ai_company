# チャットボット一次受付: `chatbot_intent_router.py`の`process_memo_event()`への結線 設計

作成日: 2026-09-22(定例更新フェーズ243)

chatbot-intent-classification-escalation-design.md 4節「残課題」が「呼び出し元(実LLM
接続後のWebhookハンドラ本体)からの実結線は引き続き未着手」として残していた点について、
`prototype/cloud_function_webhook.py`の`process_memo_event()`側の受け入れ方を設計する。
実装・実LLM呼び出しは行わない、机上の設計のみとする(design docの新規作成自体は
「投資・大規模」や外部接続を伴わないため、承認不要な作業として着手できる)。

## 1. 前提: 既存の類似Protocolパターンをそのまま踏襲する

`process_memo_event()`は既に`usage_counter`・`profile_store`・`gym_area_config_store`・
`first_generation_notice_store`など複数のProtocolを`Optional[...] = None`引数として受け取り、
「未接続時(None)は該当ロジックを丸ごとスキップし、既存呼び出し元・既存テストへの影響を
ゼロにする」という設計を徹底している(webhook-processing-flow-design.md準拠)。本結線も
同じパターンを踏襲し、新規引数`intent_classifier: Optional[ChatbotIntentClassifierProtocol]
= None`を追加するのみとする。既存630件超のテストは`intent_classifier`を渡さないため、
本結線の追加によって一切の回帰が生じない設計とする。

```python
class ChatbotIntentClassifierProtocol(Protocol):
    def classify(self, memo_text: str) -> str:
        """自由入力テキストをCHATBOT_INTENT_VALUES(5分類)のいずれかへ分類する。
        実装は実LLM呼び出しを伴うため、承認後に実クライアントで差し替える
        (llm_callと同じ位置づけ)。"""
        ...
```

## 2. 挿入位置: 9ステップ処理フロー中の位置づけ

`process_memo_event()`のdocstringが列挙する既存フロー(1〜9)のうち、本結線は
「3. LLM呼び出し結果を検証し...」の直前、すなわち`_generate_with_api_retry()`を
呼び出す直前に挿入する。理由は以下の通り。

- **2.5(owner_faq明示コマンド)より後**: 「FAQ」「Q1」〜「Q6」等の明示コマンドは
  LLM呼び出し(分類含む)を一切要さない決定的な文字列一致であり、コストゼロで
  即座に応答できる。自由入力の意図分類(将来LLMコストを伴う)より優先し、既存の
  判定順序・既存テストを変更しない。
- **生成一時停止判定(8)・決済失敗制限モード判定(9)より後**: これら2つの安全側の
  早期リターンは「LLM呼び出し自体を一切行わない」ことを主眼としており、
  chatbot-intent-classification-escalation-design.md側でも一時停止・制限モード中の
  意図分類自体を想定していない。既存の判定順序をそのまま維持し、一時停止・制限
  モード中は意図分類(将来的にLLM呼び出しを伴いうる)も行わない。
- **`_generate_with_api_retry()`呼び出しの直前**: 上記いずれにも該当しない場合のみ
  意図分類を行い、分類結果に応じて「投稿文生成へ進む」か「FAQ回答/エスカレーション
  で処理を完結する」かを分岐する。

## 3. 分岐ロジック

```python
if intent_classifier is not None:
    intent = intent_classifier.classify(memo_text)
    if intent != "post_generation_request":
        reply_text = route_chatbot_intent(
            intent,
            user_id=user_id_for_pause_check,
            memo_text=memo_text,
            push_client=escalation_push_client,  # 新規Optional引数、後述
        )
        reply_sent = _reply_with_retry(reply_client, reply_token, reply_text)
        return MemoProcessResult(
            handled=True, reply_sent=reply_sent,
            reply_text=reply_text if reply_sent else None,
            chatbot_intent=intent,
        )
    # post_generation_request: 何もせず下の既存フローへフォールスルー
```

- `intent == "post_generation_request"`の場合は分岐せず既存フロー(LLM呼び出し・
  検証・カウント増分等)へそのままフォールスルーする。`route_chatbot_intent()`の
  `post_generation_request`分岐(`append_faq_followup_hint()`を適用する経路)は
  ここでは使わない。理由は、`append_faq_followup_hint()`は生成成功後の`reply_text`
  組み立て(`format_reply_text()`呼び出し後)に対して行う後処理であり、生成前の
  この時点では適用対象の文字列がまだ存在しないため。既存の`format_reply_text()`
  呼び出し箇所(4節)の直後に`append_faq_followup_hint()`を適用する形で別途
  結線する(4節参照)。
- FAQ 3分類・`other_needs_human`は`route_chatbot_intent()`にそのまま委譲し、
  LLM呼び出し・月間カウント増分・トライアル判定等は一切行わない(2.5節の明示
  コマンドと同じ扱い)。
- `other_needs_human`の運営者通知(`send_chatbot_escalation_notification()`)は
  `push_client`(LINE Push API、返信用の`reply_client`とは別チャネル)を要求する。
  `process_memo_event()`に新規Optional引数`escalation_push_client:
  Optional[LinePushClient] = None`を追加し、Noneの場合(未接続時)は
  `route_chatbot_intent()`呼び出し自体をスキップして安全側にフォールバックする
  (下記4点目参照)。

## 4. `post_generation_request`時の`append_faq_followup_hint()`結線

意図分類が有効(`intent_classifier`が渡されている)かつ分類結果が
`post_generation_request`だった場合のみ、既存の`reply_text = format_reply_text(...)`
呼び出し直後に`reply_text = append_faq_followup_hint(reply_text)`を適用する
(status=="generated"の場合のみ。cancellation_intent等の既存分岐にはFAQ折り返し
文言は不要なため対象外とする)。`intent_classifier`未指定時(既存呼び出し元)は
この後処理自体を行わず、既存の返信文言を一切変更しない。

## 5. 未解決点・安全側フォールバック

- `escalation_push_client`が`None`のまま`intent_classifier`が`other_needs_human`を
  返した場合の挙動: `send_chatbot_escalation_notification()`は`push_client`必須の
  ため呼び出せない。この場合は運営者通知を送らずに`OTHER_NEEDS_HUMAN_CUSTOMER_REPLY_
  TEXT`のみ顧客へ返す(通知漏れよりも無応答放置を避けることを優先する、3節
  design.mdの主眼と同じ考え方)。ただし本ケースは運用上「意図分類は有効だが
  エスカレーション通知は未接続」という中途半端な組み合わせであり、実際には
  `intent_classifier`と`escalation_push_client`は同じタイミング(実LLM接続・実LINE
  Push接続完了時)で揃って渡される想定のため、この分岐が実運用で発生する可能性は
  低い。
- 意図分類自体の失敗(LLM API呼び出しエラー)時のフォールバックは未設計。
  `classify()`が例外を送出した場合にどう扱うか(post_generation_request扱いに
  倒すか、API_FAILURE_FALLBACK_MESSAGEを返すか)は、実装時に
  `_generate_with_api_retry()`と同様の即時リトライ方針を適用するかどうか含め、
  次回以降の課題とする。
- `MemoProcessResult`への`chatbot_intent: Optional[str] = None`フィールド追加、
  および`test_cloud_function_webhook.py`への新規テストクラス(スタブ
  `ChatbotIntentClassifierProtocol`実装+`InMemoryLinePushClient`を用い、
  (a)`intent_classifier`未指定時は既存630件超の挙動が一切変わらないこと、
  (b)FAQ 3分類それぞれで`llm_call`が一度も呼ばれないこと、(c)`other_needs_human`で
  `escalation_push_client`にメッセージが送られ顧客への返信が定型文になること、
  (d)`post_generation_request`では既存の生成フローへフォールスルーし
  `append_faq_followup_hint()`が末尾に適用されること、を検証するテストの追加)は、
  本設計に基づく次回以降の実装フェーズで行う。

## 6. 実装状況(フェーズ244で追記)

上記1〜5節の設計に基づき、`prototype/cloud_function_webhook.py`の
`process_memo_event()`に`intent_classifier`・`escalation_push_client`の2引数を
Optionalで追加し、実装した。

- `ChatbotIntentClassifierProtocol`を`MemoProcessResult`定義の直前に新規追加(design 1節)。
- 挿入位置は設計通り、決済失敗制限モード判定(9)より後・`_generate_with_api_retry()`
  呼び出しの直前(design 2節)。
- 分岐ロジックは設計3節の通り実装。ただし`other_needs_human`かつ
  `escalation_push_client is None`の場合は`route_chatbot_intent()`を呼ばず(push_client
  必須でValueErrorになるため)、`OTHER_NEEDS_HUMAN_CUSTOMER_REPLY_TEXT`を直接返す
  分岐を明示的に実装した(design 5節の安全側フォールバックをコード化)。
- `post_generation_request`時の`append_faq_followup_hint()`結線は設計4節の通り、
  `format_reply_text()`呼び出し直後・`status=="generated"`の場合のみ適用。
- `MemoProcessResult.chatbot_intent`フィールドを追加し、早期リターン分岐・最終的な
  生成成功時の返却の両方に設定した(検証エラー等の中間フォールバック分岐には設定
  していない。design側で明示されていた範囲外のため今回は対象外とした)。
- `test_cloud_function_webhook.py`に`ChatbotIntentRouterWiringTest`(9ケース)を新規
  追加し、design 5節が挙げた(a)〜(d)の観点をいずれもカバーした。
- 回帰確認としてventure全体643件(634件→643件)・schema検証21件、いずれもパス
  (変更前と同じ結果)を確認した。
- 未解決のまま残る点(design 5節と同じ):意図分類自体(`classify()`)が例外を送出した
  場合のフォールバックは未実装。実LLM接続時に`_generate_with_api_retry()`と同様の
  即時リトライ方針を適用するかは次回以降の課題。また`dispatch_webhook_events()`から
  `process_memo_event()`への`intent_classifier`・`escalation_push_client`の受け渡しは
  本フェーズの設計・実装スコープ外(design自体が`process_memo_event()`単体への結線に
  限定していたため)であり、実LLM・実LINE Push接続時にあわせて別途結線が必要。
