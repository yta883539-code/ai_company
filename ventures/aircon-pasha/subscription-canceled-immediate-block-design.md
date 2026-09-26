# 解約確定時の生成即時ブロック(subscription-canceled-immediate-block-design.md)

## 1. 発見の経緯

kura-pashaフェーズ188で、「`subscription_status == "canceled"`が専用分岐を持たず、
ローカルのトライアル終了判定に紛れて扱われていたため、解約済みworkshopが最大30日間
生成を使い続けられてしまう」という欠落が見つかり修正された。course-set-pashaフェーズ258は
この横展開の一環として、個別タイムスタンプ方式(`_is_generation_paused`/
`_is_payment_suspended`)では有料転換済みユーザーが解約後**無期限に**生成を使い続けられて
しまう、より広い欠落を発見・修正した。kura-pashaフェーズ188・course-set-pashaフェーズ258の
いずれも「他venture(aircon-pasha・line-reservation-ai)への横展開確認がまだ残っている」を
次回候補として残しており、aircon-pashaフェーズ273は一度この論点に触れたが、当時は
「course-set-pasha側の決済失敗系フィールドクリア漏れの解消状況」の確認にとどまり、
kura-pashaフェーズ188・course-set-pashaフェーズ258が本来問い直した「解約確定を専用分岐として
扱えているか」という論点そのものへの回答ではなかった。本フェーズはその論点を実際に
aircon-pasha側のコードで確認した。

## 2. 確認結果: aircon-pashaにもcourse-set-pashaと同型の欠落があった

aircon-pashaは、course-set-pashaと同じく`subscription_status`列挙型ではなく、個別の
タイムスタンプフィールドの組み合わせで生成可否を判定する設計になっている
(`cloud_function_webhook.py`)。

生成をブロックする既存の判定は次の2つのみ:

- `_is_generation_paused()`: トライアル終了通知送信済み(`trial_end_notified_at`が非null)
  かつ未アップグレード(`upgraded_at`がnull)。
- `_is_payment_suspended()`: 決済失敗検知後の猶予期間終了(`payment_suspended_at`が
  設定済み)。

`stripe_dispatch.py`の`customer.subscription.deleted`分岐(`dispatch_stripe_event()`)は、
削除候補化(365日後のデータ削除用)・`current_plan_id`のクリア・
`blocked_but_billing_owner_notified_at`のクリア・決済失敗系5フィールドのクリア
(フェーズ272・274)・解約完了案内の送信のみを行い、解約確定そのものを記録する
フィールドを一切書き込んでいなかった。

その結果、**既に有料転換済み(`upgraded_at`が設定済み)のユーザーが、決済失敗を一度も
経験せずに解約した場合**、上記2つの判定はどちらも成立しないため
(`_is_generation_paused`は`upgraded_at`が非nullである限り常にFalse、
`_is_payment_suspended`は決済失敗が検知されない限り常にFalse)、
`customer.subscription.deleted`受信後も**無期限に**生成を使い続けられてしまう欠落が
あった。course-set-pashaフェーズ258と同型(kura-pashaフェーズ188の「最大30日間」よりも
広い、期間の上限が無いケース)。

## 3. 修正内容

course-set-pashaの`_is_subscription_canceled()`/`subscription_canceled_at`と同じ考え方を、
aircon-pashaの「`profile_store`が保持する`UserProfile`を直接読む」設計
(`_is_generation_paused`/`_is_payment_suspended`と同じ引数形)に合わせて実装した。

- `user_id_linking.py`の`UserProfile`に`subscription_canceled_at: Optional[datetime] = None`
  を追加。`UserProfileStoreProtocol`に`get_subscription_canceled_at`/
  `set_subscription_canceled_at`を追加し、`InMemoryUserProfileStore`にも実装した。
  `resolve_linking_code()`(再連携時のフィールド引き継ぎ)にも本フィールドを追加し、
  再連携だけで解約済み状態が失われないようにした(引き継ぎ漏れがあると、解約済み
  user_idが新規連携コードを送っただけで生成ブロックが解除されてしまう別の欠落になる
  ため、修正と同時に対応)。
- `cloud_function_webhook.py`に`_is_subscription_canceled(profile)`判定関数と
  `SUBSCRIPTION_CANCELED_MESSAGE`を追加。`process_memo_event()`内で
  `_is_generation_paused()`/`_is_payment_suspended()`より先に判定し、該当時はLLM呼び出し・
  各種カウント増分を一切行わず即座に停止応答する(トライアル進捗・決済失敗猶予期間の
  状態によらず解約確定を最優先する)。
- `stripe_dispatch.py`の`customer.subscription.deleted`分岐で、`payment_store`指定時に
  (決済失敗検知の有無によらず)常に`subscription_canceled_at`を書き込むよう変更。
  `PaymentFailureStoreProtocol`自体は変更せず(design対象の5フィールドのみを扱う既存の
  位置づけを保つ)、`hasattr`で新メソッドの存在を確認してから呼ぶ
  (course-set-pashaの`_is_subscription_canceled()`と同じ後方互換方針)。
  `customer.subscription.created`分岐(再契約)で同様にクリアする。

## 4. テスト

- `test_cloud_function_webhook.py::ProcessMemoEventSubscriptionCanceledTest`(5件):
  解約確定時の停止応答、未設定時は素通り、profile_store未接続時は安全側False、
  generation_paused/payment_suspendedのいずれよりも優先されること。
- `test_stripe_dispatch.py`(4件追加): `customer.subscription.deleted`受信時の
  `subscription_canceled_at`書き込み(決済失敗の有無によらず)、payment_store未指定時は
  素通り、`customer.subscription.created`受信時のクリア、未指定時も例外を送出しない。
- `test_user_id_linking.py::InMemoryUserProfileStoreSubscriptionCanceledAtFieldTest`
  (5件): get/set・Noneクリア・未知user_idでのno-op・再連携時の引き継ぎ。
- 回帰確認: venture全体610件(変更前596件+新規14件、`python3 -m unittest discover
  -s prototype -p "test_*.py"`)・schema検証25件(`python3 schema/validate_test_cases.py`)、
  いずれもパス。

## 5. 残課題

- 実Stripeアカウント接続後、`customer.subscription.deleted`の`created`タイムスタンプが
  実際にevent発生時刻と一致するかの確認(現状は机上のモックイベントのみで検証)。
- line-reservation-aiについても、同じ「解約確定を専用のタイムスタンプ/状態として
  持っているか」の確認がまだ残っている(次回候補。kura-pashaフェーズ187時点では
  「該当する統合ハンドラ自体が未実装のため対象外」と記録されていたが、その後の実装
  状況次第では再点検が必要)。
