# suspension_reasonによる新規予約受付停止の実配線設計

作成日: 2026-09-26(フェーズ続き274)

## 背景

subscription-cancellation-flow-design.md「未確定事項・残課題」(2026-09-26 09:00 UTC時点)が
指摘していた通り、`suspension_reason`(なし/`trial_unselected`/`payment_failed`/
`payment_suspended`/`cancelled`)は`store_profile_store.py`に保存されているものの、
これを実際の「新規予約受付を停止する」という顧客向け自動応答の分岐に読み込ませる配線
(`cloud_function_process_event.py`側)はどの休止要因についても未実装だった。
owner-settings-wireframe.md「4節へのsuspension_reason分岐の反映」・subscription-
cancellation-flow-design.md 2節はいずれも状態遷移・画面表示・値の意味付けの設計にとどまり、
実際に顧客からのnew_booking intentをブロックする実装は本フェーズまで存在しなかった
(この欠落は本venture固有ではなく、aircon-pasha・kura-pasha・course-set-pashaの
プロセッサ側にも共通して残っている。他venture分は別途の課題として残す)。

## 対応表(owner-settings-wireframe.md 4節を正とする)

| `suspension_reason` | 新規予約受付 | 本フェーズでの扱い |
|---|---|---|
| なし | 継続 | ブロックしない |
| `payment_failed`(猶予期間中) | 継続 | ブロックしない |
| `payment_suspended`(制限モード) | 停止 | ブロックする |
| `trial_unselected`(休止モード) | 停止 | ブロックする |
| `cancelled`(解約済み、subscription-cancellation-flow-design.md 2節) | 停止 | ブロックする |

## 実装

`cloud_function_process_event.py`の`ConversationEventProcessor._start_new_booking()`冒頭に
ガードを追加した。

- `SUSPENSION_REASONS_BLOCKING_NEW_BOOKING = frozenset({"trial_unselected",
  "payment_suspended", "cancelled"})`(上表の「停止」3値)。
- `_is_new_booking_blocked_by_suspension()`: `store_profile`が未指定(`None`、既存呼び出し元
  への後方互換)の場合は常に`False`。それ以外は`get_suspension_reason(store_id)`が上記
  frozensetに含まれるかで判定する。
- ブロック時は`SUSPENDED_NEW_BOOKING_MESSAGE`(「現在新規のご予約受付を一時的に停止して
  おります。恐れ入りますが、ご予約に関しては店舗まで直接お問い合わせください」)を送信し、
  `DispatchResult(action="new_booking_blocked_suspended", detail=suspension_reason)`を返す。
  会話状態(`ConversationFlowStateMachine`)は変更しない(stageはブロック前のまま)。

### change_context=Trueの場合はブロックしない(重要な例外)

`_handle_change()`は`change`intentの処理で、旧予約が実際に解放された場合
(`released_old_booking`、stageが`awaiting_details`/`confirmed`だった場合)、`_start_new_booking()`
を`change_context=True`で呼び出し、そのまま新規候補検索へ接続する(change-intent-handling-
design.md準拠)。この経路では**suspension_reasonに関わらずブロックしない**設計とした。

理由: `_handle_change()`は`_start_new_booking()`を呼ぶ前に既に旧予約枠を解放済みである。
ここでブロックすると、顧客は「旧予約は取り消し済み・新予約も受け付けてもらえない」という
どちらの予約も持たない状態に陥ってしまい、owner-settings-wireframe.md 4節が言う
「既存確定予約とリマインドは継続」(休止モード中でも既存の確定予約自体は保護する)という
方針と矛盾する。既存確定予約の「変更」はこの方針の対象内(保護すべき既存関係)であり、
「新規」予約の対象外と整理した。

`released_old_booking=False`(旧予約が実体として存在しなかった、例: `candidates_presented`
段階からのchange)の場合は`change_context=False`のまま渡されるため、通常の新規予約と
同じくブロック対象になる。これは意図通り(失うべき既存予約が無いため、通常のnew_bookingと
同じ扱いで問題ない)。

## テスト

`test_cloud_function_process_event.py`に`SuspendedNewBookingBlockTests`(7件)を追加した。

- `trial_unselected`/`payment_suspended`/`cancelled`の3値それぞれで新規予約がブロックされ、
  `SUSPENDED_NEW_BOOKING_MESSAGE`が送信され、会話stageが進まないことを確認。
- `payment_failed`(猶予期間中)・`suspension_reason`なし・`store_profile`未指定(`None`)の
  3パターンでは従来通りブロックされず`candidates_presented`まで進むことを確認。
- 確定済み予約をchange(解約済み状態で変更)した場合、`change_context=True`のため
  suspension_reasonに関わらず新規候補検索が続行されることを確認。

回帰確認: venture全体863件(`python3 -m unittest discover -s prototype -p "test_*.py"`、
変更前856件+新規7件)・schema検証28件(`python3 schema/validate_test_cases.py`)いずれもパス。

## 今回のスコープに含めなかったもの・次の課題

- 本フェーズはLINEの実際の1対1トーク(`ConversationEventProcessor`)の新規予約フローのみを
  対象とした。`owner_faq_router.py`等、他の応答経路への同種の配線が必要かどうかは未確認
  (FAQは予約フローそのものではないため優先度は低いと考えられるが、次回以降の棚卸し候補とする)。
- 他venture(aircon-pasha・kura-pasha・course-set-pasha)のプロセッサ側は同種の未配線が
  残ったままである(各venture固有の予約フロー実装への横展開は別途の課題として残す)。
- コード変更のみで、実際のFirestore・LINE公式アカウントとの接続(オーナー承認待ち)には
  影響しない。承認が必要なアクションは今回発生していないためpending-approval.mdへの
  追記はなし。
