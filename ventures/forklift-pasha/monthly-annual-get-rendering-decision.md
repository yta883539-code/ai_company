# monthly/annual区分のGET動的レンダリング要否の検討(フェーズ264)

## 背景

フェーズ263次回候補(3)「monthly/annual区分のGET動的レンダリング要否の検討(daily区分のみ
design.md適用範囲、他2区分は「車両を追加」枠以外の前回値キャッシュ需要があるかを確認してから
着手判断)」に対応する。机上検討のみで、実コード化は行わない(行う場合も次回以降に持ち越す)。

## 1. 現状のマークアップ構造の違い

daily.html/daily-empty.htmlは`<input type="text" name="inspector_name" value="...">`・
`<input type="date" name="date" value="...">`という**フォーム入力欄**として点検者名・実施日を
表示しており、`prototype/daily_form_render.py`の`render_daily_form_html()`はこの`value="..."`
属性を正規表現で置換する実装になっている(フェーズ263)。

一方、`web-form-mockup/monthly.html`(374〜383行目)・`web-form-mockup/annual.html`
(300〜309行目)は、点検者名・実施日を`<span class="value">山田 太郎</span> <a class="edit-link"
href="#">変更</a>`という**表示用span+変更リンク**の形式で表示しており、`<input value="...">`
形式ではない。この構造的な違いにより、既存の`render_daily_form_html()`はmonthly.html/
annual.htmlにはそのまま適用できず、適用する場合は別途span向けの置換パターンを新規実装する
必要がある(既存コードの流用はできない)。

## 2. 実施日(date)のキャッシュ要否

inspector-name-date-prefill-design.md(フェーズ261)2節の結論「実施日は常に『当日』でよく
キャッシュ機構は不要」というロジックは、点検実施当日にその場でフォームに記入するという
運用前提に基づくものであり、この前提はdaily・monthly・annualのいずれの区分でも変わらない
(月次・年次点検も「点検を実施した日」にその場で記録することが想定される)。したがって
実施日については、monthly/annualでもdailyと同じ「キャッシュ不要・当日日付を動的注入すれば
よい」という結論がそのまま当てはまると判断する。

## 3. 点検者名キャッシュの要否

daily区分で点検者名キャッシュを設計した根拠(inspector-name-date-prefill-design.mdフェーズ261)
は、「毎日同じ名前を入力する負担」という高頻度反復入力の負荷軽減にあった。頻度で比較すると:

| 区分 | 頻度 | 同一入力者の反復度 |
| --- | --- | --- |
| daily | 1日1回 | 非常に高い(毎日の反復入力) |
| monthly | 1月1回 | monthly-checklist-decision.md(フェーズ81)が既に指摘した通り、dailyより反復度・負荷軽減効果は相対的に小さいと見込まれる |
| annual | 1年1回 | さらに低頻度で、前回値キャッシュによる負荷軽減効果はほぼ無視できる水準と見込まれる |

加えてannual区分は、web-form-mockup/annual.html冒頭のコメント(12〜15行目)が示す通り
`inspector_company`(検査業者名)という別フィールドを必須自由記述欄として追加する設計に
なっている。年次の特定自主検査は登録検査業者への外部委託が多いと見込まれ(安衛則第151条の24、
monthly-checklist-decision.mdフェーズ83で確認済みの条文マッピング)、事業者単位で「前回と
同じ検査業者」が継続する保証はdaily区分の「同じ事業者内の点検者」よりも弱い可能性がある。
この`inspector_company`のキャッシュ要否は本フェーズの検討範囲外の別論点であり、今回は判断
しない。

## 4. 決定

1. **実施日の動的注入**: monthly/annualについても、将来実装する場合はdaily同様「キャッシュ
   不要・当日日付を注入するだけでよい」という設計方針を適用する。優先度は高くないが、
   実装自体はdaily向けの日付注入ロジック(`today_jst_date_str()`、フェーズ263)を流用できる
   見込みのため、着手コストは低い。
2. **点検者名のキャッシュ**: monthly/annualは頻度がdailyより大幅に低く、前回値キャッシュに
   よる負荷軽減効果もdailyより小さいと見込まれるため、**本フェーズでは着手を見送る**。
   実顧客ヒアリング(オーナー承認待ち)でmonthly/annualについても同様のニーズが確認できた
   場合に実装着手を検討する(customer-interview-design.mdへの質問追加は次回候補とする)。
3. **検査業者名(inspector_company)のキャッシュ要否**: annual固有の別論点として切り出し、
   本フェーズでは判断を見送る(次回候補として持ち越す)。
4. **実装方式**: monthly/annualのマークアップは`<span class="value">...</span>`形式で
   daily(`<input value="...">`形式)と異なるため、将来実装する場合は`render_daily_form_html()`
   を流用せず、span向けの新規置換関数を実装する必要がある。

本フェーズはコード変更なし(机上検討のみ)。既存テスト(`python3 -I -m unittest discover -s
prototype -p "test_*.py"`121件・`python3 -I schema/validate_test_cases.py`11件・
`python3 -I prototype/run_all_tests.py`26ファイル全件)いずれもパス(回帰なし)。実LLM/LINE/
Stripe/GCP/Firestore API接続・支払い・アカウント作成・外部公開・送信は一切行っていない。

## 次回候補(フェーズ264時点)

1. customer-interview-design.mdに、monthly/annual区分の点検者名・検査業者名キャッシュ需要
   (daily同様の負荷軽減効果があるか)を確認する質問を追加する検討。
2. (優先度低)monthly/annualの実施日動的注入のみを先行実装する場合の設計・実コード化
   (点検者名キャッシュは見送ったまま、日付のみ)。
3. annual固有の`inspector_company`キャッシュ要否の検討。
4. 他venture・アイデア領域の前進。

最終更新: 2026-11-24 14:00 UTC(フェーズ264定例更新: 新規作成。monthly/annual区分のGET
動的レンダリング要否を検討し、実施日はdaily同様キャッシュ不要の方針を適用可能、点検者名
キャッシュは頻度の低さから本フェーズは見送り、annual固有のinspector_companyキャッシュ要否は
別論点として持ち越しと判断した。コード変更なし、既存テスト121件・schema検証11件・
run_all_tests 26ファイルいずれもパス、回帰なし)
