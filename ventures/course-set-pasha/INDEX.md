# course-set-pasha ドキュメント索引

配下のMarkdown設計文書が増加し、新規着手前の重複確認コストが増大していたため、
テーマ別に索引化した(kura-pasha・line-reservation-aiのINDEX.mdと同種の整理、
pending-approval.md 2026-11-08 08:00 UTC記載の「整理(重複排除・要約インデックス化)」
提案への対応の一環)。内容の要約・ステータス追跡は行わず一覧整理のみ。

## 事業・市場
- market-research.md / pricing-plan.md / unit-economics-estimate.md
- customer-interview-design.md / interview-candidate-selection-criteria.md
- interview-rehearsal-script.md / interview-request-package.md / candidate-longlist-draft.md
- llm-api-cost-estimate.md / subscription-billing-cost-estimate.md
- support-cost-estimate.md / support-cost-selfservice-reduction.md
- payment-processor-metered-billing-usage-research.md
- sns-post-example-observation.md / sns-tone-research.md
- overage-price-value-validation.md / notification-threshold-per-plan-review.md
- multi-area-mixed-case-review.md / multi-setter-shared-usage-design.md

## LLM・チャットボット・生成品質
- mvp-flow-draft.md / llm-system-prompt-draft.md
- llm-quality-verification-plan.md / llm-quality-verification-results-template.md
- chatbot-first-response-feasibility.md
- chatbot-intent-classification-escalation-design.md
- chatbot-intent-classification-llm-prompt-draft.md
- chatbot-intent-router-webhook-wiring-design.md
- checkout-intent-iii-chitchat-status-mapping-review.md
- subscription-intent-iii-chitchat-status-mapping-review.md
- intent-classification-failure-observability-design.md
- character-limit-fallback-design.md / prompt-caching-design.md
- content-generation-time-estimate.md / first-generation-notice-implementation-design.md
- text-image-bundling-design.md / history-export-usage-guide.md
- apology-tone-horizontal-check-result.md / header-summary-edge-case-review.md
- removal-only-notice-edge-case-review.md / count-null-vs-zero-cross-venture-review.md
- post-generation-checks-cross-area-review.md / schema-structured-output-compat-check.md
- output-samples-validation.md

## 課金・Stripe・サブスク状態管理
- checkout-initiation-flow-design.md / checkout-session-cloud-function-entry-point-design.md
- checkout-session-completed-event-order-guard-design.md / checkout-session-endpoint-design.md
- checkout-session-plan-selection-design.md / customer-portal-session-endpoint-design.md
- stripe-cancellation-deletion-candidate-trigger-design.md / stripe-customer-id-linking-design.md
- stripe-event-id-store-firestore-adapter-design.md / stripe-event-idempotency-design.md
- stripe-liff-integration-sequence-design.md / stripe-webhook-cloud-function-entry-point-design.md
- stripe-webhook-event-dispatch-design.md / stripe-webhook-http-entry-point-design.md
- stripe-webhook-signature-verification-design.md
- subscription-canceled-immediate-block-design.md / subscription-cancellation-flow-design.md
- subscription-cancellation-scheduled-message-suspension-consistency-design.md
- subscription-cancellation-scheduled-notification-design.md / subscription-cancelled-notification-design.md
- subscription-event-out-of-order-guard-design.md / subscription-plan-change-design.md
- subscription-updated-event-order-guard-design.md
- payment-failure-dunning-design.md / payment-failure-event-order-guard-design.md
- payment-failure-reminder-scheduler-design.md / payment-failure-state-clear-on-subscription-deleted-design.md
- payment-suspension-owner-notification-design.md
- blocked-but-billing-detection-design.md / blocked-but-billing-owner-notification-design.md
- blocked-but-billing-owner-notification-stale-event-guard-fix.md
- deletion-candidate-query-consolidation-decision.md / deletion-candidate-stale-event-guard-design.md
- trial-end-condition-a-implementation-design.md / trial-end-notification-design.md
- trial-end-scheduler-design.md / trial-start-anchor-decision.md / unfollow-billing-faq.md

## LINE連携・申込フォーム
- application-form-submission-flow-design.md / application-form-submission-http-entry-point-design.md
- line-user-id-linking-design.md / line-image-content-api-review.md / line-price-revision-2026-check.md
- liff-plan-selection-ui-wireframe.md / follow-event-welcome-message-design.md
- unfollow-event-handling-design.md / gas-script-draft.md / contact-email-field-design.md
- webhook-event-dispatch-design.md / webhook-processing-flow-design.md
- receive-webhook-http-entry-point-design.md / onboarding-settings-and-self-check-design.md
- limit-approaching-notification-design.md / linking-code-purge-trigger-design.md
- line-webhook-event-id-idempotency-design.md
- webhook-sync-reply-timeout-root-cause-review.md
- process-memo-event-async-split-design.md
- enqueue-failure-partial-processing-safety-design.md
- enqueue-fallback-owner-notification-design.md

## インフラ・運用
- tech-stack.md / firebase.json / firestore.rules / firestore.indexes.json
- firestore-security-rules-draft.md / firestore-security-rules-emulator-verification.md
- firestore-composite-index-plan.md / firestore-provider-adapter-design.md
- firestore-runtime-dependency-failure-form-submission-response-design.md
- runtime-dependency-switching-design.md / api-call-failure-handling.md
- cloud-functions-generation-decision.md / cloud-monitoring-alert-policy-design.md
- data-retention-policy.md / vendor-breach-key-rotation-runbook.md
- deployment-runbook.md / launch-readiness-checklist.md / ci-setup.md
- schema/ (output.schema.json, validate_test_cases.py) / prototype/ (InMemoryスタブ実装・テスト)
- emulator-test/

## 顧客向け文面・法務
- landing-page/ / landing-page-copy-draft.md / landing-page-wireframe.md
- initial-contact-message-draft.md / onboarding-guide.md
- owner-faq-routing-design.md / owner-operation-self-service-faq.md
- tone-and-manner-guideline.md / legal-notices-draft.md
- restricted-mode-cancellation-message-copy-review.md
- third-party-personal-info-inclusion-handling-design.md

## 既知の運営課題
- 実GCPプロジェクト・Firestore・Stripeアカウント・LINE公式アカウントの作成が未承認で
  止まっており(pending-approval.md 2026-09-27 03:00 UTC・2026-09-27 07:00 UTC・
  2026-09-28 20:00 UTC・2026-10-24 09:00 UTC記載、2026-11-08 08:00 UTCの運営方針確認
  依頼を参照)、設計・InMemoryスタブ実装の蓄積が実サービス稼働に直結していない状態が
  続いている。
