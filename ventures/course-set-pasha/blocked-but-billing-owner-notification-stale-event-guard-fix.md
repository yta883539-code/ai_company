# blocked_but_billing_owner_notified_at クリアのstale判定漏れ是正

## 経緯

aircon-pasha/course-set-pasha/kura-pasha/line-reservation-aiの4venture横断で、
`customer.subscription.deleted`受信時の副作用処理を「配信順序入れ替わり(stale)なら
まとめてスキップする」方針(subscription-event-out-of-order-guard-design.md、
フェーズ263で本venture自身が最初に導入)へ統一する棚卸しが続いていた
(aircon-pashaフェーズ280〜283、kura-pasha、line-reservation-aiフェーズ続き286)。

本フェーズであらためて`prototype/stripe_webhook.py`の`dispatch_stripe_event()`
`customer.subscription.deleted`分岐を確認したところ、
`user_profile_store.clear_blocked_but_billing_owner_notified_at(user_id)`
(blocked-but-billing-owner-notification-design.md 4節、フェーズ144)の呼び出しが、
`is_stale_deleted_event`の算出より前に無条件で実行されたまま残っていることに気づいた。
この呼び出しはフェーズ263より前(フェーズ144)に追加された既存処理であり、フェーズ263で
stale全体スキップ方針を導入した際にこの箇所が対象から漏れていた
(aircon-pashaフェーズ283が発見・是正した同種の非対称〈plan_store・
blocked_but_billing_store〉と同じパターンだが、本venture自身のこの箇所は
これまで見落とされていた)。

## 問題

`blocked_but_billing_owner_notified_at`は「利用上限超過中かつ課金継続中」の状態を
オーナーへ一度だけ通知したことを記録するフラグで、`customer.subscription.deleted`
受信時にクリアされる設計(解約確定後に再契約した顧客が再び同状態になった場合、
新しい契約サイクルとして再度通知できるようにするため)。

Stripe Webhookは配信順序を保証しないため、実際には以下のように解約→即再契約の後に
古いdeletedイベントが遅延到着するケースがありうる。

1. `customer.subscription.deleted`(T1、解約)
2. `customer.subscription.created`(T2、即再契約、T2 > T1)
3. 再契約後に再び利用上限超過となり、`blocked_but_billing_owner_notified_at`が
   新しい契約サイクルで一度セットされる
4. T1のdeletedイベントがWebhookリトライ等で遅延し、3より後に届く

このとき、是正前の実装では手順4で`clear_blocked_but_billing_owner_notified_at()`が
無条件に実行され、手順3でセットしたばかりの「通知済み」フラグを誤ってクリアしてしまう。
その結果、実際には既に一度通知済みの状態に対して、次回の判定タイミングで重複通知が
飛んでしまう(データ破損ではないが、他の3箇所〈決済失敗フィールドクリア・
subscription_canceled_at設定・解約確定案内通知〉と同じ非対称バグ)。

## 対応

`is_stale_deleted_event`の算出位置を`mark_deletion_candidate_on_subscription_deleted()`
呼び出しの直後に据え置いたまま、`clear_blocked_but_billing_owner_notified_at()`の
呼び出しを`is_stale_deleted_event`算出の後へ移動し、`user_profile_store is not None
and not is_stale_deleted_event`でガードした(他の3箇所と同じ「stale全体スキップ」方針
への統一)。`usage_counter`未指定時は`_is_stale_subscription_state_event()`が常に
`False`を返すため、既存の`test_subscription_deleted_clears_blocked_but_billing_owner_
notified_at`(usage_counter未指定)を含む既存テストへの影響はない。

## 検証

- 新規テスト`test_stale_subscription_deleted_does_not_clear_blocked_but_billing_owner_
  notified_at`(test_stripe_webhook.py)を追加。より新しいcreatedイベント反映後に
  古いdeletedイベントが届いても`blocked_but_billing_owner_notified_at`がクリアされない
  ことを確認。
- `python3 -m unittest discover -s prototype -p "test_*.py"`: 686件(既存685件+新規1件)
  いずれもパス。
- `python3 schema/validate_test_cases.py`: 21件全件パス(変更なし、本フィールドは
  LLM構造化出力に登場しないため影響なし)。

## 次の課題

- 本フェーズの発見は「フェーズ263で先行して自ventureに導入した方針が、フェーズ263より
  前に存在していた既存処理まで遡って適用されていなかった」という見落としパターン。
  今後、新しい横断方針を導入する際は、その方針より前から存在する同種の副作用処理が
  他にも残っていないか、`grep`等で網羅的に洗い出してから対象を確定させることを教訓と
  したい。
