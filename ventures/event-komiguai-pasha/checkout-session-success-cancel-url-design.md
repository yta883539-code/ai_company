# Checkout Session success_url/cancel_url 構築方式設計(フェーズ104)

one-time-checkout-no-account-design.md(フェーズ10)2節手順3「Stripe Checkout Session
(`mode: "payment"`)を作成する」は`success_url`/`cancel_url`の具体的な構築方式を定めて
おらず、`prototype/checkout_session_creation.py`(フェーズ103)の
`StripeCheckoutSessionClientProtocol.create_session()`にも両フィールドが未実装のまま
残っていた(フェーズ103の次回候補(2)「実Stripe SDK実装をどう構成するか」に着手する前段
として、本フェーズで先にこの未設計を解消する)。

## 1. 前提

- result-page-ttl-access-design.md(フェーズ14)が結果ページURLを`/result/{draft_id}`と
  確定済み。
- custom-domain-vs-default-url-decision.md(フェーズ50)が、初回ローンチ時点では
  Cloud RunデフォルトURL(`*.run.app`)を採用し、success_url/cancel_url自体はホスト名に
  依存しない設計であることを確認済み(5節)。すなわち「ホスト名(`base_url`)+パス」の
  組み立て方式であれば、デフォルトURL採用時・将来の独自ドメイン移行時のいずれでも
  コード変更なく対応できる。

## 2. success_url の構築

- `{base_url}/result/{draft_id}` とする。`draft_id`はCheckout Session作成前
  (`create_checkout_session_for_event_memo()`内でdraft作成時)に確定済みのため、
  Stripeの `{CHECKOUT_SESSION_ID}` テンプレート変数は使用しない(他venture の継続課金
  モデルでは`account_id`がURLに不要なため同変数を使う例があるが、本ventureは
  `draft_id`自体が主キーであり、Checkout Session作成前から既知であるため不要)。
- クエリパラメータは付与しない。`/result/{draft_id}`は推測不能なUUID4を含むURLそのものが
  実質的なアクセストークンを兼ねる設計(idempotency-key-duplicate-detection-firestore-
  query-design.md 88行目で既述)であり、追加のトークンをクエリに載せる必要はない。

## 3. cancel_url の構築

- `{base_url}/` (Webフォーム入力ページのトップ)とする。`draft_id`は付与しない。
- 理由: one-time-checkout-no-account-design.md 3節の表が明記するとおり、本ventureは
  「次回利用時も同一account_idで継続」する継続課金モデルと異なり「次回利用時は新規
  `draft_id`を再発行(再利用なし)」という使い切り設計が前提のため、決済キャンセル時に
  既存`draft_id`へ入力内容を復元して再開させる機能は持たない。キャンセルした主催者は
  入力ページから再度入力し直す(5入力要素は短時間で再入力可能な分量、market-research.md
  想定の利用頻度〈月数件程度〉を踏まえても再入力コストは小さいと判断する)。
- キャンセルされた`one_time_draft/{draft_id}`は`status: awaiting_payment`のまま残るが、
  TTL(24時間、ttl-expiry-result-delivery-refund-design.md フェーズ12)により自動失効する
  ため、キャンセル時点での明示的な削除処理は不要(既存のTTL失効設計に委ねる)。

## 4. 実コード化方針(フェーズ103 `checkout_session_creation.py`への反映)

- `create_checkout_session_for_event_memo()`に`base_url`引数(必須、末尾スラッシュなし
  前提)を追加し、`StripeCheckoutSessionClientProtocol.create_session()`の呼び出し時に
  `success_url=f"{base_url}/result/{draft_id}"`・`cancel_url=f"{base_url}/"`を渡す。
- `StripeCheckoutSessionClientProtocol.create_session()`のシグネチャに
  `success_url: str`・`cancel_url: str`を追加する(実Stripe SDK実装時は
  `stripe.checkout.Session.create(..., success_url=success_url, cancel_url=cancel_url)`
  へそのまま渡す想定、実際の呼び出しはフェーズ103同様オーナー承認待ちの範囲として
  据え置く)。

## 5. 未検証・残課題

- 実際の`base_url`の値(デフォルトURL`*.run.app`か独自ドメインか)は、custom-domain-vs-
  default-url-decision.md(フェーズ50)の暫定方針どおりデフォルトURL採用だが、実際の値は
  GCPプロジェクト作成・Cloud Runデプロイ後(オーナー承認待ち)にしか確定しない。本設計は
  `base_url`を呼び出し側の引数として受け取るため、値が未確定の現時点でもコード化は可能
  (次回候補(2)の実Stripe SDK実装構成の検討もこの前提で進める)。

最終更新: 2026-11-08 15:00 UTC(フェーズ104: success_url/cancel_urlの構築方式を設計。
success_urlは`/result/{draft_id}`、cancel_urlは入力ページトップとし、`base_url`を
呼び出し側引数として受け取る方式に確定)
