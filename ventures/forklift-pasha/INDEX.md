# ドキュメント索引(フェーズ時点のスナップショット)

本venture配下のMarkdown設計文書が70件超に達し、新規ファイル名だけでは全体像を
把握しにくくなったため、テーマ別に索引を作成した(kura-pasha/INDEX.md・
course-set-pasha/INDEX.md・line-reservation-ai/INDEX.mdと同型)。新しいトピックに
着手する前に、まず本ファイルで既存文書の有無を確認し、重複する設計の再生産を
避けること。個々の文書の最新状況は各ファイル自身とREADME.mdのフェーズログを
参照する(本索引はファイル一覧の整理のみを目的とし、内容の要約・ステータス
追跡は行わない)。

## 事業・市場・候補者開拓
- market-research.md / mvp-flow-draft.md / pricing-plan.md / onboarding-guide.md
- first-daily-generation-confirmation-notice-design.md
- content-generation-time-estimate.md / monthly-checklist-decision.md
- customer-interview-design.md / interview-candidate-selection-criteria.md
- interview-rehearsal-script.md / mock-interview-responses-draft.md
- rehearsal-timing-desk-estimate.md / candidate-longlist-draft.md
- channel-partner-exploration.md / kenkakyo-proposal-draft.md
- branch-outreach-individual-drafts.md / branch-outreach-priority-ranking.md
- campaign-window-approval-contingency.md

## LLM・出力品質
- llm-system-prompt-draft.md / llm-api-cost-estimate.md / unit-economics-estimate.md
- llm-quality-verification-plan.md / llm-quality-verification-results-template.md
- output-samples-validation.md

## 課金・Stripe・プラン
- checkout-session-cloud-function-entry-point-design.md
- checkout-session-completed-event-order-guard-design.md
- checkout-runtime-dependency-failure-applicant-message-design.md
- stripe-checkout-plan-id-design.md / stripe-webhook-entry-point-design.md
- stripe-event-idempotency-design.md / stripe-subscription-updated-dispatch-design.md
- subscription-canceled-immediate-block-design.md
- subscription-lifecycle-event-order-guard-design.md
- subscription-updated-event-order-guard-design.md
- payment-failure-detected-at-firestore-adapter-design.md
- payment-failure-dunning-design.md / payment-failure-event-order-guard-design.md
- payment-failure-reminder-scheduler-design.md / payment-identity-verification-design.md
- trial-end-condition-design.md / trial-end-notification-design.md
- trial-generation-count-notified-at-firestore-adapter-design.md
- usage-and-fleet-overage-notification-design.md
- plan-selection-current-plan-highlight-design.md / plan-selection-submission-wiring-design.md
- full-scan-to-indexed-query-threshold-decision.md

## アクセス・車両・削除まわり
- access-token-reissue-design.md / access-token-store-firestore-adapter-design.md
- access-url-reissue-http-entry-point-design.md
- deletion-candidate-design.md / deletion-candidate-query-consolidation-decision.md
- deletion-candidate-unreachable-reason-design.md
- deletion-confirmation-sent-unreachable-firestore-adapter-design.md
- fleet-operator-store-firestore-adapter-design.md
- fleet-operator-store-upgraded-canceled-firestore-adapter-design.md
- vehicle-label-duplicate-handling-design.md

## インフラ・運用
- tech-stack.md / firebase.json / firestore.rules / firestore.indexes.json
- firestore-data-model.md / firestore-composite-index-plan.md
- firestore-security-rules-draft.md / firestore-security-rules-emulator-verification.md
- runtime-dependency-switching-design.md / cloud-monitoring-alert-policy-design.md
- billing-budget-cap-safeguard-design.md
- data-retention-policy.md / vendor-breach-key-rotation-runbook.md
- launch-readiness-checklist.md / ci-setup.md
- schema/ (output.schema.json・validate_test_cases.py)
- prototype/ (InMemoryスタブ実装・テスト) / emulator-test/

## 顧客向け文面・法務・ビジュアル
- landing-page-wireframe.md / landing-page-copy-draft.md / landing-page/
- web-form-ui-design.md / web-form-mockup/
- legal-notices-draft.md / tone-and-manner-guideline.md
- error-page-css-commonality-design.md
- hero-visual-concept-draft.md / hero-visual-free-asset-candidates.md
- hero-visual-license-confirmation-and-final-selection.md
- hero-image-overlay-placement-design.md / free-stock-asset-search.md
- visual-asset-procurement-cost-review.md / year-round-proposal-wording-design.md

## 既知の運営課題
- 実GCPプロジェクト・Firestore・Stripeアカウントの作成が未承認で止まっており
  (pending-approval.md 2026-08-xx以降の記録、2026-11-08 08:00 UTCの運営方針確認
  依頼を参照)、設計・InMemoryスタブ実装の蓄積が実サービス稼働に直結していない
  状態が続いている。
