# 「有料プラン開始意図検知」(他venture厳守事項7b/6b)の横展開要否レビュー

作成日: 2026-09-12(フェーズ続き217)

## 背景

aircon-pashaフェーズ206(2026-09-12 03:00 UTC)・course-set-pashaフェーズ206
(2026-09-12 02:00 UTC)は、kura-pashaがフェーズ57〜58で新設した厳守事項7b
(LLM会話中の「有料プラン開始意図検知」→ `checkout_intent`/`pricing_inquiry`/
`checkout_intent_unclear`のstatus値と`checkout_notice`フィールドを構造化出力に追加)を、
line-reservation-ai・aircon-pasha・course-set-pashaのいずれにも未展開のcross-venture
parityギャップと認定した。aircon-pasha・course-set-pashaは既に自ventureへ翻案・移植済み
(厳守事項6b/7bとして新設)で、両者とも「line-reservation-aiへの同種横展開は次の課題として
残す」と申し送っていた。本フェーズはこの横展開の要否を検討する。

## 結論: そのままの形での横展開は不要(アーキテクチャ上の理由により対象外)

kura-pasha・aircon-pasha・course-set-pashaの3ventureは、いずれも「LINE公式アカウント上で
LLMと会話する相手」=「本SaaSの課金対象者(職人・セッター本人)」という1対1の構造である。
そのため、トライアル中の職人が通常の受注整理依頼に混ぜて「有料プランはいくらですか」
「そろそろ課金お願いします」等を尋ねてくる場面が実際に起こりうり、LLM会話の構造化出力の中で
検知して案内する設計(7b/6b)が意味を持つ。

一方、line-reservation-aiは課金対象者(店舗オーナー)とLLM会話の相手(店舗のお客様=
予約したい人)が別人である。billing-upgrade-flow-design.md・checkout-initiation-flow-design.md
で確定済みの通り、店舗オーナー向けの有料プラン案内・決済導線は
- トライアル終了時の利用実績レポート+LIFF決済リンクのプッシュ配信
  (`prototype/trial_end_report_scheduler.py`)
- オンボーディング完了メッセージへの常設セルフサービスリンク
  (`prototype/onboarding_completion_message.py`)

という「オーナー宛の一方向通知+LIFF起動リンク」の経路のみで完結しており、オーナー自身が
本venture用のLLM会話エンジン(`prototype/engine.py`)と対話する経路は存在しない
(オーナーは`owner-settings-wireframe.md`の設定画面操作、またはオーナー宛の別トークルーム
での定型通知受信のみが接点で、店舗設定はconversation-flow.mdが扱う予約会話の対象外)。

したがって、LLM会話エンジンの構造化出力に`checkout_intent`等のstatus値を追加しても、
発火しうる相手(お客様)がそもそも本SaaSの契約主体ではないため、7b/6bと同じ目的
(職人・セッター本人の課金意図の検知→決済導線提示)を果たすことができない。仮に
お客様が「こちらの予約サービスは有料ですか」のように尋ねてきた場合は、既存の厳守事項9a/9b
(店舗FAQ/雑談)または6(オーナーへのエスカレーション)で扱うべき話題であり、これは
7b/6bとは別の既存の分岐(お客様向けFAQ・エスカレーション)がそのまま対応範囲になる。

## 対応関係の整理

| | 課金対象者とLLM対話相手 | 課金意図検知の実装場所 |
|---|---|---|
| kura-pasha/aircon-pasha/course-set-pasha | 同一人物(職人・セッター) | LLM構造化出力(厳守事項7b/6b) |
| line-reservation-ai | 別人物(オーナー vs お客様) | オーナー向けプッシュ通知+LIFF決済導線(billing-upgrade-flow-design.md) |

line-reservation-aiは後者の経路が既にbilling-upgrade-flow-design.md
(2026-08-14新設)・checkout-initiation-flow-design.md(2026-08-28新設、12節まで実装
済み)で7b/6bの目的に相当する機能(有料プラン移行案内・決済導線提示)をカバー済みであり、
機能的な欠落ではなく「実装方式が違うだけ」と判断する。

## 残る検討事項(本レビューのスコープ外として明記)

- お客様(LLM対話相手)が「この予約LINEって有料ですか?」のように尋ねてくるケースの
  厳守事項9a/9b/6のいずれに振り分けるべきかは、既存のfaq-escalation-boundary.mdの
  一般的な境界整理でカバーされている前提だが、conversation-samples-test-cases.mdに
  この具体的な文言のテストケースが無いため、次回以降の課題として残す
  (E17候補: 「予約って有料ですか」のような料金体系そのものへの質問)。
- 本レビューの結論(横展開不要)は、aircon-pasha・course-set-pashaのREADME側の
  「line-reservation-aiへの同種横展開は次の課題として残す」という申し送りに対する回答に
  あたるため、両venture側で本ファイルへの参照リンクを追記できると尚良いが、
  他venture側ファイルの編集は本フェーズの範囲外とし、次回以降(該当ventureの
  作業時)に譲る。
