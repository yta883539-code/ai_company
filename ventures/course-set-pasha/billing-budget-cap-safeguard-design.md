# 実GCPプロジェクト作成の承認ハードルを下げるための請求額上限(Billing Budget)安全策

## 背景
line-reservation-ai(2026-11-11 04:00 UTC、フェーズ続き386)が実GCPプロジェクト・Firestore
作成の承認依頼について、Cloud Billing Budgets & alertsによる月間予算上限+閾値到達時の
自動課金停止策を設計し、aircon-pasha・kura-pasha・oshien-pashaへ横展開済み(2026-11-13
13:00 UTC・2026-11-13 21:00 UTC記載)。本venture(course-set-pasha)もpending-approval.md
(2026-10-24 09:00 UTC記載分)で同種の実GCPプロジェクト・Firestore作成の承認依頼を抱えており、
kura-pashaフェーズ側の申し送り(「残る横展開先〈course-set-pasha・forklift-pasha・
oshien-pasha〉への同種Billing Budget安全策設計の横展開」、oshien-pashaは本リポジトリの
直前フェーズで対応済み)に対応し、本venture側でも同じ安全策を設計する。残る横展開先は
forklift-pashaの1件のみとなる。

## 本venture固有の前提確認
- tech-stack.md(コンポーネント2)の通り、本ventureもline-reservation-ai同様にGCP Cloud Run
  functions(2nd gen)を採用する設計であり、line-reservation-ai側で確認済みの「Firestore
  〈Sparkプラン〉自体は課金設定なしで利用開始できるが、Cloud Run functionsはCloud Build等
  への依存によりBlazeプラン〈課金設定〉が実質必須」という切り分けはそのまま本ventureにも
  当てはまる。
- 本ventureはCloud Storageを利用しない設計(firestore-provider-adapter-design.md相当の
  Firestoreのみ)のため、Cloud Storageバケット作成の課金設定必須化は無関係(line-
  reservation-ai・kura-pasha同様の結論)。
- 想定コスト規模: unit-economics-estimate.mdの試算によれば、1オーナーあたりのLLM API原価は
  最大プラン(セッター複数・月30回)でもキャッシュなしで約267.3円/月、決済手数料込みの
  月次粗利率は約91.2%〜94.4%と見込まれる。candidate-longlist-draft.md想定の候補母数
  (ボルダリングジム等)を踏まえると、想定される全オーナー合計の月間コストは少数オーナー×
  数百円程度の水準に留まる見込み。

## 提案: Billing Budget(予算アラート)+ 閾値到達時の自動停止による上限保証
line-reservation-ai・kura-pasha・aircon-pasha・oshien-pashaのbilling-budget-cap-safeguard-
design.mdと同じ構成を本venture用に採用する。

1. GCPプロジェクト作成・Blazeプランへのアップグレード直後に、請求先アカウント単位で
   Billing Budgetを作成する。本venture固有の想定オーナー数(構造的に少数)を踏まえ、
   他ventureと同じ月間500円を暫定予算額として採用する(50%・90%・100%到達時にオーナー宛
   メール通知)。想定オーナー数が増え、セッター複数プランの上限(267.3円/オーナー)を
   使い切るオーナーが2件を超える規模になった場合は、オーナー確認の上で引き上げる前提とする。
2. 閾値到達時に請求先アカウントを自動デタッチして課金を機械的に停止する
   `budget-cap-auto-disable`用Cloud Function(予算アラート→Pub/Sub→Cloud Function)の
   構成も、line-reservation-ai側の設計をそのまま流用する候補としてdeployment-runbook.mdへの
   追加候補とする(本venture側は既にdeployment-runbook.mdが存在するため、実GCPプロジェクト
   作成後にこの節を追記する想定)。
3. 自動停止は請求先アカウントのデタッチのみでFirestoreデータ自体の削除を伴わないため、
   復旧時はオーナー確認の上での再アタッチのみで済む(データ損失リスクを増やさない)。

## 承認依頼への反映方針
本ドキュメントは設計のみであり、実行(GCPプロジェクト作成・課金設定・Budget作成)は
依然オーナー承認が必要なアクションのため一切行わない。pending-approval.md既存エントリ
(2026-10-24 09:00 UTC記載)自体の文面は履行記録としてそのまま保持し、新規の承認依頼
エントリも追加しない(承認を求めるアクションの実体は変わらないため)。次回承認依頼の
検討・提示時には、本ドキュメントが示す「月間500円上限のBilling Budget+自動停止」を
添えて提示する。

## 未確定・今後の課題
- 500円という暫定閾値は他ventureの値をそのまま踏襲した置きの値であり、本venture固有の
  オーナー数見込み(顧客ヒアリング未実施、customer-interview-design.md参照)を踏まえた
  精緻化は今後の課題として残す。
- `budget-cap-auto-disable`用Cloud Functionの実コード化・deployment-runbook.mdへの追記は、
  実GCPプロジェクト作成後の課題として残す。
- 残る横展開先(forklift-pasha)についても同種のBilling Budget安全策設計が未着手のため、
  次回以降の横展開候補として残す。

最終更新: 2026-11-13 22:00 UTC(新規作成: line-reservation-ai/kura-pasha/aircon-pasha/
oshien-pashaのbilling-budget-cap-safeguard-design.mdをcourse-set-pasha向けに横展開。
実行〈GCPプロジェクト作成・課金設定・Budget作成〉は一切行っていない。)
