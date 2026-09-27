# Stripe Webhookの配信順序入れ替わりに対するsubscription_canceled_atガード
(subscription-event-out-of-order-guard-design.md)

## 1. 発見の経緯

subscription-canceled-immediate-block-design.md(フェーズ258)で、`customer.subscription.
deleted`受信時に`subscription_canceled_at`を書き込み・`customer.subscription.created`
受信時に消去する仕組みを追加した。これにより解約確定後の生成無期限継続バグは修正された
一方、`dispatch_stripe_event()`はどちらのイベントも「届いた時点のものを常に最新の真実」
として無条件に適用しており、Stripe公式ドキュメントが明記する「Webhookイベントは発生順に
届くとは限らず、再送(リトライ)により大幅に遅延することもある」という前提への対応が
抜けていることに気づいた。本フェーズでこの欠落を検証・修正した。

## 2. 具体的にどう壊れるか

Stripeは配信失敗時に最大3日間程度リトライを続けるため、同一customerに対する2つの
`customer.subscription.*`イベントが、実際に発生した順序と異なる順序でこのWebhook
エンドポイントに届くことがあり得る。

**ケースA: 「解約→即再契約」で deleted が created より後に届く**

1. ユーザーが契約を解約する(`customer.subscription.deleted`、実際の発生時刻T1)。
2. 直後に新しいプランで再契約する(`customer.subscription.created`、実際の発生時刻T2、
   T2 > T1)。
3. ネットワーク事情でcreated(T2)が先に届き処理される(`subscription_canceled_at`は
   未設定のまま、または既存値があれば消去される)。
4. 遅れてdeleted(T1)が届く。**修正前の実装はイベントの前後関係を一切見ないため、
   ここで`subscription_canceled_at`を書き込んでしまう**。結果、実際には新しい契約で
   有効な状態のユーザーが生成をブロックされる。

**ケースB: 初回created のリトライが、後続の deleted より後に届く**

1. ユーザーが契約する(`customer.subscription.created`、発生時刻T1)。このイベントの
   配信が何らかの理由で失敗し、Stripeがリトライを続ける。
2. その後ユーザーが解約する(`customer.subscription.deleted`、発生時刻T2、T2 > T1)。
   こちらは正常に配信され、`subscription_canceled_at`が正しく設定される。
3. 数時間〜数日後、ステップ1のcreated(T1)のリトライがようやく成功する。
   **修正前の実装はこれを「再契約」として扱い、`subscription_canceled_at`を消去して
   しまう**。結果、実際には解約済みのユーザーが生成ブロックを解除され、無期限に
   サービスを使い続けられてしまう(subscription-canceled-immediate-block-design.mdが
   防ごうとした欠落そのものが別経路で再発する)。

どちらのケースも「実際に最後に発生したイベントより古いイベントを、より新しいイベントの
後に適用してしまう」という同じ構造の問題である。

## 3. 修正方針: 反映済みイベント時刻との比較によるstale判定

`UsageCounterProtocol`(`cloud_function_webhook.py`)に`set_subscription_state_event_time()`
/`get_subscription_state_event_time()`を追加し、`subscription_canceled_at`の設定・消去の
どちらか最後に**実際に反映した**イベントの`event.created`(Unixタイムスタンプ→UTC
`datetime`)をuser_idごとに記録する。

`stripe_webhook.py`の`dispatch_stripe_event()`は、`customer.subscription.deleted`/
`customer.subscription.created`のいずれかを処理する際、`_is_stale_subscription_state_
event()`で今回のイベントの`event.created`を上記の記録済み時刻と比較する。今回のイベント
時刻が記録済み時刻以前(`<=`)であれば、より新しいイベントが既に反映済みと判断し、
`subscription_canceled_at`への反映(設定/消去のどちらであっても)をスキップする
(`StripeDispatchResult.stale_subscription_deleted_user_ids`/
`stale_subscription_created_user_ids`に記録するのみ)。反映した場合は、
`set_subscription_state_event_time()`で記録時刻を今回のイベント時刻に更新する。

`customer.subscription.created`イベントはこれまで`event.created`を一切読んでいなかった
(deleted側のみ読んでいた)ため、created側にも同様の取得ロジックを追加した。取得できない
場合(フィールド欠落・数値でない)は判定不能として常に「staleではない」を返し、従来通り
イベントを適用する(既存の呼び出し経路・テストとの後方互換)。`usage_counter`が
`get_subscription_state_event_time`に対応していない場合も同様に順序ガード自体を
スキップする(他のset_*系メソッドと同じ`hasattr()`判定による後方互換パターンの踏襲)。

## 4. 意図的に対象外とした範囲(残課題)

以下は本フェーズの対象外とし、次回以降の課題として残す。

- `mark_deletion_candidate_on_subscription_deleted()`(365日後データ削除用の削除候補化)・
  `clear_deletion_candidate_on_subscription_reactivated()`は、本ガードの対象にしていない。
  これらは`deletion_candidate.py`のProtocol(タイムスタンプを持たない)を使っており、
  同じstale問題が理論上は存在し得るが、実際の影響(365日という長い猶予期間の起点が
  数日ずれる程度)は`subscription_canceled_at`(生成の即時ブロック)よりも軽微であり、
  `deletion_candidate.py`自体のProtocol拡張は他venture(kura-pasha・aircon-pasha・
  line-reservation-ai)にも影響する可能性がある共通モジュールへの変更となるため、
  本フェーズのスコープには含めなかった。
- `customer.subscription.deleted`受信時の解約確定案内通知(`push_client`経由)・
  `payment_failure_cleared_on_deletion_user_ids`によるフィールドクリアは、本ガードの
  対象にしていない(deleted判定がstaleであっても、これらは従来通り実行される)。
  実運用上、deletedイベントがstaleと判定される(=直後に再契約されていた)ケースは
  稀であり、解約案内通知が1通誤って届く程度の実害にとどまると判断した。
- aircon-pasha・kura-pasha・line-reservation-aiへの横展開確認は未実施。次回候補とする。

## 5. テスト

`test_stripe_webhook.py`に以下を追加(いずれもパス)。

- 通常の順序(deleted→created、created→deleted)では従来通り反映されることの回帰確認。
- ケースAの再現: 既により新しいcreatedイベントが反映済みの状態で、それより古いdeleted
  イベントが届いても`subscription_canceled_at`が設定されないこと
  (`stale_subscription_deleted_user_ids`に記録されること)。
- ケースBの再現: 既により新しいdeletedイベントが反映済みの状態で、それより古いcreated
  イベントが届いても`subscription_canceled_at`が消去されないこと
  (`stale_subscription_created_user_ids`に記録されること)。
- `event.created`が取得できないcreatedイベント(既存テストの形式)は従来通り適用される
  ことの回帰確認。

venture全体・schema検証もあわせて実行し、いずれもパスを確認した(結果件数はREADME.md
最新フェーズ参照)。
