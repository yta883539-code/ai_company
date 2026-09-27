# リマインダースケジューラーがsuspension_reasonを参照しないことの妥当性確認

## 経緯

`prototype/reminder_scheduler.py`(前日リマインド・再送の送信要否判定を担うモジュール)を
確認したところ、`StoreReminderConfig`・`ReminderBooking`のいずれのdataclassにも
`suspension_reason`フィールドが無く、判定ロジック内でも一度も参照していないことに気づいた。
新規予約受付のブロック判定(`_start_new_booking()`等)・休止モード再通知
(`dormant_mode_scheduler.py`、10箇所で参照)・decision-failureリマインド
(`dunning_notification_scheduler.py`)はいずれも`suspension_reason`を参照する設計に
なっているのに対し、リマインダースケジューラーだけが参照していない非対称な状態に見えたため、
記載漏れ(欠落)かどうかを確認した。

## 確認結果: 記載漏れではなく、設計方針どおりの意図的な独立

`subscription-cancellation-flow-design.md` 1節の表、および
`billing-upgrade-flow-design.md` 4節の休止モード方針はいずれも、
「新規予約受付は停止するが、**既存の確定済み予約と前日リマインドは継続する**」ことを
明記している。

- `suspension_reason`が`"trial_unselected"`(休止モード)・`"payment_failed"`
  (決済失敗)・`"payment_suspended"`・`"cancelled"`(解約確定)のいずれの値であっても、
  この方針は共通(値の種類によらず「新規予約受付のみ止める」という一律の扱い)。
- リマインドは来店客が既に確定させた予約に対する送客対応であり、店舗側の支払い状態・
  解約状態とは独立した「来店客との約束を守るための通知」という性質を持つため、
  `suspension_reason`を判定条件に含めないことがそもそもの設計意図である。
- したがって`reminder_scheduler.py`が`suspension_reason`を一切参照しないのは実装漏れでは
  なく、上記の設計方針を正しく反映した結果であると確認した。

参考として、`dormant_mode_scheduler.py`が`suspension_reason`を参照しているのは、
リマインド送信の可否判定のためではなく、休止モード中のオーナー自身への再通知
(dormant-mode-renotification-design.md)という別目的のためであり、両者は矛盾しない。

## 結論

本件はコード変更を要しない。設計と実装の整合を確認できたのみのため、
venture全体のテスト件数(`python3 -m unittest discover -s prototype -p "test_*.py"`
870件、`python3 schema/validate_test_cases.py` 28件)に変化はない。
