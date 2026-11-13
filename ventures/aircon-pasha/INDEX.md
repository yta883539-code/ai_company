# ドキュメント索引(フェーズ時点のスナップショット)

本venture配下のMarkdown設計文書が100件超に達し、ファイル名だけでは全体像を
把握しにくくなったため、kura-pasha・course-set-pasha・forklift-pasha・
line-reservation-aiと同様にテーマ別の索引を作成した。新しいトピックに着手する前に、
まず本ファイルで既存文書の有無を確認し、重複する設計の再生産を避けること。個々の文書の
最新状況は各ファイル自身とREADME.mdのフェーズログを参照する(本索引はファイル一覧の
整理のみを目的とし、内容の要約・ステータス追跡は行わない)。

## 事業・市場・コスト試算
- market-research.md / tech-stack.md / pricing-plan.md / unit-economics-estimate.md
- support-cost-estimate.md / support-cost-selfservice-reduction.md
- llm-api-cost-estimate.md / subscription-billing-cost-estimate.md
- content-generation-time-estimate.md / line-price-revision-2026-check.md
- billing-budget-cap-safeguard-design.md

## 顧客ヒアリング・LP・公開準備・法務
- customer-interview-design.md / interview-candidate-selection-criteria.md
- interview-rehearsal-script.md / candidate-longlist-draft.md / candidate-readiness-summary.md
- initial-contact-message-draft.md / landing-page-copy-draft.md / landing-page-wireframe.md
- launch-readiness-checklist.md / legal-notices-draft.md / data-retention-policy.md
- deployment-runbook.md / ci-setup.md / vendor-breach-key-rotation-runbook.md
- sns-blog-example-observation.md / onboarding-guide.md / mvp-flow-draft.md
- output-samples-validation.md

## チャットボット・会話フロー・LLM
- chatbot-first-response-feasibility.md
- chatbot-intent-classification-escalation-design.md
- chatbot-intent-classification-followup-design.md
- chatbot-intent-classification-llm-prompt-draft.md
- llm-system-prompt-draft.md / llm-quality-verification-plan.md
- llm-quality-verification-results-template.md
- character-limit-fallback-design.md / tone-and-manner-guideline.md
- checkout-intent-6b-iii-chitchat-status-mapping-review.md
- subscription-intent-6a-iii-chitchat-status-mapping-review.md
- first-generation-self-check-design.md / prompt-caching-design.md

## 申請フォーム・連携・共有利用
- application-form-submission-http-entry-point-design.md
- firestore-runtime-dependency-failure-form-submission-response-design.md
- gas-script-draft.md / linking-code-delivery-method-decision.md
- user-account-linking-design.md / relinking-subscription-canceled-crosscheck.md
- multi-technician-shared-usage-design.md
- third-party-personal-info-inclusion-handling-design.md
- increment-and-mark-notice-horizontal-survey.md

## 課金・Stripe・サブスクリプション
- checkout-initiation-flow-design.md / checkout-session-plan-selection-design.md
- checkout-session-completed-event-order-guard-design.md
- checkout-session-completed-handling-design.md
- stripe-cancellation-deletion-candidate-trigger-design.md
- stripe-event-idempotency-design.md / stripe-webhook-event-dispatch-design.md
- stripe-webhook-http-entry-point-design.md
- stripe-webhook-runtime-dependency-failure-response-design.md
- stripe-webhook-signature-verification-design.md / webhook-http-entry-point-design.md
- subscription-canceled-immediate-block-design.md / subscription-cancellation-flow-design.md
- subscription-cancellation-notification-design.md
- subscription-cancellation-scheduled-message-suspension-consistency-design.md
- subscription-event-out-of-order-guard-design.md / subscription-updated-event-order-guard-design.md
- portal-session-provider-design.md
- trial-end-condition-a-cta-design.md / trial-end-notification-design.md
- trial-end-scheduler-design.md / trial-start-anchor-decision.md
- payment-failure-dunning-design.md / payment-failure-event-order-guard-design.md
- payment-failure-reminder-scheduler-design.md
- payment-failure-state-clear-on-subscription-deleted-design.md
- payment-suspension-owner-notification-design.md
- blocked-but-billing-detection-design.md / blocked-but-billing-owner-notification-design.md
- unfollow-billing-faq.md

## Firestore・インフラ・監視
- firestore-provider-adapter-design.md / firestore-security-rules-draft.md
- firestore-security-rules-emulator-verification.md / firestore-composite-index-plan.md
- full-scan-to-indexed-query-threshold-decision.md
- runtime-dependency-switching-design.md / cloud-monitoring-alert-policy-design.md
- api-call-failure-handling.md

## 退会・解約・削除候補処理
- daily-checks-and-deletion-candidate-final-confirmation-dependency-failure-response-design.md
- deletion-candidate-final-confirmation-scheduler-design.md
- deletion-candidate-query-consolidation-decision.md
- deletion-candidate-unreachable-owner-review-design.md
- follow-unfollow-event-handling-design.md
- restricted-mode-cancellation-message-copy-review.md

## 通知・レポート・FAQ
- limit-approaching-notification-design.md / business-name-owner-notification-display-design.md
- btob-management-company-report-variant-design.md
- owner-faq-routing-design.md / owner-operation-self-service-faq.md

## 横断レビュー・陳腐化棚卸し
- stale-next-candidate-cross-venture-survey.md
- requester-own-personal-info-management-company-disclosure-review.md

## 実装・テスト
- prototype/ / schema/
