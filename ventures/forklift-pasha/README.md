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
- フェーズ5(2026-10-03 04:00 UTC): pricing-plan.mdの「次のステップ候補」だったllm-api-cost-
  estimate.md相当の原価試算を新規作成した。claude-apiスキルで2026年10月時点の現行料金表
  (Haiku 4.5/Sonnet 5.5/Opus 5.5)を確認し、システムプロンプト+スキーマ(約9,300文字)・
  点検メモ入力・構造化出力の3要素からシナリオA/Bの2通りでトークン数を概算、生成1回あたりの
  コスト(Opus 5.5・シナリオBで約5.43円)を試算した。pricing-plan.mdの従量単価(80〜100円)・
  基本料実質単価(22.6〜39.2円)と比較し、最も保守的な組み合わせでも最安の基本料実質単価の
  約24%にとどまり十分な粗利が残ることを確認した。プロンプトキャッシュ適用時の試算(Sonnet
  5.5で約1.45円、キャッシュなし比約47%削減)も行った。実LLMでの動作検証・fixtureファイル
  作成・実顧客ヒアリングは未着手。承認不要な原価試算文書作成のみで、外部サービスへの公開・
  アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。
- フェーズ6(2026-10-03 05:00 UTC): フェーズ5の「次のステップ候補」だったfixtureファイル
  (テストケース)の作成に着手した。kura-pasha等の既存「パシャッと」シリーズと同型の
  schema/validate_test_cases.py(外部ライブラリ非依存のpure stdlib簡易バリデータ)を新規
  作成し、正常系8件(type=daily/monthly/annualの各ケース、reminder_noticeの有無、annual
  での検査業者名記載)+ネガティブ3件(厳守事項3違反・reminder_notice常時null違反・
  status排他性違反の検出確認)、計11件のテストケースを用意して全件パスを確認した
  (output-samples-validation.md)。実LLMでの動作検証・llm-quality-verification-plan.md
  相当の文書作成・実顧客ヒアリングは未着手。承認不要なテストスクリプト・文書作成のみで、
  外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。
- フェーズ7(2026-10-03 07:00 UTC): output-samples-validation.mdの「次回候補」2点目だった
  llm-quality-verification-plan.mdを新規作成した。kura-pasha等の既存文書と同じ位置づけで、
  llm-system-prompt-draft.mdの厳守事項1〜7ごとに検証観点・判定方法(機械チェック/人手)・
  対象ケース(G1〜G4・OOS1・II1〜II3)を整理し、3回中1回でも不合格なら要改善とする基準や
  トークン数計測手順を他venture同様に定めた。あわせて、本venture未実装だった絵文字不使用
  (厳守事項7)の機械チェック用スクリプトが他ventureのpost_generation_checks.py相当に
  未着手であることを明示し次の課題とした。実LLMでの動作検証・llm-quality-verification-
  results-template.mdの切り出し・実顧客ヒアリングは未着手。承認不要な検証計画文書作成の
  みで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。
- 最終更新: 2026-10-03 07:00 UTC(フェーズ7: llm-quality-verification-plan.mdの新規作成)
- フェーズ8(2026-10-03 08:00 UTC): llm-quality-verification-plan.mdが「本venture未実装」と
  明示していた、厳守事項7(絵文字不使用)の機械チェック用スクリプトを新規作成した。
  kura-pasha/course-set-pasha/aircon-pashaのprototype/post_generation_checks.pyと同じ
  位置づけで、prototype/post_generation_checks.pyを新規作成し、(1)厳守事項7の絵文字
  不使用チェック(inspection_record.body・reminder_notice・out_of_scope_message・
  missing_fields_requestの全出力本文を対象)、(2)厳守事項6(点検記録整形・期限管理以外の
  要求には応答しない)の機械チェックとして、status=generated時の本文に修理の実施・部品
  調達・費用見積り等の対象外キーワードが紛れ込んでいないかの判定、の2つを実装した。
  schema/validate_test_cases.pyのPOSITIVE_CASES(G1〜G4・OOS1・II1〜II3)を再利用した
  回帰テストに加え、絵文字混入・対象外キーワード混入を意図的に仕込んだネガティブケースの
  検出確認もあわせてprototype/test_post_generation_checks.pyとして新規作成した(本venture
  初のprototype/ディレクトリ)。`python3 -m unittest discover -s prototype -p "test_*.py"`
  (11件、新規)・`python3 schema/validate_test_cases.py`(11件、変更なし)いずれもパスを
  確認した。実LLMでの動作検証・llm-quality-verification-results-template.mdの切り出し・
  実顧客ヒアリングは未着手。承認不要なスクリプト・テスト作成のみで、外部サービスへの公開・
  アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。
- 最終更新: 2026-10-03 08:00 UTC(フェーズ8: prototype/post_generation_checks.pyを新規
  作成し、厳守事項6・7の機械チェックを実装。prototype/test_post_generation_checks.pyも
  新規作成し、既存fixtureの回帰確認11件・schema検証11件いずれもパス)
- フェーズ9(2026-10-03 09:00 UTC): llm-quality-verification-plan.md「記録先」節が
  「実LLM検証着手の承認が下りた時点で切り出す」としていたllm-quality-verification-
  results-template.mdについて、kura-pasha/aircon-pasha/course-set-pashaは承認を待たず
  机上作業として先行して用意していることを確認し、本ventureも同じ方針に揃えて新規作成した。
  schema/validate_test_cases.pyのG1〜G4・OOS1・II1〜II3(8正常系ケース)に対応する空の
  記録表(厳守事項1・4・5・6・7、II1〜II3の必須項目欠落別、トークン数実測欄)を用意した。
  表の記入自体は実LLM接続の承認後に行う。実LLMでの動作検証・実顧客ヒアリングは未着手。
  承認不要な記録表(空テンプレート)の作成のみで、外部サービスへの公開・アカウント作成・
  支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。
- 最終更新: 2026-10-03 09:00 UTC(フェーズ9: llm-quality-verification-results-
  template.mdを新規作成し、8ケース分の空の記録表を用意)
- フェーズ10(2026-10-03 10:00 UTC): 他venture(aircon-pasha・course-set-pasha・
  kura-pasha・line-reservation-ai)には既にあるが本venture未着手だったtech-stack.md自体の
  cross-venture parityギャップを解消した。kura-pasha/tech-stack.mdの構成を踏襲しつつ整理
  した結果、本ventureのmarket-research.md・mvp-flow-draft.mdがこれまで入力チャネルを
  LINE等に特定せず「メモ入力」とのみ記述していたことが判明し、他venture全てがLINE
  Messaging API前提である一方で本venture顧客層(倉庫業・運送業・建設業の現場)での
  LINE業務利用率は未検証であるという、本venture固有の未決事項を新たに明文化した
  (tech-stack.md「未検証・残課題」)。Firestoreデータモデル(`fleet_operator`・`vehicle`・
  `usage_counter`)の初回設計もあわせて整理したが実ファイル化は次回候補とした。実LLMでの
  動作検証・入力チャネルの確定・実顧客ヒアリングは未着手。承認不要な設計文書作成のみで、
  外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。
- 最終更新: 2026-10-03 10:00 UTC(フェーズ10: tech-stack.mdを新規作成。入力チャネル未確定
  という本venture固有の課題を明文化)
- フェーズ11(2026-10-03 11:00 UTC): tech-stack.mdの「コンポーネント4」が初回設計のみに
  留めていた課金・契約単位のFirestoreデータモデルを、firestore-data-model.mdとして実
  ファイル化した。line-reservation-ai/firestore-data-model.mdの構成方針を参考にしつつ、
  本ventureは「1事業者=1契約」の単純構造であるため、`fleet_operator`(契約・課金)・
  `vehicle`(車両マスタ)・`usage_counter`(月間生成回数カウンタ、kura-pashaの
  usage-counter-workshop-key-design.mdと同型)の3コレクション構成とした。点検記録本文
  自体は永続化せず点検担当者への返却のみに留める方針(mvp-flow-draft.md「範囲外」)を
  Firestore設計にも反映した。実際のGCPプロジェクト作成・Firestore有効化・入力チャネルの
  確定(tech-stack.mdの残課題)は未着手。承認不要な設計文書作成のみで、外部サービスへの
  公開・アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの
  追記なし。
- 最終更新: 2026-10-03 11:00 UTC(フェーズ11: firestore-data-model.mdを新規作成。課金・
  契約単位のFirestoreデータモデルを3コレクション構成で実ファイル化)
- フェーズ12(2026-10-03 12:00 UTC): tech-stack.md(フェーズ10)・firestore-data-model.md
  (フェーズ11)の両方が未確定・残課題として挙げていた入力チャネル確定(LINE Messaging
  API vs 汎用Webフォーム)に向けて、customer-interview-design.mdを新規作成した。他venture
  (aircon-pasha等)と同じ構成(目的→対象選定→質問項目→実施方法→留意点)を踏襲し、
  入力チャネルの検証(質問4〜6)・pricing-plan.mdの価格感覚検証(質問7)・点検種別3区分
  の分類粒度検証(質問8)・annual区分での検査業者名記載の現場適合性検証(質問9、厳守
  事項3関連)を含む全12問を整理した。対象(仮)は倉庫業3〜4件・運送業2〜3件・建設業2件の
  計7〜9件。選定基準の明文化・ロングリスト作成(interview-candidate-selection-criteria.md
  相当)・リハーサル台本作成は未着手で次回候補とした。実顧客への連絡はオーナー承認が
  必要な範囲のため、本フェーズは質問項目の設計までに留めた。実LLMでの動作検証・実顧客
  ヒアリングの実施自体は未着手。承認不要な設計文書作成のみで、外部サービスへの公開・
  アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。
- 最終更新: 2026-10-03 12:00 UTC(フェーズ12: customer-interview-design.mdを新規作成。
  入力チャネル確定に向けた全12問のヒアリング設計を整理)
- フェーズ13(2026-10-03 13:00 UTC): customer-interview-design.md(フェーズ12)の「次の
  ステップ候補」1点目だった、interview-candidate-selection-criteria.md相当の対象選定
  基準の明文化に着手した。aircon-pasha等の既存構成(必須条件→望ましい条件→除外条件→
  情報源→選定プロセス)を踏襲しつつ、本venture固有の論点として、(1)大手物流・運送
  会社の直営拠点(意思決定者が現場責任者と異なる)を除外条件に追加したこと、(2)倉庫業・
  運送業・建設業の3区分それぞれに観察すべき特記事項(LINE運用実態、運転者とドライバーの
  兼務有無、巡回体制の有無)を整理したことの2点を新設した。実在業者の特定・連絡は未着手
  (選定方法の設計のみ)。実LLMでの動作検証・ロングリスト作成・実顧客ヒアリングの実施
  自体は未着手。承認不要な設計文書作成のみで、外部サービスへの公開・アカウント作成・
  支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。
- 最終更新: 2026-10-03 13:00 UTC(フェーズ13: interview-candidate-selection-criteria.mdを
  新規作成。倉庫業・運送業・建設業の3区分ごとの選定基準・情報源・特記事項を整理)
