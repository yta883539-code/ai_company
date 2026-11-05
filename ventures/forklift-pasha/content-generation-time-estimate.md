# 「浮いた作業時間の目安」試算(1回あたりの手動作成時間の仮置き)

作成日: 2026-11-05(フェーズ210)

## 背景

trial-end-notification-design.md(フェーズ119)3節が「本venture向けのcontent-generation-
time-estimate.md相当の試算ドキュメントが未作成のため今回は含めない(6節『今後の課題』に
切り出す)」としたまま、aircon-pasha(フェーズ192)・kura-pasha・course-set-pashaには
既に存在する同種ドキュメントが本ventureだけ未着手のまま残っていたcross-venture parity
ギャップを解消する。

## 前提: 他ventureとの構造の違い(「台数」ではなく「点検種別」で分岐)

aircon-pasha(分解洗浄台数n)・kura-pasha(受注1件固定)とは異なり、本ventureの1回の生成は
「車両1台・1回の点検/検査」に対応し、history_rowsのような複数行配列は持たない
(schema/output.schema.jsonの通り、生成1回につき`inspection_record.body`1本+条件付きの
`reminder_notice`1本のみ)。代わりに、mvp-flow-draft.mdの点検種別3区分
(`daily`/`monthly`/`annual`)によって記載事項の量・リマインド有無が異なるため、本ventureでは
「台数」ではなく「点検種別」を試算の分岐軸とする。

## 試算(仮置き、区分ごと)

| 区分 | (1)記録簿1行分の整形 | (2)次回実施期限リマインド | 前提 |
|---|---|---|---|
| `daily`(始業前点検) | 2〜3分(中間2.5分) | 対象外(次回期限の概念が無い、mvp-flow-draft.md) | 車両番号・ブレーキ/警告灯等の定型項目の記録のみで、ライティング要素は薄い。 |
| `monthly`(月次自主検査) | 4〜6分(中間5分) | 2〜3分(中間2.5分、期限が近い場合のみ発生) | 油圧系統等の記載が加わり項目数が増える分、記録文言がdailyより長くなる。リマインドは前回実施日+1ヶ月の算出+通知文作成。 |
| `annual`(特定自主検査) | 5〜7分(中間6分) | 2〜3分(中間2.5分、期限が近い場合のみ発生) | 検査業者名の記載・告示第321号切替への目配り(mvp-flow-draft.mdフェーズ45)等、記載事項が3区分で最も多い。リマインドは前回実施日+1年の算出+通知文作成。 |

AIによる生成自体は数秒〜数十秒で完了し、利用者側の作業は生成結果の確認・微修正(1〜2分程度と
仮定、他venture同様に削減効果の対象時間からは除外)にとどまるため、削減効果は上記の時間に
ほぼ等しいとみなす。

## 1回あたりの単一値への統合(トライアル期間中の生成はdailyが大半を占めるとの仮定)

trialGenerationCount・trialEndEmailの文言(trial-end-notification-design.md 3節)はいずれも
点検種別を区別せず生成回数のみを数えるため、区分別の試算を単一の代表値に統合する必要がある。
market-research.mdの点検種別ごとの実施頻度(daily=稼働日ごと、monthly=月1回、annual=年1回)を
用いて、1ヶ月あたりの生成回数比で加重平均する(稼働日数は仮に月20日と仮定)。

```
加重平均(分) = (20×2.5[daily] + 1×5[monthly、リマインド未加算] + (1/12)×6[annual、リマインド未加算])
              ÷ (20 + 1 + 1/12)
            = (50 + 5 + 0.5) ÷ 21.083
            ≈ 2.63分
```

monthly/annualのリマインド加算分(発生頻度がさらに低い〈期限7日前以内のみ〉ため影響は
軽微)は保守的に見積もりへ含めず、daily(稼働日ごとに発生し生成回数の大半を占める)を支配的な
要因として扱った。30日間の無料トライアル期間中に発生する生成もほぼdailyが占めると見込まれる
(monthly・annualがトライアル期間中に1回も発生しないケースも多い)ため、上記2.63分を単一の
代表値として丸めた**3分/回**を採用する。

## 採用値・実装への反映

- `prototype/trial_management.py`に`BASE_MINUTES_PER_GENERATION = 3`・
  `estimate_trial_minutes_saved(generation_count)`(=`3×generation_count`)・
  `format_minutes_saved_line(generation_count)`を実装した(フェーズ210)。
- (A)経路(`record_generation_and_get_trial_end_notice()`、返却テキストへの追記)・
  (B)経路(`trial_end_email_scheduler.render_trial_end_email_body()`、メール本文)の両方が
  `format_minutes_saved_line()`を共通で呼ぶことで、trial-end-notification-design.md 3節の
  既存方針(「回数到達だから」「期間到達だから」で文言を分けない)を維持したまま、通知文言に
  「浮いた作業時間の目安: 約○分(1回の点検記録整形につき平均3分と仮定)」の1行を追加した。

## 残課題

- 上記の値はすべて仮置きであり、実ヒアリングによる検証は未実施。customer-interview-design.md
  に時間感覚を尋ねる質問が既にあるか次回棚卸しする。
- 区分別の試算(表)を単一値(3分/回)に統合した加重平均は、稼働日数を月20日と仮定した粗い
  見積りであり、実際の事業者の稼働日数・月次/特定自主検査の実施頻度のばらつきによって変動する。
- monthly/annualのリマインド加算分を単一値の算出に含めなかったため、月次/特定自主検査の
  比率が高い事業者(フォークリフト複数台保有・頻繁な自主検査実施等)では実際の削減時間を
  過小評価する可能性がある。区分別の内訳を`trialGenerationCount`とは別に記録するフィールドの
  追加(本venture未着手)により精度を上げられる可能性があるが、本フェーズでは既存フィールドの
  範囲内で単一値化する方針とした。

最終更新: 2026-11-05 03:00 UTC(フェーズ210: trial-end-notification-design.md〈フェーズ119〉
「今後の課題」1点目の未作成ギャップを解消。点検種別〈daily/monthly/annual〉ごとの試算を
行った上で、trialGenerationCountが種別を区別しないことを踏まえ加重平均により単一の代表値
〈3分/回〉へ統合。prototype/trial_management.pyに実装)
