# 実Firestore承認後のランタイム依存切り替え設計(フェーズ158)

course-set-pashaフェーズ297(runtime-dependency-switching-design.md)の次回候補
「残る横展開先(line-reservation-ai・forklift-pasha)」を受け、本venture
(forklift-pasha)に横展開する。コード変更・外部アカウント作成のいずれも
行わない(ドキュメントのみの設計フェーズ)。

## 1. 現状の棚卸し

本ventureには`get_.*_runtime_dependencies()`系の関数が4つ存在し、いずれも
現状はInMemory実装(または`_UnconfiguredEmailSender`等の未接続スタブ)を
常に返す。他venture(aircon-pasha・kura-pasha・course-set-pasha)と異なり
LINE非依存・Webフォーム+メール通知構成(tech-stack.md)のため、LIFF・
LINE公式アカウント起因の依存(`verify_id_token`等)自体がそもそも存在しない。

- `checkout_session.get_checkout_runtime_dependencies()`: `access_token_store`・
  `operator_store`・`checkout_session_creator`(`MockCheckoutSessionCreator`)を
  常に非Noneで返す。
- `stripe_webhook.get_stripe_runtime_dependencies()`: `store`のみを常に
  非Noneで返す(aircon-pasha・course-set-pashaと同じ位置づけ)。
- `cloud_function_send_deletion_confirmations.get_deletion_confirmation_
  runtime_dependencies()`: `store`・`email_sender`(`_UnconfiguredEmailSender`、
  常に送信失敗を返す安全側フォールバック)を常に非Noneで返す。
- `cloud_function_send_trial_end_emails.get_trial_end_email_runtime_
  dependencies()`: `operator_store`・`email_client`・`access_url_provider`
  (`_PLACEHOLDER_BASE_URL`経由)を常に非Noneで返す。

いずれも呼び出し先がNoneを許容しない必須引数のため、既出3venture(kura-pasha・
aircon-pasha・course-set-pasha)で確立した「`_firestore_enabled()`が真の場合に
Firestore版実装一式へ差し替える」方式がそのまま適用できる。本ventureには
「空dictが未接続を表す」パターン(他venture共通の`webhook.get_runtime_
dependencies()`相当)は存在しない。

## 2. 切り替え条件(命名規則の横展開)

kura-pasha・aircon-pasha・course-set-pashaと同じ命名規則
(`<venture-prefix>_FIRESTORE_ENABLED`)に揃え、本ventureでは
`FORKLIFT_PASHA_FIRESTORE_ENABLED`(値`"1"`で有効)とする。未設定時は常に
InMemory実装にフォールバックする安全側設計とし、承認前の誤接続を防ぐ
(`GOOGLE_CLOUD_PROJECT`はCloud Functions実行環境で常に自動設定されるため
接続準備完了の判定には使えない、という既出3venture共通の判断理由をそのまま
踏襲)。

```python
import os

def _firestore_enabled() -> bool:
    return os.environ.get("FORKLIFT_PASHA_FIRESTORE_ENABLED") == "1"
```

Stripe API実接続・実メール送信手段の確定(送信元ドメイン・SMTP/メールAPIの
選定)・本番LPドメイン確定はいずれも別軸(それぞれ別の承認待ち項目、
pending-approval.md参照)のため、本フラグはFirestoreストア
(`InMemoryFleetOperatorStore`・`InMemoryAccessTokenStore`)の切り替えのみを
対象とし、`checkout_session_creator`・`email_sender`・`email_client`・
`access_url_provider`の接続先切り替えは本設計の対象外のまま残す
(aircon-pasha・course-set-pashaの整理と同じ)。

## 3. 各エントリポイントへの適用案

### 3.1. `get_checkout_runtime_dependencies()`

`operator_store`のみをFirestore実装に差し替える(`access_token_store`は
別途アクセストークン方式自体のFirestore化が必要なため、本フェーズでは
`operator_store`のみを対象とする想定)。`checkout_session_creator`は実Stripe
接続待ちのため対象外。

### 3.2. `get_stripe_runtime_dependencies()`

`store`(`InMemoryFleetOperatorStore`)をFirestore実装一式に差し替える構成
(aircon-pasha・course-set-pashaの同種エントリポイントと同型)。

### 3.3. `get_deletion_confirmation_runtime_dependencies()`・`get_trial_end_email_runtime_dependencies()`

いずれも同形の条件分岐(`store`/`operator_store`をFirestore実装に差し替え、
`email_sender`・`email_client`・`access_url_provider`はそのまま)を適用する
想定。2関数とも対称構成であるため、設計自体は1パターンで足りる
(course-set-pashaフェーズ297 3.4節のライフサイクル通知系と同じ考え方)。

## 4. 未検証・残課題

- `_firestore_enabled()`・各`get_.*_runtime_dependencies()`の実コード化は、
  実`google-cloud-firestore`ライブラリの導入・本venture用Firestoreアダプタ
  設計(kura-pashaのworkshop-store-firestore-adapter-design.mdに相当する
  文書が本ventureにはまだ無い)とセットで行うのが安全なため、承認後の
  結合実装フェーズに持ち越す(本フェーズはコード変更を行わない)。
- 残る横展開先はline-reservation-aiのみとなった(次回候補として記録)。
  line-reservation-aiはLINE Platform Webhook受信時点で検証済みの
  `event.source.userId`をそのまま使う構成(2026-09-27 08:00 UTC pending-
  approval記載)のため、Firestoreストア切り替え自体の対象関数が本venture・
  他3ventureとどの程度対称になるか個別に確認が必要。
- `access_token_store`(アクセストークン方式そのもの)のFirestore化は
  本フェーズでは対象外としたため、別途検討が必要(次回候補)。
- フラグが`"1"`のまま実クライアント構築が例外を投げるケースのハンドリングは
  未設計(他3venture共通の理由により本フェーズでは対応しない)。

## 5. 実クライアント構築失敗時の例外処理方針(フェーズ191)

4節の残課題のうち、`_firestore_enabled()`が真であるにもかかわらず
`firestore_sdk.Client()`(または各Firestoreアダプタの初期化)が例外を投げる
ケース(認証情報未設定・サービスアカウント権限不足・一時的なネットワーク障害等)の
ハンドリング方針を、kura-pashaフェーズ263(同ファイル6節)・aircon-pashaフェーズ343
(同ファイル5節)・course-set-pashaフェーズ333(同ファイル5節)の横展開として、
本venture固有の4エントリポイント(`get_checkout_runtime_dependencies()`・
`get_stripe_runtime_dependencies()`・`get_deletion_confirmation_runtime_
dependencies()`・`get_trial_end_email_runtime_dependencies()`)向けに設計する。

### 5.1. 方針: 例外は握り潰さずそのまま伝播させる(InMemoryへの自動フォールバック禁止)

未設定時(フラグが`"1"`でない)は2節のとおりInMemory実装へ安全側フォールバックする
既定だが、フラグが明示的に`"1"`に設定された状態で実クライアント構築が失敗した場合に
InMemory実装へ自動的に切り替えることはしない。理由は既出3venture(kura-pasha・
aircon-pasha・course-set-pasha)と同じく以下の2点。

- フラグ`"1"`はオーナー承認後の結合実装フェーズで意図的に設定される値であり、
  この状態での構築失敗は「実Firestoreへの接続が必要な場面で接続できていない」という
  設定・権限上の不具合を意味する。これをInMemoryへ自動フォールバックすると、
  `operator_store`・`store`への書き込みが実際には永続化されずに処理自体は正常終了
  したように見えるため、不具合の発覚が遅れ、顧客データの消失・重複処理を招くリスクが
  ある。
- 残る横展開先であるline-reservation-ai側の同ファイル4節にも同一の残課題があり
  (本フェーズ着手前に確認済み)、5venture全体で「フラグON時は失敗を隠さず表面化
  させる」という一貫した方針を揃える必要がある。

### 5.2. 実装方針(擬似コード)

```python
import logging
import os

logger = logging.getLogger(__name__)


def _firestore_enabled() -> bool:
    return os.environ.get("FORKLIFT_PASHA_FIRESTORE_ENABLED") == "1"


def get_checkout_runtime_dependencies() -> dict:
    if not _firestore_enabled():
        return {
            "operator_store": InMemoryFleetOperatorStore(),
            "access_token_store": InMemoryAccessTokenStore(),
            "checkout_session_creator": MockCheckoutSessionCreator(),
        }
    try:
        client = firestore_sdk.Client()
        return {
            "operator_store": FirestoreFleetOperatorStore(client),
            "access_token_store": InMemoryAccessTokenStore(),
            "checkout_session_creator": MockCheckoutSessionCreator(),
        }
    except Exception:
        logger.exception(
            "FORKLIFT_PASHA_FIRESTORE_ENABLED=1 but Firestore client "
            "construction failed; re-raising instead of falling back "
            "to InMemory to avoid silently losing persistence."
        )
        raise
```

`get_stripe_runtime_dependencies()`・`get_deletion_confirmation_runtime_
dependencies()`・`get_trial_end_email_runtime_dependencies()`の残り3関数も同様に、
try/exceptでログを出した上で例外を再raiseする形を取る(3.2・3.3節の擬似コードに
同じtry/except構造を追加するのみで、`access_token_store`・`email_sender`・
`email_client`・`access_url_provider`等Firestore対象外の依存先はそのまま維持する)。

### 5.3. 例外伝播後の挙動(呼び出し元別)

- Webhookエントリポイント(`get_stripe_runtime_dependencies()`経由、HTTPトリガー):
  例外が実行環境まで伝播すると5xxレスポンスを返す。Stripe側の自動再送に委ねる
  (他venture共通の整理と同じ)。
- 日次/定期スケジューラ(`get_deletion_confirmation_runtime_dependencies()`・
  `get_trial_end_email_runtime_dependencies()`経由): Cloud Loggingへのエラー記録に
  留まる。アラート設計は本venture未作成のcloud-monitoring-alert-policy-design.md
  相当文書(aircon-pasha・course-set-pasha・kura-pashaには既存)への横展開を次回候補
  とする。(フェーズ196で解消済み。本venture向けcloud-monitoring-alert-policy-
  design.mdはフェーズ192で新規作成され、4エントリポイント全てを対象とする
  Firestoreランタイム依存構築失敗アラート〈1節〉が既に揃っている。下記注記参照)
- `get_checkout_runtime_dependencies()`(LP/フォーム経由のチェックアウト起点):
  例外発生時はチェックアウト自体を失敗させ、申込者にはエラー表示(実装は承認後の
  結合実装フェーズで確定)とする想定。

他venture(aircon-pasha・course-set-pasha・kura-pasha)側の同ファイルで確立された
方針と同型であるため、本フェーズでは設計のみとし実コード化は行わない(承認後の
結合実装フェーズに持ち越す、4節の既存整理と同じ)。

最終更新: 2026-10-25 19:00 UTC(フェーズ191)

追記(フェーズ196・2026-10-27 22:00 UTC): 5.3節が「本venture未作成の
cloud-monitoring-alert-policy-design.md相当文書への横展開を次回候補とする」と
記載していたが、同ファイルは既にフェーズ192(2026-10-26 01:00 UTC)で新規作成
済みであり、4エントリポイント(`get_checkout_runtime_dependencies()`・
`get_stripe_runtime_dependencies()`・`get_deletion_confirmation_runtime_
dependencies()`・`get_trial_end_email_runtime_dependencies()`)全てを対象とする
Firestoreランタイム依存構築失敗アラート(同ファイル1〜2節)が既に揃っている
ことを確認した(陳腐化記載の是正)。5.3節の記載自体は経緯の記録として残し、
本追記で解消済みであることを明記するのみとする。コード変更なし(棚卸し確認・
記載是正のみ)、回帰確認として`python3 -m unittest discover -s prototype -p
"test_*.py"`(93件、変更なし)・`python3 schema/validate_test_cases.py`
(11件、変更なし)を実行しいずれも変更なしでパスすることを確認した(回帰なし)。
承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生
していないためpending-approval.mdへの追記なし。
