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

## 10. 認可チェック不一致時のエラー文言・案内先設計(フェーズ続き171・新規)

store-id-resolution-and-owner-identity-design.md「残課題」に残っていた、9節手順3の認可
チェック(`stores/{store_id}.owner_user_id`と検証済み個人`user_id`の一致確認)が不一致
だった場合の、オーナー向けエラー文言・案内先を設計する。

### 想定される不一致の種類

9節手順3の認可チェックが失敗するケースは2種類あり、原因が異なるため文言も分ける。

1. **`owner_user_id`未設定**: 店舗が接続テスト(owner-notification-channel-design.md
   参照、公式アカウントへの特別な発言でオーナーを特定する運用)をまだ実施しておらず、
   `stores/{store_id}.owner_user_id`自体が保存されていない状態。この場合は「誰も
   決済できない」状態であり、店舗側の設定不備が原因。
2. **個人`user_id`不一致**: `owner_user_id`は設定済みだが、LIFFを起動した人物(検証済み
   個人`user_id`)がその値と一致しない状態。想定される主因は、オーナー以外の人物
   (スタッフ・顧客等)が誤ってLIFF起動リンクを開いた、または不正な`store_id`クエリ
   パラメータ(9節・3節「残課題」参照、改ざんされた場合でもこの認可チェックが最終防波堤
   となる)を渡された場合。

### 表示方法

success_urlページ(4節)と同じく、認可チェック自体はCheckout Session作成エンドポイント
(サーバーサイド)で行うため、エラー時はCheckout Sessionを作成せず、エンドポイントが
直接エラーページ(Web静的ページ)を返す構成とする(LIFFページ→サーバーサイドの往復では
なく、サーバーサイドが最終的にブラウザへ返すレスポンスの一種という位置づけ)。4節の
結論(Web側の静的ページは店舗オーナーという単一の管理担当者向けであり、トーン分岐に
見合う効果が薄い)を踏襲し、エラーページもトーン分岐しない単一文言とする。

- 「`owner_user_id`未設定」時: 接続テストの実施を促す文言とする。
- 「個人`user_id`不一致」時: オーナー本人のLINEアカウントでの再試行を促す文言とする。

いずれも4節と同じ「LINEに戻る」ボタン(`build_line_return_link()`のユニバーサルリンク)を
併設し、エラー画面で行き止まりにしない。

### プロトタイプ実装

`prototype/checkout_session.py`に以下を実装した(store-profile-store.pyへの
`get_owner_user_id()`/`set_owner_user_id()`追加とあわせて)。

- `verify_checkout_authorization(store_id, requester_user_id, store) -> AuthorizationResult`:
  9節手順3の認可チェック本体。`AuthorizationResult(authorized, denied_reason)`を返し、
  `denied_reason`は`AUTHORIZATION_DENIED_OWNER_NOT_SET`/
  `AUTHORIZATION_DENIED_USER_ID_MISMATCH`のいずれか。
- `render_checkout_authorization_error_page(denied_reason, line_return_link) -> str`:
  上記2種の文言+「LINEに戻る」リンクを組み立てる。

テスト16件追加(`verify_checkout_authorization()`5件・
`render_checkout_authorization_error_page()`4件・`get_owner_user_id`/
`set_owner_user_id`7件)、venture全体519件全件パス・schema検証25件パスを確認した。

### 残課題(本節)

- `owner_user_id`自体の書き込み配線(接続テストメッセージ受信時に
  `store.set_owner_user_id()`を呼ぶ処理、owner-notification-channel-design.md参照)は、
  実Firestore接続待ちのため引き続き未着手のまま残る。
- Checkout Session作成エンドポイント本体(9節手順1〜4を結ぶHTTPハンドラ)から
  `verify_checkout_authorization()`/`render_checkout_authorization_error_page()`を
  実際に呼び出す配線も、エンドポイント本体自体が未実装(残課題参照)のため次回以降。
- エラーページの実際のHTML/デザインは、`success_url`ページ(4節)と同様、LP実装
  (オーナー承認待ち)とあわせて行う。

## 11. LIFF起動リンクの組み立て(store_idクエリパラメータ埋め込み、フェーズ続き172・新規)

store-id-resolution-and-owner-identity-design.md「残課題」に最後まで残っていた、
「LIFF起動リンクへの`store_id`クエリパラメータ埋め込みの具体的な実装」に対応する。

### 背景

9節手順1は「クエリパラメータから`store_id`受領」を前提にしているが、実際に
オーナーへLIFF起動リンクを届けている送信元(`cloud_function_send_trial_end_reports.py`の
`send_trial_end_reports()`)は、全店舗共通の固定プレースホルダ文字列
(`PAYMENT_LIFF_URL_PLACEHOLDER = "{有料プランへ進むLIFFアプリ URL}"`)を送っているだけで、
`store_id`を一切埋め込んでいなかった。これでは実LIFFアプリ登録後もどの店舗の決済か
特定できず、9節手順1が成立しない配線漏れだった。

### 採用方針

`prototype/checkout_session.py`に`build_liff_checkout_link(store_id, *, liff_id=
DEFAULT_LIFF_ID) -> str`を新設した。`https://liff.line.me/{liff_id}?store_id={store_id}`
形式で、`store_id`はURLエンコードして埋め込む。改ざん検知(署名付与等)は行わない。
store-id-resolution-and-owner-identity-design.md「残課題」の結論どおり、`store_id`が
改ざん・誤入力されても最終的には`verify_checkout_authorization()`(10節、
`owner_user_id`との一致確認)が防波堤になるため、現時点では過剰な防御と判断した
(3節「残課題」に既にあった判断を踏襲)。

`cloud_function_send_trial_end_reports.py`の`send_trial_end_reports()`を、固定の
`payment_page_url`引数から`liff_id`引数(既定値`DEFAULT_LIFF_ID`)へ差し替え、候補
(`TrialEndReportCandidate`)ごとに`build_liff_checkout_link(candidate.store_id,
liff_id=liff_id)`で個別のリンクを組み立ててから`render_trial_end_report_message()`へ
渡すよう変更した。オンボーディング完了メッセージ側(`cloud_function_send_onboarding_
completion_message.py`)は決済導線への言及がないため対象外。

テスト10件追加(`build_liff_checkout_link()`単体6件・`send_trial_end_reports()`の
store_id別リンク検証4件)、venture全体529件全件パス・schema検証25件パスを確認した。

### 残課題(本節)

- 実LIFF ID自体はLIFFアプリ実登録(オーナー承認待ち)後に`DEFAULT_LIFF_ID`
  プレースホルダから差し替える。
- オンボーディング完了メッセージ以外にも今後決済導線への言及を追加するメッセージが
  増えた場合、同じ`build_liff_checkout_link()`を再利用する。

## 12. Checkout Session作成エンドポイント本体の実装(フェーズ続き174・新規)

10節「残課題」・11節「残課題」に残っていた、9節手順1〜4・10節の認可チェックをすべて
結ぶCheckout Session作成エンドポイント本体を実装する。course-set-pasha/
checkout-session-cloud-function-entry-point-design.md(フェーズ115)と同じ「依存注入で
テスト可能な本体+実`functions_framework`リクエストを扱う薄い`main(request)`」という
構成を踏襲する。

### 処理順序

`prototype/checkout_session.py`に`create_checkout_session(store_id,
authorization_header, *, verify_id_token, store, line_return_link, success_url=...,
cancel_url=...) -> CreateCheckoutSessionResult`を新設し、9節手順1〜4を実装した。

1. `store_id`(design 11節のLIFF起動リンクが埋め込むクエリパラメータ)が空文字列・Noneの
   場合は400(design 9節手順1、認可チェックより前段のガード。`store_id`自体が読み取れなければ
   `owner_user_id`の参照先も定まらないため)。
2. `authorization_header`が`Bearer `形式でない場合は401(design 9節手順2の前段、
   course-set-pasha版と同じガード)。
3. `verify_id_token(id_token)`で個人`user_id`を取得する(design 9節手順2)。`None`が返れば
   401。`NotImplementedError`はここでは捕捉せず`main()`側に伝播させる(course-set-pasha版と
   同じ「未実装は501で明示する」方針)。
4. `verify_checkout_authorization(store_id, requester_user_id, store)`(design 9節手順3・
   10節)で不一致なら403+`render_checkout_authorization_error_page()`のエラーページを返し、
   Checkout Sessionは作成しない。
5. 認可を通過した場合のみ`store.get_stripe_customer_id(store_id)`(design 9節手順3、
   `store_id`をキーとする想定に読み替え済み)で既存Stripe顧客を確認し、design 3節・5節の
   `build_checkout_session_params()`で200を返す。

`CreateCheckoutSessionResult`はcourse-set-pasha版の`status_code`必須構成に、認可チェック
不一致時専用の`error_page`(design 10節のWeb静的ページ文言)を追加した形とした。

### プレースホルダの追加

design 4節で「Basic IDは公式アカウント開設(オーナー承認待ち)後に確定するため、実装では
プレースホルダ定数として切り出す」としていた方針を、`DEFAULT_LINE_BASIC_ID =
"LINE_BASIC_ID_PLACEHOLDER"`として実装した(design 11節の`DEFAULT_LIFF_ID`と対称)。

### `get_checkout_runtime_dependencies()`・`main(request)`

course-set-pasha版と対称の構成。`store`(`InMemoryStoreProfileStore()`、実運用では
Cloud Function A/B・Stripe Webhook側と同一Firestoreの`stores`コレクションを共有する想定だが
本プロセスでは別インスタンスのため呼び出しをまたいだ引き継ぎは無い、実Firestore接続後に
解消される既知の限界)・`verify_id_token`(`_verify_id_token_not_implemented`)・
`line_return_link`(`build_line_return_link(DEFAULT_LINE_BASIC_ID)`)を組み立てる。
`main(request)`は`request.args.get("store_id")`・`request.headers.get("Authorization")`を
取り出して`create_checkout_session()`に委譲し、`NotImplementedError`捕捉時は501を返す。

テスト15件追加(`create_checkout_session()`10件・`get_checkout_runtime_dependencies()`1件・
`main()`4件)、venture全体553件全件パス・schema検証25件パスを確認した。

### 残課題(本節)

- 実LIFFアプリ登録後、`verify_id_token`実装本体(LINE Platform APIの
  `/oauth2/v2.1/verify`相当への実HTTPリクエスト)への差し替えが必要(引き続きオーナー
  承認待ち)。それまでの間`main(request)`が501を返すことで「未実装」であることを明示できる
  状態にした。
- `checkout_session_params`を実際にStripe Checkout Session作成APIへ渡し、返り値のURLを
  レスポンスとして返す処理(実Stripeアカウント接続後の課題)は未着手のまま残る
  (course-set-pasha版「残課題」と同種)。
- 実Cloud Functions環境で`store`をFirestore版に差し替える配線、および`owner_user_id`
  自体の書き込み配線(10節「残課題」参照)は実Firestore接続確定後に行う。

## 残課題

- LIFFアプリのLINE Developersコンソールでの実登録、LINE公式アカウントの開設(Basic ID
  確定)はオーナー承認待ち(pending-approval.mdに記録する)。
- `resolve_existing_stripe_customer_id()`・`handle_checkout_session_completed()`を実際に
  Stripe Webhook受信エンドポイント本体に配線する処理(実HTTPハンドラ・実Stripe API呼び出し)は
  未実装。実アカウント接続後に着手する。うち署名検証部分(`verify_stripe_signature()`)は
  実アカウント接続前でも机上実装・テスト可能だったため、stripe-webhook-signature-
  verification-design.md(フェーズ続き158)として先行着手済み。エンドポイント本体(署名
  検証〜イベント種別ディスパッチ〜各ハンドラ呼び出しを結ぶ層)は引き続き未着手のまま残る。
  Checkout Session作成エンドポイント側の本体配線(9節手順1〜4・10節を結ぶ層)は12節
  (フェーズ続き174)で実装済み。
- IDトークン検証の実装(LINE Platform APIの`/oauth2/v2.1/verify`相当)は実LIFF登録後に着手
  (12節`_verify_id_token_not_implemented`プレースホルダを差し替える)。
- Checkout Session作成APIへの実HTTPリクエスト送信(`build_checkout_session_params()`が
  組み立てたdictを実際に`stripe.checkout.Session.create(**params)`へ渡す処理)は実Stripe
  アカウント接続後の課題として残る(12節「残課題」参照)。
- `success_url`ページの実際のHTML/デザインは、LP実装(オーナー承認待ち)とあわせて行う。
- オンボーディング完了メッセージの発火判定・1回のみ発火の制御の本体配線は、
  owner-settings-wireframe.mdのフォーム保存処理の実装着手時にあわせて設計する
  (onboarding-completion-message-design.md参照)。
