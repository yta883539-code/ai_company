# ドキュメント索引(フェーズ時点のスナップショット)

本venture配下のMarkdown設計文書が45件に達し、ファイル名だけでは全体像を
把握しにくくなったため、kura-pasha・course-set-pasha・forklift-pasha・
line-reservation-ai・aircon-pashaと同様にテーマ別の索引を作成した。新しい
トピックに着手する前に、まず本ファイルで既存文書の有無を確認し、重複する設計の
再生産を避けること。個々の文書の最新状況は各ファイル自身とREADME.mdのフェーズ
ログを参照する(本索引はファイル一覧の整理のみを目的とし、内容の要約・ステータス
追跡は行わない)。

## 事業・市場・コスト試算
- market-research.md / tech-stack.md / pricing-plan.md

## 顧客ヒアリング・LP・公開準備・法務
- landing-page-copy-draft.md / landing-page-wireframe.md / landing-page/
- legal-notices-draft.md / data-retention-policy.md
- ci-setup.md / vendor-breach-key-rotation-runbook.md / tone-and-manner-guideline.md

## LLM・生成フロー
- llm-system-prompt-draft.md / llm-quality-verification-plan.md
- input-output-sample-mapping.md / generation-count-design.md
- result-display-page-generation-request-design.md / input-form-ui-ux-design.md

## 会場(venue)マスタ・名寄せ・ゴロ合わせ入力
- venue-master-data-structure-design.md / venue-master-draft.md
- venue-match-confidence-and-staleness-design.md
- venue-matcher-llm-postprocessing-integration-design.md
- venue-name-normalization-design.md / venue-operational-status-output-reflection-design.md
- venue-alias-input-text-logging-design.md / venue-alias-verification-and-naming-rights-risk.md
- multi-venue-hashigo-schema-design.md / goods-line-participation-input-field-design.md

## 課金・プラン(都度/月額/推し活パス)
- checkout-result-http-entry-point-design.md / stripe-webhook-entry-point-design.md
- checkout-result-combined-migration-decision.md
- payment-method-design.md / plan-change-billing-design.md
- monthly-pass-identity-design.md / monthly-pass-trial-decision.md
- monthly-pass-user-identification-design.md / one-time-plan-access-token-design.md
- fan-pass-store-protocol-design.md / fan-pass-canceled-access-block-design.md
- subscription-updated-event-order-guard-preemptive-note.md
- subscription-updated-past-due-grace-period-reconsideration.md
- usage-counter-store-protocol-design.md

## アクセストークン・再送・通知
- access-token-client-storage-design.md / access-url-resend-api-design.md
- access-url-resend-http-entry-point-design.md / email-lookup-necessity-review.md

## Firestore・インフラ・監視
- firestore-data-model.md / firestore-security-rules-draft.md
- cloud-monitoring-alert-policy-design.md

## 実装・テスト
- prototype/ (run_all_tests.py含む) / schema/
