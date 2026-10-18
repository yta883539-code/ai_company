# Firestoreセキュリティルール検証(Firebase Local Emulator Suite、デモプロジェクト)

firestore-security-rules-draft.md 4節の残課題「実Firestoreプロジェクトが無いため、本
ルール自体をFirebase Local Emulator Suiteで実行して検証することは今回出来ていない」を
解消するため着手した(フェーズ続き332)。

## 1. 前提の訂正

4節は検証には「実Firestoreプロジェクト作成(オーナー承認後)」が必要と記載していたが、
確認の結果、Firebase Local Emulator Suiteは`--project`に任意の文字列(デモプロジェクトID、
例: `demo-line-reservation-ai`)を指定するだけでFirestoreエミュレータを起動できる。これは
完全にローカルで動作し、実際のGCPプロジェクトの作成・課金設定・Firebaseアカウントへの
ログインのいずれも不要である(`firebase login`していない状態でも動作することを確認した。
起動時に認証していない旨の警告が出るが、エミュレータの動作自体には影響しない)。したがって
本検証は支払い・アカウント作成を伴わず、pending-approval.mdに記載されている「実Stripe
アカウント」「実LINE公式アカウント」等の承認待ち事項とは独立して実施可能であり、オーナー
承認を待たずに今回実施した。

## 2. 検証環境

- `firebase-tools@13.35.1`(`npx --yes firebase-tools@13`、本セッションでのみ使用。
  グローバルインストールは行っていない)
- Firestore Emulator `cloud-firestore-emulator-v1.19.8.jar`(firebase-toolsが自動取得)
- プロジェクトルート: 本venture配下に`firebase.json`(Firestoreエミュレータのみ設定)・
  `firestore.rules`(firestore-security-rules-draft.md 2節のルールをそのまま配置)を新設。
- 実行コマンド: `firebase emulators:exec --project demo-line-reservation-ai --only firestore
  "bash emulator-test/run_rules_check.sh"`

## 3. 検証内容(emulator-test/run_rules_check.sh)

認証無し(クライアントSDK相当、LIFFのIDトークン検証を経由しない想定)のFirestore REST API
リクエストを、Firestore Emulatorに対して直接送信し、いずれも`403 PERMISSION_DENIED`が
返ることを確認した。

| # | 対象 | メソッド | 結果 |
|---|---|---|---|
| 1 | `stores/{storeId}` 本体への書き込み | POST(create) | PASS: 403 PERMISSION_DENIED |
| 2 | `stores/{storeId}/bookingSlots/{slotKey}` への書き込み | POST(create) | PASS: 403 PERMISSION_DENIED |
| 3 | `stores/{storeId}/conversations/{sessionId}` への書き込み | POST(create) | PASS: 403 PERMISSION_DENIED |
| 4 | 想定外トップレベルコレクション(`document=**` catch-all) | POST(create) | PASS: 403 PERMISSION_DENIED |
| 5 | `stores/{storeId}` 本体の読み取り | GET | PASS: 403 PERMISSION_DENIED |

全5件がPASSし、`{subcollection=**}`の再帰ワイルドカードが`bookingSlots`・`conversations`
双方のサブコレクションに正しく適用されること、および明示していない想定外コレクションも
末尾の`document=**`ブロックによってdenyされることを確認した(`notificationLogEntries`・
`escalationWindows`の2サブコレクションは`{subcollection=**}`と同一のルールブロックが
適用されるため個別確認は省略した)。

## 4. Cloud Functions(Admin SDK)側への影響

本検証はエミュレータのFirestore REST APIに対する未認証アクセスのみを対象とし、
Admin SDK経由のアクセス(本venture全体の946件のテストスイート)には変更を加えていない。
firestore-security-rules-draft.md 1節の記載通りAdmin SDKはセキュリティルールをバイパス
するため、本ルールはAdmin SDK経由の既存処理に影響しない。今回あらためて
`python3 -m unittest discover -s prototype -p "test_*.py"`(946件)・
`python3 schema/validate_test_cases.py`(28件)を実行し、いずれも変更なしでパスすることを
確認した(回帰なし)。

## 5. 残課題

- 本検証は未認証アクセスのdeny-allのみを対象とした。将来Cloud Functions以外のアクセス経路
  (例: 運営者向け管理画面をFirestore Web SDK経由で直接実装する等)を追加する場合は、その
  時点で認証済みリクエストに対する許可条件を本ルールに追加し、本エミュレータ環境で許可・
  拒否双方のケースを検証する必要がある(現時点ではそのような経路の追加は未計画)。
- `firebase.json`・`firestore.rules`・`emulator-test/`はいずれもローカル検証専用であり、
  実Firestoreプロジェクト作成後はそのまま`firebase deploy --only firestore:rules`で適用
  できる想定(deploy自体は実行していない)。
