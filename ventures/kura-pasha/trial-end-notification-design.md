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
  発言した場合のみを扱う)であるため、本ドキュメントでは机上設計にとどめ、実際の
  postbackイベント処理配線は次の課題として残す。

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

## 5. 実装への影響メモ(設計のみ、実装は次回以降)

- `WorkshopStoreProtocol`(prototype/usage_counter_workshop.py)へ
  `get_trial_end_notified_at`/`set_trial_end_notified_at`の2メソッド追加が必要になる
  想定(2節の二重送信防止フラグ)。命名は既存の`get_payment_failure_detected_at`/
  `set_payment_failure_detected_at`(フェーズ56)と同じスタイルを踏襲する。
- (A)経路は`process_generation_request()`内、`trial_generation_used`をFalse→Trueへ
  更新した直後に通知要否を判定する分岐を追加する想定。
- (B)経路は本venture側にまだ存在しない日次スケジューラ本体の実装が前提となる(6節参照)。
- テスト(`prototype/test_usage_counter_workshop.py`)では、(A)経路の通知要否判定
  (`trial_generation_used`が今回の呼び出しで初めてTrueになった場合のみ通知対象と
  判定し、2回目以降の生成では判定しないこと)を中心に検証する方針とする。実装自体は
  本フェーズでは着手しない。

## 6. 今後の課題

- (B)期間到達判定用の日次スケジューラの選定ロジック・構成(line-reservation-ai/
  reminder-scheduler-design.md・aircon-pasha/trial-end-scheduler-design.md相当)は
  本venture未着手。本venture固有の低頻度受注特性(候補workshopの多くは(A)経路で
  完結し(B)経路の発生頻度自体が低いと見込まれる)を踏まえ、他venture(高頻度利用が
  前提)ほどの優先度は無いと判断し、次の課題として残す。
- 2節の`trial_end_notified_at`フラグ・(A)経路の通知要否判定処理の実コード実装
  (`prototype/usage_counter_workshop.py`)は次の課題として残す。
- 3節の通知メッセージからの直接ボタン起動(postbackイベント処理)の配線は
  checkout-initiation-flow-design.mdの対象外であるため、別途の設計・実装が必要
  (次の課題として残す)。
- 実際のCloud Scheduler実行環境の構築、LINE公式アカウント接続・Stripe接続はいずれも
  オーナー承認待ちの範囲(pending-approval.md参照)。本ドキュメントはメッセージ文言・
  トリガー条件の机上設計にとどめる。

最終更新: 2026-09-09 08:00 UTC(フェーズ59: トライアル終了通知メッセージをcontent-
generation-time-estimate.md〈フェーズ18〉の20分試算を用いて設計。(A)生涯最初の生成完了
経路と(B)30日期間到達経路の二重トリガー・二重送信防止方針を確定。実コード実装・日次
スケジューラ本体は次の課題として残る)
