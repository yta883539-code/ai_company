# 契約者向けセルフサービスFAQの導線設計

作成日: 2026-09-15(定例更新フェーズ225)

owner-operation-self-service-faq.md(フェーズ224)「次のステップ候補」で残課題として
いた「本FAQへの導線実装」に着手する。course-set-pasha(フェーズ219)・
line-reservation-ai(フェーズ続き233)・kura-pasha(フェーズ126)に続く4venture目・
最後の横展開となる(これで4venture全ての横展開が完了する)。

## 1. 本ventureにおける「契約者」の扱い

owner-operation-self-service-faq.md「前提」節の通り、本ventureには来店客に相当する
層が存在せず、訪問施工完了報告メモを送信する施工業者本人、またはBtoBプランで契約する
管理会社自身が契約者=本サービスの唯一の利用者である(この点はcourse-set-pashaと同型)。
そのためline-reservation-ai・kura-pashaのような`owner_user_id`との一致判定による
絞り込みは不要であり、`process_memo_event()`に届いたテキストメッセージ全件を対象に
FAQトリガー判定を行う設計とする(course-set-pashaのowner-faq-routing-design.mdと
同じ考え方)。

## 2. コマンドの仕様

他3venture・同じ「(a)リンク方式/(b)コマンド方式」の比較を行い、同じ理由((a)は
FAQページの外部公開〈ホスティング〉を伴いオーナー承認待ちになるのに対し、(b)はLINEの
トークルーム内で完結し実LINE公式アカウント接続前でも机上実装・テストまで進められる)で
(b)コマンド方式を採用する。

- トリガー: 本文「FAQ」(大文字小文字を区別しない、前後空白は無視)を送信すると、
  Q1〜Q7の短い見出し一覧(メニュー)を返信する。
- 各項目の本文照会: 続けて「Q1」〜「Q7」(大文字小文字を区別しない)を送信すると、
  該当項目の回答本文を返信する。本venture固有として、Q1〜Q6(6項目)のみの他3venture
  より1項目多い(Q7「管理会社向けプランと個人向けプランの使い分け」がBtoB/BtoC併存の
  本venture固有項目)。
- 上記2パターンに一致しない入力は、これまで通り`process_memo_event()`の既存フロー
  (生成一時停止判定→決済失敗制限モード判定→LLM呼び出し)にそのまま進む。
- LLM呼び出し(`llm_call.generate()`)を経由せず、`usage_counter`の月間生成回数
  カウント・トライアル専用生成回数カウント(`profile_store.increment_trial_generation_
  count()`)のいずれも増分しない(運用コマンドであり、完了報告生成の1回として
  消費させるべきではないため)。

### 生成一時停止・決済失敗制限モードとの優先順位

course-set-pashaと同様、`_is_generation_paused()`(トライアル終了・未アップグレード)・
`_is_payment_suspended()`(決済失敗の猶予期間超過)による定型応答よりも、FAQコマンド
判定を先に行う設計とした。Q2(トライアル条件)・Q3(解約/再開)はまさに一時停止・
制限モード中の契約者が知りたい内容であり、FAQコマンド自体はLLM呼び出しを伴わず
各種カウントも増分しない(判定に使う状態を変更する副作用を持たない)ため、優先順位を
入れ替えても安全側であることを確認済み。

## 3. FAQ本文の出典

owner-operation-self-service-faq.mdのQ1〜Q7の内容を、LINEメッセージとして送信するのに
適した簡潔な文面に整理し直した(内部設計ドキュメントのファイル名参照は運用者向けの
参考情報のため、契約者向け返信本文には含めない)。Q1(プラン変更)・Q3(解約/再開)は、
本ventureが既にStripeカスタマーポータルへのリンクを`portal_link_provider`経由で
案内する会話フロー(status=cancellation_intent/downgrade_intent)を持つため、FAQ回答
本文ではURLを直接埋め込まず「トークルームで『プランを変更したい』『解約したい』と
お伝えいただくと手続きページのリンクをご案内します」という、既存フローへの誘導文言と
した(owner_faq_router.py自体はportal_link_providerに依存しない純粋関数のまま保つ
設計を他3ventureから踏襲するため)。

## 4. 実装

`prototype/owner_faq_router.py`に、LLM呼び出し・LINE送信・状態参照を一切持たない
純粋関数として実装した(他3ventureと同一のインターフェース、Q7まである点のみ異なる)。

- `is_owner_faq_menu_trigger(text) -> bool`: 「FAQ」トリガー判定。
- `match_owner_faq_item_code(text) -> Optional[str]`: 「Q1」〜「Q7」判定、一致すれば
  `"Q1"`〜`"Q7"`を返す。
- `render_owner_faq_menu_message() -> str`: Q1〜Q7の見出し一覧を整形する。
- `render_owner_faq_answer_message(code) -> str`: 指定コードの回答本文を整形する。
  未知のcodeは`KeyError`(呼び出し元は`match_owner_faq_item_code()`で事前に検証済みの
  値のみ渡す前提のため、フォールバックは設けない)。

`cloud_function_webhook.py`の`process_memo_event()`冒頭、`memo_text`・`user_id`・
`profile`を取り出した直後(`_is_generation_paused()`判定より前)に、上記2関数を使った
分岐を追加した。一致した場合は`_reply_with_retry()`で直接返信し、`MemoProcessResult`に
新設した`owner_faq_action`フィールド(`"menu"`または`"Q1"`〜`"Q7"`、非該当時は`None`)へ
セットして返す。他のearly-return分岐(`generation_paused`・`payment_suspended`)と同様、
`handled=True`・`reply_sent`は`_reply_with_retry()`の成否をそのまま反映する。

## 5. 未検証の仮説・残課題

- (解消済み 2026-09-17・フェーズ226: 「FAQ」という単語自体を契約者が思いつかない可能性が
  あるという周知課題に対応し、first-generation-self-check-design.md 6節の通り、
  全業者が生涯に一度は必ず受け取るSELF_CHECK_NOTICE_TEXT(初回生成時セルフチェック案内)の
  末尾にFAQコマンドの案内文を追記した。既存の確認依頼部分の文言は変更していない)
- (解消済み 2026-09-18定例更新: 上記が残していた「友だち追加直後〈初回生成より前〉の周知は
  実LINE API接続後の検討課題」という記載を見直した。format_welcome_message()自体は
  followイベント受信時の固定テンプレート文字列を組み立てるだけの関数で、実LINE API接続の
  有無にかかわらず机上実装・テストが可能であり、他3venture(course-set-pasha・kura-pasha・
  line-reservation-ai)も同じ理由で自身のウェルカムメッセージへ周知文言を追記済みだった
  ことを踏まえ、本ventureのformat_welcome_message()末尾にも同種の一文
  (「ご利用方法や料金プラン変更・解約などのご質問は、トークルームで「FAQ」と送信すると
  いつでもご案内します。」)を追記し、これで4venture全ての横展開が完了した。
  test_welcome_message_mentions_faq_trigger_keyword()で本文がowner_faq_router.pyの
  トリガーキーワードと一致することを検証済み)
- Q1〜Q7以外の想定外の質問への追加ハンドリングは無く、その場合は契約者が今まで通り
  運営者へ直接問い合わせる想定のまま。
- 実際に契約者がこのコマンドをどの程度使うか、support-cost-estimate.mdが試算した
  月次対応コストの削減にどの程度寄与するかは実運用データ(LINE公式アカウント接続後)が
  無いと検証できない。
- これで4venture全てにオーナー・契約者向けセルフサービスFAQのコマンド方式導線実装が
  完了した。次回以降は、実運用データが取得でき次第の効果検証、またはオンボーディング
  完了メッセージ等へのFAQ周知文言の追加を候補とする。
