# ドキュメント索引(フェーズ時点のスナップショット)

本venture配下のMarkdown設計文書が90件超に達し、新規ファイル名だけでは全体像を
把握しにくくなったため、テーマ別に索引を作成した。新しいトピックに着手する前に、
まず本ファイルで既存文書の有無を確認し、重複する設計の再生産を避けること。
個々の文書の最新状況は各ファイル自身とREADME.mdのフェーズログを参照する
(本索引はファイル一覧の整理のみを目的とし、内容の要約・ステータス追跡は行わない)。

## 事業・市場
- market-research.md / mvp-flow-draft.md / pricing-plan.md
- unit-economics-estimate.md / support-cost-estimate.md / support-cost-selfservice-reduction.md
- cross-venture-support-cost-comparison.md / cross-venture-support-selfservice-reduction-comparison.md
- cross-venture-discover-compatibility-review.md
- candidate-longlist-draft.md / candidate-readiness-summary.md
- interview-candidate-selection-criteria.md / interview-rehearsal-script.md / customer-interview-design.md

## LLM・チャットボット
- llm-system-prompt-draft.md / llm-api-cost-estimate.md / prompt-caching-design.md
- llm-quality-verification-plan.md / llm-quality-verification-results-template.md
- output-samples-validation.md / content-generation-time-estimate.md
- chatbot-first-response-feasibility.md / chatbot-intent-classification-design.md
- chatbot-intent-classification-llm-prompt-draft.md / chatbot-intent-classification-wiring-design.md
- intent-classification-failure-observability-design.md / message-context-selection-design.md
- character-limit-fallback-design.md / first-generation-self-check-notification-design.md

## 課金・Stripe
- checkout-initiation-flow-design.md / stripe-webhook-checkout-completed-design.md
- stripe-webhook-tolerance-seconds-cross-venture-survey.md
- stripe-event-idempotency-design.md / stripe-event-id-store-firestore-adapter-design.md
- checkout-session-completed-plan-event-order-guard-design.md
- subscription-billing-data-model-design.md / subscription-plan-sync-design.md
- subscription-status-event-order-guard-design.md / subscription-updated-event-order-guard-design.md
- subscription-canceled-webhook-design.md / subscription-canceled-immediate-block-design.md
- subscription-cancellation-flow-design.md / subscription-cancellation-notification-design.md
- subscription-cancellation-scheduled-notification-design.md
- payment-failure-dunning-design.md / payment-failure-reminder-scheduler-design.md
- payment-failure-state-clear-on-subscription-deleted-design.md
- payment-suspension-owner-notification-design.md
- blocked-but-billing-detection-design.md / blocked-but-billing-owner-notification-design.md
- downgrade-excess-member-handling-design.md / member-retention-notice-design.md
- trial-end-condition-design.md / trial-end-notification-design.md
- portal-session-provider-design.md / unfollow-billing-faq.md / line-price-revision-2026-check.md

## LINE連携・会員/職人まわり
- craftsman-account-linking-design.md / linking-code-store-firestore-adapter-design.md
- invite-code-store-firestore-adapter-design.md
- line-webhook-event-id-idempotency-design.md / line-webhook-event-id-store-firestore-adapter-design.md
- contractor-transfer-design.md / contractor-transfer-confirmation-detection-design.md
- contractor-transfer-expired-notice-design.md / contractor-transfer-non-contractor-message-design.md
- requester-personal-info-inclusion-handling-design.md
- usage-counter-workshop-key-design.md / firestore-usage-counter-provider-adapter-design.md
- limit-approaching-notification-design.md
- workshop-name-owner-notification-display-design.md / workshop-store-firestore-adapter-design.md
- deletion-candidate-final-confirmation-design.md / deletion-candidate-query-consolidation-decision.md
- deletion-candidate-query-consolidation-horizontal-survey.md
- stripe-cancellation-deletion-candidate-trigger-design.md

## インフラ・運用
- tech-stack.md / firebase.json / firestore.rules / firestore.indexes.json
- firestore-security-rules-draft.md / firestore-security-rules-emulator-verification.md
- firestore-composite-index-plan.md / firestore-provider-adapter-design.md
- runtime-dependency-switching-design.md / daily-scheduler-design.md
- cloud-monitoring-alert-policy-design.md / api-call-failure-handling.md
- data-retention-policy.md / vendor-breach-key-rotation-runbook.md
- deployment-runbook.md / launch-readiness-checklist.md / ci-setup.md
- webhook-sync-reply-timeout-root-cause-review.md(本venture単独の経路構造確認・
  根本対策費用対効果検討、course-set-pashaフェーズ369の個別確認版)
- schema/ (output.schema.json, validate_test_cases.py) / prototype/ (InMemoryスタブ実装・テスト)
- emulator-test/

## 顧客向け文面・法務
- landing-page-wireframe.md / landing-page-copy-draft.md / landing-page/
- initial-contact-message-draft.md / onboarding-guide.md
- owner-faq-routing-design.md / owner-operation-self-service-faq.md
- tone-and-manner-guideline.md / legal-notices-draft.md

## 既知の運営課題
- 実GCPプロジェクト・Firestore・Stripeアカウント・LINE公式アカウントの作成が未承認で
  止まっており(pending-approval.md 2026-08-xx以降の記録、2026-11-08 08:00 UTCの
  運営方針確認依頼を参照)、設計・InMemoryスタブ実装の蓄積が実サービス稼働に
  直結していない状態が続いている。
