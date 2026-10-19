# `inquiry`コレクション命名・構造のcross-venture parity確認(フェーズ16)

inquiry-handling-design.md(フェーズ15)「未検証・残課題」1点目に残っていた、
`inquiry`コレクションの命名・構造が他ventureのエスカレーション系設計と整合しているか
(cross-venture parity)を確認する。

## 1. 他ventureのFirestoreコレクション命名規則の確認

aircon-pasha・kura-pasha・forklift-pasha・course-set-pashaの設計文書(例:
`user_profile/{user_id}`・`usage_counter/{workshop_id}`・
`craftsman_workshop/{workshop_id}`・`fleet_operator/{internal_id}`)を確認した
結果、いずれもトップレベルのFirestoreコレクション名はスネークケース(snake_case、
複数形にしない単数形)で統一されていることを確認した。本venture側の
`one_time_draft/{draft_id}`・`inquiry/{inquiry_id}`(いずれもフェーズ10・15で
確定済み)は、この命名規則(スネークケース・単数形)と一致しており、命名規則面での
不整合は無い。

フィールド名についても、他venture側の例(`current_plan_id`・`member_user_ids`・
`accessToken`等)ではスネークケースとcamelCaseが混在しているのに対し、
inquiry-handling-design.mdで定義した`inquiry`のフィールド(`draft_id`・
`customer_email`・`category`・`detail`・`status`・`created_at`)は全てスネーク
ケースに統一されている。この点は他venture側の混在よりも統一度が高いが、不整合
(他ventureのスタイルからの逸脱)とまでは言えないため、本venture側を他venture側に
合わせて混在させる必要はないと判断する。

## 2. 「問い合わせ・エスカレーション」相当の仕組みの構造比較

line-reservation-ai(本プラットフォーム群で唯一、継続的な会話チャネル〈LINE〉を
持つventure)は、`stores/{storeId}/escalationWindows/{sessionId}`という
店舗(`storeId`)配下のサブコレクションで、チャットボットが一次対応できなかった
会話を5分間の時間窓でまとめてオーナーへ即時通知する「エスカレーション」機構を持つ
(escalation-consolidation-logic.md)。これは、

- 常時稼働する会話チャネル(LINE)が前提のため、問い合わせ内容をコレクションに
  蓄積し続けるのではなく、通知後は時間窓の集計状態のみを保持する一時データ構造
  である点、
- `storeId`という契約主体(アカウント)に紐づくサブコレクションである点、

の2点で、本venture(`event-komiguai-pasha`)の`inquiry`コレクションとは前提が
異なる。本ventureはtech-stack.md(フェーズ7)の方針により継続的な会話チャネルを
持たず、かつアカウント登録なしの単発決済モデル(one-time-checkout-no-account-
design.md、フェーズ10)のため`storeId`に相当する契約主体の識別子が存在しない。
したがって`inquiry`をトップレベルの独立コレクションとし、`draft_id`を唯一の
紐付けキーとする設計は、line-reservation-aiのサブコレクション方式を機械的に
模倣するのではなく、本venture固有のアーキテクチャ制約(アカウントなし・低頻度
利用)に忠実に従った結果であり、意図的な差異であって命名・構造上の見落としでは
ないと結論する。

aircon-pasha・course-set-pasha・kura-pashaの`chatbot-intent-classification-
escalation-design.md`等も確認したが、いずれも継続的な会話チャネル(LINE公式
アカウント)を前提としたチャットボットの一次対応失敗時のオーナー通知であり、
本ventureのような「自動フロー対象外の個別問い合わせをWebフォームで受け付けて
Firestoreに蓄積するだけ」という設計(双方向チャットボット無し)に相当する前例は
他venture側に存在しない。これは、本venture以外の全ventureが継続的なサブスク
リプション課金・LINE公式アカウントを採用しているのに対し、本ventureのみが
単発決済・アカウント登録なし・低頻度利用という異なるモデルを採用している
(tech-stack.mdフェーズ7)ことに起因する構造的な違いであり、是正すべき不整合では
ない。

## 3. 結論

- 命名規則(スネークケース・単数形のトップレベルコレクション)は他venture側と整合
  している。
- 構造(店舗アカウント配下のサブコレクションではなく、`draft_id`のみをキーとする
  独立コレクション)は他venture側と異なるが、これは本venture固有のアーキテクチャ
  (アカウント登録なしの単発決済・低頻度利用・継続的会話チャネル不採用)に起因する
  意図的な差異であり、修正を要する不整合ではないと判断する。
- 本確認により、inquiry-handling-design.md(フェーズ15)「未検証・残課題」1点目は
  解消した(是正不要でクローズ)。

設計文書作成のみで実際のFirestoreコレクション作成・Webフォーム実装自体は発生して
いないためpending-approval.mdへの追記なし。

次回候補: (1)対象候補のロングリスト作成(フェーズ9から持ち越し)、(2)市場仮説
(market-research.md・competitor-comparison.md)を踏まえたcustomer-interview-
design.mdのヒアリング対象候補への反映(フェーズ13から持ち越し)、(3)問い合わせ
フォーム自体のUI草案(他venture発のフォーム系wireframeとの体裁統一検討)。

最終更新: 2026-10-19 18:00 UTC(フェーズ16: `inquiry`コレクションの命名・構造に
ついて他venture(line-reservation-aiのescalationWindows等)との cross-venture
parityを確認。命名規則は整合、構造上の差異は本venture固有のアーキテクチャ制約に
起因する意図的なものと結論し是正不要でクローズ)
