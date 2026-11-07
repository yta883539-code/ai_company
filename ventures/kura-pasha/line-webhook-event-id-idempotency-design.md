# LINE Webhook `webhookEventId`べき等性(重複配信)対策設計(フェーズ286)

作成日: 2026-11-07(フェーズ286)

フェーズ285まで、本venture・aircon-pasha・course-set-pashaはStripe Webhookの
`event.id`べき等性対策(stripe-event-idempotency-design.md、フェーズ77)を横断棚卸し・
是正してきた。一方、同じ「Webhookは重複配信されうる」というat-least-once配信の性質は
LINE Messaging API Webhookにも当てはまるにもかかわらず、本venture・aircon-pasha・
course-set-pashaのいずれも(line-reservation-aiを除く)LINE Webhook受信側には
イベント単位のべき等性チェックが一度も実装されていなかった。本フェーズはこのギャップを
発見し、本venture自身について是正する。

## 1. 背景・問題の発見

WebSearchでLINE Messaging API公式ドキュメント・関連解説記事を確認した結果、以下の仕様を
確認した。

- LINE Platformはbotサーバーへwebhookを送信した際、**2秒以内に応答が返らないと
  `request_timeout`として記録する**(LINE公式: Check webhook error statistics、
  developers.line.biz/en/docs/messaging-api/check-webhook-error-statistics/)。
  タイムアウトは「botサーバーが未受信」を保証するものではなく、実際には受信済みの場合もある
  (応答が間に合わなかっただけ)。
- Webhook再送(redelivery)はチャネルごとのオプトイン機能であり、有効化されている場合
  botサーバーからの応答が得られないとLINE Platformが再送を試み、最終的に応答が得られない
  まま終了すると「Webhook redelivery stopped」通知がオーナーへ送られる。再送回数・間隔自体は
  公式には明記されていない(Hookdeckの解説記事調べ)。
- 重複配信を検知するための仕組みとして、LINE公式は各webhookイベントオブジェクトが持つ
  **`webhookEventId`**(再送であっても同一値を維持する一意なID)を使って重複排除する
  ことを推奨している。再送か否かは`deliveryContext.isRedelivery`で判別できる。

本venture(kura-pasha)・aircon-pasha・course-set-pashaの3ventureは、いずれも
「LINE Webhook受信→署名検証→LLM呼び出し(3種出力生成)→機械チェック→
usage_counter加算→LINE返信送信」までを**1つのCloud Function内で同期処理**する設計
(各venture側deployment-runbook.md「ステップ4」参照)であり、course-set-pasha側の
当該記述は「応答時間の見込み(LLM呼び出し1回分)がLINE Webhookのタイムアウト内に収まる
想定のため、現時点では非同期化は不要と判断」としていた。しかし上記の通りLINEの実際の
タイムアウトは2秒であり、LLM API呼び出し(構造化出力生成)は通常これを大きく超える
(数秒〜十数秒)。したがって、この3ventureは**実運用で日常的に`request_timeout`に
該当し、チャネル側でWebhook再送が有効化されていれば同一メモに対しLLM呼び出し・LINE返信・
usage_counter加算が複数回実行されるリスクが高い**ことが判明した(course-set-pasha
deployment-runbook.mdの上記想定は訂正が必要な誤った前提だったことになる)。

実害の具体例:
1. 同じ施工メモに対しLLM呼び出しが複数回行われる(LLM APIコスト増)。
2. 同じ内容のLINE返信が利用者へ複数回届く(体験の劣化)。
3. `usage_counter`(trial-end-notification-design.md・limit-approaching-notification-
   design.md等が参照する月次生成回数)が1件のメモに対し複数回加算される(利用者が
   実際より早く上限に達してしまう、課金判定に影響しうる実害)。

Stripe側の`event.id`対策(stripe-event-idempotency-design.md)と異なり、本件は
`checkout.session.completed`のような「一部ハンドラのみべき等でない」話ではなく、
**message/follow/unfollow/postbackいずれのイベント種別でも同期処理している限り
日常的にタイムアウト条件を満たしうる**ため、種別を問わず一律にエントリポイント層で
防ぐ設計とする。

## 2. 設計方針(Stripe版と同じ発想、キーをwebhookEventIdに翻案)

- `webhookEventId`(LINEイベントオブジェクトの一意なID)を処理済みイベントIDの集合として
  保持し、2回目以降の同一`webhookEventId`受信時はハンドラを一切呼び出さず
  (副作用ゼロで)スキップする方式とする。
- `dispatch_webhook_events()`のエントリポイント層で一括して弾く(個別ハンドラごとの
  べき等性を作り込まない)。理由はStripe版2節と同じ: (1)将来ハンドラが増えるたびに
  個別対応が必要になる構造を避けたい、(2)署名検証と同じ「エントリポイント層での一括処理」
  という既存の設計思想と一貫する。Stripe版との違いとして、message/follow/unfollow/postback
  いずれの種別にも一律に適用する(Stripe版は`event.id`チェック自体は全イベント種別に
  適用済みなので、この点はむしろ一致している)。
- Protocol定義(`LineWebhookEventIdStoreProtocol`):
  - `has_processed(webhook_event_id: str) -> bool`
  - `mark_processed(webhook_event_id: str) -> None`
- `webhook_event_id_store`は`dispatch_webhook_events()`・`receive_webhook()`双方の
  新規キーワード専用引数(デフォルト`None`)とし、未指定時は従来通りべき等性チェックを
  一切行わない(既存呼び出し経路への後方互換措置、Stripe版と同じ)。
- `webhookEventId`が欠落している、または文字列でない場合はべき等性チェックをスキップし
  従来通り処理する(Stripe版の`event.id`欠落時と同じ理由。テスト用の最小イベントdict等で
  省略されることがあるため、安全側〈処理を止めない〉に倒す)。
- 記録タイミング: 各ハンドラ呼び出し「後」に`mark_processed()`を呼ぶ(ハンドラ内で例外が
  飛んだ場合に未処理のまま処理済み扱いになる事故を避けるため、Stripe版と同じ理由)。
- 検知結果は`DispatchResult.duplicate_webhook_event_ids`(新規フィールド)に記録する。
  Stripe側は200応答に差を付けない設計だったが、本件もLINE側には200を返す点は同じ
  (`receive_webhook()`は重複検知の有無にかかわらずstatus_code=200を返す。LINE Platformに
  エラーを返しても再送を招くだけで解決にならないため)。

## 3. 実装(フェーズ286)

`prototype/cloud_function_webhook.py`に以下を実装した。

- `LineWebhookEventIdStoreProtocol` / `InMemoryLineWebhookEventIdStore`
  (Stripe版`InMemoryStripeEventIdStore`と同じ構造、実Cloud Functions環境ではプロセスを
  またいで保持されない既知の限界も同じ)。
- `DispatchResult.duplicate_webhook_event_ids: List[str]`(新規フィールド)。
- `dispatch_webhook_events()`のループ先頭で、`event_type`による分岐より前に
  `webhookEventId`の処理済みチェックを行い、処理済みならハンドラを呼ばずスキップする。
  各ハンドラ呼び出し(message/follow/unfollow/postback)の直後に`mark_processed()`を
  呼ぶ(ignored_types行き〈依存未接続〉の場合は記録しない。実際に処理されていないため、
  後で依存が接続された際に改めて処理できるようにする安全側の判断)。
- `receive_webhook()`に`webhook_event_id_store`引数を追加し、そのまま
  `dispatch_webhook_events()`へ橋渡しする。

新規テスト7件(test_cloud_function_webhook.py、355件→371件〈check()呼び出し数ベース〉)
を追加し、以下を確認した。
- 処理済み`webhookEventId`のイベントはLLM呼び出し・返信のいずれも行われない。
- 1回目処理後にストアへ記録される。
- 同一イベントが2回のdispatch呼び出し(=2回のHTTPリクエストを模擬)にまたがっても
  2回目は副作用ゼロ。
- `webhook_event_id_store`未指定時は従来通り毎回処理される(後方互換)。
- `webhookEventId`欠落時はチェックをスキップし通常通り処理される(安全側)。
- unfollow(依存関係を問わず常に処理される特殊な種別)にもチェックが一律に効く。
- `receive_webhook()`経由でも`webhook_event_id_store`がそのまま効き、200応答自体は
  変わらない。

既存テスト(`python3 -m unittest discover -s prototype -p "test_*.py"`300件、
`python3 schema/validate_test_cases.py`32件)はいずれも変更なしでパスし、回帰がない
ことを確認した。

## 4. 未検証・残課題

- **InMemory実装の限界**: 実Cloud Functions環境では呼び出しをまたいで状態が保持されない
  (Stripe版と同じ既知の限界)。実装時(オーナー承認後)はFirestoreアダプタへの差し替えが
  必要(`firestore-provider-adapter-design.md`相当のパターンを流用できる見込み)。
- **TTL設計**: `webhookEventId`の処理済み記録を無期限に保持し続けるとFirestore容量が
  肥大化するため、一定期間(LINE側の再送が発生しうる現実的な期間、例えば数日〜1週間)で
  失効させるTTL設計が必要(data-retention-policy.mdとの整合も含め次回以降の課題)。
- **根本対策の要否**: 本フェーズの対策は「重複実行を防ぐ」対症療法であり、
  「2秒タイムアウトに収まるよう処理自体を非同期化する」(line-reservation-aiの
  Cloud Tasksエンキューパターンへの移行)という根本対策とは別物。後者は3venture共通の
  アーキテクチャ変更(Function分割)を要し、本ventureの低頻度・オーダーメイド中心という
  特性(deployment-runbook.md参照)を踏まえると費用対効果の検討が必要なため、
  今回は対症療法(べき等性チェック)のみを先行させた。
- **aircon-pasha・course-set-pashaへの横展開**: 本件は3venture共通のアーキテクチャ上の
  ギャップだが、今回は「7venture中最も更新が止まっていたventure」である本venture側のみ
  是正した。aircon-pasha・course-set-pashaは次回以降、それぞれが選ばれた回で同様の
  対策を横展開する必要がある(本design doc・実装をそのまま参照・翻案できる)。
- **実際の再送有無の確認**: LINE Developersコンソールでの「Webhook再送」設定が実際に
  オンになるかどうかはLINE公式アカウント開設(オーナー承認待ち)後でなければ確認できない。
  仮にオフのままであれば2秒タイムアウト自体は発生しても再送による重複処理は起きないが、
  「オフであることを前提に対策を省略する」のはリスクが高い(将来の設定変更・LINE側の
  仕様変更に対して脆弱)と判断し、オフの場合でも無害(副作用ゼロ)な本対策を先行実装した。

## 参考(WebSearch)

- Check webhook error statistics(LINE公式、2秒タイムアウトの記述):
  https://developers.line.biz/en/docs/messaging-api/check-webhook-error-statistics/
- Guide to LINE Webhooks: Features and Best Practices(Hookdeck、再送オプトイン・
  webhookEventIdがULID形式との記述): https://hookdeck.com/webhooks/platforms/guide-to-line-webhooks-features-and-best-practices
- Receive messages (webhook)(LINE公式): https://developers.line.biz/en/docs/messaging-api/receiving-messages/
