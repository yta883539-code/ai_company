# Checkout Session プラン選択・購入プランの記録設計

作成日: 2026-09-03(フェーズ続き181)

## 0. 発見された経緯(残課題棚卸し)

フェーズ続き180(monthly-booking-limit-notification-design.md)で、月間予約件数上限
(pricing-plan.mdのスタータープラン50件/スタンダードプラン150件/プロプラン300件)への
接近をオーナーへ知らせる仕組みを実装した際、「`store_profile_store.py`に契約プランを
保持するフィールドが無く`monthly_booking_limit`を実際に接続する配線が無い」ことを
次回以降の課題として残した。

これはcourse-set-pashaがフェーズ152(checkout-session-plan-selection-design.md)で
発見・解消した「Checkout Sessionが購入プランを一切記録していなかった」ギャップと同種
であることを確認した。line-reservation-aiでも同様に、以下の未設計・未接続の
ギャップが存在していた。

- `checkout-initiation-flow-design.md`(フェーズ続き139)・
  design 9節「認可チェック・LIFF起動リンク」(フェーズ続き174)はいずれもプラン選択に
  ついて一切触れておらず、`prototype/checkout_session.py`の
  `build_checkout_session_params()`はどのStripe Price(=どのプラン)を購入するかを表す
  `line_items`を含めていなかった。
- `store_profile_store.handle_checkout_session_completed()`は`client_reference_id`
  (=store_id、本ventureは`user_id`をそのまま`store_id`として扱う)と`customer`
  (stripe_customer_id)の紐付けのみを行い、購入されたプランをどこにも記録していなかった。
- `prototype/engine.py`の`ConversationFlowStateMachine`は`monthly_booking_limit`引数
  (省略時None=機能無効)を既に持つが(フェーズ続き180)、この引数へ渡すべき「その店舗が
  実際に契約しているプラン」を店舗プロフィール側から読み出す経路自体が存在しなかった。

本ドキュメントはこのギャップを解消するための設計と、承認不要な範囲(パラメータ組み立て・
記録ロジック)の実装をあわせて記録する。course-set-pashaのcheckout-session-plan-
selection-design.md(フェーズ152)と同じ方針を、本venture固有の事情
(`store_id`をキーとする点、購入プランと月間予約件数上限を結びつける点)に合わせて
翻案したもの。

## 1. 方針

1. LIFFフロントエンド側のプラン選択UI(未実装、実LIFF登録後の課題)が、Checkout Session
   作成リクエストに選択プラン名(`"スタータープラン"`/`"スタンダードプラン"`/
   `"プロプラン"`のいずれか、`store_profile_store.PLAN_MONTHLY_BOOKING_LIMITS`のキーと
   同一集合)をクエリパラメータ`plan`として付与する想定とする(design 11節の
   `build_liff_checkout_link()`が埋め込む`store_id`と同様、クエリパラメータ方式に揃える)。
2. `checkout_session.create_checkout_session()`は`verify_id_token`成功後・
   `verify_checkout_authorization()`(design 9節手順3・10節の店舗オーナー本人確認)より前に
   `plan`を検証し、未知の値は`status_code=400`・`error="invalid_plan"`を返す(未認証
   ユーザーにプラン名の有効集合を推測させないよう認証前には検証しない、という
   course-set-pasha版の方針を踏襲。本venture固有の認可チェックより前に置くのは、
   店舗オーナーが誤ったプラン名を渡した場合に無関係な403エラーページ〈認可チェック不一致〉
   ではなく素直な400を返すため)。
3. `build_checkout_session_params()`は`plan`が渡された場合、選択プランに対応するStripe
   Price ID(`PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER`、実Price ID確定まではプレースホルダ)を
   1件含む`line_items`と、`metadata: {"plan": plan}`をパラメータに追加する。`metadata`は
   Stripeの仕様上Checkout Sessionオブジェクトにそのまま保持され、後続の
   `checkout.session.completed`イベントのセッションオブジェクトにも含まれるため、
   `line_items`のexpand等の追加API呼び出しなしに購入プランを特定できる。
4. `store_profile_store.handle_checkout_session_completed()`は
   `data.object.metadata.plan`を取り出し、`PLAN_MONTHLY_BOOKING_LIMITS`にある既知の値のみ
   `store.set_plan(store_id, plan)`で書き込む(未知の値・`metadata`欠落は書き込まない、
   安全側)。
5. `ConversationFlowStateMachine`構築時に`store.get_plan(store_id)`から
   `PLAN_MONTHLY_BOOKING_LIMITS[plan]`を引いて`monthly_booking_limit`引数へ渡す配線
   (`prototype/cloud_function_process_event.py`側)は、本フェーズでは着手しない。
   course-set-pashaのフェーズ152と同様、実Stripe接続後にどのタイミングで
   `ConversationFlowStateMachine`を構築するか(会話イベントごとに毎回構築するか、
   店舗単位でキャッシュするか)が未確定なため、店舗プロフィール側への記録・読み出し
   インターフェースの整備までを本フェーズのスコープとし、呼び出し元の配線は次回以降の
   課題として残す。

## 2. 実装した変更

- `prototype/store_profile_store.py`: `PLAN_MONTHLY_BOOKING_LIMITS`(pricing-plan.mdの
  3プラン名→月間予約件数上限のマッピング、本venture内でPLAN定数を一元管理する唯一の
  場所)を新設。`StoreProfileStoreProtocol`に`get_plan`/`set_plan`を追加、
  `InMemoryStoreProfileStore`に`_plans`辞書ベースの実装を追加(`set_plan`は未知のプラン名を
  `ValueError`で拒否)。`handle_checkout_session_completed()`に`metadata.plan`からの
  読み取り・`store.set_plan()`書き込みを追加、`CheckoutSessionLinkResult`に
  `plan_written: bool`フィールドを追加。
- `prototype/checkout_session.py`: `PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER`(3プラン分の
  プレースホルダPrice ID、`store_profile_store.PLAN_MONTHLY_BOOKING_LIMITS`をインポート
  してキー集合を単一の正として同期)を新設。`build_checkout_session_params()`に`plan`引数
  (省略時は従来通り`line_items`・`metadata`を含めない)、`create_checkout_session()`に
  `plan`引数と400エラー分岐(`verify_id_token`成功後・認可チェック前)、`main()`に
  `request.args.get("plan")`からの読み取り配線を追加。

テスト: `test_store_profile_store.py`(`PlanTest`5件・
`HandleCheckoutSessionCompletedPlanTest`4件の計9件)・`test_checkout_session.py`
(`BuildCheckoutSessionParamsTest`3件・`CreateCheckoutSessionTest`2件・
`MainEntryPointTest`1件の計6件)の計15件を追加。venture全体623件全件
(`python3 -m unittest discover -s prototype -p "test_*.py"`)パス・schema検証25件
(`python3 schema/validate_test_cases.py`)パスを確認済み(詳細はREADME.mdフェーズ続き181
参照)。

## 3. 残課題

- `PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER`の実Price ID(Stripeダッシュボードでの商品・価格
  作成)は実Stripeアカウント接続(オーナー承認待ち、pending-approval.md参照)後の課題として
  残る。
- LIFFフロントエンド側のプラン選択UI自体(3プランのいずれかを選ばせるLIFF画面)は未着手。
  実LIFFアプリ登録(オーナー承認待ち)後、UIから`plan`クエリパラメータを付与する実装と
  あわせて着手する。
- (解消済み 2026-09-04・フェーズ続き187: `ConversationFlowStateMachine`構築時に
  `store.get_plan(store_id)`から`monthly_booking_limit`引数への配線(1節手順5参照)のうち、
  値を求める部分(`resolve_monthly_booking_limit()`、フェーズ続き182)に続き、実際に
  `ConversationFlowStateMachine`のコンストラクタへこの値を渡す構築ヘルパー
  `build_conversation_flow_state_machine_for_store()`を`prototype/store_profile_store.py`に
  新設した(conversation-flow-construction-design.md参照)。この関数を
  `cloud_function_process_event.py`側のどのタイミング(会話イベントごとに毎回構築するか、
  店舗単位でキャッシュするか)から呼ぶかという配線自体は、会話状態の永続化・復元方式が
  実Firestore接続後に確定するまで引き続き次回以降の課題として残る。プラン未記録
  (トライアル中で未購入)の店舗では引き続き`monthly_booking_limit=None`(機能無効、
  フェーズ続き180の既定動作)のまま構築される。テスト7件追加、venture全体669件全件パス・
  schema検証25件パスを確認した)。

## 4. `ConversationFlowStateMachine`構築時の配線ヘルパー(フェーズ続き182)

3節で残していた「`ConversationFlowStateMachine`構築時に`store.get_plan(store_id)`から
`monthly_booking_limit`引数へ渡す値を求める」部分について、`prototype/store_profile_store.py`に
`resolve_monthly_booking_limit(store_id, store) -> Optional[int]`を新設した。
`store.get_plan(store_id)`がNone(トライアル中で未購入)ならNoneをそのまま返し、既知のプラン名
なら`PLAN_MONTHLY_BOOKING_LIMITS[plan]`を返す(`store.set_plan()`が未知のプラン名を
`ValueError`で拒否済みのため、`.get()`が未知キーに当たることは想定していないが防御的に使う)。
同モジュールの`resolve_existing_stripe_customer_id()`/`make_resolve_store_id_by_customer()`と
同じ「店舗プロフィールストアと呼び出し元(engine.py)の結線点を切り出す」位置づけの薄い
ヘルパー関数であり、`ConversationFlowStateMachine`側(engine.py)には変更を加えていない。

呼び出し元(実際に`ConversationFlowStateMachine(monthly_booking_limit=...)`を構築している
箇所)自体は、店舗の会話状態機械をどのタイミング・単位で構築するかという設計(1節手順5・
3節参照)が実Firestore接続後まで確定しないため、本ヘルパーをそこから呼ぶ配線は
引き続き次回以降の課題として残る(store-id-resolution-and-owner-identity-design.md
「残課題」に残っている`ConversationEventProcessor`組み立てファクトリ関数〈実Firestore接続待ち〉
と同じ制約)。

テスト: `test_store_profile_store.py`に`ResolveMonthlyBookingLimitTest`6件を追加
(プラン未設定時None・3プランそれぞれの上限値・店舗間の独立性・空store_id時の
`ValueError`)。venture全体629件全件
(`python3 -m unittest discover -s prototype -p "test_*.py"`)パス・schema検証25件
(`python3 schema/validate_test_cases.py`)パスを確認済み(詳細はREADME.mdフェーズ続き182
参照)。
- プラン変更(アップグレード・ダウングレード)時に`stores/{storeId}.plan`を更新する経路は
  未設計のまま残る(現状は`checkout.session.completed`、すなわち新規契約時のみ書き込む
  設計。course-set-pashaのcheckout-session-plan-selection-design.md「残課題」と同じ
  制約)。Stripeの`customer.subscription.updated`イベントからの`plan`更新は次回以降の
  課題として残す。
- 実LLM・実Stripe接続後、実際の`checkout.session.completed`イベントでの動作検証
  (本ドキュメントの設計はあくまで机上検証)は、実接続確定後の検証課題として残る。
