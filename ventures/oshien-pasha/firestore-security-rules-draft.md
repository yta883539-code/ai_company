# Firestoreセキュリティルール草案

aircon-pasha・course-set-pasha・forklift-pasha・kura-pasha・line-reservation-ai・
event-komiguai-pashaはいずれもfirestore-security-rules-draft.mdを作成済みだが、本venture
(oshien-pasha)のみ未作成のまま残っていたcross-venture parityギャップに対応する(event-
komiguai-pashaフェーズ97次回候補(1)で指摘済みの「横展開の残りはoshien-pashaのみ」への対応)。
実Firestoreプロジェクトの作成自体はオーナー承認待ち(pending-approval.md記載のGCPプロジェクト
作成等と同種)のため、本ドキュメントは承認後すぐに適用できる草案の作成に限定し、実デプロイは
行わない。

## 1. 前提の整理

- 本ventureのFirestoreアクセスは、全てLINE Platform Webhook(月額フリーパスのアクセスURL
  再発行等)・Stripe Webhook(Checkout Session完了・`customer.subscription.*`系)を受ける
  Cloud Run functionsからFirebase Admin SDK経由で行われる設計であり、ブラウザ等のクライアント
  からFirestoreへ直接読み書きする経路は設計上存在しない。
- Firebase Admin SDKはセキュリティルールを経由せずFirestoreにアクセスするため、Cloud Run
  functions側の処理自体は本ルールの内容に影響されない。したがって他venture版と同じく、本ルール
  の役割は「クライアントからの直接アクセスを一切許可しない」というdeny-allを明示することに
  限られる(多層防御・設定ミス時の事故防止が目的で、業務ロジック上必須ではない)。
- 対象コレクションは、firestore-data-model.md(フェーズ36)で確定済みの以下1コレクション
  +サブコレクション構成(都度プランは`fan_pass`相当の永続ドキュメントを持たないため、
  他venture〈forklift-pashaの3コレクション構成等〉より少ないシンプルな構成となる)。

| コレクション名 | 用途 | 設計doc |
|---|---|---|
| `fan_pass/{internal_id}` | 月額フリーパス契約者単位の識別・課金(`stripeCustomerId`/`stripeSubscriptionId`/`subscriptionStatus`)・アクセス制御ドキュメント | firestore-data-model.md 1.1節 |
| `fan_pass/{internal_id}/generation_log/{auto_id}` | 1回の生成リクエストごとに追記するサブコレクション(異常検知用の内部ログ目的) | firestore-data-model.md 1.2節 |

## 2. ルール草案

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // 本venture全体でクライアント(ブラウザ等)からの直接アクセスは一切想定していない。
    // 全てCloud Run functions(Admin SDK)経由のサーバーサイド処理とする設計のため、
    // 全コレクションを明示的にdeny-allとする。
    match /fan_pass/{internalId} {
      allow read, write: if false;

      match /generation_log/{logId} {
        allow read, write: if false;
      }
    }
    // 上記以外への想定外のアクセスも明示的に拒否する(デフォルトdenyとの二重化だが、
    // 将来コレクションが追加された際の事故防止のため明示しておく)。
    match /{document=**} {
      allow read, write: if false;
    }
  }
}
```

## 3. 検証方針(承認後の着手手順)

aircon-pasha版・kura-pasha版・event-komiguai-pasha版と同じ方針を踏襲する。

1. 実Firestoreプロジェクト作成(オーナー承認後)の際、`firestore.rules`として本ルールを
   配置する(`firebase.json`・`firestore.indexes.json`は未作成のため別途着手)。
2. Firebase Local Emulator Suite(`firebase emulators:exec`)を用いた単体テストで、
   クライアントSDK相当のモック認証無しリクエストが`fan_pass`・`generation_log`いずれに
   対しても`PERMISSION_DENIED`になることを確認するテストを追加する(aircon-pashaの
   firestore-security-rules-emulator-verification.mdと同種)。
3. prototype配下の既存テストは本ルールの影響を受けない(Admin SDKはルールをバイパスする
   ため)ことを確認済みの前提として明記する。

## 4. 未検証・残課題

- 実Firestoreプロジェクトの作成自体(オーナー承認待ち)は未着手のまま。承認・プロジェクト
  作成後、Firebase Local Emulator Suiteでの検証(aircon-pasha版と同様の手順)に着手する。
- `firestore.indexes.json`は本venture未作成のため、他venture(aircon-pasha等)の既存構成を
  参考に別途整理する必要がある(本フェーズの範囲外、次回候補)。
- 横展開は本フェーズでaircon-pasha・course-set-pasha・forklift-pasha・kura-pasha・
  line-reservation-ai・event-komiguai-pasha・oshien-pashaの全7venture完了となった。

最終更新: 2026-11-06 13:00 UTC(新規作成。event-komiguai-pashaフェーズ97で指摘された
「横展開の残りはoshien-pashaのみ」に対応し、本venture固有の`fan_pass`コレクション+
`generation_log`サブコレクションに対するdeny-allルール草案を整理。全7venture横展開完了)
