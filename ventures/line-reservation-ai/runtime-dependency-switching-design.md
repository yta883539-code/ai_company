# 実Firestore承認後のランタイム依存切り替え設計(フェーズ続き325)

forklift-pashaフェーズ158(runtime-dependency-switching-design.md)の次回候補
「残る横展開先line-reservation-aiへの同パターン適用」を受け、本venture
(line-reservation-ai)に横展開する。コード変更・外部アカウント作成のいずれも
行わない(ドキュメントのみの設計フェーズ)。

## 1. 現状の棚卸し

本ventureには`get_.*_runtime_dependencies()`系の関数が3つ存在し、いずれも
現状は呼び出しごとに新しいInMemory実装を組み立てて返す(他venture共通の
「空dictが未接続を表す」パターンは本ventureには存在しない)。

- `checkout_session.get_checkout_runtime_dependencies()`: `store`
  (`InMemoryStoreProfileStore()`)・`verify_id_token`
  (`_verify_id_token_not_implemented`、LIFFアプリ実登録待ちの意図的な
  `NotImplementedError`送出スタブ)・`line_return_link`
  (`build_line_return_link(DEFAULT_LINE_BASIC_ID)`、LINE公式アカウント
  Basic ID確定待ちのプレースホルダ値)を返す。
- `conversation_event_processor_assembly.get_process_conversation_event_
  runtime_dependencies()`: `store`(`InMemoryStoreSettingsStore()`)・
  `push_client`(`InMemoryLinePushClient()`)・`llm_call`
  (`_llm_call_not_implemented`、LLM APIキー発行・課金承認待ちの意図的な
  `NotImplementedError`送出スタブ)を返す。
- `stripe_webhook_entry_point.get_stripe_webhook_runtime_dependencies()`:
  `dunning_store`・`subscription_store`・`cancellation_store`・
  `store_profile_store`・`event_id_store`(いずれも`InMemory*`実装)を返す。
  `push_client`・`portal_link_provider`は意図的に返り値へ含めず(常に`None`)、
  各ハンドラ側の「`None`の場合は処理をスキップして200を返す」既存の安全側
  フォールバックに委ねている。

他3venture(kura-pasha・aircon-pasha・course-set-pasha)・forklift-pashaで
確立した「`_firestore_enabled()`が真の場合にFirestore版実装一式へ差し替える」
方式がそのまま適用できる構造である。

## 2. 切り替え条件(命名規則の横展開)

既出4ventureと同じ命名規則(`<venture-prefix>_FIRESTORE_ENABLED`)に揃え、
本ventureでは`LINE_RESERVATION_AI_FIRESTORE_ENABLED`(値`"1"`で有効)とする。
未設定時は常にInMemory実装にフォールバックする安全側設計とし、承認前の
誤接続を防ぐ(`GOOGLE_CLOUD_PROJECT`はCloud Functions実行環境で常に自動
設定されるため接続準備完了の判定には使えない、という既出4venture共通の
判断理由をそのまま踏襲)。

```python
import os

def _firestore_enabled() -> bool:
    return os.environ.get("LINE_RESERVATION_AI_FIRESTORE_ENABLED") == "1"
```

`verify_id_token`(LIFFアプリ実登録待ち)・`llm_call`(LLM API接続待ち)・
`line_return_link`(LINE公式アカウントBasic ID確定待ち)・`push_client`/
`portal_link_provider`(実LINE Messaging API・Stripe Billing Portal接続待ち)
はいずれも別軸の承認待ち項目(それぞれpending-approval.md参照)のため、
本フラグは`InMemoryStoreProfileStore`・`InMemoryStoreSettingsStore`・
`InMemoryLinePushClient`(※`push_client`自体は3節参照)・stripe_webhook側の
5ストアといったFirestoreストアの切り替えのみを対象とし、これら他の依存の
接続先切り替えは本設計の対象外のまま残す(forklift-pashaの整理と同じ)。

## 3. 各エントリポイントへの適用案

### 3.1. `get_checkout_runtime_dependencies()`

`store`(`InMemoryStoreProfileStore`)のみをFirestore実装に差し替える。
`verify_id_token`・`line_return_link`はいずれもLIFF・LINE公式アカウント
接続待ちのため対象外。

### 3.2. `get_process_conversation_event_runtime_dependencies()`

`store`(`InMemoryStoreSettingsStore`)をFirestore実装に差し替える。
`push_client`(`InMemoryLinePushClient`)は実LINE Messaging API接続自体が
別軸の承認待ちのため、本フラグでの切り替え対象には含めない(フラグが
真でも実LINE接続が別途完了するまではInMemoryのまま、course-set-pasha等の
`push_client`相当の扱いと同じ整理)。`llm_call`も同様に対象外。

### 3.3. `get_stripe_webhook_runtime_dependencies()`

`dunning_store`・`subscription_store`・`cancellation_store`・
`store_profile_store`・`event_id_store`の5ストアをいずれもFirestore実装に
差し替える(他venture側の`store`単体の切り替えと異なり、本ventureはStripe
Webhook側の状態を5つのストアに分割している点が構造上の違いだが、切り替え
方式自体は同型で足りる)。`push_client`・`portal_link_provider`は元々
`None`のまま返す設計のため、本フラグの対象外(接続後も別途LINE/Stripe
Billing Portal接続の承認を待つ)。

## 4. 未検証・残課題

- `_firestore_enabled()`・各`get_.*_runtime_dependencies()`の実コード化は、
  実`google-cloud-firestore`ライブラリの導入・本venture用Firestoreアダプタ
  設計(kura-pashaのworkshop-store-firestore-adapter-design.mdに相当する
  文書が本ventureにはまだ無い)とセットで行うのが安全なため、承認後の
  結合実装フェーズに持ち越す(本フェーズはコード変更を行わない)。
- 本フェーズで`<venture-prefix>_FIRESTORE_ENABLED`命名規則の横展開は
  5venture(kura-pasha・aircon-pasha・course-set-pasha・forklift-pasha・
  line-reservation-ai)すべてに完了した。次回候補は、承認後の結合実装
  フェーズでの実コード化、またはFirestoreアダプタ設計自体の各venture
  横展開の要否検討。
- `checkout_session`・`conversation_event_processor_assembly`・
  `stripe_webhook_entry_point`は別プロセス(別Cloud Function)として
  起動されるため、`store_profile_store`等の同一コレクションを指す複数の
  Firestoreクライアント初期化が重複しないか(接続コスト・コネクション
  プーリングの観点)は実装時の確認事項として残る(新規の論点、他venture
  では未検討)。
- フラグが`"1"`のまま実クライアント構築が例外を投げるケースのハンドリングは
  未設計(他4venture共通の理由により本フェーズでは対応しない)。

## 5. 実クライアント構築失敗時の例外処理方針(フェーズ続き347)

kura-pashaフェーズ263(runtime-dependency-switching-design.md 6節)の次回候補(3)
「ログ+re-raise、InMemory自動フォールバック禁止方針の他4venture側への横展開」を受け、
aircon-pasha(フェーズ343)・course-set-pasha(フェーズ333)・forklift-pasha(フェーズ191)
に続き、残っていた本venture(line-reservation-ai)に最後に適用する。4節の残課題のうち、
`_firestore_enabled()`が真であるにもかかわらず各`get_.*_runtime_dependencies()`内の
実クライアント構築(`firestore_sdk.Client()`・各Firestoreアダプタの初期化)が例外を
投げるケースのハンドリング方針を設計する。これで5venture全てへの横展開が完了する。

### 5.1. 方針: 例外は握り潰さずそのまま伝播させる(InMemoryへの自動フォールバック禁止)

理由は他4venture(kura-pashaフェーズ263・aircon-pashaフェーズ343等)と同一であり、
本venture固有の事情を補足すると以下の2点となる。

- フラグ`"1"`はオーナー承認後の結合実装フェーズで意図的に設定される値であり、この状態
  での構築失敗は「実Firestoreへの接続が必要な場面で接続できていない」という設定・権限
  上の不具合を意味する。InMemoryへ自動フォールバックすると、`conversation_event_
  processor_assembly`側の予約枠状態(`store`)が永続化されないまま「成功した」ように
  見え、二重予約防止(double-booking-prevention.md)の前提が崩れるリスクがある。
  `stripe_webhook_entry_point`側も同様に、dunning_store・subscription_store等5ストアが
  InMemoryへ自動フォールバックするとstripe-event-idempotency-design.md前提(冪等性
  チェックがInMemory上のみで行われ再起動ごとにリセットされる)との不整合を招く。
- 本venture(line-reservation-ai)が5venture中で最後の横展開対象であり、本フェーズを
  もって`<venture-prefix>_FIRESTORE_ENABLED`命名規則・ログ+re-raise方針のいずれも
  全venture共通の一貫した設計になる。

### 5.2. 実装方針(擬似コード)

3.1節の`get_checkout_runtime_dependencies()`を例に、Firestore関連キー(`store`)の
構築のみをtry/exceptで囲み、ログを出した上で例外を再raiseする(`verify_id_token`・
`line_return_link`は元々Firestore非依存のため対象外)。

```python
import logging

logger = logging.getLogger(__name__)

def get_checkout_runtime_dependencies() -> dict:
    if not _firestore_enabled():
        return {
            "store": InMemoryStoreProfileStore(),
            "verify_id_token": _verify_id_token_not_implemented,
            "line_return_link": build_line_return_link(DEFAULT_LINE_BASIC_ID),
        }
    try:
        from google.cloud import firestore as firestore_sdk
        client = firestore_sdk.Client()
        store = FirestoreStoreProfileStore(client)
    except Exception:
        logger.exception(
            "LINE_RESERVATION_AI_FIRESTORE_ENABLED=1 but Firestore client "
            "construction failed; re-raising instead of falling back "
            "to InMemory to avoid silently losing persistence."
        )
        raise
    return {
        "store": store,
        "verify_id_token": _verify_id_token_not_implemented,
        "line_return_link": build_line_return_link(DEFAULT_LINE_BASIC_ID),
    }
```

`get_process_conversation_event_runtime_dependencies()`(`store`のみ対象、`push_client`・
`llm_call`は対象外)・`get_stripe_webhook_runtime_dependencies()`(5ストア全てが対象、
`push_client`・`portal_link_provider`は元々`None`のため対象外)も同様に、Firestore
関連キーの構築のみをtry/exceptで囲み例外を再raiseする。

### 5.3. 例外伝播後の挙動(呼び出し元別)

- `checkout_session`(Stripe Checkout開始用HTTPエントリポイント、checkout-initiation-
  flow-design.md): 例外伝播によりCloud Functions実行環境が5xxを返す。利用者(LIFF
  アプリ側)は決済開始操作の失敗として再試行する想定で、新たな設計変更は不要。
- `conversation_event_processor_assembly`(LINE Messaging API Webhook受信、HTTP
  トリガー): webhook-async-processing-design.mdの非同期処理方針上、5xx応答はLINE
  Platform側の再送に委ねられる前提と整合する(他venture側webhookと同型)。
- `stripe_webhook_entry_point`(Stripe Webhook、HTTPトリガー): stripe-webhook-http-
  entry-point-design.mdは5xx応答時にStripe側の再送(リトライ)に委ねる前提を既に
  持っており、本方針と整合する。

### 5.4. 未検証・残課題

- 本フェーズはログ・re-raiseという方針の決定のみで、`.py`ファイルへの実装反映は
  実`google-cloud-firestore`ライブラリ導入とセットで行う結合実装フェーズに持ち越す。
- 本venture固有のcloud-monitoring-alert-policy-design.md相当の文書は未作成であり
  (aircon-pasha・course-set-pashaには存在、kura-pashaフェーズ264で確認済み)、本例外の
  ログをアラート対象に含めるかどうかは当該文書の新規作成とセットで検討する次回候補と
  する。
- これで5venture(kura-pasha・aircon-pasha・course-set-pasha・forklift-pasha・
  line-reservation-ai)全てへの「ログ+re-raise、InMemory自動フォールバック禁止」方針の
  横展開が完了した。

最終更新: 2026-10-25 22:00 UTC(フェーズ続き347: kura-pashaフェーズ263の横展開として、
本venture固有の3エントリポイント〈checkout_session・conversation_event_processor_
assembly・stripe_webhook_entry_point〉向けに5節を新規設計。これで5venture全てへの
横展開が完了。コード変更なし、回帰確認は本venture側README.md参照)
