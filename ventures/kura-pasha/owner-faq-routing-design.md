# オーナー(契約者)向けセルフサービスFAQの導線設計

作成日: 2026-09-15 20:00 UTC(フェーズ126)

owner-operation-self-service-faq.md(フェーズ125)「次のステップ候補」で残課題として
いた「本FAQへの導線実装」に着手する。line-reservation-aiのowner-faq-routing-
design.md(フェーズ続き233)と同じ設計思想(トークルーム内で完結するコマンド方式)を
踏襲するが、本venture固有のQ1〜Q8を対象とする点、および判定対象を「契約者本人」に
絞る根拠が本venture固有の複数職人プラン(workshop共有)構造に由来する点が異なる。

## 1. 方式の選定

line-reservation-aiと同じく2方式を検討した。

- (a) オンボーディング完了メッセージ等の文末にFAQページへのリンクURLを追記する方式。
  実際にFAQ本文をホスティングするWebページが必要になり、外部サービスへの公開
  (ホスティング環境の用意)を伴うためオーナー承認待ちになってしまう。
- (b) 契約者がトークルームでキーワード(「FAQ」)を送信すると、ボットがFAQメニューを
  その場で返信するコマンド方式。LINEのトークルーム内で完結し、新たな外部公開を
  必要としない。

本venture自体が実LINE公式アカウント接続待ち(pending-approval.md 2026-09-15 03:00
UTC記載)の状態であっても、(b)は机上実装・テストまで完結できるため、本フェーズでは
(b)を採用する。(a)は実際にFAQページを外部公開する判断が下りた時点で改めて検討する
残課題として残す。

## 2. 判定対象を契約者本人に絞る理由(本venture固有)

course-set-pasha・aircon-pashaと異なり、本ventureには複数職人プラン
(craftsman-account-linking-design.md 11.7節、最大5名の共同利用者)が存在する。
owner-operation-self-service-faq.md Q4・Q6・Q7が示す通り、プラン変更・解約・
ダウングレード時のメンバー扱い・契約者交代はいずれも契約者(`contractor_user_id`)
本人のみが操作できる権限モデルを採用しており、FAQの内容自体も契約者向けの運用手続き
が中心である。そのため本コマンドも、`workshop_store.get_contractor_user_id(workshop_id)`
と一致する`user_id`から送信された場合のみ発火させる。共同利用者(メンバー)が
「FAQ」「Q1」等と偶然一致する内容を依頼メモとして送信した場合は、これまで通り
通常の生成フロー(process_memo_event())にそのまま委譲され、影響を受けない。

## 3. コマンドの仕様

- トリガー: 連携済みのuser_idかつ契約者本人が、本文「FAQ」(大文字小文字を区別しない、
  前後空白は無視)を送信すると、Q1〜Q8の短い見出し一覧(メニュー)を返信する。
- 各項目の本文照会: 契約者本人が続けて「Q1」〜「Q8」(大文字小文字を区別しない)を
  送信すると、該当項目の回答本文を返信する。
- 上記2パターンに一致しない入力、または送信者が契約者本人でない場合は、これまで通り
  `process_memo_event()`(依頼メモ生成・意図検知等の既存フロー)にそのまま委譲する。
- LLM呼び出し(`llm_call()`)を経由しない。運用コマンドであり、通知ログ記録・オーナーへの
  転送も行わない(オーナー自身が起点の操作のため)。

## 4. FAQ本文の出典

owner-operation-self-service-faq.mdのQ1〜Q8の内容を、LINEメッセージとして送信するのに
適した簡潔な文面に整理し直した(内部設計ドキュメントのファイル名参照は運用者向けの
参考情報のため、契約者向け返信本文には含めない)。

## 5. 実装

`prototype/owner_faq_router.py`に、LLM呼び出し・LINE送信を持たない純粋関数として実装した
(line-reservation-aiのowner_faq_router.pyと同じ関数構成)。

- `is_owner_faq_menu_trigger(text) -> bool`: 「FAQ」トリガー判定。
- `match_owner_faq_item_code(text) -> Optional[str]`: 「Q1」〜「Q8」判定、一致すれば
  `"Q1"`〜`"Q8"`を返す。
- `render_owner_faq_menu_message() -> str`: Q1〜Q8の見出し一覧を整形する。
- `render_owner_faq_answer_message(code) -> str`: 指定コードの回答本文を整形する。
  未知のcodeは`KeyError`(呼び出し元は`match_owner_faq_item_code()`で事前に検証済みの
  値のみ渡す前提のため、フォールバックは設けない)。

`cloud_function_webhook.py`の`process_message_event()`に、連携済みuser_idの分岐
(`user_profile_store.get_workshop_id(user_id)`が設定済みの場合)の内部で、
`process_memo_event()`へ委譲する前に`_maybe_handle_owner_faq_command()`を呼び出す
形で配線した。この関数が`workshop_store.get_contractor_user_id(workshop_id) ==
user_id`かつトリガー一致と判定した場合のみ`MemoProcessResult`を直接返し、それ以外は
`None`を返して従来通り`process_memo_event()`へ進む。

テストは`prototype/test_owner_faq_router.py`(純粋関数の単体テスト)、および
`prototype/test_cloud_function_webhook.py`に3件追加(契約者のFAQトリガー・Q7照会・
契約者以外からのFAQ送信が通常フローにフォールバックすること)し、いずれもパスを
確認した。回帰確認としてventure全体13ファイル(`python3 prototype/run_all_tests.py`)・
schema検証30件(`python3 schema/validate_test_cases.py`)いずれもパス
(新規追加分以外は変更前と同じ結果)を確認した。

## 6. 未検証の仮説・残課題

- 【解消済み・2026-09-17 20:00 UTC追記】「FAQ」という単語自体を契約者が思いつかない
  可能性がある問題は、course-set-pasha・aircon-pashaと同じ考え方で対応した。本venture
  固有の唯一確実な初回導線である`format_follow_welcome_message()`(友だち追加時の
  ウェルカムメッセージ)の末尾に「ご利用方法などのご質問は、トークルームで『FAQ』と
  送信するといつでもご案内します。」の一文を追記した。既存の連携コード案内部分の文言・
  処理は変更していない。test_cloud_function_webhook.pyに、ウェルカムメッセージ本文が
  実際にowner_faq_router.is_owner_faq_menu_trigger()のトリガーキーワード「FAQ」と
  一致することを検証するテストを1件追加した。
- Q1〜Q8以外の項目(想定外の質問)が来た場合の追加ハンドリングは無く、その場合は契約者が
  今まで通り運営者へ直接問い合わせる想定のまま。
- 実際に契約者がこのコマンドをどの程度使うか、対応コスト削減(support-cost-estimate.md・
  cross-venture-support-cost-comparison.md)にどの程度寄与するかは実運用データ
  (LINE公式アカウント接続後)が無いと検証できない。
- これでcourse-set-pasha・aircon-pashaに続き、本venture(kura-pasha)でもFAQ導線の
  周知対応が完了した。【解消済み・2026-09-17 21:00 UTC追記】残っていたline-reservation-ai
  も、同venture固有の制約(follow時のウェルカムメッセージがオーナー・一般顧客共用のため、
  代わりにオーナー本人にのみ送信されるonboarding-completion-message-design.mdを周知先に
  採用)を踏まえて対応済みとなり、これで4venture全ての周知対応が完了した
  (line-reservation-ai/owner-faq-routing-design.md 5節参照)。

## 7. 全角入力への対応(フェーズ131)

course-set-pashaのフェーズ221で、オーナー向けFAQコマンドのトリガー「FAQ」・項目コード
「Q1」〜の判定が半角英数字の入力のみを想定しており、日本語入力の携帯端末で既定になり
やすい全角入力(「ＦＡＱ」「Ｑ１」)では一致しない想定漏れが見つかった。同フェーズの
記載で「line-reservation-ai・kura-pasha・aircon-pashaへの横展開は各ventureの次回
ローテーション時の課題」とされていたうち、line-reservation-aiはフェーズ続き240で対応
済みとなった。本フェーズで残る本venture(kura-pasha)分の横展開を行った。

course-set-pasha・line-reservation-aiと同一実装の`_normalize_command_text()`
(`unicodedata.normalize("NFKC", text)`を`strip().upper()`の前段に追加)を新設し、
`is_owner_faq_menu_trigger()`・`match_owner_faq_item_code()`から呼び出すよう変更した。
`prototype/test_owner_faq_router.py`に全角入力(「ＦＡＱ」「ｆａｑ」「　ＦＡＱ　」
「Ｑ１」「ｑ７」)のテストを2件追加し、venture全体100件(`python3 -m unittest discover
-s prototype -p "test_*.py"`、98件→100件)・schema検証30件(`python3
schema/validate_test_cases.py`)いずれもパスした。今回のコード変更は入力の正規化のみで
外部サービスへの公開・アカウント作成・支払い・送信等は発生していないため
pending-approval.mdへの追記なし。

これで残るaircon-pashaへの同種横展開のみが未対応として残る。実際に契約者が全角入力を
行う頻度自体は実運用データ(LINE公式アカウント接続後)が無いと検証できず引き続き
未検証のまま残る。
