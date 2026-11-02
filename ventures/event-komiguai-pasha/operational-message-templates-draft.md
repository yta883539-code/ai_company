# 運用メッセージ系 文例ドラフト・機械チェック適用設計(フェーズ81)

tone-and-manner-guideline.md(フェーズ80)「未検証の仮説」で指摘した、運用メッセージ系
(結果ページ案内・問い合わせ返信下書き・返金案内メール)には機械チェックの仕組みが無い
というギャップに対応する。これまで各設計文書(result-page-ttl-access-design.md・
inquiry-handling-design.md・ttl-expiry-result-delivery-refund-design.md)は文面の
「内容・方針」を文章で記述するのみで、実際に送信・表示する文字列そのものを確定して
いなかったため、機械チェックの対象となる具体的な文例をまず本文書で確定する。

## 1. 対象メッセージ一覧

| ID | 名称 | 出典 | 表示/送信先 |
| --- | --- | --- | --- |
| A | 完了メール(結果ページ案内) | ttl-expiry-result-delivery-refund-design.md 2節 | `customer_email` |
| B | 保存期間終了案内(結果ページ) | result-page-ttl-access-design.md 3節(3) | `/result/{draft_id}` |
| C-1 | 問い合わせ返信下書き(メール未着・TTL失効前再送) | inquiry-handling-design.md 3節1 | `customer_email` |
| C-2 | 問い合わせ返信下書き(TTL失効後、再生成/返金の2案提示) | inquiry-handling-design.md 3節2 | `customer_email` |
| D | 生成失敗時の全額返金案内メール | ttl-expiry-result-delivery-refund-design.md 3-2節(4) | `customer_email` |

C-3(品質不満による返金希望)はオーナー判断用の内部要約であり主催者への送信文面では
ないため、本文書の機械チェック対象には含めない(tone-and-manner-guideline.mdの対象は
「主催者が実際に目にする文言」に限定する既存方針と整合させる)。

## 2. 文例ドラフト

いずれもtone-and-manner-guideline.md(フェーズ80)の方針(絵文字不使用・見出し記号
〈【】〉不使用・ですます調)に従う。

### A. 完了メール(結果ページ案内)

件名: イベントこみぐあいパシャっと 生成結果のご案内

本文:
お申し込みいただいた内容の生成が完了しました。以下のリンクより結果ページをご確認
ください。
{result_page_url}
結果ページは決済完了から24時間でご確認いただけなくなりますので、イベント準備に
お早めにお役立てください。
内容についてご不明な点がございましたら、結果ページ下部の問い合わせフォームより
ご連絡ください。

### B. 保存期間終了案内(結果ページ)

このURLの結果の保存期間(24時間)が終了したため閲覧できません。再度ご利用いただく
場合はお手数ですが最初からお申し込みください。
既にお支払い済みの場合、再生成(無料)または返金についてこちらの問い合わせフォーム
よりご連絡ください。

(result-page-ttl-access-design.md フェーズ47確定の文言をそのまま採用。表記差分なし)

### C-1. 問い合わせ返信下書き(メール未着・TTL失効前再送)

お問い合わせいただいた内容を確認し、結果ページへの再送用のご案内を作成いたしました。
下記のリンクから再度ご確認ください。
{result_page_url}

(フェーズ84: inquiry-handling-design.md 3-1節〈フェーズ83、tone-and-manner-guideline.md
方針3「主催者側の過失ではない事務的対応は謝罪語を省略可」を適用〉確定の文言に合わせて
改訂。フェーズ81時点の文言は謝罪語を含まない点では方針3と矛盾しなかったが、フェーズ83で
別途確定した固定文言と一字一句一致していなかったため、本document・
prototype/operational_message_templates.pyを3-1節の文言に統一した)

### C-2. 問い合わせ返信下書き(TTL失効後、再生成/返金の2案提示)

ご指定のデータは、保存期間(24時間)を過ぎたため削除済みとなっております。恐れ入り
ますが、再送はできません。ご希望の場合、同内容を再入力いただくことで無料で再生成を
承ります。返金をご希望の場合は、その旨を担当者が確認のうえ個別にご連絡いたします。

(フェーズ84: 同上。inquiry-handling-design.md 3-1節〈方針3「主催者側の過失によらない
失敗は率直な事実提示+謝罪は控えめ」を適用〉確定の文言に合わせて改訂)

### D. 生成失敗時の全額返金案内メール

生成処理に不具合が発生したため、ご入力いただいた内容の生成が完了しませんでした。
お支払いいただいた金額は全額返金の手続きを行いました。反映まで数日かかる場合が
ございます。
恐れ入りますが、改めてご入力をお願いできますと幸いです。
{retry_url}
ご不便をおかけして申し訳ございません。

## 3. 機械チェックの適用方式

- schema経由のLLM構造化出力(checklist等)はschema/output.schema.jsonのインスタンス
  単位でprototype/post_generation_checks.pyが検証するが、本文書の5文例はLLM出力では
  なく固定テンプレート文字列(`{result_page_url}`等のプレースホルダ埋め込みのみ)である
  ため、インスタンス単位の検証ではなく「テンプレート文字列そのもの」に対する静的検証で
  十分と判断する。
- post_generation_checks.pyのEMOJI_PATTERN(厳守事項9の絵文字検出用正規表現)をそのまま
  再利用し、本文書の5文例文字列に対して絵文字が含まれていないことをテストする
  (prototype/operational_message_templates.py・
  prototype/test_operational_message_templates.py、4節参照)。
- 見出し記号(【】)不使用チェックの機械化は、tone-and-manner-guideline.md記載の既存
  LLM生成物系チェック(check_no_emoji_anywhere等)にも現状存在しない横断的な未実装
  事項であり、本フェーズの対象範囲を絵文字チェックの横展開に限定するため次回候補に残す。

## 4. 実装状況

- prototype/operational_message_templates.py: 上記5文例をPythonの辞書`TEMPLATES`として
  定数化した(新規作成)。
- prototype/test_operational_message_templates.py: `TEMPLATES`の全値に対し
  post_generation_checks.EMOJI_PATTERNで絵文字が検出されないことを確認するテストを
  新規作成した(テストメソッド1件、`subTest`で5テンプレート全件を検証し5/5件パス)。
  `python3 -m unittest discover -s prototype -p "test_*.py"`で既存50件+新規1件=51件、
  回帰なしでパスすることを確認した。
- 実際のメール送信・結果ページ表示への反映(テンプレートエンジンへの組み込み等)は
  実装時の課題として残す(コード変更は本チェック機構の追加のみ)。

## 5. 未検証・残課題

- 見出し記号(【】)不使用の機械チェック化(他venture・本venture共通の横断課題として
  次回候補)。
- C-1・C-2・D文面の実際の文言は、オーナー承認後の実メール送信連携時に最終確認が必要
  (本フェーズはテンプレート文字列の確定と機械チェック基盤の追加のみ)。
- 本文書で確定した文例とinquiry-handling-design.md・ttl-expiry-result-delivery-refund-design.md
  の記述内容(フロー自体の方針)との不整合が今後生じないよう、フロー側の文書を更新する
  場合は本文書の文例も合わせて見直す運用が必要(cross-document整合の今後の課題)。

最終更新: 2026-11-02 00:00 UTC(フェーズ81: tone-and-manner-guideline.md〈フェーズ80〉の
次回候補(1)に対応。運用メッセージ系5文例(完了メール・保存期間終了案内・問い合わせ
返信下書き2類型・返金案内メール)を初めて文字列として確定し、絵文字不使用の機械チェックを
新規追加。コード変更はテンプレート定数化+チェックテストの新規追加のみ、既存テスト50件は
変更なしでパス)
