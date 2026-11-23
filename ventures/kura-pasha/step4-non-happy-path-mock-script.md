# ステップ4(本番運用時のメモ送信)正常系以外のケース トーク画面モックスクリプト

## 位置づけ

step4-production-usage-mock-script.md「次のステップ候補」2点目(insufficient_input・
out_of_scopeといった正常系以外のケースについても、本番運用で実際に起こりうるやり取りの
例としてモックスクリプト化する)に対応する。実LINE公式アカウント・実LLM APIの接続・
画像生成は一切行っていない。

## モック対象ケース

`schema/validate_test_cases.py`記載の既存テストケース(32件中パス済み)のうち、
`prototype/test_cloud_function_webhook.py`の
`test_process_memo_event_out_of_scope_returns_message_as_is()`・
`test_process_memo_event_insufficient_input_returns_missing_fields_request()`で
実際に使用されている2件を素材とした。新しい事実確認・WebSearch調査は行わず、既存
テストケースの入力文言(`_make_event()`引数)・出力フィールドの内容をそのままトーク画面
の文面として再構成した。

- `OOS1_membership_question`(status="out_of_scope"): 入力「会員は何人まで?」
- `II1_no_category`(status="insufficient_input"): 入力「鞍作って」

## トーク画面の見え方(案)

```
[LINE公式アカウント「鞍パシャッと」とのトーク画面(本番運用中)]

(代表者から送信)
会員は何人まで?

(アプリから自動返信・out_of_scope_messageをそのまま返す)
本サービスは受注整理・納品案内・お手入れ案内の下書き作成支援のみを行っております。
```

```
[同トーク画面・別のやり取り]

(代表者から送信・区分の記載漏れ)
鞍作って

(アプリから自動返信・missing_fields_requestをそのまま返す)
区分(新規制作/修理)が不明なため下書きを作成できません。区分を教えてください。
```

## 注記・限界

- 上記2件はいずれも`cloud_function_webhook.py`の`process_memo_event()`が
  `status="out_of_scope"`では`out_of_scope_message`を、`status="insufficient_input"`
  では`missing_fields_request`をそのまま返信文として採用する既存の実装分岐
  (schema/validate_test_cases.py 87〜121行の検証ロジックと対応)をそのまま文面化した
  ものであり、実際にLLM APIを呼び出して生成したものではない。実LLM接続後、同じ入力に
  対して実際にこの通りのstatus分類・文面が返るかは、output-samples-validation.md
  「残る未検証事項」と同じ限界として引き続き未検証。
- `II1_no_category`以外にも`II2_no_saddle_type`(鞍の型が不明な場合の
  missing_fields_request)が既存テストケースに存在するが、文面パターンとしては
  「不足項目名が異なるだけで構造は同一」のため、本ドキュメントでは重複掲載を避けて
  代表例1件(`II1_no_category`)のみを採用した。
- 本番運用時のやり取りである前提(実LINE公式アカウント接続・オーナー承認待ち)自体は
  step4-production-usage-mock-script.mdと同じ限界が残る。

## 次のステップ候補

- 複数職人プランにおいて、代表者以外の職人が自分のLINEアカウントから直接メモを送信する
  ケースのモックスクリプト化(step4-production-usage-mock-script.md「次のステップ候補」
  1点目、本ドキュメントでは対象外のまま持ち越し)。
- 他venture・アイデア領域の前進。
