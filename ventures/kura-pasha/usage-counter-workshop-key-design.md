# usage_counterキー移行設計(user_id → workshop_id)(フェーズ26)

作成日: 2026-09-07(フェーズ26)

## 背景・対応する残課題

craftsman-account-linking-design.md(フェーズ25)「未検証・残課題」1点目、および
README.md「次にやること(候補)」1点目で指摘されていた、`usage_counter`のキーを
user_idからworkshop_idへ読み替える対応を行う。

先に確認しておくと、`usage_counter`はLLMへの入出力そのものではなく月間生成回数を
積算するFirestore側のカウンタであり、schema/output.schema.json(LLM構造化出力スキーマ)
には元々登場しない概念である。そのため本フェーズは output.schema.json /
validate_test_cases.py への直接の変更ではなく、pricing-plan.mdの月間生成回数枠の
運用主体を確定させる設計文書として本ファイルを新規作成する形で対応する
(README.mdの次課題文言はやや不正確だった点を本ファイルの冒頭で訂正しておく)。

## 1. なぜuser_idキーのままでは成立しないか

pricing-plan.md「複数職人プラン」(月20回まで・複数職人での共同利用)は、1つの契約
(=1つの月間生成回数枠)を複数の職人(複数のuser_id)が共有する前提である。
`usage_counter`をuser_idキーのままにすると、職人ごとに別々の月20回枠を持って
しまい、実質的に契約単位の上限が意味を失う(工房全体でのべ最大60回等、メンバー数×
20回まで生成できてしまう抜け穴になる)。craftsman-account-linking-design.md
(フェーズ25)でcraftsman_workshopという契約単位が確定したことで、この抜け穴が
明確になった。

## 2. 確定する設計

- `usage_counter`のドキュメントキーを`{user_id}`から`{workshop_id}`へ変更する。
  フィールド構成(`month`・`count`)自体は変更しない。
- ライト/スタンダードプラン(craftsman-account-linking-design.md 3節により1人だけの
  workshopとして統一的に扱われる)も、`workshop_id`キーで一貫させる。これにより
  プラン間でカウンタの参照ロジックを分岐させる必要がなくなる。
- 生成リクエスト受信時のカウント処理は次の手順に統一する。
  1. 送信元`user_id`から`user_profile/{user_id}.workshop_id`を引く。
  2. `usage_counter/{workshop_id}`を読み、`month`が当月でなければ`count=0`で
     リセットしてから加算する(リセット判定ロジック自体はcourse-set-pashaの
     既存方式をそのまま踏襲し、本ファイルでの再検討は行わない)。
  3. `plan_id`は`craftsman_workshop/{workshop_id}.plan_id`から取得し、
     pricing-plan.mdのプラン別上限(3回/8回/20回)と突き合わせて上限超過時の
     従量課金要否を判定する。
- ダウングレード時の`count`の扱い(現行請求サイクル内は`count`を維持し上限のみ
  新プラン値へ差し替える)は、subscription-cancellation-flow-design.mdが既に
  踏襲済みのcourse-set-pasha方式のままとし、キーがworkshop_idに変わる点以外の
  変更はない。

## 3. schema/output.schema.json・validate_test_cases.pyへの影響範囲(確認結果)

`usage_counter`はLLMの構造化出力に含まれないフィールドであるため、
schema/output.schema.jsonの`required`/`properties`定義には変更が発生しない。
validate_test_cases.pyの各TEST_CASESフィクスチャにも影響はない
(いずれも1回の生成リクエストに対する出力形を検証するものであり、月間の
累積回数管理はコード側の別レイヤーに属するため)。よって本フェーズでは両ファイルへの
編集は不要と結論づける。「次にやること」の該当項目は本ファイルの作成をもって解消済みとする。

## 4. 月の途中でworkshopが新規作成された場合の上限按分(フェーズ32で追記)

「未検証・残課題」2点目(複数職人プランの請求サイクル境界とworkshop作成
タイミングがずれるケースでの当月上限の按分要否)を検討する。

- 前提の再確認: `usage_counter/{workshop_id}`の`month`は**Stripeの請求サイクル
  (billing_cycle_anchor)ではなく暦月(カレンダー月)**でリセットされる設計である
  (本ファイル2節、course-set-pasha既存方式の踏襲)。上限(3回/8回/20回)は
  「1暦月あたりの固定枠」であり、日割りで積み上がっていく性質の枠ではない
  (例えば「1日あたり◯回」を1ヶ月分積算したものではない)。
- 結論: **按分は不要、月の途中で作成されたworkshopにもその月の残り期間について
  満額の月間上限をそのまま適用する**。理由は次の2点。
  1. 上限がそもそも時間比例(日割り)の性質を持たない固定枠であるため、
     「按分」という操作自体が定義できない(1日あたりの枠という概念が存在しない)。
  2. 課金(Stripeサブスクリプション料金)側は既にpricing-plan.md・
     course-set-pasha踏襲のプロレーション機能で日割り精算されており
    (ダウングレード時のプロレーションはsubscription-cancellation-flow-design.md
     で確認済み)、新規契約時もStripe側の初回請求額は契約日からの日割りに
     なる。つまり「お金は使った日数分」「生成回数枠は満額」という組み合わせは、
     course-set-pasha・aircon-pashaの単一契約でも月の途中で新規契約したユーザーに
     対して既に生じている状態であり、本ventureのworkshopに固有の問題ではない
     (workshop構造の導入によって新たに生じた論点ではなく、単に暦月リセット方式を
     採用した時点で既存venture群にも共通して内在していた前提が、本ファイル作成時に
     複数職人プランの文脈で改めて言語化されただけと整理できる)。
  3. 按分を行わない方が実装がシンプルであり(`usage_counter`のリセット判定
     (`_current_month_key`との比較)以外にworkshop作成日を考慮する分岐が
     不要になる)、契約初月に上限を減らすことは新規契約者の体験を悪化させる
     (せっかく契約した月にすぐ上限に達しやすくなる)ため事業判断としても
     望ましくない。
- 「未検証・残課題」1点目(`user_profile.workshop_id`未設定のエッジケース)は
  フェーズ29(prototype/usage_counter_workshop.py)で`WorkshopNotLinkedError`
  として既に実装・テスト済み(test_workshop_not_linked_raises等)であり、本フェーズ
  時点で解消済みと確認した。

## 未検証・残課題

- 生成リクエスト処理・按分不要の結論(本フェーズ4節)自体は机上確認であり、
  実際にStripe初回請求と`usage_counter`双方の日付が想定通りに独立して動作するかは
  実接続後(オーナー承認待ちの範囲)の確認が必要。
- 本ファイルで指摘していた2件の残課題はいずれも解消済み。新規の残課題は
  現時点で無し(次の技術的課題は他ventureの残課題一覧・README.mdを参照)。

最終更新: 2026-09-07 16:02 UTC
