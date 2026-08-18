# デプロイ手順書(GCPアカウント作成承認後に実施)

## 位置づけ
本ドキュメントは、pending-approval.md記載の「GCPプロジェクト作成・APIキー取得(アカウント作成・
支払いが発生するためオーナー承認が必要なアクション)」が承認された際に、実際に何をどの順番で
行うかを事前に整理した実行手順書である。**本ドキュメント作成自体はアカウント作成・課金を一切
伴わない机上整理であり、承認前に着手してよい範囲内の作業として実施した。** 承認が得られるまでは
本手順書のいずれのステップも実行しない。line-reservation-ai/deployment-runbook.md・
course-set-pasha/deployment-runbook.mdと同じ位置づけのドキュメントを本venture向けに作成したもの
(両ventureには既存、本ventureには未着手だったため今回新規作成)。

これまでの設計(tech-stack.md・hosting-platform-selection.md〈line-reservation-ai流用〉・
limit-approaching-notification-design.md等)とprototype/配下のコード(cloud_function_webhook.py・
post_generation_checks.py)は、以下の手順に沿ってそのまま接続できる設計にしてある。

## line-reservation-ai・course-set-pashaとの構成上の違い(本手順書に影響する点)
- course-set-pashaと同様、会話状態を保持する双方向のやり取りがなく、「1メモ受信→LLM呼び出し→
  3種類のテキスト生成→即時返信」の単純なリクエスト/レスポンス型で完結する(tech-stack.md参照)。
  そのためline-reservation-aiのFunction B(Cloud Tasks経由の非同期本処理)・Function C
  (リマインド定期実行)に相当するものは不要で、デプロイするCloud Functionsは1関数のみ。
- 永続データストア(Firestore)は、月間生成回数カウント(`usage_counter`、コレクション
  「ユーザー1人=1ドキュメント、フィールドはmonth・countのみ」)専用の最小構成に限られる点も
  course-set-pashaと同じ。
- **本venture固有の相違点: 想定利用ペースが月60〜100件(繁忙期はさらに増加)と、
  course-set-pashaの月8〜30回より一桁多い。** そのためステップ4のCloud Functions同時実行数・
  タイムアウト設定は、course-set-pashaの初期値をそのまま流用せず、繁忙期のピーク時間帯
  (施工完了が集中しやすい夕方)の同時アクセスを見込んだ余裕を持たせる(具体的な数値は
  ステップ4参照)。
- limit-approaching-notification-design.mdで設計した「残り5回」閾値通知(3プラン共通)は
  usage_counter加算処理の一部として実装するため、ステップ2・4の対象に含める。

## 手順

### ステップ0: 前提の確認(承認後、着手前に再確認)
- オーナーが承認したのは「(1)GCPプロジェクト作成、(2)Firestore有効化(usage_counter用途のみ)、
  (3)Cloud Functionsの有効化、(4)LLM APIキー取得、(5)LINE公式アカウント・Messaging API
  チャネル開設」のどこまでかを、pending-approval.mdのオーナー回答文言で再確認する。範囲外の
  ステップ(例: 本番ドメイン取得、決済代行サービス契約等)は別途pending-approval.mdに追記して
  承認を待つ。
- line-reservation-ai・course-set-pashaと同一GCPプロジェクト内で同居させるか、venture単位で
  別プロジェクトに分けるかは、承認時にオーナーへ確認する(課金・アクセス権限の管理単位として
  別プロジェクトを推奨するのは他2件と同じ)。

### ステップ1: GCPプロジェクト作成
- 新規GCPプロジェクトを作成(プロジェクトIDは`aircon-pasha-mvp`等)。
- 請求先アカウントを紐づける(=支払い設定。この時点で初めて課金が発生しうるため、承認範囲に
  含まれていることを必ず確認してから実施する)。
- 想定コストの参考値: subscription-billing-cost-estimate.md・llm-api-cost-estimate.mdの試算。
  月60〜100件規模はcourse-set-pashaより利用量が多いため、無料枠超過の可能性はやや高い
  (両ドキュメントの試算値を参照し、超過が見込まれる場合はプラン価格への転嫁要否を
  pricing-plan.mdの前提と突き合わせて確認する)。

### ステップ2: Firestore有効化・usage_counter初期設定
- limit-approaching-notification-design.md・tech-stack.md「5. 月間生成回数カウントの保存先」の
  設計通り、Native modeでFirestoreを有効化。
- コレクションはコード側の初回書き込みで自動作成されるため、事前の手動作成は不要。
  複合インデックスを要するクエリは無いため、`firestore.indexes.json`の追加設定は不要。
- 「残り5回」閾値通知(限定1回のみ)のフラグ管理(`usage_counter`ドキュメントへの
  `notified`フィールド追加等)も本ステップで併せて初期設定する。

### ステップ3: シークレット管理
- LLM APIキー・LINE Channel Secret/Channel Access Tokenは環境変数に直書きせず、
  Secret Managerに登録し、Cloud Functionsのランタイムから参照する(他2ventureと同じ方針)。
- prototype/cloud_function_webhook.pyの各Protocol(LLM呼び出し・返信送信)は、
  Secret Manager参照に差し替えるだけで済む引数設計に既にしてある(コード変更不要、
  注入方法の変更のみ)。

### ステップ4: Cloud Functions デプロイ(1関数)
- **Webhook受信〜生成〜返信を1関数で完結**(cloud_function_webhook.py)。署名検証→
  施工メモ本文・画像添付有無の抽出→LLM呼び出し(3出力生成)→post_generation_checks.pyによる
  機械チェック(冷媒・電気系統への言及回避等)→usage_counterへの加算・上限接近通知判定→
  LINE返信送信、までを同期処理で行う。HTTPトリガー、LINE側のWebhook URLに設定。
- **同時実行数・タイムアウトは、月60〜100件(繁忙期はさらに増加)という利用ペースを踏まえ、
  course-set-pashaの初期値より余裕を持たせた設定にする**(繁忙期の夕方に施工完了報告が
  集中しうるため)。具体的な最大同時実行数の数値は、実LLM接続後の1件あたり処理時間の実測を
  待って確定する(次の課題として残す)。
- Python 3.x ランタイム、prototype/配下のコードをそのままエントリポイントとしてデプロイ
  できる設計(クラウドSDK呼び出し部分のみ後付けで注入するスタブ構成のため)。

### ステップ5: LINE公式アカウント・Messaging APIチャネル開設
- LINE Developersでチャネルを作成し、Channel Secret/Channel Access Tokenを取得、
  ステップ3のSecret Managerに登録。
- Webhook URLをステップ4の関数URLに設定し、Webhook利用をON。
- line-api-pricing.md(line-reservation-ai)の料金プランを踏まえ、MVP検証中はフリープラン
  (月間メッセージ通数上限内)での運用を基本とする。ただし月60〜100件・画像添付ありという
  利用量は他2ventureより通数を消費しやすいため、フリープラン上限との比較確認をステップ6で
  行う(次の課題)。

### ステップ6: 結合テスト
- schema/配下の期待出力・output-samples-validation.mdのパターンを、実LLM APIに投入して
  自然文・構造化出力の安定性を確認する(pending-approval.md記載の「実LLM API呼び出しによる
  自動テスト」に相当)。
- テスト用LINEアカウント(オーナー自身の個人アカウント等)からWebhookへ実メモ(+画像添付あり・
  なしの両パターン)を流し、生成〜返信までのエンドツーエンド疎通を確認する。
- usage_counterの加算・「残り5回」閾値通知が、実際のFirestore書き込みと連動して動作するかを
  確認する。
- ステップ5で洗い出したLINEメッセージ通数消費の実測値を、フリープラン上限
  (月60〜100件・繁忙期はさらに増加という前提)と突き合わせて有償プランへの切替要否を判断する。

### ステップ7: 本番投入前チェックリスト
- legal-notices-draft.mdの特定商取引法表記・プライバシーポリシーが実際のLLMプロバイダ名で
  更新されているか。
- post_generation_checks.pyの機械チェック(冷媒ガス・電気系統への言及回避、メモに無い効果の
  推測付与防止等)が実LLM出力に対して誤検知・見落としなく機能しているか(実LLM接続後に
  生成文の実例で確認)。
- pricing-plan.md・subscription-cancellation-flow-design.mdの決済代行サービス選定・契約自体は
  本ステップの範囲外(別途オーナー承認・契約が必要)。

## 未確定事項・承認前に決めておきたいこと
- 請求先アカウントの支払い方法(オーナー個人のクレジットカード等)をどれにするかは、
  承認時にオーナーから指定してもらう必要がある(本エージェントは決済手段を選定・登録できない)。
- LLM APIプロバイダ(Claude API等)の選定自体は未確定。schema/配下の構造化出力設計は
  プロバイダ非依存であるため、承認後にプロバイダを決めても手順への影響はない
  (line-reservation-ai・course-set-pashaと同じ整理)。
- ステップ4の同時実行数の具体的な数値、ステップ6のLINEメッセージ通数消費の実測は、
  いずれも承認・実接続後でなければ確定できない。
