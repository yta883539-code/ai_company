# 決済導線設計(トライアル終了後・有料プラン選択時のStripe Checkout Session作成)

作成日: 2026-08-28(フェーズ続き139)

billing-upgrade-flow-design.md「次のステップ候補」の「休止モードへの移行ロジック・
再通知設計の詳細化」とは別に、同ドキュメント3節で「決済完了後にLINEへ戻る導線
(success_url先の案内ページでLINEアプリへの復帰リンクを提示する等)は、
checkout-initiation-flow-design.mdの実装着手時にあわせて設計する残課題として残す」と
明記されていた。本ventureにはcourse-set-pasha/aircon-pashaのような決済導線設計
(checkout-initiation-flow-design.md)がまだ存在しなかったため、本ドキュメントで新規に
設計し、あわせてLINEへ戻る導線も具体化する。

## 0. 前提の整理(本venture固有)

course-set-pasha・aircon-pashaは「個人ユーザー(施設利用者)のLINE user_id」に対して
課金する設計だったが、本venture(line-reservation-ai)は店舗オーナーのLINE公式アカウントを
通じて予約対応を行うサービスであり、課金対象は「店舗オーナー」である。よって本設計での
`user_id`は店舗オーナーのLINE user_id(店舗の管理者アカウントが友だち追加している公式
アカウント運用アカウント宛のuser_id)を指す。trial-to-paid-billing-flow-consistency-check.mdの
結論(「レポート提示→本人の能動的な有料プラン選択→その時点で初めてカード登録」の順序)を
そのまま踏襲する。

## 1. トリガーのタイミング

pricing-plan.mdの無料トライアル条件(カード登録なしで開始、トライアル終了時は自動課金せず
本人が有料プランを選択する場合のみ課金開始)を踏まえ、Checkout Session作成は「本人が
有料プランへ進むボタンを押した時」にのみ発生させる。

トリガー元として2経路を想定する(course-set-pasha/checkout-initiation-flow-design.mdと
同型):

- (a) `prototype/trial_end_report_scheduler.py`(フェーズ続き、2026-08-21 13:00 UTC実装済み)が
  送信するトライアル終了レポート内の「有料プランへ進む」リンク。
- (b) オンボーディング完了メッセージ等に常設する、いつでも有料プランへ切り替えられる
  セルフサービスリンク(現時点では該当メッセージ自体が未設計。次の課題として残す)。

## 2. user_id取得方式の比較

course-set-pasha・aircon-pashaと同じ比較を行い、同じ結論に至る。

- **署名付きURLパラメータ方式**: 実装は簡単だが、決済という金銭が絡む導線でリンクの
  転送・推測による第三者へのなりすましリスクがあり、防ぐには自前の署名検証ロジックが必要。
- **LINE LIFFアプリ方式**: `liff.getIDToken()`で得たIDトークンをLINE Platform APIに
  照会してLINEのuserIdを取得する。LINEプラットフォーム自身が認証を担うためなりすまし
  対策が不要。LIFFアプリ自体の登録(LINE Developersコンソール)が必要。

**結論(暫定)**: LIFF方式を採用する。LIFFアプリ登録はオーナー承認待ち事項として
pending-approval.mdに記録し、本ドキュメントでは設計にとどめる。

## 3. Checkout Session作成エンドポイント(設計)

新設のCloud Functions HTTPエンドポイント`create_checkout_session(request)`を想定する。

1. リクエストヘッダ`Authorization: Bearer <LIFF IDトークン>`を受け取る。
2. IDトークンをLINE Platform APIで検証し、店舗オーナーのuser_idを取得する
   (実装は実LIFF登録後)。
3. 店舗プロフィールストア(現時点では未実装。本ドキュメントで
   `get_stripe_customer_id(user_id)` / `set_stripe_customer_id(user_id, customer_id)`の
   2メソッドを持つProtocolとして定義し、Firestoreの店舗設定コレクション
   〈firestore-data-model.md参照〉に`stripe_customer_id`フィールドを追加する形で
   実装する想定。既存フィールドとの衝突はないため後方互換性の懸念なし)で既存の
   `stripe_customer_id`を確認し、過去に契約歴がある店舗は同一customerを再利用する。
4. Stripe Checkout Session作成APIを、`mode=subscription`・`client_reference_id=user_id`・
   (既存customerがあれば`customer=<既存stripe_customer_id>`)・`success_url`/`cancel_url`
   を指定して呼び出す(下記4節`build_checkout_session_params()`が組み立てるdictをそのまま
   渡す想定)。
5. 生成されたCheckout SessionのURLを返し、LIFFページ側がそこへリダイレクトする。

IDトークン検証・実Stripe API呼び出しは実アカウント接続後の課題であり、本ドキュメントでは
机上設計にとどめる。

## 4. 決済完了後にLINEへ戻る導線(本ドキュメントでの新規検討事項)

billing-upgrade-flow-design.mdで残課題化されていた項目。Stripe Checkoutの`success_url`は
自ホストのWebページを指定でき、決済完了直後にそのページがブラウザで開く
(billing-upgrade-flow-design.mdの結論どおり、LIFFアプリ内ブラウザではなく`external: true`で
OS標準ブラウザへ切り替えて決済するため、success_urlのページもOS標準ブラウザ上に表示される)。

検討した3案:

- **LINE公式アカウントのトーク画面を開くリンク(`https://line.me/R/ti/p/<Basic ID>`形式の
  ユニバーサルリンク)を設置する案**: LINEアプリが端末にインストールされていればアプリを
  起動しトーク画面へ遷移、未インストールならブラウザでLINEのダウンロード誘導ページへ
  遷移する標準的な挙動。実装が単純(静的リンク1本)で、店舗オーナー側の追加設定が不要。
- **`line://`カスタムURLスキーム直接指定案**: 端末・OSバージョンによっては非対応
  ブラウザ挙動の差異が報告されており、公式ドキュメントでも新規実装にはユニバーサルリンク
  (`https://line.me/...`)の使用が推奨されている。
- **LIFFアプリを経由して`liff.closeWindow()`で閉じる案**: そもそも今回の決済導線は
  `external: true`でLIFFの外(OS標準ブラウザ)に出る設計のため、`liff.closeWindow()`
  (LIFFブラウザ内でのみ有効)は適用できない。

**結論**: success_urlページには「LINEに戻る」ボタンを1つ設置し、
`https://line.me/R/ti/p/<公式アカウントのBasic ID>`形式のユニバーサルリンクを割り当てる
(1つ目の案を採用)。Basic IDは公式アカウント開設(オーナー承認待ち)後に確定するため、
実装ではプレースホルダ定数として切り出し、開設後に差し替え可能にする。success_urlページの
文言は「お支払いが完了しました。LINEに戻って引き続きご利用ください」を基本形とし、
message-tone-variants.mdのトーン分岐はLINEメッセージ本体(トライアル終了レポート等)のみに
適用し、Web側の静的ページは単一トーン(standard相当)で統一する(Web側の店舗オーナーは
単一の管理担当者であることが多く、トーン分岐の複雑化に見合う効果が薄いと判断)。

## 5. プロトタイプ実装方針

course-set-pasha/prototype/checkout_session.pyと同じ考え方で、Checkout Session作成APIへ
渡すパラメータを組み立てる部分とLINEへ戻るリンクを組み立てる部分を、実HTTPリクエストなしで
検証可能な純粋関数として切り出す。

`build_checkout_session_params(user_id, existing_stripe_customer_id=None) -> dict`
(新設`prototype/checkout_session.py`):

- `user_id`が空文字列・Noneの場合は`ValueError`。
- 返り値は`{"mode": "subscription", "client_reference_id": user_id, "success_url": ...,
  "cancel_url": ...}`を基本とし、`existing_stripe_customer_id`が渡された場合のみ
  `"customer"`キーを追加する。

`build_line_return_link(basic_id) -> str`(同ファイル内):

- `basic_id`が空文字列・Noneの場合は`ValueError`。
- `https://line.me/R/ti/p/{basic_id}`を返す(URLエンコードは`basic_id`が英数字主体の
  LINE Basic ID仕様上不要だが、念のため`urllib.parse.quote`を通す)。

`success_url`/`cancel_url`・`basic_id`は本ドキュメントでは仮のプレースホルダとし、実LP
ドメイン・公式アカウント開設後に差し替える(定数として関数の外に切り出し、テストでは
上書き可能にする)。

## 6. 店舗プロフィールストア実装(2026-08-28追記)

上記「残課題」にあった店舗プロフィールストア(`stripe_customer_id`保持用)を実装した。
firestore-data-model.md 1節`stores/{storeId}`ドキュメントへ`stripeCustomerId`フィールドを
追加し、`prototype/store_profile_store.py`に`StoreProfileStoreProtocol`
(`get_stripe_customer_id`/`set_stripe_customer_id`の順引き2メソッドのみ。本ventureでは
Webhookディスパッチ側のresolve_user_id〈逆引き〉が別課題として未着手のため、
course-set-pasha/stripe-customer-id-linking-design.mdの`UserProfileStoreProtocol`より
薄いスコープとした)と、その場しのぎ検証用の`InMemoryStoreProfileStore`を実装した。
3節手順3の「既存customerを確認する処理」との結線点として`resolve_existing_stripe_customer_id
(user_id, store) -> Optional[str]`も追加し、呼び出し元(Checkout Session作成エンドポイント
予定地)が`store`の型を意識せず`StoreProfileStoreProtocol`のみに依存できるようにした。
テスト8件追加、venture全体337件全件パスを確認した。

## 残課題

- LIFFアプリのLINE Developersコンソールでの実登録、LINE公式アカウントの開設(Basic ID
  確定)はオーナー承認待ち(pending-approval.mdに記録する)。
- `resolve_existing_stripe_customer_id()`を実際に`build_checkout_session_params()`の
  呼び出し前に配線するCheckout Session作成エンドポイント本体(Cloud Functions側)は未実装。
  実Stripe API呼び出しと合わせて実アカウント接続後に着手する。
- `checkout.session.completed`イベント受信時に`store.set_stripe_customer_id()`を呼ぶ
  Webhookハンドラ(course-set-pasha/stripe_webhook.pyの
  `handle_checkout_session_completed()`相当)は本ventureでは未実装。次の課題として残す。
- IDトークン検証の実装(LINE Platform APIの`/oauth2/v2.1/verify`相当)は実LIFF登録後に着手。
- 上記1(b)「オンボーディング完了メッセージへの常設セルフサービスリンク」の文言自体は
  未設計。次の課題として残す。
- `success_url`ページの実際のHTML/デザインは、LP実装(オーナー承認待ち)とあわせて行う。
