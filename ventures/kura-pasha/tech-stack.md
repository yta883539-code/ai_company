# 技術構成案(初回メモ)

他venture(aircon-pasha・course-set-pasha・line-reservation-ai)には既にあるが本venture
未着手だったtech-stack.md自体のcross-venture parityギャップに対応する初回メモ。
aircon-pasha/tech-stack.mdの構成を踏襲しつつ、本venture固有の低頻度受注特性
(納期数ヶ月に及ぶオーダーメイドが中心で受注件数自体が少ない、llm-api-cost-estimate.md
参照)と、workshop単位の複数職人共同利用構造(craftsman-account-linking-design.md・
subscription-billing-data-model-design.md・usage-counter-workshop-key-design.md参照)を
反映する。

## 全体構成イメージ

LINE公式アカウント(職人本人向け) ⇄ Webhookサーバー ⇄ LLM(3出力生成) ⇄ 返信メッセージ(下書きをそのまま返す)

course-set-pasha・aircon-pashaと同様、双方向の会話状態管理は不要な単方向バッチ処理
(「1メモ受信 → LLM呼び出し → 3種類のテキスト生成 → 返信」)で完結する。ただし本venture
固有の構造として、月間生成回数の上限管理・課金主体が`user_id`単位ではなく
`craftsman_workshop/{workshop_id}`単位である点が他3ventureと異なる
(コンポーネント4・5参照)。

## 想定コンポーネント

1. **LINE Messaging API(入力受付・返信)**
   - 職人本人が使う入力チャネル。顧客対応ではなく事業者(職人)本人向けのツールである点は
     他ventureと同じで、Botとの1:1トークで完結する。
   - 受注メモ(区分: 新規制作/修理、鞍の型、革の種類、金具仕様、用途、納期、備考)を
     受け付け、返信で3出力(受注内容整理メモ・納品案内下書き・お手入れ案内下書き)の
     下書きをまとめて送る。
2. **Webhook / バックエンド**
   - line-reservation-aiで選定済みのGCP Cloud Functions (Python)を第一候補として流用する
     (hosting-platform-selection.mdの比較結果を踏襲)。実際のGCPプロジェクト作成・
     請求先設定は着手時にオーナー承認が必要。
   - market-research.mdの見積もり(候補母数が構造的に少なく、他ventureより低頻度)は
     いずれもサーバーレスの従量課金特性と相性が良い低頻度・単発処理の範囲内であり、
     構成自体を変える必要はないと見込む。
3. **LLM(3出力生成)**
   - 入力メモ→ llm-system-prompt-draft.mdの厳守事項リストに沿って出力1(受注内容整理
     メモ)・出力2(納品案内下書き、区分に応じて新規制作/修理で分岐)・出力3(お手入れ
     案内下書き)を構造化出力形式(schema/output.schema.json)で生成する。
   - mvp-flow-draft.mdの厳守事項(採寸・型紙作成・革選定・縫製・仕上げ等の専門的判断、
     および修理可否の判断への不介入)をシステムプロンプトの必須制約とする方針は据え置き。
   - llm-api-cost-estimate.mdの試算により、低頻度利用ゆえにプロンプトキャッシュの効果が
     薄い可能性が高く、キャッシュなし前提でも粗利は十分に残るため実装優先度は他venture
     より下げてよいと判断済み。
4. **課金・契約単位のデータストア(Firestore)**
   - `craftsman_workshop/{workshop_id}`: `contractor_user_id`・`member_user_ids`・
     `plan_id`・`stripe_customer_id`・`subscription_status`・`trial_start_at`・
     `current_period_end`等、契約・課金に関するフィールドを一括して持つ
     (subscription-billing-data-model-design.md「配置の確定」)。決済主体が
     workshopそのものであり個々の`user_id`ではないため、他3venture
     (`user_profile`側に課金フィールドを直接持たせる構造)とはStripe Webhookの
     解決先(`stripe_customer_id → workshop_id`)が異なる点が唯一の構造的な差異。
   - `user_profile/{user_id}`: `workshop_id`のみを持ち、課金関連フィールドは持たない
     (LINEのfollow/unfollow状態は別途追加予定)。
   - `usage_counter/{workshop_id}`: 月間生成回数の積算(`month`・`count`)。
     ライト/スタンダード/複数職人いずれのプランも`workshop_id`キーで一貫させ、
     プラン間でカウンタ参照ロジックを分岐させない(usage-counter-workshop-key-design.md)。
5. **画像の一時保存**
   - 他venture同様、画像内容の自動解析は行わず「添付の有無」のみを判定材料とする設計
     (専用の永続ストレージは不要、Webhook処理中の一時メモリ上の有無判定のみに限定)。

## MVPスコープ(最小構成)

- 入力は1メッセージ=1回の受注メモ(pricing-plan.mdの課金単位「1メモ送信=1回」に対応)。
- 会話状態マシンは不要(他venture同様)。
- 画像は「有無」のみを判定材料とし、画像内容の自動解析は範囲外。
- 課金・回数上限管理はworkshop単位(コンポーネント4)。

## 初期投資・ランニングコストの目安

- 開発: 既存クラウドサービス・LLM APIの組み合わせのみで、専用インフラ購入は不要。
- ランニング: LINE Messaging APIの無料枠+LLM API従量課金+Firestore読み書き課金。
  他ventureより受注頻度自体が低い(市場調査で確認した候補母数の少なさに対応)ため、
  月間の絶対額は他venture(特にaircon-pasha・course-set-pasha)より小さくなる見込み。

## 未検証・残課題

- (訂正 2026-09-12 12:00 UTC・フェーズ91): 本節はsubscription-billing-data-model-
  design.md「4. 未検証・残課題」を要約する形でフェーズ88に作成したが、同ファイルの
  「Checkout Session発行フロー・Stripe Webhookの署名検証・イベントディスパッチの実装は
  未着手」という記載自体がフェーズ50・51(2026-09-08)で対応済みにもかかわらず訂正
  されていなかった記載漏れであり、本節も同じ記載漏れをそのまま引き継いでいたことが
  判明した。実際には`prototype/checkout_session.py`(Checkout Session発行)・
  `prototype/stripe_webhook.py`(`verify_stripe_signature()`・`receive_stripe_webhook()`)
  として実装済みであることを確認した(subscription-billing-data-model-design.md側も
  本フェーズであわせて訂正済み)。
- `current_period_end`フィールドの読み書きメソッド(`WorkshopStoreProtocol`への
  永続化用メソッド)は引き続き未着手。トライアル条件判定関数はtrial-end-condition-
  design.md(フェーズ52、`is_trial_period_over`)として対応済み。
- 実際のGCPプロジェクト作成・LINE公式アカウント接続・Stripeアカウント接続は、
  他ventureと同様にアカウント作成・支払いが発生するためオーナー承認待ちの範囲
  (pending-approval.md参照)。今回は技術構成の整理・cross-venture parityギャップの
  解消のみに留める。

最終更新: 2026-09-12 12:00 UTC(フェーズ91: 記載漏れ訂正)
