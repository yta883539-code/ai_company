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
- (解消済み・2026-09-18追記: 下記「FAQ自己解決導線の横展開完了と対応コストへの示唆」の
  通り、本フェーズ当時「次の課題」としていたFAQ整備等のサポート負荷軽減策は、
  2026-09-15〜18の間に4venture全てへの実装が完了した)

## FAQ自己解決導線の横展開完了と対応コストへの示唆(追記、2026-09-18 定例更新)

上記「結論・示唆」が優先候補として挙げていたFAQ整備(オーナー向けセルフサービスFAQへの
導線)は、その後2026-09-15〜18の定例更新で4venture全てに実装が完了した
(course-set-pasha: owner-faq-routing-design.md フェーズ219・2026-09-15 / kura-pasha:
同フェーズ126・2026-09-17 19:00 UTC / aircon-pasha: 同フェーズ225・2026-09-17 23:00 UTC
/ line-reservation-ai: フェーズ続き233、42e5af6以前)。いずれもLINEトークルームで
「FAQ」(またはaircon-pashaのみSELF_CHECK_NOTICE_TEXT等の初回導線、他3ventureは
ウェルカムメッセージ・オンボーディング完了メッセージ)を送ると案内が返るコマンド方式で、
LLM呼び出し・運営者対応を経由しない。

- FAQ項目数(2026-09-18時点、owner_faq_router.pyの`Q1`〜`Qn`定義数): course-set-pasha
  6件、aircon-pasha 7件、line-reservation-ai 7件(告知文コマンドの周知含む)、
  kura-pasha 8件(複数職人プラン・契約者譲渡等、本venture固有項目を含み4venture中最多)。
- 上記(b)節「継続的な問い合わせ対応時間」の内訳のうち、「通常の使い方の再質問」
  「料金プラン・トライアル条件の確認」「解約・再開方法の確認」に該当する問い合わせは、
  各ventureのFAQ項目(Q1〜Q3相当)が概ねカバーしている。一方、契約者譲渡・複数職人
  メンバー整理(kura-pasha固有)、決済失敗時の個別状況確認等、本人確認や個別状況判断を
  要する問い合わせはFAQの定型回答では代替できず、運営者対応が引き続き必要と見込まれる。
- 上記を踏まえた粗い試算(未検証の仮定): 「通常の使い方の再質問」区分の問い合わせのうち
  概ね3〜5割程度がFAQコマンドで自己解決に置き換わると仮定すると、(b)継続的な問い合わせ
  対応コストの一部(4venture共通で月1〜2件×5〜10分の区分)が圧縮される計算になるが、
  この置き換わり率自体が根拠のない仮定値であり、かつオンボーディング時間(a)・特殊対応
  (契約者譲渡等)には影響しないため、上記比較表の「月次対応コスト」全体を大きく動かす
  水準ではないと見込まれる。
- 本節もあくまで机上の見立てであり、上記「結論・示唆」が既に指摘している通り実LINE公式
  アカウント接続・実顧客対応後の実測データ(FAQコマンドの実際の利用率・利用後の運営者
  問い合わせ削減効果)による再検証が必須である点は変わらない。実測データが得られるまでは、
  比較表・順位付け自体の更新は行わない。

## 参照元

- course-set-pasha/support-cost-estimate.md
- aircon-pasha/support-cost-estimate.md
- kura-pasha/support-cost-estimate.md
- line-reservation-ai/support-cost-estimate.md
- course-set-pasha/owner-faq-routing-design.md、aircon-pasha/owner-faq-routing-design.md、
  kura-pasha/owner-faq-routing-design.md、line-reservation-ai/owner-faq-routing-design.md
  (2026-09-18追記「FAQ自己解決導線の横展開完了と対応コストへの示唆」節の出典)
