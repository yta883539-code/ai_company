# 受信メッセージのプロンプト文脈選択・優先順位設計(フェーズ43)

作成日: 2026-09-08(フェーズ43)

## 背景・気付いた未整理点

これまで、workshopの一時状態(pending state)に応じてLLM呼び出し前のプロンプト文脈を
切り替える設計が、必要になった順に個別に確定してきた。

1. member-retention-notice-design.md(フェーズ29): `pending_member_reduction_
   effective_at`が設定済み(ダウングレード後の縮小猶予期間中)かつ送信者が契約者本人の
   場合、「残すメンバー」連絡の文脈を注入する。
2. contractor-transfer-confirmation-detection-design.md(フェーズ36): `pending_
   contractor_transfer`が存在し期限内、かつ送信者が契約者本人の場合、契約者譲渡の
   再確認応答を検知する文脈を注入する(`is_contractor_transfer_confirmation_context`)。
3. contractor-transfer-expired-notice-design.md(フェーズ39・実装はフェーズ40):
   `check_and_expire_pending_contractor_transfer`が直前の呼び出しで期限切れを検出した
   場合、送信者・メッセージ内容によらず期限切れ案内の文脈を強制注入する。

これら3つはそれぞれの設計文書の中では単独の条件式として明確だが、1つの`workshop_id`に
複数の一時状態が同時に存在しうるケースが検討されないまま残っていた。例えば、契約者が
「太郎さんに交代したい」と譲渡申請中(`pending_contractor_transfer`が期限内)の
workshopが、直前にダウングレードもしており`pending_member_reduction_effective_at`も
設定済み、という状態は設計上あり得る(craftsman-account-linking-design.mdは1人1workshop
のみと簡素化しているが、譲渡申請と縮小猶予は同じworkshop内で独立に発生しうる別種の
一時状態であり、互いを禁止する制約はこれまで一度も設けられていない)。この場合、契約者
本人からのメッセージに対してどちらの文脈を注入すべきかが未定義だった。本ファイルはこの
優先順位を確定する。

## 1. 優先順位の確定

送信者`user_id`から`workshop_id`を特定した後、以下の順に該当する文脈を1つだけ選び、
最初に該当したものを採用する(先勝ち・排他)。

```
(a) check_and_expire_pending_contractor_transfer(workshop_id, now, workshop_store)
    が非Noneを返した(=直前の呼び出しで期限切れを検出した)
        → 契約者譲渡・期限切れ案内の文脈を注入
        (送信者が契約者本人かどうかを問わない。contractor-transfer-non-contractor-
        message-design.mdで確認済みの通り、期限切れ後は誰からのメッセージでも
        pending状態自体が既にクリアされるため、この文脈は最大1回しか注入されない)

(b) 送信者 == workshopのcontractor_user_id
    かつ is_contractor_transfer_confirmation_context(...) が真
        → 契約者譲渡・再確認応答検知の文脈を注入

(c) 送信者 == workshopのcontractor_user_id
    かつ workshop.pending_member_reduction_effective_at が設定済み
        → 「残すメンバー」連絡検知の文脈を注入

(d) 上記いずれにも該当しない
        → 通常の生成リクエスト文脈(process_generation_requestの入出力)
```

## 2. 優先順位の根拠

- (a)を最優先とする理由: 期限切れ案内はcontractor-transfer-expired-notice-design.md
  4節の方針により能動プッシュ通知を行わず「次回メッセージ受信時の受動的な案内」に
  委ねる設計である。この1回の受動案内の機会を他の文脈に奪われて取りこぼすと、契約者は
  譲渡申請が失効したことを永久に知らされない可能性がある(次に契約者本人からメッセージが
  来るとは限らない)。一方、`pending_member_reduction_effective_at`はチェックする度に
  再評価される(period_endを過ぎていれば毎回該当し続ける)ため、1回の受信で(a)を優先
  しても次回以降のメッセージで(c)が改めて評価される機会は失われない。
- (b)を(c)より優先する理由: 契約者譲渡は工房の統治(誰が契約者本人であるかという
  根本的な権限の所在)そのものに関わる操作であり、craftsman-account-linking-design.md
  4節が示す通り解約・ダウングレード操作権限の判定基準に直結する。これに対し「残すメンバー」
  連絡はプランのメンバー枠という運用上の細目であり相対的に重要度が低い。また譲渡の再確認
  応答は24時間の期限付き(contractor-transfer-confirmation-detection-design.md1節)で
  あるのに対し、縮小猶予は次回請求サイクル開始まで(通常は数日〜1ヶ月弱)と期間が長く、
  1回のメッセージで(c)の検知を後回しにしても致命的な機会損失にはなりにくい。
- (a)(b)(c)がいずれも排他的である(同時に真になる組み合わせが無い)ことをschema側で
  保証する必要はない。status enum(`contractor_transfer_expired_notice`・
  `contractor_transfer_confirmed`等・`member_retention_selection`等)は既に互いに
  独立した値として設計済み(各フェーズのvalidate_cross_field_rulesがそれぞれの
  排他性のみを検証)であり、本ファイルが定める優先順位は「複数の条件が同時に真になり得る
  という入力側(workshopの状態)の話」であって、LLMの構造化出力側の排他性とは別レイヤーの
  制約である。両者を混同しないよう、本ファイルの優先順位判定はLLM呼び出し**前**の文脈
  選択ロジック(アプリケーション側の責務)として位置づける。

## 3. 未実装であることの確認(フェーズ104追記: 本節はフェーズ44時点で解消済み。
下記の記述は作成当時〈フェーズ43〉の状態の記録として残すが、6節の追記を参照のこと)

現時点のprototype/usage_counter_workshop.pyには、上記4段階を1つの関数へ統合する実装
(`select_message_context`相当)は存在しない。個々の判定関数
(`check_and_expire_pending_contractor_transfer`・
`is_contractor_transfer_confirmation_context`・`pending_member_reduction_effective_at`の
存在確認・`process_generation_request`)はいずれも実装済みだが、それらを呼び出す順序を
1箇所にまとめる統合レイヤーは無い。`process_generation_request`は(d)のみを扱う関数
であり、名称からもメッセージ受信全体のエントリポイントではなく生成リクエスト専用である
ことを明確にしている。次の課題として、以下を実装する。

- `select_message_context(user_id, now, user_profile_store, workshop_store,
  usage_counter_store) -> MessageContext`(仮称)という統合関数を新設し、本ファイル1節の
  優先順位をコードに落とし込む。
- (d)に該当した場合のみ内部で`process_generation_request`を呼び出す形にし、既存の
  70件のテストへの影響を避ける(既存関数のシグネチャ・挙動は変更しない)。
- 各分岐に対応する新規テストケース(特に(a)(b)が同時に真になりうる状態を人為的に
  作った場合に(a)が優先されることを検証するケース)を追加する。

## 4. 未検証・残課題(フェーズ104追記: 1点目はフェーズ44時点で解消済み。6節参照)

- ~~上記3節の統合関数`select_message_context`(仮称)自体の実装・テストは本ファイルでは
  扱わず次の課題とする。~~ → フェーズ44(2026-09-08 14:00 UTC)で
  `prototype/usage_counter_workshop.py`に実装・テスト8件追加済み。ただし6節の通り、
  実際の呼び出し元への配線は別問題として未着手のまま残っている。
- (b)(c)が同時に真になるケース(契約者譲渡の再確認応答待ちと縮小猶予期間が重複する
  workshop)は理論上あり得ると整理したが、実際にそのような状態が生じる業務上の頻度・
  蓋然性は未検証(いずれもオーナー承認後の実運用データが無いと検証できない)。
- 実際のLINE公式アカウント接続・Stripe接続・実LLM検証は引き続きオーナー承認待ちの範囲
  (pending-approval.md参照)。

## 5. 追記(フェーズ101): 厳守事項7a/7b/7c意図検知との関係の整理

craftsman-account-linking-design.md 11.3節が「message-context-selection-design.mdへの
優先順位組み込み(契約者からの通常メモ送信・他の一時状態〈(a)〜(d)〉との割り込み位置の
検討)」を未着手の残課題としていた件に対応する。

結論: 厳守事項7a(解約意図検知)・7b(有料プラン開始意図検知)・7c(職人追加・招待コード
発行意図検知)のいずれも、(a)(b)(c)のような独立した「pre-injection文脈」を新設する必要は
ない。3種とも`subscription_procedure_notice`/`checkout_notice`/`workshop_invite_notice`
という`status`enum値・付随フィールドとして、既存の(d)「通常の生成リクエスト文脈」1回の
LLM呼び出し(`process_generation_request`)が返す構造化出力の一部にすぎず、呼び出し**前**に
どの文脈を注入するかを分岐させる(a)(b)(c)とは設計レイヤーが異なるためである(1節末尾です
でに「両者を混同しないよう」と整理済みの区別と同じ)。したがって(a)〜(d)の4段階の優先
順位はそのままで変更不要であり、7a/7b/7cはすべて(d)に内包される。

この結論の帰結として、(a)(b)(c)のいずれかに該当したメッセージ(期限切れ案内・譲渡再確認・
縮小連絡)では、そのメッセージ自体がたとえ「職人を追加したい」等の7c相当の文面を含んでいても、
LLMは呼び出されず7a/7b/7cの意図検知は一切行われない(該当する文脈のプロンプトへ強制的に
差し替わるため)。これは1節の根拠(a)(b)(c)の重要度説明とも整合する。例えば契約者譲渡の
期限切れ案内(a)を受け取るべき送信者が同じメッセージで職人追加を申し出ていた場合、7cの
意図検知は次回以降のメッセージ受信時まで持ち越される。これは意図的な設計判断であり、
不具合ではない(期限切れ案内という1回限りの受動通知機会〈1節(a)の根拠〉を7c検知のために
犠牲にしないという優先順位を維持するため)。

よって`select_message_context`(仮称、3節)の実装時、7a/7b/7cのための分岐追加は不要で
あることを本節で確定する。3節の実装スコープ(a)(b)(c)(d)の4分岐のみで足りる。

## 6. 追記(フェーズ104): `select_message_context`が呼び出し元に一度も配線されていない
未着手のギャップの発見

フェーズ102・103(craftsman-account-linking-design.md 11.7・11.8節)がいずれも「次回候補」
として「3節`select_message_context`統合関数自体の実装」を挙げ続けていたため、本フェーズで
着手しようとしたところ、3節・4節の記述自体が既に古く、`select_message_context`は
フェーズ44(2026-09-08 14:00 UTC、README.md参照)の時点で`prototype/usage_counter_
workshop.py`へ実装・テスト8件追加済みであることが判明した(3節・4節に訂正済み)。少なくとも
5回分のフェーズ(101〜103、および11.6〜11.8節)にわたり、既に解消済みの課題を「未着手」と
誤認したまま「次にやること」として引き継ぎ続けていた記載漏れである。

**さらに調査した結果判明した、より本質的な未解決のギャップ**: `select_message_context`は
実装・単体テストとも存在するにもかかわらず、実際のLINEメッセージ受信の入口である
`prototype/cloud_function_webhook.py`の`process_message_event()`・`process_memo_event()`
のどちらからも一度もimport・呼び出しされていない(`grep -n "select_message_context"
prototype/cloud_function_webhook.py`で確認、ヒット無し)。`process_memo_event()`は現在も
常に`usage_counter_workshop.process_generation_request()`(= (d)のみ)を直接呼び出しており、
(a)(b)(c)の3分岐(契約者譲渡期限切れ案内・契約者譲渡再確認・残すメンバー連絡)へ切り替える
経路が実装コード上どこにも存在しない。

加えて、`llm-system-prompt-draft.md`を「contractor_transfer_confirm」「contractor_transfer_
expired」「member_retention」の各キーワードで検索してもヒットが無く、LLMへ渡す
システムプロンプト側にもこれら3状態を扱う記述が一切無い。`prototype/test_cloud_function_
webhook.py`の`test_process_memo_event_contractor_transfer_expired_notice_returns_body()`
等の既存テストは、`_StubLlmCall`でLLM呼び出し自体をスタブ化し「LLMが
`status=contractor_transfer_expired_notice`を返した前提」で`format_reply_text()`の
文面抽出ロジックのみを検証しており、実際の運用でこの`status`がどうやって生成されるかは
検証していない。

以上を総合すると、(a)(b)(c)の3つの通知系統(契約者譲渡期限切れ案内・再確認・残すメンバー
連絡)は、設計文書・schema・整形ロジック・`select_message_context`の単体テストがいずれも
存在するにもかかわらず、**現時点の実装では実際のメッセージ受信フローから到達不可能**
という状態にある。これは1節冒頭の「1つのworkshopに複数の一時状態が同時に存在しうる
ケースの優先順位」という設計課題以前の、より基礎的な「そもそも(a)(b)(c)へ分岐する経路が
実装されていない」という配線漏れである。

**本フェーズでは対応せず記録のみにとどめた理由**: 実際の配線には(1)`process_memo_event()`
を`select_message_context()`経由に置き換える制御フロー変更、(2)(a)(b)(c)それぞれに対応する
返信文面をLLM呼び出し無しで生成する経路の設計(現状これらの`status`はLLM構造化出力の一部
としてのみ定義されており、Python側の決定論的な定型文言生成関数〈`format_limit_approaching_
notice()`同様のもの〉が存在しない)、(3)関連する既存687件のテストへの影響範囲の洗い出し、
が必要であり、1フェーズの作業量を超えると判断したため、次の課題として明記するにとどめる。

**次の課題(優先順位案)**:
1. (a)(b)(c)それぞれについて、LLM呼び出し無しでPython側の決定論的な定型文言を返す
   `format_contractor_transfer_expired_notice_message()`等の整形関数を新設する方針
   (`member_limit_reached`〈11.8節〉と同じ「Python側エラーコード→固定文言」パターンを
   踏襲できるか検討する)、または既存方針通りLLM構造化出力側に委ねるなら
   `llm-system-prompt-draft.md`へ(a)(b)(c)用のプロンプト文脈を新設する方針、のいずれを
   採るか設計判断を行う。
2. 1.の方針決定後、`process_message_event()`/`process_memo_event()`を
   `select_message_context()`経由に配線し直す。
3. 配線後、(a)(b)(c)が実際のメッセージ受信フローで到達可能になることを検証する統合
   テストを追加する(現状の`test_process_memo_event_contractor_transfer_expired_notice_
   returns_body()`等はLLM出力のスタブ止まりであるため、統合テストとしては不十分)。

## 7. 追記(フェーズ105): 6節「次の課題1.」の方針決定(Python決定論的テンプレート
か、LLM構造化出力への委任か)

6節が「次の課題」1点目としていた、(a)(b)(c)それぞれの返信文面をどう生成するかの
設計判断を行う。

**結論: 3つとも既存方針(LLM構造化出力への委任)を維持し、`member_limit_reached`
(craftsman-account-linking-design.md 11.8節)のようなPython側決定論的テンプレートには
切り替えない。** 理由は(b)(c)と(a)で異なる。

- (b)契約者譲渡・再確認応答検知、(c)「残すメンバー」連絡検知は、いずれも受信メッセージ
  本文(自由記述の自然文)から意図(譲渡を確認するか取り消すか/どのメンバーを残すか)を
  解釈する必要がある。これは厳守事項7a(解約意図検知)・7b(有料プラン開始意図検知)・
  7c(職人追加意図検知)がまさに同種の自然文解釈をLLMに委ねている設計(1節末尾の判定
  基準)と同じ性質の作業であり、キーワード一致等のPython側ヒューリスティックでは
  「太郎さんでお願いします」のような表記ゆれ・言い換えを安定して解釈できない。従って
  (b)(c)はLLMによる意図解釈が必須であり、決定論的テンプレートへの切り替えは選択肢と
  ならない。
- (a)契約者譲渡・期限切れ案内は、受信メッセージの内容に関わらず強制される一言案内
  (contractor-transfer-expired-notice-design.md 1節)であり、`candidate_member_name`を
  文中に差し込むだけの機械的な文章生成という点では`member_limit_reached`と類似する。
  しかし本ventureはtone-and-manner-guideline.mdで職人向け実務文書としての文体(ですます調・
  絵文字不使用等)をLLM生成文言全体で統一する方針を既に確定しており、`member_limit_
  reached`はエラーコード分岐(あくまで機能不全時の定型案内)である一方、(a)は通常の
  サービス利用フローの一部として送られる案内文であるため、他のLLM生成文言(お手入れ
  案内・納品案内等)と地の文の書き味を揃える必要がある。この一貫性を保つコストのほうが
  「LLM呼び出し1回を節約する」利益より大きいと判断し、(a)もLLMに委ねる方針を維持する。
  (`candidate_member_name`が非nullである限りbody生成の自由度は低く、事実上テンプレート的な
  出力になる想定だが、生成方式としてはLLM呼び出しを経る点で(b)(c)と統一する。)

**帰結: 8節(新設、次項)の通り、(a)(b)(c)はいずれも「LLM呼び出し前にアプリケーション側が
選択した文脈を、システムプロンプトへ追加指示として注入し、その回のLLM呼び出しでは通常の
受注メモ生成(厳守事項1〜8・7a〜7c)を行わず、注入された文脈に対応するstatusのみを返す」
という統一的な扱いとする。** これは7a〜7cが「通常の生成リクエスト文脈(d)の中で常時
評価される分岐」であるのに対し、(a)(b)(c)は「(d)そのものを差し替える、より優先度の高い
強制文脈」であるという1節の整理と整合する。llm-system-prompt-draft.mdには、7a〜7cとは
別枠で「文脈注入時の追加指示」として(a)(b)(c)用のプロンプト文面を新設する(厳守事項の
番号は流用せず、既存の1〜8・7a〜7cとは別区分であることを明示する)。

**本フェーズで着手した範囲**: 3つのうち最も設計が確定している(a)のプロンプト文面を
llm-system-prompt-draft.mdへ新設した(該当追記参照)。(b)(c)は以下の理由で本フェーズでは
プロンプト文面の新設まで進めず、次の課題として残す。

- (b)は、contractor-transfer-confirmation-detection-design.md 3節が既に
  `contractor_transfer_confirmed`/`contractor_transfer_cancelled`/`contractor_
  transfer_reconfirm_unclear`の3分岐とschema(`contractor_transfer_confirmation`
  フィールド)を確定させている一方、プロンプトへどう`candidate_member_name`(確認対象)を
  渡すかの記述がまだ無い。
- (c)は、member-retention-notice-design.md側で「残すメンバー」選択の対象となる
  メンバー一覧(`member_user_ids`)をどうプロンプトへ渡すか(名前は`user_profile`側に
  あるがLLMにuser_id自体を渡すべきか等)の整理が必要で、(a)より設計の手戻りリスクが
  高いと判断した。

**次の課題**: (b)(c)のプロンプト文面新設、その後8節で述べる「文脈注入」の実装
(`LlmCallClient.generate()`の呼び出し前に注入文脈を組み立てて渡す経路、および
`process_message_event()`/`process_memo_event()`を`select_message_context()`経由に
置き換える制御フロー変更)に着手する。実装時は既存687件のテストへの影響範囲の洗い出しが
必要になるため、複数フェーズに分けて進める想定。

最終更新: 2026-09-13 07:00 UTC(フェーズ105: 6節「次の課題1.」の方針決定〈LLM構造化出力
への委任を維持〉、(a)のプロンプト文面新設に着手)

## 8. 追記(フェーズ106): (b)契約者交代・再確認応答検知のプロンプト新設

7節「本フェーズで着手した範囲」が(b)(c)のうち先に着手する対象として挙げていた(b)に
ついて、contractor-transfer-confirmation-detection-design.md 3節で既に確定していた
判定パターン(肯定/否定/不明瞭の3分類)・schema設計(status 3値・`contractor_
transfer_confirmation`フィールド)をもとに、llm-system-prompt-draft.mdへプロンプト
文面を新設した(該当追記参照)。(a)が「受信内容を問わず常に同じ一言を返す」構造だった
のに対し、(b)は厳守事項7a〜7cと同種の自然文からの意図解釈による3分岐判定である点が
異なる。

なお着手にあたり確認したところ、schema/output.schema.json・schema/validate_test_
cases.pyへの反映(status enum3値・`contractor_transfer_confirmation`フィールド追加、
CTC1〜CTC3等の正例テストケース)はフェーズ37(2026-09-08 02:00 UTC)の時点で既に完了
済みであった。本フェーズで必要だったのはプロンプト文面のみであり、schemaへの追加反映は
不要だった。

**次の課題**: (c)「残すメンバー」連絡検知のプロンプト文面新設。member-retention-
notice-design.mdが未整理としている「メンバー一覧(`member_user_ids`)をどうプロンプト
へ渡すか(名前のみか、user_id自体も渡すか)」の設計判断が(c)着手の前提となる(`member_
retention_notice`のstatus enum・専用フィールド自体は2026-09-07 13:02 UTC改訂で既に
反映済みであり、(b)同様schema拡張は不要と見込む)。その後、`LlmCallClient.generate()`
への文脈注入経路の実装、`process_message_event()`/`process_memo_event()`を
`select_message_context()`経由に置き換える制御フロー変更、統合テストの追加に着手する。

最終更新: 2026-09-13 10:00 UTC(フェーズ106: (b)契約者交代・再確認応答検知のプロンプト
文面を新設。(c)・schema反映・実配線は次の課題)
