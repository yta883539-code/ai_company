# ドキュメント索引(フェーズ時点のスナップショット)

本venture配下のMarkdown設計文書が40件超に達し、新規ファイル名だけでは全体像を
把握しにくくなったため、テーマ別に索引を作成した(kura-pasha/INDEX.md・
course-set-pasha/INDEX.md・line-reservation-ai/INDEX.md・forklift-pasha/INDEX.md・
aircon-pasha/INDEX.mdと同型)。新しいトピックに着手する前に、まず本ファイルで既存
文書の有無を確認し、重複する設計の再生産を避けること。個々の文書の最新状況は各
ファイル自身とREADME.mdのフェーズログを参照する(本索引はファイル一覧の整理のみを
目的とし、内容の要約・ステータス追跡は行わない)。

## 事業・市場・候補者開拓
- market-research.md / competitor-comparison.md / mvp-flow-draft.md
- pricing-plan.md / unit-economics-estimate.md / candidate-longlist-draft.md
- customer-interview-design.md / interview-rehearsal-script.md

## LLM・出力品質
- llm-system-prompt-draft.md / llm-api-cost-estimate.md
- llm-quality-verification-plan.md / output-samples-validation.md

## 申込フォーム・UI・LP
- inquiry-form-ui-draft.md / inquiry-handling-design.md
- web-form-ui-design.md / web-form-hosting-selection.md
- admin-search-ui-necessity-design.md
- landing-page-wireframe.md / landing-page-copy-draft.md
- custom-domain-vs-default-url-decision.md

## 決済・Stripe
- one-time-checkout-no-account-design.md
- checkout-session-success-cancel-url-design.md
- stripe-checkout-session-params-design.md
- stripe-event-idempotency-design.md
- stripe-webhook-signature-verification-design.md

## 冪等性・重複/衝突制御
- idempotency-key-duplicate-detection-firestore-query-design.md
- idempotency-key-write-conflict-control-design.md
- draft-id-last4-collision-design.md

## Cloud Run functions HTTPエントリポイント
- inquiry-form-http-entry-point-design.md
- submit-event-form-http-entry-point-design.md
- handle-stripe-webhook-http-entry-point-design.md
- get-result-page-http-entry-point-design.md

## ドラフト生成・結果配信・TTL
- draft-creation-and-event-memo-storage-design.md
- result-page-ttl-access-design.md / ttl-expiry-result-delivery-refund-design.md
- operational-message-templates-draft.md / result-page-display-copy-draft.md
- initial-contact-message-draft.md

## 顧客対応・文面・法務・横断レビュー
- customer-email-normalization-design.md / legal-notices-draft.md
- tone-and-manner-guideline.md
- cross-venture-inquiry-collection-naming-parity-review.md

## インフラ・運用
- tech-stack.md / firebase.json / firestore.rules
- firestore-security-rules-draft.md / firestore-security-rules-emulator-verification.md
- runtime-dependency-switching-design.md / cloud-monitoring-alert-policy-design.md
- data-retention-policy.md / vendor-breach-key-rotation-runbook.md / ci-setup.md

## コード・スキーマ・テスト(ディレクトリ)
- prototype/ (実装コード・テスト) / schema/ (スキーマ検証) / emulator-test/ / landing-page/
