# 月間予約件数の上限接近通知 設計

作成日: 2026-09-03

## 背景

pricing-plan.mdはスタータープラン(〜50件/月)・スタンダードプラン(〜150件/月)・
プロプラン(〜300件/月)を「想定予約件数上限目安」として定義済みだが、実際に店舗の
月間予約確定件数がこの目安へ近づいた・達した際にオーナーへ知らせる仕組みは未設計のまま
README.md「次にやること」に残っていた(aircon-pasha/course-set-pashaの
limit-approaching-notification-design.mdに相当する検討が本ventureには存在しなかった)。
両venture(月間生成回数の上限)とは異なり、本ventureの「上限」は生成回数ではなく
「月間予約確定件数」(pricing-plan.mdの想定予約件数上限目安)である点が対象の違いだが、
「利用量が店舗のプラン想定を超えつつあることを、超過前にオーナーへ知らせる」という
目的・通知の位置づけは同じであるため、両ventureの設計・実装パターンを踏襲する。

## 1. 他ventureの設計をそのまま流用できない点

- course-set-pasha/aircon-pashaは「LLM生成1回」を単位にカウントし、閾値到達時の
  生成完了返信メッセージ(顧客向け)に注記を追記する方式だった。本ventureで同じ場所
  (`format_confirmation_message()`、顧客向け予約確定メッセージ)に「プラン上限が
  近い」旨を書き加えるのは不適切(プランや料金の話は店舗オーナーの関心事であり、
  予約した顧客に伝える情報ではない)。そのため本ventureはfirst-booking-self-check-
  notification-design.mdと同じ「オーナー宛の追加メッセージを別送する」方式を採用する。
- 本ventureの`ConversationFlowStateMachine`は1インスタンス=1店舗を前提とする設計
  (first-booking-self-check-notification-design.md「残課題」参照)のため、
  store_id単位の辞書は不要で、月キー(`YYYY-MM`)のみで足りる(インスタンス自体が
  既に店舗を表す)。

## 2. カウントの対象・タイミング・月の区切り

- カウント対象は`provide_details()`が`confirm()`成功で`confirmed`へ遷移した回数
  (=予約確定処理を行った回数)。キャンセル・変更で後から取り消されても、その月の
  カウントからは減算しない(aircon-pasha/course-set-pashaの「サービスを実際に使って
  処理した回数」という利用実績の考え方を踏襲。`InMemoryBookingRecordStore.
  count_confirmed_bookings()`の考え方と同じ)。
- 月の区切りは他venture同様JST基準の暦月(`YYYY-MM`)とする(market-research.mdの
  対象が日本国内の個人事業主のため)。`provide_details()`の`now`引数がJST時刻である
  前提は、trial_start_at等の既存フィールドと同じ(本venture一貫の前提)。
- 既存の`InMemoryBookingRecordStore.count_confirmed_bookings()`(累計・店舗生涯)とは
  別に、`ConversationFlowStateMachine`側に月別カウンタを新設する(record_store未指定
  でも本機能が動くようにするため。trial判定用カウントとは目的・ライフサイクルが異なる)。

## 3. 通知トリガー・閾値

- aircon-pashaの固定閾値(プラン上限−5件)方式を踏襲する。course-set-pashaのように
  プランごとに異なる閾値ではなく、3プラン共通で「残り5件」時点で通知する
  (aircon-pasha同様、月内の利用ペースが閾値到達から上限到達までの間に予約が
  積み増しされやすい業態のため、早めの一律閾値とする)。
  - スタータープラン(50件): 45件目の確定時点で通知。
  - スタンダードプラン(150件): 145件目の確定時点で通知。
  - プロプラン(300件): 295件目の確定時点で通知。
- 通知は月内1回のみ(閾値到達の確定時に1回)。月が変わればカウンタ・通知済みフラグ
  ともにリセットされ、翌月また閾値到達時に1回発火する(first_booking_self_checkが
  店舗生涯で1回きりなのとは異なり、こちらは「暦月ごとに1回」である点が差分)。
- 上限を超えた場合の追加課金・予約受付停止は本設計の対象外とする。pricing-plan.mdの
  現行プラン表は「想定予約件数上限目安」であって明確な従量課金・打ち切りルールを
  定めていないため(course-set-pasha/aircon-pashaの生成回数上限とは異なり、予約自体を
  拒否するとその場で来店機会を逃す=店舗の売上機会損失に直結するため、上限超過時に
  自動で予約を止める設計は本venture向けではないと判断)。上限超過時の具体的な運用
  (プランアップグレードの提案のみに留めるか、追加料金を課すか)は、この通知を受けた
  オーナーが人手で判断する運用とし、機械的な制御は行わない。

## 4. 実装

`prototype/engine.py`の`ConversationFlowStateMachine`に以下を追加した。

- `__init__`に`monthly_booking_limit: Optional[int] = None`引数を追加(既定None=機能無効、
  後方互換)。店舗のプラン上限件数を渡す。plan_store等プランをstore_profile_store.pyから
  取得する配線自体は次回以降の課題(6節参照)。
- `_monthly_confirmed_counts: dict[str, int]`(月キー→件数)、
  `_monthly_booking_limit_notice_pending: bool`を新設。
- `provide_details()`の確定成功分岐で、`monthly_booking_limit`が指定されていれば
  `now`のJST月キーでカウントを1件増やし、増加後の件数が
  `monthly_booking_limit - MONTHLY_BOOKING_LIMIT_NOTICE_MARGIN`(=5)と一致した瞬間のみ
  `_monthly_booking_limit_notice_pending`をTrueにする(超えた後は再セットしないため
  月内1回のみ)。
- `consume_monthly_booking_limit_notice() -> bool`を新設。first_booking_self_checkと
  同じ「一度だけ消費してTrueを返す」パターン。
- `get_monthly_confirmed_count(month: str) -> int`を新設(通知文言の組み立て・テスト用)。
- `format_monthly_booking_limit_notice_message(plan_limit: int, current_count: int) -> str`を
  新設。escalation-notification-templates.mdの「オーナー向け通知は主語をAI/システムにして
  よい」規約に従った固定文面(トーン別出し分けなし)。

```
【ご確認のお願い】今月のご予約確定件数が{current_count}件になりました(現在のプラン上限目安:
    {plan_limit}件)。上限に近づいていますので、プランの見直しが必要かご確認ください。
```

- テスト(`prototype/test_engine.py`)を4件追加:
  - 上限−5件目の確定で`consume_monthly_booking_limit_notice()`がTrueを返し(それより前の
    確定では発火しないことも同一テスト内で確認)、消費後は同月中Falseのままであること。
  - `monthly_booking_limit`未指定(None)では発火しないこと(後方互換)。
  - 月をまたぐと(`now`の月キーが変わると)カウンタが`get_monthly_confirmed_count()`上も
    リセットされ、翌月あらためて閾値到達時に発火すること。
  - 通知文言(`format_monthly_booking_limit_notice_message()`)に上限件数・現在件数が
    含まれること。

## 5. 通知経路との接続

first-booking-self-check-notification-design.md「残課題」と同様、`consume_monthly_
booking_limit_notice()`が返す通知をオーナーへ実際に送る配線(Cloud Function B側で
`provide_details()`成功直後にこれを呼び、Trueなら追加送信する)は、オーナー向け送信先
(LINE以外の経路も含めて未確定)自体が実LINE API接続(オーナー承認待ち)後の課題として
残る他のオーナー通知実装(first_booking_self_check含む)と合わせて未着手。

## 6. 今後の課題

- (解消済み 2026-09-04・フェーズ続き187: `monthly_booking_limit`が呼び出し側の直接値渡し
  にとどまっていた点のうち、store_profile_store.pyへの契約プラン保持フィールド
  (`get_plan`/`set_plan`)はフェーズ続き181で、その値から`monthly_booking_limit`を求める
  ヘルパー(`resolve_monthly_booking_limit()`)はフェーズ続き182で、実際に
  `ConversationFlowStateMachine`のコンストラクタへ渡す構築ヘルパー
  (`build_conversation_flow_state_machine_for_store()`)はフェーズ続き187で、それぞれ
  解消済み(詳細はcheckout-session-plan-selection-design.md「残課題」・
  conversation-flow-construction-design.md参照)。プラン変更(アップグレード/ダウングレード)
  時に`store_profile_store`側の値をどう更新するかは、checkout-session-plan-selection-
  design.md「残課題」に記載の別の残課題として引き続き残る。この構築ヘルパーを実際に
  どこから呼ぶか(会話状態の永続化・復元方式)は実Firestore接続後の課題として残る)
- 「残り5件」という固定閾値は、aircon-pashaの先例に倣った机上の仮決めであり、実際の
  予約ペース(繁忙期・閑散期の差など)を踏まえた妥当性検証は実運用データが取れてから
  行う。
- 上限超過後の運用(3節で機械的制御を見送ると決めた判断)は、実際に上限へ到達する店舗が
  出た段階で、オーナーの反応(プラン変更を希望するか、上限超過のまま使い続けたいか)を見て
  見直す。
