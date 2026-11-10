# Firestoreセキュリティルール エミュレータ検証

firestore-security-rules-draft.md 4節「未検証・残課題」(実Firestoreプロジェクトが無い
ため、deny-allルール自体をFirebase Local Emulator Suiteで実行して検証できていない)を、
forklift-pashaフェーズ174・line-reservation-aiフェーズ続き332と同じ手法(デモプロジェクト
ID指定、実GCPプロジェクト・課金設定・Firebaseログインいずれも不要)で解消する。

## 1. 検証方法

- `firebase.json`・`firestore.rules`(firestore-security-rules-draft.md 2節のルール草案
  をそのまま配置)を本venture配下に新設した。
- `npx firebase-tools@13 emulators:exec --project demo-kura-pasha --only firestore
  "bash emulator-test/run_rules_check.sh"` で、Firestore Local Emulatorを起動し、
  `emulator-test/run_rules_check.sh`から未認証クライアント(Firestore REST API相当への
  生HTTPリクエスト、Admin SDK経由ではない)によるアクセスを試行した。
- デモプロジェクトID(`demo-kura-pasha`)を指定しているため、実GCPプロジェクトの作成・
  課金設定・`firebase login`はいずれも不要であり、支払い・アカウント作成を伴わないため
  オーナー承認を待たずに実施した。

## 2. 検証結果

対象8コレクション(`craftsman_workshop`・`stripe_customer_index`・`user_profile`・
`pending_workshop_invites`・`pending_links`・`usage_counter`・`line_webhook_event_ids`・
`processed_stripe_events`)への書き込み8件、`craftsman_workshop`・
`line_webhook_event_ids`への読み取り2件、想定外トップレベルコレクションへの書き込み1件
(`{document=**}` catch-allの検証)、計11件を試行し、全件`403 PERMISSION_DENIED`に
なることを確認した(`emulator-test/run_rules_check.sh`実行ログ、全11件PASS)。

## 3. 結論

firestore-security-rules-draft.md 4節の「未検証・残課題」のうち、本venture分の
Firebase Local Emulator Suiteでの検証は解消済みとする。実Firestoreプロジェクトへの
デプロイ自体は、他venture同様オーナーのFirestoreプロジェクト作成承認待ちのまま残る
(pending-approval.md参照)。

## 4. 追補(フェーズ295)

line-webhook-event-id-store-firestore-adapter-design.md(フェーズ288)・
stripe-event-id-store-firestore-adapter-design.md(フェーズ290)で`firestore.rules`に
追加された`line_webhook_event_ids`・`processed_stripe_events`の2コレクションは、
フェーズ294の時点では本検証(1〜3節)に未反映のまま残っていた(firestore-security-
rules-draft.md側の記載陳腐化はフェーズ294で是正済みだったが、本検証スクリプト自体の
拡張は次回候補として先送りされていた)。本フェーズで`emulator-test/run_rules_check.sh`
に当該2コレクション分の書き込み検証2件・読み取り検証1件を追加し、
`npx firebase-tools@13 emulators:exec --project demo-kura-pasha --only firestore
"bash emulator-test/run_rules_check.sh"`を再実行して全11件PASSを確認した(デモ
プロジェクトIDのため実GCPプロジェクト・課金設定・`firebase login`は今回も不要)。
これにより、firestore-security-rules-draft.md 4節が言及していた「新規2コレクション分の
`PERMISSION_DENIED`検証が未実施」という残課題は解消した。
