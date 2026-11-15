# デプロイ手順書(GCPプロジェクト作成・Stripeアカウント開設の承認後に実施)

## 位置づけ

aircon-pasha・course-set-pasha・forklift-pasha・kura-pasha・line-reservation-ai・
oshien-pashaにはいずれも既にdeployment-runbook.mdがあるが、本venture
(event-komiguai-pasha)のみ未作成だったcross-venture parityギャップに対応する
(launch-readiness-checklist.mdフェーズ119の次回候補(1)「承認待ち事項が承認された場合は
その着手を最優先」に備え、承認後すぐ着手できる手順を事前に整理したもの)。

**本ドキュメント作成自体はGCPプロジェクト作成・Stripeアカウント開設・課金を一切伴わない
机上整理であり、承認前に着手してよい範囲内の作業として実施した。** launch-readiness-
checklist.md記載の承認待ち事項1(実GCPプロジェクト作成+Firestoreデータベース新規作成)・
2(実Stripeアカウント開設)がオーナーから承認されるまでは、本手順書のいずれのステップも
実行しない。

これまでの設計(tech-stack.md・web-form-hosting-selection.md・firestore-security-
rules-draft.md・各HTTPエントリポイント設計文書)とprototype/配下のコードは、以下の手順に
沿ってそのまま接続できる設計にしてある。

## 他venture(aircon-pasha等)との構成上の違い(本手順書に影響する点)

- 入力チャネルがLINE公式アカウントではなく、シンプルなWebフォーム(URLアクセスのみ、
  アカウント登録不要)である(tech-stack.md・web-form-hosting-selection.md)。そのため
  LINE Developersでのチャネル開設・Channel Secret取得のステップが不要な一方、Stripe
  Checkout(一回払いモード)の導入ステップが新たに必要になる。
- 課金モデルが継続課金(サブスクリプション)ではなく都度決済(1回=1イベント、
  one-time-checkout-no-account-design.md)である。そのためサブスクリプション状態管理
  (`subscription_status`・`current_period_end`等)やWebhookイベント種別の分岐は不要で、
  Stripe側で待ち受けるイベントは`checkout.session.completed`単一種別のみに限定される
  (stripe-webhook-signature-verification-design.md2節)。
- フォーム配信とバックエンド処理を同一Cloud Runサービス内に統合する構成
  (web-form-hosting-selection.md選択肢A)のため、Firebase Hosting等の追加GCPプロダクト
  有効化は不要。
- 会話状態マシンが無く「1フォーム送信=1イベント→LLM呼び出し→4出力生成→画面表示」で
  完結するため、line-reservation-aiのFunction B(Cloud Tasks経由の非同期本処理)・
  Function C(リマインド定期実行)に相当する非同期処理は不要(ただしTTL失効チェック用の
  定期実行は後述ステップ6で扱う)。

## 手順

### ステップ0: 前提の確認(承認後、着手前に再確認)

- オーナーが承認したのは「(1)GCPプロジェクト作成、(2)Firestoreデータベース新規作成、
  (3)Cloud Run functionsの有効化、(4)LLM APIキー取得、(5)Stripeアカウント開設・本番用
  APIキー取得」のどこまでかを、pending-approval.mdのオーナー回答文言で再確認する。範囲外の
  ステップ(例: 独自ドメイン取得〈custom-domain-vs-default-url-decision.mdの通り初回は
  デフォルトURL採用のため当面不要〉)は別途pending-approval.mdに追記して承認を待つ。
- 他venture(line-reservation-ai・course-set-pasha・aircon-pasha等)と同一GCPプロジェクト
  内で同居させるか、venture単位で別プロジェクトに分けるかは、承認時にオーナーへ確認する
  (課金・アクセス権限の管理単位として別プロジェクトを推奨するのは他ventureと同じ)。

### ステップ1: GCPプロジェクト作成

- 新規GCPプロジェクトを作成(プロジェクトIDは`event-komiguai-pasha-mvp`等)。
- 請求先アカウントを紐づける(=支払い設定。この時点で初めて課金が発生しうるため、承認範囲に
  含まれていることを必ず確認してから実施する)。
- billing-budget-cap-safeguard-design.md(フェーズ118)で設定済みの月間予算500円のBilling
  Budgetを本プロジェクトに対して作成し、閾値到達時の自動課金停止を有効化する(他6venture
  横展開済みの手順をそのまま適用)。
- 想定コストの参考値: llm-api-cost-estimate.md・unit-economics-estimate.mdの試算
  (都度決済1回あたりのLLM API原価・Stripe決済手数料〈4.3%〉・Firestore原価を合算した
  粗利率試算)。

### ステップ2: Firestoreデータベース新規作成・コレクション初期設定

- Native modeでFirestoreを有効化。
- firestore-security-rules-draft.mdで確定済みの3コレクション(`one_time_draft`・
  `inquiry`・`idempotency_key_index`)はコード側の初回書き込みで自動作成されるため、
  事前の手動作成は不要。
- `one_time_draft`コレクションのTTL24時間自動失効(ttl-expiry-result-delivery-
  refund-design.md)は、Firestore TTLポリシー(`expireAt`フィールド基準)をコレクション
  単位で設定する。`idempotency_key_index`側は`one_time_draft`用途(24時間)と`inquiry`
  用途(永続)が1コレクション内に共存するため、TTLポリシーは`expireAt`フィールドが
  設定されているドキュメントのみに適用される(Firestore TTLの既定動作通り、フィールド
  未設定のドキュメントは対象外)ことを有効化後に確認する。
- firestore-security-rules-draft.mdで確定済みのセキュリティルール(deny-all、Firebase
  Admin SDK経由のみ許可)をデプロイする。
- 複合インデックスの要否: **不要と確定済み**(idempotency-key-duplicate-detection-
  firestore-query-design.md フェーズ66・2節)。本venture内の重複検知クエリ(`one_time_draft`・
  `inquiry`いずれも`idempotencyKey`への単一フィールド等価条件のみ)は、他venture
  (forklift-pasha等)のfirestore-composite-index-plan.mdが扱う「2フィールド以上の組み合わせ・
  不等号を含む範囲指定」には該当せず、Firestoreが自動作成する単一フィールドインデックスで
  処理できるため、`firestore.indexes.json`への追記は不要。実GCPプロジェクト作成後は、この
  机上結論どおりデフォルトインデックスで想定クエリが処理されることの実環境確認のみ行う
  (想定外の挙動が確認された場合のみ追記する)。

### ステップ3: シークレット管理

- LLM APIキー、Stripe本番用APIキー・Webhook署名シークレット(`whsec_...`)は環境変数に
  直書きせず、Secret Managerに登録し、Cloud Run functionsのランタイムから参照する
  (他venture・vendor-breach-key-rotation-runbook.mdと同じ方針)。
- prototype/配下の各エントリポイント(checkout_session_creation.py・stripe_webhook.py・
  draft_generation_fn.py等)は、Secret Manager参照に差し替えるだけで済む引数設計に
  既にしてある(コード変更不要、注入方法の変更のみ)。

### ステップ4: Cloud Run functions デプロイ(4関数)

web-form-hosting-selection.md選択肢Aの方針通り、フォーム配信(GET)と各処理(POST)を
同一Cloud Runサービス内の別ルートとして実装し、以下4つのHTTPエントリポイントをデプロイする
(いずれも2nd gen、Python 3.xランタイム、prototype/配下のコードをそのままエントリポイント
として使える設計)。

1. **申込フォーム**(GET `/`・POST `/submit-event`): inquiry-form-http-entry-point-
   design.md・submit-event-form-http-entry-point-design.md相当
   (prototype/inquiry_form_http_entry.py・cloud_function_submit_event_form.py)。
2. **問い合わせフォーム**(POST `/inquiry`): inquiry-form-http-entry-point-design.md相当
   (prototype/cloud_function_submit_inquiry.py)。
3. **Stripe Webhook受信**(POST `/webhook/stripe`): handle-stripe-webhook-http-entry-
   point-design.md(prototype/cloud_function_handle_stripe_webhook.py・
   stripe_webhook.py)。署名検証(ステップ3のWebhook署名シークレット使用)→冪等性チェック
   (`idempotency_key_index`参照)→`one_time_draft`への書き込み→LLM生成トリガーの順で
   処理する。
4. **結果ページ**(GET `/result/{draft_id}`): get-result-page-http-entry-point-design.md
   (prototype/cloud_function_get_result_page.py・result_page_entry.py)。TTL24時間以内
   かつ`page_state`に応じた表示切り替え(フェーズ116実装済みのJS切り替えとの結合)。

4関数は同一のタイムアウト・同時実行数で揃えるべきではない。関数3(Stripe Webhook受信)
だけが`generate_fn`(LLM呼び出し)を同期的に、最大`MAX_ATTEMPTS=3`回(初回+リトライ2回、
generation_retry_and_refund.py)まで試行してからHTTPレスポンスを返す設計であり
(リトライ間のsleep/backoffは実装されていないため、1回あたりのLLM応答時間×最大3回が
そのままHTTPリクエストの占有時間になる)、関数1・2・4(フォーム受付・結果ページ表示、
いずれもFirestoreへの単純な読み書きのみでLLM呼び出しを含まない)とは処理時間の性質が
大きく異なる。

- **関数1・2・4**: 低頻度利用(月数件/主催者)を前提に、タイムアウト・同時実行数とも
  Cloud Run functions(2nd gen)の既定に近い保守的な初期値から開始し、実運用後の利用
  ペースを見て調整する。
- **関数3(Stripe Webhook受信)だけはタイムアウトを明示的に長め(2nd genの上限である
  3600秒に近い値)に設定する。** これは応答速度を上げるための性能チューニングではなく、
  **プラットフォーム側のタイムアウトで関数が途中終了すると、処理フローの途中(リトライ
  継続中、または2回失敗後のStripe Refund API呼び出し前)で処理が止まり、「決済は完了した
  のに生成も返金も行われないまま主催者が放置される」という金銭に関わる不整合が起きうる**
  ためである(ttl-expiry-result-delivery-refund-design.md 3-2節のリトライ→返金フローは
  同期処理内で完結する前提で設計されており、途中終了への耐性は別途設けていない)。
  タイムアウトを十分長く取ることで、この不整合の発生経路の一つ(プラットフォーム起因の
  強制終了)を塞ぐ。
- 一方、Stripe自身がWebhookへの応答をいつ「失敗」と判断し再送するかは、Stripe公式ドキュ
  メントに具体的な秒数が明記されておらず、サードパーティ情報でも数秒〜30秒程度と幅がある
  (2026-11-15 WebSearch調査)。本venture側のタイムアウトを長く取っても、Stripe側が応答を
  待たずに先に再送してしまう可能性は残るが、stripe-event-idempotency-design.md 2節の
  `event_id_store.mark_processed()`は`handle_checkout_session_completed()`呼び出しの
  直後(`process_generation_after_payment()`等の生成・返金処理より前)に呼ばれる配線に
  なっていることをprototype/stripe_webhook.py(`receive_stripe_webhook()`)で確認済み
  であり、Stripe側の再送が生成処理の実行中に届いても二重のLLM呼び出し・二重課金・二重
  返金には至らない(course-set-pashaフェーズ368でLINE Webhookタイムアウト〈2秒〉との
  不整合が見つかった際と同種の確認を行った結果、本ventureは既存設計の時点で安全側に
  組まれていたことを確認した、という位置づけ)。したがって対応が必要なのは「Stripe側の
  再送表示」というダッシュボード上の見かけの問題のみであり、残るタイムアウト設定は
  「本venture側の処理を最後まで完了させる」ことに専念してよい。
- 関数3の同時実行数(max-instances)自体は、低頻度利用のため低く絞ってよいが、1回の処理
  占有時間が他3関数より長いため、関数1・2・4と同じ数値をそのまま流用せず関数3単独で
  決める(具体的な数値は実LLM接続後の1件あたり処理時間の実測を待って確定する、既存の
  他venture同様の扱いとする)。

### ステップ5: Stripeアカウント開設・Webhookエンドポイント登録

- Stripeアカウントを開設し、本人確認・銀行口座登録を行う(オーナー自身の対応が必要な
  範囲)。
- 本番用APIキー・Webhook署名シークレットを取得し、ステップ3のSecret Managerに登録する。
- StripeダッシュボードでWebhookエンドポイントを登録し、ステップ4-3の関数URLを宛先に設定、
  購読イベントは`checkout.session.completed`のみを選択する(stripe-webhook-signature-
  verification-design.md2節の通り、本ventureは都度決済1種別のみで完結するため他イベント
  種別の購読は不要)。
- stripe-checkout-session-params-design.md・checkout-session-success-cancel-url-
  design.mdの設計通り、Checkout Session発行時の`success_url`/`cancel_url`をステップ4の
  結果ページURLに合わせて設定する。

### ステップ6: TTL失効時の定期実行判定ロジック: 不要と確定済み(追加コンポーネントなし)

- ttl-expiry-result-delivery-refund-design.md(フェーズ12)1節の設計方針どおり、本venture
  はFirestore TTLポリシー単体に委ね、Cloud Scheduler等の定期実行コンポーネントは追加しない
  (tech-stack.mdが志向する「低頻度利用に対して固定費・常時稼働コンポーネントを増やさない」
  方針に基づく、フェーズ12時点での既定方針)。
- TTL失効時点で追加の判定ロジックが不要である理由は、同design.md 3節の2ケースを突き合わせる
  と次のように整理できる(本フェーズで明確化)。
  1. 決済未完了(`awaiting_payment`)のまま失効するケース(3-1節): 課金自体が発生していない
     ため返金の概念が生じず、TTL失効による削除のみで処理が完結する。失効タイミングでの
     追加判定は不要。
  2. 決済完了後に生成処理が失敗するケース(3-2節): Webhook受信直後(決済完了から数分〜
     数時間以内)に最大2回の自動リトライ→`generation_failed`へのステータス更新→Stripe
     Refund APIでの全額自動返金、までを**即時**に行う設計であり、TTL失効(24時間後)という
     タイミングを待って判定する処理ではない。
  - 以上より、「TTL失効」と「返金判定」は本venture設計上もともと別タイミングで発生する
    処理であり、両者を結びつける定期実行コンポーネントは設計上存在しない。本ステップ名の
    「TTL失効・返金判定の定期実行設定」という前提(両者をまとめて定期実行する想定)自体が
    誤りだったため、本フェーズで前提を修正した。
- したがって本ステップで追加の設定作業は発生しない。Firestore TTLポリシーの有効化(ステップ2)
  とWebhook受信時の即時リトライ・返金ロジック(prototype/generation_retry_and_refund.py、
  ステップ4-3の実装済みコードをそのまま使用)だけで本venture要件を満たす。

### ステップ7: 結合テスト

- schema/output.schema.json・output-samples-validation.mdのパターンを、実LLM APIに
  投入して構造化出力(`generated`/`out_of_scope`/`insufficient_input`)の安定性を
  確認する。
- テスト用のStripeテストモードAPIキーでCheckout Session発行〜Webhook受信〜結果ページ
  表示までのエンドツーエンド疎通を確認する(本番キーへの切替前)。
- `one_time_draft`のTTL24時間失効・`idempotency_key_index`による重複検知が、実際の
  Firestore書き込みと連動して動作するかを確認する。
- post_generation_checks.pyの機械チェックが実LLM出力に対して誤検知・見落としなく
  機能しているかを実出力例で確認する。

### ステップ8: 本番投入前チェックリスト

- legal-notices-draft.mdの特定商取引法表記・プライバシーポリシーが実際のLLMプロバイダ名・
  Stripeアカウント名で更新されているか。
- data-retention-policy.md・vendor-breach-key-rotation-runbook.mdの保有キー一覧
  (Stripe・LLM API・GCPサービスアカウント鍵)に変更が無いか最終確認する。
- custom-domain-vs-default-url-decision.md(フェーズ50)の通り、初回ローンチはCloud Run
  デフォルトURL(`*.run.app`)のまま進める。

## 未確定事項・承認前に決めておきたいこと

- 請求先アカウントの支払い方法(オーナー個人のクレジットカード等)をどれにするかは、
  承認時にオーナーから指定してもらう必要がある(本エージェントは決済手段を選定・登録
  できない)。
- LLM APIプロバイダ(Claude API等)の選定自体は未確定だが、schema/配下の構造化出力設計は
  プロバイダ非依存であるため、承認後にプロバイダを決めても手順への影響はない(他venture
  と同じ整理)。
- ステップ4の同時実行数(max-instances)の具体的な数値は、承認・実接続後の実測を待って
  確定する(ステップ2の複合インデックス要否・ステップ6の定期実行の要否は、いずれも
  フェーズ121で机上確定済み。上記各ステップ参照)。関数3(Stripe Webhook受信)のタイムアウト
  自体は、実測を待たず「プラットフォーム起因の途中終了で返金未実行のまま放置される」リスクを
  塞ぐ目的で、フェーズ122にて2nd gen上限に近い値へ先に確定した(ステップ4参照、同時実行数
  とは独立した判断)。

最終更新: 2026-11-15 13:00 UTC(フェーズ122: ステップ4の「同時実行数・タイムアウトは低頻度
利用を前提とした初期値から」という一括記載を、関数3〈Stripe Webhook受信〉が同期的に
`generate_fn`を最大3回試行してから応答する点で他3関数と処理時間の性質が異なることを
prototype/generation_retry_and_refund.py(`MAX_ATTEMPTS=3`、リトライ間sleepなし)で確認し、
関数3単独でタイムアウトを2nd gen上限に近い値へ先に確定する方針に改めた(プラットフォーム
タイムアウトによる途中終了がリトライ継続中・Refund API呼び出し前に起きると、決済済みなのに
生成も返金も行われない不整合が残るため)。また、Stripe自身のWebhook応答待ち秒数は公式未公開
(WebSearchで確認、サードパーティ情報は数秒〜30秒程度と幅がある)だが、prototype/
stripe_webhook.py(`receive_stripe_webhook()`)で`event_id_store.mark_processed()`が
生成・返金処理より前に呼ばれる配線であることを確認済みのため、Stripe側の再送が本venture側の
生成処理の実行中に届いても二重実行には至らないことを明確化した(course-set-pashaフェーズ368の
LINE Webhookタイムアウト不整合と同種の確認を行い、本ventureは既存設計の時点で安全側だったと
結論)。コード変更なし(deployment-runbook.mdの記載のみ)、回帰確認として既存テスト184件・
schema検証22件を実行しいずれも変更なしでパスすることを確認した(回帰なし)。承認が必要な
アクション(支払い・アカウント作成・外部公開・送信等)は今回発生していないため
pending-approval.mdへの追記なし。次回候補: (1)承認待ち事項(launch-readiness-checklist.md
記載の1〜3)がオーナーから承認された場合はその着手を最優先、(2)関数1・2・4の同時実行数・
関数3のmax-instancesの具体的な数値確定(実LLM接続後の実測待ち)、(3)他venture・アイデア
領域の前進。)

追記(フェーズ121の記録、参考): 2026-11-15 03:00 UTC(フェーズ121: ステップ2「複合インデックス要否」・ステップ6
「TTL失効・返金判定の定期実行」の2件の未確定事項を、既存設計文書(idempotency-key-
duplicate-detection-firestore-query-design.mdフェーズ66・ttl-expiry-result-delivery-
refund-design.mdフェーズ12)の記載から机上で確定した。複合インデックスは単一フィールド
等価条件のみのため不要、TTL失効時の定期実行は返金判定がWebhook受信直後の即時処理であり
TTL失効タイミングとは無関係に発生するため不要、と判断し、ステップ6の前提自体(両者を
結びつけた定期実行という想定)が誤りだったことを明確化した。コード変更なし(設計文書のみ)、
回帰確認として既存テスト184件・schema検証22件を実行しいずれも変更なしでパスすることを
確認した(回帰なし)。承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は
今回発生していないためpending-approval.mdへの追記なし。

追記(フェーズ120の記録、参考): 2026-11-14 20:00 UTC(フェーズ120: 他6venture既存の
deployment-runbook.mdのcross-venture parityギャップを解消し、本venture(都度決済・
Webフォーム・LINE非採用という他venture群と異なる構成)向けに新規作成した。コード変更なし、
実行(GCPプロジェクト作成・
Stripeアカウント開設・課金設定等)は一切行っていない。)
