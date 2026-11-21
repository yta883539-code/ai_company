# ステップ1・2の自由記述バリエーション(連絡先メール実入力・利用形態自由記述)トーク画面モックスクリプト

## 位置づけ

step1-2-linking-and-profile-collection-mock-script.md「次のステップ候補」が
持ち越していた2件のうち、(1)連絡先メールアドレスを実際に入力するケース、
(2)利用形態を自由記述で回答するケース、の2バリエーションを本ドキュメントで
対応する。実LINE公式アカウント・実LLM APIの接続・画像生成は一切行っていない。

## モック対象ケース

新しい事実確認・WebSearch調査は行わず、`prototype/cloud_function_webhook.py`
`_process_profile_collection_reply()`の既存実装(コード変更なし)の分岐を素材とした。

- 連絡先メールアドレス入力(`PROFILE_COLLECTION_STEP_AWAITING_EMAIL`):
  回答が`PROFILE_COLLECTION_EMAIL_NONE_ANSWER`(「なし」)と完全一致しない場合、
  `workshop_store.set_contact_email(workshop_id, answer_text)`で回答文字列が
  そのまま保存される分岐(540〜572行目)。
- 利用形態の自由記述回答(`PROFILE_COLLECTION_STEP_AWAITING_USAGE_TYPE`):
  回答が`PROFILE_COLLECTION_USAGE_TYPE_SOLO_ANSWER`(「個人のみ」)・
  `PROFILE_COLLECTION_USAGE_TYPE_MULTIPLE_ANSWER`(「複数人で利用予定」)の
  いずれとも完全一致しない場合、`resolved_usage_type = answer_text`として
  回答文字列がそのまま`expected_usage_type`に保存される分岐(577〜584行目、
  design.md 3節「未分類時は自由記述をそのまま保存」どおり)。

## トーク画面の見え方(案)

### ケースA: 連絡先メールアドレスを実際に入力する場合

```
(アプリから自動返信、PROFILE_COLLECTION_ASK_EMAIL_MESSAGE)
連絡先メールアドレスを教えてください(納品案内等の控えが必要な場合のみで構いません。
不要な場合は「なし」とお送りください)。

――――――――――――――――
(職人から送信)
isshin.kuragu@example.com

(アプリから自動返信、PROFILE_COLLECTION_ASK_USAGE_TYPE_MESSAGE)
複数の職人でご利用される予定はありますか?(「個人のみ」/「複数人で利用予定」の
いずれかでお答えください)
```

`isshin.kuragu@example.com`がそのまま`contact_email`として保存される
(「なし」との完全一致判定に該当しないため、形式チェック・正規化は行わず
入力文字列をそのまま保存する現行仕様どおり)。

### ケースB: 利用形態を自由記述で回答する場合

```
(アプリから自動返信、PROFILE_COLLECTION_ASK_USAGE_TYPE_MESSAGE)
複数の職人でご利用される予定はありますか?(「個人のみ」/「複数人で利用予定」の
いずれかでお答えください)

――――――――――――――――
(職人から送信)
今はひとりだけど、来月から弟子が1人入る予定なのでそのときに相談したい

(アプリから自動返信、PROFILE_COLLECTION_COMPLETED_MESSAGE)
ありがとうございます。続けて手順3(接続テスト)にお進みください。
```

回答文字列全文が`expected_usage_type`にそのまま保存され(2択の定型回答との
完全一致判定に該当しないため`resolved_usage_type = answer_text`に落ちる)、
完了メッセージの文言自体は定型回答時と変わらない(design.md 3節どおり、
自由記述の分類・要約処理は行わない)。

## 注記・限界

- いずれも`_process_profile_collection_reply()`に形式チェック・要約処理は
  実装されていないため、自由記述の内容がどれだけ長文・口語的であっても
  そのまま保存される。本モックスクリプトはこの「無加工でそのまま保存する」
  現行仕様を正しく反映していることの確認が目的であり、将来的に自由記述を
  LLMで要約・分類する機能追加が必要かどうかの検討は対象外とする。
- `contact_email`に実際のメールアドレスを保存した場合の、納品案内等での
  実際の送信先としての利用(メール送信機能自体)はcustomer-interview-design.md
  等で既に承認待ち事項として記録済みの範囲であり、本モックスクリプトでは
  トーク画面上の見え方のみを対象とする。

## 次のステップ候補

- 複数職人プラン(招待コードでの参加)のオンボーディング部分は
  step2-invite-code-join-mock-script.mdで既に対応済み。本ドキュメントにより
  step1-2-linking-and-profile-collection-mock-script.md「次のステップ候補」
  2件はいずれも解消した。
- 他venture・アイデア領域の前進を継続する。
