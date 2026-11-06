# Firestoreセキュリティルール草案

aircon-pasha・course-set-pasha・forklift-pasha・kura-pasha・line-reservation-aiは
いずれもfirestore-security-rules-draft.mdを作成済みだが、本venture(event-komiguai-pasha)
のみ未作成のまま残っていたcross-venture parityギャップに対応する。実Firestoreプロジェクトの
作成自体はオーナー承認待ち(pending-approval.md記載のGCPプロジェクト作成等と同種)のため、
本ドキュメントは承認後すぐに適用できる草案の作成に限定し、実デプロイは行わない。

## 1. 前提の整理

- 本ventureのFirestoreアクセスは、全てWebフォーム送信を受けるCloud Run functions
  (prototype/form_submission_intake.py・prototype/inquiry_form_intake.py相当の
  エントリーポイント、tech-stack.mdフェーズ7「Webhook/バックエンド」節参照)から
  Firebase Admin SDK経由で行われる設計であり、ブラウザ等のクライアントからFirestoreへ
  直接読み書きする経路は設計上存在しない(本ventureはLINE公式アカウントを採用せず、
  申込・問い合わせのいずれもシンプルなWebフォーム→Cloud Run functionsエンドポイントに
  閉じている、tech-stack.mdフェーズ7参照)。
- Firebase Admin SDKはセキュリティルールを経由せずFirestoreにアクセスするため、
  Cloud Run functions側の処理自体は本ルールの内容に影響されない。したがって他venture版と
  同じく、本ルールの役割は「クライアントからの直接アクセスを一切許可しない」という
  deny-allを明示することに限られる(多層防御・設定ミス時の事故防止が目的で、業務ロジック上
  必須ではない)。
- 対象コレクションは、one-time-checkout-no-account-design.md(フェーズ10)・
  inquiry-handling-design.md(フェーズ15)・idempotency-key-write-conflict-control-design.md
  (フェーズ67・68)で確定済みの以下3コレクション(line-reservation-ai等の複数コレクション
  構成より少ないのは、本ventureがアカウント登録なしの単発決済モデルを採り、
  `organizer_account`相当の継続的ユーザープロファイルを持たないため)。

| コレクション名 | 用途 | 設計doc |
|---|---|---|
| `one_time_draft` | 単発決済(500円/回)の入力メモ・ステータス(`awaiting_payment`/`paid`)・生成結果を格納。24時間TTL | one-time-checkout-no-account-design.md・result-page-ttl-access-design.md |
| `inquiry` | メール未着・再送希望・返金希望等の問い合わせ受付キュー。TTLなし(永続保存) | inquiry-handling-design.md・data-retention-policy.md |
| `idempotency_key_index` | `idempotencyKey`をドキュメントIDとする重複検知インデックス。`expireAt`任意フィールドで`one_time_draft`側24時間/`inquiry`側永続の2方針を1コレクション内に共存 | idempotency-key-write-conflict-control-design.md(フェーズ67・68) |

## 2. ルール草案

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // 本venture全体でクライアント(ブラウザのWebフォーム等)からの直接アクセスは
    // 一切想定していない。全てCloud Run functions(Admin SDK)経由のサーバーサイド処理と
    // する設計のため、全コレクションを明示的にdeny-allとする。
    match /one_time_draft/{draftId} {
      allow read, write: if false;
    }
    match /inquiry/{inquiryId} {
      allow read, write: if false;
    }
    match /idempotency_key_index/{idempotencyKey} {
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

aircon-pasha版・kura-pasha版と同じ方針を踏襲する。

1. 実Firestoreプロジェクト作成(オーナー承認後)の際、`firestore.rules`として本ルールを
   配置する(`firebase.json`・`firestore.indexes.json`はaircon-pasha等の既存構成を流用する
   想定、本venture未作成分は別途着手)。
2. Firebase Local Emulator Suite(`firebase emulators:exec`)を用いた単体テストで、
   クライアントSDK相当のモック認証無しリクエストが3コレクションいずれに対しても
   `PERMISSION_DENIED`になることを確認するテストを追加する(aircon-pashaの
   firestore-security-rules-emulator-verification.mdと同種、prototype配下のInMemory
   実装テストとは別系統の、ルール自体の検証テスト)。
3. prototype配下の既存テスト(本フェーズ時点で79件)は本ルールの影響を受けない
   (Admin SDKはルールをバイパスするため)ことを確認済みの前提として明記する。

## 4. 未検証・残課題

- 実Firestoreプロジェクトの作成自体(オーナー承認待ち)は未着手のまま。承認・プロジェクト
  作成後、Firebase Local Emulator Suiteでの検証(aircon-pasha版と同様の手順)に着手する。
- `idempotency_key_index`は`expireAt`を持つドキュメントと持たないドキュメントが同一
  コレクション内に混在する設計(idempotency-key-write-conflict-control-design.md
  フェーズ68)のため、deny-allルール自体には影響しないが、エミュレーター検証時には
  両パターン(TTL対象/対象外)のドキュメントで`PERMISSION_DENIED`になることを確認する
  必要がある(本フェーズでは設計のみ、実検証は次回以降)。
- 横展開の残りはoshien-pashaのみ(aircon-pasha・course-set-pasha・forklift-pasha・
  kura-pasha・line-reservation-ai・event-komiguai-pashaは本フェーズで完了)。

最終更新: 2026-11-06 03:00 UTC(新規作成。aircon-pasha等の既存5venture横展開パターンを
踏襲し、本venture固有の3コレクション〈`one_time_draft`・`inquiry`・
`idempotency_key_index`〉に対するdeny-allルール草案を整理)
