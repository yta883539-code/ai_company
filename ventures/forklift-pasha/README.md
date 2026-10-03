# フォークリフトパシャっと

個人経営・小規模の倉庫業・運送業・建設業向けに、フォークリフトの始業前点検・月次自主検査・
特定自主検査(年次)の実施メモを送るだけで、AIが(1)点検記録簿の記載事項を満たす整形、
(2)次回実施期限のリマインド通知下書き、をまとめて生成するサービス。

## 概要

- 対象顧客: 専任の安全担当者を置かない個人経営・従業員数名規模の倉庫業・運送業・建設業で、
  フォークリフトを1〜数台保有する事業者の経営者・現場責任者。
- 入力: 点検者が入力する簡単なメモ(車両番号・点検種別・実施日・点検項目・結果等)。
- 出力: (1)点検記録簿1行分の記載事項を満たす整形テキスト、(2)月次自主検査・特定自主検査の
  次回実施期限リマインド通知下書き。
- 実際の点検・特定自主検査の実施自体、検査標章の貼付自体、点検結果の良否判断は事業者・検査
  業者側が行う前提とし、本サービスは記録整形と期限管理のみを行う(course-set-pasha等と同型の
  「パシャッと」シリーズの方針を踏襲)。

## 原案

- ideas.md 2026-10-02 23:00 UTCの原案(名前:「フォークリフトパシャっと」)を踏襲。

## ステータス

- フェーズ1(2026-10-02 23:00 UTC): venture新規作成。WebSearchでフォークリフトの点検・記録
  義務の法的根拠(安衛則第151条の22・24・25、記録3年保存)を確認し(market-research.md)、
  原案では「始業前点検」「特定自主検査」の2点のみに絞られていたが、月次自主検査(安衛則第151条
  の22)もMVPの記録対象に含めるべきと判断した。MVPの入出力フォーマット草案(mvp-flow-draft.md)
  として、点検種別3区分(daily/monthly/annual)・入出力例・既存「パシャッと」シリーズと同型の
  status分岐方針(generated/out_of_scope/insufficient_input)を整理した。実装・実LLM検証・
  既存競合SaaSの具体的な価格比較は未着手。承認不要な調査・設計文書作成のみで、外部サービスへの
  公開・アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。
- フェーズ2(2026-10-03 00:00 UTC): mvp-flow-draft.mdの次回候補に挙げたLLMシステムプロンプト
  草案(llm-system-prompt-draft.md)を作成した。kura-pasha等の既存「パシャッと」シリーズと同型の
  status分岐(generated/out_of_scope/insufficient_input)を踏襲しつつ、annual(特定自主検査)の
  整形では検査業者名を必須項目とする厳守事項を新設した。実LLMでの動作検証・schema実ファイル化・
  競合の価格比較調査は未着手。承認不要な設計文書作成のみで、外部サービスへの公開・アカウント
  作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。
- フェーズ3(2026-10-03 01:00 UTC): llm-system-prompt-draft.mdの「次の課題」1点目として挙げた
  schema/output.schema.jsonを実ファイル化した。kura-pashaのstatus分岐パターン
  (generated/out_of_scope/insufficient_input)を踏襲し、inspection_record内にvehicle_id・
  type(daily/monthly/annual)・date・items・result・inspector_name・inspector_company・body・
  reminder_noticeを保持する構成とした。annual区分でinspector_companyが欠落している場合は
  status=insufficient_inputとする分岐(厳守事項3)、type=dailyの場合はreminder_noticeを常に
  nullとする分岐(mvp-flow-draft.md)をdescriptionに明記した。実LLMでの動作検証・
  fixtureファイル(テストケース)の作成・競合の価格比較調査・pricing-plan.mdの作成は未着手。
  承認不要なスキーマ設計文書作成のみで、外部サービスへの公開・アカウント作成・支払い・送信等は
  今回発生していないためpending-approval.mdへの追記なし。
- フェーズ4(2026-10-03 03:00 UTC): market-research.mdの「次回候補」だった既存点検記録SaaS・
  アプリの価格帯・機能の具体的な競合調査をWebSearchで実施した(カミナシ レポート: 基本料金
  25,000円〜/月、SmartDrive CheckLog、MasterCheck等)。カミナシ等の汎用現場DXツールは本venture
  想定顧客(専任の安全担当者を置かない個人経営〜従業員数名規模)には価格帯が合わず、安衛則の
  月次自主検査・特定自主検査という日本固有の法定区分に特化した低価格帯の競合は確認できなかった
  ことを価格設計の仮説とした。これを踏まえ、pricing-plan.mdを新規作成し、保有台数(1台/3台/10台)
  を主軸にした3プラン(980円/2,480円/4,980円、月間生成回数と従量課金を併用)を仮決めした。
  実LLMでの動作検証・原価試算(llm-api-cost-estimate.md相当)・実顧客ヒアリングは未着手。
  承認不要な調査・設計文書作成のみで、外部サービスへの公開・アカウント作成・支払い・送信等は
  今回発生していないためpending-approval.mdへの追記なし。
- 最終更新: 2026-10-03 03:00 UTC(フェーズ4: 競合調査・pricing-plan.mdの新規作成)
