# 独自ドメイン運用かCloud RunデフォルトURLのままとするかの検討(フェーズ50)

tech-stack.md(フェーズ7)「未検証・残課題」、web-form-hosting-selection.md(フェーズ49)4節
「未検証・残課題」2点目で「実際のサービス公開時に再検討する」として持ち越されていた論点に
ついて、実際のGCPプロジェクト作成・サービス公開自体はオーナー承認待ち(pending-approval.md
参照)のままだが、公開時の判断基準・暫定方針を先行して整理する(机上整理のみ、実際のドメイン
取得・DNS設定は発生しない)。

## 1. 前提の整理

- web-form-hosting-selection.md(フェーズ49)で、フォーム配信・送信処理はCloud Run(2nd gen)
  の同一サービスに統合する方式を確定済み。URLは `https://<サービス名>-<ハッシュ>.<リージョン>.
  run.app` 形式のデフォルトURLか、独自ドメイン(例: `toriketsu-pasha.com`等、未取得)のいずれかを
  入力ページ・結果ページで使用することになる。
- one-time-checkout-no-account-design.md(フェーズ10)で、Stripe Checkout one-time payment
  modeのsuccess_url/cancel_urlに結果ページURL(`draft_id`を含む)を設定する設計のため、ドメイン
  選択はStripe側の設定にも影響する。
- 本venture固有の制約(tech-stack.mdフェーズ7)として、低頻度利用(主催者あたり月数件程度)に
  対して運用コスト・保有キー数を増やさない方針が一貫している。

## 2. 独自ドメイン採用案の評価

メリット: (1)主催者向けの告知・問い合わせフォーム案内文(initial-contact-message-draft.md等)
にサービス名を冠したURLを記載でき信頼性・覚えやすさが向上する、(2)将来的にサービス名を
変更せず基盤(Cloud Run/他クラウド)を移行する場合もURLを維持できる。

デメリット: (1)ドメイン取得(年間登録料)・DNS設定・Cloud Run側へのカスタムドメインマッピング
(Google提供の管理用SSL証明書発行を含む)という新たな初期作業・年次コストが生じる、(2)
vendor-breach-key-rotation-runbook.md(フェーズ48)が明記した本venture保有キー3種(Stripe・
LLM API・GCPサービスアカウント鍵)に、ドメインレジストラの管理アカウント認証情報が新たな
依存先として加わり、侵害時のローテーション対象が増える、(3)月数件程度の低頻度利用では
ドメイン費用が1件あたりのコスト(llm-api-cost-estimate.md参照)に対し相対的に重くなる。

## 3. デフォルトURL(`*.run.app`)案の評価

メリット: (1)追加費用・DNS設定・証明書管理が一切不要でtech-stack.mdフェーズ7の低コスト
運営方針に最も合致する、(2)vendor-breach-key-rotation-runbook.mdの保有キー一覧に変更が
生じない。

デメリット: (1)URLが長く主催者向け告知文に記載した際の印象・信頼性が独自ドメインに比べて
弱い、(2)基盤を将来移行する場合はURLが変わり、既に配布済みの告知文・問い合わせ導線の
修正が必要になる。

## 4. 暫定方針

本venture初回ローンチ時点では**Cloud RunデフォルトURL(`*.run.app`)を採用し、独自ドメインは
取得しない**方針を暫定決定する。理由は、tech-stack.mdフェーズ7が一貫して採る「低頻度利用に
対して運用コスト・保有キー数を増やさない」方針と、現時点で利用実績がなく独自ドメインの
信頼性向上効果を売上に結びつけられる見込みが未検証であることの2点による。独自ドメインの
再検討は、(a)実際の利用件数・売上が一定規模に達した場合、または(b)candidate-longlist-draft.md
記載の候補(奈良NEVER LAND等)へのヒアリング実施(オーナー承認後)で「URLの印象が導入障壁に
なっている」との声が確認された場合、のいずれかを契機とする。

## 5. 他設計文書への影響確認

- vendor-breach-key-rotation-runbook.md(フェーズ48)の保有キー一覧(Stripe・LLM API・GCP
  サービスアカウント鍵)に変更はない(ドメインレジストラの依存先が加わるのは独自ドメイン
  採用後のみ)。
- one-time-checkout-no-account-design.md(フェーズ10)のStripe success_url/cancel_url設計、
  result-page-ttl-access-design.md(フェーズ14)の結果ページURL設計は、いずれもURLのホスト名
  (デフォルトURL/独自ドメイン)に依存しない設計のため、本決定による変更は不要。

## 6. 未検証・残課題

- 独自ドメイン再検討の具体的なトリガー基準(4節(a)の「一定規模」の定量化)は、実際の利用件数
  データが蓄積された段階で検討する。
- 実際のGCPプロジェクト作成・Cloud Runサービスのデプロイ・デフォルトURLの確認自体は、他venture
  と同様にオーナー承認待ちの範囲(pending-approval.md参照)。

最終更新: 2026-10-25 00:00 UTC(フェーズ50: 独自ドメイン運用かCloud RunデフォルトURLのままと
するかを検討し、初回ローンチ時点はデフォルトURL採用を暫定決定。独自ドメイン再検討のトリガー
条件を整理し、vendor-breach-key-rotation-runbook.md等の既存設計への影響がないことを確認した)
