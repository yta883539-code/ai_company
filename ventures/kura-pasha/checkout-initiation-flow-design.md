# 決済導線設計(有料プラン開始時のStripe Checkout Session作成)

作成日: 2026-09-08(フェーズ50)

subscription-billing-data-model-design.md(フェーズ46・49)「4. 未検証・残課題」1点目、
および README.md「次にやること」1点目の「Checkout Session発行フロー、Stripe Webhookの
署名検証・イベントディスパッチの実装(course-set-pasha/stripe-webhook-http-entry-point-
design.md相当)」のうち、まずCheckout Session発行フロー(申込者が有料プランを開始する側の
導線)を対象に設計する。Stripe Webhook側(受信・署名検証・イベントディスパッチ)は
本ドキュメントの範囲外とし、次の課題として残す。

## 1. 前提

- craftsman-account-linking-design.md(フェーズ25)で確定した通り、契約単位は
  `craftsman_workshop/{workshop_id}`であり、Checkout Sessionの`client_reference_id`には
  `user_id`ではなく`workshop_id`を設定する(4節)。
- trial-end-condition-design.md(フェーズ47・48)により、無料トライアルは
  「生成1回使用」または「workshop作成から30日経過」いずれか早い方で終了する。トライアル
  終了後に生成を止める配線自体はフェーズ48で意図的に見送られており(有償契約判定手段が
  当時未実装だったため)、本ドキュメントが対象とするCheckout Session発行フローと
  フェーズ49で実装済みの`get_subscription_status`/`set_subscription_status`が揃うことで、
  次の課題としてその配線に着手できる状態になる(本ドキュメントの範囲外)。
- 契約操作の権限は、subscription-cancellation-flow-design.md(フェーズ23)で
  「契約者(`contractor_user_id`)のみが解約・ダウングレード操作を行える」と定義されて
  いる。本ドキュメントの有料プラン開始導線も同じ権限モデルを踏襲し、
  **契約者本人のみがCheckout Sessionを開始できる**こととする(理由: 複数職人プランは
  1つのworkshopを複数人が共有するため、非契約者が誤って/意図的に決済を開始できてしまうと
  誰の名義で課金されるか不明確になる)。

## 2. トリガーのタイミング・経路

course-set-pasha/checkout-initiation-flow-design.md(フェーズ98)はLIFFアプリ経由の
Webボタンを想定していたが、本ventureでは以下の理由により**LINEトーク内のテキストメッセージ
(意図検知)を起点とする方式**を採用する。

- subscription-cancellation-flow-design.md(フェーズ23)が既に「契約者が解約したい意図を
  LINEメッセージで示す→LLMが厳守事項7aの意図判定で検知→案内メッセージ返信」という同型の
  設計を確立済みであり、有料プラン開始の意図検知もこれをそのまま踏襲できる。
- 本venture(鞍職人向け)は受注頻度が低く、course-set-pasha・aircon-pashaのような
  「常設のWebランディングページ+申込フォーム」自体がまだ存在しない(README.md冒頭でも
  会員管理・予約受付・決済に関する高度な機能はMVP範囲外としていた経緯がある)。
- LIFFアプリを新規登録せずに済む(LIFFはLINE Developersコンソールでの外部サービス設定=
  オーナー承認が必要なアクションに該当するため、意図検知方式を採れば当該承認待ち事項を
  1つ削減できる)。
- LINEのMessaging API Webhookは受信時点でLINE Platform側の署名(`X-Line-Signature`)で
  検証済みであることが前提となっており(この署名検証自体は本venture共通の受信処理の
  前提として他のフロー〈follow event処理・解約意図検知等〉でも暗黙に依拠しているため、
  本ドキュメントでは新設せず既存前提を踏襲する)、そこから得られる`event.source.userId`は
  第三者になりすまされない値として扱える。そのためLIFFのIDトークン検証のような追加の
  なりすまし対策を要しない。

トリガー元として2経路を想定する(course-set-pasha同様の整理):

- (a) トライアル終了が近づいた際の通知メッセージ内の案内文(aircon-pasha/
  limit-approaching-notification-design.md相当を本venture向けに設計する必要があるが、
  本ドキュメントの範囲外。次の課題として残す)。
- (b) 契約者がいつでもLINEトーク上で「有料プランを始めたい」「申し込みたい」等の意図を
  示すメッセージを送信する経路(セルフサービス)。

## 3. Checkout Session作成エンドポイント(設計)

既存のLINE Messaging API Webhook受信処理(message event)の一部として、
`handle_checkout_intent(event, workshop_store)`を新設する想定とする。

1. `event.source.userId`(LINE Platform検証済み)を取得する。
2. `workshop_store.get_workshop_id(user_id)`(usage_counter_workshop.pyに既存の
   `LinkStoreProtocol.get_workshop_id`相当)でworkshopを特定する。未所属(未連携)の
   場合はcraftsman-account-linking-design.mdの連携コード案内へフォールバックする
   (本ドキュメントの対象外)。
3. `workshop_store.get_contractor_user_id(workshop_id)`と`user_id`を比較し、一致しない
   場合は「契約者本人のみお申し込みいただけます」旨の案内を返し処理を打ち切る(1節の
   権限モデルの実装)。
4. `workshop_store.get_subscription_status(workshop_id)`(フェーズ49実装済み)が
   既に`"active"`の場合は「既にご契約中です」旨の案内を返し重複契約を防ぐ。
5. `workshop_store.get_stripe_customer_id(workshop_id)`(フェーズ49実装済み)で既存の
   `stripe_customer_id`を確認する。過去に解約して再契約する場合等、既に値がある場合は
   同一customerを再利用しStripe側に重複顧客レコードを作らない。
6. `build_checkout_session_params(workshop_id, plan_id, existing_stripe_customer_id)`
   (下記4節)が組み立てたdictでStripe Checkout Session作成APIを呼び出す(実装は実Stripe
   アカウント接続後、オーナー承認待ち)。
7. 生成されたCheckout SessionのURLをLINEメッセージとして契約者へ返信する(course-set-pasha
   のLIFFページ遷移と異なり、本ventureはLINEトーク上にURLをそのまま貼るシンプルな導線と
   する。Stripe Checkout自体はLINE内蔵ブラウザまたは外部ブラウザで開かれる)。

実LINE Messaging API・実Stripe API呼び出しは実アカウント接続後の話であり、本ドキュメントでは
机上設計にとどめる。

## 4. プロトタイプ実装方針

course-set-pasha/checkout-initiation-flow-design.md 4節と同じ方針(実API呼び出し自体は
対象外とし、パラメータ組み立てのみ純粋関数として切り出す)を踏襲するが、本venture固有の
`workshop_id`起点・`plan_id`引数を反映する。

`build_checkout_session_params(workshop_id, plan_id, existing_stripe_customer_id=None) ->
dict`(新設`prototype/checkout_session.py`):

- `workshop_id`が空文字列・Noneの場合は`ValueError`(呼び出し元の3節手順2〜3が必ず
  先に成功している前提を明示するガード)。
- `plan_id`はpricing-plan.mdの3プラン(ライト/スタンダード/複数職人)のいずれかである
  ことを検証し、不正な値の場合は`ValueError`(trial-end-condition-design.mdの
  `InvalidSubscriptionStatusError`と同じ「早期にデータ不整合を検知する」方針を踏襲)。
- 返り値は`{"mode": "subscription", "client_reference_id": workshop_id,
  "line_items": [{"price": <plan_idに対応するStripe Price ID>, "quantity": 1}],
  "success_url": ..., "cancel_url": ...}`を基本とし、`existing_stripe_customer_id`が
  渡された場合のみ`"customer"`キーを追加する。
- `plan_id`→Stripe Price IDの対応表、`success_url`/`cancel_url`は本ドキュメントでは
  仮のプレースホルダとし、実Stripeダッシュボードでの商品登録・実LPドメイン確定後に
  差し替える(定数として関数の外に切り出し、テストでは上書き可能にする)。

## 残課題

- Stripe Webhook(`checkout.session.completed`)受信・署名検証・イベントディスパッチの
  設計・実装(course-set-pasha/stripe-webhook-*-design.md相当)。受信後、
  `client_reference_id`(=`workshop_id`)から対象workshopを特定し、
  `set_stripe_customer_id`・`set_subscription_status(workshop_id, "active")`を呼び出す
  処理が必要(フェーズ49で実装済みのメソッドを実際に配線する箇所)。
- フェーズ48で見送った`is_trial_period_over`のトライアル終了時生成一時停止への配線
  (本ドキュメントとStripe Webhook実装が揃った後に着手)。
- トライアル終了通知メッセージ自体(上記2(a))は本venture未設計。次の課題として残す。
- ~~意図検知(「有料プランを始めたい」等)のllm-system-prompt-draft.mdへの厳守事項追加
  (解約意図検知の厳守事項7aと対になる新規項目)は本ドキュメントでは未着手。~~
  → フェーズ57(2026-09-09 06:00 UTC)でllm-system-prompt-draft.mdに厳守事項7bとして
  対応済み。対応するschema拡張(status enum拡張)は実API接続オーナー承認待ちのため
  引き続き次の課題として残る。
- `plan_id`→Stripe Price IDの対応表・`success_url`/`cancel_url`の実際の値確定は、実Stripe
  ダッシュボードでの商品登録(オーナー承認待ち)と合わせて行う。
- 実LINE Messaging API・実Stripe API接続はオーナー承認待ち(pending-approval.md参照)。
