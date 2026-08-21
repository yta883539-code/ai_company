# unfollow(ブロック)イベント受信時の扱い

作成日: 2026-08-21(フェーズ84)

## 背景

webhook-event-dispatch-design.md(フェーズ81)の残課題として「`unfollow`イベント受信時の
扱い(連携コード・利用状況データの扱いをどうするか)は未検討のまま残る」としていた。
現状の`dispatch_webhook_events()`は`unfollow`を他の未対応種別(`postback`・`join`等)と
同列に扱い、`DispatchResult.ignored_types`へ記録するだけで実処理は行っていない
(cloud_function_webhook.py L825-828)。本ドキュメントはこの扱いを具体的に決める。

## 論点1: LINEのブロックとStripeサブスクリプションは別システムである

`unfollow`(ブロック)は、あくまでLINE公式アカウントとの友だち関係が切れるだけのイベントであり、
pricing-plan.md・subscription-cancellation-flow-design.mdが扱う「解約」(Stripeカスタマー
ポータルでのサブスクリプション解約)とは別レイヤーの事象である。ユーザーがブロックだけを行い
Stripe側の解約操作をしなければ、サブスクリプション課金は自動的には止まらない。

これはline-reservation-aiのdormant-mode-renotification-design.mdが指摘した「通知チャネルの
ブロックによる再開機会の喪失」と表裏の問題で、本ventureの場合は「サービスを使う意思がない
(ブロックした)のに課金だけ続く」というオーナー・ユーザー双方にとって望ましくない状態が
生じうる。

**本サービスがunfollowを検知して自動的にStripeの解約処理を行うことはしない。**
理由:
- 決済の解約はユーザー本人の明示的な意思表示(カスタマーポータルでの操作)によるべき事項で
  あり、ブロックという行為だけから「解約の意思」を確定的に読み取ってよいとは言えない
  (誤ブロック・一時的な通知過多での一時ブロック等、再フォローして使い続ける可能性を残す
  ケースもある)。
- subscription-cancellation-flow-design.mdが前提とする解約フローはあくまでカスタマーポータル
  起点であり、Webhook側から逆方向にStripeの解約APIを呼ぶ設計はどこにも存在しない。安易に
  ここで新設すると、確定していない意思表示に基づく取消不能な決済操作を行うことになり
  リスクが大きい。

一方で、「ブロックしたのに課金が続く」状態を放置してよいわけではない。この点は本フェーズの
スコープを超える運用課題として、下記「今後の課題」に切り出す(オーナー向けの案内文言・
問い合わせ対応フローの整備が必要になる見込み)。

## 論点2: `pending_links`(連携コード)の扱い

該当`user_id`宛に発行済みで未使用のまま残っている連携コードがあれば、ブロック時点で
削除してよいか。

- 連携コードは`user_profile`の初期設定(申込フォーム提出)のためだけに使う一回限りの
  トークンであり、ブロックしたユーザーが申込フォームを提出する可能性は実質的に無くなる
  (フォーム提出の呼び出し元はLINEのウェルカムメッセージで案内されたコードであり、
  ブロック後は新たな案内を受け取れない)。
- line-user-id-linking-design.mdの既存方針(有効期限24時間で自然失効、実害は「Firestore上に
  空きドキュメントが残るだけ」)から、削除しなくても実害はない。ただし、放置しても得るものが
  ない一方、即時削除すれば`purge_expired_links()`の対象を早めに減らせる。
- **結論: 即時削除する。** 実害はないが、不要になったことが確定した時点(unfollow)で
  速やかに片付ける方が、`pending_links`コレクションのドキュメント数を不必要に膨らませない
  という意味で望ましい。24時間の自然失効を待つ理由はない。

## 論点3: `user_profile`(ジム名・地域名設定)・`usage_counter`・履歴データの扱い

- **結論: 一切削除・変更しない。** 再フォロー(`follow`イベントの再発火)時に同じ`user_id`で
  戻ってきた場合、再度申込フォームから設定し直す手間をユーザーに強いない設計とする
  (line-user-id-linking-design.md 4節が既に「未フォロー・再フォロー時の扱い」で同様の
  考え方を示している)。
- 個人情報保護法の観点からの保存期間上限は未整理のまま残っている(line-reservation-aiの
  data-retention-policy.mdに相当する文書が本ventureにはまだ無い)。本フェーズはunfollow
  イベント受信時の**即時**処理のみを決めるものであり、長期保存の要否・上限は別途
  data-retention-policy.md相当の文書化が必要な次の課題として残す(下記参照)。

## 決定のまとめ

| 対象 | unfollow時の処理 |
|---|---|
| Stripeサブスクリプション課金 | 何もしない(自動解約しない) |
| `pending_links`(未使用の連携コード) | 該当`user_id`分を即時削除 |
| `user_profile`(ジム名・地域名) | 何もしない(保持) |
| `usage_counter`・履歴データ | 何もしない(保持) |
| LINEへの返信 | 行わない(ブロックされているため送達不可) |

## プロトタイプ実装方針

- `user_id_linking.py`に`delete_pending_links_for_user(user_id, store) -> int`を新設する。
  既存の`items()`(`(code, user_id, issued_at)`を列挙)を使って対象コードを絞り込み、
  `delete()`する薄い関数とし、`purge_expired_links()`と同じ実装パターンを踏襲する。
- `cloud_function_webhook.py`に`process_unfollow_event(event, linking_store) -> UnfollowProcessResult`
  (`deleted_link_count: int`を持つdataclass)を新設する。`event["source"]["userId"]`が
  取得できない場合・`linking_store`が未接続(None)の場合は何もせず`deleted_link_count=0`を
  返す(他のイベントハンドラと同じ「未接続時は安全側で素通り」方針)。
- `DispatchResult`に`unfollow_results: list`フィールドを追加し、`dispatch_webhook_events()`で
  `event["type"] == "follow"`と同様に`"unfollow"`も専用の振り分け対象へ変える
  (`ignored_types`からは外れる。`postback`・`join`等の真に未対応な種別のみ引き続き
  `ignored_types`に記録される)。

## 今後の課題

- 「ブロックしたのに課金だけ続く」状態への対応(オーナー向けFAQ・問い合わせ対応文言の整備、
  あるいはunfollow検知をトリガーにしたオーナー向け内部通知の要否)は、本フェーズのスコープ
  外の運用設計課題として残る。実LINE接続後にunfollow発生率が実測できた段階で優先度を
  判断する。
- `user_profile`・`usage_counter`等の長期保存期間の上限は、line-reservation-aiの
  data-retention-policy.mdに相当する文書が本ventureにまだ無いため未整理。次の課題とする。
- 実Firestore接続後、`delete_pending_links_for_user()`の実装が複数ドキュメントの削除を
  伴う場合のバッチ削除・部分失敗時の扱いは接続後の課題として残る。
