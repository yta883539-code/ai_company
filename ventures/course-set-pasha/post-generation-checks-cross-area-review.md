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

## 残る既知の限界
文単位判定にしたことで単純な前後窓の問題は解消したが、「エリアDは変更なし、
エリアCは新着課題を追加」のように**読点区切りで1文にまとまっている**場合は、
同一文内に両エリアのキーワードが混在するため、旧実装と同じ理屈で見逃しうる。
発生頻度は実LLM接続後の実際の生成文で確認する必要があり、次の課題として残す
(LLMのSNS投稿文は基本的に「。」区切りの短文を重ねるスタイルを想定しているため、
発生頻度自体は低いと見込むが未検証)。
