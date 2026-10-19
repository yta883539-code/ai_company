# Firestoreセキュリティルール草案

kura-pashaフェーズ244(workshop-store-firestore-adapter-design.md 31節)の次回候補
「Firestoreセキュリティルール草案の他venture横展開(course-set-pasha・forklift-pasha・
line-reservation-ai)」を受け、本venture分に着手する。実Firestoreプロジェクトの作成自体は
オーナー承認待ち(pending-approval.md参照)のため、本ドキュメントは承認後すぐに適用できる
草案の作成に限定し、実デプロイは行わない。

## 1. 前提の整理

- 本ventureのFirestoreアクセスは、全てCloud Functions(`cloud_function_webhook.py`・
  `stripe_webhook.py`・`checkout_session.py`・`portal_session.py`・
  `cloud_function_application_form_submission.py`・`cloud_function_send_reminders.py`
  等の各種日次バッチ)からFirebase Admin SDK経由で行われる設計であり、LINEミニアプリ
  (LIFF)・申込フォーム等のクライアントからFirestoreへ直接読み書きする経路は設計上
  存在しない。LIFFはチェックアウト時のIDトークン取得にのみ使われ(checkout-initiation
  -flow-design.md)、取得したIDトークンをCloud Functionsエンドポイントに送信して
  検証・Checkout Session作成を行う構成であり、クライアントが直接Firestoreへアクセスする
  経路ではない。申込フォーム(application-form-submission-http-entry-point-design.md)も
  Google Apps Script経由でCloud Functionsエンドポイントへのみ送信する設計である。
- Firebase Admin SDKはセキュリティルールを経由せずFirestoreにアクセスするため、
  Cloud Functions側の処理自体はルールの内容に影響されない。したがって本ルールの役割は
  kura-pasha版(firestore-security-rules-draft.md)と同様、「クライアントからの直接
  アクセスを一切許可しない」というdeny-allを明示することに限られる(多層防御・設定ミス時の
  事故防止が目的で、業務ロジック上必須ではない)。
- 対象コレクションは、firestore-provider-adapter-design.md・firestore.indexes.jsonで
  確定済みの以下4コレクション(kura-pashaの6コレクションと異なり、本ventureは
  `craftsman_workshop`相当の独立コレクションを持たず、ジム・セッターの契約状態等も
  `usage_counter`コレクションに集約する設計のため4コレクションで足りる)。

| コレクション名 | 用途 | 設計doc |
|---|---|---|
| `usage_counter` | ジム/セッターごとの契約状態・プラン・月次利用回数カウンタ・初回生成通知済みフラグ等 | firestore-provider-adapter-design.md 19.2節・19節(`FirestoreFirstGenerationNoticeStore`は同コレクションの別フィールド) |
| `user_profile` | LINEユーザーの連携状態・削除候補系フィールド | firestore-provider-adapter-design.md、firestore.indexes.json |
| `stripe_customer_index` | Stripe Customer ID→user_idの逆引き | firestore-provider-adapter-design.md 232〜233行目 |
| `pending_links` | 連携コード(linking_code)の保留状態 | firestore-provider-adapter-design.md 41行目 |

## 2. ルール草案

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // 本venture全体でクライアント(LINEミニアプリ・申込フォーム等)からの直接アクセスは
    // 一切想定していない。全てCloud Functions(Admin SDK)経由のサーバーサイド処理と
    // する設計のため、全コレクションを明示的にdeny-allとする。
    match /usage_counter/{userId} {
      allow read, write: if false;
    }
    match /user_profile/{userId} {
      allow read, write: if false;
    }
    match /stripe_customer_index/{customerId} {
      allow read, write: if false;
    }
    match /pending_links/{linkingCode} {
      allow read, write: if false;
    }
    // 上記4コレクション以外への想定外のアクセスも明示的に拒否する(デフォルトdeny
    // との二重化だが、将来コレクションが追加された際の事故防止のため明示しておく)。
    match /{document=**} {
      allow read, write: if false;
    }
  }
}
```

## 3. 検証方針(承認後の着手手順)

kura-pasha版と同じ方針を踏襲する。

1. 実Firestoreプロジェクト作成(オーナー承認後)の際、`firebase.json`に本ルールを
   `firestore.rules`として配置する。
2. Firebase Local Emulator Suite(`firebase emulators:exec`)を用いた単体テストで、
   クライアントSDK相当のモック認証無しリクエストが全コレクションに対し`PERMISSION_
   DENIED`になることを確認するテストを追加する(他venture・prototype配下のInMemory
   実装テストとは別系統の、ルール自体の検証テスト)。
3. Cloud Functions(Admin SDK経由)の既存テスト(prototype配下、全761件)は本ルールの
   影響を受けない(Admin SDKはルールをバイパスするため)ことを確認済みの前提として
   明記する。

## 4. 未検証・残課題(解消済み)

- 実Firestoreプロジェクトが無いため、本ルール自体をFirebase Local Emulator Suiteで
  実行して検証することは当初出来ていなかったが、デモプロジェクトID(`demo-course-
  set-pasha`、実GCPプロジェクト・課金設定・Firebaseログイン不要)を用いた検証により
  解消した。詳細はfirestore-security-rules-emulator-verification.mdを参照。
- 残るforklift-pasha・line-reservation-aiへの横展開は、forklift-pashaフェーズ174・
  line-reservation-aiフェーズ続き332でそれぞれ同種の検証が既に実施済み。残る
  aircon-pashaへの横展開はkura-pashaフェーズ249「次回候補(2)」として未実施のまま
  残る(次回候補)。
