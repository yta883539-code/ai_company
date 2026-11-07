# Stripe Webhook署名検証・受信エントリポイントの設計(フェーズ99)

one-time-checkout-no-account-design.md(フェーズ10)5節が「stripe-webhook-signature-
verification-design.md相当の署名検証・stripe-event-idempotency-design.md相当の冪等性
チェックを他venture同様に適用する前提」と、実在しないファイル名を前提として書いたまま
フェーズ51・53の棚卸しでも見過ごされていた記載を是正する。本venture独自のこれら2ファイルを
新規に作成し、「相当」という仮置きの参照を実体に置き換える。

aircon-pasha/stripe-webhook-signature-verification-design.md(フェーズ125)と同じく、
署名検証アルゴリズム自体はStripe公式仕様に従う汎用ロジックであり、venture固有の差異は
無い。本ドキュメントは1節をそのまま踏襲し、2節以降で本venture固有の受信エントリポイント
設計(単発決済モデル・`checkout.session.completed`単一イベント種別)を新規に整理する。

## 1. `Stripe-Signature`ヘッダの検証アルゴリズム(汎用、他venture同一)

aircon-pasha版(フェーズ125)・course-set-pasha版(フェーズ93)と同一のアルゴリズムを
そのまま踏襲する。

- ヘッダ形式: `t=<Unixタイムスタンプ>,v1=<署名>,v0=<旧方式、無視>`(`v1`は複数含まれうる、
  シークレットローテーション運用のため)。
- `sig_header`が`None`・空文字列、または`t`・`v1`のいずれかを含まない不正な形式なら
  検証失敗(`False`)。
- 署名対象文字列`f"{t}.{payload}"`を`webhook_secret`でHMAC-SHA256署名し、`v1`のいずれか
  1つとでも`hmac.compare_digest()`で一致すれば署名一致。
- 署名が一致してもタイムスタンプが許容範囲(`tolerance_seconds`、デフォルト300秒 =
  Stripe公式ライブラリのデフォルト値)を超えていれば検証失敗とする(リプレイ攻撃対策)。

## 2. 本venture固有の受信エントリポイント設計

他venture(継続課金モデル)との最大の違いは、本ventureが扱うStripeイベント種別が
`checkout.session.completed`の1種類のみで、`customer.subscription.*`等のディスパッチ
(`stripe_dispatch.py`相当)を一切持たない点である(tech-stack.mdフェーズ7・one-time-
checkout-no-account-design.mdフェーズ10で確定済みの単発決済モデル)。このため
`dispatch_stripe_event()`のような汎用ディスパッチャは導入せず、`checkout.session.
completed`以外のイベント種別は全て`ignored_type`として200を返すだけの単純な分岐とする。

### 2-1. `client_reference_id` / `customer_email`の取り出し

- `client_reference_id`を`draft_id`として扱う(one-time-checkout-no-account-design.md
  2節で確定済み)。継続課金モデル(aircon-pasha等)が`client_reference_id`に既知の
  `user_id`を設定するのに対し、本ventureは`one_time_draft/{draft_id}`という「決済前から
  既に存在するドキュメント」のキーをそのまま使う点は同じ構造(`store.get(draft_id)`が
  `None`なら異常系として扱う、aircon-pasha版`handle_checkout_session_completed()`の
  `user_profile_not_found`と同じ安全策)。
- `customer_email`はdraft-id-last4-collision-design.md(フェーズ53)で確定済みの
  `customer_email`必須化を受け、`data.object.customer_details.email`(Stripe Checkout
  Sessionの実レスポンス形式、`customer_email`フィールド自体はリクエスト時の事前入力値で
  あり確定値は`customer_details.email`側)から取得する方針とする。

### 2-2. 冪等性の二重の防御(ドラフト状態 + event_idストアの併用)

本ventureは継続課金モデルと異なり、`one_time_draft`のステータス自体が「一度きりの状態
遷移」を表現する(`awaiting_payment` → 生成試行 → `generated`/`out_of_scope`/
`insufficient_input`(mvp-flow-draft.md)または`generation_failed`(ttl-expiry-result-
delivery-refund-design.mdフェーズ12 3-2節)のいずれか)。したがって`checkout.session.
completed`を2回受信しても、2回目の時点で既に`awaiting_payment`以外のステータスに遷移
済みであれば生成を再実行しない、という業務ロジック自体が天然の冪等性ガードになっている
(aircon-pasha版の`upgraded_at is None`チェックと同じ「一度だけ」設計思想)。

この業務ロジック層のガードに加え、stripe-event-idempotency-design.md(フェーズ99)で
設計する`event_id_store`によるエントリポイント層でのチェックも併用する(2つの理由:
(1)Stripeの推奨実装に合わせる、(2)event_idチェックの方が業務ロジックに到達する前に
Firestore読み取りすら発生させずに弾けるため、将来`awaiting_payment`判定ロジックに
バグが混入した場合の多層防御になる)。

### 2-3. TTL失効ドラフトへの防御的チェック

ttl-expiry-result-delivery-refund-design.md(フェーズ12)1節が要求する「`expires_at`を
過ぎた`draft_id`への`checkout.session.completed`受信時は生成を行わず期限切れエラーとして
処理する」防御的チェックを、`handle_checkout_session_completed()`内で行う(2節参照)。

## 3. プロトタイプ実装方針

- 新規ファイル`prototype/stripe_webhook.py`に`verify_stripe_signature()`・
  `handle_checkout_session_completed()`・`receive_stripe_webhook()`を実装する
  (他venture同様、既存の`form_submission_intake.py`等とは独立した別ファイル)。
- テストは`prototype/test_stripe_webhook.py`に新設する(1節の署名検証7ケース + 2節の
  受信エントリポイントのケース、詳細はstripe-event-idempotency-design.md参照)。

## 残課題

- `webhook_secret`の実際の値の取得・保管方法(Secret Manager等)、実Stripeアカウント・
  Webhookエンドポイント登録、実Firestore接続はいずれも実GCPプロジェクト作成(オーナー
  承認待ち、pending-approval.md参照)後の課題として残る。
- LLM生成の実際の呼び出し配線(`handle_checkout_session_completed()`が返す
  `proceed_to_generation=True`を受けてのmock_llm_client.py相当の呼び出し)は本フェーズの
  範囲外(Webhook受信口・冪等性チェックまでの設計に限定する)。
