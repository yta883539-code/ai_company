# 「ブロック中かつ契約継続中」候補のオーナー通知(メール版) 設計(フェーズ続き177)

blocked-but-billing-detection-design.md(フェーズ続き176)4節「未着手のまま残る課題」に
残っていた、「候補一覧を実際にオーナーへ届ける手段(メール等の代替チャネル)」の設計・
実装(通知内容の組み立てまで)に対応する。

## 0. 前提の再確認: なぜLINEではなくメールか

follow-unfollow-event-handling-design.md 3節・blocked-but-billing-detection-design.md
2節の通り、本ventureのLINE公式アカウントはオーナー自身がブロック(unfollow)した対象
そのものであるため、検知した「ブロック中」state自体がLINE経由での送達不可を意味する。
aircon-pasha/course-set-pashaのLINE Flex Message通知パターン(オーナーは業者=顧客とは
別人であり、ブロックされるのは顧客からのみ)をそのまま転用できないのは本venture固有の
制約であり、blocked-but-billing-detection-design.md 2節が既に明記した整理である。

## 1. 送信先: `owner_email`フィールドの新設

`stores/{storeId}`ドキュメント(firestore-data-model.md)に`ownerEmail: Optional[str]`
を追加する。`prototype/store_profile_store.py`の`StoreProfileStoreProtocol`/
`InMemoryStoreProfileStore`に`get_owner_email(store_id) -> Optional[str]`・
`set_owner_email(store_id, email: str) -> None`を追加する(`get_owner_user_id`/
`set_owner_user_id`と同じ形)。

- 値の取得元(オンボーディング時にどうやってメールアドレスを収集するか)自体は
  onboarding-guide.mdの範囲であり本フェーズの対象外とする。実運用では、
  Googleフォーム経由の店舗登録(store-id-resolution-and-owner-identity-design.md
  前提)にメールアドレス欄を追加する想定だが、フォーム自体の作成・変更は既存の
  pending-approval.md記載(2026-08-23 04:00 UTC相当、外部サービス側の設定操作)の
  範囲に含まれるため、新たな承認待ち事項としては扱わない。
- `owner_email`が未設定の店舗は、後述4節の候補一覧に残り続けるが送信自体はスキップされる
  (2節参照)。これは「メールアドレス未登録の店舗にはそもそも通知できない」という当然の
  制約であり、`aircon-pasha`の`OWNER_LINE_USER_ID_PLACEHOLDER`未設定時の扱いとは異なり
  店舗ごとに異なりうる値のため、固定プレースホルダ定数ではなくストアフィールドとした。

## 2. メール本文の組み立て: プレーンテキスト

本venture・course-set-pasha・aircon-pashaのいずれも会話内通知はLINE(テキストまたは
Flex Message)だが、メールはLINEのMessaging APIとは独立したチャネルであるため、
リッチな装飾(Flex Message相当のUI)は不要と判断し、件名+プレーンテキスト本文の
シンプルな構成とする。`build_blocked_but_billing_owner_email(store_id)`が
`EmailContent(subject: str, body: str)`(dataclass)を返す。

- 件名: `【要確認】店舗のLINE公式アカウントがブロックされたままです(store_id: {store_id})`
- 本文: (1)何が起きているか(オーナー自身が公式アカウントをブロック中のまま契約が
  継続している旨)、(2)何が困るか(予約確定・無断キャンセル確認等の業務通知が
  オーナーに届かない、unfollow-billing-faq.md記載の実害)、(3)対処方法(公式アカウントの
  ブロックを解除する)、の3点を含む。実際の文面はaircon-pasha/course-set-pashaの
  Flex Message本文(build_blocked_but_billing_owner_notification_flex_message()相当)を
  平文化・翻案したもの。

## 3. 冪等性: `blocked_but_billing_owner_notified_at`(店舗単位)

aircon-pasha/course-set-pashaは`UserProfile`(オーナー=顧客とは別のuser_id単位)に
このフラグを持たせたが、本ventureはオーナーがstore_id単位の存在(1節・
blocked-but-billing-detection-design.md 1節)であるため、`owner_is_following`・
`suspension_reason`と同じ`stores/{storeId}`ドキュメント上に
`blockedButBillingOwnerNotifiedAt`として持たせる方が自然である。
`StoreProfileStoreProtocol`/`InMemoryStoreProfileStore`に
`get_blocked_but_billing_owner_notified_at(store_id) -> Optional[str]`・
`set_blocked_but_billing_owner_notified_at(store_id, value: Optional[str]) -> None`を
追加する(`value=None`でクリアも兼ねる、course-set-pasha/aircon-pashaの
`clear_blocked_but_billing_owner_notified_at()`と同じ考え方を1本のsetterに統合)。

- 通知対象は「`list_blocked_but_billing_candidates()`の結果に含まれる」かつ
  「`blocked_but_billing_owner_notified_at`が未設定」かつ「`owner_email`が設定済み」の
  store_idのみ(digest形式ではなく1店舗=1回の個別メール)。
- 送信成功時のみ`blocked_but_billing_owner_notified_at`を書き込む
  (送信失敗時は次回実行時に自然に再試行対象として残る、既存の全通知バッチと同じ方式)。
- クリア配線(フォロー再開・解約確定時に`None`へ戻す)は、aircon-pashaが
  フェーズ175で踏んだのと同じ最終段階として次回以降の課題とする(4節)。

## 4. 実装状況

`prototype/blocked_but_billing_owner_email_notification.py`に以下を実装した。

- `EmailContent`(dataclass、`subject`・`body`)
- `build_blocked_but_billing_owner_email(store_id) -> EmailContent`(2節の文面組み立て)
- `select_new_blocked_but_billing_candidates_for_email_notification(store) ->
  List[str]`(3節の抽出条件。`list_blocked_but_billing_candidates()`を内部で呼び、
  `blocked_but_billing_owner_notified_at`未設定かつ`owner_email`設定済みで絞り込む)
- `EmailSenderProtocol`(`send(to_email: str, subject: str, body: str) -> bool`の
  1メソッドのみを要求する薄いProtocol。実際のメール配信基盤〈SendGrid・Gmail API等〉への
  接続実装〈`EmailSenderProtocol`の具象クラス〉は、外部サービスとの接続・実際の送信操作を
  伴うためオーナー承認待ちの範囲とし、本フェーズでは対象外とする)
- `send_blocked_but_billing_owner_email_notifications(store, email_sender:
  EmailSenderProtocol) -> List[str]`(Cloud Function本体相当。3節の対象store_idごとに
  `email_sender.send()`を呼び、成功した場合のみ`blocked_but_billing_owner_notified_at`を
  書き込む。送信したstore_idの一覧を返す)

`store_profile_store.py`の`StoreProfileStoreProtocol`/`InMemoryStoreProfileStore`に
1節・3節のフィールド(`owner_email`・`blocked_but_billing_owner_notified_at`)を追加した。

テスト追加、venture全体テストパスを確認済み(詳細は上記README.md本フェーズ参照)。

## 5. 今後の課題

- `EmailSenderProtocol`の実装本体(実際のメール配信基盤〈SendGrid・Gmail API等〉への
  接続)・実際のアカウント作成・APIキー取得はオーナー承認待ちの範囲(pending-approval.md
  参照)。
- 誰が/どの頻度でこの関数を呼ぶか(日次Cloud Scheduler相当)自体の実際の作成・接続も
  オーナー承認待ちの範囲(course-set-pasha・aircon-pashaの同種案件と同じ整理)。
- (解消済み 2026-09-03、フェーズ続き178: 6節参照) クリア配線(フォロー再開・解約確定時に
  `blocked_but_billing_owner_notified_at`を`None`へ戻す)。
- `owner_email`の収集手段(オンボーディングフォームへの項目追加)自体は1節記載の通り
  本フェーズの対象外。

## 6. クリア配線(フェーズ続き178)

5節に残っていた「フォロー再開」・「解約確定」時のクリア配線を実装した。aircon-pashaが
フェーズ175で踏んだのと同じ最終段階(course-set-pashaフェーズ144相当)に当たる。

- フォロー再開側: `prototype/blocked_but_billing_owner_email_notification.py`に
  `clear_blocked_but_billing_owner_notified_at(store, store_id) -> bool`
  (`BlockedButBillingOwnerNotifiedAtStoreProtocol`引数、`blocked_but_billing_owner_
  notified_at`が設定済みの場合のみクリアしTrue/Falseを返す純粋関数、
  aircon-pashaの同名関数と同じ考え方)を新設した。`cloud_function_process_event.
  ConversationEventProcessor.process_follow_event()`が、オーナー本人の再フォロー時に
  `set_owner_is_following(store_id, True)`と同じ分岐でこの関数を呼ぶよう配線した
  (`OwnerFollowStatusStoreProtocol`に`get_blocked_but_billing_owner_notified_at`/
  `set_blocked_but_billing_owner_notified_at`を追加要求するよう拡張)。
- 解約確定側: 本ventureの`cloud_function_subscription_cancelled_webhook.py`は
  store_id keyed Protocolではなく、呼び出し元が既にFirestoreから読み込んだ1件ぶんの
  `StoreSubscriptionState`を直接書き換える設計(1節冒頭参照)であるため、上記の
  `clear_blocked_but_billing_owner_notified_at()`はそのままでは呼べない。同じ
  「設定済みの場合のみクリアしTrue/Falseを返す」ロジックを、`StoreSubscriptionState`に
  新設した`blocked_but_billing_owner_notified_at`フィールドの書き換えとして
  `handle_subscription_deleted()`内にインライン実装し(`suspension_reason = "cancelled"`と
  同じ「stateを書き換え、実際のFirestore書き戻しは呼び出し側」という本モジュール既存の
  方針を踏襲)、結果を`SubscriptionCancellationResult.blocked_but_billing_owner_
  notified_at_cleared`として返すようにした。`OUTCOME_ALREADY_CANCELLED`(Webhook再送)の
  場合は早期returnのためクリア処理自体を通らず、二重クリアは発生しない。
- テスト11件追加(process_follow_event側3件・clear_blocked_but_billing_owner_notified_at
  単体4件・handle_subscription_deleted側4件)、venture全体598件全件
  (`python3 -m unittest discover -p "test_*.py"`、prototype/ディレクトリで実行)パス・
  schema検証25件パスを確認した。
- 実際にこの2箇所(LINE follow Webhook・Stripe `customer.subscription.deleted`
  Webhook)を呼び出すエントリポイント本体、および実Firestore接続自体は、他の各種
  Webhookハンドラと同じく引き続き次回以降の課題(実クラウド接続はオーナー承認待ち)。
