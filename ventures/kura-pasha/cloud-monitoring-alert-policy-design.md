# Cloud Monitoringログベース指標・アラートポリシー設計(事前検討)

intent-classification-failure-observability-design.md(本venture向け新規作成)が
確認した、フェーズ174実装済みのWARNINGログ(`event=chatbot_intent_classification_failed`,
`memo_length=<int>`)を対象に、course-set-pasha/cloud-monitoring-alert-policy-design.md・
aircon-pasha側の同種設計を本venture向けに横展開する。実際のGCPプロジェクト上での作成
作業自体は、既存のオーナー承認待ち事項(GCPプロジェクト作成、tech-stack.md想定
コンポーネント2)の範囲内であり実行しないが、承認・プロジェクト作成後に即座に設定
できるよう、設定値をここで確定しておく。

## 1. ログベース指標(Log-based Metric)

- 種別: カウンタ型(該当ログ1件ごとに1カウント)。
- 名前(案): `kura_pasha_chatbot_intent_classification_failure_count`
  (aircon-pasha・course-set-pasha・line-reservation-aiの既存指標名を確認したところ、
  いずれも`chatbot_intent_classification_failure_count`という同一名を使っており、
  venture名を含めない場合は将来同一GCPプロジェクト配下で複数venture分を運用する際に
  指標名が衝突する可能性がある。他venture側の既存指標名を今から変更する必要は無いが、
  本venture分は新規作成のため、衝突を避けるため`kura_pasha_`接頭辞を付与する方針とした)。
- フィルタ(Logging クエリ言語):
  ```
  resource.type="cloud_function"
  jsonPayload.event="chatbot_intent_classification_failed"
  severity="WARNING"
  ```
  course-set-pashaのcloud-functions-generation-decision.md(2026-09-25 11:00 UTC定例更新)の
  確定に基づき、`resource.type`は`cloud_run_revision`を採用する(2nd gen / Cloud Run
  functionsに確定。Googleが新規プロジェクトでの1st gen新規作成を停止済みのため、他venture
  共通で選択の余地がない)。`service_name`・`revision_name`等の具体的なリソースラベル値は
  実プロジェクト作成後(関数デプロイ後)でなければ確定できないため、この点のみ引き続き
  要確認として残す。
- ラベル: `memo_length`はカーディナリティが高く指標のラベルには不向きなため含めない
  (course-set-pashaと同じ方針)。障害調査時はCloud Logging側のログ本文
  (jsonPayload全体)を直接参照する運用とし、指標はあくまで「発生有無・頻度」の検知に
  用途を絞る。

## 2. アラートポリシー

- 条件: 上記ログベース指標が「直近60分間で合計1件以上」発生した場合に発火する
  しきい値アラート(`count > 0`, ローリングウィンドウ60分, アラート集計は`sum`)。
- しきい値を「1件以上」とした理由: course-set-pashaと同じく、意図分類は
  `chatbot_intent`が`None`でも既存の生成フロー(memo_processing_request相当)へ
  フォールスルーする設計(chatbot-intent-classification-wiring-design.md 4節、
  フェーズ174実装)であり顧客影響は軽微だが、LLM API側の障害・レート制限等の前兆を
  早期に把握する目的のため、件数の多寡によらず発生自体を即検知する方針とする。
  本ventureは低頻度受注特性(llm-api-cost-estimate.md、他ventureより受注件数自体が
  少ない)のため、同じ「1件以上」しきい値でも実際の発火頻度は他ventureより低くなる
  見込みだが、しきい値自体を緩める理由にはならないためcourse-set-pashaと同一の
  設定値を採用する。将来的に誤検知(一時的なAPI瞬断等)が頻発する場合は、しきい値を
  緩和する調整を運用開始後に検討する。
- 通知チャネル: payment-suspension-owner-notification-design.mdで確認した通り、本
  ventureの「オーナー(契約者・工房)向け通知」は`OWNER_LINE_USER_ID_PLACEHOLDER`への
  LINE Push固定送信先として設計済みである。本アラートは低頻度・技術的な運用監視目的
  であり、契約者向け業務通知とは経路・宛先(運営者自身であり契約者ではない)が異なる
  ため、既存のLINE通知導線は流用せず、course-set-pashaと同様にCloud Monitoring標準の
  メール通知チャネル(`OWNER_ALERT_EMAIL_PLACEHOLDER`)を素直に使う方針とする。実際の
  送信先メールアドレス設定は、GCPプロジェクト作成(既存承認待ち事項)後にオーナー自身が
  Cloud Monitoringコンソール上で設定する想定とし、本ドキュメントではプレースホルダの
  みを定義する。

## 3. スコープ外(引き続き次回以降の課題)

- 上記フィルタの`service_name`・`revision_name`等の具体的なリソースラベル値は、
  実プロジェクト作成後(関数デプロイ後)に要確認(世代自体はcourse-set-pasha側の
  cloud-functions-generation-decision.mdにて2nd genに確定済み、他venture共通)。
- 意図分類の成功率・レイテンシ等、失敗以外の運用指標の収集(intent-classification-
  failure-observability-design.md 3節から継続して範囲外)。
- 実際のログベース指標・アラートポリシーの作成(`gcloud logging metrics create`
  および`gcloud alpha monitoring policies create`相当の操作)は、GCPプロジェクト作成後に
  オーナー承認の範囲内で実施する。
- line-reservation-ai向けの検討(会話状態管理を前提とする別構成のため、本設計を
  そのまま横展開できるかは別途course-set-pasha側の記載の通り同venture固有の課題として
  残る、本ドキュメントの範囲外)。

## 4. Firestoreランタイム依存構築失敗アラート(フェーズ265)

runtime-dependency-switching-design.md 6節(フェーズ263)で決定した「フラグ
`KURA_PASHA_FIRESTORE_ENABLED`が`"1"`のまま実クライアント構築が失敗した場合は
InMemoryへ自動フォールバックせずログ出力の上で例外を再raiseする」方針について、
6.3節は「日次スケジューラ側のエラー通知(アラートポリシー)の具体的な構成は、本
venture未作成のcloud-monitoring-alert-policy-design.md相当の文書に委ねる」と
記載していたが、本ファイル自体は既にフェーズ174由来の意図分類失敗アラート
(1節・2節)として作成済みであり、この記載は不正確だった。実際には1節・2節は
意図分類失敗(`chatbot_intent_classification_failed`)専用であり、Firestore
ランタイム依存構築失敗(6節のre-raise方針が対象とする事象)を検知する指標・
アラートはまだ定義されていなかった。両者は検知対象(LLM API起因かGCP認証・
権限起因か)が異なるため、1節・2節を転用せず新規に以下を定義する。

### 4.1. ログベース指標

- 名前(案): `kura_pasha_firestore_runtime_dependency_construction_failure_count`
- フィルタ:
  ```
  resource.type="cloud_run_revision"
  jsonPayload.event="firestore_runtime_dependency_construction_failed"
  severity="ERROR"
  ```
  ログ出力側(runtime-dependency-switching-design.md 6.2節の`logger.exception(...)`)は
  現状メッセージ文字列のみで`event`キーを持たないため、結合実装フェーズで
  `logger.exception(..., extra={"json_fields": {"event": "firestore_runtime_dependency_construction_failed"}})`
  相当の構造化ログに揃える必要がある(本フェーズでは設計のみ、`.py`実装は
  未反映。6.2節の疑似コードへの反映は次回候補)。
- severityを意図分類失敗(WARNING)と区別しERRORとする理由: 6.1節の通り、本事象は
  「設定・権限上の不具合」であり顧客影響(処理失敗・5xx応答)を伴うため、意図分類
  失敗(フォールスルーにより顧客影響が軽微)より重大度が高い。

### 4.2. アラートポリシー

- 条件: 上記指標が「直近60分間で合計1件以上」で発火(1節・2節と同一のローリング
  ウィンドウ・しきい値)。6.1節の通りフラグON時の構築失敗は即時表面化させる方針
  のため、しきい値を緩める理由がない。
- 通知チャネル: 2節と同じCloud Monitoring標準メール通知チャネル
  (`OWNER_ALERT_EMAIL_PLACEHOLDER`)を共用する(運営者自身向けの技術監視目的で
  宛先・経路が1節・2節と同一のため、チャネル自体を分ける必要はない。ポリシー自体は
  指標が異なるため1節・2節のポリシーとは別個に作成する)。

### 4.3. スコープ外(引き続き次回以降の課題)

- 4.1節のログ出力側(`.py`実装)への`event`フィールド構造化反映は、3節既存項目
  と同様に実`google-cloud-firestore`導入・結合実装フェーズに持ち越す。
- 実際のログベース指標・アラートポリシーの作成自体は、3節同様GCPプロジェクト
  作成後にオーナー承認の範囲内で実施する。

## 4.4. Webhookエントリポイント側への同種可視化(フェーズ266)

4.3節(フェーズ265)が残課題としていた「Webhookエントリポイント側
(`cloud_function_webhook.py`)で同一事象が発生した場合の可視化」について、
runtime-dependency-switching-design.md 3.2節・6.2節を再確認した結果、別途
新規の指標設計は不要であり、4.1節の指標が既にWebhook側を対象範囲に含む設計で
あったことを確認した。

- 6.2節で示されている`try`/`except`付き疑似コードの関数シグネチャは
  `get_runtime_dependencies()`であり、これは3.2節の通りWebhookエントリポイント
  (`cloud_function_webhook.py`)側の関数そのものである(日次スケジューラ側の
  `get_daily_workshop_checks_runtime_dependencies()`は、6.2節末尾で「同様の
  try/except構造を追加するのみ」と参照されているに留まり、別途の疑似コードは
  示されていない)。したがって4.1節が「現状メッセージ文字列のみでeventキーを
  持たない」と指摘した`logger.exception(...)`呼び出しは、実はWebhook側の
  コードを指しており、4.1節の構造化ログ対応(結合実装フェーズ持ち越し)は
  Webhook側から着手することになる見込みである。
- 4.1節のログベース指標フィルタ(`resource.type="cloud_run_revision"`・
  `jsonPayload.event="firestore_runtime_dependency_construction_failed"`・
  `severity="ERROR"`)は`resource.labels.service_name`による絞り込みを含まない
  (1節のフィルタと同様、実プロジェクト作成後にサービス単位のラベル値を確認する
  方針のまま未確定)。そのため、日次スケジューラ側の`get_daily_workshop_checks_
  runtime_dependencies()`にも6.2節と同じ構造化ログ(同一の`event`名)を結合実装
  フェーズで反映すれば、両エントリポイントの構築失敗を**同一の指標・同一のアラート
  ポリシー**(4.1節・4.2節)で検知でき、Webhook専用の第2の指標・アラートポリシーを
  新規作成する必要はない。4.3節(フェーズ265)はこの点を「要確認」の残課題として
  挙げていたが、指標設計自体はすでに両エントリポイント共用で成立することが本検討で
  判明したため解消する。
- 残る未確定事項は、実プロジェクト作成・両Cloud Functionsのデプロイ後に
  `resource.labels.service_name`の実際の値を確認し、必要であれば(障害調査時に
  どちらのエントリポイントが起因かをログビューア側で素早く絞り込みたい場合)
  Cloud Logging側のクエリでservice_name別にドリルダウンできることを確認する、
  という運用確認レベルの話に限られる(アラート発火自体の要件ではないため
  スコープ外のまま)。

最終更新: 2026-10-26 10:00 UTC (フェーズ266: 4.3節の残課題だった「Webhook
エントリポイント側への同種可視化」を検討し、6.2節の疑似コードが実はWebhook側の
関数であったことを確認した上で、4.1節の指標フィルタがservice_nameで絞り込まれて
いないため両エントリポイント(Webhook・日次スケジューラ)の構築失敗を単一の指標・
アラートポリシーで検知できることを明らかにし、Webhook専用の第2指標が不要である
ことを確認して4.3節の残課題を解消した。コード変更なし、設計文書の追記のみ)
