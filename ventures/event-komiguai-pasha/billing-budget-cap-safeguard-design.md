# 実GCPプロジェクト作成の承認ハードルを下げるための請求額上限(Billing Budget)安全策

## 背景
line-reservation-ai(2026-11-11 04:00 UTC、フェーズ続き386)が、実GCPプロジェクト・Firestore
作成の承認依頼を「上限が確定額に抑えられた状態での打診」にできるよう、Cloud Billing Budgets &
alertsによる月間予算上限+閾値到達時の自動課金停止策を設計し、aircon-pasha・kura-pasha・
oshien-pasha・course-set-pasha・forklift-pashaの5ventureが順次横展開してきた(forklift-pasha
フェーズ、2026-11-13 23:00 UTC「当初の横展開対象5venture全ての設計が完了」)。同フェーズの
「未確定・今後の課題」節で、本venture(event-komiguai-pasha)がpending-approval.md
(2026-10-28 06:00 UTC記載分)で同種の承認依頼を抱えているにもかかわらず、本venture他venture群
と異なる決済モデル(継続課金サブスクリプションではなくStripe one-time payment中心、
unit-economics-estimate.md前提)であるため横展開対象として一度も検討されていない旨が申し送られ
ていた。本フェーズでこの横展開対象の棚卸しを行い、本venture向けに同種の安全策を設計する。

## 「月額課金モデルではない」ことが本安全策の前提を揺るがさないことの確認
- Cloud Billing Budgetは**GCP側のクラウド利用コスト(支出)**を月次サイクルで監視する機能であり、
  監視対象は「オーナーがGoogle Cloudに支払う金額」である。本venture自身の**顧客からの収益認識
  モデル**(単発都度決済か継続課金サブスクか)とは独立した別軸の話であり、本venture特有の
  one-time payment採用(one-time-checkout-no-account-design.md)は、Billing Budgetが月次で
  機能すること自体には影響しない。
- したがって、他venture群(継続課金サブスク)で確立した「月間予算上限+自動課金停止」の設計を
  そのまま本ventureにも適用できる。本venture固有の論点は、月間予算額をどう見積もるか(=本
  venture固有のコスト構造を反映する値にするか)の1点のみである。

## 本venture固有の前提確認
- tech-stack.md(コンポーネント2)の通り、本ventureも他venture同様にGCP Cloud Run functions
  (2nd gen)を採用する設計であり、line-reservation-ai側で確認済みの「Firestore(Sparkプラン)
  自体は課金設定なしで利用開始できるが、Cloud Run functionsはCloud Build等への依存により
  Blazeプラン(課金設定)が実質必須」という切り分けはそのまま本ventureにも当てはまる。
- 本ventureはCloud Storageを利用しない設計(tech-stack.md全体・5「画像・添付の扱い」節で
  画像添付自体がスコープ外と明記、ventures/event-komiguai-pasha/*.mdをgrepしてもCloud
  Storage関連の設計文書は存在しないことを確認済み)のため、2026年2月3日以降のCloud Storage
  バケット作成の課金設定必須化は無関係(他venture同様の結論)。landing-page/配下の静的アセットは
  リポジトリ内・ホスティング側で扱う前提であり、Cloud Storageバケットを新設する設計にはなって
  いない。
- 想定コスト規模: unit-economics-estimate.md(フェーズ93)の試算によれば、1回あたりのLLM API
  原価はキャッシュなしで約4.71円(プロンプトキャッシュ利用時は約2.31円)。本venture想定顧客
  (イベント主催者、1主催者あたり月数件程度の低頻度利用、tech-stack.md・llm-api-cost-estimate.md
  前提)の構造上、他venture(月極めの継続利用)と比べて「1顧客あたりの月間利用件数」自体が
  少ない。pricing-plan.mdのスタンダードプラン(1,980円/月、含まれる件数10件)を1顧客あたりの
  最大想定利用量とすると、月間LLM原価は4.71円×10件=47.1円(キャッシュ利用時23.1円)に留まり、
  他venture(kura-pashaの1工房あたり最大約101.8円、forklift-pashaの複数台プラン1件あたり最大
  約598.4円)と比べても顧客単位の絶対額は小さい側に位置する。
- 一方、本ventureは単発利用(都度500円、アカウント登録不要、tech-stack.md「4.課金・利用回数の
  データストア」節で扱い未確定と明記)の利用者もおり、こちらは1顧客あたりの利用件数が1件単位で
  読みにくい(継続利用を前提としないため)。ただし1件あたりのLLM原価(4.71円)自体は他venture
  群の1回あたり原価と同水準であり、単発利用の件数が仮に他venture群の月間最大顧客数を上回る規模
  (数百件規模)になったとしても、件数×4.71円が月間予算の支配的な変数になる構造である。

## 提案: Billing Budget(予算アラート)+ 閾値到達時の自動停止による上限保証
line-reservation-aiのbilling-budget-cap-safeguard-design.md(2026-11-11 04:00 UTC)と同じ構成を
本venture用に採用する。本venture固有の暫定予算額は、他venture群が採用した500円
(月極め継続課金venture群の想定顧客規模に基づく値)と同水準とする。根拠は、本venture立ち上げ
初期の想定利用規模(単発利用+少数の月額プラン利用者)が、500円÷4.71円≒約106回分のLLM呼び出し
に相当し、立ち上げ初期(market-research.mdの候補1〈奈良NEVER LAND〉への初回コンタクトが
pending-approval.md 2026-10-21 03:00 UTC記載の承認待ちの段階、実顧客ヒアリング未実施)の
想定稼働件数(月数件〜数十件規模)を十分に上回る水準であるため。

1. GCPプロジェクト作成・Blazeプランへのアップグレード直後に、請求先アカウント単位でBilling
   Budgetを作成する。暫定予算額は月間500円(50%・90%・100%到達時にオーナー宛メール通知)とし、
   他5venture(aircon-pasha・course-set-pasha・forklift-pasha・kura-pasha・oshien-pasha)・
   line-reservation-aiと同額で揃える。立ち上げ初期の低稼働を踏まえた暫定値であり、単発利用・
   月額プラン利用者が増え実際の利用件数がこれを超える見込みとなった場合は、オーナー確認の上で
   引き上げる前提とする。
2. 閾値到達時に請求先アカウントを自動デタッチして課金を機械的に停止する`budget-cap-
   auto-disable`用Cloud Function(予算アラート→Pub/Sub→Cloud Function)の構成も、line-
   reservation-ai側の設計をそのまま流用する候補とする。本venture側にはdeployment-runbook.md
   相当の文書が未作成のため、新規作成時にこの構成を反映する候補として残課題に記録する。
3. 自動停止は請求先アカウントのデタッチのみでFirestoreデータ自体の削除を伴わないため、復旧時は
   オーナー確認の上での再アタッチのみで済む(データ損失リスクを増やさない)。本venture固有の
   `one_time_draft`24時間TTL(result-page-ttl-access-design.md・ttl-expiry-result-delivery-
   refund-design.md)にも影響しない(TTL失効はFirestore側の独立した仕組みであり、請求先
   アカウントのデタッチとは無関係)。

## 承認依頼への反映方針
本ドキュメントは設計のみであり、実行(GCPプロジェクト作成・課金設定・Budget作成)は依然オーナー
承認が必要なアクションのため一切行わない。pending-approval.md既存エントリ(2026-10-28 06:00 UTC
記載)自体の文面は履行記録としてそのまま保持し、新規の承認依頼エントリも追加しない(承認を求める
アクションの実体は変わらないため)。次回承認依頼の検討・提示時には、本ドキュメントが示す「月間
500円上限のBilling Budget+自動停止」を添えて提示する。

## 未確定・今後の課題
- 月間500円という暫定閾値は、立ち上げ初期の低稼働(単発利用の件数が読みにくい・月額プラン利用者
  が少数)を前提とした置きの値であり、実顧客ヒアリング(market-research.md候補1の初回コンタクト
  がオーナー承認待ちのため未実施)を踏まえた精緻化は今後の課題として残す。
- `budget-cap-auto-disable`用Cloud Functionの実コード化・deployment-runbook.md相当文書の新規
  作成(本venture未作成)は、実GCPプロジェクト作成後の課題として残す。
- forklift-pashaのbilling-budget-cap-safeguard-design.md「未確定・今後の課題」節で申し送られた
  横展開対象の棚卸しは、本フェーズをもって7venture全ての設計が完了した。

最終更新: 2026-11-14 05:00 UTC(新規作成: forklift-pasha・line-reservation-aiのbilling-budget-
cap-safeguard-design.mdをevent-komiguai-pasha向けに横展開。本venture固有のone-time payment
モデルがBilling Budgetの前提〈GCP側の月次コスト監視〉を揺るがさないことを確認した上で、暫定
予算額を他6venture同額の月間500円に設定した。これにより、line-reservation-aiフェーズ続き386
(2026-11-11 04:00 UTC)が開始した7venture横展開が全て完了。実行〈GCPプロジェクト作成・課金
設定・Budget作成〉は一切行っていない。)
