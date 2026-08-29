# トライアル開始起点(申込時点 vs オンボーディング完了時点 vs 初回予約確定時点)の確定

作成日: 2026-08-29(定例更新)

onboarding-completion-message-design.md(フェーズ続き140)2節で「line-reservation-aiには
course-set-pasha/aircon-pashaのような`trial-start-anchor-decision.md`が未整備であり、この
起算点の明文化は別課題として残す」としていた点に対応し、本venture専用の確定ドキュメントを
新規作成する。

## 1. 結論: 起点は「店舗全体で最初の予約確定時」とする

course-set-pasha(初回生成成功時)・aircon-pasha(初回生成成功時)と同じ考え方で、
「申込時点」でも「オンボーディング完了時点(MVP必須項目が揃った時点)」でもなく、
**店舗全体で最初の予約確定(confirmed)が発生した時点**を14日間トライアルの起点として
確定する。これは`first-booking-self-check-notification-design.md`が既に検知・記録している
「店舗全体で最初の1件目の予約確定」と同一のタイミングである。

## 2. 理由

- pricing-plan.mdのトライアル条件は「14日間、または予約20件到達のいずれか早い方」という
  **期間条件と件数条件の複合**であり、両条件が同じ起点を共有していないと「期間は◯◯基準・
  件数は予約確定基準」で2つの条件が別々の起点を持つねじれが生じる(course-set-pasha
  フェーズ100・aircon-pashaフェーズ130と同じ問題)。件数条件(予約20件)は必然的に
  「予約確定」を数えるものであるため、期間条件の起点も予約確定基準に揃えるのが最も自然。
- 「申込時点」(onboarding-guide.mdステップ1)を起点にすると、そこからLINE公式アカウント
  連携(ステップ2)・営業情報設定(ステップ3)・接続テスト(ステップ4)・本番公開(ステップ5)
  という、オーナー自身の作業ペース次第で長さが変わる準備期間を経てようやく顧客対応が
  始まる。この準備期間はオーナーの都合(繁忙期か、店舗の他業務との兼ね合いか等)で
  数日〜数週間とばらつき、準備に時間がかかった店舗ほど実質的な利用可能日数が14日より
  目減りする不公平が生じる。これはcourse-set-pashaの「follow〜フォーム提出」・aircon-pashaの
  「フォーム提出→LINE連携→初回生成」で指摘された不公平と同種の構造である。
- 「オンボーディング完了時点」(ステップ3完了、onboarding-completion-message-design.mdが
  送信トリガーとして採用した時点)を起点にする案も検討したが、これも本質的な解決にならない。
  設定完了(ステップ3)から実際に顧客対応が始まる(=最初の予約が入る)までの間隔は、
  その店舗の集客力・LINE公式アカウントの友だち数次第でさらに不確定である。設定は済ませたが
  友だち登録がまだ少なく最初の予約が入るまで日数がかかる店舗ほど、この起点案でもやはり
  実質利用可能日数が目減りする。
- 「最初の予約確定時点」は「実際に価値(自動予約受付・確定メッセージ送信)を受け取った瞬間」
  であり、pricing-plan.mdが意図する「無料で試せる期間」の起点として最も実態に近い。
  申込・オンボーディング完了という「準備」段階の長さに一切左右されない点が、
  course-set-pasha/aircon-pashaの「初回生成成功時」(投稿文・作業完了報告という価値を
  実際に受け取った瞬間)と同じ設計思想である。
- `first-booking-self-check-notification-design.md`が既に`ConversationFlowStateMachine`
  (`prototype/engine.py`)に「店舗全体で最初の予約確定」を検知する仕組み
  (`_first_booking_self_check_sent`フラグ、`provide_details()`のconfirm成功分岐)を
  実装済みであり、同じ判定タイミングに`trialStartAt`の書き込みを便乗させれば、追加の
  イベント検知ロジックを新設せずに済む(course-set-pasha/aircon-pashaで一貫している
  「既存の完了フローに便乗させ、追加のAPI呼び出し・課金を発生させない」方針と整合する)。

## 3. `stores/{storeId}`ドキュメントへのフィールド追加

firestore-data-model.md 1節`stores/{storeId}`に以下を追加する。

```
{
  ...(既存フィールド)
  trialStartAt: null   // 新規追加。店舗全体で最初の予約確定成功時に1回だけ設定、以降不変
                        // (Timestamp | null)。first-booking-self-check-notification-design.mdの
                        // `_first_booking_self_check_sent`がTrueになる分岐と同一タイミングで
                        // 書き込む想定。
}
```

- 書き込みタイミングは`_first_booking_self_check_sent`をTrueにする分岐
  (`ConversationFlowStateMachine.provide_details()`のconfirm成功時、店舗全体で最初の1件目)
  と同一とし、同一書き込みに相乗りさせる(実Firestore接続時、単一ドキュメント更新の
  原子性を保つため。course-set-pasha/aircon-pashaと同じ方針)。
- `trialStartAt`が`null`のまま(=まだ1件も予約確定していない)店舗に対しては、期間到達
  判定用スケジューラ(下記5節、未着手)は判定対象外とする。件数条件(予約20件)についても
  同様に、`trialStartAt`が設定されて初めて件数のカウント対象になる(1件目の確定自体が
  カウント開始点であるため、実質的に「1件目」からカウントすることと同じ)。

## 4. pricing-plan.md・onboarding-completion-message-design.mdへの反映

- pricing-plan.md「無料トライアル条件(仮)」の「期間: 導入から14日間、または予約20件
  到達のいずれか早い方まで無料。」を、「期間: 初回の予約確定から14日間、または初回の予約
  確定を含め予約20件到達のいずれか早い方まで無料。」に表現を確定する(本ドキュメント作成と
  同時に反映)。
- onboarding-completion-message-design.md 2節の「起算点自体は...未確定」という記述は、
  本ドキュメントによる正式確定を受けて更新する(下記の通り反映)。なお2節の結論
  (本メッセージの送信有無とトライアル起算点は独立している)自体は変わらない。
  オンボーディング完了メッセージは「いつでも能動的にアップグレードできる案内」という
  役割のまま、トライアル起算(=最初の予約確定)とは別のタイミングで送信され続ける。

## 5. 今後の課題

- `trialStartAt`の実書き込みロジック(`ConversationFlowStateMachine.provide_details()`への
  Firestore書き込み配線、`InMemoryBookingRecordStore`相当の永続化層実装)は、
  firestore-data-model.mdの実接続フェーズ(オーナー承認待ち)に合わせて次回以降実装する。
- 期間到達判定用の日次スケジューラ本体(`trialStartAt`から14日経過した店舗の抽出クエリ・
  `trial_end_report_scheduler.py`への配線)、および件数条件(予約20件到達)判定ロジック
  (`InMemoryBookingRecordStore.list_booking_entries()`等での集計)は、
  aircon-pasha/course-set-pashaの日次スケジューラ設計を参考に別途設計する必要があり、
  引き続き未着手。
- 実際のFirestore・Cloud Scheduler実行環境の構築、LIFF等の外部サービス接続はオーナー承認待ち
  (pending-approval.md参照)。
