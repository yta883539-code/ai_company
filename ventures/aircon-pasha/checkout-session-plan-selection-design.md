# Checkout Session プラン選択・購入プランの記録設計

作成日: 2026-09-03(フェーズ179)

## 0. 発見された経緯(残課題棚卸し)

course-set-pasha(フェーズ152)・line-reservation-ai(フェーズ180・181)がそれぞれ
「Checkout Sessionが購入プランを一切記録していなかった」ギャップを解消した際の横展開検討
として本ventureの`prototype/checkout_session.py`を確認したところ、それらの2venture以上に
根本的なギャップが見つかった。

`build_checkout_session_params()`は`mode: "subscription"`のCheckout Sessionパラメータを
組み立てていたが、`line_items`(どのStripe Priceを購入するか)を一切含めていなかった。
Stripeの仕様上、`mode="subscription"`のCheckout Sessionは最低1件の`line_items`なしでは
作成できない(実際にAPI呼び出しを行えば`invalid_request_error`になる)。つまり本venture
唯一の決済導線である`process_postback_event()`の`action=start_checkout`分岐
(`cloud_function_webhook.py`)は、実Stripe接続後にそのまま動かすと必ず失敗する状態のまま
放置されていた。

pricing-plan.mdは既に3プラン(スモール/スタンダード/繁忙期対応)を定義しており、
`subscription_plan_sync.py`(フェーズ161)は`customer.subscription.*`イベントの
`items.data[0].price.lookup_key`から`current_plan_id`を同期する仕組み(`LOOKUP_KEY_TO_PLAN_ID`)
を既に備えていた。つまり「購入後にどのプランかを追跡する」仕組みは既にあったが、
「そもそもどのプランを購入させるか」を指定する`line_items`の組み立てが欠落していた。

## 1. 方針

1. 本ventureの決済導線はLIFFのプラン選択UIではなく、LINEのpostbackボタン1個
   (`START_CHECKOUT_POSTBACK_DATA = "action=start_checkout"`)のみである
   (checkout-initiation-flow-design.md)。ボタンを複数プラン分に分割する設計変更は
   スコープが大きいため本フェーズでは見送り、次回以降の課題として残す(3節参照)。
2. 単一ボタンである以上、全ユーザーを既定の1プランで開始させる必要がある。
   pricing-plan.mdの「想定顧客像」のうちmarket-research.mdの標準的な利用量
   (年間720〜1,200台、月60〜100件)に最も近い「スタンダードプラン」を既定値
   (`DEFAULT_CHECKOUT_PLAN`)とした。
3. 開始後にプランを変更したい業者は、既存のStripe Customer Portal導線
   (`action=update_payment_method`ポストバック→`portal_session.py`、
   portal-session-provider-design.md、フェーズ178で実装済み)から自身でプラン変更できる
   想定とする(Stripe Customer Portalは商品・価格の設定でプラン変更を許可できるため、
   追加のアプリ側実装は不要)。プラン変更後は`subscription_plan_sync.py`の
   `customer.subscription.updated`ハンドラが`current_plan_id`を自動的に追従させる
   (既存の仕組みがそのまま機能する)。
4. `build_checkout_session_params()`に`plan`引数(既定値`DEFAULT_CHECKOUT_PLAN`)を追加し、
   `PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER`(3プラン名→Stripe Price IDのプレースホルダ辞書、
   実Price ID確定まではプレースホルダ文字列)から解決した1件の`line_items`を必ず含める。
   未知の`plan`値は`ValueError`(安全側、想定外の値でCheckout Session作成APIへ到達させない)。
5. `metadata.plan`は付与しない。course-set-pashaは`checkout.session.completed`の
   `metadata.plan`を購入プランの記録手段として使っているが、本ventureは既に
   `subscription_plan_sync.py`がPriceの`lookup_key`から`current_plan_id`を同期する
   (より正確な、Stripe側のサブスクリプション状態そのものを情報源とする)仕組みを持つため、
   同じ情報を二重に持たせる必要はない(3プラン名リテラルを`checkout_session.py`・
   `cloud_function_webhook.py`(`PLAN_MONTHLY_LIMITS`)・`subscription_plan_sync.py`
   (`LOOKUP_KEY_TO_PLAN_ID`)の3箇所で個別に保持する既存の重複パターンへ、4箇所目
   〈metadata経由の記録〉を追加しない判断)。

## 2. 実装した変更

- `prototype/checkout_session.py`: `PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER`
  (3プラン分のプレースホルダPrice ID)・`DEFAULT_CHECKOUT_PLAN`(`"スタンダード"`)を新設。
  `build_checkout_session_params()`に`plan`引数(キーワード専用、既定値
  `DEFAULT_CHECKOUT_PLAN`)を追加し、常に1件の`line_items`を含めるようにした。未知の
  `plan`は`ValueError`。
  - `cloud_function_webhook.py`が既に`checkout_session.py`をインポートしているため
    (`START_CHECKOUT_POSTBACK_DATA`・`build_checkout_session_params`)、循環インポートを
    避けるため`cloud_function_webhook.PLAN_MONTHLY_LIMITS`からのインポートは行わず、
    プラン名リテラルを`checkout_session.py`内に独立して保持した(course-set-pashaとは
    異なりインポート方向が逆であるため、同じ手法を単純に横展開できなかった点)。
- `process_postback_event()`(`cloud_function_webhook.py`)側の呼び出しは変更していない
  (`build_checkout_session_params(user_id, profile.stripe_customer_id)`のまま、既定値の
  `DEFAULT_CHECKOUT_PLAN`がそのまま使われる)。

テスト: `test_checkout_session.py`に5件追加(既定プラン適用・明示的プラン選択2種・未知
プランでの`ValueError`・既存顧客再利用時も`line_items`が含まれることの確認)。venture全体
411件全件(`python3 -m unittest discover -s prototype -p "test_*.py"`)パス・schema検証9件
(`python3 schema/validate_test_cases.py`)パスを確認済み(詳細はREADME.mdフェーズ179参照)。

## 3. 残課題

- `PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER`の実Price ID(Stripeダッシュボードでの商品・価格
  作成、`subscription_plan_sync.LOOKUP_KEY_TO_PLAN_ID`と対応する`lookup_key`の設定を含む)
  は実Stripeアカウント接続(オーナー承認待ち、pending-approval.md参照)後の課題として残る。
- (解消済み 2026-09-03フェーズ180: トライアル終了通知(Push Message、業者が最初にプランを
  選ぶ主要な入口)のFlex Messageフッターを、`checkout_session.build_start_checkout_postback_data(plan)`
  (`"action=start_checkout&plan=<プラン名>"`)を使った3プラン分のボタンに分割した
  〈`trial_end_scheduler.build_trial_end_notification_flex_message()`〉。
  `process_postback_event()`側は`checkout_session.parse_start_checkout_postback_data()`で
  postbackデータからプラン名を解決し(プラン未指定の`START_CHECKOUT_POSTBACK_DATA`は
  `DEFAULT_CHECKOUT_PLAN`へ後方互換、未知のプラン名は他アクション同様`handled=False`で
  素通り)、`build_checkout_session_params()`へ渡すよう対応した。テスト9件追加
  (`test_checkout_session.py`7件・`test_cloud_function_webhook.py`2件、
  `test_trial_end_scheduler.py`の既存テストは3ボタン確認に更新)、venture全体420件
  全件パス・schema検証9件パスを確認した。
  一方、`QuickReplyButton`(プレーンテキストへのボタン添付、条件A(生成回数到達)・
  一時停止/制限モード通知等で使用)は現状`Optional[QuickReplyButton]`単数のままで、
  これらの経路はなお既定プラン(`DEFAULT_CHECKOUT_PLAN`)据え置き。`QuickReplyButton`を
  複数ボタン対応にする(`ReplyClient.reply()`・`InMemoryReplyClient`・呼び出し元3箇所の
  変更を伴う)設計は次回以降の課題として残す)
- (解消済み 2026-09-03 22:00 UTCフェーズ181: 上記で残っていた`QuickReplyButton`の複数ボタン
  対応に着手した。`ReplyClient.reply()`・`InMemoryReplyClient.reply()`・`_reply_with_retry()`の
  `quick_reply`引数を`Optional[QuickReplyButton]`単数から`Optional[list[QuickReplyButton]]`へ
  変更し、新設の`_build_plan_selection_quick_reply()`(`PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER`の
  3プラン分、`build_start_checkout_postback_data(plan)`でpostback_dataを組み立て、ラベルは
  `build_trial_end_notification_flex_message()`のfooterボタンと表記を揃えた
  `"{plan}プランで始める"`)を条件A(生成回数到達)・生成一時停止の2経路に適用した。
  `process_postback_event()`側は`parse_start_checkout_postback_data()`で従来通り解釈できる
  ため変更不要。決済失敗時の制限モード通知(`UPDATE_PAYMENT_METHOD_POSTBACK_DATA`)は
  プラン選択ではなく支払い方法の更新のCTAのため対象外とし、単一ボタンを要素数1の
  リストとして渡す形のみ変更した。テスト更新のみ(新規テスト追加なし、既存の3テストの
  期待値を単一`QuickReplyButton`から3ボタンのリストへ更新)、venture全体420件全件パス・
  schema検証9件パスを確認した。実Price ID確定は引き続き実Stripeアカウント接続
  (オーナー承認待ち)後の課題として残る。承認不要な設計・実装・テスト更新のみで、
  外部サービスへの公開・アカウント作成・支払い等は今回発生していないため
  pending-approval.mdへの追記なし)
- Stripe Customer Portalの設定でプラン変更(price切り替え)を実際に許可するかどうかの
  ダッシュボード設定確認は、実Stripeアカウント接続後の課題として残る。
- 実Stripe接続後、`build_checkout_session_params()`が組み立てたパラメータで実際に
  Checkout Sessionが作成できることの結合テストは、実接続確定後の検証課題として残る。
