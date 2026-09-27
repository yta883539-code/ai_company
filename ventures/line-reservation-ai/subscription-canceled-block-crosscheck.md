# 解約確定時の新規予約ブロックに関する横断確認(kura-pashaフェーズ188系の横展開)

## 経緯

kura-pasha(フェーズ188)・course-set-pasha(フェーズ258)・aircon-pasha(フェーズ275)では、
「生成可否判定がトライアル終了判定・決済失敗判定という既存の2判定のみに委ねられており、
解約確定(`customer.subscription.deleted`)という終端イベント専用の分岐が無かったため、
既に有料転換済み・決済失敗未経験のユーザーが解約後も生成を使い続けられてしまう」という
共通パターンの欠落が発見・修正された。

kura-pashaフェーズ187時点では、line-reservation-aiは「該当する統合ハンドラ自体が未実装のため
対象外」と記録されていた。以降line-reservation-ai側でも
`cloud_function_subscription_cancelled_webhook.py`が実装され状況が変わったため、
aircon-pashaフェーズ275の「次回候補」に沿って本ventureへの横展開確認を再実施した。

## 確認結果: 該当する欠落は無い

line-reservation-aiの新規予約受付可否判定は、他venture(kura-pasha等)のような
「トライアル終了フラグ」「決済失敗フラグ」という**複数の独立したブール値/タイムスタンプの
組み合わせ**ではなく、店舗ごとに1つだけ持つ`suspension_reason`という**単一のenum的フィールド**
(値: `None`/`"payment_failed"`/`"payment_suspended"`/`"cancelled"`)で一元管理されている。

- 新規予約のブロック判定は`cloud_function_process_event.py`の`_start_new_booking()`・
  `_handle_candidate_selection()`・`_handle_details()`のいずれも
  `store_profile.get_suspension_reason(store_id)`を直接参照し、`None`以外なら
  `new_booking_blocked_suspended`を返す設計(値の種類を判定に使っていない)。
- `cloud_function_subscription_cancelled_webhook.py`の`classify_subscription_deleted()`は、
  既に`"cancelled"`なら`already_cancelled`、`"payment_failed"`(dunning側管轄)なら
  `out_of_scope_payment_failed`として関与しないが、それ以外(`None`または`"payment_suspended"`)
  の場合は無条件に`OUTCOME_CANCELLED`を返し`suspension_reason`を`"cancelled"`へ書き換える。

すなわち、line-reservation-aiにはpasha系ventureが抱えていた「解約確定という終端イベントが
専用分岐を持たず既存判定に紛れて扱われない」という構造そのものが存在しない
(独立フラグの組み合わせではなく単一フィールドの排他的なenum遷移として設計されているため、
解約確定時に他の判定に委ねてしまう余地がない)。よって「既に有料転換済み・決済失敗未経験の
ユーザーが解約後も新規予約を使い続けられる」という同型の欠落は発生し得ないと判断した。

なお`trial_start_at`(pasha系の「トライアル期間」に相当しうる概念)は本ventureでは
利用実績レポート送信タイミングの算出にのみ使われ(`trial-end-scheduler-design.md`)、
`engine.py`のいずれの予約受付判定にも一切参照されていないことも確認した
(コード上grep該当なし)。したがって「トライアル終了判定への意図しないフォールバック」の
経路自体が存在しない。

## 結論・次回候補

コード変更は行わず、確認・文書化のみ(pasha系で見つかったパターンの欠落は本ventureには
存在しないことの確認)。テスト結果に変化は無い(venture全体870件・schema検証28件、
いずれもパス、変更前と同じ)。承認が必要なアクション(支払い・アカウント作成・外部公開・
送信等)は今回発生していないためpending-approval.mdへの追記なし。

次回候補: (1)候補longlist-draft.md優先度B候補(9・11・1・10・17)のオーナー回答待ち状況の
再確認、(2)他venture(course-set-pasha・kura-pasha・aircon-pasha)に候補提示・確定までの
複数ターン継続フロー自体が存在するかの横断確認、(3)他venture・アイデア領域の前進。
