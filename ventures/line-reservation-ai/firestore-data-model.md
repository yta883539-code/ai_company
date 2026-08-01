# Firestoreデータモデル設計

hosting-platform-selection.md でホスティング基盤の第一候補として選定した
GCP Cloud Functions (Python) + Firestore を前提に、prototype/engine.py の各クラス
(BookingSlotManager / ConversationFlowStateMachine / NotificationLogAggregator /
EscalationConsolidator)が現在オンメモリの `dict` で保持している状態を、
Firestoreのコレクション/ドキュメントとしてどう分割するかを設計する。
実際のGCPプロジェクト作成・Firestore有効化(アカウント作成に該当)は着手時に
別途オーナー承認が必要なため、本設計は机上のスキーマ整理のみに留める。

## 設計方針

- engine.py の各クラスが持つメソッド(hold/confirm/release、present_candidates/
  select_slot 等)のシグネチャ・戻り値の型はそのまま維持し、内部の保持先だけを
  `dict` → Firestore ドキュメントの読み書きに差し替えられる形を目指す
  (呼び出し側であるLLM出力ハンドラのコードを変えずに済むようにするため)。
- 店舗(オーナー)ごとにデータを分離する必要があるため、全コレンクションで
  `storeId` をドキュメントIDまたはパスの先頭に含める(将来のマルチテナント対応)。
- channel-agnostic-session-id.md の方針(userId不在チャネルはセッションID代替)に
  合わせ、顧客を指す識別子は全コレクションで `sessionId`(LINEの場合は現状の
  userIdをそのまま使う)という共通名で統一する。

## コレクション構成

### 1. `stores/{storeId}`
店舗単位の設定ドキュメント。owner-settings-wireframe.md の「営業情報設定ページ」
に対応する。
```
{
  businessHours: [{start: "09:00", end: "18:00"}, ...],       // business-hours-lunch-break.md: 複数区間対応
  weekdayBusinessHours: {"5": [{start:"10:00", end:"15:00"}]}, // weekday-specific-business-hours.md、曜日は0=月〜6=日
  closedWeekdays: [0],                                          // availability-closed-weekday-support.md
  messageTone: "standard",                                      // message-tone-variants.md: formal|standard|casual
  faqInfo: {address: "...", parking: "...", paymentMethods: [...]}, // faq-response-templates.md 9a用
  menus: [{name: "カット", durationMinutes: 30}, ...]
}
```
書き込み頻度は低く(オーナーが設定画面を更新した時のみ)、読み取りは全会話処理で
毎回参照するホットパスのため、Cloud Functionsインスタンス内キャッシュ
(TTL数分程度)を挟む余地がある。

### 2. `stores/{storeId}/bookingSlots/{slotKey}`
BookingSlotManager の `_Slot` に対応する、仮押さえ→確定の2段階予約枠管理。
`slotKey` はこれまでの `(date, time)` タプルを `"2026-08-09_15:30"` のような
文字列に正規化してドキュメントIDとする(Firestoreドキュメントキーはタプル不可のため)。
```
{
  status: "pending" | "confirmed",
  sessionId: "U1234...",
  heldAt: <Timestamp>
}
```
- `hold()`/`confirm()` は「読み込み→空きチェック→書き込み」を1つの
  Firestoreトランザクション(`runTransaction`)にまとめることで、
  BookingSlotManagerのコメントに残っていた「MVP段階では単一プロセス前提で
  真の並行アクセス未対応」という制約をFirestore側で解消できる
  (Cloud Functionsは同時多重起動されうるため、この置き換えが実装上のメリットになる)。
- `HOLD_TIMEOUT`(5分)超過のpendingは、読み取り時に`heldAt`をチェックして
  失効扱いにする従来のロジック(`_expire_if_needed`)をそのまま踏襲しつつ、
  加えてFirestoreのTTLポリシー(`heldAt`に有効期限フィールドを別途持たせる)で
  古いpendingドキュメントを自動削除し、ストレージコストを抑える
  (TTL削除の実行タイミングは保証されないため、正しさは読み取り時チェックに
  依存し、TTLはあくまで掃除目的と位置づける)。
- confirmed状態のドキュメントはTTL対象外とする(予約実績として保持)。

### 3. `stores/{storeId}/conversations/{sessionId}`
ConversationFlowStateMachine の `_ConversationState` に対応する会話状態。
```
{
  stage: "candidates_presented" | "awaiting_details" | "confirmed",
  slotKey: "2026-08-09_15:30" | null,
  name: "山田太郎" | null,
  menu: "カット" | null,
  candidates: [{slotKey: "...", label: "8/9(土) 15:30〜"}, ...] | null,
  reconfirmCount: 0,
  lastActivityAt: <Timestamp>
}
```
- `release_idle_conversations()`(30分無応答失効)・`archive_completed_conversations()`
  は idle-conversation-trigger-design.md で設計済みの「Webhook便乗+5分間引き」方式
  のまま、Cloud Functions側でLINE Webhook受信のたびに`lastActivityAt`が
  閾値を超えたドキュメントをクエリして処理する。Firestoreは`lastActivityAt`への
  範囲クエリ(複合インデックス: storeId昇順+lastActivityAt昇順)で失効候補を
  効率的に取得できる。
- confirmed状態は前日リマインド等で参照され続けるため、アーカイブ時は削除ではなく
  `archivedAt`フィールドを立てるだけに留め(conversation-state-cleanup.md方針を踏襲)、
  前日リマインド送信バッチは`stage == "confirmed" AND archivedAt == null`のクエリで
  対象を拾う。

### 4. `stores/{storeId}/notificationLogEntries/{autoId}`
NotificationLogAggregator が集計する元データを、集計値ではなく生ログとして
追記型(append-only)で保存する。Firestoreにはクライアント側でのユニークカウント
機能がないため、`record()`が行っていた「(日付, sessionId, topic)でユニーク化」を
そのままオンメモリ集合(`_seen_topics`)で再現するのではなく、以下の2案を検討した。

- **案A(採用)**: `notificationLogEntries`には毎回そのまま追記し、
  ユニーク化はドキュメントID自体を `{date}_{sessionId}_{topic}` の決定的な文字列にした
  別コレクション `stores/{storeId}/notificationLogUniqueTopics/{date}_{sessionId}_{topic}`
  への「存在すれば上書き(冪等)」書き込みで表現する。集計画面はこの
  `notificationLogUniqueTopics`コレクションに対する`count()`集約クエリ
  (Firestoreが提供するサーバーサイドのドキュメント数カウント)で件数を取得でき、
  全件読み出し不要のため低コスト。
- 案B(不採用): Cloud Functions側でCloud Schedulerによる日次バッチ集計を行い
  事前計算済みの集計ドキュメントを作る方式。リアルタイム性は落ちるが読み取りは
  さらに軽量になる。MVPでは案Aの`count()`集約クエリで十分なコスト・速度が
  見込めるため、案Bは規模拡大時の代替案として残す。

`escalation_reason`が`unimplemented_feature`/`SYSTEM_ESCALATION_REASONS`
(`booking_conflict`・`candidate_selection_unresolved`)/それ以外(consultation)の
3区分は、`notificationLogEntries`の`category`フィールドに正規化して書き込み、
集計画面側は`category`でフィルタした`count()`クエリを使い分ける
(notification-log-classification-labels.mdの区分をそのまま踏襲)。

```
// notificationLogEntries/{autoId}
{
  date: "2026-08-09",
  sessionId: "U1234...",
  topic: "parking" | null,          // faq_segments由来、consultation/system_eventはnull
  category: "unresolved_faq" | "unimplemented_feature" | "consultation" | "system_event",
  escalationReason: "booking_conflict" | null,
  resolved: false | null,
  createdAt: <Timestamp>
}

// notificationLogUniqueTopics/{date}_{sessionId}_{topic}  (存在チェック用、値は空でも可)
{ createdAt: <Timestamp> }
```

### 5. `stores/{storeId}/escalationWindows/{sessionId}`
EscalationConsolidator の `_Window`(集約通知の時間窓管理)に対応する。
```
{
  windowStartAt: <Timestamp>,
  countInWindow: 0,
  reopenCount: 0,       // escalation-consolidation-logic.md「再発火3回目で都度通知」用
  lastEventAt: <Timestamp>
}
```
書き込み頻度は集約対象になるエスカレーション発生時のみで、`bookingSlots`と同様
Firestoreトランザクションでの読み書きが必要になる可能性が高い
(同一顧客からの連続イベントが短時間に重なるケースがあるため)。

## engine.pyとの対応関係のまとめ

| engine.pyのクラス/メソッド | Firestore側 |
|---|---|
| `BookingSlotManager._slots` (dict) | `stores/{storeId}/bookingSlots/{slotKey}` |
| `ConversationFlowStateMachine._states` (dict) | `stores/{storeId}/conversations/{sessionId}` |
| `NotificationLogAggregator._seen_topics` (set) | `stores/{storeId}/notificationLogUniqueTopics/{...}` |
| `NotificationLogAggregator.consultation_count`等 | `notificationLogEntries`への`category`別`count()`クエリ |
| `EscalationConsolidator._windows` (dict) | `stores/{storeId}/escalationWindows/{sessionId}` |
| `stores`設定(owner-settings-wireframe.md) | `stores/{storeId}` |

## 残課題

- `hold()`/`confirm()`・`escalationWindows`更新をFirestoreトランザクションに
  置き換える際の実装(現状engine.pyは`dict`直接操作のため、Firestore
  クライアントライブラリの`transaction`デコレータへの書き換えが必要)は
  実装フェーズ(Cloud Functions雛形作成)の課題として残す。
- Firestoreの読み書き課金・無料枠(1日あたりの読み取り/書き込み回数上限)が
  想定トラフィックで収まるかの試算は、hosting-platform-selection.mdでは
  定性的な比較に留めており、次の課題として残す。
- 実際のFirestoreデータベース作成・GCPプロジェクトの請求先設定は
  「アカウント作成」に該当するため、着手時に改めてオーナー承認が必要
  (pending-approval.md参照)。
