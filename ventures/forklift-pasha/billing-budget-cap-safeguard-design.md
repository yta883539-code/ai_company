# 実GCPプロジェクト作成の承認ハードルを下げるための請求額上限(Billing Budget)安全策

## 背景
line-reservation-ai(2026-11-11 04:00 UTC、フェーズ続き386)が、約19日間オーナーからの回答が
無いまま保留が続いていた実GCPプロジェクト・Firestore作成の承認依頼について、技術的に「上限が
確定額に抑えられた状態での打診」ができるよう、Cloud Billing Budgets & alertsによる月間予算上限
+閾値到達時の自動課金停止策を設計した(billing-budget-cap-safeguard-design.md)。この申し送りを
受けて、aircon-pasha・kura-pasha・oshien-pasha・course-set-pashaの4ventureが同種の安全策設計を
順次横展開してきた(course-set-pashaフェーズ、2026-11-13 22:00 UTC「残る横展開先はforklift-pasha
のみ」)。本venture(forklift-pasha)はpending-approval.md(2026-10-24 07:00 UTC記載分)で同種の
実GCPプロジェクト・Firestore作成の承認依頼を抱えており、今回この最後の横展開対象として同じ安全策
を設計する。

## 本venture固有の前提確認
- tech-stack.md(コンポーネント2)の通り、本ventureも他venture同様にGCP Cloud Run functions
  (2nd gen)を採用する設計であり、line-reservation-ai側で確認済みの「Firestore(Sparkプラン)
  自体は課金設定なしで利用開始できるが、Cloud Run functionsはCloud Build等への依存により
  Blazeプラン(課金設定)が実質必須」という切り分けはそのまま本ventureにも当てはまる(サーバー
  レス関数実行環境側の制約であり、venture固有の設計差異によらない)。
- 本ventureはCloud Storageを利用しない設計(firestore-data-model.md相当のFirestoreのみ、
  ventures/forklift-pasha/*.mdをgrepしてもCloud Storage関連の設計文書は存在しないことを
  確認済み)のため、2026年2月3日以降のCloud Storageバケット作成の課金設定必須化は無関係
  (他venture同様の結論)。hero-visual関連の素材(hero-visual-concept-draft.md等)はLP用の
  静的アセットとしてリポジトリ内・ホスティング側で扱う前提であり、Cloud Storageバケットを
  新設する設計にはなっていない。
- 想定コスト規模: llm-api-cost-estimate.md(60〜76行目)の試算によれば、Sonnet 5.5採用時の
  生成1回あたりの原価はキャッシュなしで約2.72円、プロンプトキャッシュ適用後は約1.45円。
  pricing-plan.mdの複数台プラン(10台まで、月220回まで)が本venture最大規模の単一顧客想定
  であり、この顧客が上限まで使い切った場合の月間LLM原価はキャッシュなしでも
  2.72円×220回=約598.4円(キャッシュ適用時は約319円)に留まる。他venture(line-reservation-ai
  の1店舗あたり0.1〜2.6円、kura-pashaの1工房あたり最大約101.8円)と比べ、本ventureは「保有台数
  に応じて課金単位が線形に増える」構造(aircon-pashaに近い)のため、顧客単位の絶対額はkura-pasha
  より大きい。一方でmarket-research.md・candidate-longlist-draft.mdが確認した本venture想定顧客
  (専任の安全衛生担当者を置かない個人経営・小規模の倉庫業・運送業・建設業)の構造的な母数の
  少なさ(建荷協経由の間接チャネルに依存する段階、kenkakyo-proposal-draft.md参照)を踏まえると、
  立ち上げ初期に想定される全顧客合計の月間コストは、少数の複数台プラン顧客×数百円〜数千円程度
  の水準に留まる見込み。

## 提案: Billing Budget(予算アラート)+ 閾値到達時の自動停止による上限保証
line-reservation-aiのbilling-budget-cap-safeguard-design.md(2026-11-11 04:00 UTC)と同じ構成を
本venture用に採用する。ただし上記の通り本ventureは顧客単位の最大原価(複数台プラン1件あたり
最大約598円/月)が他venture(line-reservation-ai・kura-pasha・aircon-pasha・oshien-pasha・
course-set-pashaが採用した暫定値500円)より大きいため、暫定予算額は500円ではなく、複数台プラン
顧客が数件立ち上がっても即座に閾値へ達しない水準として暫定的に月間3,000円を採用する(50%・90%・
100%到達時にオーナー宛メール通知)。

1. GCPプロジェクト作成・Blazeプランへのアップグレード直後に、請求先アカウント単位でBilling
   Budgetを作成する。暫定予算額は月間3,000円(複数台プラン顧客が最大5件程度稼働しても閾値に
   達しない水準、598.4円×5≒2,992円)とする。立ち上げ初期(建荷協・労働局経由の間接チャネルに
   よる顧客発見が中心、forklift-pasha想定顧客の構造的な少数性)を踏まえた暫定値であり、実際の
   契約件数がこれを超える見込みとなった場合は、オーナー確認の上で引き上げる前提とする。
2. 閾値到達時に請求先アカウントを自動デタッチして課金を機械的に停止する`budget-cap-
   auto-disable`用Cloud Function(予算アラート→Pub/Sub→Cloud Function)の構成も、line-
   reservation-ai側の設計をそのまま流用する候補とする。本venture側にはdeployment-runbook.md
   相当の文書が未作成のため、新規作成時にこの構成を反映する候補として残課題に記録する。
3. 自動停止は請求先アカウントのデタッチのみでFirestoreデータ自体の削除を伴わないため、復旧時は
   オーナー確認の上での再アタッチのみで済む(データ損失リスクを増やさない)。

## 承認依頼への反映方針
本ドキュメントは設計のみであり、実行(GCPプロジェクト作成・課金設定・Budget作成)は依然オーナー
承認が必要なアクションのため一切行わない。pending-approval.md既存エントリ(2026-10-24 07:00 UTC
記載)自体の文面は履行記録としてそのまま保持し、新規の承認依頼エントリも追加しない(承認を求める
アクションの実体は変わらないため)。次回承認依頼の検討・提示時には、本ドキュメントが示す「月間
3,000円上限のBilling Budget+自動停止」を添えて提示する。

## 未確定・今後の課題
- 月間3,000円という暫定閾値は、複数台プラン顧客の最大原価(約598.4円/月)×5件という粗い見積り
  による置きの値であり、本venture固有の実顧客数見込み(顧客発見チャネル自体が建荷協・労働局経由
  の間接連絡の承認待ちのため実顧客ヒアリング未実施、market-research.md参照)を踏まえた精緻化は
  今後の課題として残す。
- `budget-cap-auto-disable`用Cloud Functionの実コード化・deployment-runbook.md相当文書の新規
  作成(本venture未作成)は、実GCPプロジェクト作成後の課題として残す。
- line-reservation-aiの元々の横展開対象リスト(aircon-pasha・course-set-pasha・forklift-pasha・
  kura-pasha・oshien-pashaの5venture)に本ventureの設計が完了したことで、当初リストに含まれて
  いた5venture全ての横展開が完了した。一方、event-komiguai-pashaは当初リストに含まれておらず、
  pending-approval.md(2026-10-28 06:00 UTC記載分)で同種の実GCPプロジェクト・Firestore・
  Stripeアカウント作成の承認依頼を抱えているにもかかわらず、本安全策の横展開対象として一度も
  検討されていないことに気づいた。event-komiguai-pashaは他venture(継続課金サブスクリプション
  モデル)と異なり単発生成・Stripe one-time payment向けの設計(README.md 175〜176行目)である
  ため、月間課金の上限保証という前提がそのまま当てはまるかの確認を含め、次回以降の横展開検討
  (または対象外と判断する場合はその理由の明文化)候補として残す。

最終更新: 2026-11-13 23:00 UTC(新規作成: line-reservation-aiのbilling-budget-cap-
safeguard-design.mdをforklift-pasha向けに横展開。当初の横展開対象5venture全ての設計が完了。
実行〈GCPプロジェクト作成・課金設定・Budget作成〉は一切行っていない。)
