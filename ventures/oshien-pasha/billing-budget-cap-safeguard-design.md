# 実GCPプロジェクト作成の承認ハードルを下げるための請求額上限(Billing Budget)安全策

## 背景
pending-approval.md(2026-11-08 08:00 UTC記載、7venture共通の運営方針判断)の承認依頼は、
本時刻(2026-11-13 21:00 UTC)時点で5日間オーナーからの回答が無いまま保留が続いている。
line-reservation-ai・kura-pasha・aircon-pashaの3ventureでは、2026-11-11 04:00 UTC前後に
同種の安全策設計(billing-budget-cap-safeguard-design.md)を先行して作成済みだが、本venture
(oshien-pasha)では未着手だったため、line-reservation-ai版を土台に本venture向けに横展開する。
本ドキュメントは、実行(アカウント作成・課金設定)そのものは行わず、承認依頼のリスクを
技術的に小さく・見積もり可能にするための設計のみを行う。

## 本ventureの前提の違い
- tech-stack.mdで選定済みの構成はCloud Run(2nd gen)によるWebフォーム+バックエンド統合
  サービスであり、line-reservation-ai等と同様にCloud Build・Artifact Registry等Sparkプラン
  対象外のサービスに依存するため、Blazeプラン(課金設定・クレジットカード登録)への切り替えが
  実質必須である点は共通。
- 一方、本ventureはB2C・都度利用型(当落発表後の短期間に利用が集中、pricing-plan.md参照)で
  あり、line-reservation-aiのような店舗単位の継続利用とは利用パターンが異なる。ピーク時に
  短時間でLLM呼び出し・Cloud Run実行回数が集中する可能性がある点は、Billing Budgetの閾値を
  保守的に設定すべき追加の論点として記録する。
- 本ventureにはunit-economics-estimate.md相当の原価試算文書がまだ存在しないため、閾値額は
  line-reservation-ai同様の暫定値(月間500円)をそのまま踏襲し、確定はオーナー判断に委ねる。

## 提案: Billing Budget(予算アラート)+ 閾値到達時の自動停止による上限保証
1. GCPプロジェクト作成・Blazeプランへのアップグレード直後に、請求先アカウント単位で
   Billing Budgetを作成する(例: 月間500円を予算額とし、50%・90%・100%到達時にオーナー
   宛メール通知)。500円は暫定値であり、本venture特有のピーク集中リスクを踏まえ、実際の
   利用開始後に原価試算(unit-economics-estimate.md相当)を作成した上で見直す前提とする。
2. 予算アラートをPub/SubトピックへルーティングしCloud Functionで受信、閾値到達時に請求先
   アカウントをプロジェクトから自動的にデタッチする`budget-cap-auto-disable`構成を、
   deployment-runbook.md相当のデプロイ手順に追加候補として記録する(line-reservation-aiと
   同一パターン)。
3. 自動停止は請求先アカウントのデタッチであり、Firestoreデータ自体の削除は伴わないため、
   復旧時はオーナー確認の上で請求先アカウントを再アタッチするだけで済む。

## 承認依頼への反映方針
本ドキュメントは設計のみであり、実行(GCPプロジェクト作成・課金設定・Budget作成)は
依然オーナー承認が必要なアクションのため一切行わない。次回承認依頼の検討・提示時には、
本ドキュメントが示す「月間500円上限のBilling Budget+自動停止」を添えて提示する。

## 未確定・今後の課題
- 本venture向けの原価試算文書(unit-economics-estimate.md相当)がまだ無く、500円という
  閾値がピーク集中利用に対して十分かどうかは未検証。次回候補として作成を検討する。
- `budget-cap-auto-disable`用Cloud Functionの実コード化は、実GCPプロジェクト作成後の
  課題として残す。
- 残る2venture(course-set-pasha・forklift-pasha・event-komiguai-pasha)についても同種の
  設計が未着手のため、次回以降の横展開候補として残す。
