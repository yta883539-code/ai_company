# トーン変換の固定語彙不変性チェック設計(2026-08-22 02:00 UTC)

## 位置づけ

llm-quality-verification-plan.md「残る未確定事項」の最後の項目
「トーン変換の固定語彙不変性チェックを機械化する際、どの文字列を『固定語彙』として
突き合わせ対象にするかのリスト化」に対応する。message-tone-variants.md「前提: 3トーン共通で
変えてはいけないもの」節の4項目を、機械チェックに適するものと適さないものに分けて整理し、
機械チェックできるものについては実際にprototype/test_engine.pyへ実装した。

## 対象4項目の切り分け

| # | 項目(message-tone-variants.md) | 機械チェック可否 | 理由 |
|---|---|---|---|
| 1 | 「仮押さえ」「確定」という語を言い換えない | 可能 | 各`format_*_message()`関数内でformal/standard/casualの3文字列がリテラルに直書きされており、単語の出現有無を文字列比較で判定できる |
| 2 | 日付「8/9(土)」・時刻「15:30〜」の表記形式 | 追加チェック不要(構造的に保証済み) | `candidate_label`は呼び出し側が1つの文字列として生成し、3トーンのf-stringに同じ変数をそのまま埋め込む実装のため、表記が3トーン間でずれることが構造上あり得ない(engine.py:1516以降の各`format_*`関数を参照) |
| 3 | FAQ実質情報(住所・駐車場台数・支払い方法の登録値) | 追加チェック不要(構造的に保証済み) | 同上。`address_text`・`capacity`・`methods`は変数展開のみで、3トーンとも同じ変数を使うため言い換えが構造的に発生しない |
| 4 | 1メッセージ1用件・催促は1回のみ、等の構造上のルール | 対象外(別課題) | 単一メッセージの文字列比較では検証できず、複数ターンにまたがる会話フロー全体の検証が必要(llm-quality-verification-plan.mdの別の残課題「複数ターンにまたがる状態遷移の検証」と同じスコープなので、本ドキュメントでは扱わない) |

2・3が「追加チェック不要」なのは、テストを書かなくても壊れ得ないという意味ではなく、
`candidate_label`等を組み立てる側(`label_from_slot_key()`等)の実装が正しい前提での話である。
その前提自体の妥当性は既存のテスト(`label_from_slot_key`関連のテスト等)でカバー済み。

## 機械チェックの実装方針

「特定の語が3トーンのうちどれか1つにでも出現するなら、残り2トーンにも出現しなければならない」
という関数非依存のall-or-nothing不変条件として実装する。個々の`format_*_message()`関数が
「仮押さえ」「確定」のどちらを使うかを事前にリスト化する方式(関数ごとの期待値テーブル)ではなく、
出現パターンの一致だけを見る方式を選んだ理由は、将来トーン関数が追加された際にテーブルの
更新漏れがあっても検知漏れにならない(その関数がどちらの語も使わなければ何もチェックされない
だけで、使うのに一部トーンで言い換えられていれば必ず検知できる)ため。

対象語彙リスト: `FIXED_VOCABULARY = ["仮押さえ", "確定"]`
(tone-and-manner-guideline.md 基本方針2 に対応する2語のみ。他の語はmessage-tone-variants.mdの
「前提」節に明記が無いため対象外とする)

## 実装箇所

`ventures/line-reservation-ai/prototype/test_engine.py`に`FixedVocabularyInvariantAcrossTonesTest`
を追加した。tone引数を持つ全関数(`format_confirmation_message`・`format_reminder_message`・
`format_reminder_resend_message`・`format_hold_message`・`format_cancel_confirmed_message`・
`format_cancel_pending_message`・`format_cancel_not_found_message`・`format_change_started_message`・
`format_change_not_found_message`・`format_faq_parking_message`・`format_faq_address_message`・
`format_faq_payment_message`・`format_faq_hours_message`・`format_faq_hours_message_weekly`・
`format_faq_unregistered_message`、計15関数)を代表引数付きでテーブル化し、各関数について
formal/standard/casualの3出力を生成、`FIXED_VOCABULARY`の各語について3出力間で出現有無が
一致することを検証する。

実行結果: `python3 -m unittest ventures/line-reservation-ai/prototype/test_engine.py -v`で
新規追加分を含め全件パスを確認済み(具体的な件数はtest_engine.py実行結果を参照)。

## 残る課題

- 表4項目目(1メッセージ1用件・催促1回のみ)の機械チェックは、複数ターンにまたがる会話フロー
  検証の設計(llm-quality-verification-plan.mdの別の未確定事項)とあわせて今後検討する。
- 将来`format_*_message()`系の新規関数を追加する際は、`FixedVocabularyInvariantAcrossTonesTest`の
  テーブルに追加することを忘れないようにする(all-or-nothing方式のため追加自体を忘れても
  誤検知は起きないが、その関数のトーン不変性はテスト対象外のまま静かに漏れる)。
- (解消済み 2026-08-28 07:00 UTC: 「自由文側の機械チェック(絵文字不使用の検証等)を追加するか」
  として持ち越されていた点に対応した。message-tone-variants.mdの絵文字欄
  (formal/standardは「使用しない」)は、これまで`ToneRenderingTest`が
  `format_confirmation_message()`・`format_hold_message()`の2関数のみをスポットチェックする
  にとどまり、残り13関数(FAQ・キャンセル・変更・リマインド等)は未検証だった。
  `FixedVocabularyInvariantAcrossTonesTest.TONE_FUNCTIONS`(tone引数を持つ全15関数の一覧、
  同一テーブルを流用するため関数追加時の網羅漏れリスクも共有)を再利用し、
  `NoEmojiInFormalStandardTonesTest`としてformal/standard出力に絵文字
  (Unicode範囲`\U0001F300`-`\U0001FAFF`・`☀`-`➿`)が一切含まれないことを機械チェックする
  テストを`prototype/test_engine.py`に新規追加した(engine.py内で実際に使われている絵文字は
  現状🙌・🙏の2種のみと確認済み)。テスト1件追加、プロトタイプ全体320件パス・schema検証25件
  パスを確認した。casualトーンの絵文字頻度上限(1メッセージにつき1個まで)自体は既存の
  `CasualEmojiFrequencyLimitTest`・`ToneRenderingTest`でカバー済みのため対象外とした。)
