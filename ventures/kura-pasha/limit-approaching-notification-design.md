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
- ~~トライアル期間中(有償契約が未確定な状態)でもcheck_and_increment_usageは仮設定された~~
  ~~plan_id(craftsman-account-linking-design.md「最安プランで仮設定」)に基づき加算される~~
  ~~既存の挙動があり、トライアル中に「残り1回」通知が届くケースが起こりうる。この場合、~~
  ~~文言中の「上限到達後は追加料金」という表現がトライアル中のユーザーには正確でない~~
  ~~(実際にはトライアル終了・有償契約が別途必要)可能性があるが、本ドキュメントでは~~
  ~~対象外とし、実運用データが得られた段階で文言の出し分けが必要か再検討する。~~
  → フェーズ74(6節)で対応済み。

## 6. トライアル期間中の文言分岐(フェーズ74、2026-09-10 22:00 UTC)

5節に残っていた課題(トライアル期間中は「上限到達後は追加料金」という表現が不正確)に
対応する。

- **判定式**: `workshop_store.get_subscription_status(workshop_id) != "active"`を
  「トライアル中(有償契約が未確定)」の判定に使う。これは`process_generation_request()`が
  `TrialPeriodOverError`を送出するかどうかの判定式(`subscription_status != "active"`、
  usage_counter_workshop.py)で既に使われているものと同じ式であり、新しい状態フラグは
  追加しない。`subscription_status`の初期値は`"trialing"`(craftsman-account-linking-
  design.md「workshop作成時は最安プラン`"light"`で仮設定」と同時期に`"trialing"`のまま)
  であり、Checkout完了時に`stripe_webhook.handle_checkout_session_completed()`が
  `"active"`へ書き換えるまでの間は本判定により「トライアル中」として扱われる。
  `"past_due"`(既に有償契約済みで決済失敗中)は「トライアル中」に含めない
  (既に一度有償契約に至っているため、上限到達時の性質は「追加料金」に近い)。
- **文言の差し替え**: `is_trial=True`の場合、3節の「上限到達後は追加料金[単価]円」
  「本回は追加料金[単価]円が発生します」という表現を使わず、以下に差し替える
  (単価には一切触れない。トライアル中のplan_idはcraftsman-account-linking-design.md
  7節の通りあくまで仮設定であり、実際の従量課金額を保証する情報ではないため)。
  - 残り1回時: 「※トライアル期間中にご利用いただける生成回数は残り1回です
    (トライアル終了後も引き続きご利用いただくには有料プランへのお申し込みが必要です)」
  - 上限到達時: 「※トライアル期間中にご利用いただける生成回数の上限に達しました。
    引き続きご利用いただくには有料プランへのお申し込みが必要です」
- **実装**: `format_limit_approaching_notice(usage: UsageCheckResult, is_trial: bool)`に
  `is_trial`引数を追加し、`is_trial`の値で上記2種類の文言セットを出し分ける。呼び出し元の
  `process_memo_event()`は`generation_result.usage.workshop_id`から
  `workshop_store.get_subscription_status()`を呼び、結果を`is_trial`として渡す
  (追加のストア読み取りは発生するが、同一リクエスト内で既に`process_generation_request()`
  がstoreへアクセス済みのため新規の外部呼び出しは発生しない)。
- **範囲外(次の課題)**: 本フェーズはトライアル中かどうかで文言を出し分けるのみであり、
  トライアル終了通知(`format_trial_end_notification_message`・`TRIAL_END_QUICK_REPLY`)を
  本通知にも添付する(「▼ 有料プランへ進む」ボタンを本通知からも押せるようにする)ことは
  対象外とした。本通知は「残り1回」到達時点(生涯最初の生成とは独立したタイミング)で
  発火するため、ボタン添付を追加するには`process_memo_event()`側のquick_reply選択ロジック
  自体の拡張が必要であり、本フェーズのスコープ(文言の出し分けのみ)を超えると判断した。

## 7. トライアル中の本通知へのCTAボタン添付(フェーズ75、2026-09-11 00:00 UTC)

6節末尾で範囲外としていた課題(「有料プランへ進む」ボタンを本通知〈「残り1回」/上限超過〉
からも押せるようにする)に対応する。

- **対象**: `is_trial=True`の場合の本通知(6節の2種類の文言、「残り1回」到達時・上限超過時の
  両方)のみ。`is_trial=False`(既に有償契約済みで従量課金が発生するケース)は対象外とする。
  既に有償契約に至っているユーザーに対して「有料プランへ進む」ボタン(実体は
  `TRIAL_END_QUICK_REPLY`、`resolve_checkout_intent()`が処理する新規Checkout Session発行の
  導線)を提示するのは文脈として不自然であり、pricing-plan.mdが定めるプラン変更(アップ
  グレード/ダウングレード)導線とも役割が重複するため。
- **実装**: `process_memo_event()`側で`limit_notice`が`None`でなく、かつ`limit_notice_is_trial`
  (=`format_limit_approaching_notice()`呼び出し時に渡した`is_trial`)が`True`の場合、
  5.のトライアル終了通知(生涯最初の生成1回目)と同じ`TRIAL_END_QUICK_REPLY`を返信の
  quick_replyとして添付する。両条件(5.と本条件)は判定タイミングが独立しており
  (5.は生涯最初の生成1回目のみ、本条件は「残り1回」到達時のみ)、現行3プラン(月3回以上)
  では同一回で重複しないため、単純なor条件で足りる(重複時の排他処理は設けない)。
  返信結果には新規フィールド`MemoProcessResult.limit_notice_cta_attached`を追加し、
  本条件によってボタンが添付されたかどうかを`trial_end_notification_sent`と独立して
  追跡できるようにした。
- **範囲外(次の課題)**: 本フェーズはトライアル中の本通知へのボタン添付のみを扱う。
  トライアル期間中の仮plan_id(craftsman-account-linking-design.md 7節)に基づく通知文言・
  ボタン導線が、実際にCheckout完了後に選ばれたプランと異なる場合の整合性(例:仮設定の
  ライトプランで「残り1回」通知を受け取ったユーザーが、実際にはスタンダードプランで
  契約する場合の案内の齟齬)は未検証のまま残る。

最終更新: 2026-09-11 00:00 UTC(フェーズ75: 6節末尾の課題だったトライアル中の本通知への
CTAボタン添付に対応。`process_memo_event()`が`limit_notice_is_trial=True`の場合に
`TRIAL_END_QUICK_REPLY`を添付するようにし、`MemoProcessResult.limit_notice_cta_attached`を
新設した〈7節〉。既に有償契約済み〈`is_trial=False`〉の場合はボタンを添付しない)

## 8. 発見(フェーズ76、2026-09-11 01:00 UTC): 6〜7節のis_trial=True分岐は実際には到達不能

7節の「範囲外(次の課題)」を調査する過程で、6〜7節が実装した`format_limit_approaching_notice
(usage, is_trial=True)`の「残り1回」/上限超過の文言と、それに伴う`TRIAL_END_QUICK_REPLY`の
CTAボタン添付(7節)は、**実際にオンボーディングされたworkshopでは原理的に到達し得ない**
ことが判明した。

- `pricing-plan.md`「無料トライアル条件(仮)」が定めるトライアルは「初回の生成成功から
  1回無料、または30日間のいずれか早い方」であり、月間の複数回無料ではなく生涯1回のみ無料
  という条件である。
- `usage_counter_workshop.is_trial_period_over()`は、`trial_generation_used`が既に
  `True`(=生涯最初の生成が完了済み)であれば、経過日数を問わず即座に`True`を返す。
- `process_generation_request()`は`is_trial_period_over() and subscription_status != "active"`
  が真の場合、`check_and_increment_usage()`(=`UsageCheckResult.count_after_increment`を
  加算する処理、6節の「残り1回」/上限判定の入力元)へ到達する**前**に`TrialPeriodOverError`
  を送出する。`trial_generation_used`は1回目の生成が成功した直後に`True`へ更新される
  (`process_generation_request()`内、`check_and_increment_usage()`呼び出し後)。
- 一方、`workshop_linking.create_workshop_from_linking_code()`(実際のオンボーディング
  経路、craftsman-account-linking-design.md 7節)はworkshop作成時に必ず`trial_start_at`を
  明示的に設定する(未設定=安全側False、というのはデータ不整合時のフォールバックであり
  正常経路では発生しない)。

以上を組み合わせると、正常にオンボーディングされたworkshopは、`subscription_status`が
`"active"`になる(=Checkout完了)前は、**生涯最初の1回の生成にしか成功できない**。
2回目の生成リクエストは、`format_limit_approaching_notice()`へ到達する前に必ず
`TrialPeriodOverError`(→`TRIAL_PERIOD_OVER_NOTICE`、こちらも`TRIAL_END_QUICK_REPLY`を
添付済み)で遮断される。ライトプラン(月3回)を前提に「2回目=残り1回・4回目=上限超過」を
想定した6〜7節の文言・CTAボタンが実際に送信される機会は存在しない。

`test_process_memo_event_appends_trial_wording_when_subscription_not_active()`
(フェーズ74)・`test_process_memo_event_does_not_attach_cta_for_active_subscription_
limit_notice()`(フェーズ75)がこの矛盾に気付かなかったのは、いずれも`_make_stores()`が
返す素のstoreに対して`workshops.set_plan()`・`set_members()`のみを呼び、
`workshops.set_trial_start_at()`を一度も呼んでいなかったためである。この場合
`is_trial_period_over()`は`trial_start_at`未設定を理由に恒久的に`False`を返し続け、
本来はあり得ない「トライアル状態のまま4回連続で生成に成功する」状態を作り出してしまって
いた。実際のオンボーディング経路(`create_workshop_from_linking_code()`)を通した場合に
2回目で`TrialPeriodOverError`により遮断されることを
`test_process_memo_event_trial_limit_notice_is_unreachable_for_real_onboarded_workshop()`
として新規に追加し、この矛盾を再現・実証した(既存の2テストは削除していない。
`trial_start_at`未設定という「実際には起きない」状態を前提にしたテストとして残る)。

- **今回は対応しない(次の課題として残す判断)**: 本フェーズは矛盾の発見・実証に留め、
  6〜7節のコード(`format_limit_approaching_notice()`のis_trial分岐、
  `limit_notice_cta_attached`関連)自体の削除・トライアル条件の再設計は行わない。
  理由は、どちらの方向に直すべきかが`pricing-plan.md`のトライアル条件という製品判断に
  関わるため(a. 現状の「生涯1回無料」を維持するなら6〜7節のis_trial分岐は到達不能な
  デッドコードとして削除するのが妥当、b. 6〜7節を活かすなら「生涯1回無料」ではなく
  「トライアル期間中は各プランの月間上限まで無料」等にトライアル条件自体を変更する必要が
  ある)。オーナー判断または次フェーズでの方針決定を待つ。実害(誤った文言がユーザーに
  送信される等)は無い(到達不能なだけで誤動作はしていない)ため、緊急の修正は不要と
  判断した。

最終更新: 2026-09-11 01:00 UTC(フェーズ76: 6〜7節のis_trial=True分岐が、実際の
オンボーディング経路〈`create_workshop_from_linking_code()`が必ず`trial_start_at`を
設定すること〉と`is_trial_period_over()`〈生涯最初の生成完了で即トライアル終了〉の
組み合わせにより、現実には到達不能であることを発見・テストで実証した〈8節〉。
`pricing-plan.md`のトライアル条件(生涯1回無料)自体の見直しが必要かはオーナー判断待ちの
次の課題として残す)
