# チャットボット一次受付: other_needs_human エスカレーション導線 設計

作成日: 2026-09-25(定例更新フェーズ259)

chatbot-intent-classification-llm-prompt-draft.md(フェーズ257)「残課題」に残っていた
2点のうち、chatbot-intent-classification-followup-design.md(フェーズ258)で対応済みの
`faq_guidance_candidate`案内文・`completion_report_request`一言追加を除く、
`other_needs_human`判定時のエスカレーション導線(運営者への通知文言・送信経路)を設計する。
実装・実LLM呼び出し・実LINE接続は行わない、机上の設計のみとする。

## 1. 送信先・送信経路: 既存パターンの踏襲

course-set-pashaのchatbot-intent-classification-escalation-design.md 3節と同じ考え方で、
本venture内で既に確立済みの運営者通知パターンをそのまま踏襲し、新規のインフラ・外部
サービスアカウントは追加しない。

- **送信先**: `blocked_but_billing_owner_notification.OWNER_LINE_USER_ID_PLACEHOLDER`
  (payment_suspension_owner_notification.pyも同じ定数を再利用しており、本ventureの
  運営者宛送信先は単一の定数に集約されている。本設計もこの慣行を踏襲し、独自の定数は
  新設しない)。
- **送信経路**: `trial_end_scheduler.LinePushClient`プロトコル(`send_flex_message(
  user_id, alt_text, contents)`)をそのまま利用する。course-set-pasha版は`send_message
  (user_id, text)`という単純なテキスト送信インターフェースだが、本ventureの
  `LinePushClient`プロトコルは`payment_suspension_owner_notification.py`・
  `blocked_but_billing_owner_notification.py`がいずれも`send_flex_message()`のみを
  要求する設計であり、テキスト送信メソッドを持たない。本設計もこの慣行に合わせ、
  ボタンを持たないテキストのみのbubble形式のFlex Message(`build_payment_suspension_
  owner_notification_flex_message()`と同じ構成)を組み立てて送信する。

## 2. 検知条件・冪等性

course-set-pashaのchatbot-intent-classification-escalation-design.md 3節と同じ判断を
本ventureにも適用する。

- **検知条件**: 意図分類が`other_needs_human`と判定された時点。日次バッチではなく、
  該当メッセージ受信時にリアルタイムで通知する(決済失敗猶予期間のような日数条件は
  存在せず、契約者が今まさに応答を待っている状況のため)。
- **冪等性**: 1メッセージにつき1通知。同一契約者からの連続した`other_needs_human`判定は
  それぞれ別メッセージとして都度通知する(payment-suspension-owner-notification-design.md
  の「1回のみ送信」フラグとは異なり、本件はメッセージ単位のイベント通知のため、送信済み
  フラグによる重複排除の仕組みは持たない)。

## 3. 通知文言

course-set-pasha版の文言パターン(`[サービス名 運営]`接頭辞、契約者IDとメッセージ本文の
記載)を踏襲し、サービス名部分のみ本venture向けに置き換える。

```
[エアコンパシャッと運営] 一次受付チャットボットからのエスカレーション

以下の契約者からのメッセージが、FAQ・完了報告書生成のいずれにも自動分類されませんでした。
内容をご確認のうえ、必要に応じて個別にご対応ください。

契約者ID: {user_id}
メッセージ本文: {memo_text}
```

「顧客」ではなく「契約者」という呼称は、本venture既存のドキュメント群(owner-faq-
routing-design.md等)が一貫して「契約者」を使っている慣行に合わせた(course-set-pasha側の
「顧客」呼称とは異なるが、これは各ventureが既に定めた対象者呼称の違いをそのまま反映した
ものであり、意図的な差異である)。

## 4. 顧客(契約者)への応答との関係

`other_needs_human`判定時も、無応答のまま放置しない。契約者自身には運営者宛の通知文言とは
別の、定型の受付応答を返す。

```
お問い合わせありがとうございます。担当者が内容を確認しご連絡しますので、少々お待ちください。
```

course-set-pashaの`OTHER_NEEDS_HUMAN_CUSTOMER_REPLY_TEXT`と同一文言を採用する(対象読者が
「担当者からの個別連絡を待つ」という状況自体は両ventureで変わらないため、あえて別文言を
用意する理由がない)。

## 5. 入口関数: `route_chatbot_intent()`相当

`chatbot-intent-classification-followup-design.md`(フェーズ258)で実装済みの
`render_faq_guidance_message()`・`append_faq_followup_hint()`と、本ドキュメントで設計する
`send_chatbot_escalation_notification()`を、3分類それぞれの扱いに沿ってディスパッチする
入口関数を実装する(course-set-pashaの`route_chatbot_intent()`相当)。本venture固有の
差異は以下の2点。

- 本ventureは3分類(`completion_report_request`/`faq_guidance_candidate`/
  `other_needs_human`)のみであり、course-set-pasha版のようなFAQ項目別コード変換
  (`faq_intent_to_code()`)は不要。`faq_guidance_candidate`は常に
  `render_faq_guidance_message()`を返すのみ。
- `completion_report_request`判定時に渡される返答文(完了報告書生成本体、実LLM接続が
  オーナー承認待ちのため未実装)には`append_faq_followup_hint()`を適用する。

送信失敗時の扱いもcourse-set-pasha版と同じ考え方を踏襲する。`send_chatbot_escalation_
notification()`の戻り値(bool)はログ・監視目的で呼び出し元に判断を委ね、`route_chatbot_
intent()`自体は通知の成否にかかわらず同じ定型応答を契約者に返す(4節の応答を無条件で
返すことで「無応答のまま放置しない」という方針を優先する)。

## 6. 残課題

- 上記の通知文言・応答文言は実LLM呼び出し・実契約者サンプルなしの机上設計にとどまる。
  実運用データに基づく`other_needs_human`への分類頻度(通知過多にならないか)の確認は
  引き続き未着手。
- ~~`send_chatbot_escalation_notification()`・`route_chatbot_intent()`の実装
  (`prototype/`配下へのコード追加)は次回以降の課題とする。~~
  → フェーズ259で`prototype/chatbot_intent_router.py`として実装済み(テスト14件、
  `test_chatbot_intent_router.py`)。1節の方針どおり、送信インターフェースは
  `send_message(user_id, text)`ではなく`send_flex_message(user_id, alt_text,
  contents)`を採用し、`build_chatbot_escalation_notification_flex_message()`が
  `payment_suspension_owner_notification.py`と同じボタンなしbubble形式を組み立てる。
  `route_chatbot_intent()`は3分類それぞれを既存ヘルパー(`render_faq_guidance_
  message()`・`append_faq_followup_hint()`・`send_chatbot_escalation_
  notification()`)へディスパッチするのみで、各ヘルパーの内部ロジックは変更していない。
- `cloud_function_webhook.py`側からの実結線(実際にLLM分類結果を受け取り`route_chatbot_
  intent()`を呼び出す配線)は次回以降の課題として残す。
- kura-pasha側での同種チャットボット一次受付・エスカレーション導線の検討は未着手。
