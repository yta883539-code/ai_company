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

対象6コレクション(`craftsman_workshop`・`stripe_customer_index`・`user_profile`・
`pending_workshop_invites`・`pending_links`・`usage_counter`)への書き込み6件、
`craftsman_workshop`への読み取り1件、想定外トップレベルコレクションへの書き込み1件
(`{document=**}` catch-allの検証)、計8件を試行し、全件`403 PERMISSION_DENIED`に
なることを確認した(`emulator-test/run_rules_check.sh`実行ログ、全8件PASS)。

## 3. 結論

firestore-security-rules-draft.md 4節の「未検証・残課題」のうち、本venture分の
Firebase Local Emulator Suiteでの検証は解消済みとする。実Firestoreプロジェクトへの
デプロイ自体は、他venture同様オーナーのFirestoreプロジェクト作成承認待ちのまま残る
(pending-approval.md参照)。
