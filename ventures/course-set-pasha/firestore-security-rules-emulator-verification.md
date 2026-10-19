# Firestoreセキュリティルール検証(Firebase Local Emulator Suite、デモプロジェクト)

firestore-security-rules-draft.md 4節の残課題「実Firestoreプロジェクトが無いため、本
ルール自体をFirebase Local Emulator Suiteで実行して検証することは今回出来ていない」を
解消するため着手した(forklift-pashaフェーズ174・kura-pashaフェーズ249・
line-reservation-aiフェーズ続き332と同じ手法を本venture分に適用。kura-pashaフェーズ249
「次回候補(2)」〈course-set-pasha・aircon-pashaへの横展開〉を受けたもの)。

## 1. 前提の訂正

4節は検証には「実Firestoreプロジェクト作成(オーナー承認後)」が必要と記載していたが、
line-reservation-ai側の検証(フェーズ続き332)で確認済みの通り、Firebase Local Emulator
Suiteは`--project`に任意の文字列(デモプロジェクトID、本venture用に
`demo-course-set-pasha`)を指定するだけでFirestoreエミュレータを起動できる。実際のGCP
プロジェクトの作成・課金設定・Firebaseアカウントへのログインのいずれも不要であり(本
検証も`firebase login`していない状態で実施)、支払い・アカウント作成を伴わないため、
pending-approval.mdに記載されている承認待ち事項とは独立して実施可能であり、オーナー承認を
待たずに今回実施した。

## 2. 検証環境

- `firebase-tools@13`(`npx --yes firebase-tools@13`、本セッションでのみ使用。グローバル
  インストールは行っていない)
- Firestore Emulator `cloud-firestore-emulator-v1.19.8.jar`(firebase-toolsが自動取得)
- プロジェクトルート: 本venture配下に`firebase.json`(Firestoreエミュレータのみ設定)・
  `firestore.rules`(firestore-security-rules-draft.md 2節のルールをそのまま配置)を新設。
- 実行コマンド: `firebase emulators:exec --project demo-course-set-pasha --only firestore
  "bash emulator-test/run_rules_check.sh"`

## 3. 検証内容(emulator-test/run_rules_check.sh)

認証無し(クライアントSDK相当、本ventureはCloud Functions経由のサーバーサイド処理のみで
クライアント直接アクセス経路を持たない設計)のFirestore REST APIリクエストを、Firestore
Emulatorに対して直接送信し、いずれも`403 PERMISSION_DENIED`が返ることを確認した。

| # | 対象 | メソッド | 結果 |
|---|---|---|---|
| 1 | `usage_counter/{userId}` への書き込み | POST(create) | PASS: 403 PERMISSION_DENIED |
| 2 | `user_profile/{userId}` への書き込み | POST(create) | PASS: 403 PERMISSION_DENIED |
| 3 | `stripe_customer_index/{customerId}` への書き込み | POST(create) | PASS: 403 PERMISSION_DENIED |
| 4 | `pending_links/{linkingCode}` への書き込み | POST(create) | PASS: 403 PERMISSION_DENIED |
| 5 | 想定外トップレベルコレクション(`document=**` catch-all) | POST(create) | PASS: 403 PERMISSION_DENIED |
| 6 | `usage_counter/{userId}` の読み取り | GET | PASS: 403 PERMISSION_DENIED |

全6件がPASSし、firestore-security-rules-draft.md 2節のルール草案(4コレクションの
deny-all + 末尾`document=**`のcatch-all)が設計通りに機能することを確認した。

## 4. Cloud Functions(Admin SDK)側への影響

本検証はエミュレータのFirestore REST APIに対する未認証アクセスのみを対象とし、Admin SDK
経由のアクセス(本venture全体のテストスイート)には変更を加えていない。
firestore-security-rules-draft.md 1節の記載通りAdmin SDKはセキュリティルールをバイパス
するため、本ルールはAdmin SDK経由の既存処理に影響しない。

## 5. 残課題

- 本検証は未認証アクセスのdeny-allのみを対象とした。将来Cloud Functions以外のアクセス
  経路を追加する場合は、その時点で認証済みリクエストに対する許可条件を本ルールに追加し、
  本エミュレータ環境で許可・拒否双方のケースを検証する必要がある(現時点ではそのような
  経路の追加は未計画)。
- `firebase.json`・`firestore.rules`・`emulator-test/`はいずれもローカル検証専用であり、
  実Firestoreプロジェクト作成後はそのまま`firebase deploy --only firestore:rules`で適用
  できる想定(deploy自体は実行していない)。
- 残るaircon-pashaへの横展開はkura-pashaフェーズ249「次回候補(2)」として未実施のまま
  (同venture側の次回候補として申し送る)。
