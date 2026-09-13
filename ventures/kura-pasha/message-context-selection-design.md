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

## 3. 未実装であることの確認

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

## 4. 未検証・残課題

- 上記3節の統合関数`select_message_context`(仮称)自体の実装・テストは本ファイルでは
  扱わず次の課題とする。
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

最終更新: 2026-09-13 03:00 UTC(フェーズ101)
