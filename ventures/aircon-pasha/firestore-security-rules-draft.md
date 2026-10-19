# Firestoreセキュリティルール草案

kura-pashaのfirestore-security-rules-draft.md(フェーズ231)「未検証・残課題」で
「他venture(aircon-pasha・course-set-pasha・line-reservation-ai)も同型(Cloud
Functions経由のみ、クライアント直接アクセス無し)の設計であるため、同じdeny-all方針の
ルール草案を横展開できる可能性がある(次回候補として記録)」とされていた点を受け、本
venture(aircon-pasha)向けに横展開する。実Firestoreプロジェクトの作成自体はオーナー
承認待ち(pending-approval.md記載のLINE公式アカウント開設等と同種)のため、本ドキュメントは
承認後すぐに適用できる草案の作成に限定し、実デプロイは行わない。

## 1. 前提の整理

- 本ventureのFirestoreアクセスは、全てCloud Functions(`checkout_session.py`・
  `stripe_webhook.py`・`cloud_function_webhook.py`・`cloud_function_send_deletion_
  candidate_final_confirmations.py`等)からFirebase Admin SDK経由で行われる設計であり、
  LINEミニアプリ・Webブラウザ等のクライアントからFirestoreへ直接読み書きする経路は
  設計上存在しない(本ventureの申込・決済導線はLINE Flex Messageのpostbackアクション・
  申込フォーム経由でいずれもCloud Functionsエンドポイントに閉じている、
  checkout-initiation-flow-design.md参照)。
- Firebase Admin SDKはセキュリティルールを経由せずFirestoreにアクセスするため、
  Cloud Functions側の処理自体はルールの内容に影響されない。したがって本ルールの役割も
  kura-pasha版と同じく「クライアントからの直接アクセスを一切許可しない」という
  deny-allを明示することに限られる(多層防御・設定ミス時の事故防止が目的で、業務ロジック上
  必須ではない)。
- 対象コレクションは、data-retention-policy.md(フェーズ108)・user-account-linking-
  design.md 5節・firestore-provider-adapter-design.mdで確定済みの以下3コレクション
  (kura-pasha〈5コレクション〉・line-reservation-ai〈複数コレクション〉より少ないのは、
  本ventureが`deletion_candidate`・`payment_failure`・`blocked_but_billing`等の状態を
  いずれも単一の`user_profile`ドキュメントへ統合する設計を採っているため)。

| コレクション名 | 用途 | 設計doc |
|---|---|---|
| `user_profile` | LINEユーザー(業者)の屋号・事業形態・連携状態・Stripe状態・削除候補フラグ等を統合 | user-account-linking-design.md 5節・data-retention-policy.md |
| `pending_links` | 連携コード(linking_code)の保留状態(発行から24時間で自然失効) | user-account-linking-design.md 3節・firestore-provider-adapter-design.md |
| `usage_counter` | 業者ごとの月間生成回数カウンタ(`month`・`count`) | data-retention-policy.md |

## 2. ルール草案

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // 本venture全体でクライアント(LINEミニアプリ・ブラウザ等)からの直接アクセスは
    // 一切想定していない。全てCloud Functions(Admin SDK)経由のサーバーサイド処理と
    // する設計のため、全コレクションを明示的にdeny-allとする。
    match /user_profile/{userId} {
      allow read, write: if false;
    }
    match /pending_links/{linkingCode} {
      allow read, write: if false;
    }
    match /usage_counter/{userId} {
      allow read, write: if false;
    }
    // 上記3コレクション以外への想定外のアクセスも明示的に拒否する(デフォルトdeny
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
3. Cloud Functions(Admin SDK経由)の既存テスト(prototype配下、全739件)は本ルールの
   影響を受けない(Admin SDKはルールをバイパスするため)ことを確認済みの前提として
   明記する。

## 4. 未検証・残課題

- (解消済み)実Firestoreプロジェクトが無い状態での本ルールの検証は、Firebase Local
  Emulator Suite(デモプロジェクトID`demo-aircon-pasha`、実GCPプロジェクト・課金設定
  不要)を用いて完了した。詳細はfirestore-security-rules-emulator-verification.mdを
  参照。未認証クライアントからの直接アクセス5件がいずれも`403 PERMISSION_DENIED`に
  なることを確認済み。
- 実Firestoreプロジェクトの作成自体(オーナー承認待ち)は未着手のまま。承認・プロジェクト
  作成後、本番環境でも同様の検証を行うことが望ましい(firestore-security-rules-
  emulator-verification.md 4節参照)。
- 横展開の残りはcourse-set-pashaのみ(kura-pasha・aircon-pasha・forklift-pashaは完了)。
