# Firestoreセキュリティルール草案

kura-pashaフェーズ244(workshop-store-firestore-adapter-design.md 31節)・
course-set-pashaフェーズ309・forklift-pashaフェーズ172の次回候補「Firestoreセキュリティ
ルール草案の他venture横展開(course-set-pasha・forklift-pasha・line-reservation-ai)」を
受け、本venture分に着手する(course-set-pasha・forklift-pashaは完了済み、本フェーズで
残り3件のうち最後の1件が完了する)。実Firestoreプロジェクトの作成自体はオーナー承認待ち
(pending-approval.md参照)のため、本ドキュメントは承認後すぐに適用できる草案の作成に
限定し、実デプロイは行わない。

## 1. 前提の整理

- 本ventureのFirestoreアクセスは、全てCloud Functions(`cloud_function_webhook.py`・
  `stripe_webhook.py`・`checkout_session.py`・`portal_session.py`・各種日次バッチ
  〈`reminder_scheduler.py`・`escalation_digest_flush_trigger.py`等〉)からFirebase
  Admin SDK経由で行われる設計である。
- checkout-initiation-flow-design.md(0節〜4節)により、本ventureはLINE LIFFアプリ方式
  (`liff.getIDToken()`で取得したIDトークンを`Authorization: Bearer`ヘッダでCloud
  Functionsエンドポイントに送信し、サーバー側でLINE Platform APIにより検証)を採用して
  おり、course-set-pashaと同様にLIFFはIDトークン取得にのみ使われる。LIFFアプリ(クライアント)
  からFirestore Web SDK経由でドキュメントを直接読み書きする経路は設計上存在しない。
- Firebase Admin SDKはセキュリティルールを経由せずFirestoreにアクセスするため、Cloud
  Functions側の処理自体はルールの内容に影響されない。したがって本ルールの役割も他venture
  同様、「クライアントからの直接アクセスを一切許可しない」というdeny-allを明示することに
  限られる(多層防御・設定ミス時の事故防止が目的で、業務ロジック上必須ではない)。
- 対象コレクションは、firestore-data-model.mdで確定済みの以下5コレクション(店舗
  〈`storeId`〉をルートとする1トップレベルコレクション+4サブコレクション構成)。
  他venture(kura-pasha・course-set-pasha・forklift-pasha)と異なり、本ventureは店舗単位の
  予約・会話状態・通知・エスカレーションを全て`stores/{storeId}`配下のサブコレクションに
  集約する設計(firestore-data-model.md「設計方針」のマルチテナント分離方針)である点が
  構造上の違いとなる。

| コレクション(パス) | 用途 | 設計doc |
|---|---|---|
| `stores/{storeId}` | 店舗単位の設定・課金状態ドキュメント | firestore-data-model.md 1 |
| `stores/{storeId}/bookingSlots/{slotKey}` | 予約枠の保持(hold/confirm/release) | firestore-data-model.md 2 |
| `stores/{storeId}/conversations/{sessionId}` | 会話状態(ConversationFlowStateMachine相当) | firestore-data-model.md 3 |
| `stores/{storeId}/notificationLogEntries/{autoId}` | 運営者通知ログ(重複抑制用) | firestore-data-model.md 4 |
| `stores/{storeId}/escalationWindows/{sessionId}` | エスカレーション集約ウィンドウ | firestore-data-model.md 5 |

## 2. ルール草案

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // 本venture全体でクライアント(LINE LIFFアプリ等)からの直接アクセスは一切想定して
    // いない。全てCloud Functions(Admin SDK)経由のサーバーサイド処理とする設計のため、
    // storesドキュメントとその配下の全サブコレクションをまとめて明示的にdeny-allとする。
    match /stores/{storeId} {
      allow read, write: if false;

      match /{subcollection=**} {
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

他venture版が各コレクションを個別に`match`していたのに対し、本ventureは全対象が
`stores/{storeId}`配下のサブコレクションに閉じているため、`{subcollection=**}`の再帰
ワイルドカードで4サブコレクションをまとめて1ブロックで記述できる(新規サブコレクションが
将来追加されてもルール修正不要という利点がある一方、個別コレクション名がルール上に
明示されない点はkura-pasha版等との差異として記録しておく)。

## 3. 検証方針(承認後の着手手順)

kura-pasha・course-set-pasha・forklift-pasha版と同じ方針を踏襲する。

1. 実Firestoreプロジェクト作成(オーナー承認後)の際、`firebase.json`に本ルールを
   `firestore.rules`として配置する。
2. Firebase Local Emulator Suite(`firebase emulators:exec`)を用いた単体テストで、
   クライアントSDK相当のモック認証無しリクエストが`stores/{storeId}`本体・4サブ
   コレクションのいずれに対しても`PERMISSION_DENIED`になることを確認するテストを追加する
   (他venture・prototype配下のInMemory実装テストとは別系統の、ルール自体の検証テスト)。
3. Cloud Functions(Admin SDK経由)の既存テスト(prototype配下、全946件)は本ルールの
   影響を受けない(Admin SDKはルールをバイパスするため)ことを確認済みの前提として明記する。

## 4. 未検証・残課題

- ~~実Firestoreプロジェクトが無いため、本ルール自体をFirebase Local Emulator Suiteで実行
  して検証することは今回出来ていない~~ → フェーズ続き332で解消済み。Firebase Local
  Emulator SuiteはデモプロジェクトID指定のみで実GCPプロジェクト無しに起動できることを
  確認し、未認証クライアントアクセスが全て`PERMISSION_DENIED`になることを検証した
  (詳細はfirestore-security-rules-emulator-verification.md参照)。実デプロイ(`firebase
  deploy --only firestore:rules`)自体は実Firestoreプロジェクト作成後のため未実施。
- 本フェーズでkura-pashaフェーズ244「次回候補(2)」(Firestoreセキュリティルール草案の
  他venture横展開、course-set-pasha・forklift-pasha・line-reservation-aiの3件)が全件
  完了した。
