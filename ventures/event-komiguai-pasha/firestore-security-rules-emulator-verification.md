# Firestoreセキュリティルールのエミュレータ検証

firestore-security-rules-draft.md 4節「未検証・残課題」(実Firestoreプロジェクトが無いため
ルール自体をFirebase Local Emulator Suiteで検証できていない)を、aircon-pasha版
(firestore-security-rules-emulator-verification.md、forklift-pashaフェーズ174と同じ手法)を
踏襲して解消した。デモプロジェクトID`demo-event-komiguai-pasha`を指定し、実GCPプロジェクトの
作成・課金設定・Firebaseログインいずれも不要な形で検証を行った。

## 1. 検証方法

- `firebase.json`・`firestore.rules`(firestore-security-rules-draft.md 2節のルール草案を
  そのまま配置)・`emulator-test/run_rules_check.sh`を新設。
- `npx firebase-tools emulators:exec --project demo-event-komiguai-pasha --only firestore
  "bash emulator-test/run_rules_check.sh"` を実行し、Firestore Local Emulator上で未認証
  クライアント(REST API、認証トークン無し)からの直接アクセスが全て`403
  PERMISSION_DENIED`になることを確認した。

## 2. 検証結果

以下6件のチェックを実行し、全件`403 PERMISSION_DENIED`であることを確認した(PASS)。

1. `one_time_draft/{draftId}` への未認証直接書き込み
2. `inquiry/{inquiryId}` への未認証直接書き込み
3. `idempotency_key_index/{idempotencyKey}` への未認証直接書き込み(`expireAt`あり、
   `one_time_draft`側24時間TTLパターン)
4. `idempotency_key_index/{idempotencyKey}` への未認証直接書き込み(`expireAt`なし、
   `inquiry`側永続保存パターン)
5. 想定外トップレベルコレクションへの書き込み(`document=**` catch-allの検証)
6. `one_time_draft/{draftId}` への未認証読み取り

いずれもHTTP 403・`PERMISSION_DENIED`を確認し、`run_rules_check.sh`は
`ALL CHECKS PASSED`で終了した(exit code 0)。firestore-security-rules-draft.md 4節が
本venture固有の残課題として挙げていた「`idempotency_key_index`は`expireAt`を持つ
ドキュメントと持たないドキュメントが同一コレクション内に混在する設計のため、両パターンで
`PERMISSION_DENIED`になることを確認する必要がある」という点は、チェック3・4として個別に
検証し、両パターンとも同じdeny-allルールの対象であることを確認した。

## 3. 前提の確認(変更なし)

本venture(event-komiguai-pasha)のFirestoreアクセスは全てCloud Run functions(Admin SDK経由)
に閉じており、Webフォーム等のクライアントから直接Firestoreへアクセスする経路は設計上存在
しない(firestore-security-rules-draft.md 1節)。Admin SDKはセキュリティルールをバイパス
するため、既存のprototype配下のテスト群(本フェーズ時点で79件)・schema検証(22件)はこの
検証の影響を受けない。

## 4. 残課題

- 実Firestoreプロジェクトの作成自体はオーナー承認待ち(pending-approval.md記載のGCP
  プロジェクト作成等と同種)のため、本検証はあくまでルール草案のロジックそのものが意図通り
  deny-allとして機能することの確認であり、実デプロイは行っていない。承認・実際のFirestore
  プロジェクト作成後に、本番環境でも同様の検証(または同一スクリプトの再実行)を行うことが
  望ましい。
- 横展開の残りはoshien-pashaのみ(firestore-security-rules-draft.md 4節時点の記載を踏襲)。

最終更新: 2026-11-06 18:00 UTC(新規作成。aircon-pasha版と同じ手法で6件のdeny-all検証を
実施、全件PASS)
