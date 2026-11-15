# 「契約業者数に応じたBilling Budget予算見直し」運用手順の他venture横展開状況(フェーズ388)

## 背景
フェーズ387で、billing-budget-cap-safeguard-design.md(4節)が次回候補のまま未反映だった
「契約業者数が想定上限の8割に達した時点で予算額見直しをオーナーに提案する」運用手順を、
本venture(aircon-pasha)のlaunch-readiness-checklist.mdに反映した。フェーズ387の次回候補(1)
「他4venture(course-set-pasha・forklift-pasha・kura-pasha・oshien-pasha)へのBilling Budget
安全策設計そのものの横展開」に対応するため、本フェーズで他4ventureの状況を確認した。

## 確認結果
他4venture全てに`billing-budget-cap-safeguard-design.md`自体は既に存在しており(各venture側
フェーズで横展開済み)、安全策設計そのものの横展開は完了済みであることを確認した(フェーズ387
次回候補(1)の文面は陳腐化していた)。一方、本venture同様に「想定件数が一定数を超えた場合に
予算見直しをオーナーに提案する」運用手順を各venture自身のlaunch-readiness-checklist.mdに
反映している venture は1件もなかった(4venture全ての`launch-readiness-checklist.md`を
grepし、「予算見直し」「Billing Budget」を含む運用手順節が存在しないことを確認)。

各ventureのbilling-budget-cap-safeguard-design.mdに記載済みの見直しトリガー条件を確認すると、
具体的な数値閾値が既に設計されているものと、未確定のものに分かれる。

| venture | 見直しトリガー(設計済みの記載) | 運用手順への反映可否 |
|---|---|---|
| course-set-pasha | セッター複数プランの上限(267.3円/オーナー)を使い切るオーナーが2件を超える規模 | 反映可能(数値閾値あり) |
| kura-pasha | 複数職人プランの上限(101.8円/工房)を使い切る工房が5件を超える規模 | 反映可能(数値閾値あり) |
| forklift-pasha | 「実際の契約件数がこれを超える見込みとなった場合」(複数台プラン顧客5件分の原価見積り約2,992円が暫定予算3,000円の算出根拠だが、見直しトリガーとしての明示的な件数閾値は未確定) | 反映にはトリガー件数の確定が先に必要 |
| oshien-pasha | 原価試算文書(unit-economics-estimate.md相当)自体が未作成のため、500円という閾値が十分かどうかの検証自体が未着手 | 反映には原価試算文書の作成が先に必要 |

## 今回の対応範囲
各venture自身のlaunch-readiness-checklist.mdへの追記は、各venture側の設計ドキュメントと
整合させながら行う必要があり、かつ本リポジトリの運用慣習(各venture内の変更は原則そのventure
自身の実行回で行う)に沿うため、本フェーズでは他venture側ファイルの変更は行わない。代わりに、
上記の確認結果を本ドキュメントとして記録し、course-set-pasha・kura-pashaの次回実行回での
反映候補として引き渡す。

## 次回候補
- course-set-pasha・kura-pashaはいずれも数値閾値が設計済みのため、各venture自身の次回実行回で
  本venture(aircon-pasha)フェーズ387の運用手順節(launch-readiness-checklist.md)と同形式で
  反映することを推奨する。
- forklift-pashaは見直しトリガーの数値閾値確定、oshien-pashaは原価試算文書の作成が、運用手順
  反映の前提として先に必要。
- 2026-11-08 08:00 UTC記載の運営方針判断が引き続き未回答のまま7venture共通の最大のボトル
  ネックとして残っている(pending-approval.md参照)ため、オーナーから得られた場合はその着手を
  最優先とする。

最終更新: 2026-11-15 21:00 UTC(フェーズ388: 新規作成。他venture側ファイルの変更は行っていない。
実GCP/Stripe接続・支払い・アカウント作成・外部公開・送信は一切行っていない。)
