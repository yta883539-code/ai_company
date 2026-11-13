# LINE Webhook `webhookEventId`べき等性(重複配信)対策設計・実装(フェーズ379)

作成日: 2026-11-13(フェーズ379)

kura-pashaフェーズ286・287・course-set-pashaフェーズ368で発見・是正された「本venture・
kura-pasha・course-set-pashaの3ventureはいずれもStripe Webhook側
(stripe-event-idempotency-design.md)のべき等性対策は済んでいるが、LINE Messaging API
Webhook側には一度もイベント単位のべき等性チェックが実装されていない」というギャップが、
kura-pasha版「4節 aircon-pasha・course-set-pashaへの横展開」に次回以降の課題として
残っていた(course-set-pasha側は既にフェーズ368で対応済み)。本フェーズでは本venture
(aircon-pasha)側を是正する(kura-pasha版をそのまま翻案、設計・実装・テストまで本フェーズ内で
完了させた)。

## 1. 背景・問題

kura-pasha版1節で確認済みの通り、LINE Platformはbotサーバーへwebhook送信時に
**2秒以内に応答が返らないと`request_timeout`として記録する**(LINE公式: Check webhook
error statistics)。タイムアウトは「botサーバーが未受信」を保証するものではなく、実際には
受信済みの場合もある。Webhook再送(redelivery)が有効化されている場合、LINE Platformは
応答が得られないbotサーバーに対し再送を試みる。重複配信の検知には、各webhookイベント
オブジェクトが持つ**`webhookEventId`**(再送であっても同一値を維持する一意なID)を使う
ことがLINE公式に推奨されている。

本venture(aircon-pasha)は、他venture同様「Webhook受信→署名検証→メモ本文の抽出→
LLM呼び出し(3出力生成)→post_generation_checks.pyによる機械チェック→usage_counterへの
加算・上限接近通知判定→LINE返信送信」までを**1つのCloud Function内で同期処理**する設計
(`process_memo_event()`、`cloud_function_webhook.py`)であり、LLM API呼び出し(構造化
出力生成)は通常LINEのタイムアウト(2秒)を大きく超える(数秒〜十数秒)。したがって本venture
も**実運用で日常的に`request_timeout`に該当し、チャネル側でWebhook再送が有効化されていれば
同一メモに対しLLM呼び出し・LINE返信・usage_counter加算が複数回実行されるリスクが高い**
(kura-pasha版・course-set-pasha版と同じ構造)。

本フェーズの着手前に`ventures/aircon-pasha/`配下を`webhookEventId`で検索したところ0件
であり、kura-pasha版が指摘していたギャップ(本venture側に同種対策が一度も実装されていない
こと)を確認した。また本venture固有の事情として、`process_memo_event()`自体が
owner-faq-routing-design.md(FAQ固定応答)・chatbot-intent-router-webhook-wiring-
design.md(意図分類)という、course-set-pashaフェーズ368が対象とした分岐構造と同種の
複数経路を既に持っていること、かつ`dispatch_webhook_events()`がfollow/message/unfollow/
postbackの4種別を扱う点(message/unfollowの2種別のみを扱うcourse-set-pasha・kura-pasha
よりpostbackが1種別多い)を確認した。kura-pasha版は既にpostbackを含む4種別対応版の
設計・実装を済ませているため、本フェーズはkura-pasha版をそのまま翻案する。

実害の具体例(kura-pasha版2節と同型):
1. 同じ施工メモに対しLLM呼び出しが複数回行われる(LLM APIコスト増)。
2. 同じ内容のLINE返信が利用者へ複数回届く(体験の劣化)。
3. `usage_counter`(limit-approaching-notification-design.md等が参照する月次生成回数)が
   1件のメモに対し複数回加算される(利用者が実際より早く上限に達してしまう、課金判定に
   影響しうる実害)。
4. トライアル専用生成回数カウンタ(`increment_trial_generation_count()`)やトライアル終了
   通知(`set_trial_end_notified_at()`)も同様に複数回実行されうる。

follow/message/unfollow/postbackいずれのイベント種別でも同期処理している限り日常的に
タイムアウト条件を満たしうるため、種別を問わず一律にエントリポイント層で防ぐ設計とする。

## 2. 設計方針(kura-pasha版と同じ発想、本venture固有の関数名・構造に翻案)

- `webhookEventId`を処理済みイベントIDの集合として保持し、2回目以降の同一
  `webhookEventId`受信時はハンドラ(`process_follow_event()`/`process_message_event()`/
  `process_unfollow_event()`/`process_postback_event()`)を一切呼び出さず(副作用ゼロで)
  スキップする方式とする。
- `dispatch_webhook_events()`のエントリポイント層で一括して弾く(個別ハンドラごとの
  べき等性を作り込まない。stripe_webhook.pyの`event_id_store`と同じ設計思想)。
- Protocol定義(`LineWebhookEventIdStoreProtocol`、kura-pasha版と同一シグネチャ):
  - `has_processed(webhook_event_id: str, *, now: Optional[datetime] = None) -> bool`
  - `mark_processed(webhook_event_id: str, *, now: Optional[datetime] = None) -> None`
- `webhook_event_id_store`は`dispatch_webhook_events()`・`receive_webhook()`双方の新規
  キーワード専用引数(デフォルト`None`)とし、未指定時は従来通りべき等性チェックを一切
  行わない(既存呼び出し経路への後方互換措置)。
- `webhookEventId`が欠落している、または文字列でない場合はべき等性チェックをスキップし
  従来通り処理する(安全側に倒す)。
- 記録タイミング: 各ハンドラ呼び出し「後」に`mark_processed()`を呼ぶ(ハンドラ内で例外が
  飛んだ場合に未処理のまま処理済み扱いになる事故を避けるため)。依存関係未接続のため
  当該イベント種別のループ自体に到達しない場合(例: `reply_client`未接続時のfollow)は
  記録しない(実際に処理されていないため、依存が接続された際に改めて処理できるようにする
  安全側の判断)。
- 検知結果は`DispatchResult.duplicate_webhook_event_ids`(新規フィールド)に記録する。
  LINE側には重複検知の有無にかかわらず200を返す(`receive_webhook()`の既存方針を維持)。
- **TTL**: kura-pashaフェーズ287で解消済みのTTL設計をそのまま採用する(本venture側は
  「発見」のステップを経ず最初からTTL込みで実装する)。
  `DEFAULT_LINE_WEBHOOK_EVENT_ID_TTL_SECONDS = 7日(604800秒)`。
  `InMemoryLineWebhookEventIdStore`は`webhook_event_id`ごとに`processed_at`を
  `dict[str, datetime]`で保持し、`has_processed()`はTTL以内の場合のみ`True`を返す。

## 3. 実コードへの反映(本フェーズで実装済み)

`prototype/cloud_function_webhook.py`に以下を実装した。

- `LineWebhookEventIdStoreProtocol` / `InMemoryLineWebhookEventIdStore` /
  `DEFAULT_LINE_WEBHOOK_EVENT_ID_TTL_SECONDS`(kura-pasha版と同じ構造)。
- `DispatchResult.duplicate_webhook_event_ids: list`(新規フィールド)。
- `dispatch_webhook_events()`は、本venture既存の「イベント種別ごとに`events`から
  フィルタしたリストを作り、依存関係が揃っている場合のみループ処理する」という既存構造
  (kura-pasha版の単一for文+if/elif分岐とは異なる)を維持したまま、冒頭で`events`全体を
  一度だけ走査して処理済み`webhookEventId`を除いた`effective_events`を作り、以降の
  follow_events/message_events/unfollow_events/postback_events・`ignored_types`判定は
  すべて`effective_events`から行うように変更した。各ハンドラ呼び出しの直後に
  `_mark_processed()`ヘルパー(内部関数)で記録する。既存の依存関係ガード(reply_client
  未接続時にfollowを素通りする等)の挙動は変更していない。
- `receive_webhook()`に`webhook_event_id_store`引数を追加し、そのまま
  `dispatch_webhook_events()`へ橋渡しした。

新規テスト12件(`test_cloud_function_webhook.py`、`LineWebhookEventIdIdempotencyTest`
8件・`LineWebhookEventIdStoreTtlTest`4件)を追加し、以下を確認した。
- 処理済み`webhookEventId`のfollow/unfollow/messageイベントはハンドラ呼び出し・返信の
  いずれも行われず、`duplicate_webhook_event_ids`に記録される。
- 1回目処理後にストアへ記録され、2回目のdispatch呼び出し(Webhook再送を模擬)では
  副作用ゼロになる。
- `webhook_event_id_store`未指定時は従来通り毎回処理される(後方互換)。
- `webhookEventId`欠落時はチェックをスキップし通常通り処理される(安全側)。
- `receive_webhook()`経由でも`webhook_event_id_store`がそのまま効き、200応答自体は
  変わらない。
- `InMemoryLineWebhookEventIdStore`のTTL(7日以内は処理済み、超過後は未処理扱いに戻り
  再処理可能、デフォルトTTLが604800秒であること)。

既存テスト(`python3 -I -m unittest discover -s prototype -p "test_*.py"`803件、
`python3 -I schema/validate_test_cases.py`25件)はいずれも変更なしでパスし、回帰がない
ことを確認した(新規12件を加えた全815件もパス)。承認が必要なアクション(支払い・
アカウント作成・外部公開・送信等)は今回発生していないためpending-approval.mdへの
追記なし。

## 4. 未検証・残課題

- **InMemory実装の限界**: 実Cloud Functions環境では呼び出しをまたいで状態が保持されない
  (Stripe版・kura-pasha版と同じ既知の限界)。実装時(オーナー承認後)はFirestoreアダプタへの
  差し替えが必要(`firestore-provider-adapter-design.md`相当のパターンを流用できる見込み)。
- **根本対策の要否**: 本対策は「重複実行を防ぐ」対症療法であり、「2秒タイムアウトに収まる
  よう処理自体を非同期化する」(line-reservation-aiのCloud Tasksエンキューパターンへの
  移行)という根本対策とは別物。course-set-pashaフェーズ369〜372がこの根本対策を
  Function A/B構成(`process_memo_event_async`新設)として設計・実装済みであり、
  course-set-pashaフェーズ372「次回候補(2)」は本venture(aircon-pasha)への横展開を
  検討する際に「postbackアクション中心でFAQキーワード一致方式を採用していない可能性が
  あるため個別確認が必要」としていた。本フェーズで`process_memo_event()`の実装
  (owner-faq-routing-design.md準拠のFAQ固定応答分岐・chatbot-intent-router-webhook-
  wiring-design.md準拠の意図分類分岐)を確認した結果、**本ventureもcourse-set-pasha同様
  FAQキーワード一致方式を採用しており(「FAQ」「Q1」〜「Q7」)、postbackは別イベント種別
  (決済・ポータルURL取得専用、LLM呼び出しを含まない)として並存している**ことが判明した。
  したがってFunction A/B分割の対象はmessageイベントのみでよく、course-set-pashaの
  `process-memo-event-async-split-design.md`をそのまま翻案可能と判断した(postback
  イベント自体はLLM呼び出しを含まないため非同期化の対象外)。本件の設計ドキュメント化・
  実装は次回以降の課題として残す(本フェーズはwebhookEventIdべき等性対策〈対症療法〉のみ
  に範囲を絞った)。
- **実際の再送有無の確認**: LINE Developersコンソールでの「Webhook再送」設定が実際に
  オンになるかどうかはLINE公式アカウント開設(オーナー承認待ち)後でなければ確認できない。
  オフの場合でも無害(副作用ゼロ)な本対策を先行実装した(kura-pasha版と同じ判断)。
- **event-komiguai-pasha・forklift-pasha・oshien-pashaへの横展開**: 本フェーズ着手前に
  7venture全体を`webhookEventId`で横断検索した結果、本venture・event-komiguai-pasha・
  forklift-pasha・oshien-pashaの4ventureが未対応(kura-pasha・course-set-pasha・
  line-reservation-aiの3ventureは対応済み)であることを確認した。本フェーズで
  aircon-pashaが対応済みとなり、残る3ventureはそれぞれが「7venture中最も更新が止まって
  いたventure」として選ばれた回に、本design doc・kura-pasha版をそのまま参照・翻案して
  対応する想定。

## 参考(kura-pasha版・course-set-pasha版が確認済みのWebSearch結果を再利用、本フェーズでの
追加検索は無し)

- Check webhook error statistics(LINE公式、2秒タイムアウトの記述):
  https://developers.line.biz/en/docs/messaging-api/check-webhook-error-statistics/
- Guide to LINE Webhooks: Features and Best Practices(Hookdeck、再送オプトイン・
  webhookEventIdがULID形式との記述):
  https://hookdeck.com/webhooks/platforms/guide-to-line-webhooks-features-and-best-practices
- Receive messages (webhook)(LINE公式):
  https://developers.line.biz/en/docs/messaging-api/receiving-messages/
