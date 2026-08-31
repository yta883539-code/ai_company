# Stripe Webhook署名検証の設計

作成日: 2026-08-31(フェーズ続き158)

checkout-initiation-flow-design.md「残課題」2点目に「`resolve_existing_stripe_customer_id()`・
`handle_checkout_session_completed()`を実際にCloud Functions側のCheckout Session作成
エンドポイント・Stripe Webhook受信エンドポイント本体に配線する処理(実HTTPハンドラ・実Stripe
API呼び出し)は未実装」と記載されたまま、本venture(line-reservation-ai)には
aircon-pasha・course-set-pashaの両ventureに既にある「Stripe Webhook署名検証」自体が
存在しないという配線漏れ以前の欠落があることに気づいた。実Stripeアカウント作成・Webhook
エンドポイント登録(いずれもオーナー承認待ち)なしでも、公開されているアルゴリズム仕様のみ
から机上実装・テスト可能な署名検証部分だけを先行して着手する。

aircon-pashaのstripe-webhook-signature-verification-design.md(フェーズ125)・
course-set-pashaの同名ドキュメント(フェーズ93)と同一のアルゴリズムをそのまま踏襲する
(署名検証自体はStripe仕様に従う汎用ロジックであり、venture固有の差異は無い)。

## 1. `Stripe-Signature`ヘッダの形式

Stripeの公式仕様どおり、ヘッダは以下のカンマ区切り形式:

```
t=1614556800,v1=5257a869e7ecebeda32affa62cdca3fa51cad7e77a0e56ff536d0ce8e108d8bd,v0=...
```

- `t`: イベント送信時のUnixタイムスタンプ(秒)。
- `v1`: 現行の署名方式(HMAC-SHA256)による署名(16進数)。Webhookシークレットのローテーション
  期間中は複数の`v1`が同時に含まれることがあるため、**いずれか1つでも一致すれば検証成功**と
  する(Stripe公式ライブラリ`stripe-python`の`Webhook.construct_event`と同じ方針)。
- `v0`: 廃止済みの旧方式。本実装では一切参照しない(意図的に無視する)。

## 2. 検証アルゴリズム

1. `sig_header`が`None`または空文字列なら`False`(本venture既存のLINE版
   `verify_line_signature()`〈webhook-http-entry-point-design.md〉と同じ「未検証時は
   安全側で拒否」)。
2. ヘッダを`,`で分割し、各要素を`key=value`で解析する。`t`と`v1`(複数可)を収集する。
   `t`が存在しない、または`v1`が1つも無ければ`False`(不正な形式)。
3. 署名対象文字列(signed payload)を`f"{t}.{payload.decode('utf-8')}"`として組み立てる
   (Stripe仕様どおり、タイムスタンプと生のリクエストボディをドット区切りで連結)。
4. `webhook_secret`をキーに`hmac.new(..., signed_payload.encode(), hashlib.sha256).hexdigest()`
   で期待署名を計算し、収集した`v1`のいずれかと`hmac.compare_digest()`で一致するか確認する
   (タイミング攻撃対策、LINE版のBase64比較と同じ考え方)。
5. タイムスタンプ許容範囲(リプレイ攻撃対策): `abs(now - int(t)) > tolerance_seconds`なら
   署名が一致していても`False`とする。Stripe公式ライブラリのデフォルト許容値である
   **300秒(5分)**を`tolerance_seconds`のデフォルト値として採用する。

```python
def verify_stripe_signature(
    payload: bytes,
    sig_header: Optional[str],
    webhook_secret: str,
    *,
    tolerance_seconds: int = 300,
    now: Optional[float] = None,
) -> bool:
```

`now`(Unixタイムスタンプ、float)は省略可能な引数とし、省略時は`time.time()`を使う
(タイムスタンプ許容範囲チェックがテスト時に固定時刻を注入できるようにするため)。

## 3. LINE版との違い

- LINE版(本venture`webhook-http-entry-point-design.md`の`verify_line_signature()`、
  `prototype/cloud_function_webhook.py`)は署名アルゴリズムのみで完結し、タイムスタンプの
  概念が無い(LINE Platform側にリプレイ対策の仕組みが別途あるため)。Stripe版はヘッダ自体に
  タイムスタンプが埋め込まれており、これを検証すること自体がStripe公式ドキュメントで明示的に
  推奨されている。
- 複数署名(`v1`が複数)への対応もLINE版には無い概念で、Stripeのシークレットローテーション
  運用に固有の要件。

## 4. プロトタイプ実装方針

- 新規ファイル`prototype/stripe_webhook.py`に`verify_stripe_signature()`のみを実装する
  (`cloud_function_webhook.py`とは別ファイルとし、LINE側のコードに一切影響を与えない構成。
  `checkout_session.py`をStripe関連の別ファイルとして切り出した前例〈フェーズ続き139〉を
  踏襲)。
- テストは`prototype/test_stripe_webhook.py`に新設し、aircon-pasha版
  `VerifyStripeSignatureTest`と同じ7ケースをそのままカバーする:
  1. 正しい署名・許容範囲内のタイムスタンプ → `True`
  2. 署名ヘッダが`None`・空文字列 → `False`
  3. 署名ヘッダの形式が不正(`t=`や`v1=`が無い、無効な文字列) → `False`
  4. 署名が一致しない(誤ったシークレットで計算した署名) → `False`
  5. 署名は一致するがタイムスタンプが許容範囲外(古すぎる・未来すぎる) → `False`
  6. `v1`が複数含まれ、そのうち後方の1つのみが一致する(シークレットローテーション想定) →
     `True`
  7. `v0`のみが一致し`v1`が一致しない(旧方式は無視する方針の確認) → `False`

## 残課題

- 実際のWebhookエンドポイント本体(署名検証〜イベント種別(`checkout.session.completed`等)
  ディスパッチ〜`handle_checkout_session_completed()`〈`prototype/store_profile_store.py`
  フェーズ続き139で実装済み〉の呼び出しを結ぶ層)は、今回のスコープ外(署名検証のみ先行実装)
  として次の課題に残す。course-set-pasha/stripe-webhook-http-entry-point-design.md・
  aircon-pasha/stripe-webhook-http-entry-point-design.md相当を、本venture向けに設計する
  必要がある。本venture固有の留意点として、checkout.session.completed以外のイベント種別
  (`customer.subscription.deleted`等)を扱う`cloud_function_payment_webhook.py`・
  `cloud_function_subscription_activated_webhook.py`が既に存在するため、これらとの
  ディスパッチ責務の分担(どのモジュールがどのイベント種別を処理するか)を整理する必要が
  ある点をcourse-set-pasha・aircon-pashaには無かった追加検討事項として明記する。
- `webhook_secret`の実際の値の取得・保管方法(Secret Manager等)は、実Stripeアカウント接続
  (オーナー承認待ち)後の設計課題として別途残る。
- Stripeイベントの重複配信対策(`event.id`によるべき等性チェック)は、エンドポイント本体側の
  設計課題として次回以降に持ち越す(署名検証層のスコープ外)。
