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
  追加意思表示/非契約者からの表明/一般的な相談/判断不能、の4分岐)を新設した。ただし
  対応するschema拡張(status enumへの`workshop_invite_request`/
  `workshop_invite_request_unclear`追加、`workshop_invite_notice`フィールド新設)、
  および message-context-selection-design.md(フェーズ43)の優先順位への組み込み
  (契約者からの通常メモ送信・他の一時状態〈(a)〜(d)〉との割り込み位置の検討)は
  未着手のまま次の課題として残す。
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

最終更新: 2026-09-12 23:00 UTC(フェーズ98)
