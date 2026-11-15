# Cloud Monitoringログベース指標・アラートポリシー設計(新規作成・フェーズ続き348)

runtime-dependency-switching-design.md 5.4節が残課題としていた「本venture固有の
cloud-monitoring-alert-policy-design.md相当の文書は未作成」を解消する。
kura-pashaフェーズ265(cloud-monitoring-alert-policy-design.md 4節)・
course-set-pasha・aircon-pasha側の同種設計を本venture向けに横展開するが、本venture
固有の事情(1節参照)により横展開は単純な転記にならない。実際のGCPプロジェクト上での
作成作業自体は既存のオーナー承認待ち事項(GCPプロジェクト作成・Firestore接続、
pending-approval.md参照)の範囲内であり実行しないが、承認後に即座に設定できるよう
設定値をここで確定しておく。コード変更・外部アカウント作成のいずれも行わない
(ドキュメントのみの設計フェーズ)。

## 1. 本venture固有の事情(他4venture横展開との差異)

kura-pasha・aircon-pasha・course-set-pasha・forklift-pashaは単一の意図分類
(`chatbot_intent_classification_failed`、WARNING)イベントを検知対象とするが、
本venture(line-reservation-ai)にはそれに相当する意図分類の仕組みがなく(構造化
出力〈JSON〉のフォーマット崩れ時のリトライ・フォールバックはjson-output-retry-
fallback.md側で扱うが、現時点でログ出力の設計自体が未着手)、代わりに
runtime-dependency-switching-design.md 5節で設計済みの「Firestoreランタイム依存
構築失敗時のログ+re-raise」方針が唯一の構造化ログ対象イベントである。さらに本
venture側はこのイベントが`checkout_session`・`conversation_event_processor_
assembly`・`stripe_webhook_entry_point`という3つの別プロセス(別Cloud Function)
それぞれで発生し得る点が他4venture(単一のチャットボットWebhook関数内で発生)と
構造的に異なる。このため、kura-pasha 4節のような単一指標ではなく、3エントリ
ポイント共通のイベント名・指標は1つに統一しつつ、`service_name`ラベルで発生元を
区別する設計とする(2.2節参照)。

## 2. ログベース指標(Log-based Metric)

### 2.1. 対象イベント

runtime-dependency-switching-design.md 5.2節の`logger.exception(...)`を、
`event`フィールドを持つ構造化ログに揃える(現状はメッセージ文字列のみ、本フェーズ
では設計のみで`.py`実装は未反映。結合実装フェーズでの反映は4節の次回候補とする)。

```python
logger.exception(
    "LINE_RESERVATION_AI_FIRESTORE_ENABLED=1 but Firestore client "
    "construction failed; re-raising instead of falling back "
    "to InMemory to avoid silently losing persistence.",
    extra={"json_fields": {
        "event": "firestore_runtime_dependency_construction_failed",
        "entry_point": "checkout_session",  # or "conversation_event_processor_assembly" / "stripe_webhook_entry_point"
    }},
)
```

`entry_point`フィールドを追加するのは、同一イベント名が3関数で共通発生するため、
ログ本文側でも発生元を自己記述させておくとCloud Logging側のクエリ(`service_name`
ラベルへの依存のみでは将来のリファクタ〈関数の統合・分割〉に弱い)を補強できるため。

### 2.2. ログベース指標本体

- 種別: カウンタ型(該当ログ1件ごとに1カウント)。
- 名前(案): `line_reservation_ai_firestore_runtime_dependency_construction_failure_count`
  (kura-pasha 4.1節と同じ`<venture-prefix>_`接頭辞方針を踏襲し、将来同一GCP
  プロジェクト配下で複数venture分を運用する際の指標名衝突を避ける)。
- フィルタ(Logging クエリ言語):
  ```
  resource.type="cloud_run_revision"
  jsonPayload.event="firestore_runtime_dependency_construction_failed"
  severity="ERROR"
  ```
  `resource.type`はcourse-set-pashaのcloud-functions-generation-decision.mdの
  確定(2nd gen / Cloud Run functions)を他venture共通で踏襲する。severityを
  ERRORとする理由はkura-pasha 4.1節と同一(設定・権限上の不具合であり顧客影響
  〈処理失敗・5xx応答〉を伴うため)。
- ラベル: `entry_point`はカーディナリティが低く(3値固定)、発生元の切り分けに
  直接役立つため、本venture固有の追加ラベルとして指標に含める(kura-pasha等が
  `memo_length`〈高カーディナリティ〉を除外した判断とは別の理由による取り扱い)。
  `resource.labels.service_name`も同じ発生元情報を持つが、Cloud Monitoring標準
  ラベルとして別途利用可能なため、ログベース指標側の独自ラベルは`entry_point`
  のみに絞る。
  ```
  labelExtractors:
    entry_point: "EXTRACT(jsonPayload.entry_point)"
  ```

## 3. アラートポリシー

- 条件: 上記ログベース指標が「直近60分間で合計1件以上」発生した場合に発火する
  しきい値アラート(`count > 0`, ローリングウィンドウ60分, アラート集計は`sum`、
  `entry_point`ラベルでグループ化しない。3関数いずれで発生しても同一重大度の
  設定・権限不具合であり、まず発生自体を検知した上でラベル値はログ本文の確認時に
  参照すれば足りるため)。
- しきい値を「1件以上」とした理由: kura-pasha 4.2節と同一。フラグON時の構築失敗は
  即時表面化させる方針のため、しきい値を緩める理由がない。
- 通知チャネル: Cloud Monitoring標準のメール通知チャネル
  (`OWNER_ALERT_EMAIL_PLACEHOLDER`)を使う(他4venture共通方針を踏襲)。実際の
  送信先メールアドレス設定は、GCPプロジェクト作成(既存承認待ち事項)後にオーナー
  自身がCloud Monitoringコンソール上で設定する想定とし、本ドキュメントでは
  プレースホルダのみを定義する。

## 4. スコープ外(引き続き次回以降の課題)

- 2.1節のログ出力側(`.py`実装、`event`/`entry_point`フィールドの構造化反映)は、
  実`google-cloud-firestore`導入・結合実装フェーズに持ち越す。
- 上記フィルタの`service_name`・`revision_name`等の具体的なリソースラベル値は、
  実プロジェクト作成後(3関数デプロイ後)に要確認(他venture共通の残課題と同型)。
- 実際のログベース指標・アラートポリシーの作成(`gcloud logging metrics create`
  および`gcloud alpha monitoring policies create`相当の操作)は、GCPプロジェクト
  作成後にオーナー承認の範囲内で実施する。
- 5.3節で確定したしきい値(日次6件以上)は、json-output-retry-fallback.mdの
  「要検討: 暫定で1日5件など」をそのまま転用した仮置きであり、実LLM運用データが
  無い現時点ではなお検証が必要(次回候補として残す)。

## 5. 構造化出力(JSON)フォールバック発生の検知(新規検討・解消)

4節(旧版)で未検討としていた「構造化出力(JSON)のフォーマット崩れ・リトライ失敗
側に、本venture独自の意図分類失敗相当のログ・指標・アラートを新設するかどうか」を
検討した。

### 5.1. 1節・2節(Firestore依存構築失敗)との違い

1節・2節で扱うFirestoreランタイム依存構築失敗は、フラグON時には本来絶対に
発生してはならない設定・権限上の不具合であり、発生自体が異常(ベースラインは
常にゼロ)であるため「直近60分で1件以上」という低いしきい値で即時検知する
設計とした(他4venture共通方針)。

一方、json-output-retry-fallback.mdが扱う構造化出力のフォーマット崩れ(パース
失敗・スキーマ不一致・値想定外・自然文とJSONの矛盾の4分類)は、LLM応答の
確率的なゆらぎに起因して平常運用時にも一定頻度で発生しうる事象であり、
同ドキュメントの「ログ・監視」節が既に「日次で一定件数(暫定1日5件)を超えたら
プロンプト改善を検討する」という品質チューニング目的のトリガーを設計済みである。
この性質の違い(ゼロベースライン異常 vs. 非ゼロベースラインの品質シグナル)から、
他4venture・1節/2節と同じ「60分・1件以上」のしきい値をそのまま転用すると、
平常運用でも頻繁に発火し誤報(アラート疲れ)を招く。このため本節では横展開ではなく
別設計としたうえで、json-output-retry-fallback.mdの日次方針をCloud Monitoring
アラートポリシーに素直に落とし込む方針を採った。

### 5.2. ログベース指標(Log-based Metric)

- 対象イベント: json-output-retry-fallback.mdの「フォールバック方針」に該当した
  会話(リトライ1回でも解消せず`needs_owner_check: true`相当として扱われた会話)で
  発生する構造化ログ(`.py`実装・結合実装フェーズ持ち越し、2.1節と同様に本フェーズは
  設計のみ)。
  ```python
  logger.warning(
      "Structured output could not be recovered after 1 retry; "
      "falling back to needs_owner_check=true (confirmed=false).",
      extra={"json_fields": {
          "event": "json_structured_output_fallback",
          # 1: 構文エラー / 2: キー不足・余分 / 3: 値の型・列挙値想定外 / 4: 自然文とJSONの矛盾
          "failure_category": "schema_mismatch",
      }},
  )
  ```
  severityはWARNING(他4venture側の`chatbot_intent_classification_failed`と同じ
  考え方。フォールバック経路で安全側〈`needs_owner_check: true`・`confirmed: false`〉
  に処理が続くため顧客影響は限定的だが、LLM API側の障害・プロンプト劣化の兆候を
  把握する目的で記録する)。
- 種別: カウンタ型。
- 名前(案): `line_reservation_ai_json_output_fallback_count`
  (2.2節と同じ`<venture-prefix>_`接頭辞方針を踏襲)。
- フィルタ:
  ```
  resource.type="cloud_run_revision"
  jsonPayload.event="json_structured_output_fallback"
  severity="WARNING"
  ```
- ラベル: `failure_category`(4値固定・低カーディナリティ)を含める。json-output-
  retry-fallback.mdの「どのケース(1〜4)で落ちたかを分類してログに残し、実装
  フェーズでのプロンプトチューニングの材料にする」という既存方針をそのまま
  指標のラベルとして反映したもの(2.2節の`entry_point`と同じ考え方)。
  ```
  labelExtractors:
    failure_category: "EXTRACT(jsonPayload.failure_category)"
  ```

### 5.3. アラートポリシー

- 条件: 「直近24時間のローリングウィンドウで合計6件以上」発生した場合に発火する
  しきい値アラート(`count > 5`, 集計は`sum`、`failure_category`でグループ化
  しない)。json-output-retry-fallback.mdの暫定しきい値「1日5件」を「超えた場合」
  なので`count > 5`(6件目で発火)とした。
- 1節・2節と異なり60分窓を採用しない理由は5.1節の通り(品質シグナルを日次で
  捉える設計のため)。
- 通知チャネル: 2節・3節・他4venture共通のCloud Monitoring標準メール通知チャネル
  (`OWNER_ALERT_EMAIL_PLACEHOLDER`)をそのまま使う。本アラートもjson-output-
  retry-fallback.mdが既に想定していたプロンプト改善検討のトリガーという位置づけで
  あり、宛先・経路を新設する理由がないため。

これにより、4節(旧版)で未検討としていた本venture独自の第二の検知対象の設計を
完了した。

## 6. 5.3節しきい値(日次6件以上)の検証方針の具体化(フェーズ続き350)

4節で残課題としていた「5.3節のしきい値(日次6件以上)は実LLM運用データが無い
現時点では仮置き」について、実運用データが得られた後にどう再検証するかの方針を
具体化する。本節も設計のみで、実際の指標値収集・しきい値変更自体は実`google-
cloud-firestore`導入・本番LLM API接続後(結合実装フェーズ以降)に行う。

### 6.1. 暫定しきい値をそのまま初期値とする理由

5.3節の「1日5件を超えたら」は、json-output-retry-fallback.mdが他の数値的根拠
なしに置いた暫定値である。実運用前に数値だけを変更しても恣意的な調整に
過ぎないため、初回リリース時はこの暫定値をそのまま採用し、後述の再検証
手順でのみ変更する(初回リリース前に「それらしい数字」へ差し替えることは
行わない)。

### 6.2. 再検証のトリガー条件

次のいずれか早い方の時点で再検証を実施する。

- (A)本番稼働開始から4週間経過した時点(曜日・時間帯による変動をならすため、
  最低でも4週分=28日分のデータが必要という判断。kura-pasha・aircon-pasha等
  他ventureの類似の「実運用データが無い」系の暫定値見直しでも同様の最低期間を
  今後踏襲できるよう、本節が先例となる)。
- (B)4週間経過前でも、本アラート(5.3節)が2回以上連続して発火した場合
  (暫定値が実態と乖離して頻発しているか、逆に本当にプロンプト劣化が
  起きている可能性があるため、期間を待たず即座に生データを確認する)。

### 6.3. 再検証時の具体的な手順

1. Cloud Loggingから対象期間の`json_structured_output_fallback`イベントを
   `failure_category`別に日次集計する(クエリは2節と同じフィルタをベースに
   `failure_category`でグルーピング)。
2. 日次発生件数の分布(p50・p90・最大値)を算出する。p90を「通常運用でも
   時々起こりうる上限」とみなし、新しいしきい値候補を「p90 + 安全マージン
   (p90とp50の差分、または最低1件のいずれか大きい方)」として機械的に算出する
   (他venture側のアラート設計〈1節・2節〉が採用する「ゼロベースライン・即時
   検知」とは性質が異なり、本節は品質シグナルの統計的なしきい値決定であるため、
   山勘ではなくログの実測値から導出する)。
3. `failure_category`別の内訳も確認し、特定カテゴリ(例: 構文エラー)が
   突出して多い場合は、しきい値の見直しと並行してllm-system-prompt-draft.md
   側のプロンプト改善検討にも繋げる(json-output-retry-fallback.mdが既に
   想定していた「プロンプト改善検討のトリガー」という位置づけを踏襲)。
4. 算出した新しきい値をcloud-monitoring-alert-policy-design.md(本ドキュメント)
   5.3節に反映し、実際のアラートポリシー更新(`gcloud alpha monitoring
   policies update`相当)を実施する。

### 6.4. スコープ外

- 本節はあくまで「いつ・どう再検証するか」という手順の確定であり、実測値が
  存在しない現時点で数値そのものを変更することはしない(6.1節参照)。
- 6.2節(A)の「4週間」という期間自体の妥当性は、実運用データが蓄積された
  後に実際の変動パターン(曜日性・季節性の有無)を見て再調整しうる(次回候補)。

最終更新: 2026-10-26 15:00 UTC(フェーズ続き350: 5.3節しきい値〈日次6件以上〉の
再検証方針〈トリガー条件・p90ベースの機械的な算出手順〉を6節として新規設計。
コード変更なし、回帰確認としてテスト1004件・schema検証28件を再実行しいずれも
変更なしでパスすることを確認)

## 7. Enqueue失敗検知アラート(フェーズ続き387、aircon-pashaフェーズ385の横展開・severity変更版)

aircon-pashaフェーズ385(course-set-pashaフェーズ376の横展開)が設計した「Enqueueフォール
バック発生率アラート」を、enqueue-fallback-owner-notification-design.md 5節で実装した本
venture版の構造化ログ出力に合わせて横展開する。aircon-pasha・course-set-pasha版は
`enqueue_fallback_occurred`をWARNINGとしているが、その理由は「Cloud Tasksへのenqueue失敗時に
Function A自身が同期フォールバックでFunction B相当の処理を行い、顧客への応答自体は正常に
行われる」ためである。本venture版はFunction A単一責務設計(LLM呼び出しを一切行わない)により
同期フォールバックを採用せず、enqueue失敗時はそのイベントの処理を断念する(顧客への応答が
行われない)。したがって本節では指標名・イベント名を他venture版と区別し、severityもERRORへ
引き上げる(1節「本venture固有の事情」と同じ「単純な転記にならない」横展開パターン)。

### 7.1. 実装側の対応

5節で前述の通り、`prototype/cloud_function_webhook.py`の`handle_webhook_event()`内、
`TaskAlreadyExistsError`以外の例外を捕捉する分岐に、`_logger.error(..., extra={"event":
"enqueue_failed_occurred", "webhook_event_id": ...})`を実装済み。新規テスト4件を追加し、
全1051件・schema検証28件いずれもパス(回帰なし)。

### 7.2. ログベース指標

- 名前(案): `line_reservation_ai_enqueue_failed_occurred_count`(他venture版の
  `<venture-prefix>_enqueue_fallback_occurred_count`命名規則を踏襲しつつ、`fallback`では
  なく実態に合わせ`failed`とする)。
- フィルタ(Logging クエリ言語):
  ```
  resource.type="cloud_run_revision"
  jsonPayload.event="enqueue_failed_occurred"
  severity="ERROR"
  ```
  severityをERRORとする理由は本節冒頭の通り(他venture版との差異)。1〜2節(Firestore
  依存構築失敗、ERROR)と同水準、5節(JSON構造化出力フォールバック、品質シグナル)とは
  目的が異なる。
- `webhook_event_id`はカーディナリティが高くログベース指標のラベルには不向きなため
  含めない(2節・aircon-pasha版7.2節と同じ考え方)。障害調査時はCloud Logging側の
  ログ本文を直接参照する。
- `resource.type`・`service_name`等のリソースラベル値は、他節と同様実プロジェクト
  作成後(関数デプロイ後)でなければ確定できないため引き続き要確認として残す。

### 7.3. アラートポリシー

- 条件: 上記ログベース指標が「直近60分間で合計1件以上」で発火(1〜2節・aircon-pasha版
  7.3節と同一のローリングウィンドウ・しきい値)。本venture版はenqueue失敗=顧客応答の
  欠落そのものを意味するため、件数の多寡によらず発生自体を即検知する方針とする。
- 通知チャネル: 1〜2節と同じCloud Monitoring標準メール通知チャネル
  (`OWNER_ALERT_EMAIL_PLACEHOLDER`)を共用する(ポリシー自体は指標が異なるため別個に
  作成する)。将来enqueue-fallback-owner-notification-design.md 4節の(a)/(b)選択に基づく
  LINE Push通知が実装された場合も、本アラートはそれとは経路・目的が異なる技術監視の
  補完的な位置づけとして併用する(aircon-pasha版7.3節と同じ考え方)。

### 7.4. スコープ外(引き続き次回以降の課題)

- `resource.type`のリソースラベル値は、実プロジェクト作成後に確定する(1〜2節と同様)。
- 実際のログベース指標・アラートポリシーの作成(`gcloud logging metrics create`および
  `gcloud alpha monitoring policies create`相当の操作)は、GCPプロジェクト作成後にオーナー
  承認の範囲内で実施する。
- enqueue-fallback-owner-notification-design.md 4節で未確定のLINE Push通知送信元((a)/(b))
  の決定は、本節の範囲外として次回フェーズに残す。
- 残る横展開先(event-komiguai-pasha・forklift-pasha・kura-pasha・oshien-pasha)は、各venture
  自身の`dispatch_webhook_events()`実装(同期フォールバック方式か本venture版の断念方式か)を
  個別に確認した上で対応する必要があり、本フェーズでは範囲外とし次回以降の課題として残す。

最終更新: 2026-11-15 02:00 UTC(フェーズ続き387: enqueue-fallback-owner-notification-design.md
5節で実装したenqueue失敗時の構造化ログ出力〈`enqueue_failed_occurred`〉に対するCloud
Monitoringアラート設計を7節として新規追加。aircon-pashaフェーズ385の横展開だが、本venture
固有の「同期フォールバックを行わない」設計差異によりseverityをWARNINGからERRORへ変更。
コード変更は5節側で実施済み、本節自体はドキュメントのみ。テスト1051件・schema検証28件
いずれもパス(回帰なし))
