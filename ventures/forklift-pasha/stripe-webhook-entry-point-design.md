# Stripe Webhook受信エントリポイント設計

README.mdフェーズ125・126の「次回候補(2)(3)」(`FleetOperatorStoreProtocol`への
`email`/`stripe_customer_id`読み書きメソッド追加→完了、Webhook受信エントリポイントの
実装)のうち、残っていた(3)に着手する。

## 1. 位置づけ

aircon-pasha/prototype/stripe_webhook.py・course-set-pasha/prototype/stripe_webhook.pyと
同じ位置づけ: 実Stripeアカウント接続(オーナー承認待ち、pending-approval.md参照)なしでも
検証できる、`Stripe-Signature`ヘッダの検証ロジックと`checkout.session.completed`受信時の
紐付け処理を切り出したモジュール(`prototype/stripe_webhook.py`)。

本ventureは他venture(aircon-pasha等)と異なり、`customer.subscription.*`系イベントを
処理する`stripe_dispatch.py`・決済失敗検知(`payment_failure.py`相当)・解約通知等が
まだ一切存在しないため、本フェーズのスコープは`checkout.session.completed`の受信・紐付けと
署名検証のみに限定する(他ventureのような多数のオプション引数〈`payment_store`・
`plan_store`・`event_id_store`等〉は本venture未着手の機能に対応するものであり、今回は
導入しない。将来それらの機能を追加する際に合わせて拡張する)。

## 2. 署名検証

aircon-pasha/course-set-pashaの`verify_stripe_signature()`と同一のアルゴリズム
(venture固有の差異は無い、Stripe公式の検証方式に従うため)をそのまま踏襲する。

## 3. `checkout.session.completed`の紐付け

payment-identity-verification-design.md 3節の設計どおり:

- `client_reference_id`(= `internal_id`、checkout_session.build_checkout_session_params()が
  Checkout Session作成時に設定した値)と`customer`(= `stripe_customer_id`)を取り出す。
- 両方が非空文字列の場合のみ、`FleetOperatorStoreProtocol.set_stripe_customer_id()`で
  紐付けを書き込む。
- `metadata.plan`(同じくbuild_checkout_session_params()が設定した値)を
  `plan_id_resolution.write_plan_id_from_checkout_session_metadata()`にそのまま渡し、
  plan_idの初回記録を行う(未知の値・欠落時は書き込まない、同関数の既存の安全側方針)。
- `upgraded_at`(trial_management.FleetOperatorStoreProtocol)は「有料転換時に設定する」
  フィールドのため、`get_upgraded_at(internal_id)`が未設定(None)の場合のみ
  `set_upgraded_at(internal_id, now)`を書き込む(同フィールドのdocstringは上書き可能と
  しているが、「初回の有料転換日時」を保持する値として扱うほうが実用上の意味が明確なため、
  本モジュールでは「未設定時のみ書き込み」を採用する)。

本venture固有の設計判断として、aircon-pashaの`handle_checkout_session_completed()`が
行う「対応する`user_profile`が存在しない場合は異常系として書き込みをスキップする」という
事前存在チェックは**行わない**。aircon-pasha等は決済前にLINEの`follow`イベント経由で
`user_profile`が必ず作成されている前提があるが、本venture(Webフォームのみ、LINE非依存)は
`fleet_operator`ドキュメント自体がいつ作成されるかの運用がまだ確定していない
(firestore-data-model.md参照、Webフォームのプラン選択UI自体が未実装)。そのため、
`internal_id`の形式さえ正しければ`FleetOperatorStoreProtocol`への書き込みをそのまま
試みる(存在しない`internal_id`への書き込みが問題になるのは実Firestore接続後の課題として
残し、現時点のInMemory実装・pure関数検証の範囲では support対象としない)。

## 4. 残課題

- 実HTTPリクエストオブジェクト(`functions_framework`の`request`)からの`body`・
  `Stripe-Signature`ヘッダ取り出し配線は`main(request)`として用意するが、実Cloud Functions
  デプロイ自体はオーナー承認待ち(アカウント作成に該当)。
- `customer.subscription.updated`等(`plan_id_resolution.sync_plan_id_on_subscription_
  event()`が既に用意済みだが未配線)の受信・ディスパッチは次回以降の課題。
- Webフォームのプラン選択UI自体(Checkout Session発行の起点)は本venture未着手のまま。

最終更新: 2026-10-11 14:00 UTC(フェーズ127: README.mdフェーズ125「次回候補(2)」
〈フェーズ126で解消〉に続く(3)に対応し、本設計に基づき`prototype/stripe_webhook.py`を
新設した)
