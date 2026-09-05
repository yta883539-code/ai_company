# 前日リマインド配信ブロック検知によるオーナーへの早期無断キャンセルリスク通知

作成日: 2026-09-05

## 位置づけ

follow-unfollow-event-handling-design.mdの「残課題」に残っていた
「顧客がunfollowした後にリマインド送信(`_send()`/`send_reminders()`)が失敗し続ける
ケースを、no-show-handling.mdの無断キャンセルリスク判定シグナルとして活用できないか」
に対応する。

no-show-handling.mdの現行の検知条件は「予約時間を過ぎても来店済み操作がない」ことが
起点であり、**来店予定時刻を過ぎるまでオーナーには何も伝わらない**。一方、前日リマインドが
LINEのブロック(unfollow)によって配信不能であることは前日の時点で判明しており、これは
「顧客が来店しない可能性がある」ことを示す先行シグナルとして使える。本ドキュメントは、
この先行シグナルを既存の無断キャンセル運用に追加する設計を行う(既存のno-show-handling.md
自体の検知条件・記録項目は変更しない。あくまで「予約時間より前に」オーナーへ一次情報を
届ける追加のチャネルを新設するもの)。

## なぜ既存の`LinePushDeliveryError`(失敗一律)では不十分か

`api-call-failure-handling.md`の`LinePushDeliveryError`は、5xx・レート制限429・ネットワーク断等の
**送信自体の失敗全般**を表す例外で、`send_reminders()`は失敗時に`reminder_sent_at`を更新せず
次回Cloud Scheduler起動(15分間隔)で自然に再試行する設計になっている。この設計は一時的な
障害には正しいが、LINEのブロック(またはLINE公式アカウントの削除)による配信不能は
**顧客が能動的に関係を断っている限り解消しない**ため、15分ごとに際限なく再試行してもいずれも
失敗に終わる。かつ、この「ブロックによる配信不能」こそが無断キャンセルリスクの先行シグナル
として価値があるにもかかわらず、一律の`LinePushDeliveryError`のままではこの2つ
(一時障害 / ブロック)を区別できず、オーナーへ知らせる判断材料にならない。

## 設計

### 1. 新しい例外`LinePushBlockedError`

`cloud_function_process_event.py`に`LinePushBlockedError(LinePushDeliveryError)`を
新設する。LINE Messaging APIのpush送信がブロック・未フォロー(「the user hasn't added
the LINE Official Account as a friend」等)を理由に失敗した場合、実クライアント側でこの
例外に変換して送出する想定(既存の`line-bot-sdk`等が返すエラーレスポンスのステータス・
エラーコードから判定する変換処理は、実LINE API接続実装時の課題として残す)。

`LinePushDeliveryError`のサブクラスにすることで、既存の`except LinePushDeliveryError`で
一律に捕捉している箇所(`ConversationEventProcessor._send()`等)の挙動は一切変更されず、
後方互換を保つ。`send_reminders()`側でのみ`LinePushBlockedError`を先に捕捉することで
区別する。

### 2. `send_reminders()`(Cloud Function C)での扱い

初回リマインド送信(`select_due_initial_reminders()`の対象)で`LinePushBlockedError`を
捕捉した場合:

- 従来通り`reminder_sent_at`は更新しない(`failed`に計上する点も同じ)。ブロックが
  一時的なものである可能性(顧客が後で自らブロック解除する)を排除しないため、
  15分ごとの再試行自体は止めない。
- 追加で、**オーナーへの通知が未送信の場合のみ**(`reminder_blocked_owner_notified_at is None`)、
  `stores[store_id].owner_line_user_id`宛に`format_reminder_blocked_owner_notice()`
  (engine.py新設)で組み立てた一次情報通知を1回だけ送る。送信できたら
  `reminder_blocked_owner_notified_at`にタイムスタンプを記録し、以後の15分間隔の
  再試行では再通知しない(15分ごとに何十通も届くと運用上のノイズになるため)。
- オーナー通知自体の送信が失敗した場合は`reminder_blocked_owner_notified_at`を更新せず、
  次回起動時に自然に再試行される(reminder-scheduler-design.mdの冪等性設計と同じ考え方)。
- `owner_line_user_id`が店舗設定として未登録の場合は、静かにスキップする
  (cloud_function_process_event.pyの`owner_user_id`未設定時の既存方針と同じ)。

再送(`select_due_resends()`対象)では追加通知を行わない。初回リマインドの時点で
既に1回通知済みのため、当日朝の再送でブロックが再検知されても二重通知にしかならない。

### 3. 通知文面(`format_reminder_blocked_owner_notice()`、engine.py新設)

no-show-handling.mdの通知文言(催促ではなく事実通知、過度に顧客を追及しない)と同じ
トーンを踏襲する。顧客名は本システムでは保持していない(LINEのuser_idのみ)ため、
予約日時・メニューで予約を特定できるようにする。

```
【要確認】明日{candidate_label} {menu}のご予約について、前日リマインドをお届け
できませんでした(LINEのブロック・削除の可能性があります)。ご来店の意思を
お電話等の別経路でご確認いただくことをおすすめします。
```

トーン(formal/standard/casual)による出し分けは行わない。本通知はオーナー向けの
事実通知であり、顧客向けメッセージ(`format_reminder_message()`等)のような
接客トーンの使い分けは不要と判断した(`format_escalation_notification()`と
同じ扱い)。

### 4. データモデルへの追加

- `reminder_scheduler.ReminderBooking`に`reminder_blocked_owner_notified_at:
  Optional[datetime] = None`を追加(冪等性フラグ)。
- `reminder_scheduler.StoreReminderConfig`に`owner_line_user_id: str = ""`を追加。
  firestore-data-model.mdの`stores/{storeId}`には既に`ownerUserId`相当のフィールドが
  存在する前提(cloud_function_payment_webhook.pyの`StoreDunningState.owner_line_user_id`と
  同じ値を指す想定)。

## 意図的に含めなかったもの

- ブロック検知を理由にした予約の自動キャンセル・自動フラグ付け(no-show-handling.mdの
  既存方針「最終確定はオーナー自身が行う」を踏襲し、あくまで一次情報の通知に留める)。
- no-show-handling.mdの「累計無断キャンセル数」等の顧客詳細画面への表示項目への統合
  (本シグナルは「リマインドが届いたかどうか」であり「無断キャンセルが確定したか」とは
  別の情報のため、混同を避けるためオーナー向け設定画面への反映は別課題として残す)。
- `reminder_blocked_owner_notified_at`のクリア配線(顧客が再フォローした場合に
  リセットするか等)。blocked-but-billing-owner-notification-design.mdで同種の
  冪等性フラグに対して行ったクリア配線と同じパターンが適用できると見込まれるが、
  実装は次回以降の課題として残す。

## 次の課題

- `owner_line_user_id`未設定時に静かにスキップする挙動は、他のオーナー通知経路
  (cloud_function_process_event.pyの`owner_user_id`)と設定元が重複している。
  実Firestore接続時に、店舗ドキュメントの同一フィールドを両経路で参照するよう
  実装を揃える必要がある(現時点ではいずれも未接続のプロトタイプ段階のため実害なし)。
- 実LINE APIクライアントでの`LinePushBlockedError`への変換処理(エラーコード判定)自体は
  実装未着手(オーナー承認待ちのLINE公式アカウント開設後の課題)。
