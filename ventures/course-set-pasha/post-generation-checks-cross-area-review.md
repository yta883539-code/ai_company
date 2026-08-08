# post_generation_checks.py 見逃し(false negative)の発見と修正

## 背景
README「次にやること」に残っていた、`post_generation_checks.py`のヒューリスティック
(近傍探索の窓幅15文字、キーワード一覧)が仮の値であり見直しが必要という課題に対し、
実LLM接続を待たずに機械的な机上レビューで確認できる範囲(複数エリアが同じ投稿文に
混在するケース)に着手した。line-reservation-aiのE16(複合質問でのtopic重複検証)や
本venture自身のmulti-area-mixed-case-review.mdと同様の「複数項目が同じ文面に混在する
ときに判定ロジックが破綻しないか」の観点。

## 発見した問題
旧実装は、エリア名の出現箇所ごとに前後15文字の固定窓を切り出し、その窓内に
NEW_CONTENT_KEYWORDS(「新着」等)があり、かつUNCHANGED_KEYWORDS(「変更ありません」等)が
無ければ違反として検出していた。

この固定窓は前後どちらの方向にも及ぶため、対象エリアとは無関係な**別エリアの**
「変更ありません」が窓内に入り込むと、対象エリア自身が新着扱いされている本物の違反を
誤って見逃す(false negative)ケースがあることが分かった。

例:
```
エリアDは変更ありません。エリアCに新着課題を追加しました。
```
`unchanged_areas=["エリアC"]`のとき、本来は「エリアCが新着扱いされている」ため
厳守事項2違反として検出すべきだが、旧実装では「エリアC」の前方15文字に
「エリアDは変更ありません」の「変更ありません」が入り込み、`has_unchanged=True`と
誤判定されて検出漏れとなっていた。

既存のテスト(`test_unchanged_area_mentioned_with_unchanged_wording_is_allowed`)は
逆方向(前の文の「新着」が対象エリア自身の「変更ありません」文と共存して正しく
許容される)ケースのみをカバーしており、この見逃しパターンは未検出のまま残っていた。

## 修正内容
`_find_suspicious_area_mentions()`を固定文字数の近傍窓から、「。」区切りの文単位判定に
変更した。対象エリア名を含む文の中だけでNEW_CONTENT_KEYWORDS/UNCHANGED_KEYWORDSの有無を
見るため、別の文にある無関係なエリアの「変更なし」文言が紛れ込むことがなくなる。

`prototype/post_generation_checks.py`・`prototype/test_post_generation_checks.py`に
回帰テスト(`test_unrelated_areas_unchanged_wording_does_not_mask_real_violation`)を
追加。既存の全8件(新規1件含む)・schema検証6件・history_export関連6件、いずれもパス
確認済み。

## 追記(2026-08-08 15:00 UTC): 読点区切りケースへの対応
上記で「次の課題」として残していた、「エリアDは変更なし、エリアCは新着課題を追加」の
ように**読点区切りで1文にまとまっている**ケースに対応した。

対応方針は読点そのものでの分割ではなく、`unchanged_areas`と`history_rows[].area`から
集めた「既知のエリア名一覧」を境界として文をセグメント分割する方式を採用した
(`_split_into_area_segments()`新規実装)。各セグメントは、あるエリア名の出現位置から
次のエリア名の出現位置の直前まで(無ければ文末まで)となる。読点そのものを区切り文字と
すると、「エリアCは、新着課題を追加しました。」のように対象エリア自身の説明文中に
読点が含まれる(日本語では主語の直後に読点を打つスタイルが一般的)ごく普通のケースまで
誤って分断してしまい、かえって見逃しを増やす(新たなfalse negative)リスクがあったため、
「他の既知エリア名が出現する位置」を境界とする方式にした。既知のエリア名が対象エリア
以外に無い場合は文全体を1セグメントとして扱うため、この種の誤分断は起きない。

`prototype/post_generation_checks.py`の`check_unchanged_areas_not_mentioned_as_new()`は
`history_rows`からも変更エリア名を収集して`_find_suspicious_area_mentions()`に渡すように
変更した(unchanged_areasの記載漏れ・列挙不足があっても、実際に変更したエリアの言及が
境界として機能する)。回帰テスト4件を`prototype/test_post_generation_checks.py`に追加
(読点区切りでの新着扱い検出、真に変更なしエリアの誤検出無し、対象エリア自身の読点での
誤分断無し、history_rows由来のエリア名での境界機能)。既存分含め全12件・schema検証6件・
history_export関連6件、いずれもパス確認済み。

## 残る既知の限界
既知のエリア名一覧(`unchanged_areas`∪`history_rows[].area`)に**どちらにも載っていない**
第三のエリア名が同じ文中に登場するケース(例:入力メモに記載の無いエリアへの言及、
LLMの誤生成による架空のエリア名)は、セグメント分割の境界として認識できないため、
引き続き旧来の文単位判定と同じ理屈で見逃しうる。この種のケースは入力メモ自体に
無い情報をLLMが生成している時点で別の重大な逸脱であり、後処理チェック以前に
実LLM接続後の生成品質そのものの検証課題として扱うのが妥当と考える。
