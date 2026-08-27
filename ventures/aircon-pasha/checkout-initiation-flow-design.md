# 決済導線設計(トライアル終了後・セルフサービスでのStripe Checkout Session作成起動方式)

作成日: 2026-08-27(フェーズ131)

trial-end-notification-design.md 3節・6節「残課題」で繰り返し未確定のまま残っていた、
通知メッセージ内CTA「▼ 有料プランへ進む」リンクの具体的な実現方式(LIFF経由のIDトークン
検証を使うか等)を確定する。course-set-pashaのcheckout-initiation-flow-design.md(フェーズ98)
を参照しつつ、本venture固有の前提差を踏まえて再設計する。

## 1. course-set-pashaとの違い: LIFF登録なしでも認証済みuser_idを取得できる

course-set-pashaのcheckout-initiation-flow-design.mdは、決済ボタンを外部リンク
(トライアル終了通知メッセージ内のリンク、または常設のセルフサービスリンク)として提供する
前提だったため、リンクを踏んだ先のブラウザ上でLINEのuser_idを認証済みの形で取得する手段が
必要になり、LIFFアプリのIDトークン検証方式を採用した。

本ventureはuser-account-linking-design.md 4節で既に整理済みの通り、「Checkout Session
作成時点でuser_idは`user_profile`上で判明済み」という前提が成立する(申込フォーム→LINE
連携が決済より先に完了しているため)。この前提を活かし、決済ボタンを外部リンクではなく
**LINEのFlex Message内のpostbackアクション**として提供する設計を採用する。

postbackイベントは、webhook-http-entry-point-design.md(フェーズ115)の
`verify_line_signature()`によるHMAC-SHA256署名検証を経た`events`配列の一部として届くため、
`event["source"]["userId"]`はLINEプラットフォーム自身が認証した値であることが保証される。
これにより、本venture固有の設計として、course-set-pashaが必要とした「LIFFアプリの
LINE Developersコンソールでの追加登録」「IDトークンをLINE Platform APIに照会する処理
(`/oauth2/v2.1/verify`相当)」の両方を省略できる。決済導線がLINEトーク内で完結する分、
外部ブラウザへの遷移はStripe Checkout Session自体のURL(Stripeドメイン)を開く1回のみになる。

## 2. トリガー元とpostbackデータ設計

- トリガー元は trial-end-notification-design.md 3節のCTA(「▼ 有料プランへ進む」)を、
  プレーンテキストリンク`[決済導線リンク]`からFlex Messageのボタン
  (postbackアクション、`data="action=start_checkout"`、`displayText="有料プランへ進む"`
  ※タップ時にトーク画面へエコー表示する文言)に差し替える。
- `data`文字列はサーバ側(本venture)がメッセージ生成時に固定値として埋め込む値であり、
  ユーザー側で書き換え不可能なため、course-set-pasha同様「連携コードの推測・なりすまし」に
  類する懸念は生じない(postbackの`data`はボタン定義時に決まる固定文字列で、他のuser_idを
  騙る余地がない)。
- 将来、トライアル終了通知以外にも決済導線が必要になった場合(オンボーディング完了時の
  常設セルフサービスリンク等、course-set-pasha 1節(b)相当)に備え、`data`は
  `action=start_checkout`のみとし、将来別アクションを追加する場合は`action=`以降の値で
  分岐する前提とする(現時点では本venture未着手のため設計のみ言及)。

## 3. 処理フロー(設計)

1. `dispatch_webhook_events()`(cloud_function_webhook.py)に`postback`イベント種別の
   振り分けを追加する(現状は「それ以外の種別(postback・join等)は無視」とコメントされて
   おり、本フェーズの対応範囲としてこの一文を「postbackはprocess_postback_event()へ
   振り分け、join等その他は引き続き無視」に更新する必要がある。**振り分け配線自体の実装は
   次回以降の課題とし、本フェーズは4節のパラメータ組み立てロジックの実装にとどめる**)。
2. `process_postback_event(event, user_profile_store)`(新設予定、次回以降の課題)が
   `event["postback"]["data"] == "action=start_checkout"`を確認し、
   `user_id = event["source"]["userId"]`を取得する。
3. `user_profile_store.get(user_id)`で`UserProfile`を取得する。存在しない場合
   (連携未完了のまま何らかの経路でpostbackが送られた異常系)は、user_id_linking.pyの
   既存の未連携案内文言(design 3節)と同じ方針で「先に連携コードの送信が必要です」を返す。
4. 存在する場合、`build_checkout_session_params(user_id, profile.stripe_customer_id)`
   (4節)でStripe Checkout Session作成APIへ渡すパラメータのdictを組み立てる。
5. 実Stripe Checkout Session作成API呼び出し(`stripe.checkout.Session.create(**params)`
   相当)は実Stripeアカウント接続後の話であり、本ドキュメント・本フェーズの範囲外
   (pending-approval.md参照)。呼び出し後に得られるURLをLINEへのreplyメッセージとして
   返す処理も、実API接続後にあわせて設計する。

## 4. プロトタイプ実装方針

course-set-pashaのcheckout_session.pyの`build_checkout_session_params()`と同じ設計を、
本venture向けに`prototype/checkout_session.py`として新設する。本ventureはLIFF IDトークン
検証を経由しないため、`create_checkout_session()`(Authorizationヘッダ・`verify_id_token`
依存)に相当する部分は不要とし、パラメータ組み立て純粋関数のみを先行実装する。

`build_checkout_session_params(user_id, existing_stripe_customer_id=None) -> dict`:

- `user_id`が空文字列・Noneの場合は`ValueError`(呼び出し元でpostbackイベントの
  `source.userId`取得が必ず先に成功している前提を明示するガード)。
- 返り値は`{"mode": "subscription", "client_reference_id": user_id, "success_url": ...,
  "cancel_url": ...}`を基本とし、`existing_stripe_customer_id`が渡された場合のみ
  `"customer"`キーを追加する(既存Stripe顧客の再利用、course-set-pashaと同じ理由)。
- `success_url`/`cancel_url`は本ドキュメントでは仮のプレースホルダ文字列とし、実LPドメイン
  確定後に差し替える(定数として関数の外に切り出し、テストでは上書き可能にする)。

## 5. trial-end-notification-design.mdへの反映

trial-end-notification-design.md 3節・6節の「CTAリンクの具体的な実現方式(LIFF経由の
IDトークン検証を使うか等)は未確定」という記述は、本ドキュメントにより「postbackアクション
方式に決定・LIFF不要」として解消済みとする。該当箇所は本フェーズであわせて更新する。

## 残課題

- `dispatch_webhook_events()`への`postback`イベント種別の振り分け配線、
  `process_postback_event()`本体の実装(2節手順1〜3)は次回以降の課題として残す。
- 実Stripe Checkout Session作成API呼び出し・LINEへのURL返信処理は、実Stripeアカウント
  接続後(オーナー承認待ち)にあわせて設計する。
- `success_url`/`cancel_url`の実際のLPドメイン確定はLP実装(オーナー承認待ち)と合わせて行う。
- 決済完了後のStripe側処理(`checkout.session.completed`受信)は
  checkout-session-completed-handling-design.md(フェーズ128)で既に設計・実装済みのため、
  本ドキュメントの対応範囲外(既存フローにそのまま接続できる)。
