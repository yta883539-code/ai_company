# オーナー・セッター向けセルフサービスFAQの導線設計

作成日: 2026-09-15(定例更新フェーズ219)

owner-operation-self-service-faq.md(フェーズ218)「次のステップ候補」で残課題としていた
「本FAQへの導線実装」に着手する。line-reservation-ai(フェーズ続き233)・kura-pasha
(フェーズ126)に続く3venture目の横展開。

## 1. 本ventureにおける「オーナー」の扱い

line-reservation-ai・kura-pashaでは、トークルームに複数の利用者(来店客と店舗オーナー等)が
混在するため、`owner_user_id`との一致判定でオーナー本人のみに絞り込む必要があった。

一方、本ventureは owner-operation-self-service-faq.md冒頭で整理した通り「来店客」に相当する
層が存在せず、課題(ルート)入れ替え後のメモを送信するジムオーナー・セッター自身が
契約者=本サービスの唯一の利用者である。そのためLINEのトークルームに届くメッセージは
常に契約者本人からのものであり、`owner_user_id`のような絞り込み判定自体が不要
(かつ対応する状態を保持する仕組みも現状存在しない)。本設計はこの前提の違いを踏まえ、
`process_memo_event()`に届いたテキストメッセージ全件を対象にFAQトリガー判定を行う。

## 2. コマンドの仕様

line-reservation-ai・kura-pashaと同じ「(a)リンク方式/(b)コマンド方式」の比較を行い、
同じ理由((a)はFAQページの外部公開〈ホスティング〉を伴いオーナー承認待ちになるのに対し、
(b)はLINEのトークルーム内で完結し実LINE公式アカウント接続前でも机上実装・テストまで
進められる)で(b)コマンド方式を採用する。

- トリガー: 本文「FAQ」(大文字小文字を区別しない、前後空白は無視)を送信すると、
  Q1〜Q6の短い見出し一覧(メニュー)を返信する。
- 各項目の本文照会: 続けて「Q1」〜「Q6」(大文字小文字を区別しない)を送信すると、
  該当項目の回答本文を返信する。
- 上記2パターンに一致しない入力は、これまで通り`process_memo_event()`の既存フロー
  (生成一時停止判定→決済失敗制限モード判定→LLM呼び出し)にそのまま進む。
- LLM呼び出し(`llm_call.generate()`)を経由せず、`usage_counter`の月間生成回数
  カウントも増分しない(運用コマンドであり、投稿文生成の1回として消費させるべきでは
  ないため)。

### 生成一時停止・決済失敗制限モードとの優先順位

本venture固有の論点として、`_is_generation_paused()`(トライアル終了・未アップグレード)・
`_is_payment_suspended()`(決済失敗の猶予期間超過)による定型応答よりも、FAQコマンド判定を
先に行う設計とした。理由は、Q2(トライアル条件)・Q3(解約/再開)のようにまさに一時停止・
制限モード中の契約者が知りたい内容をFAQが含んでいるため、これらの状態でもFAQコマンドが
機能する方が有用と判断したため。FAQコマンド自体はLLM呼び出しを伴わず月間カウントも
増分しないため、一時停止・制限モードの判定ロジック(`_is_generation_paused`・
`_is_payment_suspended`)そのものには影響を与えない(判定に使う状態を変更する副作用を
持たないコマンドのため、優先順位を入れ替えても安全側であることを確認済み)。

## 3. FAQ本文の出典

owner-operation-self-service-faq.mdのQ1〜Q6の内容を、LINEメッセージとして送信するのに
適した簡潔な文面に整理し直した(内部設計ドキュメントのファイル名参照は運用者向けの
参考情報のため、契約者向け返信本文には含めない)。Q1(プラン変更)・Q3(解約/再開)は、
本ventureが既にStripeカスタマーポータルへのリンクを`portal_link_provider`経由で
案内する会話フロー(`cancellation_intent`/`downgrade_intent`)を持つため、FAQ回答本文では
URLを直接埋め込まず「トークルームで『プランを変更したい』『解約したい』とお伝えいただくと
手続きページのリンクをご案内します」という、既存フローへの誘導文言とした
(owner_faq_router.py自体はportal_link_providerに依存しない純粋関数のまま保つ設計を
line-reservation-ai・kura-pashaから踏襲するため)。

## 4. 実装

`prototype/owner_faq_router.py`に、LLM呼び出し・LINE送信・状態参照を一切持たない
純粋関数として実装した(line-reservation-ai・kura-pashaと同一のインターフェース)。

- `is_owner_faq_menu_trigger(text) -> bool`: 「FAQ」トリガー判定。
- `match_owner_faq_item_code(text) -> Optional[str]`: 「Q1」〜「Q6」判定、一致すれば
  `"Q1"`〜`"Q6"`を返す。
- `render_owner_faq_menu_message() -> str`: Q1〜Q6の見出し一覧を整形する。
- `render_owner_faq_answer_message(code) -> str`: 指定コードの回答本文を整形する。
  未知のcodeは`KeyError`(呼び出し元は`match_owner_faq_item_code()`で事前に検証済みの
  値のみ渡す前提のため、フォールバックは設けない)。

`cloud_function_webhook.py`の`process_memo_event()`冒頭、`memo_text`・`has_photo`を
取り出した直後(`_is_generation_paused()`判定より前)に、上記2関数を使った分岐を追加した。
一致した場合は`_reply_with_retry()`で直接返信し、`MemoProcessResult`に新設した
`owner_faq_action`フィールド(`"menu"`または`"Q1"`〜`"Q6"`、非該当時は`None`)へ
セットして返す。他のearly-return分岐(`generation_paused`・`payment_suspended`)と
同様、`handled=True`・`reply_sent`は`_reply_with_retry()`の成否をそのまま反映する。

## 5. 未検証の仮説・残課題

- (解消済み 2026-09-17 UTC定例更新: follow-event-welcome-message-design.md残課題を参照。
  「FAQ」という単語自体を契約者が思いつかない問題に対し、ウェルカムメッセージ
  (`format_welcome_message()`)末尾へトリガーキーワードの案内文を追記した)
- Q1〜Q6以外の想定外の質問への追加ハンドリングは無く、その場合は契約者が今まで通り
  運営者へ直接問い合わせる想定のまま。
- 実際に契約者がこのコマンドをどの程度使うか、support-cost-estimate.mdが試算した
  月次対応コスト(2ヶ月目以降500〜1,500円相当)の削減にどの程度寄与するかは、
  実運用データ(LINE公式アカウント接続後)が無いと検証できない。
- aircon-pashaへの同種導線の横展開は未着手のまま残る(次回以降の候補)。
