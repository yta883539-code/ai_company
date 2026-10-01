# course-set-pashaフェーズ248「他ventureへの横展開検討」の本venture側確認

作成日: 2026-09-29 10:00 UTC(フェーズ続き289)

## 背景

course-set-pasha/chatbot-first-response-feasibility.md フェーズ248(2026-09-23)は、
一次受付自動化(LLMによる意図分類+FAQ定型回答方式)の他venture横展開検討において、
aircon-pasha・kura-pashaへは横展開可能性が高いと判断した一方、本venture
(line-reservation-ai)については「既にLLMによる会話応答・意図判定
(`intent-to-flow-mapping.md`)が中核機能として存在し、双方向の会話状態管理を前提とする
設計であるため、本ドキュメントが想定する『単方向バッチ処理への一次受付分岐追加』という
構成自体が当てはまらず、本ventureの一次受付自動化とは別の検討軸(既存の意図判定に
FAQ系インテントを追加する形)になると考えられる」として、本venture固有の検討を
「同venture側の次回以降の課題」として申し送っていた。

あわせてkura-pashaフェーズ200(2026-09-29 09:00 UTC)の「残課題」でも、「line-reservation-ai
に同種のチャットボット一次受付・意図分類モジュールが存在するかの確認(存在しない場合は
横展開候補として検討)」が次回候補として申し送られていた。本ドキュメントはこの2件の
申し送りに対応する。

## 確認結果: 既に実装済みであることを確認

intent-to-flow-mapping.md の対応表の最終行に、以下の通り既に明記されている。

> `intent: escalation` / `faq` / その他 | 任意 | (呼ばない) | 予約フロー外。
> EscalationConsolidator/NotificationLogAggregator側の処理に委ねる

つまり本ventureのLLM構造化出力(`schema/booking_output.schema.json`準拠)は、
予約の新規(`new_booking`)/変更(`change`)/キャンセル(`cancel`)に加えて、`faq`・
`escalation`をintent値として最初から含む設計になっている。

さらに、以下のドキュメント群により、FAQ・エスカレーションの判定基準・回答方式が
具体的に確立・実装済みであることを確認した。

- faq-escalation-boundary.md(2026-07-30 18:58 UTC): 厳守事項9(FAQ/雑談)と6
  (予約以外の相談→エスカレーション)の境界を、(1)予約フロー、(2)店舗設定済みの
  静的情報に基づくFAQ回答(厳守事項9a)、(3)挨拶・雑談・スパムへの定型応答
  (厳守事項9b)、(4)上記いずれにも当たらない相談の運営者エスカレーション(厳守事項6)、
  の4分類に整理済み。
- faq-response-templates.md(同日22:58 UTC): 厳守事項9a向けに、住所・アクセス/
  駐車場/支払い方法/営業時間/メニューの5項目を「登録された値をそのまま埋め込むだけ」の
  穴埋め式テンプレートとして実装し、AIによる言い換え・推測補完を排除する設計。
- owner-faq-routing-design.md・owner-operation-self-service-faq.md: オーナー向けの
  FAQ運用導線。

これらは、他3venture(aircon-pasha・course-set-pasha・kura-pasha)が意図分類レイヤーの
追加検討を始めた2026-09-23よりも約2ヶ月近く前の2026-07-30時点で、本venture独自の設計
として既に確立・実装済みであった。

## 結論

course-set-pashaフェーズ248が想定していた「既存の意図判定にFAQ系インテントを追加する形」
での対応は、実際には追加の実装作業を要しない。本venture固有の検討の結果、**本venture
(line-reservation-ai)は既に同等の機能を備えており、移植・横展開の対象ではない**と結論する。
kura-pashaフェーズ200・course-set-pashaフェーズ248がそれぞれ申し送った確認事項は、
いずれも本ドキュメントによりクローズとする。

## 構成上の違いの整理(参考)

- 他3venture(単方向バッチ処理、メモ生成が中核機能): FAQ/エスカレーション判定を、
  中核処理(メモ生成LLMコール)の手前に独立した軽量分類レイヤーとして追加する必要が
  あった(1件の問い合わせにつきLLM呼び出しが最大2回に増えるトレードオフが生じる、
  course-set-pasha/chatbot-first-response-feasibility.md参照)。
- 本venture(双方向の会話状態管理、予約処理が中核機能): 元々すべてのメッセージに対して
  1回の構造化出力LLMコールを行う設計であり、その出力schemaのintent列に`faq`/
  `escalation`を含めるだけで済むため、追加のLLM呼び出し増加というトレードオフは
  発生しない。アーキテクチャの違いに起因する設計時点の差であり、優劣ではない。

実装・実LLM呼び出し・実LINE接続の新規実施は行っていない(既存ドキュメント・既存実装の
確認のみ)。

最終更新: 2026-09-29 10:00 UTC(フェーズ続き289: 本ドキュメント新規作成。
course-set-pashaフェーズ248・kura-pashaフェーズ200の申し送り事項を確認しクローズ)
