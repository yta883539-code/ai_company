# Stripe Webhook受信エントリポイントの設計(フェーズ95)

README.mdフェーズ94次回候補(2)「月額フリーパスのStripe Webhook受信フロー自体の設計着手」に
対応する。本venture(oshien-pasha)はこれまで`fan_pass_store.py`(フェーズ39・40)で
Webhookから呼ばれる前提のメソッド(`create`・`update_subscription_status`等)のみを先行して
実装しており、それを実際に呼び出すWebhook受信エントリポイント自体の設計はsubscription-
updated-event-order-guard-preemptive-note.md(フェーズ88)が明言する通り未着手だった。
本フェーズはこの設計に着手する(プロトタイプ実装は次回以降とし、今回は設計のみ)。

## 1. 位置づけ・スコープ

- aircon-pasha/course-set-pasha/forklift-pasha等の`prototype/stripe_webhook.py`と同じ
  位置づけ(実Stripeアカウント接続・実Cloud Functionsデプロイなしでも検証できる、署名検証
  +イベントディスパッチのロジックを切り出したモジュール)を、本venture向けに設計する。
- payment-method-design.md(フェーズ5)が確定した「都度プラン(`mode=payment`)と月額
  フリーパス(`mode=subscription`)の両方をプラン選択に応じて発行する」方針のうち、本
  ドキュメントは**月額フリーパス(`mode=subscription`)側のWebhook受信のみ**を対象とする。
  都度プラン側の`checkout.session.completed`受信(event-komiguai-pashaのone-time-
  checkout-no-account-design.md相当の設計)は別途必要だが、本venture側では都度プランの
  Checkout Session発行起点(プラン選択UI)自体が未着手のため、今回のスコープ外として残す。
- 本venture固有の制約として、LINE非依存のWeb単体(payment-method-design.md 2節)・会員
  登録なし(monthly-pass-identity-design.md)がある。既存6venture(LINE Webhook前提)とは
  イベント受信チャネル自体が独立しており、Stripe Webhookの設計には影響しない(他venture同様
  Cloud Functions HTTPエンドポイントで受ける)。

## 2. 署名検証

aircon-pasha・course-set-pasha・forklift-pasha等の`verify_stripe_signature()`と同一の
アルゴリズム(Stripe公式仕様に従う汎用ロジックであり、venture固有の差異は無い)をそのまま
踏襲する。

- ヘッダ形式`t=<Unixタイムスタンプ>,v1=<署名>`の解析、`f"{t}.{payload}"`を`webhook_secret`
  でHMAC-SHA256署名して`v1`のいずれかと`hmac.compare_digest()`で一致確認、
  `tolerance_seconds`(デフォルト300秒)超過時は検証失敗、という3点は他venture完全同一。

## 3. 本venture固有のイベント種別とディスパッチ

対象イベントは以下の4種類のみとする(都度プランの`checkout.session.completed`は前述の
通りスコープ外)。それ以外の種別は他venture同様`ignored_type`として200を返すのみとする。

### 3-1. `checkout.session.completed`(`mode=subscription`のみ)

- `data.object.mode == "subscription"`であることを確認し、`mode=payment`(都度プラン)は
  本ハンドラの対象外として無視する(将来都度プランのWebhookを実装する際に分岐が混ざらない
  ようにするための事前の切り分け)。
- `customer`(= `stripe_customer_id`)・`subscription`(= `stripe_subscription_id`)・
  `customer_details.email`(= `email`、event-komiguai-pashaフェーズ99と同じ理由で
  `customer_email`ではなく`customer_details.email`を採用する実レスポンス形式を踏襲)を
  取り出し、`fan_pass_store.create(email=..., stripe_customer_id=..., 
  stripe_subscription_id=...)`を呼び出す。
- `create()`は既にフェーズ40で`stripe_subscription_id`をdedupキーとした冪等性を実装済み
  (重複配信時は新規発行せず既存の`(internal_id, access_token)`を返す)ため、本ハンドラ
  自身は追加の重複チェックを持たない。

### 3-2. 決済完了直後のアクセスURL表示との整合性(新規の論点)

monthly-pass-identity-design.md(フェーズ7)2節は「`return_url`遷移後の結果ページで
Checkout Session IDから該当ドキュメントを特定し、アクセスURLをその場で画面表示する」と
しているが、これは**Webhookの非同期配信とブラウザのリダイレクトという2つの独立した経路が
完了する順序を前提にしていない**という設計上の欠落が今回新たに見つかった。Stripeの
Webhook配信は多くの場合リダイレクトより先に届くが、保証はされていない(Stripe公式も
「Webhookの方が速いとは限らない」と明記している)。したがって結果ページ表示時点で
まだ`fan_pass`ドキュメントが作成されていない(Webhookが未到達)ケースが起こりうる。

**対応方針(今回の設計判断)**: 結果ページ表示用のバックエンドエンドポイントは、
Checkout Session IDを受け取り、(a)Stripe APIで該当Sessionを取得し`subscription`
フィールド(= `stripe_subscription_id`)を得た上で、(b)`fan_pass_store.
get_by_stripe_subscription_id()`で問い合わせる。(b)が`None`を返す場合は「Webhook未到達」
と判断し、短い間隔(例: 1秒間隔・最大5回程度)でのポーリングにより再試行し、それでも
見つからない場合のみ「準備中、数分後に再度アクセスしてください」という案内を表示する
(forklift-pashaのメール送信遅延時の案内パターンと同種の「失敗時は案内のみ、自動復旧は
試みる」方針)。この設計により、Webhookエントリポイント自体にはポーリング対応のための
追加ロジックは不要(`create()`が呼ばれさえすれば足りる)ことを確認した。

### 3-3. `customer.subscription.deleted`(解約)

fan-pass-canceled-access-block-design.md(フェーズ35)4節で既に確定済みの方針通り、
`stripe_subscription_id`から`get_by_stripe_subscription_id()`で`internal_id`を特定し、
`update_subscription_status(internal_id, "canceled", event_time=...)`を呼ぶ(`event_time`
引数は4節で後述)。該当ドキュメントが見つからない場合は異常系としてログに残すのみとし
200を返す(他venture同型の安全策)。

### 3-4. `customer.subscription.created`(再加入)

同じくfan-pass-canceled-access-block-design.md 4節の方針通り、解約済み利用者が同一
`accessToken`のまま再加入した場合に`update_subscription_status(internal_id, "active", 
event_time=...)`へ戻す。ただし本イベントは「新規契約」にも「解約後の再加入」にも発火する
ため、`get_by_stripe_subscription_id()`で既存ドキュメントが見つかった場合のみ本分岐を
適用し、見つからない新規契約相当のケースは3-1の`checkout.session.completed`側で処理済み
のはず、という前提で本ハンドラは何もしない(重複処理の回避)。

### 3-5. `customer.subscription.updated`(新規の論点: ステータス遷移の対応表)

既存の`_VALID_STATUSES = {"active", "canceled"}`(fan_pass_store.py)は「有効/解約」の
2値のみを想定しており、Stripeのサブスクリプションステータス(`active`・`past_due`・
`unpaid`・`canceled`・`trialing`等)のうち決済失敗時の中間状態(`past_due`)を表現できない
という設計上の欠落が今回見つかった。本フェーズでは以下の暫定マッピングを採用する
(aircon-pasha等が個別の`_is_payment_suspended`タイムスタンプで表現する方式ほどの精緻さは
本venture規模ではオーバーエンジニアリングと判断し、2値のまま寄せる単純化を採る)。

- Stripeステータスが`active`・`trialing`: `fan_pass.subscriptionStatus = "active"`。
- Stripeステータスが`past_due`・`unpaid`・`canceled`・`incomplete_expired`: 
  `fan_pass.subscriptionStatus = "canceled"`(猶予期間を設けず即座にアクセスを止める、
  安全側に倒す判断。都度利用中心でLTVが低いB2C想定のため、督促より即時停止を優先する)。
  この判断は仮説であり、実運用データが無い時点での保守的な初期値である旨を残課題に残す。

## 4. `update_subscription_status()`のevent_time拡張(設計のみ、コード変更は次回)

subscription-updated-event-order-guard-preemptive-note.md(フェーズ88)3節が示した
パターンをそのまま採用する。

1. `FanPass`に`subscription_status_updated_at: int | None`フィールドを追加する
   (firestore-data-model.mdの`fan_pass/{internal_id}`スキーマにも反映が必要、次回対応)。
2. `update_subscription_status(internal_id, status, *, event_time: int)`へシグネチャ変更
   (既存の`internal_id, status`の2引数から1引数追加)。
3. `event_time <= 既存のsubscription_status_updated_at`なら更新をスキップする(遅延配信
   された古いイベントによる巻き戻りを防ぐ)。初回(未設定)は無条件適用する。
4. この変更は3-3・3-4・3-5の全ハンドラが共通して使うため、本フェーズの設計時点で先に
   確定させる。実装(fan_pass_store.pyの変更・既存テストへの影響確認)は次回候補とする。

## 5. 冪等性(event_idストア)

他venture同様、エントリポイント層での`event.id`ベースの冪等性チェック
(stripe-event-idempotency-design.md相当)も将来的に導入する想定だが、3-1の`create()`が
既に`stripe_subscription_id`ベースの冪等性を持ち、3-3〜3-5も`update_subscription_status`
の`event_time`ガードで遅延配信・順序入れ替わりに対応できるため、本venture規模では
event_idストアを**必須とはしない**(他venture完了済みの横展開対象には含めない)。導入是非
は実運用でのWebhook再送頻度を見てから再検討する、と残課題に留める。

## 6. 残課題・次回候補

1. `prototype/stripe_webhook.py`の新規実装(3節・4節の設計に基づく`verify_stripe_
   signature()`・`dispatch_stripe_event()`・各ハンドラ関数)。
2. `fan_pass_store.py`の`update_subscription_status()`への`event_time`引数追加(4節)と
   `firestore-data-model.md`の`fan_pass`スキーマへの`subscription_status_updated_at`
   フィールド追記、既存テストへの影響確認。
3. 3-5の暫定ステータスマッピング(`past_due`等を即`canceled`扱いにする判断)の妥当性の
   再検討。猶予期間を設ける設計に変更する場合は、aircon-pasha等の`_is_payment_suspended`
   相当の仕組みの要否も合わせて検討する。
4. 3-2のポーリング設計(結果ページ表示エンドポイント)の実装は、本Webhook設計とは別の
   HTTPエントリポイント(フロントエンド向けAPI)として次回以降に着手する。
5. 実Stripeアカウント・Webhookエンドポイント登録・実Cloud Functionsデプロイ・実Firestore
   接続はいずれも実GCPプロジェクト作成(オーナー承認待ち、pending-approval.md参照)後の
   課題として残る。
6. 都度プラン(`mode=payment`)側のWebhook受信設計(1節でスコープ外とした部分)は、都度
   プランのプラン選択UI・Checkout Session発行自体の設計が先に必要なため、別フェーズの
   課題として残す。
7. 他venture・アイデア領域の前進。

最終更新: 2026-11-07 14:00 UTC(フェーズ95: 本設計により、フェーズ88の先行メモが「未着手」
としていたStripe Webhook受信フローの設計に着手。署名検証・4種のイベントディスパッチ
(`checkout.session.completed`・`customer.subscription.deleted`・`customer.subscription.
created`・`customer.subscription.updated`)の設計、ならびに決済完了直後のアクセスURL表示と
Webhook非同期配信の順序不整合という新規の論点を発見しポーリング方針で対応。コード変更は
次回以降、本フェーズは設計ドキュメントのみ)
