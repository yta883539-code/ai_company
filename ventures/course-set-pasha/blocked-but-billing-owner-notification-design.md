# 「ブロック中かつ契約継続中」候補のオーナー通知 設計

blocked-but-billing-detection-design.md(フェーズ142)「残る限界・今後の課題」に残っていた
「候補一覧をオーナーへ実際に届ける手段(バッチ実行主体・通知チャネル)は未設計」に対応する。
`list_blocked_but_billing_candidates()`が洗い出した候補user_idを、実際に運営者(オーナー、
顧客であるボルダリングジムオーナーとは別)へ届けるバッチと通知チャネルを設計する。

payment-suspension-owner-notification-design.md(フェーズ125)が既に確立した「顧客ごとの
user_idではなく固定のオーナー1件へLINE Push」というチャネル設計をそのまま踏襲する。新たな
通知チャネルの検討は行わない。

## 1. 送信先

payment-suspension-owner-notification-design.mdと同一。`OWNER_LINE_USER_ID_PLACEHOLDER`
(送信先は同ventureで1箇所に集約する想定だが、本モジュールでは独立した定数として定義する。
実際のオーナーLINEユーザーIDの取得・設定は既存の「実LINE API接続はオーナー承認待ちの範囲」に
含まれるため、新たな承認待ち事項としては扱わない)。

## 2. バッチ実行主体・実行頻度

`list_blocked_but_billing_candidates()`自体はMVPでは`profile_store.all_user_ids()`の
線形走査(design 3節)であり、日次1回程度の実行を想定する。trial_end_scheduler.py・
payment_suspension_owner_notification.pyと同じ「日次Cloud Scheduler → Cloud Function」の
構成に揃える(Cloud Function G相当。実際のCloud Scheduler作成はオーナー承認待ちの範囲)。

## 3. 冪等性(いつ・誰を通知するか)

`list_blocked_but_billing_candidates()`は毎回「現時点でブロック中かつ契約継続中の全候補」を
返す設計であり(deletion_candidate_atが確定するまで対象であり続ける)、そのまま毎日通知すると
同じ候補を延々と再通知し続けてしまう。payment_suspension_owner_notification.pyの
`payment_suspension_owner_notified_at`(1顧客1回のみ送信)と同じ考え方で、
候補ごとに一度だけ通知する冪等性フラグを新設する。

- 新規フィールド`blocked_but_billing_owner_notified_at`を`user_profile`ドキュメントに追加する
  (`stripe_customer_id`・`is_following`と同じ`UserProfileStoreProtocol`側で管理する。
  `deletion_candidate_at`同様に本ventureでは`usage_counter`を持たないため、
  `payment_suspension_owner_notified_at`が`usage_counter`側にあるのとは置き場所が異なる点に
  注意)。
- 通知対象は「`list_blocked_but_billing_candidates()`の結果に含まれる」かつ
  「`blocked_but_billing_owner_notified_at`が未設定」のuser_idのみ(新規候補のみを通知する、
  digest形式ではなく1候補=1回の個別通知)。
- 送信成功時のみ`blocked_but_billing_owner_notified_at`を書き込む(送信失敗時は書き込まず
  次回実行時に自然に再試行対象として残る、既存の全通知バッチと同じ方式)。

## 4. クリア(再度ブロック中かつ契約継続中に戻った場合)

`blocked_but_billing_owner_notified_at`は「フォロー再開(is_followingがTrueに戻る)」または
「解約確定(deletion_candidate_atが設定される)」のいずれかが起きた時点でクリアする
(`process_follow_event()`・`mark_deletion_candidate_on_subscription_deleted()`相当の箇所に
配線する)。クリアしないと、一度通知された顧客が再度フォロー解除→再契約継続という状態に
戻った場合に二度と通知が飛ばなくなる(payment_failure_reminder_sent_atのクリアと同じ理由、
payment-failure-reminder-scheduler-design.md 3節参照)。本設計フェーズでは判定条件の追加のみ
行い、実際の配線(process_follow_event()等への呼び出し追加)は次回以降の実装課題として残す
(下記6節)。

## 5. 通知文言

顧客ごとに内容が変わるため、payment-suspension-owner-notification-design.md 4節と同型の
テンプレートを用いる。

```
[コースセットパシャッと運営] ブロック中かつ契約継続中のお知らせ

以下の顧客がLINEをブロックしていますが、Stripeでの契約(決済)は継続中です。

顧客ID: {user_id}

必要に応じて顧客への個別フォロー(再フォローのお願い・解約意向の確認等)をご検討ください。
```

## 6. 今後の課題

- 4節のクリア配線はフェーズ144で実装済み。`blocked_but_billing_owner_notified_at`は
  `application_form_submission_flow.UserProfileStoreProtocol`/`InMemoryUserProfileStore`側の
  フィールドとして追加し、`cloud_function_webhook.process_follow_event()`
  (`profile_store`指定時、`set_is_following(user_id, True)`と同時に
  `clear_blocked_but_billing_owner_notified_at()`を呼ぶ)と、
  `stripe_webhook.dispatch_stripe_event()`の`customer.subscription.deleted`分岐
  (`user_profile_store`指定時、`mark_deletion_candidate_on_subscription_deleted()`と同時に
  クリア)の両方に配線した。`dispatch_stripe_event()`・`receive_stripe_webhook()`の
  `user_profile_store`引数は既存のcheckout.session.completed経路のものをそのまま再利用して
  おり、新規の依存関係追加はない。テスト7件追加、venture全体471件全件パス・schema検証9件
  パスを確認した。
- `blocked_but_billing_owner_notified_at`の実Firestoreフィールド追加・実際のCloud Scheduler
  作成・実LINE API接続はオーナー承認待ちの範囲(既存の記載を参照、新規追加なし)。
- aircon-pashaは`current_plan_id`ベースの同種ロジックを持つが、本ドキュメントと同じ
  「オーナー通知バッチ」の設計はまだ行っていない(aircon-pashaフェーズ167時点でも
  「候補一覧をオーナーへ届ける手段は未設計のまま残す」との記載のみ)。同様の設計は
  aircon-pasha側でも横展開可能だが、本フェーズではcourse-set-pashaのみを対象とする。
