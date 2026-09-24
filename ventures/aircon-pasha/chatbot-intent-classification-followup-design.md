# チャットボット一次受付: FAQ案内文・完了報告一言追加の実装(2026-09-24 定例更新フェーズ258)

chatbot-intent-classification-llm-prompt-draft.md(フェーズ257)「残課題」に残っていた
以下2点に対応した。

1. `faq_guidance_candidate`判定時に実際に返す案内文の具体的な文面
2. `completion_report_request`判定時への一言追加(course-set-pashaの
   `append_faq_followup_hint()`相当)

## 実装内容

`prototype/chatbot_intent_router.py`に純粋関数2件を新規実装した。

- `render_faq_guidance_message()`: `faq_guidance_candidate`判定時に返す案内文を返す。
  プロンプト草案「設計上の要点2」の方針どおり、`owner_faq_router.py`のQ1〜Q7個別回答文は
  含めず、項目を問わず同一の「FAQコマンドへの誘導文」のみとした。
- `append_faq_followup_hint(reply_text)`: `completion_report_request`判定時の返答文
  (完了報告書生成成功時の応答文)末尾に、FAQコマンドへの案内一言を常に付加する。
  プロンプト草案「設計上の要点5」が指摘した複合入力(完了報告メモとプラン質問等が
  同時に含まれる場合、判定順位1によりcompletion_report_requestと判定されFAQ案内文の
  提示が欠落する誤判定パターン)への運用回避であり、course-set-pashaがフェーズ238で
  採用したのと同じ「判定結果に関わらず常時付与する」方式を踏襲した(個別にFAQ相当の
  内容を含んでいたかを判定する方式は、判定順位1のフェイルセーフの単純さを崩すため
  不採用というcourse-set-pasha側の判断も踏襲)。

テスト6件を新規追加(`test_chatbot_intent_router.py`)、venture全体533件→539件、
schema検証25件いずれもパス。

## 対象外(次回以降の課題)

- `other_needs_human`判定時のエスカレーション導線(運営者への通知文言・送信経路、
  course-set-pashaのchatbot-intent-classification-escalation-design.md 3節相当)は
  本ドキュメントでは設計しない。本venture既存の`payment-suspension-owner-notification-
  design.md`(フェーズ255)の通知先(`OWNER_LINE_USER_ID_PLACEHOLDER`)・文言パターンを
  流用できる可能性が高い。
- 分類結果(category文字列)を受け取り、上記2関数・将来のエスカレーション通知へ実際に
  振り分ける入口関数(course-set-pashaの`route_chatbot_intent()`相当)は未実装。
  `cloud_function_webhook.py`側の`process_memo_event()`との結線も未着手。
- 実LLM API接続・実LINE送信はいずれもオーナー承認待ち(pending-approval.md
  2026-07-31 13:58 UTC記載と同種の位置づけ)のため未着手。
- kura-pashaへの同型の展開は、kura-pasha側の次回以降のフェーズとして申し送る
  (chatbot-first-response-feasibility.md 4節で既出の申し送り事項)。
