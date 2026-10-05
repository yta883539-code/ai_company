# 技術構成案(初回メモ)

他venture(aircon-pasha・course-set-pasha・kura-pasha・line-reservation-ai)には既にあるが
本venture未着手だったtech-stack.md自体のcross-venture parityギャップに対応する初回メモ。
kura-pasha/tech-stack.mdの構成を踏襲しつつ、本venture固有の特性(点検種別3区分
(daily/monthly/annual)で利用頻度が大きく異なること、課金主体が保有台数単位であること、
pricing-plan.md参照)を反映する。

## 全体構成イメージ

点検担当者 ⇄ (Web/チャット入力フォーム) ⇄ Webhook/バックエンド ⇄ LLM(記録整形+リマインド
下書き生成) ⇄ 整形済みテキストの返却

他「パシャッと」シリーズと同様、双方向の会話状態管理は不要な単方向バッチ処理
(「1点検メモ受信 → LLM呼び出し → 構造化出力生成 → 返却」)で完結する。本ventureは
mvp-flow-draft.md・schema/output.schema.jsonの設計時点でLINE Messaging APIへの依存を
前提にしておらず、入力チャネルをLINEに限定するか汎用Webフォームにするかは未確定のまま
ここまで進んでいたため、本メモでチャネル選定を明文化する。

## 想定コンポーネント

1. **入力チャネル(暫定決定: 汎用Webフォーム優先)**
   - 他venture(aircon-pasha・course-set-pasha・kura-pasha・line-reservation-ai)はいずれも
     LINE公式アカウントを入力チャネルとして選定済みだが、本ventureの想定顧客(美容室・
     ジム等の対個人向けサービス業と異なり、倉庫業・運送業・建設業の現場)はLINE公式
     アカウントの業務利用率が未検証のまま、実顧客ヒアリング(customer-interview-
     design.md相当)自体が外部への連絡を伴いオーナー承認待ちのため確定時期が見通せない
     状態が続いていた(フェーズ10〜12)。承認待ちの間もMVP設計を前進させるため、本フェーズ
     (70)で暫定決定に切り替える。
   - 暫定決定: 入力チャネルは**汎用Webフォーム(LINE非依存)を第一候補**とする。理由は
     (1)本ventureの会話状態管理は不要な単方向バッチ処理(mvp-flow-draft.md)であり、
     LINE Messaging API固有の機能(リッチメニュー・LIFF等)に依存する設計上の必要性が
     そもそも薄いこと、(2)LINE公式アカウント開設はaircon-pasha等で実際に外部アカウント
     作成・オーナー承認待ちとなっている依存を本ventureにも追加することになり、Webフォーム
     であればその依存を1つ減らせること、(3)倉庫業・運送業・建設業の現場では個人携帯での
     LINE利用よりも、点検担当者がPC/タブレットでURLを開いて入力する運用(月次・特定自主
     検査等の低頻度な区分)や、現場に据え置いたタブレットのブラウザから入力する運用の方が
     実態に合う可能性があると判断したため。
   - daily(始業前点検、月20〜25回/台)の高頻度入力については、Webフォームでも入力項目を
     ボタン選択・プルダウン中心にして入力負荷を下げる方向で設計する(具体的なUI設計は
     次回候補)。LINE(リッチメニュー/LIFF)は将来的な追加チャネルの選択肢として残すが、
     MVPの前提とはしない。
   - 本決定は机上の設計判断による暫定決定であり、実顧客ヒアリング(承認後に実施)の結果、
     対象業種で実際にLINE業務利用率が高いことが判明した場合は見直す前提とする。
2. **Webhook / バックエンド**
   - line-reservation-aiで選定済みのGCP Cloud Functions (Python) 2nd gen (Cloud Run
     functions)を他venture同様に第一候補として流用する(hosting-platform-selection.md・
     course-set-pasha/cloud-functions-generation-decision.mdの確定を踏襲)。実際のGCP
     プロジェクト作成・請求先設定は着手時にオーナー承認が必要。
   - market-research.mdで確認した通り、既存の汎用現場DXツール(カミナシ等)は想定顧客には
     価格帯が合わないため、本ventureは低コストなサーバーレス従量課金構成を維持する前提。
3. **LLM(記録整形・リマインド下書き生成)**
   - 入力メモ → llm-system-prompt-draft.mdの厳守事項リストに沿って、type(daily/monthly/
     annual)別のinspection_record整形と、type=monthly/annualの場合のreminder_notice
     下書きを構造化出力形式(schema/output.schema.json)で生成する(type=dailyの場合は
     reminder_noticeを常にnullとする分岐、mvp-flow-draft.md)。
   - prototype/post_generation_checks.py(フェーズ8)で絵文字不使用(厳守事項7)・対象外
     応答の混入(厳守事項6)を機械チェック済み。
   - llm-api-cost-estimate.md(フェーズ5)の試算通り、プロンプトキャッシュ適用でさらに
     コストを抑えられる見込み(他venture同様、daily利用頻度が高い顧客ほどキャッシュ効果
     が大きい)。
4. **課金・契約単位のデータストア(Firestore)**
   - `fleet_operator/{operator_id}`: `plan_id`(ライト/スタンダード/複数台)・保有台数・
     `stripe_customer_id`・`subscription_status`・`trial_start_at`・`current_period_end`等。
     pricing-plan.mdの課金軸が「保有台数」であるため、他venture(course-set-pasha等の
     「生成回数」主軸)よりaircon-pashaの「屋号単位」の構造に近い。
   - `vehicle/{vehicle_id}`: `operator_id`・車両番号等、点検記録の紐付け用の最小限の
     マスタ情報。
   - `usage_counter/{operator_id}`: 月間生成回数の積算(`month`・`count`)。
     kura-pashaのusage-counter-workshop-key-design.mdと同様、プラン間でカウンタ参照ロジック
     を分岐させずoperator_idキーで一貫させる方針とする。
   - 上記は本メモでの初回設計であり、実ファイル化(schema/output.schema.jsonとは別の
     Firestoreデータモデル設計文書としての切り出し)は次回候補とする。
5. **画像の一時保存**
   - 他venture同様、画像内容の自動解析は行わず「添付の有無」のみを判定材料とする設計
     (専用の永続ストレージは不要)。本venture固有の検討事項として、annual(特定自主
     検査)では検査標章の写真添付が実務上有用な可能性があるが、画像解析自体は範囲外とする
     方針は他ventureと同じく維持する。

## MVPスコープ(最小構成)

- 入力は1メッセージ=1回の点検メモ(pricing-plan.mdの課金単位「1メモ送信=1回」に対応)。
- 会話状態マシンは不要(他venture同様)。
- 画像は「有無」のみを判定材料とし、画像内容の自動解析は範囲外。
- 課金・回数上限管理はoperator(事業者)単位、保有台数に応じたプラン選択(コンポーネント4)。

## 初期投資・ランニングコストの目安

- 開発: 既存クラウドサービス・LLM APIの組み合わせのみで、専用インフラ購入は不要。
- ランニング: 入力チャネル(LINE Messaging API等、確定後)の無料枠+LLM API従量課金+
  Firestore読み書き課金。llm-api-cost-estimate.mdの試算通り、daily区分の高頻度利用でも
  pricing-plan.mdの単価に対し十分な粗利が残る見込み。

## 未検証・残課題

- 入力チャネルはコンポーネント1の通り汎用Webフォーム(LINE非依存)を暫定決定したが
  (フェーズ70)、机上判断であり実顧客ヒアリング(承認後実施)での検証が必要。
- Webフォームのボタン選択・プルダウン中心のUI詳細設計(daily区分の入力負荷低減、次回候補)。
- Firestoreデータモデルの実ファイル化(本メモのコンポーネント4は初回設計段階)。
- 実際のGCPプロジェクト作成・Webフォームのホスティング・Stripeアカウント接続は、
  他ventureと同様にアカウント作成・支払いが発生するためオーナー承認待ちの範囲
  (pending-approval.md参照)。今回は技術構成の整理のみに留める。

最終更新: 2026-10-05 22:00 UTC(フェーズ70: 入力チャネルを汎用Webフォーム〈LINE非依存〉に
暫定決定。顧客ヒアリングが承認待ちで確定時期が見通せないため、机上判断でMVP設計を前進させた)
