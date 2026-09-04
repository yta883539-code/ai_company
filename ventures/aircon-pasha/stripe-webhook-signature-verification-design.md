# Stripe Webhook署名検証の設計

作成日: 2026-08-25(フェーズ125)

フェーズ124の申し送り通り、「Stripe Webhook受信口自体の設計(署名検証方式・エンドポイントURL)」
に着手する。stripe-cancellation-deletion-candidate-trigger-design.md(フェーズ123)5節で
「実際のStripe Webhook受信エンドポイント(署名検証・イベント種別ディスパッチ)は本venture
にまだ存在しない」と明示されていた残課題のうち、実Stripeアカウント作成・Webhookエンドポイント
登録(いずれもオーナー承認待ち)なしでも公開されているアルゴリズム仕様のみから机上実装・
テスト可能な署名検証部分を、course-set-pashaのstripe-webhook-signature-verification-design.md
(フェーズ93)と同じ方針でそのまま踏襲して設計する。

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

course-set-pasha版と同一のアルゴリズムをそのまま踏襲する(署名検証自体はStripe仕様に
従う汎用ロジックであり、venture固有の差異は無い)。

1. `sig_header`が`None`または空文字列なら`False`(LINE版`verify_line_signature()`と同じ
   「未検証時は安全側で拒否」)。
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

- LINE版(本venture`webhook-http-entry-point-design.md`の`verify_line_signature()`)は
  署名アルゴリズムのみで完結し、タイムスタンプの概念が無い(LINE Platform側にリプレイ対策の
  仕組みが別途あるため)。Stripe版はヘッダ自体にタイムスタンプが埋め込まれており、これを
  検証すること自体がStripe公式ドキュメントで明示的に推奨されている。
- 複数署名(`v1`が複数)への対応もLINE版には無い概念で、Stripeのシークレットローテーション
  運用に固有の要件。

## 4. プロトタイプ実装方針

- 新規ファイル`prototype/stripe_webhook.py`に`verify_stripe_signature()`を実装する
  (`cloud_function_webhook.py`とは別ファイルとし、LINE側のコードに一切影響を与えない構成。
  `deletion_candidate.py`をStripe関連の別ファイルとして切り出した前例〈フェーズ124〉を踏襲)。
- テストは`prototype/test_stripe_webhook.py`に新設し、以下を最低限カバーする
  (course-set-pasha版`VerifyStripeSignatureTest`と同じ7ケース):
  1. 正しい署名・許容範囲内のタイムスタンプ → `True`
  2. 署名ヘッダが`None`・空文字列 → `False`
  3. 署名ヘッダの形式が不正(`t=`や`v1=`が無い、無効な文字列) → `False`
  4. 署名が一致しない(誤ったシークレットで計算した署名) → `False`
  5. 署名は一致するがタイムスタンプが許容範囲外(古すぎる・未来すぎる) → `False`
  6. `v1`が複数含まれ、そのうち後方の1つのみが一致する(シークレットローテーション想定) →
     `True`
  7. `v0`のみが一致し`v1`が一致しない(旧方式は無視する方針の確認) → `False`

## 残課題

- (解消済み 2026-09-02 14:02 UTC・フェーズ173点検: 「実際のWebhookエンドポイント本体を結ぶ層は
  次の課題」という本項目は、実際にはフェーズ127(2026-08-27、stripe-webhook-http-entry-point-
  design.md)で`prototype/stripe_webhook.py`の`receive_stripe_webhook()`として既に実装済み
  だったにもかかわらず本ファイルが未訂正のまま残っていた記載漏れと判明した。
  `receive_stripe_webhook()`は`verify_stripe_signature()`→JSONパース→`dispatch_stripe_event()`
  (`customer.subscription.*`)/`handle_checkout_session_completed()`
  (`checkout.session.completed`)への振り分けまでを結線済み。`resolve_user_id`の解決先
  (`stripe_customer_id → user_id`)も`make_resolve_user_id()`(同ファイル)が
  `user_profile_store.get_user_id_by_stripe_customer_id()`(`prototype/user_id_linking.py`、
  インメモリ実装・テスト済み)を返す形で解決済み。実Firestore接続のみが実Stripeアカウント
  接続後の課題として残る)
- `webhook_secret`の実際の値の取得・保管方法(Secret Manager等)は、実Stripeアカウント接続
  (オーナー承認待ち)後の設計課題として別途残る。
- (解消済み 2026-09-04 09:00 UTC・フェーズ183点検: 「エンドポイント本体側の設計課題として
  次回以降に持ち越す」という本項目は、実際にはstripe-event-idempotency-design.mdとして
  設計され`prototype/stripe_webhook.py`に`StripeEventIdStoreProtocol`・
  `InMemoryStripeEventIdStore`・`receive_stripe_webhook()`の`event_id_store`引数
  (指定時、同一`event.id`の2回目以降の配信はハンドラを呼び出さず200を返す)として
  実装済みだったにもかかわらず、本ファイルが未訂正のまま「次回以降」の記載を残していた
  記載漏れと判明した。`test_stripe_webhook.py`の`InMemoryStripeEventIdStoreTest`・
  `event_id_store`関連テストで検証済み。なお本項目の実装作業自体はコミット履歴上
  「フェーズ177」として行われていたが、README.mdの現行フェーズ177エントリは別内容
  (`payment_failure.py`docstring整理)であり、当時の並行作業によるフェーズ番号の
  重複でREADME.md側に本実装のフェーズログ記載が欠落していたことも判明した
  〈詳細はREADME.mdフェーズ183参照〉)
