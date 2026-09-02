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

## 7. checkout.session.completed Webhookハンドラ実装(2026-08-28追記・続き)

上記「残課題」にあった、`checkout.session.completed`イベント受信時に
`store.set_stripe_customer_id()`を呼ぶWebhookハンドラ本体
(course-set-pasha/stripe_webhook.pyの`handle_checkout_session_completed()`相当)を
`prototype/store_profile_store.py`に実装した。course-set-pasha版と異なり、本ventureは
upgraded_at相当のフィールドを持たない(有料転換の判定は
`cloud_function_subscription_activated_webhook.py`がsuspension_reasonの書き換えで別途
担当しており、書き込み対象・トリガーが既に別モジュールに分かれている)ため、
`usage_counter`引数は持たせず、`client_reference_id`(user_id)・`customer`
(stripe_customer_id)を取り出して`store.set_stripe_customer_id()`を呼ぶだけの薄い版とした。
いずれかが欠落・非文字列・空文字列の場合は何も書き込まない安全側の設計はcourse-set-pasha版と
同じ。テスト8件追加(欠落・空文字列・非文字列・Webhook再送での冪等性を含む)、venture全体
345件全件パス・schema検証25件パスを確認した。

## 8. オンボーディング完了メッセージの文言設計(2026-08-29追記・解消)

上記「残課題」にあった、1(b)「オンボーディング完了メッセージへの常設セルフサービス
リンク」の文言自体を`onboarding-completion-message-design.md`として新規に設計した。
送信タイミングは「MVPの最低限必須項目が初めて全て揃った時点(店舗全体で1回のみ)」とし、
3トーン分の文言・`prototype/onboarding_completion_message.py`の
`render_onboarding_completion_message()`を実装した。テスト8件追加、venture全体353件
全件パスを確認した。発火判定の本体配線(店舗設定の保存処理側)は
owner-settings-wireframe.mdのフォーム保存処理自体が未実装のため、引き続き未着手として
下記残課題に記録した。

## 9. store-id-resolution-and-owner-identity-design.mdとの整合(訂正、フェーズ続き169)

store-id-resolution-and-owner-identity-design.md(フェーズ続き165〜168)により、本ドキュメント
0節・2節・3節・4節が前提としていた「LIFF IDトークンで得た個人LINE user_idをそのまま
`store_id`(`client_reference_id`)として扱う」という設計は訂正が必要であることが判明した。
本節に正しい前提を記録する。

- **0節・2節への訂正**: `store_id`は`destination`(店舗の公式アカウント自身のuserId、
  store-id-resolution-and-owner-identity-design.md 3節参照)を正とする。LIFF
  `liff.getIDToken()`で得られる個人`user_id`(店舗オーナー本人のLINE userId)は`store_id`
  そのものではない。
- **3節への訂正**: Checkout Session作成エンドポイントの手順を以下のように改める。
  1. LIFF起動リンクのクエリパラメータ(`?store_id=<destination値>`)から`store_id`を
     受け取る(store-id-resolution-and-owner-identity-design.md 2節)。
  2. `Authorization`ヘッダのLIFF IDトークンをLINE Platform APIで検証し、個人`user_id`
     (操作者本人)を取得する。
  3. `stores/{store_id}.owner_user_id`と検証済み個人`user_id`が一致するかを確認する
     認可チェックを行う(不一致・`owner_user_id`未設定の場合は決済を拒否する。文言は
     引き続き未設計)。
  4. 3.を通過した場合のみ、3節手順3以降(既存`stripe_customer_id`確認〜Checkout Session
     作成)を、`store_id`をキーとして実行する。`client_reference_id`には個人`user_id`では
     なく`store_id`を設定する。
- **コードへの影響は無い**: store-id-resolution-and-owner-identity-design.md 4節の結論
  どおり、`prototype/store_profile_store.py`・`prototype/checkout_session.py`の各関数は
  いずれも引数名`user_id`をキーとして扱う実装のままでよく、書き直しは不要。呼び出し元が
  渡す値の由来(個人LINE userId → `store_id`(`destination`))が変わるだけである。
  `build_checkout_session_params(user_id, ...)`の`user_id`引数も、実際には`store_id`を
  渡す想定に読み替える(関数シグネチャ自体の変更は次回以降、実装着手時に行う)。
- 上記3.の認可チェック自体の実装(`owner_user_id`の参照元含む)は、実Firestore接続待ちの
  ため引き続き未着手のまま残る(store-id-resolution-and-owner-identity-design.md「残課題」
  参照)。

## 残課題

- LIFFアプリのLINE Developersコンソールでの実登録、LINE公式アカウントの開設(Basic ID
  確定)はオーナー承認待ち(pending-approval.mdに記録する)。
- `resolve_existing_stripe_customer_id()`・`handle_checkout_session_completed()`を実際に
  Cloud Functions側のCheckout Session作成エンドポイント・Stripe Webhook受信エンドポイント
  本体に配線する処理(実HTTPハンドラ・実Stripe API呼び出し)は未実装。実アカウント接続後に
  着手する。うち署名検証部分(`verify_stripe_signature()`)は実アカウント接続前でも机上
  実装・テスト可能だったため、stripe-webhook-signature-verification-design.md(フェーズ続き
  158)として先行着手済み。エンドポイント本体(署名検証〜イベント種別ディスパッチ〜各
  ハンドラ呼び出しを結ぶ層)は引き続き未着手のまま残る。
- IDトークン検証の実装(LINE Platform APIの`/oauth2/v2.1/verify`相当)は実LIFF登録後に着手。
- `success_url`ページの実際のHTML/デザインは、LP実装(オーナー承認待ち)とあわせて行う。
- オンボーディング完了メッセージの発火判定・1回のみ発火の制御の本体配線は、
  owner-settings-wireframe.mdのフォーム保存処理の実装着手時にあわせて設計する
  (onboarding-completion-message-design.md参照)。
