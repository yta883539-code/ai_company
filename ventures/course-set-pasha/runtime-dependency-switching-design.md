# 実Firestore承認後のランタイム依存切り替え設計(フェーズ297)

aircon-pashaフェーズ319(runtime-dependency-switching-design.md)の次回候補
「残る横展開先(course-set-pasha・line-reservation-ai・forklift-pasha)」を
受け、本venture(course-set-pasha)に横展開する。コード変更・外部アカウント
作成のいずれも行わない(ドキュメントのみの設計フェーズ)。

## 1. 現状の棚卸し

本ventureには`get_.*_runtime_dependencies()`系の関数が8つ存在し、いずれも
現状はInMemory実装(または空dict)を常に返す。aircon-pasha(5つ)より多い
のは、Stripe定期購入のライフサイクル通知系(トライアル終了・支払い失敗・
支払い停止オーナー通知)が個別のCloud Functionに分かれているため。

- `cloud_function_webhook.get_runtime_dependencies()`: 空dict(`{}`)を返す。
  `dispatch_webhook_events()`側がNoneを許容する安全側フォールバックを持つ
  ため(aircon-pashaと同型)。
- `checkout_session.get_checkout_runtime_dependencies()`: `user_profile_store`・
  `verify_id_token`を常に非None(InMemory実装・未実装スタブ)で返す。
- `portal_session.get_portal_runtime_dependencies()`: `checkout_session`と
  対称構成で`user_profile_store`・`verify_id_token`を常に非Noneで返す。
- `stripe_webhook.get_stripe_runtime_dependencies()`: `store`・
  `user_profile_store`・`resolve_user_id`・`usage_counter`等、複数キーを
  いずれもNoneを許容しない必須引数として常に非Noneで返す。
- `cloud_function_application_form_submission.get_application_form_
  submission_runtime_dependencies()`: `store`・`rng`を常に非Noneで返す。
- `cloud_function_send_deletion_candidate_final_confirmations.get_deletion_
  candidate_final_confirmation_runtime_dependencies()`: `store`・
  `push_client`を常に非Noneで返す。
- `cloud_function_send_trial_end_notifications.get_trial_end_notification_
  runtime_dependencies()`: `usage_counter`等を常に非Noneで返す。
- `cloud_function_send_payment_failure_reminders.get_payment_failure_
  reminder_runtime_dependencies()`: `usage_counter`等を常に非Noneで返す
  (trial_end版と対称)。
- `cloud_function_send_payment_suspension_owner_notifications.get_payment_
  suspension_owner_notification_runtime_dependencies()`: 同上(reminders版
  と対称)。

aircon-pasha・kura-pashaの棚卸しと同様、この違いは呼び出し先がNoneを
許容するかどうかに応じた合理的な分岐であり矛盾ではない。切り替え方式も
同じ2パターン(「空dictが未接続を表す」/「常に非Noneを返す」)それぞれに
条件分岐を追加する形で設計する(呼び出し先のNone許容方針自体は変更しない)。

## 2. 切り替え条件(命名規則の横展開)

kura-pashaの`KURA_PASHA_FIRESTORE_ENABLED`・aircon-pashaの
`AIRCON_PASHA_FIRESTORE_ENABLED`と同じ命名規則
(`<venture-prefix>_FIRESTORE_ENABLED`)に揃え、本ventureでは
`COURSE_SET_PASHA_FIRESTORE_ENABLED`(値`"1"`で有効)とする。未設定時は
常にInMemory実装にフォールバックする安全側設計とし、承認前の誤接続を
防ぐ(`GOOGLE_CLOUD_PROJECT`はCloud Functions実行環境で常に自動設定される
ため接続準備完了の判定には使えない、という既出2venture共通の判断理由を
そのまま踏襲)。

```python
import os

def _firestore_enabled() -> bool:
    return os.environ.get("COURSE_SET_PASHA_FIRESTORE_ENABLED") == "1"
```

LIFFアプリ実登録・Stripe API実接続は別軸(それぞれ別の承認待ち項目、
pending-approval.md参照)のため、本フラグはFirestore関連のストア切り替え
のみを対象とし、`verify_id_token`・Stripe関連の依存は本設計の対象外のまま
残す(aircon-pashaフェーズ319の整理と同じ)。

## 3. 各エントリポイントへの適用案

### 3.1. `get_runtime_dependencies()`(webhook)

空dict(`{}`)が「未接続」を表す既存の意味づけを維持するため、
`_firestore_enabled()`が偽の場合は現状通り`{}`を返し、真の場合のみ
Firestore版実装を含むdictを返す想定(本ventureにはまだFirestoreアダプタ
設計文書が存在しないため、本フェーズでは参照のみ)。

### 3.2. `get_checkout_runtime_dependencies()`・`get_portal_runtime_dependencies()`

いずれも`user_profile_store`のみをFirestore実装に差し替える対称構成
(`verify_id_token`はLIFFアプリ実登録待ちのため対象外)。checkout側・
portal側は別プロセス(別Cloud Function)のため、Firestore接続後は両者が
同一Firestoreコレクションを共有することで、現状の既知の限界(プロセスを
またいだstripe_customer_id引き継ぎの欠落)が解消される見込み(1節記載の
既知の限界の解消条件として記録)。

### 3.3. `get_stripe_runtime_dependencies()`

複数キー(`store`・`user_profile_store`・`resolve_user_id`の生成元・
`usage_counter`)がNoneを許容しない必須引数のため、`_firestore_enabled()`
が真の場合はFirestore版実装一式を生成し全キーに配線する構成とする
(aircon-pashaフェーズ319 3.4節と同型の方針)。

### 3.4. ライフサイクル通知系4つ

`get_application_form_submission_runtime_dependencies()`・
`get_deletion_candidate_final_confirmation_runtime_dependencies()`・
`get_trial_end_notification_runtime_dependencies()`・
`get_payment_failure_reminder_runtime_dependencies()`・
`get_payment_suspension_owner_notification_runtime_dependencies()`は
いずれも同形の条件分岐(`store`/`usage_counter`をFirestore実装に差し替え、
Firestore以外のキーはそのまま)を適用する想定。5関数とも対称構成である
ため、設計自体は1パターンで足りる。

## 4. 未検証・残課題

- `_firestore_enabled()`・各`get_.*_runtime_dependencies()`の実コード化は、
  実`google-cloud-firestore`ライブラリの導入・本venture用Firestoreアダプタ
  設計(kura-pashaのworkshop-store-firestore-adapter-design.mdに相当する
  文書が本ventureにはまだ無い)とセットで行うのが安全なため、承認後の
  結合実装フェーズに持ち越す(本フェーズはコード変更を行わない)。
- 残る横展開先(line-reservation-ai・forklift-pasha)は次回候補として
  記録する。forklift-pashaはLINE非依存・Webフォーム構成のため、Firestore
  接続自体の有無も含めて個別に確認が必要(aircon-pashaフェーズ319の指摘を
  引き続き踏襲)。
- フラグが`"1"`のまま実クライアント構築が例外を投げるケースのハンドリングは、
  5節のとおり対応した。

## 5. 実クライアント構築失敗時の例外処理方針(フェーズ333)

kura-pashaフェーズ263(runtime-dependency-switching-design.md 6節)・
aircon-pashaフェーズ343(同5節)の次回候補「残る2venture
(course-set-pasha・forklift-pasha・line-reservation-ai)側の同ファイル4節への
横展開」を受け、本venture(course-set-pasha)に適用する。4節の残課題のうち、
`_firestore_enabled()`が真であるにもかかわらず各`get_.*_runtime_dependencies()`内の
実クライアント構築(`firestore_sdk.Client()`・各Firestoreアダプタの初期化)が
例外を投げるケース(認証情報未設定・サービスアカウント権限不足・一時的な
ネットワーク障害等)のハンドリング方針を設計する。

### 5.1. 方針: 例外は握り潰さずそのまま伝播させる(InMemoryへの自動フォールバック禁止)

未設定時(フラグが`"1"`でない)は1節のとおりInMemory実装へ安全側フォールバックする
既定だが、フラグが明示的に`"1"`に設定された状態で実クライアント構築が失敗した場合に
InMemory実装へ自動的に切り替えることはしない。理由はkura-pashaフェーズ263・
aircon-pashaフェーズ343と同一であり、本venture固有の事情を補足すると以下の2点となる。

- フラグ`"1"`はオーナー承認後の結合実装フェーズで意図的に設定される値であり、この
  状態での構築失敗は「実Firestoreへの接続が必要な場面で接続できていない」という
  設定・権限上の不具合を意味する。InMemoryへ自動フォールバックすると、checkout・
  portal・Stripe webhook・申込フォーム・各ライフサイクル通知Cloud Functionのいずれも
  「成功した」ように見えながら実際には永続化されない事態となり、顧客データの消失・
  本venture固有のリスク(3.2節記載のとおりcheckout側・portal側が別プロセスで
  Firestoreコレクションを共有する構成であるため、片方だけがInMemoryへフォール
  バックするとstripe_customer_id引き継ぎが静かに壊れ、1節記載の既知の限界が
  「解消されたはず」の後で再発する)を招くリスクがある。
- kura-pasha・aircon-pasha側で確認済みの通り、本venture(course-set-pasha)の同
  ファイル4節も同一の残課題を抱えており、残る2venture(forklift-pasha・
  line-reservation-ai)への今後の横展開に向けて「フラグON時は失敗を隠さず表面化
  させる」という一貫した方針を揃えておく必要がある。

### 5.2. 実装方針(擬似コード)

3.2節の`get_checkout_runtime_dependencies()`を例に、try/exceptでログを出した上で
例外を再raiseする形を取る(呼び出し先のNone許容方針自体は変更しない)。

```python
import logging

logger = logging.getLogger(__name__)

def get_checkout_runtime_dependencies() -> dict:
    if not _firestore_enabled():
        return {
            "user_profile_store": InMemoryUserProfileStore(),
            "verify_id_token": _stub_verify_id_token,
        }
    try:
        from google.cloud import firestore as firestore_sdk
        client = firestore_sdk.Client()
        return {
            "user_profile_store": FirestoreUserProfileStore(client),
            "verify_id_token": _stub_verify_id_token,  # LIFF実登録は別軸
        }
    except Exception:
        logger.exception(
            "COURSE_SET_PASHA_FIRESTORE_ENABLED=1 but Firestore client "
            "construction failed; re-raising instead of falling back "
            "to InMemory to avoid silently losing persistence."
        )
        raise
```

`get_runtime_dependencies()`(webhook)・`get_portal_runtime_dependencies()`・
`get_stripe_runtime_dependencies()`・ライフサイクル通知系5関数も同様に、
Firestore関連キーの構築のみをtry/exceptで囲み例外を再raiseする(Firestore以外の
キーの構築はそのまま)。

### 5.3. 例外伝播後の挙動(呼び出し元別)

- Webhookエントリポイント(`cloud_function_webhook.py`・`stripe_webhook.py`、
  いずれもHTTPトリガー): 例外がCloud Functions実行環境まで伝播すると5xx
  レスポンスを返す。送信元(LINE/Stripe)側の再送(リトライ)に委ねる前提と
  整合する(aircon-pashaフェーズ343 5.3節と同型)。
- checkout・portalエントリポイント(`checkout_session.py`・`portal_session.py`、
  いずれもHTTPトリガー想定): 例外伝播によりハンドラ内で捕捉せず終了し、Cloud
  Functions実行環境が5xxを返す。LIFFアプリ側(実登録後)はエラー表示・再試行案内
  とする想定(設計変更は不要、LIFF側実装はオーナー承認後)。
- 申込フォームエントリポイント(`cloud_function_application_form_submission.py`、
  HTTPトリガー): aircon-pashaフェーズ343 5.3節と同様に5xxとして表面化する。
- ライフサイクル通知系5つ(`cloud_function_send_deletion_candidate_final_
  confirmations.py`・`cloud_function_send_trial_end_notifications.py`・
  `cloud_function_send_payment_failure_reminders.py`・`cloud_function_send_
  payment_suspension_owner_notifications.py`、いずれもCloud Scheduler経由):
  例外伝播によりCloud Functions実行がエラー終了し、Cloud Loggingにエラーログが
  記録される。本ventureにはcloud-monitoring-alert-policy-design.md(kura-pasha
  フェーズ264で確認済みの通り本ventureにも既に存在)があるため、アラート設計
  自体の横展開は不要で、既存のログベース指標・アラートポリシーに本例外のログも
  含まれる想定(具体的な指標名の追加は結合実装フェーズに持ち越す)。

### 5.4. 未検証・残課題

- 本フェーズはログ・re-raiseという方針の決定のみで、`.py`ファイルへの実装反映は
  3節同様、実`google-cloud-firestore`ライブラリ導入とセットで行う結合実装フェーズに
  持ち越す。
- 残る2venture(forklift-pasha・line-reservation-ai)側の同ファイル4節への横展開は、
  本フェーズでは着手せず次回候補として残す。

最終更新: 2026-10-25 18:00 UTC (フェーズ333: kura-pashaフェーズ263・aircon-pasha
フェーズ343「ログ+re-raise、InMemory自動フォールバック禁止」方針の横展開として、
本venture固有の8エントリポイント向けに5節を新規設計。コード変更なし、テスト863件・
schema検証21件いずれも変更なしでパス)
