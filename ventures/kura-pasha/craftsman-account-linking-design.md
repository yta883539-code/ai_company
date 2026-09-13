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

## 8. 追記(フェーズ67): Checkout完了時のplan_id上書き配線

7節で残課題としていた`set_plan()`書き込み処理を配線した。course-set-pashaの
checkout-session-plan-selection-design.md(フェーズ152)の`metadata.plan`と同じ方式を採用し、
`checkout_session.build_checkout_session_params()`がCheckout Session作成時に
`metadata: {"plan_id": plan_id}`を設定するようにした(line_itemsのexpand等の追加API呼び出し
不要)。`stripe_webhook.handle_checkout_session_completed()`側では、受信した
`data_object.metadata.plan_id`が`VALID_PLAN_IDS`にある既知の値の場合のみ
`workshop_store.set_plan(workshop_id, plan_id)`で上書きする(未知の値・metadata欠落時は
何も書き込まない安全側の設計、`CheckoutSessionCompletedResult.plan_written`で呼び出し元が
判別可能)。これにより、2節のworkshop自動作成時に暫定設定した最安プラン`"light"`は、
契約者が実際にCheckout Sessionを完了した時点で選択したプランへ確実に上書きされるように
なった。`WorkshopStoreProtocol`にも`set_plan()`を宣言として追加した(実装
`InMemoryWorkshopStore.set_plan()`は既存、Protocol宣言漏れだった)。

新規テスト3件(`test_stripe_webhook.py`)+既存テストへのアサーション1件追加
(`test_checkout_session.py`)、venture全体416件→423件全件・schema検証27件いずれもパスを
確認した。

## 9. 追記(フェーズ68): process_follow_event()の実装

2節の「友だち追加時のコード発行」を実行可能なコードとして`cloud_function_webhook.
process_follow_event()`に落とし込んだ。`workshop_linking.issue_linking_code_on_follow()`を
呼び出してコードを発行し、`format_follow_welcome_message()`で組み立てたウェルカム
メッセージ(コードを埋め込むのみ、本ventureは申込フォームを持たないためURL差し込みは
行わない)を返信する。`dispatch_webhook_events()`側にも`"follow"`種別の振り分けを追加した
(`reply_client`・`linking_store`双方が接続済みの場合のみ処理し、未接続時は`unfollow`/
`postback`と同様`ignored_types`に記録して素通りする安全側フォールバック)。

2節で想定していた「職人がコードをトーク上に送り返すと解決される」部分(message event側で
コード形式のテキストを`create_workshop_from_linking_code()`へルーティングする処理)は
本フェーズの対象外とし、引き続き次の課題として残す。`process_memo_event()`は現状
受信した全テキストをそのままLLMへのメモとして扱うため、この次の課題が着手されるまでは
「連携コードをそのまま送信する」という2節の想定導線自体は未接続のままである点に注意
(ウェルカムメッセージの送信自体は本フェーズで実装済み)。

新規テスト12件追加、venture全体423件→444件全件・schema検証27件いずれもパスを確認した。

## 10. 追記(フェーズ69): message event側の連携コード判定ルーティング

9節で次の課題として残した「職人がコードをトーク上に送り返すと解決される」部分を実装した。
`cloud_function_webhook.process_message_event()`を新設し、messageイベントの入口として
`dispatch_webhook_events()`の委譲先を`process_memo_event()`から本関数へ差し替えた
(aircon-pashaのuser-account-linking-design.md 3節・`process_message_event()`と同じ骨格)。

`user_profile_store`・`workshop_store`・`linking_store`の3つ全てが渡された場合のみ、以下の
順で分岐する。

1. `user_profile_store.get_workshop_id(user_id)`が設定済み(連携済み)なら、従来通り
   `process_memo_event()`へそのまま委譲する。
2. 未連携の場合、受信テキストをそのまま`workshop_linking.create_workshop_from_linking_code()`
   へ渡す(2〜3節・`workshop_linking.py`フェーズ66実装済みの解決+workshop新規作成を1関数で
   行うロジックをそのまま利用)。成功時はLINKING_SUCCESS_MESSAGE(本フェーズ新設)を返信し、
   `process_memo_event()`(LLM呼び出し・usage_counter連携)へは一切進めない。
3. 解決に失敗した場合(コード不一致・期限切れ・依頼メモの先送り送信、いずれも区別しない、
   aircon-pashaと同じ「辞書引き一致を必須とし正規表現の形式一致のみでは連携コードと判定
   しない」方針)・user_idが取得できない場合は、いずれもLINKING_REQUIRED_MESSAGE(本フェーズ
   新設)を返す。

3ストアのいずれかが未接続(None)の場合は連携判定自体を行わず、フェーズ68以前と同じく
`process_memo_event()`へ直接委譲する後方互換設計とした(フェーズ64のusage_counter連携と
同じ考え方)。これにより、9節末尾で指摘していた「連携コードをそのまま送信する」という2節の
想定導線が、本フェーズで実際に接続された。

新規テスト18件追加、venture全体444件→462件全件・schema検証27件いずれもパスを確認した。

## 11. 追記(フェーズ97): 招待コード(pending_workshop_invites)発行・解決フロー詳細設計・実装

背景: フェーズ96のREADME整理で、5節「追加職人の招待」が概念設計にとどまり
(`pending_workshop_invites`という名前空間の存在のみ確定、発行契機の具体的判定条件・
コード解決後にworkshopへどう反映するかの手順・エラー時の扱いは未確定)、実装が一切
着手されていない(workshop_linking.py冒頭コメント参照)ことが判明した。本節は5節の
概念設計を、実装可能な具体的手順に落とし込む。

### 11.1 発行条件(issue_invite_code_for_workshop)

- 発行主体チェック: メッセージ送信元user_idが対象workshopの`contractor_user_id`と
  一致することを要求する(5節「契約者本人と一致する`user_id`から...検知された場合」の
  通り)。不一致の場合は`not_contractor`エラーとし、コードは発行しない。
- プランチェック: `plan_id`が`multi_craftsman`であることを要求する(5節末尾
  「ライト/スタンダードプランでは...アップグレードが必要です、という案内に置き換える」)。
  `multi_craftsman`以外の場合は`upgrade_required`エラーとし、コードは発行しない
  (呼び出し側はこのエラー種別を見てアップグレード案内文言に切り替える)。
- 上記2条件を満たす場合のみ、2節の連携コードと同一のコード仕様(6文字・31種の
  アルファベット・24時間TTL・使い切り一回限り)で`pending_workshop_invites/{code}`に
  `{workshop_id, issued_at}`を保存する(2節の`pending_links`と名前空間を分離することで、
  新規workshop作成用コードと既存workshopへの追加用コードが混同されない=解決ロジックが
  誤ったコレクションを参照して事故る可能性を構造的に排除する)。

### 11.2 解決・メンバー追加(add_member_from_invite_code)

招待コードを受け取った側(追加される職人)がLINEトーク上でコードを送信した際の
処理手順:

1. コードを`pending_workshop_invites`から解決する(存在確認・24時間TTL判定・使い切り、
   いずれも2節の連携コードと同じ判定ロジックを共有する)。失敗時はエラーを返す。
2. 解決した`workshop_id`に対し、送信元user_idの現在の所属状況を確認する。
   - 既に**同じ**workshopへ所属済み(`user_profile.workshop_id`が解決先と一致)の場合、
     冪等に`already_member=True`で成功を返す(2節`create_workshop_from_linking_code`の
     `already_linked`分岐と同じ考え方。二重送信・再タップ対策)。
   - 既に**別の**workshopへ所属済みの場合、3節で確定済みの「1人1工房のみ」という
     MVP前提(craftsman-account-linking-design.md 3節)に違反するため`already_in_
     another_workshop`エラーとし、追加は行わない(workshop移籍・脱退機能はMVP範囲外、
     次の課題とする)。
   - 未所属の場合のみ、workshopの`member_user_ids`へuser_idを追記
     (`WorkshopStoreProtocol.add_member_user_id`新設)し、
     `user_profile_store.link(user_id, workshop_id)`で所属を確定する。

`pending_workshop_invites`の期限切れパージ・unfollow時の即時削除は、2節の`pending_links`と
同じ`LinkingCodeStoreProtocol`形状を共有するため、既存の`purge_expired_links`・
`delete_pending_links_for_user`・`LinkingCodePurgeThrottle`をそのまま(別インスタンスの
ストアを渡すだけで)再利用できる。専用関数の新設は不要と判断した。

### 11.3 未検証・残課題

- ~~発行契機となる「職人を追加したい」という意図のLINEメッセージからの検知(LLM構造化
  出力への項目追加、または専用キーワード判定)自体は本節未着手。~~ → フェーズ99
  (llm-system-prompt-draft.md厳守事項7c参照)で判定方針(契約者本人からの明確な
  追加意思表示/非契約者からの表明/一般的な相談/判断不能、の4分岐)を新設した。
  ~~対応するschema拡張(status enumへの`workshop_invite_request`/
  `workshop_invite_request_unclear`追加、`workshop_invite_notice`フィールド新設)は
  未着手。~~ → フェーズ100でschema/output.schema.jsonに反映済み(checkout_notice
  〈厳守事項7b〉と同じ設計思想、`includes_invite_code`をkindによらず常にfalseとする
  補助フィールドを追加)。schema/validate_test_cases.pyにも正例2件(WIR1・WIR2)・
  ネガティブテスト1件(NEG9、includes_invite_code不一致検出)を追加した。
  ~~message-context-selection-design.md(フェーズ43)の優先順位への組み込み
  (契約者からの通常メモ送信・他の一時状態〈(a)〜(d)〉との割り込み位置の検討)は
  未着手。~~ → フェーズ101(message-context-selection-design.md 5節参照)で対応済み。
  7a/7b/7cはいずれも(a)(b)(c)のような独立したpre-injection文脈ではなく、(d)「通常の
  生成リクエスト文脈」1回のLLM呼び出しが返す構造化出力の一部であるため、(a)〜(d)の
  優先順位自体への変更は不要と結論した。(a)(b)(c)に該当するメッセージでは7a/7b/7cの
  意図検知は行われず次回メッセージへ持ち越される(意図的な設計、詳細は同5節)。
- ~~招待コード解決(message event側のルーティング、2節フェーズ69の
  `process_message_event()`相当の配線)自体も本節未着手。~~ → フェーズ98で対応済み
  (11.4節参照)。
- 複数職人プランの`member_user_ids`上限数(何名まで許容するか)はpricing-plan.md未確定
  (月間生成回数20回という利用量の上限のみ確定、人数上限は言及なし)。無制限のまま
  運用してよいか要検討、次の課題とする。
- ~~招待コード解決に成功したメッセージへの返信文言(ウェルカムメッセージ相当)自体は
  本節未設計。~~ → フェーズ98で`INVITE_JOIN_SUCCESS_MESSAGE`として確定済み(11.4節参照)。

新規テスト10件追加(`IssueInviteCodeForWorkshopTest`3件・`ResolveInviteCodeTest`3件・
`AddMemberFromInviteCodeTest`4件)、venture全体673件→683件全件
(`python3 prototype/run_all_tests.py`)・schema検証27件(`python3 schema/validate_test_cases.py`)
いずれもパスを確認した。

## 11.4 追記(フェーズ98): 招待コード解決のmessage event側ルーティング配線・ウェルカムメッセージ

11.3節の残課題のうち、以下2点に対応した(発行契機のLLM意図検知・人数上限は未着手のまま残す)。

**ルーティング配線**: `process_message_event()`(2節フェーズ69で新設)に
`invite_store: Optional[LinkingCodeStoreProtocol] = None`を追加した。未連携ユーザーが
送ってきたテキストは、(1)まず`create_workshop_from_linking_code()`(workshop新規作成用の
連携コード、`pending_links`)への解決を試み、(2)それが失敗し、かつ`invite_store`が渡されて
いる場合のみ`add_member_from_invite_code()`(既存workshopへの追加用の招待コード、
`pending_workshop_invites`)への解決を試みる、という2段構成とした。11.1節で連携コードと
招待コードを別名前空間で保存する設計としていたため、両方を順に試しても誤って別の意味の
コードとして解決される事故は構造的に起きない。`invite_store`は`user_profile_store`・
`workshop_store`・`linking_store`の3つとは別枠の完全省略可能パラメータとし、未指定時は
フェーズ69までと同じ「連携コードのみを試す」挙動をそのまま維持する後方互換設計とした
(招待コード機能自体をvent全体に一括で有効化する前の段階的ロールアウトを想定)。
`dispatch_webhook_events()`にも同様に`invite_store`引数を追加し、`process_message_event()`
への委譲時にそのまま渡すよう配線した。

**ウェルカムメッセージ**: 招待コード解決に成功した場合の返信文言として
`INVITE_JOIN_SUCCESS_MESSAGE`(「工房への参加が完了しました。依頼内容の簡単なメモを
送ってください。」)を新設した。2節`LINKING_SUCCESS_MESSAGE`(「連携が完了しました。...」)と
同じ構成だが、「連携」ではなく「工房への参加」という招待コード特有の文脈を明示する点のみ
差分とした。解決失敗時(連携コード・招待コードいずれとしても解決できない場合)は、
既存の`LINKING_REQUIRED_MESSAGE`をそのまま流用し区別しない設計とした(利用者から見て
どちらのつもりで送ったコードかをこのメッセージ単体からは判別できないため、2節と同じ
「原因を区別しない」方針を踏襲)。

`add_member_from_invite_code()`自体が「既に同じworkshopに所属済みなら冪等成功」
「既に別workshopに所属済みならエラー」を内包しているが、`process_message_event()`側は
この関数へ到達する時点で既に「送信元user_idがどのworkshopにも所属していない」ことを
直前の分岐で確認済みのため、招待コード解決に成功した場合は常に新規追加(`already_member
=False`)の分岐のみを通る。

新規テスト3件追加(`test_process_message_event_joins_workshop_on_valid_invite_code`・
`test_process_message_event_falls_back_to_linking_required_when_invite_store_not_provided`・
`test_process_message_event_replies_linking_required_when_invite_code_invalid`、
test_cloud_function_webhook.pyのcheck()呼び出しとしては13件分)、
venture全体`python3 prototype/run_all_tests.py`(10ファイル全件)・schema検証27件
(`python3 schema/validate_test_cases.py`)いずれもパスを確認した。承認不要なコード・
テスト追加のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生して
いないためpending-approval.mdへの追記なし。次回は11.3節に残る「発行契機の意図検知・
LLM構造化出力へのkind追加」または「`member_user_ids`上限数の検討」を優先候補とする。

## 11.5 追記(フェーズ100): 厳守事項7cに対応するschema拡張

llm-system-prompt-draft.md厳守事項7c(フェーズ99)・本doc 11.3節が「次回すぐに着手できる」
としていたschema拡張に対応した。course-set-pasha/aircon-pashaのフェーズ58(厳守事項7b・
checkout_notice新設)と同じ設計思想を踏襲し、`schema/output.schema.json`の`status`enumへ
`workshop_invite_request`/`workshop_invite_request_unclear`の2値を追加、これらのときのみ
非nullとなる`workshop_invite_notice`フィールド(`kind`・`body`・`includes_invite_code`)を
新設した。厳守事項7c(ii)(契約者以外からの表明)は6節の既存パターン(「契約者様に
ご確認ください」)にそのまま帰着させるため、専用のstatus・フィールドは追加していない
(7bのpricing_inquiryのような独立ステータスではなく、判定自体をPython側の
`contractor_user_id`一致チェックに委ねる6節の設計と整合)。`checkout_notice`の
`includes_checkout_url`と同じ設計思想で、`includes_invite_code`はkindによらず常にfalseと
なる(招待コード自体をLLM側で自己判断で本文に含めない、実際の発行は11.1節
`issue_invite_code_for_workshop`に委ねる)ことをコード側検証で担保する。

`schema/validate_test_cases.py`に正例2件(`WIR1_workshop_invite_request`・
`WIR2_workshop_invite_request_unclear`)・ネガティブテスト1件
(`NEGATIVE_CASE_WORKSHOP_INVITE_CODE_MISMATCH`、includes_invite_code不一致の検出確認)を
追加し、既存フィクスチャ全27件にも`workshop_invite_notice: null`を追記した(additionalProperties:
falseかつrequired化のため、既存フィクスチャの更新が必須)。schema検証は27件→30件全件
(`python3 schema/validate_test_cases.py`)、venture全体は`python3 prototype/run_all_tests.py`
(10ファイル全件、コード変更が無いため683件は変更前と同じ結果)いずれもパスを確認した。
承認不要なschema・テスト追加のみで、外部サービスへの公開・アカウント作成・支払い・送信等は
今回発生していないためpending-approval.mdへの追記なし。次回は11.3節に残る
message-context-selection-design.mdへの優先順位組み込み、または「`member_user_ids`上限数の
検討」を優先候補とする。

## 11.6 追記(フェーズ101): message-context-selection-design.mdへの優先順位組み込み

11.3節の残課題のうち「message-context-selection-design.md(フェーズ43)の優先順位への
組み込み」に対応した。詳細はmessage-context-selection-design.md 5節に記載したため要旨のみ
記す。厳守事項7a(解約意図検知)・7b(有料プラン開始意図検知)・7c(職人追加・招待コード
発行意図検知)はいずれも、`select_message_context`(仮称)が呼び出し前に文脈を差し替える
(a)(b)(c)の一時状態とは異なり、(d)「通常の生成リクエスト文脈」1回のLLM呼び出しが返す
構造化出力(`status`enum値)の一部にすぎない。したがって(a)〜(d)の4段階優先順位自体への
変更は不要と結論し、`select_message_context`の実装スコープも3節に記載の4分岐のままで
足りることを確定した。あわせて、(a)(b)(c)に該当したメッセージでは7a/7b/7cの意図検知が
行われず次回メッセージへ持ち越されるという意図的な挙動を明文化した。

本フェーズはドキュメント間の整合性確定のみでコード変更は無く、venture全体683件
(`python3 prototype/run_all_tests.py`)・schema検証30件(`python3 schema/validate_test_cases.py`)
いずれも変更前と同じ結果でパスすることを確認した。承認不要な設計文書作成のみで、外部
サービスへの公開・アカウント作成・支払い・送信等は今回発生していないためpending-
approval.mdへの追記なし。次回は11.3節に残る「`member_user_ids`上限数の検討」、または
3節`select_message_context`統合関数自体の実装、他venture・アイデア領域の前進を優先候補
とする。

## 11.7 追記(フェーズ102): 複数職人プランのmember_user_ids上限数を決定・実装

11.3節に残っていた「複数職人プランの`member_user_ids`上限数(何名まで許容するか)は
pricing-plan.md未確定」に対応した。

**上限の決定**: pricing-plan.mdの複数職人プラン(月額3,980円・月20回まで)は
market-research.mdが確認した実在事業者(ライディングショップ池上・Apion等)と同様
「個人〜小規模の職人が複数在籍する工房、乗馬クラブ専属で継続的に依頼を受ける業態」を
想定顧客像とし、法人規模の大人数工房は元々の想定顧客像に含まれない。この前提を踏まえ、
契約者本人を含めて**5名**を暫定上限とする(`prototype/workshop_linking.py`の
`MAX_MEMBER_COUNT`)。5名を超える規模の工房から要望があった場合は、本プランの機械的な
値上げ・上限緩和では対応せず、README「投資・大規模につき要相談」領域の個別カスタム対応
として扱う方針とし、pricing-plan.mdにもその旨を追記した。市場調査・想定顧客ヒアリングは
未実施のため(実際の連絡はオーナー承認待ちの範囲)、この上限数自体は他venture同様
「実顧客の声で検証すべき仮決め」の位置づけである。

**実装**: 2箇所で多重防御する設計とした。
1. `issue_invite_code_for_workshop()`(11.1節): 発行主体チェック・プランチェックに続けて
   `len(get_member_user_ids(workshop_id)) >= MAX_MEMBER_COUNT`を確認し、上限到達時は
   `member_limit_reached`エラーを返してコード自体を発行しない(呼び出し側は「上限に
   達しているため追加できません」という案内文言に切り替える想定、文言自体は未設計で
   次の課題とする)。
2. `add_member_from_invite_code()`(11.2節): 1つのworkshopに対して複数の招待コードが
   並行して発行され得るため(発行時点では上限未満でも、片方が使われて上限に達した後に
   もう片方が使われる事故があり得る)、未所属メンバーの追加直前にも同じ上限チェックを
   行う。上限到達時は`member_limit_reached`エラーとするが、招待コード自体は
   `resolve_invite_code()`の時点で既に使い切り済みのため消費される(11.2節の
   `already_in_another_workshop`分岐と同じ扱い)。

契約者自身がダウングレード等で`member_user_ids`が一時的に上限を超えて存在するケース
(downgrade-excess-member-handling-design.md参照、猶予期間中の縮小待ち状態)は本節の
発行・追加チェックの対象外であり影響しない(上限チェックは新規追加時のみに作用し、
既存メンバーを強制的に削除する処理ではないため)。

`prototype/test_workshop_linking.py`に新規テスト3件追加
(`test_rejects_issuance_when_member_limit_already_reached`・
`test_allows_issuance_one_below_the_member_limit`・
`test_rejects_new_member_when_member_limit_already_reached`)、venture全体686件
(683件→686件、`python3 prototype/run_all_tests.py`)・schema検証30件
(`python3 schema/validate_test_cases.py`、schema・フィクスチャへの変更なしのため
変更前と同じ結果)いずれもパスを確認した。承認不要な設計文書・コード・テスト追加のみで、
外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
pending-approval.mdへの追記なし。次回は上限到達時の案内文言の設計(LLM構造化出力への
反映要否含む)、または3節`select_message_context`統合関数自体の実装、他venture・
アイデア領域の前進を優先候補とする。

## 11.8 追記(フェーズ103): 上限到達時の案内文言の設計・実装

フェーズ102が次のステップ候補としていた「上限到達時の案内文言の設計(LLM構造化出力への
反映要否含む)」に対応した。

**LLM構造化出力への反映要否**: 不要と結論した。`member_limit_reached`は契約者の
明確な追加意思(厳守事項7c)をLLMが検知した後、Python側(`issue_invite_code_for_
workshop`・`add_member_from_invite_code`)が人数を数えて機械的に判定する決定論的な
分岐であり、7a/7b/7cのような「メッセージ文面からLLMが意図を読み取る」判定を必要としない。
`already_in_another_workshop`(11.2節)・`upgrade_required`・`not_contractor`(11.1節)と
同種の「Python側エラーコード→固定文言」という既存パターン(`LINKING_REQUIRED_MESSAGE`・
`INVITE_JOIN_SUCCESS_MESSAGE`と同じ構成)を踏襲すればよい。

**発見した実装漏れ**: `add_member_from_invite_code()`自体は11.7節(フェーズ102)で
`member_limit_reached`エラーを返すよう実装済みだったが、呼び出し側の
`process_message_event()`(フェーズ98、11.4節)は`membership.ok`のみを見て、`False`の
場合は全て`LINKING_REQUIRED_MESSAGE`(「先に連携コードの送信が必要です」)を返す実装の
ままだった。招待コード自体は有効に解決できているにもかかわらず「連携コードの送信が
必要です」という案内を返すのは、あたかもコードが無効・期限切れであるかのように利用者に
誤解させてしまう(実際には工房が満員であることが原因)。本フェーズで
`MEMBER_LIMIT_REACHED_MESSAGE`(「このコードは有効ですが、工房の登録人数が上限に達して
いるため追加できません。人数の調整については契約者様にご確認ください。」)を新設し、
`membership.error == "member_limit_reached"`の場合はこちらを返すよう`process_message_
event()`を修正した(`prototype/cloud_function_webhook.py`)。

**`already_in_another_workshop`は対応対象外とした理由**: 同エラーにも当初は専用文言
(`ALREADY_IN_ANOTHER_WORKSHOP_MESSAGE`)を用意し同様に分岐を追加したが、テスト実装の
過程で、`process_message_event()`の冒頭分岐(「`user_profile_store.get_workshop_id
(user_id)`が設定済みなら`process_memo_event()`へ委譲」)により、`add_member_from_
invite_code()`へ到達する時点で送信元は必ず未連携(`existing_workshop_id is None`)である
ことが保証されていることが判明した。すなわち`add_member_from_invite_code()`内部の
`already_in_another_workshop`分岐(11.2節)は、本関数を直接呼び出す単体テスト以外では
現在到達不可能であり、`process_message_event()`経由の統合テストでは検証できない
(意図的に到達不可能にしている11.4節の設計とも整合する)。到達不可能な分岐に対する
call site側のメッセージ分岐・テストを追加するのは実際には検証できないコードを追加する
だけであり、`ALREADY_IN_ANOTHER_WORKSHOP_MESSAGE`および対応する分岐は本フェーズでは
見送った(将来、workshop間の移籍・脱退機能(11.2節が「MVP範囲外」としている)が
追加され、既に連携済みのユーザーが招待コードを送れる経路ができた場合には、同様の
専用メッセージ設計が必要になる)。

`prototype/test_cloud_function_webhook.py`に新規テスト1件追加
(`test_process_message_event_replies_member_limit_reached_message_when_workshop_full`、
発行時点(4名)では上限未満だったが解決までの間に別経路で5名に達したケースを再現)、
venture全体687件(686件→687件、`python3 prototype/run_all_tests.py`)・schema検証30件
(`python3 schema/validate_test_cases.py`、schema・フィクスチャへの変更なしのため変更前
と同じ結果)いずれもパスを確認した。承認不要なコード・テスト追加のみで、外部サービスへ
の公開・アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの
追記なし。次回は3節`select_message_context`統合関数自体の実装、または他venture・アイデア
領域の前進を優先候補とする。

最終更新: 2026-09-13 05:00 UTC(フェーズ103)
