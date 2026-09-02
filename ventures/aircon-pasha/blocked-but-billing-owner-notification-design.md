# 「ブロック中かつ契約継続中」候補のオーナー通知 設計(フェーズ174)

blocked-but-billing-detection-design.md(フェーズ167)4節「未着手のまま残る課題」に
残っていた「候補一覧をオーナーへ実際に届ける手段は未設計・未接続」に対応する。
`list_blocked_but_billing_candidates()`が洗い出した候補user_idを、実際に運営者
(オーナー、本AI Companyの実オーナー。契約継続中の業者=顧客とは別人)へ届けるバッチと
通知チャネルを設計する。

course-set-pashaは同種の課題にフェーズ143・blocked-but-billing-owner-notification-
design.mdで対応済み(基盤となるpayment-suspension-owner-notification-design.md、
フェーズ125)。同ドキュメント6節が「同様の設計はaircon-pasha側でも横展開可能だが、
本フェーズではcourse-set-pashaのみを対象とする」と明記していた通り、本ドキュメントは
その横展開にあたる。

なお、フェーズ167時点では「実LINE・実Stripe接続後にunfollow発生率が実測できてから
設計する方が精度が高い」という判断で本課題を先送りしていた。しかし通知チャネル自体は
実測データを必要とせず、既存のオーナー向け固定送信先という設計パターンをそのまま
転用できることがcourse-set-pashaでの前例で判明したため、実測データ待ちという理由は
本節に限っては当てはまらないと判断し、本フェーズで着手する。

## 1. 送信先

本ventureにはcourse-set-pashaのpayment-suspension-owner-notification-design.mdに
相当する「オーナー固定宛先」の先行設計が無い。本ドキュメントで新規に
`OWNER_LINE_USER_ID_PLACEHOLDER`(送信先は同venture内で1箇所に集約する想定だが、
本モジュールでは独立した定数として定義する)を導入する。実際のオーナーLINEユーザーID
の取得・設定は既存の「実LINE API接続はオーナー承認待ちの範囲」(README.md該当箇所)に
含まれるため、新たな承認待ち事項としては扱わない(pending-approval.mdへの追記は不要)。

## 2. メッセージ形式: プレーンテキストではなくFlex Message

course-set-pashaの`LinePushClient`は`send_message(user_id, text)`(プレーンテキスト)
だが、本ventureの`LinePushClient`(trial_end_scheduler.py)は
`send_flex_message(user_id, alt_text, contents)`のみを提供し、本venture一貫の方式
(trial-end-notification-design.md等)である。オーナー通知にボタンは不要なため、
`build_trial_end_notification_flex_message()`と同じ`bubble`形式のうち、テキスト
ボックスのみで構成し`footer`(ボタン)は持たないシンプルな構成とする。

## 3. バッチ実行主体・実行頻度

`list_blocked_but_billing_candidates()`自体はMVPでは`InMemoryUserProfileStore.
all_user_ids()`の線形走査(blocked-but-billing-detection-design.md 3節)であり、
日次1回程度の実行を想定する。trial_end_scheduler.py・payment_suspension_scheduler.py
と同じ「日次Cloud Scheduler → Cloud Function」の構成に揃える(Cloud Function G相当。
実際のCloud Scheduler作成はオーナー承認待ちの範囲)。

## 4. 冪等性(いつ・誰を通知するか)

`list_blocked_but_billing_candidates()`は毎回「現時点でブロック中かつ契約継続中の
全候補」を返す設計であり(is_followingがFalseに戻るかcurrent_plan_idがNoneになる
まで対象であり続ける)、そのまま毎日通知すると同じ候補を延々と再通知し続けてしまう。
course-set-pasha版と同じ考え方で、候補ごとに一度だけ通知する冪等性フラグ
`blocked_but_billing_owner_notified_at`を`UserProfile`(user_id_linking.py)に
新設した(実装済み、下記5節参照)。

- 通知対象は「`list_blocked_but_billing_candidates()`の結果に含まれる」かつ
  「`blocked_but_billing_owner_notified_at`が未設定」のuser_idのみ(新規候補のみを
  通知する、digest形式ではなく1候補=1回の個別通知)。
- 送信成功時のみ`blocked_but_billing_owner_notified_at`を書き込む(送信失敗時は
  書き込まず次回実行時に自然に再試行対象として残る、既存の全通知バッチと同じ方式)。

## 5. 実装状況

`prototype/blocked_but_billing_owner_notification.py`に
`select_new_blocked_but_billing_candidates_for_notification()`(3節の抽出条件)・
`build_blocked_but_billing_owner_notification_flex_message()`(2節のFlex Message
整形)・`send_blocked_but_billing_owner_notifications()`(Cloud Function G本体)を
実装した。`user_id_linking.py`の`UserProfile`に`blocked_but_billing_owner_
notified_at`フィールドを追加し、`UserProfileStoreProtocol`/
`InMemoryUserProfileStore`にget/setメソッドを追加した(構造的に本モジュールの
`BlockedButBillingOwnerNotifiedAtReader`/`Writer`を満たす)。テスト追加、
venture全体テストパスを確認済み(詳細は上記README.md本フェーズ参照)。

## 6. クリア配線(フェーズ175で実装済み)

- 「フォロー再開(is_followingがTrueに戻る)」または「解約確定
  (customer.subscription.deleted受信でcurrent_plan_idがNoneに戻る)」のいずれかが
  起きた時点で`blocked_but_billing_owner_notified_at`をクリアする配線を実装した
  (course-set-pashaがフェーズ142→143→144の3段階で踏んだ順序の最終段階に相当)。
  `blocked_but_billing_owner_notification.py`の
  `clear_blocked_but_billing_owner_notified_at()`(設定済みの場合のみクリアし
  True/Falseを返す純粋関数)を新設し、`cloud_function_webhook.process_follow_
  event()`・`stripe_dispatch.dispatch_stripe_event()`の`customer.subscription.
  deleted`分岐の両方から呼び出す。`dispatch_stripe_event()`/`receive_stripe_
  webhook()`/`get_stripe_runtime_dependencies()`に新規引数`blocked_but_billing_
  store`(省略時はクリアを行わない後方互換)を追加した。テスト7件追加、venture全体
  388件全件パス・schema検証9件パスを確認した(詳細は上記README.mdフェーズ175参照)。

## 7. 今後の課題

- `blocked_but_billing_owner_notified_at`の実Firestoreフィールド追加・実際の
  Cloud Scheduler作成・実LINE API接続はオーナー承認待ちの範囲(既存の記載を参照、
  新規追加なし)。
