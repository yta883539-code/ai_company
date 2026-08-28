# 決済失敗(カード継続課金エラー)時の案内設計

作成日: 2026-08-28(フェーズ117)

## 背景

line-reservation-aiのpayment-failure-dunning-design.md、およびそれを本venture固有の
前提へ翻案したaircon-pashaのpayment-failure-dunning-design.md(2026-08-28フェーズ139)は、
いずれも「トライアル終了時に有料プランを未選択のまま放置した場合」(本venture用語では
trial-end-notification-design.md 4節の「生成一時停止」)とは別に、「いったん有料プランへ
加入し継続課金が始まった後、カード期限切れ・利用限度額超過等で毎月の自動課金自体が
失敗するケース」(dunning対応)を扱っている。本ventureにも「生成一時停止」機構
(フェーズ114実装済み、`_is_generation_paused()`/`GENERATION_PAUSED_MESSAGE`)・解約時の
データ削除候補化(stripe-cancellation-deletion-candidate-trigger-design.md相当は本venture
未着手、別課題)は存在するが、「加入後にカード決済そのものが失敗するケース」はどの
ドキュメントにも定義がなく未検討のまま残っていたため、aircon-pashaと同様に本ドキュメントで
整理する。

決済代行サービス自体の契約・実装配線は引き続きオーナー承認待ち(pending-approval.md参照)
のため、本ドキュメントは机上の設計のみを行い、実装・実際の課金は行わない。

## 1. 本venture固有の前提整理(aircon-pashaとの違い)

aircon-pashaのpayment-failure-dunning-design.md 1節は、`UserProfile`という単一の
データクラスに`upgraded_at`等のフィールドを持たせる設計を前提にしていた。本ventureは
`usage_counter`という`UsageCounterProtocol`(`get_trial_end_notified_at()`/
`get_upgraded_at()`/`set_upgraded_at()`等のメソッド群)を注入依存として扱う設計
(フェーズ103・105・114)のため、決済失敗由来の状態も新規フィールドではなく
`UsageCounterProtocol`への追加メソッド(`get_payment_failure_detected_at()`/
`set_payment_failure_detected_at()`/`clear_payment_failure_detected_at()`等、
実装着手時に確定)として設計するのが一貫性がある。

またCTA方式もaircon-pashaのpostback方式quick_replyではなく、本ventureが
checkout-initiation-flow-design.md(フェーズ98)以降一貫して採用しているLIFF経由の
Checkout Session作成導線(`LIFF_URL_PLACEHOLDER`をトライアル終了通知
(trial-end-notification-design.md 3節)と同じ形でメッセージ本文に埋め込む方式)を
踏襲する。本ventureはpostbackボタンではなくプレーンテキスト内のリンクとして案内する
点がaircon-pashaと異なる。

| | 生成一時停止(既存、trial-end-notification-design.md) | 決済失敗(本ドキュメント) |
|---|---|---|
| 発生条件 | トライアル終了時に一度も有料プランを選択していない(`get_trial_end_notified_at()`設定済み・`get_upgraded_at()`未設定) | 既に有料プランへ加入済み(`get_upgraded_at()`設定済み)で、毎月の継続課金が失敗した |
| 生成可否 | 不可(即一時停止) | 可(即座に止めない。理由は下記2節) |
| オーナー(セッター・ジムオーナー)の心理的状態 | 検討中・未決断 | 「払っているつもり」の場合が多く、通知を見落とすと不満につながりやすい |

decision: 決済失敗は「意図的な未加入」ではなく大半はカード更新のし忘れ等の事務的な理由と
想定されるため、line-reservation-ai・aircon-pashaと同じく猶予期間を設けたうえで、
既存の一時停止機構とは区別した独立フローとして設計する。

## 2. 再試行(リトライ)方針

line-reservation-aiのpayment-failure-dunning-design.md 5節で確認済みの一次情報
(Stripe Billingのスマートリトライ: 標準設定は最大2週間で最大8回、カスタム設定は
1・3・5・7日間隔で最大3〜4回)をそのまま踏襲する。unit-economics-estimate.mdで
確認済みの原価構造は他ventureと同種であり、本venture固有の再検証は不要と判断した。
自前で持つのは「決済失敗イベントをWebhookで受け取り、`usage_counter`の状態を更新し、
セッター・ジムオーナーへLINE通知する」部分のみとする。

## 3. 猶予期間と生成可否の扱い

決済失敗検知後、即座に生成を止めない。以下の3段階とする(line-reservation-ai・
aircon-pashaと同じ「猶予期間7日」を暫定値として踏襲)。

| 段階 | タイミング | 生成可否 |
|---|---|---|
| 1. 通常運用 | 決済成功中 | 可 |
| 2. 猶予期間(`payment_failed`) | 決済失敗検知〜7日間 | 可 |
| 3. 制限モード(`payment_suspended`) | 猶予期間終了後も未解消 | 不可(既存の`_is_generation_paused()`相当の分岐を再利用) |

- 猶予期間7日は他venture共通の暫定値(実測データなし)をそのまま踏襲する。venture固有の
  再検討は不要と判断した。
- 段階3(制限モード)の生成停止は、実装時に`_is_generation_paused()`の判定条件へ
  「`payment_suspended`状態」も含める(条件のORを1つ増やすだけ)想定とし、
  `GENERATION_PAUSED_MESSAGE`とは別の専用メッセージ(4節)を返す。既存の一時停止ロジックの
  「LLM呼び出し・トライアル生成回数カウントのいずれも行わず定型文を返す」という骨格自体は
  流用し、二重に一時停止機構を実装しない。

## 4. 通知文言(ですます調・絵文字不使用、本venture単一トーン)

本ventureはmessage-tone-variants.md相当の複数トーン切り替えを導入していない
(trial-end-notification-design.md 3節の既存注記の通り)ため、以下は単一文言のみ用意する。
宛先はジムオーナー・フリーランスセッター本人。

### 決済失敗検知時(猶予期間開始)

```
[コースセットパシャッと] お支払いの確認をお願いします

いつもご利用ありがとうございます。
今回のお支払い手続きが完了できませんでした
(カードの有効期限切れ・利用限度額等が考えられます)。

現在、投稿文の生成は通常どおりご利用いただけます。
7日以内にお支払い方法をご確認・更新いただけますようお願いします。

▼ お支払い方法を確認する
[LIFF経由の決済導線リンク]
```

### 猶予期間終了直前(3日前リマインド、1回のみ)

```
[コースセットパシャッと] お支払い確認のお願い(再送)

お支払い手続きが未完了のままです。
このままですと3日後に投稿文の生成を一時停止いたします。

▼ お支払い方法を確認する
[LIFF経由の決済導線リンク]
```

### 制限モード移行時(段階3)

```
[コースセットパシャッと] 投稿文の生成を一時停止しました

お支払い手続きが確認できないため、投稿文の生成を一時停止しました。
お支払い方法をご確認いただければ、確認完了後に自動で生成を再開します。

▼ お支払い方法を確認する
[LIFF経由の決済導線リンク]
```

### 決済成功による復旧時

```
[コースセットパシャッと] お支払いを確認しました

お支払い手続きが完了しました。ご不便をおかけしました。
投稿文の生成を再開しましたので、引き続きよろしくお願いします。
```

line-reservation-aiのフェーズ続き115で判明した「猶予期間中に決済が成功した場合は復旧通知の
文言を出し分ける必要がある」という論点(3分岐: 制限モードからの復旧/猶予期間中の完了通知/
状態リセットのみ)は、本ventureでも同様に発生する見込みが高い。ただし本ventureは
`_is_generation_paused()`の判定条件を1つ増やすだけの単純な構造のため、この分岐の詳細設計は
`invoice.payment_succeeded`Webhookの受信配線を実装する段階(次回以降)で行うこととし、
本フェーズでは先行して起こりうる論点として書き残すにとどめる(aircon-pashaフェーズ139と
同じ判断)。

## 5. CTAリンクの実装課題(本venture固有)

trial-end-notification-design.md 3節のCTAリンクは「LIFF経由のCheckout Session作成導線
(新規サブスクリプション申込)」であり、`build_checkout_session_params()`
(checkout-session-endpoint-design.md)が発行する新規Checkout Sessionを前提にしている。
一方、決済失敗からの復旧に必要なのは「既存サブスクリプションの支払い方法更新」であり、
これは新規Checkout Session発行とは別物のStripe Customer Portal(Billing Portal)
セッション作成が必要になる見込みがある(aircon-pashaフェーズ139・5節で指摘済みの論点と
同種)。本ventureはLIFF方式を既にCTA全般の標準としているため、Customer Portalへの遷移リンクも
同じLIFFアプリ内から`liff.getIDToken()`で取得したuser_idを使って発行する設計に揃えられる
見込みが高いが、Portalセッション作成エンドポイント自体の設計は次回以降の課題として残す。

## 6. 残課題

- `UsageCounterProtocol`への状態管理メソッド追加(`get_payment_failure_detected_at()`/
  `set_payment_failure_detected_at()`/`clear_payment_failure_detected_at()`等、
  メソッド名・戻り値型は実装着手時に確定)。
- 本venture未着手のStripe Webhookイベントディスパッチ機構(aircon-pasha/line-reservation-ai
  の`stripe_dispatch.py`相当)への`invoice.payment_failed`・`invoice.payment_succeeded`
  イベント種別対応。本venture自体のStripe Webhook受信エンドポイント設計
  (stripe-webhook-http-entry-point-design.md相当)がまだ`resolve_user_id`
  (フェーズ97相当)止まりで、イベント種別ディスパッチ本体は未実装のため、決済失敗対応の
  前提として先にそちらの整備が必要になる可能性がある(次回棚卸し時に確認)。
- `_is_generation_paused()`の判定条件拡張(制限モード状態を含める)、および
  制限モード専用メッセージの`process_memo_event()`への配線。
- 5節で触れたStripe Customer Portal(支払い方法更新用URL発行)の要否・実装方式の検討。
- 猶予期間終了直前リマインドを送信するスケジューラ(trial-end-scheduler-design.mdの
  日次バッチと同種の仕組みを流用できる見込みだが、本ドキュメントでは未検討)。
- 実際のWebhook受信・状態保存・LINE送信配線、決済代行サービスとの契約自体は
  引き続きオーナー承認待ち(pending-approval.md参照)。
- 猶予期間7日・リマインド1回のみという値は、他venture共通で実測データの無い暫定値のまま。
