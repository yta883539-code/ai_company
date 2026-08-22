# Stripe Webhook署名検証の設計

作成日: 2026-08-22(フェーズ93)

README.md「次にやること(候補)」で次回優先候補とされていた、実Stripe Webhook受信
エンドポイントのうち「署名検証方式(HMAC-SHA256、`Stripe-Signature`ヘッダのタイムスタンプ
許容範囲チェックを含む)」に対応する。`receive-webhook-http-entry-point-design.md`の
LINE版(`verify_line_signature()`)と同様、実Stripeアカウント作成・Webhookエンドポイント
登録(いずれもオーナー承認待ち)なしでも、署名検証ロジック自体は公開されているアルゴリズム
仕様のみから机上実装・テスト可能なため、今回はこの部分のみを先行して設計・実装する。

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

1. `sig_header`が`None`または空文字列なら`False`(LINE版と同じ「未検証時は安全側で拒否」)。
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

`now`(Unixタイムスタンプ、float)を省略可能な引数として持たせるのは、`verify_line_signature()`
には無かった要素だが、タイムスタンプ許容範囲チェック自体が「現在時刻」に依存するテストに
なるため、`receive-webhook-http-entry-point-design.md`の`now`引数(JST日時)と同じ理由で
テスト時に固定時刻を注入できるようにするため。省略時は`time.time()`を使う。

## 3. LINE版との違い

- LINE版(`verify_line_signature`)は署名アルゴリズムのみで完結し、タイムスタンプの概念が
  無い(LINE Platform側にリプレイ対策の仕組みが別途あるため)。Stripe版はヘッダ自体に
  タイムスタンプが埋め込まれており、これを検証すること自体がStripe公式の推奨事項
  (`Ignore the timestamp unless you have a specific need`ではなく、逆にWebhookエンドポイント
  側で許容範囲チェックを行うことが公式ドキュメントで明示的に推奨されている)。
- 複数署名(`v1`が複数)への対応もLINE版には無い概念で、Stripeのシークレットローテーション
  運用に固有の要件。

## 4. プロトタイプ実装方針

- 新規ファイル`prototype/stripe_webhook.py`に`verify_stripe_signature()`を実装する
  (`cloud_function_webhook.py`とは別ファイルとし、LINE側のコードに一切影響を与えない構成。
  `deletion_candidate.py`をStripe関連の別ファイルとして切り出した前例を踏襲)。
- テストは`prototype/test_stripe_webhook.py`に新設し、以下を最低限カバーする:
  1. 正しい署名・許容範囲内のタイムスタンプ → `True`
  2. 署名ヘッダが`None`・空文字列 → `False`
  3. 署名ヘッダの形式が不正(`t=`や`v1=`が無い、空のヘッダ文字列) → `False`
  4. 署名が一致しない(誤ったシークレットで計算した署名) → `False`
  5. 署名は一致するがタイムスタンプが許容範囲外(古すぎる・未来すぎる) → `False`
  6. `v1`が複数含まれ、そのうち後方の1つのみが一致する(シークレットローテーション想定) →
     `True`
  7. `v0`のみが一致し`v1`が一致しない(旧方式は無視する方針の確認) → `False`

## 残課題

- 実際のWebhookエンドポイント本体(`receive_webhook()`のStripe版に相当する、リクエスト
  ボディの受け取り〜`verify_stripe_signature()`〜イベント種別(`customer.subscription.deleted`
  等)ディスパッチ〜`mark_deletion_candidate_on_subscription_deleted()`等の呼び出し)は、
  今回のスコープ外(署名検証のみ先行実装)として次の課題に残す。
- `webhook_secret`の実際の値の取得・保管方法(Secret Manager等)は、実Stripeアカウント接続
  (オーナー承認待ち)後の設計課題として別途残る。
- Stripeイベントの重複配信対策(`event.id`によるべき等性チェック)は、エンドポイント本体側の
  設計課題として次回以降に持ち越す(署名検証層のスコープ外)。
