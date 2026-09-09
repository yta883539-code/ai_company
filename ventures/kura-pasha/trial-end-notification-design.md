# トライアル終了通知メッセージ設計(フェーズ59)

作成日: 2026-09-09(フェーズ59)

checkout-initiation-flow-design.md(フェーズ50)「残課題」に残っていた
「トライアル終了通知メッセージ自体(2(a))は本venture未設計」に対応し、
本venture未着手だったトライアル終了通知そのものを設計する。
aircon-pasha/trial-end-notification-design.md(フェーズ129)を参考にしつつ、本venture固有の
無料トライアル条件(pricing-plan.md「無料トライアル条件(仮)」、trial-end-condition-design.md
フェーズ47で確定した判定関数)である「生涯最初の生成1回まで無料、またはworkshop作成時点から
30日間のいずれか早い方」という二重条件を踏まえて設計する。

## 1. 他venture(aircon-pasha等)との条件の違い

aircon-pashaの二重条件は「生成回数10回」「期間14日」のいずれも複数回の余地がある
カウント基準だが、本venture固有の条件は「生成1回」という一度切りのフラグ
(`trial_generation_used`)である点が異なる。このため、回数条件(A)は「N回目に到達した
時点」ではなく「生涯最初(=唯一)の生成が完了した、まさにその時点」に発生し、
期間条件(B)より先に成立するのが通常のケースになる(受注が全く無いまま30日が経過する
場合のみ(B)が先に成立する)。

## 2. トリガー条件(二重条件のいずれか早い方)

trial-end-condition-design.md 4節の`is_trial_period_over()`が真になった時点と同じ2経路で
検知する。

- **(A) 生涯最初の生成完了**: `process_generation_request()`(prototype/
  usage_counter_workshop.py)内で`trial_generation_used`をFalse→Trueへ更新した、まさに
  その生成リクエストの返信に本ドキュメント3節の通知文言を便乗させる(aircon-pasha
  5節と同じく、追加のプッシュAPI呼び出し・課金を発生させない「生成完了時の返信に
  便乗させる」方式)。以降の生成(2回目以降)は`trial_generation_used`が既にTrueのため
  この経路では再送しない。
- **(B) 期間到達(30日)**: workshop作成(`trial_start_at`)から30日経過した時点で、
  一度も生成が行われていない(=(A)が未発生の)workshopに対してのみ検知する。生成
  イベントに便乗できないため、line-reservation-ai/reminder-scheduler-design.md相当の
  日次スケジューラ実行(Cloud Scheduler)によるプッシュメッセージ送信が必要になる
  (本venture側にはこの日次スケジューラ自体の設計〈他venture trial-end-scheduler-
  design.md相当〉がまだ無いため、6節「今後の課題」に残す)。
- 一度いずれかの経路で送信した場合は、他方の経路では二重送信しない
  (`trial_end_notified_at`のような送信済みフラグを`craftsman_workshop`に1つ持たせ、
  既に送信済みなら以降両条件とも判定をスキップする設計とする。5節で
  `WorkshopStoreProtocol`への追加フィールドとして次回以降のコード実装時に反映する)。
- (A)(B)いずれの経路で送信された場合も、後続で行うのは3節の同一メッセージ内容とする
  (aircon-pashaと同じ判断: トライアル終了という結果は同じであり、分岐を増やすと
  メッセージ・実装の複雑さに見合わない)。
- 送信先は契約者本人(`contractor_user_id`)に限定する(subscription-cancellation-
  notification-design.md〈フェーズ54〉以来の本venture固有の方針を踏襲。複数職人プランの
  共同利用者には送らない)。

## 3. 通知メッセージ内容(草案)

```
[鞍パシャッと] 無料トライアル、お疲れさまでした!

これまでの生成実績:
・受注内容整理メモ・納品案内・お手入れ案内の生成: ○回

浮いた事務作業時間の目安: 約○分(1回あたり平均20分と仮定、
content-generation-time-estimate.md参照)

引き続きご利用いただく場合は、下のボタンから有料プランをお選びください。
このまま何もしなければ自動課金は発生せず、生成のみ一時停止となります。

▼ 有料プランへ進む
[postbackボタン、checkout-initiation-flow-design.mdの意図検知〈厳守事項7b〉経由の
導線とは別に、通知メッセージからの直接ボタン起動を想定]
```

- pricing-plan.mdの「トライアル終了時: 自動課金はせず...継続を希望する場合のみ本人が
  プランを選択する形にする」という条件をそのまま踏まえ、「何もしなければ自動課金なし」で
  ある旨を明記する。
- 「浮いた事務作業時間の目安」はcontent-generation-time-estimate.md(フェーズ18)の
  1回あたり20分(仮置き)をそのまま使う。(A)経路(生成1回のみ)の場合は常に「約20分」
  固定、(B)経路(生成0回のまま30日経過)の場合はこの行を省略する(浮いた時間が0分と
  なり訴求にならないため)分岐を設ける。
- 有料プラン選択ボタンの実現方式(postbackアクション/LINEトーク内テキスト等)は
  checkout-initiation-flow-design.md 3節が既に確定済みの「LINEトーク内意図検知方式」を
  前提とするが、通知メッセージ自体からのボタン起動という導線はcheckout-initiation-
  flow-design.mdの対象外(同ドキュメントは利用者が能動的に「有料プランを始めたい」と
  発言した場合のみを扱う)であるため、本ドキュメントでは机上設計にとどめる。

### 3.1 postback_data形式(フェーズ61追記)

aircon-pashaのtrial-end-condition-a-cta-design.md(フェーズ137)が採用した形式をそのまま
踏襲し、`prototype/checkout_session.py`に次の2関数を実装した(本venture固有差分として、
plan_idはpricing-plan.mdの3プラン`light`/`standard`/`multi_craftsman`、キーはaircon-pashaの
日本語プラン名〈"スタンダード"等〉ではなく`build_checkout_session_params()`が既に使っている
英語plan_idをそのまま使う)。

- `build_start_checkout_postback_data(plan_id)`: `"action=start_checkout&plan=<plan_id>"`を
  組み立てる。未知のplan_idは`ValueError`(`build_checkout_session_params()`と同じ安全側方針)。
- `parse_start_checkout_postback_data(data)`: 上記形式を解釈しplan_idを返す。プラン未指定の
  完全一致`"action=start_checkout"`(本ドキュメント3節の汎用「▼ 有料プランへ進む」ボタン用)は
  `DEFAULT_CHECKOUT_PLAN`(`"standard"`)を返す。それ以外(無関係なdata・未知のplan_id)は
  `None`を返し、呼び出し側は不正なCheckout Session作成に繋げず素通りする想定。

本フェーズはpostback_dataの組み立て・解釈という純粋関数のみを対象とし、実際にLINEの
返信・プッシュメッセージへボタンを添付して送る配線(aircon-pashaの`ReplyClient.reply()`
`quick_reply`引数・`process_postback_event()`相当)は、本venture自体にまだLINE Webhook層
(`cloud_function_webhook.py`相当)が存在しないため対象外とし、次の課題として残す
(6節参照)。

## 4. トライアル終了後(未アップグレード)の挙動

- 通知送信後、実際にトライアル終了条件((A)または(B))に達した以降の生成リクエストは、
  trial-end-condition-design.mdフェーズ52で実装済みの`TrialPeriodOverError`により既に
  生成一時停止となる(`is_trial_period_over(...)`が真かつ`get_subscription_status(...)
  != "active"`の場合)。本ドキュメントは新たな一時停止処理を追加するものではなく、
  既存の一時停止処理と同じタイミングで通知メッセージも送るという整理になる。
- 一時停止中に契約者が有料プランへ進んだ場合は、既存のCheckout Session発行フロー
  (checkout-initiation-flow-design.md)〜Stripe決済完了
  (`handle_checkout_session_completed()`、プロトタイプ実装済み)により
  `subscription_status`が`"active"`へ更新され、通常の有料契約workshopへ遷移する
  (この経路は本ドキュメント作成前から実装済み)。

## 5. 実装への影響メモ(フェーズ60で(A)経路のみ実装済み)

- `WorkshopStoreProtocol`(prototype/usage_counter_workshop.py)へ
  `get_trial_end_notified_at`/`set_trial_end_notified_at`の2メソッドを追加した
  (2節の二重送信防止フラグ)。命名は既存の`get_payment_failure_detected_at`/
  `set_payment_failure_detected_at`(フェーズ56)と同じスタイルを踏襲した。
- (A)経路は`process_generation_request()`内、`trial_generation_used`が今回の呼び出しで
  初めてFalse→Trueへ更新された、かつ`trial_end_notified_at`が未設定の場合に限り
  `GenerationRequestResult.trial_end_notification_due`をTrueにして返し、同時に
  `trial_end_notified_at`へ`now`を書き込む処理として実装した(呼び出し側はこの
  戻り値を見て3節の通知メッセージ送信要否を判断する想定。実際のLINEプッシュ送信自体は
  実LINE Messaging API接続がオーナー承認待ちのため未実装)。
- (B)経路は本venture側にまだ存在しない日次スケジューラ本体の実装が前提となる(6節参照)。
  ただし`trial_end_notified_at`のデータ構造自体は(A)(B)共通で使える形にしてあるため、
  (B)経路実装時に(A)経路が既に送信済みかどうかを同じフィールドで判定できる。
- テスト(`prototype/test_usage_counter_workshop.py`)で、(A)経路の通知要否判定
  (1回目の生成成功でtrial_end_notification_dueがTrue・trial_end_notified_atが
  書き込まれる/2回目以降はFalse・上書きされない/(B)経路相当で既に通知済みの場合は
  (A)経路条件を満たしてもFalseのまま)を検証した(新規テスト3件)。

## 6. 今後の課題

- (B)期間到達判定用の日次スケジューラの選定ロジック・構成(line-reservation-ai/
  reminder-scheduler-design.md・aircon-pasha/trial-end-scheduler-design.md相当)は
  本venture未着手。本venture固有の低頻度受注特性(候補workshopの多くは(A)経路で
  完結し(B)経路の発生頻度自体が低いと見込まれる)を踏まえ、他venture(高頻度利用が
  前提)ほどの優先度は無いと判断し、次の課題として残す。
- 3節の通知メッセージからの直接ボタン起動について、postback_dataの組み立て・解釈
  (`build_start_checkout_postback_data`/`parse_start_checkout_postback_data`)は
  フェーズ61で対応済み(3.1節)。ただしLINE返信・プッシュメッセージへ実際にボタンを
  添付して送信する配線(aircon-pashaの`ReplyClient.reply()`quick_reply引数・
  `process_postback_event()`相当)は、本venture自体にLINE Webhook層
  (`cloud_function_webhook.py`相当)がまだ存在しないため引き続き次の課題として残す。
- `trial_end_notification_due`がTrueになった場合に実際にLINEプッシュメッセージ
  (3節の文言)を送信する呼び出し側の配線(生成完了時の通常返信への便乗)は、実LINE
  Messaging API接続がオーナー承認待ちのため机上設計・戻り値の受け渡しまでにとどまる
  (次の課題として残す)。
- 実際のCloud Scheduler実行環境の構築、LINE公式アカウント接続・Stripe接続はいずれも
  オーナー承認待ちの範囲(pending-approval.md参照)。本ドキュメントはメッセージ文言・
  トリガー条件の机上設計にとどめる。

最終更新: 2026-09-09 08:00 UTC(フェーズ59: トライアル終了通知メッセージをcontent-
generation-time-estimate.md〈フェーズ18〉の20分試算を用いて設計。(A)生涯最初の生成完了
経路と(B)30日期間到達経路の二重トリガー・二重送信防止方針を確定。実コード実装・日次
スケジューラ本体は次の課題として残る)

最終更新: 2026-09-09 10:00 UTC(フェーズ61: 3節「▼ 有料プランへ進む」ボタンの
postback_data形式を、aircon-pashaのtrial-end-condition-a-cta-design.md〈フェーズ137〉と
同じ形式で確定し`prototype/checkout_session.py`に`build_start_checkout_postback_data`/
`parse_start_checkout_postback_data`を実装した(3.1節)。新規テスト9件追加、venture全体
291件→300件全件・schema検証27件いずれもパス。実際にLINE返信へボタンを添付する配線は
本venture未着手のLINE Webhook層を要するため引き続き次の課題)

最終更新: 2026-09-09 09:00 UTC(フェーズ60: (A)経路の通知要否判定を
`prototype/usage_counter_workshop.py`に実装。`WorkshopStoreProtocol`へ
`get_trial_end_notified_at`/`set_trial_end_notified_at`追加、`process_generation_request`が
`GenerationRequestResult.trial_end_notification_due`を返すようにした。新規テスト3件追加、
venture全体291件・schema検証27件いずれもパス。(B)経路本体・実プッシュ送信配線は次の課題)
