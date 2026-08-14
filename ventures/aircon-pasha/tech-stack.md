# 技術構成案(初回メモ)

mvp-flow-draft.md「会話フロー・技術構成に関する方針」で「システム構成上のシンプルさ」に
触れつつも具体化は次回以降の課題としていた点、およびsubscription-billing-cost-estimate.mdで
指摘された「本ventureにはtech-stack.md自体が未作成」というギャップに対応する初回メモ。
course-set-pasha/tech-stack.mdの構成を踏襲しつつ、本venture固有の季節性(繁忙期は施工件数が
閑散期の2〜3倍)を反映する。

## 全体構成イメージ

LINE公式アカウント(業者本人向け) ⇄ Webhookサーバー ⇄ LLM(3出力生成) ⇄ 返信メッセージ(下書きをそのまま返す)

course-set-pashaと同様、双方向の会話状態管理は不要な単方向バッチ処理
(「1メモ受信 → LLM呼び出し → 3種類のテキスト生成 → 返信」)で完結する。ただし
course-set-pashaと同じく、月間生成回数の上限管理(pricing-plan.md)という用途に限り、
月をまたいだ回数の積算が必要になる点は例外となる(コンポーネント5参照)。

## 想定コンポーネント

1. **LINE Messaging API(入力受付・返信)**
   - 業者本人が使う入力チャネル。顧客対応ではなく事業者本人向けのツールである点は
     course-set-pashaと同じで、Botとの1:1トークで完結する。
   - 施工メモ(+任意の施工前後写真)を受け付け、返信で3出力の下書きをまとめて送る。
2. **Webhook / バックエンド**
   - line-reservation-aiで選定済みのGCP Cloud Functions (Python)を第一候補として流用する
     (hosting-platform-selection.mdの比較結果を踏襲)。実際のGCPプロジェクト作成・
     請求先設定は着手時にオーナー承認が必要。
   - market-research.mdの月60〜100件(繁忙期はさらに増加)という利用量見積もりは、
     course-set-pashaの月8〜30回程度より一桁多いが、いずれもサーバーレスの従量課金特性と
     相性が良い低頻度・単発処理の範囲内であり、構成自体を変える必要はないと見込む。
3. **LLM(3出力生成)**
   - 入力メモ(+画像有無)→ 想定システムプロンプト(次の課題として作成予定、
     course-set-pasha/llm-system-prompt-draft.mdの厳守事項リスト形式を踏襲予定)に沿って
     出力1(依頼者向け作業完了報告)・出力2(お手入れ案内)・出力3(history_rows)を
     構造化出力形式で生成する。
   - mvp-flow-draft.mdの厳守事項(冷媒ガス・電気系統への専門的助言をしない、メモに無い
     効果を推測で付け足さない)をシステムプロンプトの必須制約とする方針は据え置き。
4. **画像の一時保存**
   - course-set-pashaと同様、画像内容の自動解析は行わず「添付の有無」のみを判定材料とする
     設計を踏襲する想定。専用の永続ストレージ(Cloud Storage等)は不要とし、Webhook処理中の
     一時メモリ上の有無判定のみに用途を限定する。
5. **月間生成回数カウントの保存先**
   - course-set-pashaのlimit-approaching-notification-design.md・本コンポーネントで検討した
     結果を踏襲し、月間生成回数の積算のみを目的とした軽量データストア(Firestore等)を導入する
     方針とする。「ユーザー1人=1ドキュメント、フィールドは`month`・`count`のみ」という
     最小構成はcourse-set-pashaと同一で足りると見込む。
   - `usage_counter`(仮称`UsageCounterProtocol`、`get_count`/`increment`の2メソッド)として
     Webhook処理から差し替え可能な形で抽象化する想定もcourse-set-pashaを踏襲。
   - 本venture固有の論点: 季節性により月間カウントの振れ幅がcourse-set-pashaより大きい
     (繁忙期は閑散期比2〜3倍)。上限接近時の事前通知(残り○回等)を出す閾値・タイミングは、
     course-set-pashaの設計をそのまま流用せず、繁忙期の急激な回数増加ペースを踏まえた
     再検討が必要(次の課題として残す。course-set-pasha/limit-approaching-notification-design.md
     相当のドキュメントは本ventureではまだ作成していない)。
   - 実際のFirestoreプロジェクト作成・接続はオーナー承認待ちの範囲(設計・スタブ実装まで)。
   - 読み書き課金の原価試算はsubscription-billing-cost-estimate.mdの粗利率試算に含まれていない
     ため、course-set-pasha/subscription-billing-cost-estimate.mdの試算方法を踏まえた追試算が
     別途必要(次の課題)。

## MVPスコープ(最小構成)

- 入力は1メッセージ=1回の施工メモ(pricing-plan.mdの課金単位「1メモ送信=1回」に対応)。
- 会話状態マシンは不要(course-set-pashaと同じ)。
- 画像は「有無」のみを判定材料とし、画像内容の自動解析は範囲外。
- 月間生成回数カウント用の最小限のデータストア(コンポーネント5)のみ例外的に持つ。

## 初期投資・ランニングコストの目安

- 開発: 既存クラウドサービス・LLM APIの組み合わせのみで、専用インフラ購入は不要。
- ランニング: LINE Messaging APIの無料枠+LLM API従量課金+軽量データストアの読み書き課金
  (コンポーネント5)。月間利用回数がcourse-set-pashaより一桁多いため、LLM API従量課金・
  データストア読み書き課金ともに絶対額はcourse-set-pashaより大きくなる見込みだが、
  1回あたりの限界費用がごく小さい点は変わらない。

## 次のステップ候補

- 本venture固有の季節性(繁忙期は施工件数が閑散期の2〜3倍)を踏まえた、上限接近時の事前通知
  設計(course-set-pasha/limit-approaching-notification-design.md相当のドキュメント作成)。
- 月間生成回数カウント用データストア(Firestore等)の読み書き課金の原価試算
  (course-set-pasha/subscription-billing-cost-estimate.mdの試算方法を踏まえた追試算)。
- システムプロンプト草案・構造化出力スキーマ(JSON Schema)の作成
  (mvp-flow-draft.md「次の課題」より引き続き未着手)。
- 実LLM呼び出し・LINE公式アカウントとの実接続は、line-reservation-ai・course-set-pashaと
  同様にAPIキー取得・アカウント作成が必要でありオーナー承認待ちの範囲。今回は技術構成の
  設計整理のみに留める。
