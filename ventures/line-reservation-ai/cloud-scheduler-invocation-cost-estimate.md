# Cloud Scheduler起動間隔(暫定15分)がCloud Functions実行回数課金に与える影響の試算

reminder-scheduler-design.mdの「未解決のまま残る課題」に残っていた、Cloud Function C
(send_reminders)を単一Cloud Scheduler(暫定15分間隔)でトリガーする方式が、
hosting-platform-selection.mdで確認済みのGCP Cloud Functions無料枠(月200万回呼び出し)に
対してどの程度の影響を与えるかを試算する。

## 前提

- Cloud Function Cは店舗ごとではなく単一のCloud Schedulerジョブから起動され、1回の実行内で
  全店舗の`conversations`を横断的にスキャンして`select_due_initial_reminders()`/
  `select_due_resends()`を評価する設計(reminder-scheduler-design.md)。
  → 呼び出し回数は店舗数・予約件数に依存せず、Scheduler起動間隔のみで決まる。
- 起動間隔: 暫定15分(24時間× 60分 ÷ 15分 = 1日96回)。

## 試算

- 1日あたりのCloud Function C呼び出し回数: 96回
- 1か月(30日換算)あたり: 96回 × 30日 = 2,880回/月

これに対しCloud Function A(receive_webhook)・Cloud Function B(process_conversation_event)は
Webhookイベント駆動のためfirestore-traffic-cost-estimate.mdの想定トラフィック
(プロプラン相当で1店舗あたり月間予約300件、1予約2〜3通のやり取り)に比例して増える。
仮にプロプラン相当の店舗が100店舗ある場合でも、A・Bの呼び出し回数は
300件×100店舗×(1回のwebhook受信あたりA1回+B1回、往復メッセージ数に応じ数回)で
おおむね数万〜十数万回/月のオーダーにとどまり、Cloud Function Cの2,880回/月は
全体の呼び出し回数に対して無視できる規模(全体の1%未満)である。

## 結論

Cloud Scheduler起動間隔15分によるCloud Function C呼び出し回数(2,880回/月)は、
GCP Cloud Functionsの無料枠(月200万回)に対して0.15%程度であり、単独でも合算でも
無料枠を圧迫する要因にはならないと判断できる。起動間隔をより短く(例: 5分間隔、
1日288回・月8,640回)しても同様に無視できる規模のままであり、起動間隔の選定は
課金額ではなく「リマインド送信の目標時刻からの最大遅延許容度」
(reminder-timing-and-resend-rules.md参照)を基準に決めてよいことが確認できた。

## 残る課題

- Cloud Function A・Bの実際の呼び出し回数試算はfirestore-traffic-cost-estimate.mdの
  読み書き試算と同様、実測データ(顧客の利用実態)が取れるまでは仮定値に基づく概算にとどまる。
- 実際のCloud Schedulerジョブ作成・課金は「アカウント作成」に該当するため、
  着手時に改めてオーナー承認が必要(pending-approval.md参照)。
