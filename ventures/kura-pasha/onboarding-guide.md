# 新規職人向けオンボーディングガイド(初回メモ、フェーズ96)

これまでpricing-plan.md・tech-stack.md・craftsman-account-linking-design.md・
usage-counter-workshop-key-design.md等で料金プラン・技術構成・LINE user_id紐付け・
workshop単位の利用回数管理は個々に設計してきたが、他venture(aircon-pasha・
course-set-pasha)には既にある「申込から実際にLINE公式アカウントで受注内容整理メモ等の
生成が始まるまで、職人は何をどの順番で行うのか」という一連の導入フローの整理
(onboarding-guide.md)自体がcross-venture parityギャップとして本ventureに未着手のまま
残っていた。aircon-pasha/onboarding-guide.mdの構成を踏襲しつつ、本venture固有の
(1)craftsman-account-linking-design.mdで確定済みの「LINE友だち追加時にコードを発行する」
方式(aircon-pashaの申込フォーム主導方式とは逆順)、(2)workshop単位の複数職人プランの
存在、(3)低頻度・高単価の受注特性(月数件〜十数件、trial-end-condition-design.mdの
30日期間上限)を反映する。

**本ドキュメントは手順の設計のみを行うものであり、実際の申込受付・課金開始・LINE公式アカウントとの
連携等の運用は一切行わない。**

## 前提

- 対象は非エンジニアの個人〜小規模事業者(独立の鞍職人・馬具師、複数職人が在籍する工房、
  乗馬クラブ専属で継続的に依頼を受ける業態。candidate-longlist-draft.mdの区分に対応)。
- line-reservation-aiと異なり、営業時間・予約枠等の複雑な初期設定は不要。ただし
  aircon-pasha・course-set-pashaと異なり、契約単位が`user_id`ではなく
  `craftsman_workshop/{workshop_id}`であるため、「誰を工房の代表(契約者)とみなすか」の
  判定(craftsman-account-linking-design.md 3節)がオンボーディング手順の一部として必要になる。

## オンボーディングの全体フロー(案)

1. **LINE公式アカウントの友だち追加・連携コード発行**
   craftsman-account-linking-design.md 1節で確定した方式の通り、course-set-pashaと同じ
   「LINE友だち追加が先」の順序を踏襲する。職人が本venture用LINE公式アカウントを友だち
   追加すると、`follow`イベント受信時に6桁の連携コードが発行されウェルカムメッセージで
   届く(実装済みの範囲はcraftsman-account-linking-design.md参照、実LINE公式アカウントの
   開設自体はオーナー承認待ち)。

2. **申込フォームでの連携コード入力・工房登録**
   職人がLP(landing-page-copy-draft.md)経由で申込フォームに入力する。
   - 入力項目: 屋号(または工房名)・連携コード(手順1で受け取った6桁)・連絡先
     メールアドレス・想定利用形態(個人/複数職人での共同利用、pricing-plan.mdの
     「複数職人プラン」該当有無の目安)。
   - 連携コードの照合により`craftsman_workshop/{workshop_id}`が新規作成され、
     手順1で友だち追加したLINEアカウントの`user_id`がその工房の契約者(代表)として
     紐付けられる(craftsman-account-linking-design.md 2節)。この時点ではpricing-plan.mdの
     無料トライアル条件(30日間、trial-end-condition-design.md)に従い課金は発生しない。
   - 複数職人プランを想定する場合、代表者以外の職人分のLINE友だち追加・招待コード入力を
     追加で行うことで同一workshopに参加できる(craftsman-account-linking-design.md
     5節・11.1〜11.4節参照)。具体的には、代表者がLINEトーク上で「職人を追加したい」等の
     意思表示をすると招待コードが発行され、代表者が追加したい職人へ転送する。追加される
     職人が本venture用LINE公式アカウントを友だち追加したうえで招待コードを送ると、
     手順1の新規workshop作成用コードとは別の解決ロジックにより既存workshopへ合流する
     (`prototype/workshop_linking.py`・`cloud_function_webhook.py`として実装・テスト
     済み。契約者を含め5名を暫定上限とする〈craftsman-account-linking-design.md
     11.7節〉)。本項目は2026-09-22 20:00 UTC時点でonboarding-guide.md作成(フェーズ96)
     当時は「次のステップ候補」として残っていたが、その後craftsman-account-linking-
     design.mdのフェーズ97〜104で設計・実装とも解消済みであり、本ガイドの記載が
     追いついていなかった(cross-document parityの記載漏れ)ため今回訂正した。

3. **接続テスト・試験生成**
   代表者が、実際の受注を模した簡単なメモ(例:「テスト、区分: 新規制作、ブリティッシュ鞍、
   牛革、競技用、納期3ヶ月」)を公式LINEアカウントへ送り、mvp-flow-draft.mdの3出力
   (受注内容整理メモ・納品案内下書き・お手入れ案内下書き)が想定通り返ってくるかを本番の
   依頼者対応前に確認してもらうステップ。aircon-pasha・course-set-pashaの「接続テスト・
   試験生成」に相当し、本ventureも会話状態を持たない単方向バッチ処理(tech-stack.md)の
   ため1往復のみで完結する。

4. **本番運用開始**
   代表者(または参加職人)が試験生成の内容に問題ないと判断したら、実際の受注・納品の都度
   メモを送信し、返ってきた下書き(出力1〜3)を業務に用いる運用を開始する。修理可否の判断・
   採寸・型紙作成・革選定・縫製・仕上げ等の専門的判断はAIが行わない(mvp-flow-draft.md
   「実際の制作作業との境界」)。
   - **メモ入力時の留意事項**: 依頼者以外の第三者(他の馬主・関係者等)の氏名・連絡先等は
     メモへの記載を避けるか、必要な場合は本人を特定できない表現(「所有者様」等)で
     記載してください。出力2(納品案内)・出力3(お手入れ案内)は依頼者本人への転送を
     前提とするため、第三者を特定できる記載がそのまま含まれると、職人自身の意図に
     反して第三者の個人情報が依頼者へ開示されるおそれがあります(厳守事項9、
     requester-personal-info-inclusion-handling-design.md参照)。

5. **トライアル終了・プラン選択**
   trial-end-condition-design.mdの判定(トライアル開始から30日経過、または将来的な生成回数
   条件との論理和)に従い、トライアル終了時は自動課金せず、代表者に利用実績をLINEで
   レポートし、継続を希望する場合のみプラン(ライト/スタンダード/複数職人)を選択する。
   限度接近時の通知はlimit-approaching-notification-design.mdの設計に従う。

## 他ventureとの違い(まとめ)

- LINE友だち追加が先・フォームで連携コードを入力する順序はcourse-set-pashaと共通
  (aircon-pashaは逆順)。craftsman-account-linking-design.md 1節で確定済みの理由
  (低頻度・高単価の受注特性ではLINE上で完結する導線の方が職人にとって手数が少ない)を
  そのまま踏襲した。
- 契約単位が`workshop_id`であり、代表者(契約者本人)の判定手順がオンボーディングの一部と
  して必要になる点は他3ventureに無い本venture固有の構造。
- 月間利用回数が他ventureより一桁少なく(pricing-plan.md想定月数件〜十数件)、
  trial-end-condition-design.mdが期間上限(30日)を優先する設計としているため、
  手順5のトライアル終了は「生成回数到達」よりも「30日経過」で迎える職人が多いと見込まれる
  (aircon-pashaの「生成回数到達が先に来る想定」とは逆の傾向)。

## 未検証の仮説(要検証)

- (フェーズ178で設計対応済み: first-generation-self-check-notification-design.md参照。
  手順3〈接続テスト〉を代表者が実際に自発的に行うか、省略して本番の依頼者対応を開始し
  誤った内容〈修理可否判断の混入等〉に気づかないまま運用が始まるリスクに備え、workshop単位の
  初回生成成功時に確認案内を1回だけ付記する設計を確定した。実装自体は未着手のため
  次フェーズ以降の課題として残る。)
- 複数職人プランにおいて、代表者以外の職人が実際にどの程度の頻度で自分自身のLINEアカウント
  から直接メモを送るか(工房によっては代表者が全職人分をまとめて代行送信する運用になり、
  複数職人プラン自体の価値(共同利用)が実態としては薄い可能性がある)。

## 次のステップ候補

- (フェーズ184で対応済み)手順4に、依頼者以外の第三者の氏名・連絡先等をメモへ記載する
  際の留意事項(厳守事項9、requester-personal-info-inclusion-handling-design.md参照)を
  追記した。
- 手順1のLINE公式アカウント連携手順について、スクリーンショット付きの詳細な手順書を
  作成する(実LINE API接続着手時(オーナー承認待ち)にあわせて着手するのが効率的。
  aircon-pasha・course-set-pasha・line-reservation-aiの同種課題と合わせて着手できる)。
- (フェーズ164で対応済み)本ガイドの各ステップを、想定顧客ヒアリング
  (customer-interview-design.md)の設問に「導入のどのステップで最も不安・手間を感じるか」
  「複数職人プランの場合、代表者以外の職人が自分で送信する運用を実際に望むか」を確認する
  項目として反映した(問11への追記・条件付き新設問13として追加)。ヒアリング実施自体は
  オーナー許可が必要なアクションのため未実施。
