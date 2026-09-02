# follow/unfollowイベント受信時の扱い(フェーズ続き163)

作成日: 2026-08-31(フェーズ続き163)

## 背景・発見の経緯

aircon-pasha(follow-unfollow-event-handling-design.md、フェーズ109)・course-set-pasha
(follow-event-welcome-message-design.md・unfollow-event-handling-design.md、フェーズ80・84)
は、いずれもLINEの`follow`/`unfollow`Webhookイベントの扱いを既に設計・実装済みだが、
本ventureは一度もこれを設計していなかった(aircon-pashaフェーズ165の申し送り
「line-reservation-aiにも同種の未着手課題が残っている」で指摘済み)。

実際に`prototype/cloud_function_process_event.py`の`ConversationEventProcessor.process()`
(435行目〜)を確認すると、`event.get("source", {}).get("userId")`と
`event.get("message", {}).get("text", "")`のみを読んでおり、**`event.get("type")`を一度も
参照していない**ことが判明した。これは「`message`イベント以外はCloud Tasks段階で
そもそも来ない」という暗黙の前提に立っているように見えるが、そのような選別ロジックは
`cloud_function_webhook.py`の`handle_webhook_event()`(91行目〜)にも存在しない
(`webhookEventId`の有無と再配信フラグのみで判定し、イベント種別は一切見ずにそのまま
enqueueする)。したがって実際には`follow`/`unfollow`イベントもそのまま`process()`まで
到達し、`message`フィールドが無いため`reply_text=""`のまま`process_llm_output(llm_call)`
が呼ばれてしまう(本来不要なLLM呼び出しコストが発生したうえ、`intent`不明な出力を
どう扱うかも未定義)。本ドキュメントはこの空白を埋める。

## スコープ

1. `type`によるイベント振り分け層の新設(`message`/`follow`/`unfollow`/その他)。
2. `follow`イベント: ウェルカムメッセージの設計。
3. `unfollow`イベント: 会話状態・予約データ・オーナー通知まわりの扱いの決定。

course-set-pasha/aircon-pashaと異なり、本ventureは連携コード方式(`pending_links`)を
持たない(store_id=user_idがLIFF経由のIDトークン検証で直接確定するため、コード発行という
中間ステップ自体が存在しない。checkout-initiation-flow-design.md 2節参照)。したがって
「未使用の連携コードの扱い」は本ventureには論点として存在しない。

## 前提の整理: 本venture固有の「followerは誰か」問題

aircon-pasha/course-set-pashaは「LINEをフォローした人=サービスに課金する事業者本人」が
常に成立するが、本ventureのLINE公式アカウントは店舗ごとに1つ発行され、**そのアカウントを
フォローするのは主に店舗の「顧客」であり、店舗オーナー自身も同じアカウントをフォロー
している**(owner-notification-channel-design.md: オンボーディングのステップ4で
「オーナー自身のLINEアカウントから店舗の公式LINEアカウントへテストメッセージを送る」
ことで初めて`owner_user_id`が判明する)。つまり:

- `follow`イベントの時点では、フォローしたのがオーナー自身か一般顧客かを判別する手段が
  まだ無い(オーナーもテストメッセージを送るまでは`owner_user_id`未登録の状態で
  フォローするため、顧客と区別がつかない)。
- `unfollow`イベントの時点では、既にオンボーディングが完了していれば`owner_user_id`が
  判明しているため、`event["source"]["userId"] == store.owner_user_id`かどうかで
  「オーナー自身のブロック」と「一般顧客のブロック」を区別できる。

なお、`owner_user_id`(owner-notification-channel-design.md)と、Stripe決済導線が使う
`store_id`/`user_id`(checkout-initiation-flow-design.md・stripe-customer-id-reverse-lookup-
design.md、LIFF経由のIDトークン検証で取得)が、実際に同一のLINE userIdを指すのか
(=いずれもオーナー本人がLINEアカウントで認証している以上、自然には同一のはず)は、
両ドキュメントとも明示的に「同一である」と書いてはいない。本ドキュメントではこの2つを
別概念として扱い(混同すると設計を誤るため)、**同一かどうかの確認は次回以降の残課題**
とする(下記「残課題」参照)。幸い、下記のunfollow時の方針は「データを一切変更しない」
という点でオーナー・顧客どちらであっても共通のため、この論点は今回の設計をブロックしない。

## 1. イベント振り分け層の新設

`prototype/cloud_function_process_event.py`に`dispatch_process_event(processor, event,
llm_call, now, tone="standard") -> DispatchResult`を新設する想定。

```
event["type"] == "message"  → processor.process(event, llm_call, now, tone)  (既存、変更なし)
event["type"] == "follow"   → processor.process_follow_event(event, now)
event["type"] == "unfollow" → processor.process_unfollow_event(event, now)
event["type"] not in above  → 何もせず DispatchResult(action="ignored", detail=event.get("type", "unknown"))
```

Cloud Tasksからデキューされた1件を処理する呼び出し元(Function B本体、未実装)は、
今後`processor.process(...)`を直接呼ぶ代わりにこの`dispatch_process_event()`を
呼ぶ形に差し替える。これにより`process()`自体は「`message`イベントのみを受け取る」
という前提が事後的に正しくなり、既存435件のテストへの影響はない
(`process()`のシグネチャ・挙動は変更しない)。

## 2. followイベント: ウェルカムメッセージ

前提整理の通りフォロー時点ではオーナー/顧客の判別ができないため、**どちらが読んでも
違和感のない共通の固定文言**を送る(aircon-pashaが連携コード方式ゆえにオーナー向け専用
文言を送れたのとは異なり、本venture固有の制約)。

```
ご登録ありがとうございます!

こちらのLINE公式アカウントでは、空き時間の確認から予約の確定・前日リマインドまで、
トークだけで完結します。

ご希望の日時やメニューを、そのままメッセージで送ってください。
(例:「今週土曜の午後に予約したいです」)

营業日・アクセス・お支払い方法などのご質問もこちらでお答えします。
```

- 店舗名を差し込みたい場合は、store-settings-save-flow-design.mdで保存済みの店舗設定
  (`business_name`相当のフィールド)を`StoreSettingsProvider`的なプロトコル
  (aircon-pashaの`form_link_provider`と同じ「未接続時はプレースホルダを返す安全側
  フォールバック」の考え方)経由で取得し先頭に付与する拡張を想定するが、店舗設定の
  該当フィールド名の確定(owner-settings-wireframe.md側の項目名との突き合わせ)は
  未確認のため、本フェーズでは固定文言のみを設計対象とし、店舗名差し込みは次回以降の
  拡張候補として残す。
- `process_follow_event(event, now) -> FollowProcessResult`(`reply_sent: bool`のみを
  持つ最小限のdataclass)。`event["source"]["userId"]`欠落時は送信しない
  (aircon-pasha・course-set-pashaと同じ防御的分岐)。

## 3. unfollowイベント: 会話状態・予約データ・オーナー通知の扱い

data-retention-policy.mdの保存期間方針(業務上の必要性がある限り一定期間保持し、
`unfollow`のような関係性の変化だけでは即座に削除しない)、およびaircon-pasha/
course-set-pashaで確立済みの「LINEのブロックとStripeの解約は別レイヤーの事象」という
原則を、本ventureにもそのまま適用する。

| 対象 | unfollow時の処理 | 理由 |
|---|---|---|
| `ConversationFlowStateMachine`の会話状態(`_states`) | 何もしない(保持) | 再フォロー時に会話の続きから再開できるようにするため。confirmed-state-archival.mdのアーカイブ条件(来店日+1日)にも影響させない |
| `bookingSlots`(pending/confirmed) | 何もしない(保持、自動キャンセルしない) | 顧客がブロックしただけで予約自体が無効になるわけではない(電話等の別経路で来店する可能性もある)。自動キャンセルはno-show-handling.mdが定める無断キャンセル確定ロジックに委ねる |
| Stripeサブスクリプション課金(オーナーがunfollowした場合) | 何もしない(自動解約しない) | aircon-pasha論点2・course-set-pashaと同じ原則。オーナーが誤ってブロックしただけで課金を止めると、むしろオーナーに無断で契約状態が変わってしまう方が不利益が大きい |
| `notificationLogEntries` / 通知ログ集計 | 何もしない(保持) | data-retention-policy.mdの6か月保持方針をそのまま適用 |
| LINEへの返信・オーナー通知 | 行わない(送達不可) | 送達不可はaircon-pashaと同じく実害なし。ただし後述「残課題」参照 |

`process_unfollow_event(event, now) -> UnfollowProcessResult`(`handled: bool`のみ)を
新設する。データの検索・削除処理を一切行わない極めて薄い実装になる点はaircon-pasha版と
同じ(aircon-pashaは「pending_linksがuser_id非依存で検索不能」という技術的制約が理由
だったのに対し、本ventureは「意図的に何もしない」という設計判断が理由という違いはあるが、
実装としての薄さは同じ)。

## 実装状況(2026-08-31 20:00 UTC追記)

`dispatch_process_event()`・`process_follow_event()`・`process_unfollow_event()`を
`prototype/cloud_function_process_event.py`に実装し、テスト7件を追加した(venture全体
492件全件パス・schema検証25件パスを確認)。1節の設計通り、`event["type"]`が
`"message"`なら既存の`processor.process()`へ、`"follow"`なら`process_follow_event()`へ、
`"unfollow"`なら`process_unfollow_event()`へ振り分け、それ以外は
`DispatchResult(action="ignored", detail=event.get("type", "unknown"))`を返す(送信・状態
変更は一切行わない)。`process_follow_event()`はFOLLOW_WELCOME_MESSAGE(2節の固定文言、
原文の誤字「营业日」は「営業日」に修正して採用)を1回送るのみ、`process_unfollow_event()`は
`UnfollowProcessResult(handled=True)`を返すだけで会話状態・予約枠・通知ログのいずれにも
書き込み・削除を行わない(3節の方針通り)。ただしFunction B本体(Cloud Tasksデキュー後の
実エントリポイント)は未実装のままのため、`dispatch_process_event()`を実際に呼び出す配線は
次回以降の課題として残る。

## 残課題

- (一部解消 2026-09-01 19:00 UTC・フェーズ続き165: `owner_user_id`と決済導線の
  `user_id`の同一性を確認する過程で、より根本的に「storeId自体をWebhookイベントから
  どう解決するか」が未設計だったことを発見した。store-id-resolution-and-owner-identity-
  design.mdとして整理し、storeIdは`destination`(公式アカウント自身のuserId)を正とし、
  決済導線の個人userIdはstore_idとしてではなく`owner_user_id`との一致を確認する認可
  チェックの材料として使う方針とした。この整理により、当初の問い(同一かどうか)は
  「両者ともstore_idとしては使われないため解消される」という結論になった。ただし
  この方針をcheckout-initiation-flow-design.md等の該当記述に反映する作業自体は次回以降の
  課題として残る。
  (解消 2026-09-02 18:59 UTC・フェーズ続き175: オーナー自身がunfollowした場合の一連の
  オーナー向けpush送達不可という運用上重要な事実を、aircon-pashaのunfollow-billing-faq.md
  相当の文書としてunfollow-billing-faq.mdに整理した。本venture固有の「オーナーも一般顧客と
  同じ公式アカウントをフォローする」構造を踏まえ、ブロック中は予約通知等の業務通知も止まる
  旨を追加した点がaircon-pasha・course-set-pasha版との差分。LP掲載・実際の問い合わせ対応は
  未実施のまま、文面整理のみ。詳細はunfollow-billing-faq.md参照。)
- 顧客がunfollowした後にリマインド送信(`_send()`)が失敗し続けるケースを、
  no-show-handling.mdの無断キャンセルリスク判定シグナルとして活用できないかは未検討
  (「事前リマインドが届いていない」ことを把握できれば、無断キャンセル発生前にオーナーへ
  事前確認を促せる可能性がある)。本ドキュメントのスコープ外として次回以降の検討候補とする。
- 店舗名差し込み版ウェルカムメッセージ(2節参照)の実装は、owner-settings-wireframe.mdの
  店舗設定フィールド名確定後に着手する。
- `dispatch_process_event()`を実際に呼び出すFunction B本体(Cloud Tasksデキュー後の
  実エントリポイント)は未実装のため、その配線自体は次回以降の課題として残る
  (上記「実装状況」参照)。
