# 実Firestore承認後のランタイム依存切り替え設計(フェーズ63)

cloud-monitoring-alert-policy-design.md(フェーズ62)3節「本venture固有の
runtime-dependency-switching-design.md相当文書(実Firestore接続とモック接続の
フラグ切り替え設計、関数境界の確定)自体がまだ存在しないため、同文書の新規作成を
次回候補とする」に対応する。kura-pasha・aircon-pasha・course-set-pasha・
forklift-pashaで確立済みの設計パターンを横展開するが、本ventureはLINE非依存・
Webフォーム単発決済モデル(tech-stack.mdフェーズ7、アカウント登録なし)のため、
他4venture共通の`organizer_account`/`operator_store`相当のアカウント単位の
Firestoreストアは存在せず、代わりに`one_time_draft`・`inquiry`の2コレクション
(data-retention-policy.mdフェーズ60)が対象になる。コード変更・外部アカウント
作成のいずれも行わない(ドキュメントのみの設計フェーズ)。

## 1. 現状の棚卸し(関数境界の確定)

tech-stack.md(フェーズ7)・one-time-checkout-no-account-design.md(フェーズ10)・
ttl-expiry-result-delivery-refund-design.md(フェーズ12)・inquiry-handling-design.md
(フェーズ15)で確定済みの処理フローから、Firestoreに読み書きするCloud Run
functionsの関数境界を本フェーズで初めて明示的に確定する(他venture側は
cloud-functions-generation-decision.md相当で既に確定済みだったが、本ventureには
その文書自体が無く、本節が初めての整理となる)。

- `submit_event_form`: Webフォーム送信(HTTPSトリガー)。入力5要素を受け取り
  `one_time_draft/{draft_id}`を`awaiting_payment`として新規作成し、Stripe
  Checkout Session(`mode: "payment"`)を作成してセッションURLを返す
  (one-time-checkout-no-account-design.mdフェーズ10・2節の2〜3)。
- `handle_stripe_webhook`: Stripe Webhook受信(HTTPSトリガー、
  `checkout.session.completed`)。`one_time_draft/{draft_id}`を`paid`に更新し、
  LLM生成を実行して結果を書き込み、完了メールを送信する(同フェーズ10・2節の
  5〜6、ttl-expiry-result-delivery-refund-design.mdフェーズ12・2〜3節の
  リトライ・返金処理を含む)。
- `get_result_page`: 結果ページ`/result/{draft_id}`表示(HTTPSトリガー)。
  `one_time_draft/{draft_id}`を読み込み、ステータスに応じて生成中/結果/期限切れ
  表示を返す(result-page-ttl-access-design.mdフェーズ14)。
- `submit_inquiry`: 問い合わせフォーム送信(HTTPSトリガー)。`inquiry/{inquiry_id}`
  を新規作成する(inquiry-handling-design.mdフェーズ15・2節)。

他4venture(kura-pasha・aircon-pasha・course-set-pasha・forklift-pasha)と異なり、
本ventureには`webhook.get_runtime_dependencies()`のような「空dictが未接続を表す」
パターンは無く、4関数とも常にInMemory実装(`InMemoryOneTimeDraftStore`・
`InMemoryInquiryStore`、いずれも未実装スタブ)を返す想定である(forklift-pasha
フェーズ158・1節と同じ整理)。

## 2. 切り替え条件(命名規則の横展開)

既出4venture(kura-pasha・aircon-pasha・course-set-pasha・forklift-pasha)と同じ
命名規則(`<venture-prefix>_FIRESTORE_ENABLED`)に揃え、本ventureでは
`EVENT_KOMIGUAI_PASHA_FIRESTORE_ENABLED`(値`"1"`で有効)とする。未設定時は常に
InMemory実装にフォールバックする安全側設計とし、承認前の誤接続を防ぐ
(`GOOGLE_CLOUD_PROJECT`はCloud Functions実行環境で常に自動設定されるため接続
準備完了の判定には使えない、という既出4venture共通の判断理由をそのまま踏襲)。

```python
import os

def _firestore_enabled() -> bool:
    return os.environ.get("EVENT_KOMIGUAI_PASHA_FIRESTORE_ENABLED") == "1"
```

Stripe API実接続・実メール送信手段の確定・本番LPドメイン確定はいずれも別軸
(それぞれ別の承認待ち項目、pending-approval.md参照)のため、本フラグは
Firestoreストア(`InMemoryOneTimeDraftStore`・`InMemoryInquiryStore`)の
切り替えのみを対象とし、`checkout_session_creator`・`email_sender`の接続先
切り替えは本設計の対象外のまま残す(forklift-pashaの整理と同じ)。

## 3. 各エントリポイントへの適用案

### 3.1. `submit_event_form`

`draft_store`(`one_time_draft`書き込み)のみをFirestore実装に差し替える。
`checkout_session_creator`(`MockCheckoutSessionCreator`)は実Stripe接続待ちの
ため対象外。

### 3.2. `handle_stripe_webhook`

`draft_store`をFirestore実装に差し替える(他4venture側Stripe webhookの
エントリポイントと同型)。`email_sender`は接続先未確定のため対象外。

### 3.3. `get_result_page`

`draft_store`(読み込みのみ)をFirestore実装に差し替える。

### 3.4. `submit_inquiry`

`inquiry_store`(書き込み)・`draft_store`(`draft_id`参照時の存在確認読み込み、
inquiry-handling-design.mdフェーズ15・1節の類型1〜2で必要)の両方をFirestore
実装に差し替える。

## 4. 未検証・残課題

- `_firestore_enabled()`・各`get_.*_runtime_dependencies()`の実コード化は、実
  `google-cloud-firestore`ライブラリの導入・本venture用Firestoreアダプタ設計
  (kura-pashaのworkshop-store-firestore-adapter-design.mdに相当する文書が本
  ventureにはまだ無い、`one_time_draft`・`inquiry`の2コレクション分が必要)と
  セットで行うのが安全なため、承認後の結合実装フェーズに持ち越す(本フェーズは
  コード変更を行わない)。
- cloud-monitoring-alert-policy-design.md(フェーズ62)1節で先取りして定義した
  ログベース指標名(`event_komiguai_pasha_firestore_runtime_dependency_
  construction_failure_count`)・フィルタ条件は、本節で確定した4関数
  (`submit_event_form`・`handle_stripe_webhook`・`get_result_page`・
  `submit_inquiry`)を`resource.labels.service_name`の対象として揃えればよく、
  追加の設計変更は不要であることを確認した(同ファイル0節・1節の「対象関数の
  最終的な個数は引き続き要確認」という残課題を本節により解消)。
- 実際のGCPプロジェクト作成・Firestoreデータベース作成・Stripeアカウント接続は
  アカウント作成・支払いが発生するためオーナー承認待ちの範囲(pending-approval.md
  参照)。今回は関数境界・切り替え設計の机上整理のみに留める。

## 5. 実クライアント構築失敗時の例外処理方針(フェーズ64)

4節の残課題のうち、`_firestore_enabled()`が真であるにもかかわらず実
Firestoreクライアント構築(`InMemoryOneTimeDraftStore`・`InMemoryInquiryStore`
相当のFirestoreアダプタ初期化)が例外を投げるケース(認証情報未設定・
サービスアカウント権限不足・一時的なネットワーク障害等)のハンドリング方針を、
kura-pasha・aircon-pasha・course-set-pasha・forklift-pashaの各ファイル6節
(kura-pashaはフェーズ263)で確立済みの方針を横展開して設計する。

### 5.1. 方針: 例外は握り潰さずそのまま伝播させる(InMemoryへの自動フォールバック禁止)

未設定時(フラグが`"1"`でない)は2節のとおりInMemory実装へ安全側フォールバックする
既定だが、フラグが明示的に`"1"`に設定された状態で実クライアント構築が失敗した場合に
InMemory実装へ自動的に切り替えることはしない。理由は既出4venture側と同じ2点に加え、
本venture固有の事情として以下を補足する。

- フラグ`"1"`はオーナー承認後の結合実装フェーズで意図的に設定される値であり、
  この状態での構築失敗は設定・権限上の不具合を意味する。これをInMemoryへ自動
  フォールバックすると、`submit_event_form`・`submit_inquiry`の書き込みが実際には
  永続化されずに処理自体は成功したように見えてしまう。
- 本venture固有の事情として、`handle_stripe_webhook`が`one_time_draft`を`paid`に
  更新する処理はアカウント登録なし単発決済モデル(one-time-checkout-no-account-
  design.mdフェーズ10)の唯一の決済完了記録経路であり、ここでInMememoryへ無言で
  フォールバックすると決済は完了しているのに結果ページ(`get_result_page`)が
  いつまでも`awaiting_payment`のままになる、または再実行時に二重のLLM生成・
  二重のメール送信(ttl-expiry-result-delivery-refund-design.mdフェーズ12の
  リトライ処理との不整合)を招くリスクが既出4venture以上に大きい(本venture以外は
  アカウント単位のストアのため、再接続後に状態を手動で復旧させる余地が相対的に
  大きいのに対し、本ventureは`draft_id`単位の使い切りレコードのため復旧の猶予が
  短い)。

### 5.2. 実装方針(擬似コード)

```python
import logging

logger = logging.getLogger(__name__)

def get_submit_event_form_runtime_dependencies() -> dict:
    if not _firestore_enabled():
        return {}
    try:
        client = firestore_sdk.Client()
        return {"draft_store": FirestoreOneTimeDraftStore(client)}
    except Exception:
        logger.exception(
            "EVENT_KOMIGUAI_PASHA_FIRESTORE_ENABLED=1 but Firestore client "
            "construction failed; re-raising instead of falling back "
            "to InMemory to avoid silently losing persistence."
        )
        raise
```

他3関数(`handle_stripe_webhook`・`get_result_page`・`submit_inquiry`)側の
`get_.*_runtime_dependencies()`も、3節で確定した対象ストア(`draft_store`・
`inquiry_store`)の組み合わせに応じて同じtry/except構造を適用する。

### 5.3. 例外伝播後の挙動(呼び出し元別)

- `handle_stripe_webhook`(Stripe Webhook、HTTPSトリガー): 例外が伝播すると
  5xxレスポンスを返し、Stripe側の再送(リトライ)に委ねる。既出4venture側の
  Stripe webhookエントリポイントと同じ整理。
- `submit_event_form`・`submit_inquiry`・`get_result_page`(いずれもエンド
  ユーザーのブラウザから直接呼ばれるHTTPSトリガー): Stripe・LINEのような
  送信元側の自動再送機構を持たないため、例外伝播時は5xxがそのままブラウザに
  返り、申込者・問い合わせ者が自力で再試行する前提になる(既出4venture側は
  全エントリポイントがStripe/LINEのwebhookのため本節のような「自動再送が
  効かないエントリポイントがある」という整理は本venture固有の論点)。この
  差異がフロントエンド側のエラーメッセージ・再試行導線の設計に影響するかは
  次回候補とする(web-form-ui-design.md相当の文書が本ventureにまだ無いため、
  本フェーズでは影響範囲の指摘に留める)。

### 5.4. 未検証・残課題

- 本フェーズはログ・re-raiseという方針の決定のみで、`.py`ファイルへの実装反映は
  4節同様、実`google-cloud-firestore`ライブラリ導入とセットで行う結合実装フェーズに
  持ち越す。
- 5.3節で指摘した「自動再送が効かないエントリポイントでのエラー表示・再試行導線」の
  設計(web-form-ui-design.md相当文書の新規作成を含む)は次回候補とする。

最終更新: 2026-10-26 22:00 UTC(フェーズ64: フェーズ63次回候補(1)「実クライアント
構築失敗時の例外処理方針の本venture側への横展開」に対応し、既出4venture
(kura-pasha・aircon-pasha・course-set-pasha・forklift-pasha)の各ファイル6節で
確立済みの「ログ+re-raise、InMemory自動フォールバック禁止」方針を5節として
新規設計した。本venture固有の`handle_stripe_webhook`(アカウント登録なし単発
決済モデルの唯一の決済完了記録経路)という事情、および`submit_event_form`・
`submit_inquiry`・`get_result_page`がStripe/LINEのような自動再送機構を持たない
エンドユーザー直接呼び出しのHTTPSトリガーである点を既出4venture側との差異として
整理した。コード変更なし、回帰確認として`python3 -m unittest discover -s
prototype -p "test_*.py"`(50件、変更なし)・`python3
schema/validate_test_cases.py`(22件、変更なし)を実行しいずれも変更なしで
パスすることを確認した(回帰なし)。承認が必要なアクション(支払い・アカウント
作成・外部公開・送信等)は今回発生していないためpending-approval.mdへの
追記なし。次回候補: (1)自動再送が効かないエントリポイントのエラー表示・再試行
導線の設計(web-form-ui-design.md相当文書の新規作成)、(2)承認待ち事項(候補1
〈奈良NEVER LAND〉への連絡等)がオーナーから承認された場合はその着手、(3)他
venture・アイデア領域の前進)
