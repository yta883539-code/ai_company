# kura-pasha 公開までのチェックリスト(フェーズ196時点)

目的: 設計・実装・テストは完了しているが、実際の稼働にはオーナー承認が必要な外部サービス
設定が複数残っている。オーナーがpending-approval.mdを一つずつ確認する際に迷わないよう、
本ventureに関わる承認待ち事項を依存順に並べ、承認後すぐ着手できる作業内容を1箇所にまとめる。

## 現状(実装・検証済み、追加作業不要)

- Checkout Session発行ロジック・Stripe Webhook受信/署名検証/イベントディスパッチ:
  InMemoryStubによるテスト171件・schema検証32件いずれもパス(2026-09-28時点)。
- Stripe Webhook配信順序入れ替わりガード(`subscription_status`等の各分岐):
  フェーズ192〜195で対応完了。他venture(aircon-pasha・course-set-pasha・
  line-reservation-ai)との横断確認も済み。
- 日次バッチ(`run_daily_workshop_checks()`、トライアル30日到達報告・決済失敗3日前
  リマインド・制限モード移行時のオーナー通知): ロジック・送信判定・通知文言はProtocol
  経由の依存注入・InMemoryStubテスト(フェーズ120、8件)まで完了。
- 顧客ヒアリング候補選定・優先順位付け(候補1 ライディングショップ池上・候補2
  エクウスワールド)・連絡文面ドラフト(文面案A/B)・リハーサル台本: フェーズ7〜16で
  作成済み。

## 承認待ち事項(依存順、pending-approval.md記載の要約)

1. **Stripeアカウント開設**(2026-09-27 08:00 UTC記載)
   本人確認・銀行口座登録、本番APIキー・Webhook署名シークレット取得、
   `plan_id`→Stripe Price ID対応表・`success_url`/`cancel_url`の確定、
   Stripe側Webhookエンドポイント登録。
   → 承認後: 実キー設定・Webhookエンドポイント登録・Price ID対応表確定から着手。
   (本ventureはLINE Platform Webhook受信時点で検証済みの`event.source.userId`を
   使う設計のため、LIFFアプリ登録は不要。)

2. **LINE公式アカウント開設 + Cloud Scheduler作成**(2026-09-15 03:00 UTC記載)
   Messaging APIチャネルアクセストークン取得、日次1回(暫定JST 04:00)起動の
   Cloud Scheduler(GCPプロジェクトの課金設定を伴う)作成、オーナー向け通知送信先
   LINEユーザーID(`OWNER_LINE_USER_ID_PLACEHOLDER`)の設定。
   → 承認後: チャネルアクセストークン設定・Cloud Schedulerデプロイ・
   オーナーLINEユーザーID設定から着手。

3. **顧客ヒアリングの実施**(2026-09-11 04:00 UTC記載)
   候補1(ライディングショップ池上)・候補2(エクウスワールド)への初回コンタクト。
   → 承認後: 文面案A(メール・問い合わせフォーム用)・文面案B(電話トーク要点)を
   使い、電話での実連絡・メールフォーム送信文面の最終確定はオーナー自身が行うか、
   Gmail連携接続後に送信直前の毎回確認を経てのみ行う。

4. **実GCPプロジェクトの作成・Firestoreデータベースの新規作成**
   (2026-10-23 19:00 UTC記載)
   本番用の`WorkshopStoreProtocol`・`UsageCounterStoreProtocol`・
   `LinkingCodeStoreProtocol`・`UserProfileStoreProtocol`の4Protocol全ての実
   Firestoreアダプタ(フェーズ326までに実コード化完了済み。`WorkshopStoreProtocol`の
   deletion_candidate・deletion_confirmation系9メソッドのみフェーズ258時点では未着手で、
   フェーズ326で完了。フェーズ続き327追記)のデプロイ先となる、
   GCPプロジェクトの課金設定を含む作成、およびFirestoreデータベースの新規作成。
   → 承認後: 実GCPプロジェクトの作成、Firestoreデータベースの新規作成、
   `runtime-dependency-switching-design.md`で設計済みの`KURA_PASHA_FIRESTORE_ENABLED`
   フラグ切り替えロジックの実コード化・結合実装から着手する。

## 運用手順(工房数に応じたBilling Budget予算見直し、フェーズ続き309時点)

billing-budget-cap-safeguard-design.mdは、本venture想定の工房数(構造的に少数)を
踏まえ暫定予算額500円/月(50%・90%・100%到達時にオーナー宛メール通知)を採用した上で、
「複数職人プランの上限(101.8円/工房)を使い切る工房が5件を超える規模になった場合は、
オーナー確認の上で引き上げる」という申し送りを残していた。aircon-pashaフェーズ387・388、
course-set-pashaフェーズ380が同種の予算見直しプロセスを自venture側の
launch-readiness-checklist.mdへ運用手順として明文化・反映済みであることを踏まえ、
本venture側でも同様に運用手順として明記する。

- 複数職人プラン利用工房のうち、月間生成回数が上限(月20回)に達した工房数が
  5件を超えた時点で、billing-budget-cap-safeguard-design.mdの想定に基づき予算額の
  見直し案(現行500円/月・新規提案額・増加理由)を算出し、オーナーへ見直し提案を
  提示する。
- 見直し提案自体は承認待ち事項1〜4と同様、実際のCloud Billing Budgets & alertsの
  設定変更を伴うためオーナー承認が必要なアクションであり、本エージェントが単独で
  予算額を変更することはない。
- 本運用手順は承認待ち事項1〜4(実Stripeアカウント・LINE公式アカウント・実GCP
  プロジェクト等の作成)が承認され、実際にBilling Budgetが作成された後にのみ適用
  される(複数職人プラン利用工房数の実測自体が実Firestore/Stripeアカウント接続を
  前提とするため)。

## 次回候補

上記1〜4のいずれかがオーナーから承認された場合、その着手を最優先とする。承認が
得られるまでの間は、他venture・アイデア領域の前進、または本チェックリストと
pending-approval.mdの記載に齟齬がないかの定期的な棚卸しを行う。

## 定期棚卸し記録

2026-09-29 01:00 UTC: 4venture(kura-pasha・aircon-pasha・course-set-pasha・
line-reservation-ai)すべてのlaunch-readiness-checklist.md記載の承認待ち事項の日時
(計19件)をpending-approval.mdの「日時」「venture」欄と突き合わせたところ、全件が
1対1で対応しており記載漏れ・日時不一致は見つからなかった(aircon-pashaフェーズ278・
course-set-pasha 2026-09-28 20:00 UTC記載で過去に発見された記載漏れはいずれも是正済み
であることを確認)。またkura-pasha自身のStripe Webhook配信順序入れ替わりガード
(subscription-status-event-order-guard-design.md、フェーズ194)・line-reservation-ai
の同種ガード(subscription-event-order-guard-design.md・payment-failure-detected-at-
event-order-guard-design.md)・deployment-runbook.mdについても4venture間の横展開状況を
確認し、いずれも横展開済み・記載済みで新たな欠落は見つからなかった。

2026-10-01 19:00 UTC: 本チェックリスト「承認待ち事項」節に記載のkura-pasha自身の3件
(1. Stripeアカウント開設〈2026-09-27 08:00 UTC記載〉、2. LINE公式アカウント開設+
Cloud Scheduler作成〈2026-09-15 03:00 UTC記載〉、3. 顧客ヒアリングの実施〈2026-09-11
04:00 UTC記載〉)について、pending-approval.md本文と日時・内容を再度突き合わせたところ、
3件とも1対1で対応し記載漏れ・内容の齟齬は見つからなかった。いずれもオーナー承認が
得られておらず着手可能な新規作業がないため、本サイクルはkura-pasha側のコード変更・
設計追加は行わず、棚卸し記録の更新のみとした。回帰確認として`python3
prototype/run_all_tests.py`(16ファイルOK)・`python3 schema/validate_test_cases.py`
(32件)を再実行し、いずれもパスすることを確認した。承認が必要なアクション(支払い・
アカウント作成・外部公開・送信等)は今回発生していないためpending-approval.mdへの
追記なし。次回候補: 他venture・アイデア領域の前進、またはオーナーからの承認・回答を
待つ。

2026-10-02 08:00 UTC: 本チェックリスト「承認待ち事項」節に記載のkura-pasha自身の3件
(1. Stripeアカウント開設、2. LINE公式アカウント開設+Cloud Scheduler作成、3. 顧客ヒアリング
の実施)について、pending-approval.md本文と日時・内容を再度突き合わせたところ、3件とも
1対1で対応し記載漏れ・内容の齟齬は見つからなかった。いずれもオーナー承認が得られておらず
着手可能な新規作業がないため、本サイクルはkura-pasha側のコード変更・設計追加は行わず、
棚卸し記録の更新のみとした。回帰確認として`python3 prototype/run_all_tests.py`(16ファイル
OK)・`python3 schema/validate_test_cases.py`(32件)を再実行し、いずれもパスすることを
確認した。承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生
していないためpending-approval.mdへの追記なし。次回候補: 他venture・アイデア領域の前進、
またはオーナーからの承認・回答を待つ。

2026-10-20 00:00 UTC: 本チェックリスト「承認待ち事項」節の3件は2026-09-27 08:00 UTC
(Stripeアカウント開設)・2026-09-15 03:00 UTC(LINE公式アカウント開設+Cloud Scheduler
作成)・2026-09-11 04:00 UTC(顧客ヒアリングの実施)の記載からオーナー承認が得られておらず
約3〜6週間変化がないことを確認した(内容はpending-approval.md本文と1対1で対応、齟齬なし)。
これら3件は依然着手不可だが、承認を待つ間の前進としてフェーズ250で
`LinkingCodeStoreProtocol`(2コレクション分)の実Firestore接続アダプタを実コード化した
(実GCPアカウント接続を伴わない純粋なPythonコードのため承認不要、詳細はREADME.mdフェーズ
250参照)。回帰確認として`python3 -m unittest discover -s prototype -p "test_*.py"`
(226件)・`python3 prototype/test_cloud_function_webhook.py`(355件)・`python3
schema/validate_test_cases.py`(32件)を再実行し、いずれもパスすることを確認した。承認が
必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していないため
pending-approval.mdへの追記なし。次回候補: 残る`WorkshopStoreProtocol`の実コード化、他
venture・アイデア領域の前進、またはオーナーからの承認・回答を待つ。

2026-10-27 09:00 UTC(フェーズ269): 上記2026-10-20 00:00 UTCの次回候補「残る
`WorkshopStoreProtocol`の実コード化」が陳腐化記載であることを発見した。
firestore-provider-adapter-design.md 4節のフェーズ244追記により、本venture4Protocol
(`WorkshopStoreProtocol`・`UsageCounterStoreProtocol`・`LinkingCodeStoreProtocol`・
`UserProfileStoreProtocol`)全ての実コード化はフェーズ258までに完了済みであることを
確認した(`prototype/firestore_workshop_adapter.py`・`prototype/
test_firestore_workshop_adapter.py`が既に存在し、他3Protocolのアダプタと同じ方針
〈フェイククライアント経由のテスト、実GCP接続は結合実装フェーズまで行わない〉で
実装されている)。したがって本チェックリストの次回候補はこの時点で既に解消済みで
あり、残る着手可能な新規作業は無い。コード変更なし(棚卸し確認のみ)、回帰確認として
`python3 -m unittest discover -s prototype -p "test_*.py"`(295件、変更なし)・
`python3 prototype/test_cloud_function_webhook.py`(355件、変更なし)・`python3
schema/validate_test_cases.py`(32件、変更なし)を再実行し、いずれもパスすることを
確認した(回帰なし)。承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)
は今回発生していないためpending-approval.mdへの追記なし。次回候補: 「承認待ち事項」
節の3件(Stripeアカウント開設・LINE公式アカウント開設+Cloud Scheduler作成・顧客
ヒアリングの実施)がオーナーから承認された場合はその着手を最優先、またはREADME.md
フェーズ268次回候補(2)「4節のログ出力側(`event`構造化フィールド)への実装反映」
(結合実装フェーズ待ち)、他venture・アイデア領域の前進。

2026-10-28 07:00 UTC(フェーズ271): 本チェックリスト「承認待ち事項」節とpending-
approval.md本文の突き合わせ棚卸しを実施した。pending-approval.mdには本venture宛の
エントリが2026-10-23 19:00 UTC(実GCPプロジェクト作成・Firestoreデータベース新規
作成)を含め4件記録されているのに対し、本チェックリストの「承認待ち事項」節には
1〜3(Stripeアカウント開設・LINE公式アカウント開設+Cloud Scheduler作成・顧客
ヒアリングの実施)の3件しか反映されておらず、2026-10-23 19:00 UTC記載分が本チェック
リストへの反映漏れになっていたことを発見した。pending-approval.md側は正しく記録
済み(line-reservation-ai・aircon-pasha・forklift-pasha・course-set-pasha・
event-komiguai-pashaの5venture側の棚卸しで同種の記載漏れが是正されてきた経緯の
記録先そのものであり、欠落していたのはそれを要約する本チェックリスト側だった)
ため、実行済みアクションは一切ない。新規に項目4として追記し是正した。コード変更
なし、回帰確認として`python3 -m unittest discover -s prototype -p "test_*.py"`
(295件、変更なし)・`python3 prototype/test_cloud_function_webhook.py`
(355件、変更なし)・`python3 schema/validate_test_cases.py`(32件、変更なし)を
再実行し、いずれもパスすることを確認した(回帰なし)。承認が必要なアクション
(支払い・アカウント作成・外部公開・送信等)は今回発生していないためpending-
approval.mdへの追記なし。次回候補: 「承認待ち事項」節の4件のいずれかがオーナーから
承認された場合はその着手を最優先、またはREADME.mdフェーズ266次回候補(2)「4節の
ログ出力側(`event`構造化フィールド)への実装反映」(結合実装フェーズ待ち)、他
venture・アイデア領域の前進。

2026-11-23 08:00 UTC(フェーズ続き327): 7venture中最も更新が止まっていた本venture
(前回最終更新フェーズ続き326・2026-11-23 02:00 UTC、約7時間)を選定した。フェーズ325・
326でworkshop-store-firestore-adapter-design.md 29節のdeletion_candidate・
deletion_confirmation系9メソッドが実コード化されるまで未着手として残っていた事実を踏まえ、
本チェックリスト項目4「4Protocol全ての実Firestoreアダプタ(フェーズ258までに実コード化
完了済み)」、およびその根拠であるfirestore-provider-adapter-design.md フェーズ259追記
「本venture4Protocol全ての実コード化が完了した」が、いずれもWorkshopStoreProtocolに関して
時期尚早な記載だった(実際の完了はフェーズ326)ことを発見・是正した(両ファイルに追記)。
ドキュメントのみ、コード変更なし。既存テスト(`python3 -m unittest discover -s prototype -p
"test_*.py"`)全333件・schema検証(`python3 schema/validate_test_cases.py`)32件いずれも
パス(回帰なし)。実LINE/Stripe/GCP/Firestore API接続・支払い・アカウント作成・外部公開・
送信は一切行っていない。承認が必要な新規アクションは今回発生していないため
pending-approval.mdへの新規追記なし(2026-11-08 08:00 UTC記載の運営方針確認は前回オーナー
への直接プッシュ通知〈2026-11-22 23:00 UTC〉から約9時間・24時間未満かつ状況不変のため
今回も再通知は見送り)。次回候補: (1)「承認待ち事項」節の4件のいずれかがオーナーから
承認された場合はその着手を最優先、(2)他venture・アイデア領域の前進。
