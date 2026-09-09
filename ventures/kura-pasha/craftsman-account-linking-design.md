# LINE user_id紐付け・複数職人プラン「契約者本人」判定設計(フェーズ25)

作成日: 2026-09-07(フェーズ25)

## 背景・対応する残課題

subscription-cancellation-flow-design.md(フェーズ23)「未確定事項」で、複数職人プランに
おける「誰が契約者本人か」を判定する仕組み自体が本venture未着手であり、
course-set-pasha/line-user-id-linking-design.md相当を参照する必要がある、と指摘されていた。
本ファイルはこの課題に対応する。

着手にあたり、本venture固有の前提を確認したところ、そもそも単一契約(ライト/
スタンダードプラン)についても、course-set-pasha・aircon-pashaが既に持つような
「LINEのuser_idと契約(Stripe顧客)をどう結び付けるか」という基本設計自体が
本venture未着手のまま残っていたことが判明した(mvp-flow-draft.md「残課題」にも
本論点の記載はない)。そのため本ファイルはまず単一契約向けの基本設計を行い、その上に
複数職人プラン固有の「契約者本人」判定を積み上げる構成とする。

## 1. 前提: どちらのオンボーディング順序を踏襲するか

course-set-pasha(LINE友だち追加が先→フォームでコード入力)と、aircon-pasha(申込フォームが
先→LINEでコード送信)の2方式が既存venture内に存在する。本ventureはaircon-pashaのような
申込フォーム主導のオンボーディング設計(onboarding-guide.md相当)がまだ存在しないため、
course-set-pashaの「LINE友だち追加時にコードを発行する」方式をそのまま踏襲する
(採用する積極的な理由:本venture固有の受注特性〈低頻度・高単価〉ではフォーム入力より
LINE上で完結する導線の方が職人にとって手数が少ないと考えられるため)。

## 2. 単一契約(ライト/スタンダードプラン)の基本設計

course-set-pasha/line-user-id-linking-design.mdの連携コード方式をほぼそのまま踏襲する。

- LINE公式アカウントを友だち追加(`follow`イベント)した時点で、Cloud Function側が
  連携コード(6文字、視認性の低い`0`/`O`・`1`/`I`/`L`を除いた31種のアルファベット、
  course-set-pashaと同じコード仕様)を発行し、`pending_links/{code}`に
  `{user_id, issued_at}`を保存したうえでウェルカムメッセージにコードを埋め込んで送る。
- 本venture固有の差分: 本ventureには「申込フォーム」自体がまだ存在しないため、
  connect先はフォームではなく**新規契約(Stripe Checkout)フロー**そのものとする。
  友だち追加後、LINEトーク上で職人がコードを入力(またはウェルカムメッセージ内の
  「今すぐ始める」導線をタップ)すると、Cloud Function側がコードを解決して
  `user_id`を確定させたうえで、下記3節の「工房(workshop)」を新規作成する。
- 解決後は course-set-pasha 同様、有効期限24時間・使い切り一回限りとする。

## 3. 「工房(workshop)」という単位の導入

複数職人プランは「複数の職人が共同で1契約を利用する」形態であり、これまでの
`user_profile/{user_id}`(1人=1契約が前提)だけでは表現できない。course-set-pasha・
aircon-pashaにはこの概念自体が存在しない(いずれも1事業者=1契約のみ)ため、本venture
固有の新設計として「工房(workshop)」という契約単位を導入する。

- `craftsman_workshop/{workshop_id}`: `contractor_user_id`(契約者本人のuser_id)・
  `member_user_ids`(配列、contractor自身を含む全メンバーのuser_id)・`plan_id`
  (ライト/スタンダード/複数職人)・`stripe_customer_id`・`created_at`。
- `user_profile/{user_id}`: 既存想定フィールドに加え`workshop_id`を追加し、
  どの工房に所属するかを1対1で参照する(1人のuser_idが複数workshopへ同時所属する
  ケースはMVPでは考慮しない=1人1工房のみとする、簡素化のための仮決め)。
- **単一契約(ライト/スタンダード)も同じ`craftsman_workshop`構造に統一する**:
  友だち追加→コード解決の時点で、その職人を`contractor_user_id`かつ唯一の
  `member_user_ids`とする1人だけのworkshopを自動作成する。これにより「単一契約→
  後日、複数職人プランへアップグレードして仲間を招待する」という主要導線(小規模
  工房が事業拡大する自然な流れ)を、workshop構造の作り直しなしにシームレスに
  扱える(2節で発行される連携コードは「新規workshop作成用コード」という位置づけに
  一本化される)。

## 4. 契約者(contractor)の定義と判定方法(本題への回答)

- **契約者本人 = そのworkshopを最初に作成したuser_id**、すなわち2節の連携コードを
  解決してworkshopを新規作成した時点の`user_id`を`contractor_user_id`として
  workshop作成時に確定し、以後変更不可(MVPでは契約者の譲渡機能を持たない。
  必要になった場合は次の課題とする)。
- 契約(Stripe Checkout Session)作成時は、`client_reference_id`に
  `user_id`ではなく`workshop_id`を設定する(aircon-pasha/user-account-linking-design.md
  4節の「フォーム起点なので既知のuser_idをそのまま使える」パターンを参考にしつつ、
  本venture固有の複数人契約という性質上、紐付け先はuser_idではなくworkshop_idに
  なる点が差分)。`checkout.session.completed`Webhook受信時、`workshop_id`から
  対象workshopを特定し`stripe_customer_id`・`plan_id`を書き込む。
- これにより、subscription-cancellation-flow-design.mdが仮決めしていた
  「契約(Stripeサブスクリプション)の名義人となった申込者本人のみが解約・
  ダウングレード操作を行える」という権限モデルは、`contractor_user_id`と
  一致するかどうかで機械的に判定できるようになった(未確定事項の解消)。

## 5. 追加職人の招待(複数職人プランへのメンバー追加)

- 複数職人プランのworkshopに限り、`contractor_user_id`と一致する`user_id`から
  LINEトークで「職人を追加したい」等の意図が検知された場合、招待コード
  (`pending_workshop_invites/{code}`、フィールド`{workshop_id, issued_at}`、
  コード仕様・有効期限24時間・使い切り一回限りは2節の連携コードと同一方式)を発行し、
  契約者本人に転送用の文面として渡す(招待される側が直接受け取るのではなく、
  契約者が自分の裁量で追加したい職人へ転送する設計とし、無関係な第三者が誤って
  参加できないようにする)。
- 追加される職人がまだLINE友だち追加をしていない状態を想定し、招待コードは
  2節の「新規workshop作成用コード」とは別の名前空間(`pending_workshop_invites`)で
  管理する。招待コードを解決する際は、新規workshopを作らずに既存の
  `workshop_id`へ`member_user_ids`を追記し、`user_profile/{user_id}.workshop_id`を
  その既存workshopへ設定する処理に分岐させる(2節のコード解決ロジックに
  「新規作成 or 既存workshopへの追加」の分岐を1つ追加する形になる)。
- ライト/スタンダードプラン(1人だけのworkshop)では、この招待コード発行意図は
  「複数職人プランへのアップグレードが必要です」という案内に置き換える
  (誤って1人用プランのまま招待コードだけ発行してしまう事態を防ぐ)。

## 6. 非契約者からの解約意図表明の扱い(既存仮決めとの整合確認)

subscription-cancellation-flow-design.mdの仮決め(契約者以外からの解約意図表明は
厳守事項7aの検知対象とせず「契約者様にご確認ください」と案内する)は、本設計の
`contractor_user_id`判定と矛盾なくそのまま実装できることを確認した。判定ロジックは
「メッセージ送信元`user_id`の`user_profile.workshop_id`を引き、その
`workshop.contractor_user_id`と送信元`user_id`が一致するか」の1行で表現できる。

## データ構造まとめ

| コレクション | キー | フィールド | 用途 |
|---|---|---|---|
| `pending_links/{code}` | 連携コード | `user_id`・`issued_at` | 友だち追加〜新規workshop作成までの一時トークン(24時間失効) |
| `pending_workshop_invites/{code}` | 招待コード | `workshop_id`・`issued_at` | 既存workshopへの職人追加までの一時トークン(24時間失効) |
| `craftsman_workshop/{workshop_id}` | workshop_id | `contractor_user_id`・`member_user_ids`・`plan_id`・`stripe_customer_id`・`created_at` | 契約単位。単一契約もmember 1名のworkshopとして統一的に扱う |
| `user_profile/{user_id}` | LINE user_id | `workshop_id`(既存想定フィールドに追加) | 所属workshopへの参照(1人1工房のみ) |
| `usage_counter/{workshop_id}` | workshop_id | `month`・`count` | 月間生成回数の積算。本設計により、複数職人が共通の1つのカウンタを共有する前提が明確になった(キーをuser_idからworkshop_idへ読み替える必要があることが判明。実装未着手のため次の課題) |

## 未検証・残課題

- `usage_counter`のキーがこれまで暗黙にuser_id前提だった可能性があり(pricing-plan.md・
  content-generation-time-estimate.mdはキー設計まで踏み込んでいない)、本設計により
  workshop_idキーへ読み替える必要があることが判明した。schema/output.schema.json・
  validate_test_cases.pyへの反映は未着手で次の課題とする。
- 複数職人プランからライト/スタンダードプランへのダウングレード時の「余剰メンバーの
  扱い」(subscription-cancellation-flow-design.md 108行目で既に指摘済みの残課題)は、
  本設計のworkshop構造を前提にすると「`member_user_ids`が2名以上のままダウングレード
  された場合にどうするか(超過メンバーを強制的に外すか、次回請求まで猶予するか)」という
  形で論点が具体化した。本ファイルでは扱わず次の課題とする。
- 契約者(contractor)の譲渡機能(契約者本人が引退・交代する場合の引き継ぎ)はMVP範囲外とし、
  次の課題とする。
- 実際のLINE公式アカウント接続・Stripe接続・招待コード発行の実装(プロトタイプコード)は
  未着手。実接続はオーナー承認待ちの範囲(pending-approval.md参照)。

## 7. 追記(フェーズ66): workshop新規作成時の暫定plan_id

usage-counter-workshop-key-design.md(フェーズ26)実装の`check_and_increment_usage()`は
トライアル中の生成リクエストでも`workshop_store.get_plan_id(workshop_id)`を必ず参照する
(`process_generation_request()`内、トライアル終了前の分岐でも到達する)ため、2節の
「友だち追加→コード解決の時点でworkshopを自動作成する」処理はplan_id未設定のままでは
生涯最初の無料生成リクエストがKeyErrorで失敗してしまう既存の抜け穴だったことが判明した。

一方、checkout-initiation-flow-design.md(フェーズ38〜)の通りplan_id(ライト/スタンダード/
複数職人)は本来Stripe Checkout開始時に職人自身が選ぶものであり、友だち追加直後の
コード解決時点ではまだ確定していない。

暫定対応として、workshop作成時のplan_idはpricing-plan.mdの最安プラン`"light"`
(月間生成3回)で仮設定し、Checkout完了(`checkout.session.completed`受信、design 4節)時に
`set_plan()`相当の書き込みで実際に選ばれたプランへ上書きする、という2段階の運用とする
(`set_plan()`書き込み処理自体は本venture未実装のため次の課題)。トライアル中(生涯最初の
1回)に限り、この仮のplan_id上限(月3回)が実質的な制約にならないことは
trial-end-condition-design.md 3節の「生涯最初の1回」判定(回数条件ではなく専用フラグで
判定)により保証されている。

## workshop_linking.py(フェーズ66)の実装状況

上記2節の連携コード発行(`issue_linking_code_on_follow`)・解決(`resolve_linking_code`)、
3節のworkshop新規作成(`create_workshop_from_linking_code`)を実行可能なコードに落とし込んだ
(`prototype/workshop_linking.py`)。course-set-pasha/prototype/user_id_linking.pyの
コード発行・パージロジックをほぼそのまま踏襲しつつ、解決先をフォーム送信ではなく本venture
固有のworkshop新規作成に差し替えた。5節の招待コード(`pending_workshop_invites`)・4節の
Stripe Checkout連携(`client_reference_id`=workshop_id)は本ファイル未着手のため引き続き
次の課題として残す。

最終更新: 2026-09-09(フェーズ66) UTC
