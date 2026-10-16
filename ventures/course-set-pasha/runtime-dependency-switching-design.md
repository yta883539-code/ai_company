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
- フラグが`"1"`のまま実クライアント構築が例外を投げるケースのハンドリングは
  未設計(aircon-pashaフェーズ319と同じ理由で本フェーズでは対応しない)。

最終更新: 2026-10-16 (フェーズ297)
