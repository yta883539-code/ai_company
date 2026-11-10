# LINE Webhook `webhookEventId`べき等性(重複配信)対策設計(フェーズ368)

作成日: 2026-11-10(フェーズ368)

kura-pashaフェーズ286・287で発見・是正された「本venture・aircon-pasha・kura-pashaの
3ventureはいずれもStripe Webhook側(stripe-event-idempotency-design.md)のべき等性対策は
済んでいるが、LINE Messaging API Webhook側には一度もイベント単位のべき等性チェックが
実装されていない」というギャップが、kura-pasha側のline-webhook-event-id-idempotency-
design.md「4節 aircon-pasha・course-set-pashaへの横展開」に次回以降の課題として残っていた。
本フェーズでは本venture(course-set-pasha)側を是正する(kura-pasha版をそのまま翻案)。

## 1. 背景・問題

kura-pasha版1節で確認済みの通り、LINE Platformはbotサーバーへwebhook送信時に
**2秒以内に応答が返らないと`request_timeout`として記録する**(LINE公式: Check webhook
error statistics、developers.line.biz/en/docs/messaging-api/check-webhook-error-
statistics/)。タイムアウトは「botサーバーが未受信」を保証するものではなく、実際には
受信済みの場合もある。Webhook再送(redelivery)が有効化されている場合、LINE Platformは
応答が得られないbotサーバーに対し再送を試みる。重複配信の検知には、各webhookイベント
オブジェクトが持つ**`webhookEventId`**(再送であっても同一値を維持する一意なID)を使う
ことがLINE公式に推奨されている。

本venture(course-set-pasha)は、deployment-runbook.md ステップ4の通り
「Webhook受信→署名検証→メモ本文の抽出→LLM呼び出し(3出力生成)→post_generation_checks.py
による機械チェック→usage_counterへの加算・上限接近通知判定→LINE返信送信」までを
**1つのCloud Function内で同期処理**する設計であり、同ステップは
「応答時間の見込み(LLM呼び出し1回分)がLINE Webhookのタイムアウト内に収まる想定のため、
現時点では不要と判断」としていた。しかしkura-pasha版が確認した通りLINEの実際のタイムアウトは
2秒であり、LLM API呼び出し(構造化出力生成)は通常これを大きく超える(数秒〜十数秒)。
したがって本ventureも**実運用で日常的に`request_timeout`に該当し、チャネル側でWebhook
再送が有効化されていれば同一メモに対しLLM呼び出し・LINE返信・usage_counter加算が複数回
実行されるリスクが高い**(deployment-runbook.mdの上記想定は訂正が必要な誤った前提
だったことになる、kura-pasha版と同じ構造)。

実害の具体例(kura-pasha版2節と同型):
1. 同じメモに対しLLM呼び出しが複数回行われる(LLM APIコスト増)。
2. 同じ内容のLINE返信が利用者へ複数回届く(体験の劣化)。
3. `usage_counter`(trial-end-notification-design.md・limit-approaching-notification-
   design.md等が参照する月次生成回数)が1件のメモに対し複数回加算される(利用者が実際より
   早く上限に達してしまう、課金判定に影響しうる実害)。

message/follow/unfollowいずれのイベント種別でも同期処理している限り日常的にタイムアウト
条件を満たしうるため、種別を問わず一律にエントリポイント層で防ぐ設計とする。

## 2. 設計方針(kura-pasha版と同じ発想、本venture固有の関数名に翻案)

- `webhookEventId`を処理済みイベントIDの集合として保持し、2回目以降の同一
  `webhookEventId`受信時はハンドラ(`process_follow_event()`/`process_memo_event()`/
  `process_unfollow_event()`)を一切呼び出さず(副作用ゼロで)スキップする方式とする。
- `dispatch_webhook_events()`のエントリポイント層で一括して弾く(個別ハンドラごとの
  べき等性を作り込まない。stripe_webhook.pyの`event_id_store`と同じ設計思想)。
- Protocol定義(`LineWebhookEventIdStoreProtocol`):
  - `has_processed(webhook_event_id: str, *, now: Optional[datetime] = None) -> bool`
  - `mark_processed(webhook_event_id: str, *, now: Optional[datetime] = None) -> None`
- `webhook_event_id_store`は`dispatch_webhook_events()`・`receive_webhook()`双方の新規
  キーワード専用引数(デフォルト`None`)とし、未指定時は従来通りべき等性チェックを一切
  行わない(既存呼び出し経路への後方互換措置)。
- `webhookEventId`が欠落している、または文字列でない場合はべき等性チェックをスキップし
  従来通り処理する(テスト用の最小イベントdict等で省略されることがあるため、安全側
  〈処理を止めない〉に倒す)。
- 記録タイミング: 各ハンドラ呼び出し「後」に`mark_processed()`を呼ぶ(ハンドラ内で例外が
  飛んだ場合に未処理のまま処理済み扱いになる事故を避けるため)。`ignored_types`行き
  (follow/message/unfollow以外の種別、またはreply_client/llm_call/linking_store未接続時の
  素通り)の場合は記録しない(実際に処理されていないため、依存が接続された際に改めて
  処理できるようにする安全側の判断)。
- 検知結果は`DispatchResult.duplicate_webhook_event_ids`(新規フィールド)に記録する。
  LINE側には重複検知の有無にかかわらず200を返す(`receive_webhook()`の既存方針を維持。
  LINE Platformにエラーを返しても再送を招くだけで解決にならないため)。
- **TTL**: kura-pashaフェーズ287で解消済みのTTL設計をそのまま採用する。
  `DEFAULT_LINE_WEBHOOK_EVENT_ID_TTL_SECONDS = 7日(604800秒)`。
  `InMemoryLineWebhookEventIdStore`は`webhook_event_id`ごとに`processed_at`
  (mark_processed時刻)を`Dict[str, datetime]`で保持し、`has_processed()`は
  `now - processed_at <= ttl_seconds`の場合のみ`True`を返す。TTL超過時は
  「Firestore側でTTLポリシーにより当該ドキュメントが既に削除された後の状態」と同じ
  (ドキュメント不在=未処理)とみなして`False`を返し、該当エントリをメモリからも削除する
  (遅延GC)。`has_processed()`・`mark_processed()`双方にテスト用の`now`キーワード専用
  引数(省略時は`datetime.now(timezone.utc)`)を持つ(stripe_webhook.pyの
  `handle_checkout_session_completed(now=...)`と同じ時刻注入パターン)。

## 3. 実コードへの反映

`prototype/cloud_function_webhook.py`に以下を実装する。

- `LineWebhookEventIdStoreProtocol` / `InMemoryLineWebhookEventIdStore`
  (stripe_webhook.pyの`InMemoryStripeEventIdStore`・kura-pashaの
  `InMemoryLineWebhookEventIdStore`と同じ構造、実Cloud Functions環境ではプロセスを
  またいで保持されない既知の限界も同じ)。
- `DispatchResult.duplicate_webhook_event_ids: List[str]`(新規フィールド)。
- `dispatch_webhook_events()`のループ先頭(`event_type`による分岐より前)で、各イベントの
  `webhookEventId`の処理済みチェックを行い、処理済みならそのイベントを後続の
  follow/message/unfollow振り分けから除外する。各ハンドラ呼び出し直後に
  `mark_processed()`を呼ぶ。
- `receive_webhook()`に`webhook_event_id_store`引数を追加し、そのまま
  `dispatch_webhook_events()`へ橋渡しする。

実Firestoreアダプタ(`FirestoreLineWebhookEventIdStore`)への差し替えは、
`firestore-provider-adapter-design.md`相当のパターンを流用する想定で、実装は実GCP
プロジェクト作成(オーナー承認待ち)後の課題として残す(stripe_webhook.pyの
`firestore_stripe_event_id_adapter.py`と同型になる見込み)。

## 4. 未検証・残課題

- **InMemory実装の限界**: 実Cloud Functions環境では呼び出しをまたいで状態が保持されない
  (Stripe版・kura-pasha版と同じ既知の限界)。実装時(オーナー承認後)はFirestoreアダプタへの
  差し替えが必要。
- **根本対策の要否**: 本対策は「重複実行を防ぐ」対症療法であり、「2秒タイムアウトに収まる
  よう処理自体を非同期化する」(line-reservation-aiのCloud Tasksエンキューパターンへの
  移行)という根本対策とは別物。後者はdeployment-runbook.mdのFunction分割を要するアーキ
  テクチャ変更であり、本ventureの処理量(月額フリーパス・都度プラン利用者向けの単発メモ
  処理)を踏まえると費用対効果の検討が必要なため、今回は対症療法(べき等性チェック)のみを
  先行させる。
- **aircon-pashaへの横展開**: kura-pashaフェーズ286で発見された3venture共通のギャップの
  うち、本フェーズでkura-pasha・course-set-pashaの2件が対応済みとなり、aircon-pashaのみ
  残る。aircon-pashaが次回以降「7venture中最も更新が止まっていたventure」として選ばれた
  回に、本design doc・kura-pasha版をそのまま参照・翻案して対応する。
- **deployment-runbook.mdステップ4の記述修正**: 「応答時間の見込み(LLM呼び出し1回分)が
  LINE Webhookのタイムアウト内に収まる想定のため、現時点では不要」という既存記述は
  上記1節の通り誤った前提だったため、本フェーズで修正する(deployment-runbook.md参照)。
- **実際の再送有無の確認**: LINE Developersコンソールでの「Webhook再送」設定が実際にオンに
  なるかどうかはLINE公式アカウント開設(オーナー承認待ち)後でなければ確認できない。
  オフの場合でも無害(副作用ゼロ)な本対策を先行実装する(kura-pasha版と同じ判断)。

## 参考(kura-pasha版が確認済みのWebSearch結果を再利用、本フェーズでの追加検索は無し)

- Check webhook error statistics(LINE公式、2秒タイムアウトの記述):
  https://developers.line.biz/en/docs/messaging-api/check-webhook-error-statistics/
- Guide to LINE Webhooks: Features and Best Practices(Hookdeck、再送オプトイン・
  webhookEventIdがULID形式との記述):
  https://hookdeck.com/webhooks/platforms/guide-to-line-webhooks-features-and-best-practices
- Receive messages (webhook)(LINE公式):
  https://developers.line.biz/en/docs/messaging-api/receiving-messages/
