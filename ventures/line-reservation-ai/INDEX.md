# ドキュメント索引(フェーズ時点のスナップショット)

本venture配下のMarkdown設計文書が150件超に達し、新規ファイル名だけでは全体像を
把握しにくくなったため、kura-pashaのINDEX.md(フェーズ続き292)と同様にテーマ別の
索引を作成した。新しいトピックに着手する前に、まず本ファイルで既存文書の有無を確認し、
重複する設計の再生産を避けること。個々の文書の最新状況は各ファイル自身とREADME.mdの
フェーズログを参照する(本索引はファイル一覧の整理のみを目的とし、内容の要約・ステータス
追跡は行わない)。

## 事業・市場・コスト試算
- market-research.md / tech-stack.md / hosting-platform-selection.md
- pricing-plan.md / unit-economics-estimate.md
- support-cost-estimate.md / support-cost-selfservice-reduction.md
- llm-api-cost-estimate.md / firestore-traffic-cost-estimate.md
- payment-gateway-fee-estimate.md / subscription-billing-cost-estimate.md
- line-api-pricing.md / line-price-revision-2026-check.md
- cloud-scheduler-invocation-cost-estimate.md
- billing-budget-cap-safeguard-design.md

## 顧客ヒアリング・LP・公開準備・法務
- customer-interview-design.md / interview-candidate-selection-criteria.md
- interview-rehearsal-script.md / interview-request-package.md
- candidate-longlist-draft.md / initial-contact-message-draft.md
- landing-page-copy-draft.md / landing-page-wireframe.md / landing-page/
- launch-announcement-draft-design.md / launch-readiness-checklist.md
- legal-notices-draft.md / data-retention-policy.md
- deployment-runbook.md / ci-setup.md / vendor-breach-key-rotation-runbook.md

## 会話フロー・LLMプロンプト・構造化出力
- conversation-flow.md / conversation-flow-construction-design.md
- conversation-flow-state-machine-design.md / conversation-event-processor-assembly-design.md
- conversation-state-persistence-design.md / conversation-state-wiring-design.md
- conversation-state-cleanup.md / conversation-samples-test-cases.md
- llm-system-prompt-draft.md / llm-turn-context-design.md / llm-quality-verification-plan.md
- json-output-retry-fallback.md / json-schema-multi-intent-extension.md
- intent-to-flow-mapping.md / chatbot-first-response-architecture-comparison.md
- channel-agnostic-session-id.md / character-limit-fallback-design.md
- message-tone-variants.md / tone-and-manner-guideline.md / fixed-vocabulary-tone-check-design.md
- multi-turn-scenario-harness-design.md / candidate-selection-multiturn-crosscheck.md
- candidate-presentation-and-selection-design.md / candidate-selection-details-suspension-recheck-design.md
- prompt-caching-design.md / precheck-strengthening.md / mandatory-two-step-order-enforcement-design.md

## 予約・空き枠検索・二重予約防止
- booking-slot-manager-design.md / booking-record-store-design.md
- booking-conflict-candidate-representation.md / double-booking-prevention.md
- availability-closed-weekday-support.md / ad-hoc-closed-dates-support.md
- business-hours-lunch-break.md / business-hours-raw-to-searcher-assembly-design.md
- weekday-specific-business-hours.md / slot-search-component-design.md
- candidate-buffer-analysis.md / candidate-label-weekday-fix.md
- pending-new-booking-context-ttl-design.md / pending-timeout-ux.md
- new-booking-needs-owner-check-notification-design.md / new-booking-suspension-guard-parity-review.md
- monthly-booking-limit-notification-design.md
- menu-pricing-faq-topic-decision.md / menu-unmentioned-vs-unregistered-design.md
- no-show-handling.md

## キャンセル・変更・確定済み予約の処理
- cancel-intent-handling-design.md / change-intent-handling-design.md
- confirmed-state-archival.md / archive-trigger-unification-design.md
- candidates-expired-notification-design.md / secondary-state-classes-persistence-conclusion.md
- restricted-mode-cancellation-consistency-review.md / subscription-canceled-block-crosscheck.md

## 課金・Stripe
- checkout-initiation-flow-design.md / checkout-intent-detection-parity-review.md
- checkout-session-plan-selection-design.md / checkout-session-completed-event-order-guard-design.md
- stripe-customer-id-reverse-lookup-design.md / stripe-event-idempotency-design.md
- stripe-webhook-event-dispatch-design.md / stripe-webhook-http-entry-point-design.md
- stripe-webhook-signature-verification-design.md
- subscription-cancellation-flow-design.md / subscription-deleted-event-routing-design.md
- subscription-event-order-guard-design.md / subscription-plan-sync-design.md
- subscription-updated-event-order-guard-design.md / customer-subscription-updated-event-routing-design.md
- dunning-state-clear-on-subscription-deleted-design.md
- payment-failure-detected-at-event-order-guard-design.md / payment-failure-dunning-design.md
- billing-upgrade-flow-design.md
- blocked-but-billing-detection-design.md / blocked-but-billing-owner-email-notification-design.md
- trial-end-scheduler-design.md / trial-to-paid-billing-flow-consistency-check.md / trial-start-anchor-decision.md
- portal-session-provider-design.md / unfollow-billing-faq.md / follow-unfollow-event-handling-design.md

## Firestore・データモデル・インフラ基盤
- firestore-data-model.md / firestore-provider-adapter-design.md
- firestore-security-rules-draft.md / firestore-security-rules-emulator-verification.md
- firestore-transaction-design.md / firestore-composite-index-plan.md
- firestore.indexes.json / firestore.rules / firebase.json
- store-profile-store-firestore-adapter-design.md
- store-profile-store-firestore-adapter-design-onboarding-flag.md
- processor-cache-persistence-design.md / runtime-dependency-switching-design.md
- idle-conversation-trigger-design.md / store-id-resolution-and-owner-identity-design.md

## 店舗・オーナー設定・オンボーディング
- store-settings-save-flow-design.md / owner-settings-wireframe.md
- owner-faq-routing-design.md / owner-operation-self-service-faq.md / owner-notification-channel-design.md
- store-deletion-candidate-final-confirmation-design.md
- store-deletion-candidate-unreachable-owner-review-design.md
- store-deletion-confirmation-unreachable-clear-wiring-design.md / store-deletion-execution-design.md
- onboarding-completion-message-design.md / onboarding-guide.md
- line-account-connection-stepguide.md / line-account-connection-video-script.md

## 通知・リマインド・エスカレーション・FAQ
- reminder-scheduler-design.md / reminder-timing-and-resend-rules.md
- reminder-scheduler-composite-index-design.md / reminder-scheduler-suspension-independence-review.md
- reminder-blocked-delivery-owner-signal-design.md
- escalation-consolidation-logic.md / escalation-digest-flush-trigger-design.md / escalation-notification-templates.md
- faq-escalation-boundary.md / faq-escalation-customer-reply-implementation.md / faq-response-templates.md
- hours-other-faq-topic-resolution.md / single-item-faq-schema-decision.md
- needs-owner-check-notification-audit-across-intents.md
- notification-log-classification-labels.md / duplicate-topic-notification-log-rule.md
- customer-reply-detection-design.md / first-booking-self-check-notification-design.md
- dormant-mode-renotification-design.md / system-event-log-gap-fix.md
- suspension-reason-new-booking-block-design.md / grace-period-apology-intensity-fix.md
- api-call-failure-handling.md

## ウェブフック・監視・決済手段調査
- webhook-async-processing-design.md / webhook-function-a-implementation.md / webhook-function-b-implementation.md
- cloud-monitoring-alert-policy-design.md
- deposit-payment-research.md / deposit-payment-processor-unification-design.md
- target-datetime-denormalization-contingency-design.md

## 実装・テスト
- prototype/ (prototype-engine-design.md / automated-test-suite.md)
- schema/ (schema-validation-report.md)
- emulator-test/
