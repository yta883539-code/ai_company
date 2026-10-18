# Firestoreセキュリティルール草案

kura-pashaフェーズ244(workshop-store-firestore-adapter-design.md 31節)・course-set-pasha
フェーズ309の次回候補「Firestoreセキュリティルール草案の他venture横展開(course-set-pasha・
forklift-pasha・line-reservation-ai)」を受け、本venture分を検討する(course-set-pashaは
フェーズ309で完了済み、本フェーズは残り2件のうち1件目)。実Firestoreプロジェクトの作成自体は
オーナー承認待ち(pending-approval.md参照)のため、本ドキュメントは承認後すぐに適用できる
草案の作成に限定し、実デプロイは行わない。

## 1. 前提の整理

- 本ventureのFirestoreアクセスは、全てCloud Functions(`checkout_session.py`・
  `stripe_webhook.py`・`form_submission_flow.py`・`access_url_reissue_handler.py`・
  `cloud_function_send_trial_end_emails.py`・`cloud_function_send_deletion_
  confirmations.py`・`cloud_function_send_payment_failure_reminders.py`等)からFirebase
  Admin SDK経由で行われる設計である。
- kura-pashaのfirestore-security-rules-draft.mdが「未検証・残課題」で指摘していた懸念
  (本ventureはweb-form-ui-design.mdによりWebフォームからの入力経路を持つため、横展開の
  対象に含められるか要個別確認)を本フェーズで確認した。`prototype/form_submission_flow.py`
  (フォーム送信処理のオーケストレーション層)を確認した結果、フォーム送信は
  `process_form_submission()`というサーバーサイド関数呼び出しとして処理される設計であり、
  ブラウザ側のJavaScriptからFirestore Web SDKを用いて直接ドキュメントを読み書きする経路は
  存在しない(web-form-ui-design.mdのUI詳細設計もボタン選択・プルダウン等の入力操作のみを
  対象とし、送信先はサーバーサイドのエンドポイントを前提としている)。したがって他venture
  同様、クライアントからの直接アクセスを一切許可しないdeny-all方針がそのまま適用できる。
- Firebase Admin SDKはセキュリティルールを経由せずFirestoreにアクセスするため、Cloud
  Functions側の処理自体はルールの内容に影響されない。本ルールの役割は「クライアントからの
  直接アクセスを一切許可しない」というdeny-allを明示することに限られる(多層防御・設定ミス時
  の事故防止が目的で、業務ロジック上必須ではない)。
- 対象コレクションは、firestore-data-model.mdで確定済みの以下3コレクション(kura-pasha・
  course-set-pashaと異なり、本ventureは「1事業者(operator)=1契約」の単方向バッチ処理構成
  〈firestore-data-model.md「設計方針」〉のため、会話状態・招待コード・連携コード等の
  コレクションは持たない)。

| コレクション名 | 用途 | 設計doc |
|---|---|---|
| `fleet_operator` | 事業者(倉庫業・運送業・建設業事業者)ごとの契約・課金ドキュメント | firestore-data-model.md 1 |
| `vehicle` | 点検記録の車両単位マスタ(識別情報のみ、点検記録本文は持たない) | firestore-data-model.md 2 |
| `usage_counter` | 事業者ごとの月間生成回数の積算カウンタ | firestore-data-model.md 3 |

## 2. ルール草案

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // 本venture全体でクライアント(Webフォーム・ブラウザ等)からの直接アクセスは
    // 一切想定していない。全てCloud Functions(Admin SDK)経由のサーバーサイド処理と
    // する設計のため、全コレクションを明示的にdeny-allとする。
    match /fleet_operator/{internalId} {
      allow read, write: if false;
    }
    match /vehicle/{vehicleId} {
      allow read, write: if false;
    }
    match /usage_counter/{internalId} {
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

1. 実Firestoreプロジェクト作成(オーナー承認後)の際、`firebase.json`に本ルールを
   `firestore.rules`として配置する。
2. Firebase Local Emulator Suite(`firebase emulators:exec`)を用いた単体テストで、
   クライアントSDK相当のモック認証無しリクエストが全コレクションに対し`PERMISSION_
   DENIED`になることを確認するテストを追加する(他venture・prototype配下のInMemory
   実装テストとは別系統の、ルール自体の検証テスト)。
3. Cloud Functions(Admin SDK経由)の既存テスト(prototype配下、全21ファイル)は本ルールの
   影響を受けない(Admin SDKはルールをバイパスするため)ことを確認済みの前提として明記する。

## 4. 未検証・残課題

- ~~実Firestoreプロジェクトが無いため、本ルール自体をFirebase Local Emulator Suiteで
  実行して検証することは今回出来ていない~~ → line-reservation-aiフェーズ続き332と同じ
  手法(デモプロジェクトID指定、実GCPプロジェクト不要)でフェーズ174にて解消した。詳細は
  firestore-security-rules-emulator-verification.md参照(5件全てPASS)。
- ~~残るline-reservation-aiへの横展開は未着手~~ → line-reservation-aiフェーズ続き331にて
  同venture側で新規作成済み(kura-pashaフェーズ244「次回候補(2)」の3件が全て完了)。
