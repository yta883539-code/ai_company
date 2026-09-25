# Cloud Functions採用世代の確定(1st gen / 2nd gen)

cloud-monitoring-alert-policy-design.md 4節「スコープ外」に残っていた「Cloud Functions
採用世代(1st gen / 2nd gen)確定後にresource.typeを要調整」という保留事項について、
WebSearchでGoogle Cloudの最新の提供状況を確認し、方針を確定する。

## 1. 調査結果

- Google Cloudは2025年時点で、新規プロジェクトからのCloud Functions (1st gen) 新規作成を
  停止済み(既存の1st gen関数は引き続きサポートされるが、新規作成は不可)。
- 製品名自体も「Cloud Functions」から「Cloud Run functions」に改称されており、
  1st genは「Cloud Run functions (1st gen)」、2nd genは単に「Cloud Run functions」と
  呼ばれる。
- Googleは新規関数について2nd gen(Cloud Run functions)の採用を推奨している。
- 出典: nOps「Cloud Run Functions Pricing」、Google Cloud公式ドキュメント
  (Cloud Run functions release notes / version comparison / runtime support)。

## 2. 決定

本venture(および同じくGCP Cloud Functionsをホスティング候補としているaircon-pasha・
kura-pasha・line-reservation-ai)は、tech-stack.md・hosting-platform-selection.md
いずれの時点でもGCPプロジェクトを未作成(オーナー承認待ち)であるため、実際に
プロジェクトを作成する時点では1st genの新規作成自体が選べない。したがって

**採用世代は2nd gen(Cloud Run functions)に確定する。**

これは新規調査に基づく確定であり、追加の検証や承認を要する変更ではない
(1st genが選択肢として存在しないため、実質的に選択の余地がない)。

## 3. 影響範囲への反映

- `resource.type`は`cloud_run_revision`を採用する(cloud-monitoring-alert-policy-design.md
  2節のログフィルタから「要確認事項」を解消)。
- ラベル`service_name`・`revision_name`等、Cloud Run functions特有のリソースラベルが
  ログフィルタに追加で必要になる可能性があるが、具体的なラベル値はGCPプロジェクト作成後
  (関数デプロイ後)でなければ確定できないため、この点のみ引き続き実プロジェクト作成後の
  確認事項として残す。
- aircon-pasha・kura-pasha側の同種design docにも同じ決定を反映する(本フェーズで対応済み、
  各venture側README参照)。
- line-reservation-aiはCloud Monitoringアラート設計自体が未着手(意図分類のLLM呼び出しを
  持たないため対象ログが存在しない、フェーズ247確認済み)だが、tech-stack.md・
  hosting-platform-selection.mdのホスティング候補記載に本決定を将来反映する余地がある
  (次回候補)。

## 4. 残る保留事項

- 実際のCloud Run functionsデプロイ・ログベース指標・アラートポリシーの作成は、
  GCPプロジェクト作成(既存のオーナー承認待ち事項)後にオーナー承認の範囲内で実施する。
