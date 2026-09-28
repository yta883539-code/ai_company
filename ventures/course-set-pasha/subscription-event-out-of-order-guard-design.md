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

## 4. 意図的に対象外とした範囲(残課題、フェーズ261時点)

以下はフェーズ261時点で本フェーズの対象外とし、次回以降の課題として残していた
(フェーズ262・263での対応状況は6節参照)。

- `mark_deletion_candidate_on_subscription_deleted()`(365日後データ削除用の削除候補化)・
  `clear_deletion_candidate_on_subscription_reactivated()`は、本ガードの対象にしていない。
  これらは`deletion_candidate.py`のProtocol(タイムスタンプを持たない)を使っており、
  同じstale問題が理論上は存在し得るが、実際の影響(365日という長い猶予期間の起点が
  数日ずれる程度)は`subscription_canceled_at`(生成の即時ブロック)よりも軽微であり、
  `deletion_candidate.py`自体のProtocol拡張は他venture(kura-pasha・aircon-pasha・
  line-reservation-ai)にも影響する可能性がある共通モジュールへの変更となるため、
  本フェーズのスコープには含めなかった。→ **フェーズ262で対応済み**(6.1節)。
- `customer.subscription.deleted`受信時の解約確定案内通知(`push_client`経由)・
  `payment_failure_cleared_on_deletion_user_ids`によるフィールドクリアは、本ガードの
  対象にしていない(deleted判定がstaleであっても、これらは従来通り実行される)。
  実運用上、deletedイベントがstaleと判定される(=直後に再契約されていた)ケースは
  稀であり、解約案内通知が1通誤って届く程度の実害にとどまると判断した。
  → **フェーズ263で対応済み**(6.2節。kura-pasha・line-reservation-aiとの横展開確認
  〈次項〉の過程で、両venture共に同種のケースを「stale全体スキップ」方針で対応済み
  だったことを確認し、本ventureも同方針へ統一した)。
- aircon-pasha・kura-pasha・line-reservation-aiへの横展開確認は未実施。
  → **フェーズ263で確認済み**(6.2節。3venture全てが各自のフェーズで独立に同種
  ガードを実装済みであることを確認した)。

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

## 6. フェーズ262・263での追加対応

### 6.1 フェーズ262: `deletion_candidate.py`への適用

4節1項の残課題(`deletion_candidate_at`)は、実装コストが小さく既存パターン
(hasattr判定によるオプトイン・後方互換)をそのまま踏襲できたため、フェーズ262で
対応した。`ProfileDeletionCandidateStoreProtocol`に
`get_deletion_candidate_state_event_time()`/`set_deletion_candidate_state_event_time()`を
追加し、`mark_deletion_candidate_on_subscription_deleted()`/`clear_deletion_candidate_
on_subscription_reactivated()`にstale判定を追加した。詳細はREADME.md フェーズ262参照。

### 6.2 フェーズ263: 通知・決済失敗フィールドクリアのstale全体スキップ化+横展開確認の結果

4節2・3項の残課題を、aircon-pasha・kura-pasha・line-reservation-aiでの対応状況の
確認とあわせて棚卸しした。

**横展開確認の結果**: 3venture全てが、course-set-pashaフェーズ261・262とは独立に、
各自の状態表現(kura-pasha・line-reservation-aiは`subscription_status`列挙型/
`suspension_reason`文字列の単一フィールド方式、aircon-pashaはcourse-set-pashaと
同じ複数タイムスタンプフィールド方式)に合わせた同種のstaleイベントガードを
既に実装済みであることを確認した(aircon-pashaフェーズ280、kura-pashaフェーズ194、
line-reservation-aiフェーズ続き282〜285)。したがって4節3項の横展開確認は完了した
ものとし、追加対応は不要と判断する。

**通知・決済失敗フィールドクリアのstale全体スキップ化**: 横展開確認の過程で、
kura-pasha(`subscription-status-event-order-guard-design.md`)・
line-reservation-ai(`subscription-event-order-guard-design.md`等)の両venture共に、
staleと判定した場合は状態更新だけでなく付随する通知・関連フィールドの変更も
まとめてスキップする「stale全体スキップ」方針を採用していることを確認した
(状態だけをスキップして通知だけ送ると、実際の契約状態と矛盾する通知を送って
しまうため)。これに対しcourse-set-pashaのフェーズ261・262時点の実装は、
`subscription_canceled_at`の設定・消去のみをガード対象とし、解約確定案内通知
(`push_client`経由の`handle_subscription_cancelled()`呼び出し)と決済失敗3フィールド
クリア(`payment_failure_cleared_on_deletion_user_ids`)は、deleted判定がstaleで
あっても従来通り無条件に実行される非対称な状態だった。

4節2項が「実運用上稀・実害軽微」と判断していたのは事実だが、既にkura-pasha・
line-reservation-aiの2venture共が同種ケースをより安全な「全体スキップ」方針で
実装済みであり、course-set-pashaだけがこの非対称を残す理由は無いと判断し、
本フェーズで統一した。`dispatch_stripe_event()`の`customer.subscription.deleted`
分岐で、`_is_stale_subscription_state_event()`によるstale判定を(従来は
`subscription_canceled_at`設定の直前でのみ行っていたところを)決済失敗フィールド
クリア・`subscription_canceled_at`設定・解約確定案内通知の3箇所共通の変数
`is_stale_deleted_event`として先頭でまとめて評価するよう変更し、stale時はいずれの
副作用もスキップするようにした(`usage_counter`未指定時は判定不能として常に
`False`=従来通り適用、既存呼び出し経路への後方互換は維持)。

テスト2件追加(`test_stale_subscription_deleted_sends_no_cancellation_notice`・
`test_stale_subscription_deleted_does_not_clear_payment_failure_state`、いずれも
`test_stripe_webhook.py`)。venture全体672件(670→672)・schema検証21件
(変更なし)いずれもパス。コード変更は`prototype/stripe_webhook.py`の
`customer.subscription.deleted`分岐のみで、他の分岐・他ventureへの影響は無い。
