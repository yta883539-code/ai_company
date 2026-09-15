# cross-venture 人的サポートコスト比較(フェーズ123)

## 背景

course-set-pasha(フェーズ216)・aircon-pasha(フェーズ222)・kura-pasha(フェーズ121)・
line-reservation-ai(フェーズ続き230)の4venture全てで、時給3,000円(未検証の仮定)を
共通前提とした人的サポートコスト(オンボーディング・問い合わせ対応)の初回試算が
2026-09-15 08:00 UTC時点で完了した。course-set-pasha/support-cost-estimate.md
「残課題」は2026-09-15追記で4venture分の結果を簡単に列挙しているが、4venture間の
比較・順位付け・示唆をまとめた専用ドキュメントはまだ無かった(kura-pashaフェーズ122
「次回は他venture・アイデア領域の前進を優先候補とする」を踏まえ、本フェーズで着手)。
本ドキュメントは各venture固有のsupport-cost-estimate.mdの内容を横断比較し、示唆を
整理する。個別venture試算の前提・計算根拠自体は変更しない(参照元を参照)。

## 比較表(2ヶ月目以降、定常状態)

| venture | 月次対応コスト(機会費用) | 月次粗利額に対する比率 | 運営者1人あたり対応可能上限 | 継続対応時間/件 |
| --- | --- | --- | --- | --- |
| course-set-pasha | 500円 | 約28% | 約120顧客 | 10分 |
| kura-pasha(単一プラン) | 500円 | 約27% | 約60〜120workshop | 10分 |
| kura-pasha(複数職人プラン) | 500〜1,250円 | 約27%前後(期待値) | 同上レンジの下限側 | 10〜20分 |
| aircon-pasha | 1,250円 | 約24.5% | 約48顧客 | 25分 |
| line-reservation-ai | 1,500円 | 約26.2% | 約40顧客 | 30分 |

(出典: course-set-pasha/support-cost-estimate.md、aircon-pasha/support-cost-
estimate.md、kura-pasha/support-cost-estimate.md、line-reservation-ai/
support-cost-estimate.md 各「試算」「顧客数増加時のスケール限界」節。時給3,000円・
運営者の月間サポート対応上限20時間はいずれも4venture共通の未検証仮定。)

## 観察

1. **月次対応コストの粗利額に対する比率は4venture間で約24.5%〜28%とばらつきが小さい**。
   月額プラン価格・粗利額の絶対値が大きいventure(aircon-pasha・line-reservation-ai)は
   対応コストの絶対額も大きいが、比率で見るとcourse-set-pashaより低いか同程度であり、
   「対応コストが重い」venture・「軽い」ventureの差は絶対額ほど極端ではない。
2. **運営者1人あたりの対応可能顧客数上限は、course-set-pasha(約120顧客)を最多として
   line-reservation-ai(約40顧客)が最少**であり、約3倍の開きがある。この順位は
   line-reservation-aiのsupport-cost-estimate.md自身が示していた仮説(双方向会話ボット
   という仕組みの複雑さが店舗オーナー向けサポート負荷を高める)と整合する。
3. line-reservation-aiは「月次対応コストの絶対額が4venture中最高」かつ「対応可能顧客数
   上限が4venture中最少」の両方に該当する唯一のventureであり、4venture中で最もサポート
   体制のスケール制約が先に顕在化しうる候補と言える。ただしaircon-pashaも対応可能顧客数
   上限(約48顧客)がcourse-set-pasha・kura-pashaより顕著に低く、次点の候補である。
4. kura-pashaは複数職人プランの契約者譲渡等の追加工数を織り込んでも、単一プランと
   同水準の比率(約27%)に収まっており、他venture固有オプション(aircon-pashaの管理会社
   向けプラン等)と比べて対応コストの跳ね上がりが比較的小さい。

## 結論・示唆

- 4venture全てが「机上の未検証仮定同士を掛け合わせた粗い試算」である前提を踏まえると、
  現時点で優先的にFAQ整備・セルフサービス化・チャットボット併用等のサポート負荷軽減策を
  検討すべき最有力候補はline-reservation-ai、次点はaircon-pashaと暫定的に順位付けできる。
  ただしこれは4venture共通の「時給3,000円」「月20時間上限」という同一仮定を機械的に
  当てはめた結果であり、各venture固有の実際の運営体制・兼業状況を反映したものではない
  点に注意が必要。
- 4venture共通で「実LINE公式アカウント接続・実顧客獲得後の実測データによる再検証」が
  最優先の残課題である点は変わらない。本比較はあくまで初回の机上試算同士を並べた
  参考情報であり、実運用データが揃うまでは各venture単独の意思決定材料としては使わない。
- 本フェーズでは示唆の整理に留め、FAQ整備等の具体的なサポート負荷軽減策の設計・実装は
  次の課題として残す(いずれのventureも実LINE公式アカウント接続がオーナー承認待ちの
  ため、実装しても実顧客での検証はできない状態にある点に留意)。

## 参照元

- course-set-pasha/support-cost-estimate.md
- aircon-pasha/support-cost-estimate.md
- kura-pasha/support-cost-estimate.md
- line-reservation-ai/support-cost-estimate.md
