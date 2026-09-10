# 月間生成回数の上限接近時通知 設計

pricing-plan.md「月間生成回数の上限超過時の挙動(仮決め)」の「通知: 上限到達が近づいた
時点(残り1回等)で事前に知らせる通知設計は実装時の課題として残す」、および
checkout-initiation-flow-design.md 2節(a)「トライアル終了が近づいた際の通知メッセージ内の
案内文(aircon-pasha/limit-approaching-notification-design.md相当を本venture向けに設計する
必要があるが、本ドキュメントの範囲外)」に残っていた課題に着手する。

## 1. aircon-pashaの設計をそのまま流用できない理由

aircon-pasha/limit-approaching-notification-design.mdは「残り5回」を閾値としていたが、これは
aircon-pashaの利用ペース(1日3〜5件、月60〜100件)を前提にした値であり、本venture
(pricing-plan.mdより月3回/8回/20回)にそのまま適用すると閾値自体がプラン上限を超えてしまう
プランが生じる(ライトプラン月3回に対して「残り5回」は成立しない)。

course-set-pasha/limit-approaching-notification-design.md(月8〜30回、閾値「残り2回」)の方が
利用頻度の桁は近いが、本ventureのライトプラン(月3回)には「残り2回」でも早すぎる
(利用開始直後の1回目生成で即座に通知が届いてしまう)。本venture固有の低頻度
(pricing-plan.md「1件あたりの制作期間が長く、月あたり数件〜十数件程度」)を踏まえ、
閾値は独自に「残り1回」として再設計する(pricing-plan.md本文が仮置きしていた値と一致)。

## 2. 通知トリガー・閾値

- **閾値は3プラン共通で「残り1回」とする。** すなわち`count_after_increment ==
  monthly_limit - 1`となった生成完了時点で1回通知する。
  - ライトプラン(月3回): 2回目の生成完了時点で通知。
  - スタンダードプラン(月8回): 7回目の生成完了時点で通知。
  - 複数職人プラン(月20回): 19回目の生成完了時点で通知。
- 「残り1回」を採用した理由: 本venture固有の低頻度利用(月3〜20回、aircon-pashaの
  月60〜100回・course-set-pashaの月8〜30回と比べて一桁少ない)では、aircon-pasha同様の
  「猶予日数」ではなく「猶予件数」で考えるべきであり、月3回という最小プランでも成立する
  最も早い閾値は「残り1回」(2回目終了時点)である。これより早い「残り2回」(1回目終了
  時点)ではライトプラン利用者に対して初回生成の直後に通知が届いてしまい、体験を損なうと
  判断した。
- **通知は1回のみとする。** course-set-pasha・aircon-pashaと同じ理由(生成のたびに毎回
  通知が挟まると通常の返信〈受注内容整理メモ・納品案内下書き・お手入れ案内下書き〉の
  可読性を損なう)により、「残り1回」到達時の1回のみとし、実際に上限を超えた場合は
  超過時点の返信メッセージ自体に従量課金が発生する旨を1文添える方式(3節)でカバーする。
- **送信方法はaircon-pasha・course-set-pashaを踏襲する。** 新規のプッシュメッセージは送らず、
  該当回の生成完了時の返信メッセージ(通常のreply API応答)に追記する形で実現し、追加の
  API呼び出し・課金を発生させない。

## 3. 通知文言案(仮)

生成完了時の通常の返信メッセージ末尾に、該当条件のときのみ以下を追記する
(`format_trial_end_notification_message`と同様、実装は純粋関数として切り出す)。

- 残り1回に達した時点(プランごとに2回目/7回目/19回目の生成完了時):
  「※今月の生成回数は残り1回です(上限到達後は1回あたり[単価]円の追加料金がかかります)」
- 上限を超えて従量課金が発生した回(超過1回目以降)の返信メッセージ末尾:
  「※今月の無料生成回数の上限を超えたため、本回は追加料金[単価]円が発生します」

いずれも1文の定型文言とし、aircon-pasha・course-set-pashaと同様、post_generation_checks.py
相当の機械チェック対象(厳守事項の違反検知)には含めない(課金案内であり、厳守事項が対象と
する「受注内容整理メモ・納品案内・お手入れ案内の内容そのもの」とは性質が異なる運用
メッセージのため)。単価(`overage_price_jpy`)は`usage_counter_workshop.PLAN_LIMITS`から
プランごとの値(250円/200円/150円)をそのまま埋め込む。

## 4. 実装方針

`prototype/usage_counter_workshop.py`の`check_and_increment_usage()`が既に返す
`UsageCheckResult`(`count_after_increment`・`monthly_limit`・`overage_price_jpy`を保持)を
そのまま入力とする純粋関数`format_limit_approaching_notice(usage: UsageCheckResult) ->
Optional[str]`を`prototype/cloud_function_webhook.py`に新設する
(`format_trial_end_notification_message`と同じ配置方針)。

- `count_after_increment == monthly_limit - 1`の場合: 2節の「残り1回」文言を返す。
- `count_after_increment > monthly_limit`の場合: 2節の超過文言を返す。
- それ以外の場合: `None`を返す(呼び出し側は追記しない)。
- `monthly_limit <= 1`(現行3プランには存在しないが将来プラン追加時の防御)の場合、
  `monthly_limit - 1 == 0`または負になり得るため、`count_after_increment ==
  monthly_limit - 1`の判定は`monthly_limit - 1 >= 1`を満たす場合のみ有効とする
  (0回目や負の回数で「残り1回」通知が誤発火しないためのガード)。

`process_memo_event()`(usage_counter_store等3依存が揃っている場合のみ実行される
`process_generation_request()`呼び出しブロック)で`generation_result.usage`を保持し、
最終的な返信文組み立て後、`trial_end_notification_due`の付記と同様の位置で
`format_limit_approaching_notice(generation_result.usage)`の結果を(Noneでなければ)
末尾に追記する。トライアル終了通知(`trial_end_notification_due`)と本通知は判定条件が
独立している(トライアル終了通知は生涯最初の生成1回目のみ、本通知は残り1回到達時のみで
現行プラン〈月3回以上〉では原理的に同一回で重複しない)ため、両方が真になった場合は
両方を追記する設計とする(重複を避ける特別な排他処理は設けない)。

## 5. 今後の課題

- 「残り1回」という固定閾値の妥当性は机上の想定に基づく仮説であり、実LLM接続・実運用
  データが取れた段階で再検証する必要がある(aircon-pasha 6節と同じ位置づけ)。
- 決済代行サービス側の都度課金対応可否確認(pricing-plan.md未確定事項)が完了した段階で、
  3節の「追加料金[単価]円」の具体的な請求タイミング(即時課金か翌月合算請求か)を通知文言に
  反映する。
- トライアル期間中(有償契約が未確定な状態)でもcheck_and_increment_usageは仮設定された
  plan_id(craftsman-account-linking-design.md「最安プランで仮設定」)に基づき加算される
  既存の挙動があり、トライアル中に「残り1回」通知が届くケースが起こりうる。この場合、
  文言中の「上限到達後は追加料金」という表現がトライアル中のユーザーには正確でない
  (実際にはトライアル終了・有償契約が別途必要)可能性があるが、本ドキュメントでは
  対象外とし、実運用データが得られた段階で文言の出し分けが必要か再検討する。

最終更新: 2026-09-10 21:00 UTC
