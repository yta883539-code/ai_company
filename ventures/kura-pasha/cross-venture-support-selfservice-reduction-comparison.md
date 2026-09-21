# cross-venture サポート対応セルフサービス化・削減率比較(フェーズ155)

作成日: 2026-09-21(フェーズ155)

## 背景

cross-venture-support-cost-comparison.md(フェーズ123)は、4venture共通の時給3,000円
仮定に基づく人的サポート対応コストの**初回試算**を横断比較した。その後、course-set-pasha
(フェーズ233)・kura-pasha(フェーズ152)・aircon-pasha(フェーズ244)・
line-reservation-ai(フェーズ続き255〜256)の順で、各venture固有の
support-cost-selfservice-reduction.mdが出揃い、「FAQ整備・フロー自動化によってどの程度
対応時間を圧縮できるか」の粗い削減率試算が4venture全てで完了した。

line-reservation-aiフェーズ続き256は自ドキュメント内の追記として4venture比較コメントを
残したが、cross-venture-support-cost-comparison.mdと同様に専用の比較ドキュメントとして
独立整理されたものは無かった。本ドキュメントはそのcross-document parityのギャップを
解消し、4venture分の削減率試算を1箇所に集約する。各venture固有の試算の前提・計算根拠
自体は変更しない(参照元を参照)。

## 比較表(継続対応、2ヶ月目以降・定常状態)

| venture | 継続対応時間/件(delta前→delta後) | 削減率(目安) | 主な削減手段 |
| --- | --- | --- | --- |
| course-set-pasha | 5〜20分 → 4〜16分 | 2割弱 | 既存FAQ・案内文書の充実 |
| kura-pasha(契約者譲渡、年数件程度) | 15〜30分 → 10〜20分 | 概ね1/3程度(未検証) | 既存の自動化フロー(申請〜確認〜完了)+FAQ Q7 |
| kura-pasha(複数職人プラン招待、該当契約のみ) | 5〜10分 → 3〜7分 | 概ね3〜4割(未検証) | owner-operation-self-service-faq.md Q9(フェーズ154で追加) |
| aircon-pasha | 10〜50分 → 7〜35分(中央値25分→17.5分) | 約3割 | FAQコマンド配信導線 |
| line-reservation-ai | 中央値30分 → 15分 | 約半減 | FAQ経由の自己解決(最も楽観的な仮定) |

(出典: 各venture/support-cost-selfservice-reduction.md「粗い削減余地の試算」節。
オンボーディング工数の削減率はcourse-set-pasha〈約1/3〉のみ明記されており、他3venture
は継続対応中心の試算のため本表では継続対応を主軸に比較する。)

## 観察

1. **削減率の楽観度合いに約2倍の開きがある**。最も保守的なcourse-set-pasha(2割弱)から
   最も楽観的なline-reservation-ai(約半減)まで、同じ「FAQ・案内文書による自己解決」を
   前提にしながら見積もり幅が大きく異なる。line-reservation-aiフェーズ続き256自身が
   指摘する通り、この差は「設定変更・エスカレーション相談型の問い合わせがFAQ経由で
   どの程度自己解決されるか」という未検証の内訳比率の仮定の違いに起因する。
2. **kura-pashaのみ「フロー自体の自動化」を削減手段の主軸に据えている点が他3venture
   と質的に異なる**。他3venture(course-set-pasha・aircon-pasha・line-reservation-ai)
   は静的なFAQ・案内文書の充実が削減手段の中心だが、kura-pashaの契約者譲渡は
   contractor-transfer-design.md等によりLINE公式アカウント上のやり取り自体が既に
   自動化されたフローとして設計されており、FAQはその補助という位置づけである。
   これはkura-pasha固有の「契約者交代」という業務がそもそも存在することによるもので、
   他venture展開時にそのまま横展開できる知見ではない。
3. 4venture共通で「削減率はいずれも実測データのない机上の仮定」という限界を明記して
   おり、実LINE公式アカウント接続・実顧客獲得後の問い合わせログによる内訳比率の再検証が
   4venture共通の最優先の残課題である点は、cross-venture-support-cost-comparison.mdが
   示した初回試算の結論と変わらない。

## 結論・示唆

- 4venture間の削減率のばらつき(2割弱〜約半減)自体が「FAQ経由の自己解決率」という
  未検証仮定への感応度の高さを示しており、この仮定を実測で検証できるまでは、削減率の
  絶対値の大小をventure間の優劣判断に使わない方がよい。
- 実測データが揃った段階では、4venture共通で「問い合わせ内容のうちFAQで事前に案内済みの
  論点だったものの比率」を同一の分類基準で集計し、本比較表を実測値で置き換えることが
  次のステップになる(現時点では各venture固有の主観的な内訳仮定に基づくため、単純な
  数値比較には限界がある)。
- コード変更は無く、回帰確認としてventure全体103件(`python3 -m unittest discover -s
  prototype -p "test_*.py"`)・schema検証32件(`python3 schema/validate_test_cases.py`)
  いずれもパス(変更前と同じ結果、本ドキュメントはドキュメント整理のみのため実行結果に
  影響なし)を確認した。
