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
  menus: [{name: "カット", durationMinutes: 30}, ...],
  suspensionReason: null,           // owner-settings-wireframe.md「4節へのsuspension_reason分岐の反映」
                                     // null | "trial_unselected" | "payment_failed" | "payment_suspended"
  paymentFailureDetectedAt: null,   // payment-failure-dunning-design.md 3節の猶予期間起点日時
                                     // (Timestamp、決済失敗検知時にWebhookが設定、決済成功復旧時にnullへ戻す)。
                                     // suspensionReasonが"payment_failed"の間、猶予期間の残り日数は
                                     // paymentFailureDetectedAt + 7日 − 現在日時 で算出する
                                     // (owner-settings-wireframe.md 555行目付近の設計どおり、
                                     // 別途「残り日数」フィールドは持たない)
  stripeCustomerId: null,            // checkout-initiation-flow-design.md 3節手順3・
                                     // prototype/store_profile_store.py`StoreProfileStoreProtocol`に対応
                                     // (Stripe Checkout Session作成時、既存契約歴のある店舗が同一customerを
                                     // 再利用できるようにするための順引きフィールド。文字列 | null。
                                     // `checkout.session.completed`イベント受信時にWebhookが設定する想定
                                     // 〈course-set-pasha/stripe-customer-id-linking-design.mdと同じ書き込み
                                     // タイミングだが、本ventureでは逆引き用の別コレクションは現時点で不要〉)
  trialStartAt: null                 // trial-start-anchor-decision.mdで確定。店舗全体で最初の予約確定
                                     // 成功時に1回だけ設定、以降不変(Timestamp | null)。
                                     // first-booking-self-check-notification-design.mdの
                                     // `_first_booking_self_check_sent`がTrueになる分岐と同一タイミングで
                                     // 書き込む(InMemory版はConversationFlowStateMachine._trial_start_at・
                                     // get_trial_start_at()として実装済み。実Firestore書き込み配線は
                                     // 実接続フェーズの課題として引き続き残る)。
  trialEndReportSentAt: null         // trial-end-scheduler-design.mdで新規追加。トライアル終了時の
                                     // 利用実績レポート送信済み時刻(Timestamp | null)。
                                     // dormant-mode-renotification-design.mdのGRACE_PERIOD_DAYSは
                                     // このタイムスタンプを起点とする。InMemory版は
                                     // ConversationFlowStateMachine._trial_end_report_sent_at・
                                     // get_trial_end_report_sent_at()/mark_trial_end_report_sent()
                                     // として実装済み。
  dormantTransitionedAt: null,       // dormant-mode-renotification-design.md「5. 送信要否の判定」で
                                     // 新規追加。休止モード1通目(移行時)通知の送信済み時刻
                                     // (Timestamp | null)。dormant_mode_scheduler.py
                                     // select_due_dormant_events()の冪等性フラグ。
  dormantRenotifyCount: 0            // 同上。休止モード2〜4通目(7/30/90日後)のうち
                                     // 何通送信済みか(0〜3の整数)。3に達すると2節の
                                     // 「4回で打ち切り」方針どおり以降送信しない。
  bookingConfirmedCount: 0           // trial-end-scheduler-design.md 5節(フェーズ続き150)で
                                     // 新規追加。予約確定累計回数(InMemory版の
                                     // InMemoryBookingRecordStore.count_confirmed_bookings()
                                     // 相当)。件数条件(3節、20件到達判定)を都度の
                                     // 集計クエリではなく本フィールドの単純な読み取りで
                                     // 判定するためのカウンタ。`bookingSlots/{slotKey}`の
                                     // confirm()書き込み(2節)と同一トランザクション内で
                                     // FieldValue.increment(1)する。キャンセル・変更後も
                                     // 減算しない(count_confirmed_bookings()と同じく
                                     // 「実際に確定させた回数」の指標のため)。
  onboardingCompletionMessageSentAt: null // onboarding-completion-message-design.md
                                     // (フェーズ続き155)で新規追加。オンボーディング完了
                                     // メッセージの送信済み時刻(Timestamp | null)。
                                     // 「MVPの最低限必須項目が初めて全て揃った」保存時に
                                     // 1回だけ書き込む冪等性フラグ。InMemory版は
                                     // InMemoryStoreProfileStoreの
                                     // is_onboarding_completion_message_sent()/
                                     // mark_onboarding_completion_message_sent()として
                                     // 実装済み(現状は真偽値相当のset保持、実Firestore化時に
                                     // Timestampへ拡張する)。
  slotIntervalMinutes: null,         // owner-settings-wireframe.md「予約枠の間隔」に対応する
                                     // フィールドが未定義だった欠落を2026-08-30(フェーズ続き155)
                                     // で追加。MVPの最低限必須項目(onboarding-guide.md
                                     // ステップ3)の1つ。AvailabilitySearcherの
                                     // slot_interval_minutesコンストラクタ引数に対応。
  concurrentCapacity: null           // 同上、「同時受付可能数」に対応するフィールドの欠落を
                                     // 同時に解消。MVPの最低限必須項目の1つ。
}
```
書き込み頻度は低く(オーナーが設定画面を更新した時、またはWebhookで決済状態が変化した時のみ)、
読み取りは全会話処理で毎回参照するホットパスのため、Cloud Functionsインスタンス内キャッシュ
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
- reminder-scheduler-design.mdで設計したCloud Function C(send_reminders)の冪等性・
  再送判定のため、以下4フィールドを追加する(2026-08-02 13:00 UTC追記。実装は未着手)。
  ```
  reminderSentAt: <Timestamp> | null,   // 初回リマインド送信済み時刻(未送信はnull)
  reminderSkipped: false,               // 確定時点で目標送信時刻を既に過ぎていたためスキップ
  resendSentAt: <Timestamp> | null,     // 当日朝の再送済み時刻(未送信はnull)
  customerRepliedAt: <Timestamp> | null // 確定後の顧客からの返信検知時刻(配線はcustomer-reply-detection-design.mdで設計・実装済み、Firestore書き込み自体は未着手)
  ```

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

trial-end-scheduler-design.md 5節(フェーズ続き148)で`NotificationLogAggregator`に
追加した`auto_handled_faq_count`(`faq_segments[].resolved:true`の集計、トライアル
終了レポートの「自動対応できたお問い合わせ」の実集計元)も、4区分目の
category:"auto_handled_faq"として同じ`notificationLogEntries`に書き込む
(`resolved:false`の`unresolved_faq`と異なり`notificationLogUniqueTopics`側への
ユニーク化書き込みは行わない。値引き目的の重複排除が不要なため、実際に自動応答した
回数分だけ`notificationLogEntries`に追記すればそのまま件数になる)。

```
// notificationLogEntries/{autoId}
{
  date: "2026-08-09",
  sessionId: "U1234...",
  topic: "parking" | null,          // faq_segments由来、consultation/system_eventはnull
  category: "unresolved_faq" | "unimplemented_feature" | "consultation" | "system_event" | "auto_handled_faq",
  escalationReason: "booking_conflict" | null,
  resolved: false | true | null,
  createdAt: <Timestamp>
}

// notificationLogUniqueTopics/{date}_{sessionId}_{topic}  (存在チェック用、値は空でも可。category:"unresolved_faq"のみ書き込む)
{ createdAt: <Timestamp> }
```

#### トライアル期間(14日)を跨いだ集計クエリ

`auto_handled_faq_count`は「30日分の読み取り専用画面」(オーナー向け通知ログ集計画面)
とは異なり、trial-end-scheduler-design.md 2節が定義する「トライアル開始日時
(`trialStartAt`)から14日間」という店舗ごとに起点が異なる期間で集計する必要がある。
オーナー向け画面側の`category`等値フィルタ`count()`クエリに加えて、Cloud Function E
(`send_trial_end_reports()`)側では以下のレンジクエリを`count()`集約で実行する:

```
stores/{storeId}/notificationLogEntries
  .where("category", "==", "auto_handled_faq")
  .where("createdAt", ">=", trialStartAt)
  .where("createdAt", "<", trialStartAt + 14days)
  .count()
```

等値(`category`)+範囲(`createdAt`)の複合条件になるため、Firestoreは
`(category ASC, createdAt ASC)`の複合インデックスを要求する(単一フィールド
インデックスでは不足)。実GCPプロジェクト作成後、初回クエリ実行時にコンソールの
自動提案リンクからインデックスを作成する想定(`firestore.indexes.json`への
事前定義も可能)。件数のみ必要で内訳(topic別等)は不要なため、`count()`集約
クエリのみでよく全件読み出しは発生しない(4節冒頭の設計方針と同じ低コスト特性)。

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

- (解消済み 2026-08-17 08:00 UTC: owner-settings-wireframe.md「4節へのsuspension_reason
  分岐の反映」の残課題だった、決済失敗検知日時のフィールドを`stores`コレクションに反映した。
  `suspensionReason`(既存のフラグ機構、値はpayment-failure-dunning-design.md 3節・
  owner-settings-wireframe.mdに準拠)と`paymentFailureDetectedAt`〈猶予期間の起点日時、
  Webhook受信時に設定〉の2フィールドを追加。実際のWebhookハンドラでの書き込み実装・
  Stripe Billing等の決済代行サービスとの接続は引き続きオーナー承認待ち)
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
