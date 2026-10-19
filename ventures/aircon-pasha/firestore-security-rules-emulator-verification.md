# Firestoreセキュリティルールのエミュレータ検証

firestore-security-rules-draft.md 4節「未検証・残課題」(実Firestoreプロジェクトが無いため
ルール自体をFirebase Local Emulator Suiteで検証できていない)を、forklift-pashaフェーズ174
(line-reservation-aiフェーズ続き332と同じ手法)と同じ方法で解消した。デモプロジェクトID
`demo-aircon-pasha`を指定し、実GCPプロジェクトの作成・課金設定・Firebaseログインいずれも
不要な形で検証を行った。

## 1. 検証方法

- `firebase.json`・`firestore.rules`(firestore-security-rules-draft.md 2節のルール草案を
  そのまま配置)・`emulator-test/run_rules_check.sh`を新設。
- `npx firebase-tools emulators:exec --project demo-aircon-pasha --only firestore
  "bash emulator-test/run_rules_check.sh"` を実行し、Firestore Local Emulator上で未認証
  クライアント(REST API、認証トークン無し)からの直接アクセスが全て`403
  PERMISSION_DENIED`になることを確認した。

## 2. 検証結果

以下5件のチェックを実行し、全件`403 PERMISSION_DENIED`であることを確認した(PASS)。

1. `user_profile/{userId}` への未認証直接書き込み
2. `pending_links/{linkingCode}` への未認証直接書き込み
3. `usage_counter/{userId}` への未認証直接書き込み
4. 想定外トップレベルコレクションへの書き込み(`document=**` catch-allの検証)
5. `user_profile/{userId}` への未認証読み取り

いずれもHTTP 403・`PERMISSION_DENIED`を確認し、`run_rules_check.sh`は
`ALL CHECKS PASSED`で終了した(exit code 0)。

## 3. 前提の確認(変更なし)

本venture(aircon-pasha)のFirestoreアクセスは全てCloud Functions(Admin SDK経由)に閉じて
おり、LINEミニアプリ・申込フォーム等のクライアントから直接Firestoreへアクセスする経路は
設計上存在しない(firestore-security-rules-draft.md 1節)。Admin SDKはセキュリティルールを
バイパスするため、既存のprototype配下のテスト群はこの検証の影響を受けない。

## 4. 残課題

- 実Firestoreプロジェクトの作成自体はオーナー承認待ち(pending-approval.md
  2026-08-23 04:00 UTC記載等)のため、本検証はあくまでルール草案のロジックそのものが
  意図通りdeny-allとして機能することの確認であり、実デプロイは行っていない。承認・実際の
  Firestoreプロジェクト作成後に、本番環境でも同様の検証(または同一スクリプトの再実行)を
  行うことが望ましい。
