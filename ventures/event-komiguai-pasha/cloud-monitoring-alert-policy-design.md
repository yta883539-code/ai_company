# Cloud Monitoringログベース指標・アラートポリシー設計(フェーズ62・新規作成)

aircon-pashaフェーズ346の全6venture横断棚卸しで指摘された通り、本venture
(event-komiguai-pasha)は他5venture(aircon-pasha・course-set-pasha・forklift-pasha・
kura-pasha・line-reservation-ai)がいずれも備える「Firestoreランタイム依存構築失敗
アラート」設計(cloud-monitoring-alert-policy-design.md相当)を持たない、同種の設計
パターン自体が欠落した「真の横展開漏れ」であった。本ファイルを本venture向けに新規
作成し、このギャップに対応する。

## 0. 前提の確認(他venture側設計との差異)

- forklift-pashaのcloud-monitoring-alert-policy-design.md(フェーズ192)は、同venture
  既存のruntime-dependency-switching-design.md(実クラウド接続のon/offをフラグで
  切り替える設計、4関数分)を前提に、その構築失敗ログを検知する指標・アラートを
  設計したものだった。
- 本ventureにはこの前提となる「runtime-dependency-switching-design.md」相当の
  venture固有文書がまだ存在しない(tech-stack.mdフェーズ7で`organizer_account`・
  `usage_counter`の2 Firestoreコレクションの使途は確定しているが、実Firestore接続と
  モック接続をフラグで切り替える具体的な設計・関数境界〈Cloud Run functionsの
  デプロイ単位〉は未着手)。したがって本ファイルは、他venture側の指標命名規則・
  アラート条件の設計方針を先取りして整理するに留め、実装側(`.py`への`event`キー
  付き構造化ログ反映、関数境界の確定)は次回以降の課題として明示的に残す
  (forklift-pashaフェーズ192が実クラウド未接続の段階で設定値のみ先に確定した
  手法を踏襲)。
- 本ventureにはaircon-pasha・course-set-pasha・kura-pashaが備える「chatbot意図分類
  失敗」系の既存アラート(他venture側1〜3節相当)は存在しない(1.で確認の通り、
  本ventureはLINE非依存・Webフォーム単発送信構成でchatbot自体が無いため、
  forklift-pashaと同じ理由による対象外)。したがって本ファイルはFirestoreランタイム
  依存構築失敗アラートのみを対象とする。

## 1. ログベース指標(Log-based Metric)

- 種別: カウンタ型(該当ログ1件ごとに1カウント)。
- 名前(案): `event_komiguai_pasha_firestore_runtime_dependency_construction_failure_count`
  (kura-pasha・forklift-pashaの命名規則`<venture-prefix>_firestore_runtime_
  dependency_construction_failure_count`を踏襲し、将来同一GCPプロジェクト配下で
  複数venture分を運用する際の指標名衝突を避けるため`event_komiguai_pasha_`接頭辞を
  付与する)。
- フィルタ(Logging クエリ言語、他venture共通の`event`キー方式を踏襲):
  ```
  resource.type="cloud_run_revision"
  jsonPayload.event="firestore_runtime_dependency_construction_failed"
  severity="ERROR"
  ```
  `resource.type`は他venture側のcloud-functions-generation-decision.mdの確定
  (2nd gen / Cloud Run functions)をtech-stack.mdフェーズ7が踏襲済みのため、本venture
  側もこれに合わせる。本ventureにはCloud Run functionsの関数境界(フォーム送信受信・
  LLM呼び出し・TTL失効/結果返却スケジューラ〈ttl-expiry-result-delivery-refund-
  design.mdフェーズ12〉を何関数に分けるか)の確定文書がまだ無いため、`service_name`・
  `revision_name`等の具体的なリソースラベル値、および対象関数の最終的な個数は
  引き続き要確認として残す(0.で述べた関数境界確定が前提)。
- ログ出力側は、本venture自体がまだFirestoreクライアント構築処理の実装(`.py`)を
  持たないため該当コードが存在しない。将来実装時には他venture同様に
  `logger.exception(..., extra={"json_fields": {"event": "firestore_runtime_dependency_construction_failed"}})`
  相当の構造化ログに揃える方針をここで先に確定しておく。
- severityをERRORとする理由: 本事象は「フラグON時(実Firestore接続が必要な場面、
  例:`organizer_account`・`usage_counter`参照時)に接続できていない」という設定・
  権限上の不具合であり、顧客影響(フォーム送信後の生成処理失敗、利用回数カウントの
  不整合)を伴うため。他venture側の整理と同一の理由付け。

## 2. アラートポリシー

- 条件: 上記ログベース指標が「直近60分間で合計1件以上」発生した場合に発火する
  しきい値アラート(`count > 0`, ローリングウィンドウ60分, アラート集計は`sum`)。
  他venture同様、フラグON時の構築失敗は即時表面化させる方針のため、しきい値を
  緩める理由がない。
- 通知チャネル: 本venture固有の対外(主催者)向け通知経路はWebフォーム上での結果
  表示+ダウンロード構成(tech-stack.md)であり運営者自身向けではないため、本
  アラートにはそのまま流用しない。他venture同様にCloud Monitoring標準のメール
  通知チャネル(`OWNER_ALERT_EMAIL_PLACEHOLDER`)を運営者自身向けの技術監視用途
  として新規に用いる。実際の送信先メールアドレス設定は、GCPプロジェクト作成
  (既存承認待ち事項)後にオーナー自身がCloud Monitoringコンソール上で設定する想定
  とし、本ドキュメントではプレースホルダのみを定義する。

## 3. スコープ外(引き続き次回以降の課題)

- ~~本venture固有のruntime-dependency-switching-design.md相当文書(実Firestore接続と
  モック接続のフラグ切り替え設計、関数境界の確定)自体がまだ存在しないため、本節の
  指標・アラート設計を実装に反映する前提条件として、同文書の新規作成を次回候補と
  する。~~: runtime-dependency-switching-design.md(フェーズ63)で解消済み。本venture
  固有の4つのCloud Run functions(`submit_event_form`・`handle_stripe_webhook`・
  `get_result_page`・`submit_inquiry`)を関数境界として確定した。
- 1節のログ出力側(`.py`実装)への`event`フィールド構造化反映は、実
  `google-cloud-firestore`導入・本venture用Firestoreアダプタ設計とセットの結合実装
  フェーズに持ち越す。
- ~~`resource.type`のリソースラベル値(`service_name`等)・対象関数の最終個数は、
  実プロジェクト作成後に関数境界を確定した上で確定する。~~: 対象関数の個数(4関数)は
  runtime-dependency-switching-design.md(フェーズ63)1節で確定済み。`service_name`
  の具体的な値自体は実GCPプロジェクト作成後に確定する点のみ残る。
- 実際のログベース指標・アラートポリシーの作成(`gcloud logging metrics create`
  および`gcloud alpha monitoring policies create`相当の操作)は、GCPプロジェクト
  作成後にオーナー承認の範囲内で実施する。

追記: 2026-10-26 21:00 UTC(フェーズ63: runtime-dependency-switching-design.md新規
作成により、本節の前提条件だった関数境界・対象関数個数の未確定を解消したことを反映)

最終更新: 2026-10-26 19:00 UTC(フェーズ62: aircon-pashaフェーズ346が指摘した
「event-komiguai-pashaのみ同種の設計パターン自体を持たない真の横展開漏れ」に対応し、
本ファイルを新規作成。forklift-pashaフェーズ192のFirestoreランタイム依存構築失敗
アラート設計を横展開したが、本ventureには前提となるruntime-dependency-switching-
design.md相当文書自体がまだ無いため、指標命名・アラート条件の設計方針を先取りして
整理するに留め、同文書の新規作成を次回候補として明示した。これで6venture全てに
本アラート設計(または設計着手)が揃った。)
