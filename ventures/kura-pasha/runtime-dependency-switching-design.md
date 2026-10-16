# 実Firestore承認後のランタイム依存切り替え設計(フェーズ238)

workshop-store-firestore-adapter-design.md(基盤グループ+7グループ、全8節)・
firestore-provider-adapter-design.md・invite-code-store-firestore-adapter-design.md・
linking-code-store-firestore-adapter-design.mdは、それぞれのProtocolに対応する
`FirestoreXxxStore`/`FirestoreUserProfileProvider`クラスの設計(メソッド単位の
読み書き方針)までは完了しているが、実際にCloud Functionsのエントリポイントが
これらのクラスを「いつ・どう」選択するかは、各ファイルの
`get_xxx_runtime_dependencies()`側にまだ書かれていない(現状はInMemory実装を
常に返すのみ)。本ドキュメントはフェーズ228の次回候補(2)「テストダブル切り替え
方式の設計」を引き継ぎ、承認後すぐに適用できる切り替えロジックの草案を先行して
詰める。コード変更・外部アカウント作成のいずれも行わない。

## 1. 現状の棚卸し

本venture には`get_xxx_runtime_dependencies()`系の関数が2つ存在し、承認前の
現状では挙動が異なる。

- `cloud_function_run_daily_workshop_checks.get_daily_workshop_checks_runtime_
  dependencies()`: `workshop_store`・`user_profile_store`を**常に非None**
  (`InMemoryWorkshopStore()`等)で返す。`daily_scheduler.run_daily_workshop_
  checks()`側がNoneを想定していないため。
- `cloud_function_webhook.get_runtime_dependencies()`: **空dict**(`{}`)を返す。
  `dispatch_webhook_events()`側が各依存引数ごとに「Noneなら当該処理をスキップ」
  という安全側フォールバックを個別に持つため。

この2パターンは矛盾ではなく、呼び出し先がNoneを許容するかどうかに応じた合理的な
分岐である。したがって切り替え方式も、この2パターンそれぞれに「InMemoreyの既定値
を実クライアントに差し替える条件分岐」を追加する形で設計する(呼び出し先の
None許容方針自体は変更しない)。

## 2. 切り替え条件

実GCPプロジェクトの有無を判定する専用の環境変数を用意するのではなく、Firebase
Admin SDK/`google-cloud-firestore`が標準で参照する`GOOGLE_CLOUD_PROJECT`(Cloud
Functions実行環境では常に自動設定される)の存在だけでは「Firestoreへの接続準備が
整っているか」を判定できない(Cloud Functions自体は承認前でもデプロイし得るため、
変数の有無とオーナー承認は独立した軸)。そこで、承認後の初回デプロイ時にオーナー
(または代理の設定者)が明示的に設定する専用フラグ`KURA_PASHA_FIRESTORE_ENABLED`
(値`"1"`で有効)を切り替え条件とする。未設定時は常にInMemory実装にフォールバック
する安全側設計とし、専用フラグが無いままの誤接続(承認前の暴発)を防ぐ。

```python
import os

def _firestore_enabled() -> bool:
    return os.environ.get("KURA_PASHA_FIRESTORE_ENABLED") == "1"
```

## 3. 各エントリポイントへの適用案

### 3.1. `get_daily_workshop_checks_runtime_dependencies()`

```python
def get_daily_workshop_checks_runtime_dependencies() -> dict:
    if _firestore_enabled():
        from google.cloud import firestore as firestore_sdk

        client = firestore_sdk.Client()
        return {
            "workshop_store": FirestoreWorkshopStore(client),
            "user_profile_store": FirestoreUserProfileProvider(client),
            "push_client": LinePushClient(...),  # LINE接続は別軸、本設計の対象外
            "owner_line_user_id": OWNER_LINE_USER_ID_PLACEHOLDER,
        }
    return {
        "workshop_store": InMemoryWorkshopStore(),
        "user_profile_store": InMemoryUserProfileStore(),
        "push_client": InMemoryLinePushClient(),
        "owner_line_user_id": OWNER_LINE_USER_ID_PLACEHOLDER,
    }
```

`FirestoreWorkshopStore`・`FirestoreUserProfileProvider`は設計済みの擬似コード
(workshop-store-firestore-adapter-design.md各節・firestore-provider-adapter-
design.md 2節)をそのまま`.py`化する前提で、本設計では未実装のまま参照のみとする。

### 3.2. `get_runtime_dependencies()`(webhook)

空dict(`{}`)が「未接続」を表す既存の意味づけを維持するため、`_firestore_
enabled()`が偽の場合は現状通り`{}`を返し、真の場合のみFirestore関連キー
(`user_profile_store`・`workshop_store`・`usage_counter_store`・`linking_store`・
`invite_store`)を実クライアントで埋める。LLM API・LINE Messaging API接続は
別軸(それぞれ別の承認待ち項目)のため、本設計はFirestore関連キーのみを対象とし、
他キーは引き続き`{}`(未接続)のままで良い。

```python
def get_runtime_dependencies() -> dict:
    if not _firestore_enabled():
        return {}
    client = firestore_sdk.Client()
    return {
        "user_profile_store": FirestoreUserProfileProvider(client),
        "workshop_store": FirestoreWorkshopStore(client),
        "usage_counter_store": FirestoreUsageCounterProvider(client),
        "linking_store": FirestoreLinkingCodeStore(client),
        "invite_store": FirestoreInviteCodeStore(client),
    }
```

## 4. 未検証・残課題

- `_firestore_enabled()`・各`get_xxx_runtime_dependencies()`の実コード化
  (`.py`ファイルへの反映)自体は、実`google-cloud-firestore`ライブラリの導入・
  実Firestoreプロジェクトへの接続確認とセットで行うのが安全なため、承認後の
  結合実装フェーズに持ち越す(本フェーズはコード変更を行わない)。
- `KURA_PASHA_FIRESTORE_ENABLED`という名前・値の形式は他venture(aircon-pasha・
  course-set-pasha・line-reservation-ai・forklift-pasha)がまだ同種の設計を
  持たないため、横展開する場合は`<venture-prefix>_FIRESTORE_ENABLED`の命名規則
  として揃えられる可能性がある(次回候補として記録、他venture側の次回候補としても
  残す)。
- フラグが`"1"`のまま実クライアント構築(`firestore_sdk.Client()`)が例外を
  投げるケース(認証情報未設定等)のハンドリングは未設計。現時点では承認時点で
  認証情報も合わせて設定される前提のため、本フェーズでは例外処理を追加しない
  (発生したら結合実装フェーズで個別に対応する)。

最終更新: 2026-10-16 (フェーズ238)
