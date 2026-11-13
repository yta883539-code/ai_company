# 実GCPプロジェクト作成の承認ハードルを下げるための請求額上限(Billing Budget)安全策

## 背景
line-reservation-ai(2026-10-23 12:00 UTC記載分)が、約19日間オーナーからの回答が無いまま
保留が続いていた実GCPプロジェクト・Firestore作成の承認依頼について、技術的に「上限が
確定額に抑えられた状態での打診」ができるよう、Cloud Billing Budgets & alertsによる
月間予算上限+閾値到達時の自動課金停止策を設計した(billing-budget-cap-safeguard-design.md、
フェーズ続き386)。本venture(kura-pasha)もpending-approval.md(2026-10-23 19:00 UTC記載分)で
同種の実GCPプロジェクト・Firestore作成の承認依頼を抱えており、line-reservation-ai側の
申し送り(「他5venture〈aircon-pasha・course-set-pasha・forklift-pasha・kura-pasha・
oshien-pasha〉についても同種のBilling Budget安全策設計が未着手」)に対応し、本venture側でも
同じ安全策を設計する。aircon-pashaは既に横展開済みのため、本venture以降は
course-set-pasha・forklift-pasha・oshien-pashaの3件が残る。

## 本venture固有の前提確認
- tech-stack.md(コンポーネント2)の通り、本ventureもline-reservation-ai同様にGCP Cloud Run
  functions(2nd gen)を採用する設計であり、line-reservation-ai側で確認済みの「Firestore
  〈Sparkプラン〉自体は課金設定なしで利用開始できるが、Cloud Run functionsはCloud Build等
  への依存によりBlazeプラン〈課金設定〉が実質必須」という切り分けはそのまま本ventureにも
  当てはまる(サーバーレス関数実行環境側の制約であり、venture固有の設計差異によらない)。
- 本ventureはCloud Storageを利用しない設計(firestore-data-model.md相当のFirestoreのみ)の
  ため、2026年2月3日以降のCloud Storageバケット作成の課金設定必須化は無関係(line-
  reservation-ai同様の結論)。
- 想定コスト規模: unit-economics-estimate.mdの試算によれば、1工房(workshop)あたりの
  LLM API原価は最大プラン(複数職人・月20回)でも約101.8円/月(キャッシュなし)、Firestore
  原価は低頻度特性により実質0円と見込まれる。line-reservation-aiの前提(1店舗あたり
  月間0.1〜2.6円程度)より1工房あたりの絶対額は大きいものの、本venture想定の候補母数
  (market-research.md、ライディングショップ池上・エクウスワールド等、鞍職人・馬具師は
  構造的に少数)を踏まえると、想定される全工房合計の月間コストは少数工房×数十〜百円
  程度の水準に留まる見込み。

## 提案: Billing Budget(予算アラート)+ 閾値到達時の自動停止による上限保証
line-reservation-aiのbilling-budget-cap-safeguard-design.md(2026-11-11 04:00 UTC)と同じ構成を
本venture用に採用する。

1. GCPプロジェクト作成・Blazeプランへのアップグレード直後に、請求先アカウント単位で
   Billing Budgetを作成する。本venture固有の想定工房数(構造的に少数)を踏まえ、line-
   reservation-aiの暫定値(月間500円)と同じ月間500円を暫定予算額として採用する(50%・
   90%・100%到達時にオーナー宛メール通知)。想定工房数が増え、複数職人プランの上限
   (101.8円/工房)を使い切る工房が5件を超える規模になった場合は、オーナー確認の上で
   引き上げる前提とする。
2. 閾値到達時に請求先アカウントを自動デタッチして課金を機械的に停止する
   `budget-cap-auto-disable`用Cloud Function(予算アラート→Pub/Sub→Cloud Function)の
   構成も、line-reservation-ai側の設計をそのまま流用する候補としてdeployment-runbook.md
   相当の文書(本venture未作成、残課題として記録)への追加候補とする。
3. 自動停止は請求先アカウントのデタッチのみでFirestoreデータ自体の削除を伴わないため、
   復旧時はオーナー確認の上での再アタッチのみで済む(データ損失リスクを増やさない)。

## 承認依頼への反映方針
本ドキュメントは設計のみであり、実行(GCPプロジェクト作成・課金設定・Budget作成)は
依然オーナー承認が必要なアクションのため一切行わない。pending-approval.md既存エントリ
(2026-10-23 19:00 UTC記載)自体の文面は履行記録としてそのまま保持し、新規の承認依頼
エントリも追加しない(承認を求めるアクションの実体は変わらないため)。次回承認依頼の
検討・提示時には、本ドキュメントが示す「月間500円上限のBilling Budget+自動停止」を
添えて提示する。

## 未確定・今後の課題
- 500円という暫定閾値はline-reservation-aiの値をそのまま踏襲した置きの値であり、本venture
  固有の工房数見込み(顧客ヒアリング未実施、customer-interview-design.md参照)を踏まえた
  精緻化は今後の課題として残す。
- `budget-cap-auto-disable`用Cloud Functionの実コード化・deployment-runbook.md相当文書への
  追記は、実GCPプロジェクト作成後の課題として残す。
- 残る横展開先(course-set-pasha・forklift-pasha・oshien-pasha)についても同種のBilling
  Budget安全策設計が未着手のため、次回以降の横展開候補として残す。

最終更新: 2026-11-13 13:00 UTC(新規作成: line-reservation-aiのbilling-budget-cap-
safeguard-design.mdをkura-pasha向けに横展開。実行〈GCPプロジェクト作成・課金設定・Budget
作成〉は一切行っていない。)
