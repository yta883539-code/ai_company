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

## 5. フェーズ265: 実施日動的注入の実コード化(次回候補(2)に対応)

4節(1)(4)の決定どおり、monthly/annualの実施日動的注入のみを先行実装した。新規モジュール
`prototype/monthly_annual_form_render.py`の`render_date_only_html()`は、1節で確認した
`<span><span class="value">...</span> <a class="edit-link" href="#">変更</a></span>`形式の
「実施日」行だけを対象とする正規表現置換を行う(直前の`<span>実施日</span>`ラベルを手がかりに
点検者名行〈同一のclass="value"構造〉と区別する、`render_daily_form_html()`〈daily.html向け、
`value="..."`属性置換〉とは別実装)。`main()`(`prototype/form_submission_flow.py`)のGET分岐に
`type=monthly`/`type=annual`を追加し、`render_monthly_or_annual_form_for_get()`経由で
monthly.html/annual.htmlを読み込み、当日日付(JST、既存の`today_jst_date_str()`を流用)のみを
注入して200で返す(`type=daily`以外は`unsupported_get_type`で400という既存方針は、daily/
monthly/annual以外の値・未指定の場合のみ残る)。access_tokenの検証(欠落400・未知404)は
`render_daily_form_for_get()`と同じ方針をそのまま適用した(将来operator固有の表示に発展する
可能性がある画面を未認証のまま返さないため、本フェーズの表示内容自体はoperator非依存でも
検証自体は行う判断とした)。点検者名行は4節(2)の決定どおり未対応のままで、テンプレート側の
ダミー値「山田 太郎」が表示され続ける(次回候補(1)参照)。

新規テスト: `test_monthly_annual_form_render.py`(`render_date_only_html()`の実施日のみ置換・
点検者名行は対象外のまま残る・HTML特殊文字のエスケープ・実施日行が無いテンプレートでの
ValueErrorの確認、4件)、`test_form_submission_flow.py`にtype=monthly/annualのGET分岐
(access_token欠落400・未知token404・正常系200・当日日付注入・点検者名ダミー値が残ることの
確認、monthly/annual各5件・計10件)を追加。既存の「type=daily以外は400」テストは
`type=weekly`(存在しない区分)・type未指定の2パターンに置き換えて維持した(monthly/annualが
対応済みになったため)。`python3 -I -m unittest discover -s prototype -p "test_*.py"`121件
(変更なし、本モジュールのテストはdaily_form_render.py同様discover非互換のscript形式のため
含まれない)・`python3 -I schema/validate_test_cases.py`11件・`python3 -I prototype/
run_all_tests.py`27ファイル(新規test_monthly_annual_form_render.py追加分、26→27)いずれも
パス(回帰なし)。実LLM/LINE/Stripe/GCP/Firestore API接続・支払い・アカウント作成・外部公開・
送信は一切行っていない(daily区分同様、実デプロイ・`<form>`action配線自体はホスティング未承認
のため依然見送り)。

## 6. フェーズ268: 検査業者名(inspector_company)キャッシュ要否の机上決定

フェーズ267次回候補(2)「annual固有の`inspector_company`キャッシュ要否自体の机上検討
(フェーズ264で切り出された論点、customer-interview-design.md Q11の回答傾向待ち)」に対応する。
実顧客ヒアリング(オーナー承認待ち、customer-interview-design.md Q11)はまだ実施できていない
ため、Q11回答を待たずに現時点で参照可能な情報(安衛則条文・既存の3節の頻度比較ロジック)のみで
机上判断できる範囲を先に決定し、Q11回答が得られた段階で再検証する方針とする。

### 6.1 検査業者「継続」の可能性に関する検討

3節は、年次の特定自主検査が登録検査業者への外部委託であること(安衛則第151条の24)を踏まえ、
「事業者単位で『前回と同じ検査業者』が継続する保証はdaily区分の『同じ事業者内の点検者』よりも
弱い可能性がある」という仮説を提示していた。この仮説を次の2方向から机上で評価する。

- **継続を支える要因**: 外部委託先の選定には、委託先の信頼性確認・見積り取得・訪問日程調整など
  一定の切り替えコストがかかるため、一度選定した検査業者を翌年も継続利用する事業者は一定数
  存在すると見込まれる(自動車の継続検査〈車検〉で同一業者を使い続ける傾向と類似する運用上の
  慣性)。
- **継続を妨げる要因**: (a)年1回しか発生しない取引のため「いつもの業者」という関係が
  dailyの「いつもの点検者(同一事業者の従業員)」より弱く、価格比較による乗り換えが起きやすい。
  (b)検査業者側の都合(廃業・対応エリア変更・予約枠の都合)による不継続もdaily(事業者内部の
  人事異動)より本人以外の要因で発生しやすい。(c)本venture利用者が複数台のフォークリフトを
  保有する場合、台数・設置場所によって依頼先を分けるケースもあり得る(単一の「前回値」に
  一意化できない可能性)。

継続を支える要因・妨げる要因の双方が存在し、どちらが優勢かを机上だけで断定する根拠はない
(3節が「今回は判断しない」とした理由はまだ解消されていない)。

### 6.2 実装コストとキャッシュ効果が顕在化するまでの期間

点検者名キャッシュ(2節で見送り済み)と同じ実装方式(前回値をFirestoreへ保存し次回フォーム
表示時にプリフィルする)を転用できる見込みだが、annualは頻度が年1回であるため、キャッシュの
効果(入力省力化)が実際に顕在化するのは**利用者が2回目の年次申請を行う時点、つまり利用開始
から最短でも約1年後**になる。これはdaily(翌日から効果が出る)・monthly(翌月から効果が出る)
に比べて、投資回収(実装コストに対する負荷軽減効果の積み上げ)が最も遅い区分である。

### 6.3 決定

**annual固有の`inspector_company`キャッシュについては、本フェーズでも着手を見送る
(2節の点検者名キャッシュ見送りと同じ結論を維持する)。** 根拠は2節が点検者名キャッシュを
見送った根拠(年1回・反復度が低い)に加えて、6.1で示した「前回と同じ検査業者が継続する保証が
点検者名以上に弱い」可能性・6.2で示した「効果が顕在化するまで最短1年を要する」投資回収の遅さの
2点が上乗せされるため、点検者名キャッシュよりも優先度は**さらに低い**と判断する。

customer-interview-design.md Q11(年次区分の検査業者継続性、フェーズ267で追加)の実ヒアリング
結果(オーナー承認待ち)が得られた段階で、この机上判断(継続性は不確実、効果は1年後)を実際の
継続率で検証し、必要であれば判断を更新する。本フェーズの決定はヒアリング実施までの暫定的な
机上結論であり、最終決定ではない。

本フェーズはコード変更なし(机上検討のみ、customer-interview-design.mdへの追記も行わない
現状維持)。既存テスト(`python3 -I -m unittest discover -s prototype -p "test_*.py"`)121件・
schema検証(`python3 -I schema/validate_test_cases.py`)11件・`python3 -I prototype/
run_all_tests.py`27ファイルいずれも変更なしでパス(回帰なし)。実LLM/LINE/Stripe/GCP/
Firestore API接続・支払い・アカウント作成・外部公開・送信は一切行っていない。

## 次回候補(フェーズ268時点)

1. customer-interview-design.md Q11の実ヒアリング結果(オーナー承認待ち)を踏まえた6.3決定の
   再検証。
2. `<form>`の実際のaction配線・送信ボタン有効化(daily区分同様、実バックエンド未接続・
   ホスティング未承認の現状では見送りを継続。承認待ち事項、launch-readiness-checklist.md参照)。
3. 承認待ち事項がオーナーから承認された場合はその着手を最優先。

最終更新: 2026-11-27 02:00 UTC(フェーズ268: フェーズ267次回候補(2)に対応し、annual固有の
`inspector_company`キャッシュ要否を机上検討。継続性を支える要因・妨げる要因の双方を整理した
上で机上だけでの断定は不可と確認、加えて効果顕在化が最短1年後になる投資回収の遅さを指摘し、2節の
点検者名キャッシュ見送りと同じ結論〈着手見送り〉を維持する暫定決定とした。ドキュメントのみの
更新でコード変更なし、既存テスト121件・schema検証11件・run_all_tests 27ファイルいずれもパス、
回帰なし)
