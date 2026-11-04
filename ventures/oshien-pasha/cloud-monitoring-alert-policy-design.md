# Cloud Monitoringログベース指標・アラートポリシー設計(フェーズ44・新規作成)

フェーズ43(access-url-resend-http-entry-point-design.md)の次回候補(3)「本venture用
Cloud Monitoringアラート設定の整備」に対応し、本ファイルを本venture向けに新規作成する。

他6venture(aircon-pasha・course-set-pasha・kura-pasha・forklift-pasha・
line-reservation-ai・event-komiguai-pasha)のcloud-monitoring-alert-policy-design.mdは
いずれも「Firestoreランタイム依存構築失敗」(フラグ切替方式のruntime-dependency-switching-
design.md相当文書が前提)を主対象としているが、本ventureはまだ当該文書を作成しておらず
(tech-stack.md・prototype/配下もインメモリ実装のみ)、該当する検知対象が現段階では存在
しない。したがって本フェーズでは、フェーズ42・43で設計・コード化した
`access_url_resend_handler.py`が意図的に捕捉せず上位(Cloud Functionsランタイム)へ伝播
させている2つの異常系(access-url-resend-api-design.md 3節・access-url-resend-http-
entry-point-design.md 2節で明記)を対象として設計する。

## 1. 検知対象の棚卸し

`receive_resend_request()`(フェーズ43)は`handle_resend_request()`(フェーズ42)を内部で
呼び出すが、以下2つの例外はいずれも「利用者の入力ミスではない」運用上のアラート対象として
関数内で捕捉せず、Cloud Functionsランタイムへそのまま伝播させる設計になっている
(access_url_resend_handler.py内のdocstring参照)。

1. `MultipleActiveSubscriptionsError`: 同一メールアドレスに対しStripe側で複数の有効な
   サブスクリプションが見つかった場合。fan-pass-store-protocol-design.md 3節が定める
   「同一Stripe顧客が有効なサブスクリプションを複数持たない」という単一プラン前提が
   崩れている状態を示す。
2. `FanPassNotFoundForSubscriptionError`: Stripe側に有効なサブスクリプションがあるのに、
   対応する`fan_pass`ドキュメントがFirestore側に見つからない場合。Webhook処理の未完了・
   不整合を示す。

いずれも例外が捕捉されずランタイムまで伝播するため、Cloud Functions (2nd gen / Cloud Run
functions)の標準ログ出力により`severity=ERROR`のスタックトレース付きログエントリとして
Cloud Loggingに記録される(forklift-pasha・kura-pasha等の既存設計と同じ、Cloud Functions
ランタイムの未捕捉例外ログ出力の仕様に依拠する)。

## 2. ログベース指標(Log-based Metric)

2種の異常系は意味が異なる(単一プラン前提の崩れ/Webhook処理の不整合)ため、kura-pashaが
意図分類失敗とFirestore構築失敗を2指標に分けた考え方を踏襲し、本ventureも2指標に分ける。

- 指標1: `oshien_pasha_multiple_active_subscriptions_error_count`
  - フィルタ:
    ```
    resource.type="cloud_run_revision"
    severity="ERROR"
    textPayload:"MultipleActiveSubscriptionsError"
    ```
  - 種別: カウンタ型(該当ログ1件ごとに1カウント)。
- 指標2: `oshien_pasha_fan_pass_not_found_for_subscription_error_count`
  - フィルタ:
    ```
    resource.type="cloud_run_revision"
    severity="ERROR"
    textPayload:"FanPassNotFoundForSubscriptionError"
    ```
  - 種別: カウンタ型(該当ログ1件ごとに1カウント)。
- `textPayload`によるクラス名一致でフィルタする方式は、未捕捉例外ログがCloud Functions
  ランタイムの標準フォーマット(スタックトレースを含むプレーンテキスト)で出力されるため
  である(他venture側の構造化ログ`jsonPayload.event`方式とは異なり、本2件は本フェーズでは
  構造化ログ化のコード変更を行わないため、まずはクラス名文字列一致で検知する設計とする)。
  将来`logger.exception(..., extra={"json_fields": {"event": "..."}})`相当の構造化ログに
  揃える場合は、他venture同様`jsonPayload.event`方式に切り替えることを3節の課題とする。
- `resource.type`は他venture側のcloud-functions-generation-decision.md相当の確定
  (2nd gen / Cloud Run functions)を踏襲する。本ventureには同種の決定文書がまだ無いため、
  本節の記載をもって世代選択の確定記録とする(tech-stack.md 1節のCloud Run (2nd gen)選定
  とも整合する)。

## 3. アラートポリシー

- 条件: 指標1・指標2それぞれについて「直近60分間で合計1件以上」発生した場合に発火する
  しきい値アラート(`count > 0`, ローリングウィンドウ60分, アラート集計は`sum`)。
  他venture同様、発生は即時表面化させる方針とし、しきい値を緩める理由がない。
  - 指標1(`MultipleActiveSubscriptionsError`)が発火した場合、単一プラン前提そのものが
    崩れていることを示すため、優先度は高(月額フリーパスの複数プラン化を検討する際は
    本アラート自体の設計見直しが必要になる想定、tech-stack.mdには未記載のため将来の
    検討課題として申し送る)。
  - 指標2(`FanPassNotFoundForSubscriptionError`)が発火した場合、Stripe Webhook処理
    (本venture側は未実装、fan-pass-store-protocol-design.md参照)の遅延・失敗を示す
    可能性が高く、Webhook処理側の実装・冪等性設計(フェーズ40で確定済み)とセットで
    調査する想定。
- 通知チャネル: 他venture同様、Cloud Monitoring標準のメール通知チャネル
  (`OWNER_ALERT_EMAIL_PLACEHOLDER`)を運営者自身向けの技術監視用途として新規に用いる。
  実際の送信先メールアドレス設定は、GCPプロジェクト作成(既存承認待ち事項)後にオーナー
  自身がCloud Monitoringコンソール上で設定する想定とし、本ドキュメントではプレースホルダ
  のみを定義する。

## 4. スコープ外(引き続き次回以降の課題)

- Firestoreランタイム依存構築失敗アラート(他6venture共通パターン)は、本venture側に
  runtime-dependency-switching-design.md相当のフラグ切替方式が存在しないため対象外。
  実Firestore導入方式を検討する段階になった時点で改めて検討する。
- 1節の2例外を構造化ログ(`jsonPayload.event`)化する`.py`実装への反映は、実Cloud
  Functionsデプロイ・結合実装フェーズに持ち越す。
- `resource.type`のリソースラベル値(`service_name`等)は、実プロジェクト作成後に確定する。
- 実際のログベース指標・アラートポリシーの作成(`gcloud logging metrics create`および
  `gcloud alpha monitoring policies create`相当の操作)は、GCPプロジェクト作成後にオーナー
  承認の範囲内で実施する。

## 5. venue_matcher.py後処理のconflicts検知(フェーズ82追加)

venue-matcher-llm-postprocessing-integration-design.md(フェーズ81)3節・4節で「次回以降の
課題」としていた、`apply_venue_match_postprocessing()`が検出するconflicts(LLM自己申告の
venue_matchedとvenue_matcher.pyの判定が食い違うケース)のログ出力先の結線に対応する。

1節・2節の2例外とは異なり、conflictsは「異常系ではなく観測対象の計測値」(3節参照)という
位置づけのため、本節は1節・2節とは別の指標として設計する。

### 5.1 ログ出力(実コード化済み)

`prototype/itinerary_draft_postprocessor.py`(フェーズ82)で、conflicts検出ごとに以下の
構造化ログを出力するよう実装した。

```python
logger.warning(
    "venue_match_conflict: %s",
    conflict,
    extra={"json_fields": {"event": "venue_match_conflict", **conflict}},
)
```

`json_fields`には`event`に加えconflictの4フィールド(`venue_name_input`・
`llm_claimed_matched`・`matcher_matched`・`match_confidence`)がそのまま展開される。1節の
2例外(未捕捉例外がランタイムへ伝播し、Cloud Functionsの標準ログとして`textPayload`に
記録される方式)とは異なり、本件はアプリケーションコード側で`logging`モジュールを明示的に
呼び出す設計であるため、Cloud Logging向け構造化ログハンドラ(`google-cloud-logging`の
`StructuredLogHandler`等)を導入すれば`jsonPayload`に展開される想定(他venture側の
`runtime-dependency-switching-design.md`の`logger.exception(..., extra={"json_fields":
...})`方式と同じ)。ハンドラ自体の導入・設定は5.3節のとおり実デプロイ時の課題として残す。

### 5.2 ログベース指標(Log-based Metric)

- 指標3: `oshien_pasha_venue_match_conflict_count`
  - フィルタ:
    ```
    resource.type="cloud_run_revision"
    severity="WARNING"
    jsonPayload.event="venue_match_conflict"
    ```
  - 種別: カウンタ型(該当ログ1件ごとに1カウント)。

### 5.3 アラートポリシー(1節・2節との違い)

1節・2節の2例外は「単一プラン前提の崩れ」「Webhook処理の不整合」という即時対応が必要な
不整合状態を示すため「60分で1件以上」の即時アラートとしたが、conflictsはLLMが学習時点の
知識で会場名を自己申告する以上、venue-master.jsonの更新(命名権改称・休館等)直後は
一定数発生することが想定内であり、1件発生ごとにアラートを鳴らす設計は適切ではない
(venue-matcher-llm-postprocessing-integration-design.md 1節参照)。

- 条件: 「直近24時間でのべ10件以上」発生した場合に発火するしきい値アラート(`count >= 10`、
  ローリングウィンドウ24時間、集計は`sum`)。単発の表記揺れ的な食い違いではなく、
  venue-master.jsonの更新漏れやプロンプト設計そのものの見直しが必要な規模の継続的なずれを
  検知する目的のため、1節・2節より緩いしきい値・長いウィンドウとする。
- 発火時の対応想定: 発火した場合、ログの`venue_name_input`の内訳を確認し、(a)特定の会場に
  集中していればvenue-master.json側の更新漏れ(命名権改称・休館等)の可能性、(b)多数の
  会場に分散していればvenue-name-normalization-design.mdのプロンプト設計(会場マスタの一部を
  プロンプトに含めるか等)自体の見直し材料とする(3節の想定を踏襲)。
- 通知チャネル: 1節・2節と同じCloud Monitoring標準のメール通知チャネル
  (`OWNER_ALERT_EMAIL_PLACEHOLDER`)を用いる。

### 5.4 スコープ外

- Cloud Logging向け構造化ログハンドラの実導入・設定、ログベース指標・アラートポリシーの
  実作成(`gcloud logging metrics create`等)は、4節と同様GCPプロジェクト作成後にオーナー
  承認の範囲内で実施する。
- `apply_venue_match_postprocessing()`を実際にいつ呼ぶか(Cloud Functionsエントリポイントへの
  結線)自体は、実LLM接続後の課題(venue-matcher-llm-postprocessing-integration-design.md
  4節)のまま変わらない。

最終更新: 2026-11-04 16:00 UTC (フェーズ82: venue-matcher-llm-postprocessing-integration-
design.mdフェーズ81の次回候補(1)に対応し、conflicts検知の構造化ログ出力〈`json_fields.
event="venue_match_conflict"`〉をprototype/itinerary_draft_postprocessor.pyに追加、対応する
ログベース指標・アラートポリシー〈5節〉を設計した。1節・2節の即時アラート方針とは異なり、
24時間10件以上という緩いしきい値を採用した理由を明記。新規テスト5アサーション追加〈構造化
ログ出力の検証2件・ログ出力なしケースの検証〉、既存回帰〈22件・9件・36件・21アサーション・
20アサーション〉含め全て変更なしでパス。承認が必要なアクションは今回発生していないため
pending-approval.mdへの追記なし。)

最終更新(フェーズ44の記録): 2026-11-01 02:00 UTC (フェーズ44: 新規作成。フェーズ43の次回
候補(3)に対応し、`access_url_resend_handler.py`が意図的に上位へ伝播させる
`MultipleActiveSubscriptionsError`・`FanPassNotFoundForSubscriptionError`の2例外を対象とした
ログベース指標・アラートポリシーを設計した。本venture用のFirestoreランタイム依存構築失敗
アラートは、runtime-dependency-switching-design.md相当文書が未作成のため対象外とした。
コード変更なし、設計文書のみ。)
