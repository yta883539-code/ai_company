# Firestoreセキュリティルール草案

フェーズ228「次回候補(1)結合実装フェーズに備えた準備作業(Firestoreセキュリティルール
草案、テストダブル切り替え方式の設計等)」のうち、未着手だったFirestoreセキュリティ
ルール草案を検討する。実Firestoreプロジェクトの作成自体はオーナー承認待ち(pending-
approval.md参照)のため、本ドキュメントは承認後すぐに適用できる草案の作成に限定し、
実デプロイは行わない。

## 1. 前提の整理

- 本ventureのFirestoreアクセスは、全てCloud Functions(`checkout_session.py`・
  `stripe_webhook.py`・`cloud_function_run_daily_workshop_checks.py`等)からFirebase
  Admin SDK経由で行われる設計であり、LINEミニアプリ・Webブラウザ等のクライアントから
  Firestoreへ直接読み書きする経路は設計上存在しない(web-form-ui-design.md相当の
  ドキュメントが本ventureには無く、申込・決済導線はCheckout Session経由のCloud
  Functionsエンドポイントに閉じている)。
- Firebase Admin SDKはセキュリティルールを経由せずFirestoreにアクセスするため、
  Cloud Functions側の処理自体はルールの内容に影響されない。したがって本ルールの役割は
  「クライアントからの直接アクセスを一切許可しない」というdeny-allを明示することに
  限られる(多層防御・設定ミス時の事故防止が目的で、業務ロジック上必須ではない)。
- 対象コレクションは、workshop-store-firestore-adapter-design.md・firestore-provider-
  adapter-design.md・invite-code-store-firestore-adapter-design.md・linking-code-
  store-firestore-adapter-design.md・firestore-usage-counter-provider-adapter-
  design.md・line-webhook-event-id-store-firestore-adapter-design.md・
  stripe-event-id-store-firestore-adapter-design.mdで確定済みの以下8コレクション
  (フェーズ続き294で6→8に更新、4節参照)。

| コレクション名 | 用途 | 設計doc |
|---|---|---|
| `craftsman_workshop` | 工房(契約者)ごとの契約状態・プラン等 | workshop-store-firestore-adapter-design.md |
| `stripe_customer_index` | Stripe Customer ID→workshop_idの逆引き | workshop-store-firestore-adapter-design.md 11節 |
| `user_profile` | LINEユーザーの連携状態 | firestore-provider-adapter-design.md |
| `pending_workshop_invites` | 招待コード(invite_code)の保留状態 | invite-code-store-firestore-adapter-design.md |
| `pending_links` | 連携コード(linking_code)の保留状態 | linking-code-store-firestore-adapter-design.md |
| `usage_counter` | 工房ごとの月次利用回数カウンタ | firestore-usage-counter-provider-adapter-design.md |
| `line_webhook_event_ids` | LINE Webhookイベントのべき等性(重複配信排除) | line-webhook-event-id-store-firestore-adapter-design.md |
| `processed_stripe_events` | Stripe Webhookイベントのべき等性(重複配信排除) | stripe-event-id-store-firestore-adapter-design.md |

## 2. ルール草案

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // 本venture全体でクライアント(LINEミニアプリ・ブラウザ等)からの直接アクセスは
    // 一切想定していない。全てCloud Functions(Admin SDK)経由のサーバーサイド処理と
    // する設計のため、全コレクションを明示的にdeny-allとする。
    match /craftsman_workshop/{workshopId} {
      allow read, write: if false;
    }
    match /stripe_customer_index/{customerId} {
      allow read, write: if false;
    }
    match /user_profile/{userId} {
      allow read, write: if false;
    }
    match /pending_workshop_invites/{inviteCode} {
      allow read, write: if false;
    }
    match /pending_links/{linkingCode} {
      allow read, write: if false;
    }
    match /usage_counter/{workshopId} {
      allow read, write: if false;
    }
    match /line_webhook_event_ids/{webhookEventId} {
      allow read, write: if false;
    }
    match /processed_stripe_events/{eventId} {
      allow read, write: if false;
    }
    // 上記8コレクション以外への想定外のアクセスも明示的に拒否する(デフォルトdeny
    // との二重化だが、将来コレクションが追加された際の事故防止のため明示しておく)。
    match /{document=**} {
      allow read, write: if false;
    }
  }
}
```

## 3. 検証方針(承認後の着手手順)

1. 実Firestoreプロジェクト作成(オーナー承認後)の際、`firebase.json`に本ルールを
   `firestore.rules`として配置する。
2. Firebase Local Emulator Suite(`firebase emulators:exec`)を用いた単体テストで、
   クライアントSDK相当のモック認証無しリクエストが全コレクションに対し`PERMISSION_
   DENIED`になることを確認するテストを追加する(他venture・prototype配下のInMemory
   実装テストとは別系統の、ルール自体の検証テスト)。
3. Cloud Functions(Admin SDK経由)の既存テスト(prototype配下、全176件)は本ルールの
   影響を受けない(Admin SDKはルールをバイパスするため)ことを確認済みの前提として
   明記する。

## 4. 未検証・残課題

- ~~実Firestoreプロジェクトが無いため、本ルール自体をFirebase Local Emulator Suiteで
  実行して検証することは今回出来ていない(コード上の設計レビューのみ)。~~ →
  forklift-pashaフェーズ174・line-reservation-aiフェーズ続き332と同じ手法(デモプロジェクト
  ID`demo-kura-pasha`指定、実GCPプロジェクト・課金設定・Firebaseログインいずれも不要)で
  フェーズ249にて解消済み(詳細はfirestore-security-rules-emulator-verification.md参照)。
  対象6コレクションへの書き込み6件・読み取り1件・想定外コレクションへの書き込み1件、
  計8件がいずれも`PERMISSION_DENIED`になることを確認した。
- 他venture(course-set-pasha・forklift-pasha・line-reservation-ai)への同型(Cloud
  Functions経由のみ、クライアント直接アクセス無し)deny-allルール草案の横展開は、
  course-set-pashaフェーズ309・forklift-pashaフェーズ172・line-reservation-aiフェーズ
  続き331でそれぞれ完了済み(2026-10-18 05:00〜07:00 UTC)であることを本フェーズ
  (フェーズ246)で確認した。これにより本venture発の横展開候補は5venture全てで完了した
  (aircon-pashaも別途同型ルールを保持済み)。実デプロイ(Firebase Local Emulator Suite
  での`PERMISSION_DENIED`検証を含む)は5venture共通でオーナーのFirestoreプロジェクト
  作成承認待ちのまま残る。
- フェーズ続き294で発見・是正: 1節の対象コレクション一覧・2節のルール草案が、
  line-webhook-event-id-store-firestore-adapter-design.md(フェーズ288)・
  stripe-event-id-store-firestore-adapter-design.md(フェーズ290)で`firestore.rules`
  (実ファイル)に追加された`line_webhook_event_ids`・`processed_stripe_events`の
  2コレクション分を反映しないまま6コレクションの記載で据え置かれていた(両フェーズが
  `firestore.rules`自体は更新したものの、本「草案」ドキュメントへの反映漏れがあった
  陳腐化)。実ファイルの現状(8コレクション、本文書のとおり)に合わせて1節・2節を
  更新した。なお、3節の未検証項目で参照しているfirestore-security-rules-
  emulator-verification.md(フェーズ249)の`PERMISSION_DENIED`検証自体は当時の
  6コレクション構成のまま(フェーズ249は本ファイルの2コレクション追加より前)であり、
  新規2コレクション分の検証は未実施のまま残る(実Firestoreプロジェクト作成承認待ちの
  優先度に鑑み、本フェーズでは草案ドキュメントの記載是正に留め、再検証は次回候補とする)。
