# 解約確定(canceled)時の生成即時ブロック設計

作成日: 2026-09-26(フェーズ188)

## 背景

`prototype/usage_counter_workshop.py`の`process_generation_request()`は、フェーズ52で
「トライアル終了(`is_trial_period_over`)かつ有償契約未確認(`subscription_status != "active"`)」
の場合に生成をブロックする判定を実装し、フェーズ56で`subscription_status == "past_due"`
(決済失敗ダニング)を`is_payment_suspended()`(検知時刻から7日間の猶予)による専用分岐へ
切り出した。

しかし`subscription_status == "canceled"`(`customer.subscription.deleted`受信済み、
解約確定済み)は専用分岐を持たず、依然として「トライアル終了判定」経由の分岐
(`elif is_trial_period_over(...) and subscription_status != "active"`)に委ねられたままだった。

`is_trial_period_over()`はローカルトライアル(`trial_start_at`から30日経過、または
`trial_generation_used`が既にTrue)が終わっているかどうかのみを見る判定であり、
解約自体を見ていない。そのため次の欠落が存在した。

- workshop作成直後(`trial_start_at`設定直後)に有償プランへcheckoutし、初回生成を一度も
  使わないまま(`trial_generation_used=False`)Stripe側で即日解約した場合、
  `subscription_status`は`"canceled"`になるが`is_trial_period_over()`は依然False
  (30日経過もしていなければ初回生成も未使用のため)。
- この状態で`elif is_trial_period_over(...) and subscription_status != "active"`は
  `False and True = False`となり分岐に入らず、そのまま`check_and_increment_usage`まで
  到達してしまう。つまり**解約確定済みのworkshopが、ローカルトライアルの残り期間
  (最大30日)いっぱい生成を使い続けられてしまう**理論上のバグが存在した。

このバグクラスは、aircon-pasha フェーズ272・kura-pasha 自身のフェーズ187・
course-set-pasha フェーズ256/257で解消した「`customer.subscription.deleted`受信時に
決済失敗系フィールドのクリアが漏れる」系統とは異なるが、いずれも
「解約(`canceled`/`customer.subscription.deleted`)という終端イベントが、専用分岐を
持たない既存の状態判定に紛れて正しく扱われない」という点で同根の欠落である。

## 対応

`subscription_status`の3値("past_due"/"canceled"/その他)を排他的な専用分岐として
扱うよう`process_generation_request()`を変更した。

```python
if subscription_status == "past_due":
    if is_payment_suspended(workshop_id, now, workshop_store):
        raise PaymentSuspendedError(...)
elif subscription_status == "canceled":
    raise SubscriptionCanceledError(...)
elif is_trial_period_over(workshop_id, now, workshop_store) and subscription_status != "active":
    raise TrialPeriodOverError(...)
```

- 新設した`SubscriptionCanceledError`は、`is_trial_period_over()`の結果に関わらず
  (トライアル進捗を一切見ずに)無条件でブロックする。解約は「猶予」の概念を持たない
  終端状態であるため、`past_due`のような猶予期間は設けない。
- `WorkshopNotLinkedError`・`MemberRemovedError`・`PaymentSuspendedError`・
  `TrialPeriodOverError`と同様の位置づけとし、呼び出し側は新設の
  `SUBSCRIPTION_CANCELED_NOTICE`文言に変換して返す想定(実際のLLM/LINE配線は
  本モジュールの対象外、既存の例外設計と同じ切り分け)。

## テスト

`test_usage_counter_workshop.py`に2件追加した。

- `test_process_generation_request_raises_subscription_canceled_within_trial_window`:
  ローカルトライアル(30日・初回生成1回)がまだ終わっていない状態
  (`trial_start_at`設定直後、`trial_generation_used=False`)で`subscription_status="canceled"`
  の場合に`SubscriptionCanceledError`が送出され、`usage_counter_store`への加算が
  発生しないことを確認する(本フェーズで解消した欠落の再現・解消確認)。
- `test_process_generation_request_raises_subscription_canceled_after_trial_period_over`:
  トライアルが既に終了している場合も引き続き`canceled`workshopがブロックされることの
  回帰確認(フェーズ52時点でも`TrialPeriodOverError`としてブロックされていたケースが、
  本フェーズ以降は`SubscriptionCanceledError`に置き換わることを確認)。

回帰確認: `python3 test_usage_counter_workshop.py`(PASS=129・FAIL=0、変更前127+新規2)、
`python3 run_all_tests.py`(venture全16ファイルすべてOK)、
`python3 schema/validate_test_cases.py`(32件パス、変更前と同じ結果)いずれもパスを確認した。

## 今回のスコープに含めなかったもの・次の課題

- 本フェーズは`process_generation_request()`(生成リクエスト受信時の生成可否判定)のみを
  対象とした。他venture(aircon-pasha・course-set-pasha・line-reservation-ai)は生成可否
  判定の構造自体が本ventureと異なる(aircon-pasha・course-set-pashaはpost_generation_checks
  系、line-reservation-aiはsuspension_reasonベースのnew_booking blockという別方式)ため、
  同種のバグが存在するかは各venture固有の実装を個別に確認する必要がある(横断確認は
  次回以降の課題として残す)。
- コード変更のみで、実際のFirestore・LINE公式アカウント・Stripeとの接続(いずれも
  オーナー承認待ち、pending-approval.md参照)には影響しない。承認が必要なアクションは
  今回発生していないためpending-approval.mdへの追記はなし。
