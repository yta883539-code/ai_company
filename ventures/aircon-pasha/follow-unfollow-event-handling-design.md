# follow/unfollowイベント受信時の扱い(フェーズ109)

作成日: 2026-08-23

## 背景

user-account-linking-design.md(フェーズ107)2節・3節で、本ventureは「フォーム送信 →
LINE友だち追加」という順序が確定しているため、course-set-pashaとは異なり`follow`イベント
自体ではコードを発行しない(=`follow`直後のウェルカムメッセージには連携コードを埋め込まない)
という方針までは決まっていたが、具体的な処理フロー・実装方針は未記述だった。またフェーズ108の
data-retention-policy.mdは「本ventureはunfollowイベント処理自体が未設計のため、ブロック時の
扱いは未決定のまま」と明示していた。本ドキュメントはこの2点(follow時のウェルカムメッセージ
処理、unfollow時のデータの扱い)をまとめて設計する。

course-set-pashaのfollow-event-welcome-message-design.md(フェーズ80)・
unfollow-event-handling-design.md(フェーズ84)を参考にしつつ、本venture固有の
「フォーム起点」の紐付け方式(向きが逆)を反映する。

## 1. followイベント: ウェルカムメッセージ

course-set-pashaは`follow`時点でコードを発行し埋め込む必要があったが、本ventureは
user-account-linking-design.md 2節の通りコード発行はフォーム送信完了時点で既に済んでいる
(`pending_links/{code}`に保存済み)。したがって`follow`時のウェルカムメッセージは固定文言
のみで足り、コード発行ロジックの呼び出しは不要。

```
エアコンパシャッと 友だち追加ありがとうございます!

このサービスは、エアコンクリーニング作業後の簡単なメモを送るだけで、依頼者向け完了報告・
お手入れ案内・作業記録の下書きをまとめて生成するツールです。

お申込みフォームで発行された連携コード(6文字)をお持ちの方は、そのままこのトークに
コードを送信してください。

まだお申込みがお済みでない方は、下記フォームからお申込みください。
{APPLICATION_FORM_URL_PLACEHOLDER}
```

- `{APPLICATION_FORM_URL_PLACEHOLDER}`はcourse-set-pashaの
  `ApplicationFormLinkProvider`と同じ考え方(未接続時はプレースホルダのまま返す、
  Googleフォーム作成・接続はオーナー承認待ちのため実害なし)を踏襲する。
- コードそのものを埋め込まない分、course-set-pashaの`format_welcome_message()`より単純な
  固定テンプレートになる(`{LINKING_CODE}`のような差し込みが不要)。

### 処理フロー

`prototype/cloud_function_webhook.py`に`process_follow_event(event, *, form_link_provider=None) -> FollowProcessResult`
を新設する想定(`FollowProcessResult`は`reply_sent: bool`のみを持つ、コード発行を伴わない分
course-set-pasha版より単純なdataclass)。

- `event["type"] != "follow"`は`handled=False`で無視する(course-set-pashaと同じ設計)。
- `event["source"]["userId"]`欠落時は返信を送らない(同上、防御的分岐)。
- 本venture固有の分岐は不要(コード発行がないため、course-set-pashaにあった
  `linking_store`・`rng`・`now`引数はいずれも不要になる)。

## 2. unfollowイベント: pending_links・user_profileの扱い

### 論点1: `pending_links`(未使用の連携コード)は`user_id`と紐付いていない

ここが本ventureとcourse-set-pashaの決定的な違いである。course-set-pashaは`pending_links`が
「`follow`時点のuser_idに対して」発行されるため、unfollowした`user_id`に紐づくコードを
`delete_pending_links_for_user(user_id, store)`で検索・削除できた。

本ventureの`pending_links/{code}`(user-account-linking-design.md 5節)は
`form_submission_id`・`business_name`・`business_type`・`email`・`issued_at`のみを保持し、
**`user_id`フィールドを持たない**(フォーム送信時点ではまだ`follow`していないため、
そもそも`user_id`が存在しない)。したがって`unfollow`イベントを受信しても、それが
どの`pending_links`エントリに対応するのかを特定する手段がない。

**結論: `unfollow`イベントでは`pending_links`に対して一切の検索・削除処理を行わない。**
理由:
- 技術的に対応するエントリを特定できない(`user_id`をキーに検索するcourse-set-pasha方式が
  そもそも適用できない)。
- 実害もない。`pending_links`は24時間の有効期限で自然失効し、`purge_expired_links()`
  (course-set-pashaと同じ実装をそのまま流用予定)が期限切れエントリを別途掃除する。
  unfollowした業者がコードを送信しないまま放置しても、24時間後には自然に片付く。
- 「follow直後にunfollowされ、後で同じコードを別の`follow`で使われたら」という懸念も、
  コード自体が使い切り一回限り・24時間有効という既存方針(user-account-linking-design.md
  3節)により、最初に正しいコードを送信した`user_id`が連携される点に変わりはなく問題ない
  (unfollowした本人が再度followしてコードを送り直すケースも同様に問題なく動作する)。

### 論点2: `user_profile`(連携済み業者のプロフィール)

course-set-pashaの結論(論点3)と同じ考え方を採用する。**一切削除・変更しない。**
再フォロー時に同じ`user_id`で戻ってきた場合、フォーム再入力の手間を業者に強いない設計とする。
`stripe_customer_id`・`current_plan_id`もそのまま保持し、Stripe側のサブスクリプション状態
(`customer.subscription.*`)には一切影響させない(course-set-pasha論点1と同じ、LINEの
ブロックとStripeの解約は別レイヤーの事象という整理をそのまま踏襲)。

### 論点3: `usage_counter`

変更なし(course-set-pashaと同じく保持)。

### 決定のまとめ

| 対象 | unfollow時の処理 |
|---|---|
| Stripeサブスクリプション課金 | 何もしない(自動解約しない) |
| `pending_links`(未使用の連携コード) | 何もしない(`user_id`と紐付かないため検索不能。24時間の自然失効に委ねる) |
| `user_profile`(連携済みプロフィール・`stripe_customer_id`・`current_plan_id`) | 何もしない(保持) |
| `usage_counter` | 何もしない(保持) |
| LINEへの返信 | 行わない(送達不可) |

course-set-pashaとの唯一の差異は「pending_links」行であり、これは本venture固有のフォーム
起点方式(コードがuser_id非依存で発行される)という構造的な違いに起因する。

### プロトタイプ実装方針

- `cloud_function_webhook.py`に`process_unfollow_event(event) -> UnfollowProcessResult`
  (フィールドなし、またはブール値`handled`のみを持つ最小限のdataclass)を新設する。
  course-set-pashaと異なり削除処理を伴わないため、本venture版は「`unfollow`を
  `ignored_types`から専用の振り分け対象へ切り出すが、実処理としては何もしない」という
  極めて薄い実装になる。
- `DispatchResult`に`unfollow_results`フィールドを追加し、`dispatch_webhook_events()`
  (未実装、次回以降に`webhook-event-dispatch-design.md`相当のドキュメントで設計予定)で
  `"unfollow"`を専用振り分け対象とする方針をここで先に確定しておく。
- テストは(1)`follow`イベント正常系(固定文言での返信、コード発行が発生しないことの確認)、
  (2)`form_link_provider`未接続/接続時のURL差し替え、(3)`unfollow`受信時に`pending_links`・
  `user_profile`のいずれにも書き込み・削除が発生しないことの確認、の最低3ケースを想定する。

## 残課題

- (解消済み 2026-08-23 10:00 UTC・フェーズ111: 本ドキュメントで設計した`process_follow_event()`・
  `process_unfollow_event()`をprototype/cloud_function_webhook.pyに実装した。テスト50件
  全件パス。詳細はREADME.mdフェーズ111参照。残る2項目〈ディスパッチ経路自体、
  `process_message_event()`相当のコード判定分岐〉は引き続き未実装のまま残る)
- (解消済み・フェーズ112・113: user-account-linking-design.md 3節で設計した「連携コード判定
  vs 施工メモ判定」の分岐は`process_message_event()`として実装済み(`profile_store.exists()`で
  連携済みか判定し、連携済みなら`process_memo_event()`へ委譲、未連携なら`resolve_linking_code()`
  でコード一致のみを判定根拠とする)。`follow`/`unfollow`/`message`/`postback`の4種別を
  振り分ける`dispatch_webhook_events()`も実装済みで、`prototype/cloud_function_webhook.py`の
  `DispatchWebhookEventsTest`・`ProcessMessageEventLinkingTest`でカバーされている(連携済み
  ユーザーのmessageイベントが`process_memo_event()`側の生成フローまで実際に到達すること、
  未連携ユーザーは`linking_store`未接続時は素通りする安全側フォールバックになることを含む)。
  本節作成当初(フェーズ109)時点では未実装だったこの2項目について、後続フェーズで解消
  済みであるにもかかわらず本ドキュメント側の更新が漏れていた記載漏れを、2026-08-30 18:00 UTC
  時点の棚卸しで解消した。コード変更は無し(ドキュメント整理のみ)。)
- (解消済み 2026-08-31 15:00 UTC・フェーズ165: 「ブロックしたのに課金だけ続く」場合の
  オーナー向け運用課題(course-set-pasha unfollow-event-handling-design.md「今後の課題」と
  同一の未解決事項)について、course-set-pashaのunfollow-billing-faq.md(フェーズ86)を
  土台に本venture固有の文面へ翻案したunfollow-billing-faq.mdを新規作成し、LP掲載用FAQ文面・
  問い合わせ対応テンプレートを整理した。プロアクティブな検知・通知バッチの要否は同ドキュメント
  「今後の課題」として引き続き未着手のまま残る。)
