# 実Firestore/実LINE承認後のランタイム依存切り替え設計(フェーズ319)

kura-pashaフェーズ238(runtime-dependency-switching-design.md)の次回候補(2)
「`KURA_PASHA_FIRESTORE_ENABLED`という名前・値の形式を他venture
(aircon-pasha・course-set-pasha・line-reservation-ai・forklift-pasha)へ
`<venture-prefix>_FIRESTORE_ENABLED`の命名規則として横展開する」を受け、
本venture(aircon-pasha)に最初に適用する。コード変更・外部アカウント作成の
いずれも行わない。

## 1. 現状の棚卸し

本ventureには`get_.*_runtime_dependencies()`系の関数が5つ存在し、いずれも
現状はInMemory実装(または空dict)を常に返す。

- `cloud_function_webhook.get_runtime_dependencies()`: 空dict(`{}`)を返す。
  `dispatch_webhook_events()`側が各依存引数ごとに「Noneなら当該処理を
  スキップ」という安全側フォールバックを個別に持つため。
- `cloud_function_run_daily_checks.get_daily_checks_runtime_dependencies()`:
  `profile_store`・`push_client`を常に非None(InMemory実装)で返す。
- `cloud_function_application_form_submission.get_application_form_submission_
  runtime_dependencies()`: `store`・`rng`を常に非None(InMemory実装)で返す。
- `cloud_function_send_deletion_candidate_final_confirmations.get_deletion_
  candidate_final_confirmation_runtime_dependencies()`: `store`・
  `push_client`を常に非None(InMemory実装)で返す。
- `stripe_webhook.get_stripe_runtime_dependencies()`: `store`以下複数キーを
  常に非None(InMemory実装、フェーズ305以降は`user_profile_store`と同一
  インスタンスを使い回す構成)で返す。

kura-pashaの棚卸しと同様、この違いは呼び出し先がNoneを許容するかどうかに
応じた合理的な分岐であり矛盾ではない。切り替え方式も、この2パターン
(「空dictが未接続を表す」/「常に非Noneを返す」)それぞれに条件分岐を
追加する形で設計する(呼び出し先のNone許容方針自体は変更しない)。

## 2. 切り替え条件(命名規則の横展開)

kura-pashaの`KURA_PASHA_FIRESTORE_ENABLED`と同じ設計思想を採用し、
`<venture-prefix>_FIRESTORE_ENABLED`の命名規則に揃える。本ventureでは
`AIRCON_PASHA_FIRESTORE_ENABLED`(値`"1"`で有効)とする。未設定時は常に
InMemory実装にフォールバックする安全側設計とし、承認前の誤接続を防ぐ
(kura-pashaフェーズ238と同一の判断理由: `GOOGLE_CLOUD_PROJECT`はCloud
Functions実行環境で常に自動設定されるため接続準備完了の判定には使えない)。

```python
import os

def _firestore_enabled() -> bool:
    return os.environ.get("AIRCON_PASHA_FIRESTORE_ENABLED") == "1"
```

LINE Messaging API・Stripe API接続の有効化は別軸(それぞれ別の承認待ち
項目、pending-approval.md参照)のため、本フラグはFirestore関連の
ストア/プロバイダ切り替えのみを対象とし、`push_client`・Stripe関連の
依存は本設計の対象外のまま残す(kura-pashaフェーズ238の整理と同じ)。

## 3. 各エントリポイントへの適用案

### 3.1. `get_runtime_dependencies()`(webhook)

空dict(`{}`)が「未接続」を表す既存の意味づけを維持するため、
`_firestore_enabled()`が偽の場合は現状通り`{}`を返し、真の場合のみ
Firestore関連キーを実クライアントで埋める(`push_client`・`llm_call`等
LINE/LLM軸のキーは引き続き`{}`のままで良い、または真の場合でも未接続分は
省略する)。

### 3.2. `get_daily_checks_runtime_dependencies()`

```python
def get_daily_checks_runtime_dependencies() -> dict:
    if _firestore_enabled():
        from google.cloud import firestore as firestore_sdk
        client = firestore_sdk.Client()
        return {
            "profile_store": FirestoreUserProfileStore(client),
            "push_client": InMemoryLinePushClient(),  # LINE接続は別軸
        }
    return {
        "profile_store": InMemoryUserProfileStore(),
        "push_client": InMemoryLinePushClient(),
    }
```

`FirestoreUserProfileStore`は未設計(本ventureにはkura-pashaの
workshop-store-firestore-adapter-design.mdに相当するFirestoreアダプタ設計
文書がまだ存在しない)。本フェーズでは参照のみとし、実コード化・
アダプタ自体の設計は結合実装フェーズに持ち越す。

### 3.3. `get_application_form_submission_runtime_dependencies()`・
`get_deletion_candidate_final_confirmation_runtime_dependencies()`

いずれも3.2と同形の条件分岐(`store`をFirestore実装に差し替え、`rng`・
`push_client`等Firestore以外のキーはそのまま)を適用する想定。

### 3.4. `get_stripe_runtime_dependencies()`

フェーズ305で`store`=`user_profile_store`の同一インスタンス共有構成に
整理済みのため、`_firestore_enabled()`が真の場合は`FirestoreUserProfileStore`
一つを生成し、duck typingで満たす複数キー(`store`・`user_profile_store`・
`payment_store`・`plan_store`・`blocked_but_billing_store`)すべてに同一
インスタンスを渡す構成を維持する(Stripe API自体の実接続は別軸、本設計の
対象外)。

## 4. 未検証・残課題

- `_firestore_enabled()`・各`get_.*_runtime_dependencies()`の実コード化は、
  実`google-cloud-firestore`ライブラリの導入・本venture用Firestoreアダプタ
  設計(kura-pashaのworkshop-store-firestore-adapter-design.mdに相当する
  文書が本ventureにはまだ無い)とセットで行うのが安全なため、承認後の
  結合実装フェーズに持ち越す(本フェーズはコード変更を行わない)。
- 残る横展開先(course-set-pasha・line-reservation-ai・forklift-pasha)は
  次回候補として記録する。forklift-pashaはLINE非依存・Webフォーム構成の
  ため、Firestore接続自体の有無も含めて個別に確認が必要。
- フラグが`"1"`のまま実クライアント構築が例外を投げるケースのハンドリングは
  未設計(kura-pashaフェーズ238と同じ理由で本フェーズでは対応しない)。

最終更新: 2026-10-16 (フェーズ319)
