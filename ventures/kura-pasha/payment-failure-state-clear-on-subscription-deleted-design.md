# `customer.subscription.deleted`受信時のpayment_failure系状態クリア対応(フェーズ187)

aircon-pashaのフェーズ272(payment-failure-state-clear-on-subscription-deleted-
design.md、line-reservation-aiフェーズ続き273の横断確認を受けた対応)が「次回候補」として
残していた、本venture(kura-pasha)への同種ギャップの横断確認を実施し、実際に同種の欠落が
存在したため対応した。

## 1. 見つかったギャップ

`stripe_webhook.handle_customer_subscription_deleted()`は、`set_subscription_status`
成功時に`clear_blocked_but_billing_owner_notified_at()`(フェーズ81)を常に呼んでいたが、
`payment_failure_detected_at`(猶予期間中、または制限モード移行後に設定される)をクリアする
配線が抜けていた。

この結果、次の理論上のシーケンスが起こり得た。

1. `invoice.payment_failed`受信で`payment_failure_detected_at`が設定される(猶予期間開始)。
2. 猶予期間中に`customer.subscription.deleted`が発火し、`handle_subscription_
   cancelled()`により契約者へ「ご契約が終了しました」という解約完了案内が届く。
3. しかし`payment_failure_detected_at`はクリアされないまま残るため、後日daily_
   scheduler.pyの`select_due_payment_failure_reminders()`・`select_due_payment_
   suspensions()`相当の日次バッチが、既に解約済みのworkshopを誤って再選出してしまう。
4. 結果、解約完了案内済みの契約者に、後日リマインド・制限モード移行通知という矛盾した
   Push通知が届いてしまう。

aircon-pasha・line-reservation-aiと現れ方は同じ「解約確定イベントを受けても、決済失敗系の
旧stateが後続のスケジューラ判定に生き残る」構造のバグである。

## 2. 対応方針

新規のクリア関数は追加せず、既存の`workshop_store.clear_payment_failure_detected_at()`
(usage_counter_workshop.py、`payment_failure_reminder_sent_at`・`payment_suspension_
owner_notified_at`もまとめてクリアする1メソッド方式)を`handle_customer_subscription_
deleted()`から呼ぶ。`workshop_store`は既に`WorkshopStoreProtocol`として受け取っている
ため、新規引数は不要。設定済み(not None)の場合のみクリアする(no-op時に余計な書き込みを
発生させないため、既存の`clear_blocked_but_billing_owner_notified_at`呼び出しとは異なる
挙動だが、`payment_failure_notification.py`側の`handle_payment_succeeded`が同じ
「設定済みの場合のみ」パターンを既に採用しているため踏襲した)。

aircon-pashaは4フィールド別々のクリアだったが、本ventureは元々`clear_payment_failure_
detected_at()`が3フィールド(`payment_failure_detected_at`・`payment_failure_reminder_
sent_at`・`payment_suspension_owner_notified_at`)をまとめてクリアする設計のため、
呼び出しは1行で済む。

## 3. 実装

`prototype/stripe_webhook.py`の`handle_customer_subscription_deleted()`に以下を追加した。

```python
if workshop_store.get_payment_failure_detected_at(workshop_id) is not None:
    workshop_store.clear_payment_failure_detected_at(workshop_id)
```

## 4. テスト

`prototype/test_stripe_webhook.py`に2件追加した。

- `test_deleted_clears_payment_failure_detected_at`: 猶予期間中(`payment_failure_
  detected_at`設定済み)に解約が確定した場合、クリアされることを確認。
- `test_deleted_clear_payment_failure_is_no_op_when_unset`: 未検知のworkshopでも
  エラーにならず、Noneを維持することを確認。

venture全体171件(既存169件+新規2件)・schema検証32件いずれもパス。

## 5. 未検証・残課題

- 実Stripe・実Firestore接続時の動作確認はオーナー承認待ちのため未実施(机上・InMemory
  Stubでの検証のみ)。
- 他2venture(course-set-pasha・line-reservation-ai)への横展開可否も本フェーズで簡易
  点検した。
  - course-set-pashaの`stripe_webhook.py``customer.subscription.deleted`分岐
    (`mark_deletion_candidate_on_subscription_deleted`呼び出し箇所)は、
    `blocked_but_billing_owner_notified_at`のクリアは行っているが、
    `usage_counter.clear_payment_failure_detected_at()`/
    `clear_payment_failure_reminder_sent_at()`への配線が同様に欠落しており、本venture・
    aircon-pashaと同種のバグが**未対応のまま残っている**ことを確認した。本フェーズでは
    本venture(kura-pasha)のみを対応対象としたため、course-set-pasha側の実装修正は
    次回以降の課題として残す。
  - line-reservation-aiは`route_stripe_event()`が「イベント種別判定・store_id解決のみを
    行う薄いルータ」であり、`handle_payment_succeeded()`等の実際のハンドラ呼び出し・
    Firestore読み書きの統合エントリポイント自体がdesign「残課題」としてまだ実装されて
    いない(stripe_webhook.py冒頭コメント参照)。したがって現時点では本バグクラスの
    対象となる実装自体が存在せず、「対応済み」でも「欠落」でもない状態である。統合
    エントリポイント実装時にあわせて本パターンを組み込む必要がある旨を申し送る。
