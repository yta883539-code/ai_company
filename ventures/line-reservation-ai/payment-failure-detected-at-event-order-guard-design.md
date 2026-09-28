# payment_failure_detected_at側イベント順序保証ガード設計

subscription-event-order-guard-design.md(フェーズ続き282)が「次回候補」として残していた
「`cloud_function_payment_webhook.py`の`handle_payment_succeeded()`/`handle_payment_failed()`
との間の順序入れ替わり(dunning側)」の検討・対応。

## 1. 発見した欠落

`handle_payment_succeeded()`(`payment_succeeded`受信)と`handle_payment_failed()`
(`invoice.payment_failed`受信)は、いずれもStripe Webhookの配信順序が保証されない
前提を考慮せず、届いた順にそのまま状態を書き換えていた。

- **ケースB(決済成功の遅延配信)**: `invoice.payment_failed`でdunningを検知した後、
  それより前に発生していた(が遅延配信された)`payment_succeeded`が届くと、
  `classify_payment_succeeded()`は`payment_failure_detected_at`が設定済みであることしか
  見ないため、進行中の(実際にはまだ解決していない)dunningを誤って解除し、
  「お支払いを確認しました」という事実と異なる通知を送ってしまう。
- **ケースA(決済失敗の遅延配信、ケースBと対称)**: 逆に、`payment_succeeded`で
  dunningが解決(`payment_failure_detected_at`がNoneに戻る)した後、それより前に発生して
  いた(が遅延配信された)`invoice.payment_failed`が届くと、`handle_payment_failed()`は
  `payment_failure_detected_at`がNoneであることしか見ないため、既に解決済みのdunning
  サイクルを誤って再開させてしまう。

いずれもsubscription-event-order-guard-design.mdが発見したケースA/Bと同種の欠落。

## 2. 対応

`StoreDunningState`(cloud_function_send_dunning_notifications.py)に
`last_payment_event_time: datetime | None = None`を追加した。既存の
`payment_failure_detected_at`(dunningスケジュールの起点。`handle_payment_failed()`の
`event_time`引数は処理時刻`now`を渡す既存の呼び出し方を変更しないため、意図的に別フィールド
とした)とは異なる、順序判定専用のフィールド。

`handle_payment_succeeded()`に`event_created_at: Optional[datetime] = None`、
`handle_payment_failed()`に同名の引数を追加した(Stripeイベントの`created`を渡す想定)。
`state.last_payment_event_time`以前(同時刻含む)の`event_created_at`が渡された場合、
状態更新・通知のいずれも行わず丸ごとスキップする(subscription側と同じ「stale全体
スキップ」方針)。`handle_payment_succeeded()`は`OUTCOME_STALE_EVENT`(`stale=True`)を
返す。`handle_payment_failed()`は既存の戻り値の型(bool)を変えず`False`を返す
(「既に検知済みで上書きしない」という既存の no-op と区別する専用の分類は設けていない。
どちらも「状態は変更されない」という呼び出し側にとっての結果は同じであるため)。

`last_payment_event_time`の更新は、subscription側の実装と同じく実際に状態が変化した
分岐(dunning解除・dunning新規検知)でのみ行い、no-op分岐(`OUTCOME_NO_DUNNING`・
既に検知済み・`trial_unselected`)や送信失敗(`OUTCOME_SEND_FAILED`、状態を一切変更せず
リトライに委ねる既存方針)では更新しない。

`event_created_at`省略時、または`state.last_payment_event_time`が未設定(本ガード導入前
からの既存店舗等)の場合はチェックを行わず従来通り無条件適用する(後方互換)。

## 3. 配線

`stripe_webhook_entry_point.py`の`receive_stripe_webhook()`は既にフェーズ続き283で
`event_time = _event_time_from_created(parsed)`を解決済みだったため、
`EVENT_INVOICE_PAYMENT_SUCCEEDED`・`EVENT_INVOICE_PAYMENT_FAILED`両分岐の呼び出しに
`event_created_at=event_time`を渡す配線もあわせて行った(サブスクリプション側で
フェーズ続き282→283と2段階に分けたのとは異なり、本対応は呼び出し箇所が2つのみで
影響範囲が小さいため1段階でまとめて実施した)。

`EVENT_INVOICE_PAYMENT_FAILED`分岐が`handle_payment_failed()`へ渡す第2引数
(`payment_failure_detected_at`に書き込まれる検知時刻)は従来通り`resolved_now`
(処理時刻)のまま変更していない。今回追加した`event_created_at`はあくまで順序判定
専用の第3引数であり、dunningスケジュールの起点そのものには影響しない。

## 4. テスト

`test_cloud_function_payment_webhook.py`に`EventOrderGuardTests`を新設し6件追加
(ケースB・ケースAそれぞれの「stale時スキップ」「正常適用時にlast_payment_event_time
記録」「event_created_at省略時の後方互換」)。

venture全体`python3 -m unittest discover -s prototype -p "test_*.py"`(885件、
+6)・schema検証`python3 schema/validate_test_cases.py`(28件)いずれもパスを確認した。

承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していない
ため、pending-approval.mdへの追記なし。

次回候補: `handle_checkout_session_completed()`(サブスクリプション成立とは独立に
`stripe_customer_id`・plan書き込みのみを行う分岐)にも同種の順序入れ替わりの影響が
あるかの検討、あるいは他venture・アイデア領域の前進。
