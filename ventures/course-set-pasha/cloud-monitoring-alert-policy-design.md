# Cloud Monitoringログベース指標・アラートポリシー設計(事前検討)

intent-classification-failure-observability-design.md 3節が「次回以降の課題」として
残していた、Cloud Monitoringのログベース指標・アラートポリシーの具体的な設定内容を
事前に設計する。実際のGCPプロジェクト上での作成作業自体は、既存のオーナー承認待ち
事項(GCPプロジェクト作成、tech-stack.md想定コンポーネント2)の範囲内であり実行しないが、
承認・プロジェクト作成後に即座に設定できるよう、設定値をここで確定しておく。

## 1. 前提

フェーズ249で`_classify_intent_with_retry()`が2回ともLlmApiErrorとなり`None`を返す直前に
WARNINGログ(`event=chatbot_intent_classification_failed`, `memo_length=<int>`)を
出力する実装が完了している(`prototype/cloud_function_webhook.py`)。Cloud Functionsの
標準`logging`連携により、このログは追加設定なしでCloud Loggingへ`jsonPayload`として
転送される想定(intent-classification-failure-observability-design.md 1節)。

## 2. ログベース指標(Log-based Metric)

- 種別: カウンタ型(該当ログ1件ごとに1カウント)。
- 名前(案): `chatbot_intent_classification_failure_count`
  (line-reservation-ai側に既存の同名指標が無いことを確認済み、venture間の命名衝突なし)。
- フィルタ(Logging クエリ言語):
  ```
  resource.type="cloud_function"
  jsonPayload.event="chatbot_intent_classification_failed"
  severity="WARNING"
  ```
  `resource.type`はcloud-functions-generation-decision.md(本フェーズ確定)により
  `cloud_run_revision`を採用する(2nd gen / Cloud Run functionsに確定。1st genは
  Googleが新規プロジェクトでの作成を停止済みのため選択の余地がない)。`service_name`・
  `revision_name`等の具体的なリソースラベル値は、実プロジェクト作成後(関数デプロイ後)
  でなければ確定できないため、この点のみ引き続き要確認として残す。
- ラベル: `memo_length`はカーディナリティが高く(メモごとに値が変わる)指標のラベルには
  不向きなため、ログベース指標のラベルには含めない。障害調査時はCloud Logging側の
  ログ本文(jsonPayload全体)を直接参照する運用とし、指標はあくまで「発生有無・頻度」の
  検知に用途を絞る。

## 3. アラートポリシー

- 条件: 上記ログベース指標が「直近60分間で合計1件以上」発生した場合に発火する
  しきい値アラート(`count > 0`, ローリングウィンドウ60分, アラート集計は`sum`)。
- しきい値を「1件以上」とした理由: 意図分類は`chatbot_intent`が`None`でも既存の生成
  フローへフォールスルーする設計(フェーズ246、design 3節・5節)であり顧客影響は
  軽微だが、LLM API側の障害・レート制限等の前兆を早期に把握する目的のため、件数の
  多寡によらず発生自体を即検知する方針とする。将来的に誤検知(一時的なAPI瞬断等)が
  頻発する場合は、しきい値を「60分間で3件以上」等に緩和する調整を運用開始後に検討する。
- 通知チャネル: Cloud Monitoringのアラートポリシーはメール・Slack・PagerDuty等の
  通知チャネルを指定できるが、本ventureはpayment-suspension-owner-notification-design.md
  で「オーナー(運営者)向け通知」をLINE Push固定送信先(`OWNER_LINE_USER_ID_PLACEHOLDER`)
  として設計済みであり、Cloud Monitoringの通知チャネルとは経路が異なる。本アラートは
  低頻度・技術的な運用監視目的であるため、既存のLINE通知導線を流用せず、Cloud
  Monitoring標準のメール通知チャネル(`OWNER_ALERT_EMAIL_PLACEHOLDER`)を素直に使う方針
  とする。実際の送信先メールアドレス設定は、GCPプロジェクト作成(既存承認待ち事項)後に
  オーナー自身がCloud Monitoringコンソール上で設定する想定とし、本ドキュメントでは
  プレースホルダのみを定義する(payment-suspension-owner-notification-design.mdの
  `OWNER_LINE_USER_ID_PLACEHOLDER`と同じ考え方)。

## 4. スコープ外(引き続き次回以降の課題)

- 上記フィルタの`service_name`・`revision_name`等の具体的なリソースラベル値は、
  実プロジェクト作成後(関数デプロイ後)に要確認(世代自体はcloud-functions-generation-
  decision.mdにて2nd genに確定済み)。
- 意図分類の成功率・レイテンシ等、失敗以外の運用指標の収集(intent-classification-
  failure-observability-design.md 3節から継続して範囲外)。
- [解消(フェーズ334)] aircon-pasha・kura-pasha側で同種の意図分類機能を実装する場合の
  本設計の横展開検討は、aircon-pashaフェーズ261(2026-09-25)・kura-pasha(本venture名
  `cloud-monitoring-alert-policy-design.md`新規作成)でそれぞれ対応済みであることを
  フェーズ334の棚卸しで確認した(`grep`でaircon-pasha・kura-pasha両ファイル内に
  `chatbot_intent_classification_failure_count`系の指標名定義が存在することを確認)。
  なお、棚卸しの過程でkura-pasha側ファイル(15〜19行目)が「aircon-pasha・course-
  set-pasha・line-reservation-aiの既存指標名を確認したところ、いずれも同一名を使って
  おり」と記述しているが、line-reservation-ai自身の`cloud-monitoring-alert-policy-
  design.md`(15〜17行目・100〜101行目)は「本ventureにはそれに相当する意図分類の
  仕組みがなく...新設するかどうかは未検討」と明記しており、line-reservation-aiが
  同名指標を既に使っているという記述は事実と異なることも確認した。この点の是正は
  kura-pasha側ファイルの修正であり本venture側の作業範囲外のため、次回以降の
  kura-pasha側棚卸し候補として申し送る(本フェーズでは本venture側ファイルの修正
  のみに限定)。
- 実際のログベース指標・アラートポリシーの作成(`gcloud logging metrics create`
  および`gcloud alpha monitoring policies create`相当の操作)は、GCPプロジェクト作成後に
  オーナー承認の範囲内で実施する。

## 5. Firestoreランタイム依存構築失敗アラート(フェーズ335)

runtime-dependency-switching-design.md 5節(フェーズ333)で決定した「フラグ
`COURSE_SET_PASHA_FIRESTORE_ENABLED`が`"1"`のまま実クライアント構築が失敗した場合は
InMemoryへ自動フォールバックせずログ出力の上で例外を再raiseする」方針について、
本venture向けの検知用ログベース指標・アラートポリシーがまだ定義されていなかった
(forklift-pashaフェーズ192は「kura-pasha・aircon-pasha・course-set-pasha・
forklift-pashaの4venture全てに揃った」としていたが、aircon-pashaフェーズ344の棚卸しで
本venture分についてはこの記載が不正確〈実際には未対応〉であることが指摘されていた)。
1〜4節は意図分類失敗(`chatbot_intent_classification_failed`)専用であり、Firestore
ランタイム依存構築失敗(5節のre-raise方針が対象とする事象)は検知対象(LLM API起因か
GCP認証・権限起因か)が異なるため、1〜4節を転用せず、kura-pashaフェーズ265・
aircon-pashaフェーズ344・forklift-pashaフェーズ192と同型の設計を本venture向けに
新規に定義する。

### 5.1. ログベース指標

- 名前(案): `course_set_pasha_firestore_runtime_dependency_construction_failure_count`
  (kura-pasha・aircon-pasha・forklift-pashaの命名規則`<venture-prefix>_firestore_
  runtime_dependency_construction_failure_count`を踏襲)。
- フィルタ(Logging クエリ言語):
  ```
  resource.type="cloud_run_revision"
  jsonPayload.event="firestore_runtime_dependency_construction_failed"
  severity="ERROR"
  ```
  `resource.type`は本ファイル2節と同じく2nd gen / Cloud Run functionsを採用する
  (cloud-functions-generation-decision.md確定事項)。`service_name`・`revision_name`等
  の具体的なリソースラベル値は実プロジェクト作成後(各エントリポイントのデプロイ後)
  でなければ確定できないため、2節と同様引き続き要確認として残す。
  ログ出力側(runtime-dependency-switching-design.md 5.2節の擬似コード内`logger.
  exception(...)`)は現状メッセージ文字列のみで`event`キーを持たないため、結合実装
  フェーズで`logger.exception(..., extra={"json_fields": {"event": "firestore_
  runtime_dependency_construction_failed"}})`相当の構造化ログに揃える必要がある
  (本フェーズは設計のみ、`.py`実装への反映は次回候補)。
- severityを意図分類失敗(WARNING)と区別しERRORとする理由: kura-pashaフェーズ265・
  aircon-pashaフェーズ344と同一。本事象は「フラグON時に実Firestore接続が必要な場面で
  接続できていない」という設定・権限上の不具合であり、顧客影響(チェックアウト失敗・
  5xx応答・ライフサイクル通知系の未実行)を伴うため、顧客影響が軽微な意図分類失敗より
  重大度が高い。

### 5.2. アラートポリシー

- 条件: 上記ログベース指標が「直近60分間で合計1件以上」で発火(1〜3節と同一のローリング
  ウィンドウ・しきい値)。フラグON時の構築失敗は即時表面化させる方針(runtime-
  dependency-switching-design.md 5.1節)のため、しきい値を緩める理由がない。
- 通知チャネル: 3節と同じCloud Monitoring標準メール通知チャネル(`OWNER_ALERT_EMAIL_
  PLACEHOLDER`)を共用する(運営者自身向けの技術監視目的で宛先・経路が1〜3節と同一の
  ため、チャネル自体を分ける必要はない。ポリシー自体は指標が異なるため1〜3節のポリシー
  とは別個に作成する)。
- 対象エントリポイントは本ファイル1節・runtime-dependency-switching-design.md 1節に
  列挙された複数関数(webhook・checkout・portal・stripe・申込フォーム・ライフサイクル
  通知系)にわたるが、forklift-pashaフェーズ192と同じ理由(いずれも検知対象が同一
  〈Firestoreランタイム依存構築失敗〉)により、関数ごとに個別の指標・ポリシーを分ける
  必要はなく1指標に集約する。

### 5.3. スコープ外(引き続き次回以降の課題)

- 5.1節のログ出力側(`.py`実装)への`event`フィールド構造化反映は、3節既存項目と同様に
  実`google-cloud-firestore`導入・結合実装フェーズに持ち越す。
- `resource.type`のリソースラベル値(`service_name`等)は、実プロジェクト作成後に
  各エントリポイントのデプロイ単位を確認して確定する。
- 本設計により、Firestoreランタイム依存構築失敗アラート設計はkura-pasha・aircon-pasha・
  course-set-pasha・forklift-pasha・line-reservation-aiの5venture全てに揃ったことになる
  (forklift-pashaフェーズ193がline-reservation-ai分を確認済み、本フェーズで本venture分
  の未対応を解消)。
- 実際のログベース指標・アラートポリシーの作成(`gcloud logging metrics create`
  および`gcloud alpha monitoring policies create`相当の操作)は、GCPプロジェクト作成後に
  オーナー承認の範囲内で実施する。

最終更新: 2026-10-26 14:00 UTC (フェーズ335: aircon-pashaフェーズ344・forklift-pasha
フェーズ192が指摘していた「本ventureのFirestoreランタイム依存構築失敗アラート設計が
未対応」というギャップを解消し、5節として新規設計した。コード変更なし、テスト863件・
schema検証21件いずれも変更なしでパス)
