# 解約確定時の生成即時ブロック(subscription-canceled-immediate-block-design.md)

## 1. 発見の経緯

kura-pashaフェーズ188で、「`subscription_status == "canceled"`が専用分岐を持たず、
ローカルのトライアル終了判定に紛れて扱われていたため、解約済みworkshopが最大30日間
生成を使い続けられてしまう」という欠落が見つかり修正された。aircon-pashaフェーズ273は
この横展開の一環として、course-set-pasha側は既にフェーズ256・257で決済失敗系フィールドの
クリア漏れ(`payment-failure-state-clear-on-subscription-deleted-design.md`)を修正済みと
記録していたが、それはkura-pashaフェーズ188と同じ「解約確定を専用分岐として扱えているか」
という論点そのものへの回答ではなかった。本フェーズはその論点を実際にcourse-set-pasha側の
コードで確認した。

## 2. 確認結果: course-set-pashaにはより広い欠落があった

course-set-pashaは、kura-pashaのような`subscription_status`列挙型(trialing/active/
past_due/canceled)ではなく、個別のタイムスタンプフィールドの組み合わせで生成可否を
判定する設計になっている(`cloud_function_webhook.py`)。

生成をブロックする既存の判定は次の2つのみ:

- `_is_generation_paused()`: トライアル終了通知送信済み(`trial_end_notified_at`が非null)
  かつ未アップグレード(`upgraded_at`がnull)。
- `_is_payment_suspended()`: 決済失敗検知(`payment_failure_detected_at`)から
  `PAYMENT_FAILURE_GRACE_PERIOD_DAYS`(7日)以上経過。

`stripe_webhook.py`の`customer.subscription.deleted`ハンドラは、削除候補化
(`mark_deletion_candidate_on_subscription_deleted`、365日後のデータ削除用)と、
既に決済失敗が検知済みだった場合の決済失敗系3フィールドのクリアのみを行い、解約確定
そのものを記録するフィールドを一切書き込んでいなかった。

その結果、**既に有料転換済み(`upgraded_at`が設定済み)のユーザーが解約した場合**、
上記2つの判定はどちらも成立しないため(`_is_generation_paused`は`upgraded_at`が
非nullである限り常にFalse、`_is_payment_suspended`は決済失敗が検知されない限り常に
False)、`customer.subscription.deleted`受信後も**無期限に**生成を使い続けられてしまう
欠落があった。kura-pashaフェーズ188の「最大30日間」よりも広い(期間の上限が無い)欠落
だった。

## 3. 修正内容

kura-pashaの`SubscriptionCanceledError`(専用の終端状態として解約を独立に扱う設計)と
同じ考え方を、course-set-pashaの個別タイムスタンプ方式に合わせて実装した。

- `UsageCounterProtocol`に`set_subscription_canceled_at`/`get_subscription_canceled_at`/
  `clear_subscription_canceled_at`を追加(`InMemoryUsageCounter`にも実装)。
- `cloud_function_webhook.py`に`_is_subscription_canceled()`判定関数と
  `SUBSCRIPTION_CANCELED_MESSAGE`を追加。`process_memo_event()`内で
  `_is_generation_paused()`/`_is_payment_suspended()`より先に判定し、該当時はLLM呼び出し・
  各種カウント増分を一切行わず即座に停止応答する(トライアル進捗・決済失敗猶予期間の
  状態によらず解約確定を最優先する)。
- `stripe_webhook.py`の`customer.subscription.deleted`ハンドラで、`usage_counter`指定時に
  (決済失敗検知の有無によらず)常に`subscription_canceled_at`を書き込むよう変更。
- `customer.subscription.created`(再契約)ハンドラで`subscription_canceled_at`を消去し、
  再契約後に生成が永久にブロックされたままにならないようにした。

## 4. テスト

- `test_cloud_function_webhook.py::ProcessMemoEventSubscriptionCanceledTest`(6件):
  解約確定時の停止応答、カウント不増分、未設定時は素通り、usage_counter未接続時は安全側
  False、再契約後のクリアで復旧、決済失敗猶予期間中でも解約確定が優先されること。
- `test_stripe_webhook.py::DispatchStripeEventTest`(4件追加): `customer.subscription.deleted`
  受信時の`subscription_canceled_at`書き込み(決済失敗の有無によらず)、usage_counter未接続時
  は素通り、`customer.subscription.created`受信時のクリア。
- 回帰確認: venture全体663件(変更前653件+新規10件)・schema検証21件、いずれもパス。

## 5. 残課題

- 実Stripeアカウント接続後、`customer.subscription.deleted`の`created`タイムスタンプが
  実際にevent発生時刻と一致するかの確認(現状は机上のモックイベントのみで検証)。
- 他venture(aircon-pasha・line-reservation-ai)についても、同じ「解約確定を専用の
  タイムスタンプ/状態として持っているか」の確認がまだ残っている(次回候補)。
