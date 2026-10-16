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

最終更新: 2026-10-16 12:00 UTC(フェーズ続き325: forklift-pashaフェーズ158の
次回候補を受け、`LINE_RESERVATION_AI_FIRESTORE_ENABLED`命名規則の切り替え
設計を本ventureの3つのruntime_dependencies関数に適用。コード変更なし)
