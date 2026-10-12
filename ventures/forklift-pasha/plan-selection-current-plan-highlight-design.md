# プラン選択ページ: 現在のプランに応じたハイライト表示 設計(フェーズ140)

位置づけ: README.mdフェーズ138/139「次回候補」に残っていた、
`web-form-mockup/plan-selection.html`における「現在のプラン・契約状況に応じた
ハイライト表示(アップグレード/ダウングレード動線)」の検討。
usage-and-fleet-overage-notification-design.mdのアップセル通知とは異なり、本設計は
プラン選択ページ自体の表示切り替えのみを対象とする。コード実装は行わず設計のみ。

## 1. 前提: 本ページがまだ静的モックアップであること

`plan-selection.html`はフェーズ138で新設した時点では、daily.html・monthly.html・
settings.html等と同じ方針(JS不使用・バックエンド接続なし)の静的HTMLであり、
「今アクセスしている事業者が誰か」を知らない。そのため本設計はまず、
settings.htmlが採用している認証方式(フェーズ136 `access-url-reissue-http-entry-
point-design.md`で設計した `https://<ドメイン>/f/{accessToken}` 形式のURLから
`access_token_store.get_internal_id_by_access_token()`で`internal_id`を解決する方式)
をプラン選択ページにもそのまま適用することを前提とする。これにより、Webフォーム
バックエンドのルーティング実装確定後は、`main(request)`がアクセスURLから
`internal_id`を解決し、`plan_id_resolution.py`の`FleetOperatorStore.get_plan_id
(internal_id)`で現在のplan_id("light"/"standard"/"fleet"またはNone)を取得できる。

## 2. サーバー側テンプレート変数の設計

静的HTMLをサーバーサイドでレンダリングする際(course-set-pashaのliff-plan-
selection-ui-wireframe.mdと同様、本venture側でも単純な文字列置換テンプレートを
想定)、`main(request)`は以下の1変数のみをテンプレートへ渡す。

- `current_plan_id`: `"light"` / `"standard"` / `"fleet"` / `None`
  (トライアル中・契約情報未確定の場合はNone。trial_management.pyの
  `get_plan_id()`がNoneを返す既存契約と一致させる)

新たなAPI呼び出し・新しいストアのメソッドは不要で、既存の`get_plan_id()`のみで
十分である(差分チェックロジック等は不要、単純な現在値の読み取りのみ)。

## 3. 表示切り替えのルール

- `current_plan_id`が3プランのいずれかと一致するカードに対して:
  - カード全体に`.plan-card--current`クラスを付与し、枠線を`--color-accent`の
    実線2pxに変更する(視覚的な強調。settings.htmlの警告枠と同系色を使い回し、
    新規の色トークンは追加しない)。
  - 申し込みボタンの文言を「このプランで申し込む」から「現在のプラン」に変更し、
    `disabled`のまま維持する(Checkout Session発行用`main(request)`が未着手の
    フェーズ137の制約はそのまま継続するため、ボタンの有効化はしない)。
- `current_plan_id`と一致しない他のプランのカードは、現行どおり
  「このプランで申し込む」(disabled)のまま変更しない。
  アップグレード/ダウングレードの方向(上位/下位プランか)によるボタン文言の
  区別(例:「アップグレードする」)は、Checkout Session発行が未実装の現段階では
  導入しない。導入するとボタン文言と実際の送信先が食い違う期間が生じるため、
  `main(request)`実装後に改めて検討する(本設計のスコープ外として次回候補に残す)。
- `current_plan_id`が`None`の場合(トライアル中等)は、現行の3カードすべてが
  通常表示のまま変化しない(トライアル中はいずれのプランも「現在のプラン」では
  ないため)。

## 4. テスト観点(実装時)

`browser_mockup_checks.js`(フェーズ139で`checkPlanSelection()`を追加済み)とは
別に、本設計を実装する際は以下をテスト観点とする。

- `current_plan_id`が"light"/"standard"/"fleet"それぞれの場合に、対応する1枚の
  カードのみに`.plan-card--current`が付き、他の2枚には付かないこと。
- `current_plan_id`がNoneの場合、いずれのカードにも`.plan-card--current`が
  付かないこと。
- `current_plan_id`に未知の値("fleet"等の既知plan_id以外の文字列)が渡された
  場合は、`plan_id_resolution.KNOWN_PLAN_IDS`に含まれるかを`main(request)`側で
  検証し、含まれない場合はNoneとして扱う(既存のPLAN_ID_TO_STRIPE_PRICE_ID等と
  同様、未知の値を安全側に倒す既存方針を踏襲)。

## 5. 次回候補への影響

本設計はコード変更を伴わないため、フェーズ139までの既存テスト
(`python3 prototype/run_all_tests.py`13ファイル、`python3 schema/
validate_test_cases.py`11件、`node prototype/browser_mockup_checks.js`30件)は
変更なくいずれもパスする想定。承認が必要なアクション(実Stripe接続等)は本設計
段階では発生しない。
