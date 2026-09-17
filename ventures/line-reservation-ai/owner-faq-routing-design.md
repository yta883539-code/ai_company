# オーナー向けセルフサービスFAQの導線設計

作成日: 2026-09-15 16:00 UTC(定例更新)

owner-operation-self-service-faq.md「次のステップ候補」で残課題としていた
「本FAQへの導線設計(オンボーディング完了メッセージへのリンク追加、または
オーナー向けヘルプコマンドの新設)」に着手する。

## 1. 方式の選定

候補を2つ検討した。

- (a) オンボーディング完了メッセージ(onboarding-completion-message-design.md)の
  文末にFAQページへのリンクURLを追記する方式。
- (b) オーナーがトークルームでキーワード(例:「FAQ」)を送信すると、ボットが
  FAQメニューをその場で返信するコマンド方式。

(a)は実際にFAQ本文をホスティングするWebページが必要になり、外部サービスへの
公開(ホスティング環境の用意)を伴うためオーナー承認待ちになってしまう。
一方(b)はLINEのトークルーム内で完結し、新たな外部公開を必要としない
(support-cost-estimate.mdが示す「継続対応コストの主因」への対処を、実LINE公式
アカウント接続を待たずに机上実装・テストまで進められる)。そのため本フェーズでは
(b)コマンド方式を採用する。(a)のリンク追記は、実際にFAQページを外部公開する
判断(オーナー承認待ち)が下りた時点で改めて検討する残課題として残す。

## 2. コマンドの仕様

- トリガー: オーナー本人(`user_id == owner_user_id`が確定している場合のみ)が
  本文「FAQ」(大文字小文字を区別しない、前後空白は無視)を送信すると、
  Q1〜Q6の短い見出し一覧(メニュー)を返信する。
- 各項目の本文照会: オーナーが続けて「Q1」〜「Q6」(大文字小文字を区別しない)を
  送信すると、該当項目の回答本文を返信する。
- 上記2パターンに一致しない入力は、これまで通り通常のLLM解釈・会話フロー
  (`_process_message_event`の既存分岐)にそのまま渡す。誤ってオーナー以外の
  一般顧客が偶然「FAQ」「Q1」等を送った場合も、`owner_user_id`との一致判定が
  先に働くため通常の顧客向けフローが変わらないことを保証する
  (owner_user_id未設定・未確定の店舗ではこの分岐自体が発火しない)。
- LLM呼び出し(`llm_call()`)を経由しない。運用コマンドであり、通知ログ
  (`NotificationLogAggregator`)への記録・オーナーへの転送(`_notify_owner()`)も
  行わない(オーナー自身が起点の操作であり、オーナー自身へ転送する意味が
  ないため)。

## 3. FAQ本文の出典

owner-operation-self-service-faq.mdのQ1〜Q6の内容を、LINEメッセージとして
送信するのに適した簡潔な文面に整理し直した(内部設計ドキュメントのファイル名
参照は運用者向けの参考情報のため、オーナー向け返信本文には含めない)。

## 4. 実装

`prototype/owner_faq_router.py`に、LLM呼び出し・LINE送信を持たない純粋関数として実装した。

- `is_owner_faq_menu_trigger(text) -> bool`: 「FAQ」トリガー判定。
- `match_owner_faq_item_code(text) -> Optional[str]`: 「Q1」〜「Q6」判定、一致すれば
  `"Q1"`〜`"Q6"`を返す。
- `render_owner_faq_menu_message() -> str`: Q1〜Q6の見出し一覧を整形する。
- `render_owner_faq_answer_message(code) -> str`: 指定コードの回答本文を整形する。
  未知のcodeは`KeyError`(呼び出し元は`match_owner_faq_item_code()`で事前に
  検証済みの値のみ渡す前提のため、フォールバックは設けない)。

`cloud_function_process_event.py`の`_process_message_event()`冒頭
(LLM呼び出し・会話状態参照より前)に、上記2関数を使った分岐を追加した
(`_maybe_handle_owner_faq_command()`)。一致した場合は`_send()`で直接返信し、
`DispatchResult(action="owner_faq_menu"|"owner_faq_answer", detail=code)`を返す。

## 5. 未検証の仮説・残課題

- (解消 2026-09-17 21:00 UTC・定例更新: 「FAQ」という単語自体をオーナーが思いつかない
  可能性があるという周知課題に対応した。course-set-pasha・aircon-pasha・kura-pashaの
  3venture(それぞれフェーズ218・225・続き)は、いずれもfollow時のウェルカムメッセージが
  「オーナー本人だけが読む」ことが確定しているため、そこにFAQコマンドの案内文を追記する
  方式を採用していた。しかし本ventureのfollow-unfollow-event-handling-design.md 2節に
  ある通り、`FOLLOW_WELCOME_MESSAGE`(`format_follow_welcome_message()`)は「followした
  のがオーナーか一般顧客かをfollow時点では判別できない」という本venture固有の構造上、
  オーナー・顧客共用の固定文言になっている。ここにFAQコマンドの案内を追記すると、
  トリガー判定が`owner_user_id`一致者に限定されているため実害(誤動作)はないものの、
  一般顧客に対して「送っても何も起きない案内」を見せてしまい紛らわしい。そのため
  本venture独自の判断として、周知先には共用のfollowウェルカムメッセージではなく、
  onboarding-completion-message-design.md(オーナー本人にのみ、1回だけ送信されることが
  確定している)を採用した。また同ドキュメント3節が定める「1メッセージ1用件」の
  原則との整合を保つため、新規の段落を追加するのではなく、既存の結び文
  (「ご不明点はこのトークルームにご返信ください」相当、3トーン共通)に「よくある
  質問は『FAQ』と送ると案内する」旨を1文だけ継ぎ足す形とし、既存の主用件(トライアル中の
  セルフサービスアップグレード案内)を上書きしないようにした。
  `prototype/onboarding_completion_message.py`の3トーン全てのメッセージ文言を更新し、
  `test_onboarding_completion_message.py`に、3トーン全てが"FAQ"を含み、かつ
  `owner_faq_router.is_owner_faq_menu_trigger("FAQ")`が真であることを検証するテストを
  1件追加した。venture全体(python3 -m unittest discover -s prototype -p "test_*.py")・
  schema検証(python3 schema/validate_test_cases.py)いずれもパスを確認した。
  承認不要なドキュメント更新・コード実装のみで、外部サービスへの公開・アカウント作成・
  支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。)
- Q1〜Q6以外の項目(想定外の質問)が来た場合の追加ハンドリングは無く、
  その場合はオーナーが今まで通り運営者へ直接問い合わせる想定のまま。
- 実際にオーナーがこのコマンドをどの程度使うか、対応コスト削減にどの程度
  寄与するかは実運用データ(LINE公式アカウント接続後)が無いと検証できない。
