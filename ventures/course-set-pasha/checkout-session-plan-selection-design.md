# Checkout Session プラン選択・購入プランの記録設計

作成日: 2026-09-03(フェーズ152)

## 0. 発見された経緯(残課題棚卸し)

notification-threshold-per-plan-review.md 4節が採用した`PLAN_NOTICE_THRESHOLDS`(「プラン→
閾値」マッピング、フェーズ不明だが`prototype/cloud_function_webhook.py`に実装済み)を
きっかけに、`PLAN_MONTHLY_LIMITS`/`PLAN_OVERAGE_UNIT_PRICE_JPY`/`PLAN_NOTICE_THRESHOLDS`が
どこで実際のユーザーのプラン("ライト"/"スタンダード"/"セッター複数"のいずれか)と
突き合わされているかを追ったところ、以下の未設計・未接続のギャップが見つかった。

- `checkout-initiation-flow-design.md`(フェーズ98)・`checkout-session-endpoint-design.md`
  (フェーズ112)はいずれもプラン選択について一切触れておらず、
  `prototype/checkout_session.py`の`build_checkout_session_params()`はどのStripe Price
  (=どのプラン)を購入するかを表す`line_items`を含めていなかった。
- `stripe_webhook.handle_checkout_session_completed()`は`client_reference_id`(user_id)と
  `customer`(stripe_customer_id)の紐付けのみを行い、購入されたプランをどこにも記録して
  いなかった。
- `cloud_function_webhook.dispatch_webhook_events()`/`process_memo_event()`は`plan`を
  呼び出し元が注入する単一の引数として受け取るのみで、`user_profile`ストア側にプランを
  保持するフィールド自体が存在しなかった。実運用では1回のWebhookリクエスト(`events`配列)に
  複数ユーザーのイベントが混在しうる一方、`plan`はリクエスト全体で一律の値になってしまう
  ため、複数プランが混在する実際の運用では特定ユーザーに誤ったプランの上限・通知閾値・
  従量単価が適用されるおそれがある構造的なギャップだった(line-reservation-aiが
  monthly-booking-limit-notification-design.mdで残した「store_profile_store.pyへの
  プラン保持フィールド追加」と同種の課題)。

本ドキュメントはこのギャップを解消するための設計と、承認不要な範囲(パラメータ組み立て・
記録ロジック・優先順位ロジック)の実装をあわせて記録する。

## 1. 方針

1. LIFFフロントエンド側のプラン選択UI(未実装、実LIFF登録後の課題)が、Checkout Session
   作成リクエストに選択プラン名(`"ライト"`/`"スタンダード"`/`"セッター複数"`のいずれか、
   `cloud_function_webhook.PLAN_MONTHLY_LIMITS`のキーと同一集合)をクエリパラメータ`plan`
   として付与する想定とする。
2. `checkout_session.create_checkout_session()`は認証成功後(`verify_id_token`成功後)に
   `plan`を検証し、未知の値は`status_code=400`・`error="invalid_plan"`を返す(未認証
   ユーザーにプラン名の有効集合を推測させないよう、認証前には検証しない)。
3. `build_checkout_session_params()`は`plan`が渡された場合、選択プランに対応する
   Stripe Price ID(`PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER`、実Price ID確定まではプレース
   ホルダ)を1件含む`line_items`と、`metadata: {"plan": plan}`をパラメータに追加する。
   `metadata`はStripeの仕様上Checkout Sessionオブジェクトにそのまま保持され、後続の
   `checkout.session.completed`イベントのセッションオブジェクトにも含まれるため、
   `line_items`のexpand等の追加API呼び出しなしに購入プランを特定できる
   (`line_items`自体をイベント側で読み取る設計にしなかった理由)。
4. `stripe_webhook.handle_checkout_session_completed()`は`data.object.metadata.plan`を
   取り出し、`PLAN_MONTHLY_LIMITS`にある既知の値のみ`user_profile_store.set_plan(user_id,
   plan)`で書き込む(未知の値・`metadata`欠落は書き込まない、安全側)。
5. `cloud_function_webhook.process_memo_event()`は`profile_store`(新規引数、渡された
   場合のみ)経由で`profile_store.get_plan(user_id)`を呼び、値があれば引数`plan`より
   優先する。未記録(トライアル中で未購入、または`profile_store`未指定)の場合は従来通り
   引数`plan`にフォールバックする(後方互換、`profile_store`を渡さない既存の呼び出し元・
   テストは挙動が変わらない)。

## 2. 実装した変更

- `prototype/application_form_submission_flow.py`: `UserProfileStoreProtocol`に
  `set_plan`/`get_plan`を追加、`InMemoryUserProfileStore`に`_plans`辞書ベースの実装を
  追加(`all_user_ids()`の列挙対象にも追加)。
- `prototype/checkout_session.py`: `PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER`(3プラン分の
  プレースホルダPrice ID、`cloud_function_webhook.PLAN_MONTHLY_LIMITS`をインポートして
  キー集合を単一の正として同期)を新設。`build_checkout_session_params()`に`plan`引数
  (省略時は従来通り`line_items`・`metadata`を含めない)、`create_checkout_session()`に
  `plan`引数と400エラー分岐、`main()`に`request.args.get("plan")`からの読み取り配線
  (`request`に`args`が無い旧来のスタブでも`getattr(request, "args", {})`により
  `AttributeError`にならないフォールバック)を追加。
- `prototype/stripe_webhook.py`: `handle_checkout_session_completed()`に
  `metadata.plan`からの読み取り・`user_profile_store.set_plan()`書き込みを追加、
  `CheckoutSessionLinkResult`に`plan_written: bool`フィールドを追加。
- `prototype/cloud_function_webhook.py`: `process_memo_event()`に`profile_store`引数を
  追加し、`resolved_plan`(profile_store優先・引数plan後方互換フォールバック)による
  上限判定・通知文言生成に変更。`dispatch_webhook_events()`から`process_memo_event()`
  呼び出しへ`profile_store`を配線。

テスト: `test_checkout_session.py`(9件)・`test_stripe_webhook.py`(4件)・
`test_cloud_function_webhook.py`(3件)の計16件を追加。venture全体512件全件
(`python3 -m unittest discover -s prototype -p "test_*.py"`)パス・schema検証9件
(`python3 schema/validate_test_cases.py`)パスを確認済み(詳細はREADME.mdフェーズ152参照)。

## 3. 残課題

- `PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER`の実Price ID(Stripeダッシュボードでの商品・価格
  作成)は実Stripeアカウント接続(オーナー承認待ち、pending-approval.md参照)後の課題として
  残る。
- LIFFフロントエンド側のプラン選択UI自体(3プランのいずれかを選ばせるLIFF画面)は未着手。
  実LIFFアプリ登録(オーナー承認待ち)後、UIから`plan`クエリパラメータを付与する実装と
  あわせて着手する。
- `main(request)`の`plan`読み取りは現状クエリパラメータ(`request.args`)からのみで、
  POSTボディでの受け渡しを想定していない。実際のLIFF実装がどちらの形式でリクエストを
  送るかは、実LIFFアプリ実装時にあわせて確定する。
- (解消済み・フェーズ153/フェーズ続き154: ダウングレード・アップグレード時に
  `user_profile/{user_id}.plan`を更新する経路を`subscription-plan-change-design.md`で
  設計・実装した。`customer.subscription.updated`イベントの`items.data[0].price.id`から
  `STRIPE_PRICE_ID_TO_PLAN_PLACEHOLDER`でプラン名を逆引きし、`dispatch_stripe_event()`が
  `user_profile_store.set_plan()`を書き込む。プラン変更を伴わない更新〈支払い方法変更等〉
  では既存プランとの差分チェックにより無駄な書き込みをスキップする。実Stripe Price ID確定・
  実カスタマーポータル操作でのイベント検証は実Stripe接続後の課題として引き続き残る)
- 実LLM・実Stripe接続後、複数プランのユーザーが実際に混在するWebhookバッチでの
  動作検証(本ドキュメントの設計はあくまで机上検証)は、実接続確定後の検証課題として残る。
