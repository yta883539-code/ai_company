# 決済導線設計(申込・トライアル後のStripe Checkout Session作成)

作成日: 2026-08-23(フェーズ98)

stripe-customer-id-linking-design.md(フェーズ97)「残課題」1点目、「Stripe Checkout
Session作成時に`client_reference_id`へ内部`user_id`を設定する導線(決済ボタン設置・
Checkout Session作成API呼び出し)自体は本ドキュメントの範囲外で未設計。申込フォーム提出後の
決済導線として別途設計が必要」に対応する。

## 1. トリガーのタイミング

pricing-plan.mdの無料トライアル条件(クレジットカード登録なしで開始、トライアル終了時は
自動課金せず本人が有料プランを選択する場合のみ課金開始)を踏まえると、Checkout Session
作成は「申込・トライアル開始時」ではなく「本人が有料プランへ進むボタンを押した時」にのみ
発生させる設計とする。

トリガー元として2経路を想定する:

- (a) トライアル終了が近づいた際の通知メッセージ内の「有料プランへ進む」リンク
  (aircon-pasha/limit-approaching-notification-design.md相当の通知を本venture向けにも
  設計する必要があるが、本ドキュメントの範囲外。次の課題として残す)
- (b) オンボーディング完了メッセージ等に常設する、いつでも有料プランへ切り替えられる
  セルフサービスリンク

## 2. user_id取得方式の比較

- **署名付きURLパラメータにuser_idを埋め込む方式**: 実装は簡単だが、決済という金銭が絡む
  導線でリンクの転送・推測により第三者のuser_idになりすまして決済させられるリスクがあり、
  防ぐには自前の署名検証ロジックを追加実装する必要が生じ複雑化する。
- **LINE LIFF (LINE Front-end Framework) アプリを使う方式**: ボタンをLIFFアプリのURLとして
  提供し、LIFF SDKの`liff.getIDToken()`から得られるIDトークンをサーバ側でLINE Platform APIに
  照会してLINEのuserId(=本ventureの内部`user_id`)を取得する。LINEプラットフォーム自身が
  認証を担うため、自前のなりすまし対策が不要になる。ただしLIFFアプリ自体はLINE Developers
  コンソールでの追加登録(外部サービスへの設定)が必要。

**結論(暫定)**: LIFF方式を採用する。決済が絡む導線ではなりすましリスクを避けることを
優先する。LIFFアプリ登録の実施自体はオーナー承認待ち事項としてpending-approval.mdに記録し、
本ドキュメントでは設計にとどめる。

## 3. Checkout Session作成エンドポイント(設計)

新設のCloud Functions HTTPエンドポイント`create_checkout_session(request)`を想定する。

1. リクエストヘッダ`Authorization: Bearer <LIFF IDトークン>`を受け取る。
2. IDトークンをLINE Platform APIで検証し、LINEのuserId(本ventureの`user_id`)を取得する
   (実装は実LIFF登録後)。
3. `user_profile`ストアの`get_stripe_customer_id(user_id)`(順引き、
   stripe-customer-id-linking-design.md 2節で定義済みの逆と対になる読み出し)で既存の
   `stripe_customer_id`を確認する。既に決済経験がある場合(過去に解約して再度契約する場合等)
   は同一customerを再利用し、Stripe側に重複顧客レコードを作らない。
4. Stripe Checkout Session作成APIを、`mode=subscription`・`client_reference_id=user_id`・
   (既存customerがあれば`customer=<既存stripe_customer_id>`)・`success_url`/`cancel_url`
   を指定して呼び出す(下記4節の`build_checkout_session_params()`が組み立てるdictをそのまま
   渡す想定)。
5. 生成されたCheckout SessionのURLをレスポンスとして返し、LIFFページ側がそこへリダイレクト
   する。

IDトークン検証・実Stripe API呼び出しは実アカウント接続後の話であり、本ドキュメントでは
机上設計にとどめる。

## 4. プロトタイプ実装方針

実LINE Platform API・実Stripe API呼び出し自体はスタブ化せず対象外とし、Checkout Session
作成APIへ渡すパラメータを組み立てる部分だけを純粋関数として切り出し、実HTTPリクエストなしで
検証可能にする。

`build_checkout_session_params(user_id, existing_stripe_customer_id=None) -> dict`
(新設`prototype/checkout_session.py`):

- `user_id`が空文字列・Noneの場合は`ValueError`(呼び出し元の認証済みuser_id取得が
  必ず先に成功している前提を明示するガード)。
- 返り値は`{"mode": "subscription", "client_reference_id": user_id, "success_url": ...,
  "cancel_url": ...}`を基本とし、`existing_stripe_customer_id`が渡された場合のみ
  `"customer"`キーを追加する。
- `success_url`/`cancel_url`は本ドキュメントでは仮のプレースホルダ文字列とし、実LP
  ドメイン確定後に差し替える(定数として関数の外に切り出し、テストでは上書き可能にする)。

## 残課題

- LIFFアプリのLINE Developersコンソールでの実登録(オーナー承認待ち。実施した場合、
  pending-approval.mdに記録する)。
- トライアル終了通知メッセージ自体(上記1(a))は本venture未設計。次の課題として残す。
- IDトークン検証の実装(LINE Platform APIの`/oauth2/v2.1/verify`相当)は実LIFF登録後に着手。
- `success_url`/`cancel_url`の実際のLPドメイン確定はLP実装(オーナー承認待ち)と合わせて行う。
