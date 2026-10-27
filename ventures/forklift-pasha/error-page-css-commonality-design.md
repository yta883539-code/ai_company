# チェックアウトエラーページのCSS共通化方針(フェーズ195)

checkout-runtime-dependency-failure-applicant-message-design.md 4節「残課題」の
「HTMLの見た目(CSS)をweb-form-mockup配下の既存ページ(plan-selection.html等)と
どこまで共通化するか」に対応し、本ファイルで方針を確定する。

## 1. 前提: 本venture既存ページは「共有CSSファイルを持たない」設計

web-form-mockup配下の既存5ページ(index.html・daily.html・monthly.html・
annual.html・plan-selection.html・settings.html)は、いずれも外部スタイルシート
(`<link rel="stylesheet">`)を持たず、`<head>`内の`<style>`ブロックに同一の
CSSカスタムプロパティ(`:root`トークン: `--color-bg`・`--color-fg`・
`--color-accent`・`--color-accent-dark`・`--color-card`・`--color-border`・
`--color-muted`)とページ固有のスタイル規則を1ファイルにまとめてインライン記述する
方針を一貫して踏襲している(フェーズ138コメント「リポジトリ内の静的ファイル
〈ローカルの実装ドラフト〉に留める」の通り、ビルド工程・外部アセット配信を
一切持たない単一HTMLファイルでの閲覧を前提とするため)。これは「共通化していない」
のではなく、本venture現段階(実デプロイ・CDN配信前のMVP設計検討ドラフト段階)に
おいて意図的に選んだ設計である。

## 2. 方針: 外部共有CSSファイルへの切り出しは行わず、トークンの値のみ共通化する

上記前提を踏まえ、申込者向けエラーページ(`APPLICANT_FACING_ERROR_HTML`)についても
新規の外部CSSファイル(`shared.css`等)を切り出す対応は**行わない**。理由は以下の
3点。

- 現時点で複数ページ間の見た目の同期を保証する実行環境(ビルドツール・CDN等)が
  存在せず、外部CSSファイルを導入しても「2つの独立したファイル(HTML側とCSS側)の
  内容が将来ずれていないことをどう保証するか」という新たな課題を生むだけで、
  1ファイル完結という既存ページの利点(他ventureからのコピー・単体プレビューの
  容易さ)を損なう。
- `APPLICANT_FACING_ERROR_HTML`は`checkout_session.main(request)`内のPython文字列
  定数として実コード化される前提(design文書4節)であり、他ページのような
  「開発者がブラウザで直接開いて閲覧するスタンドアロンhtmlファイル」ではない。
  外部CSSファイルへの依存を持たせると、実コード化時にそのCSSファイルの配信経路
  (静的ファイルサーバー設定等、本venture未設計の領域)まで同時に設計する必要が
  生じ、スコープが本来のエラーハンドリング設計から逸脱する。
- 既存5ページも、ページをまたいだスタイルの完全な同期は保証しておらず(例:
  `settings.html`固有の`.danger-zone`相当のルールは他ページに存在しない)、
  本venture内の実態は「`:root`トークンの値のみを共通化し、個々のスタイル規則は
  各ページが必要な分だけ重複定義する」という緩やかな一貫性である。エラーページも
  この実態に合わせる方が、既存の設計慣習との整合性が高い。

したがって本ventureでの結論は、**`:root`トークンの値(7変数)をそのままエラー
ページの`<style>`ブロック先頭にコピーして使用し、スタイル規則自体は申込者向け
エラーページが必要とする最小限(見出し・本文・問い合わせ先・戻るリンクのみ)に
留める**とする。外部CSSファイルの新設は行わない。

## 3. モックアップドラフト

既存ページと同じ「開発者がブラウザで直接開いて確認できる静的HTMLドラフト」を
`web-form-mockup/checkout-error.html`として新規作成し、3節のテキスト案
(checkout-runtime-dependency-failure-applicant-message-design.md 3節)を
`:root`トークンに沿ったレイアウトで表示した。既存ページとの差分は以下の2点のみ。

- `.draft-banner`の文言を本ページ固有の位置づけ(フェーズ195・503エラー画面の
  ドラフトである旨)に変更した。
- ボタン(`.apply-btn`)は使用せず、代わりに`plan-selection.html`へ戻るための
  プレーンな`<a href="plan-selection.html">`リンクを設けた(他ページの
  `disabled`ボタンと異なり、エラー画面は「操作が無効化されている」のではなく
  「申込者自身の操作でやり直せる」ことを示す必要があるため、リンクを有効な
  ままにした)。

## 4. 残課題

- `APPLICANT_FACING_ERROR_HTML`定数としての実コード化時、本ファイルの
  `checkout-error.html`の`<style>`ブロック・本文テキストをそのままPython文字列
  リテラルへ移植する(実Firestore導入とセットの結合実装フェーズに持ち越し、
  checkout-runtime-dependency-failure-applicant-message-design.md 4節と同様)。
- 問い合わせ先(`OWNER_SUPPORT_CONTACT_PLACEHOLDER`)は未確定のままプレース
  ホルダー表示とした(他venture設計文書と同様、実デプロイ確定後にオーナーが
  設定)。
- 本venture以外(aircon-pasha・course-set-pasha・event-komiguai-pasha・
  kura-pasha・line-reservation-ai)が同種のFirestoreランタイム依存構築失敗時の
  申込者向けエラー画面を今後設計する際、本ファイルの2節(外部CSSファイルを
  切り出さず`:root`トークンの値のみ共通化する方針)が横展開候補になりうるが、
  各venture側の判断(自ventureのWebフォーム実装状況・CSS方針)に委ねるため、
  本ファイルから他venture側への直接書き込みは行わない。

最終更新: 2026-10-27(フェーズ195: checkout-runtime-dependency-failure-
applicant-message-design.md 4節の残課題「HTMLのCSS共通化方針」に対応。外部共有
CSSファイルの新設は行わず、`:root`トークンの値のみを既存ページと共通化する方針を
確定し、web-form-mockup/checkout-error.htmlとしてモックアップドラフトを新規作成した)
