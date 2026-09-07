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

## 未検証・残課題

- 生成リクエスト処理のプロトタイプコード(course-set-pasha/prototype相当)は
  本venture未着手であり、上記2節の手順は机上設計にとどまる。実装時に
  `user_profile.workshop_id`が未設定(workshop未作成)のエッジケースの扱いを
  別途検討する必要がある。
- 複数職人プランの請求サイクル境界とworkshop作成タイミングがずれるケース
  (月の途中でworkshopが新規作成された場合の当月上限の按分要否)は未検討。

最終更新: 2026-09-07 09:59 UTC
