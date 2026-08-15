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

## 追記(2026-08-09 03:00 UTC): 厳守事項9(絵文字ルール)の機械チェック追加

これまでpost_generation_checks.pyは厳守事項2(変更なしエリアへの誤言及)・厳守事項3
(写真有無に応じた文面調整)の2点のみを機械チェック化しており、llm-system-prompt-draft.mdの
厳守事項9(「絵文字は1〜2個程度まで(SNS投稿文のみ)。公式LINE/Web告知文・履歴記録には
絵文字を使用しない」)は方針の記述のみで、生成後の突き合わせ検証コードが無いまま残っていた
ことに気づいた。line-reservation-aiのmessage-tone-variants.md(casualトーンの絵文字頻度上限)
でも絵文字ルールが検証課題として扱われており、本ventureでも同種のギャップだった。

`check_emoji_usage_rules()`を新規実装し、`EMOJI_PATTERN`(絵文字が集中する主要Unicodeブロックを
対象としたヒューリスティック、矢印記号等の非絵文字との誤検出を避けるため範囲を絞込み)を用いて
以下を検証する。
- `sns_post.body`: 絵文字が2個(SNS_POST_MAX_EMOJI)を超えたら違反(「1〜2個程度」という
  目安のため0個は許容し、上限超過のみを検出)。
- `line_web_notice.body`: 絵文字が1個でもあれば違反。
- `history_rows[].feature_keywords`: 絵文字が1個でもあれば違反(area・
  tape_color_or_grade_bandは入力メモの転記が中心のため対象外)。

`run_all_checks()`に組み込み、`prototype/test_post_generation_checks.py`に新規テスト7件を追加。
既存の全12件と合わせて19件、schema検証6件・history_export関連6件、いずれもパス確認済み
(合計25件+6件)。

### 残る既知の限界
- `EMOJI_PATTERN`は代表的な絵文字ブロックを対象とした範囲判定であり、Unicode絵文字を
  完全網羅するものではない(新しいUnicodeバージョンで追加された絵文字や、囲み文字・
  地域指示記号(国旗)等の一部は対象外)。
- 「1〜2個程度」という目安の解釈(0個は許容、超過のみ検出)は机上判断であり、
  実際に0個の投稿文が不自然に見えないか等は実LLM接続後の生成品質検証に委ねる。

## 追記(2026-08-09 05:00 UTC): history_rowsの本数と本文の整合性チェック追加

厳守事項3(写真有無)・厳守事項2(変更なしエリア)・厳守事項9(絵文字)はいずれも
「構造化フィールド(またはルール)と本文の突き合わせ」という形の機械チェックだったが、
厳守事項4・5が指示する「本数を明示する」という要求について、history_rows(構造化データ)
側のcountと本文側の記載が食い違っていないかを確認するチェックが無いまま残っていた点に
対応した。

`check_history_row_counts_mentioned_in_text()`を新規実装し、history_rows[]の各行について
countがnullでない場合、その数値が文字列としてsns_post.body・line_web_notice.bodyの
いずれかに含まれているかを確認する(OR判定。G2フィクスチャのように出力1側では本数に
触れずSNS的な文面のみで完結させ、出力2側で本数を明示するケースがあるため)。

`prototype/test_post_generation_checks.py`に新規テスト6件を追加(既存19件と合わせて25件)。
schema検証6件・history_export関連6件と合わせて全件パス確認済み。

### 残る既知の限界(追加分)
- 数字の文字列一致による判定のため、本数と無関係な数字(日付の一部等)が偶然一致する
  ケースを誤って「整合している」と判定しうる。逆に、同じcount値を持つ複数エリアが
  存在する場合、本文側にその数字が一度でも登場すれば実際にはどのエリアの記載か
  判別せずパスと判定してしまう(厳密な対応関係の検証ではなく、あくまで「本文中に
  その数字自体は存在するか」という緩いヒューリスティック)。
- 既存の厳守事項2・3・9チェックと同様、実LLM接続後に拾いきれない不一致パターンの
  収集・ルール改善が引き続き必要になる。

## 追記(2026-08-09 06:00 UTC): EMOJI_PATTERNの対象ブロック拡張(地域指示記号・囲みCJK記号)

上記「残る既知の限界」で指摘していた`EMOJI_PATTERN`の未対応ブロックのうち、機械的に
追加しやすいものから着手した。line-reservation-aiのmessage-tone-variants.mdでも
絵文字頻度が検証課題として扱われており、同種の改善。

- 地域指示記号(Regional Indicator Symbols、U+1F1E6-U+1F1FF): 2文字の組み合わせで
  国旗絵文字(🇯🇵等)になるブロック。SNS投稿文で店舗の国際色をアピールする文脈等で
  使われうるため追加。
- 囲みCJK文字・月間補助記号(Enclosed Ideographic Supplement、U+1F200-U+1F2FF):
  🈵🈲🈴🈚等、日本語圏のSNS・掲示文で装飾的に使われることがある記号ブロック。
  日本語が主要な出力言語である本ventureでは見落とすと実害が出やすいと判断し追加。

`prototype/test_post_generation_checks.py`に新規テスト2件を追加
(`test_line_web_notice_with_enclosed_cjk_symbol_is_flagged`・
`test_line_web_notice_with_flag_emoji_is_flagged`)。既存25件と合わせて27件、
schema検証6件・history_export関連6件と合わせて全件パス確認済み。

### 残る既知の限界(引き続き未対応)
- Unicode絵文字を完全網羅する判定ではない点は変わらない。今回未対応のまま残る主な
  ブロックは、囲み英数字補助(Enclosed Alphanumeric Supplement、U+1F100-U+1F1FF、
  地域指示記号と範囲が一部重複するため優先度を下げた)、および将来のUnicode改定で
  追加されるブロック全般。
- 「1〜2個程度」という目安の解釈(0個は許容、超過のみ検出)についての判断は据え置き。

## 追記(2026-08-09 07:00 UTC): 厳守事項7(会員管理・予約・決済への不応答)の機械チェック追加

これまでpost_generation_checks.pyは厳守事項2・3・4・5・9をカバーしていたが、
llm-system-prompt-draft.mdの厳守事項7(「入力メモに会員管理・予約受付・決済に関する
記述が含まれていても一切応答せず、告知文・記録の生成対象から除外する」)は、
schema/validate_test_cases.pyのvalidate_cross_field_rules()がstatus=out_of_scope
分岐そのものの妥当性(out_of_scope_message等のnull/非null依存関係)を検証している
のみで、LLMがstatus=generatedと判定したケースの本文自体にこれらの話題が紛れ込んで
いないかを確認する後処理チェックが無いまま残っていたことに気づいた。

`check_no_out_of_scope_topics_in_generated_output()`を新規実装し、`status=="generated"`の
ときのみ`sns_post.body`・`line_web_notice.body`を対象に、`OUT_OF_SCOPE_TOPIC_KEYWORDS`
(会員・入会・退会・予約・決済・支払い・振込・クレジットカード)の出現有無を確認する。
厳守事項2・3のような近傍の文脈判定(打消し語の有無等)は行わず、出現そのものを疑いの
根拠とするシンプルな判定とした。`status=="out_of_scope"`のときの`out_of_scope_message`
自体は「会員管理・予約受付・決済のご案内はできません」のように意図的にこれらの語を
含む(OOS1フィクスチャ参照)ため、チェック対象を`sns_post`/`line_web_notice`
(status=generatedのときのみ非null)に限定することで誤検出を避けた。

`run_all_checks()`に組み込み、`prototype/test_post_generation_checks.py`に新規テスト4件を
追加(既存27件と合わせて31件)。schema検証6件・history_export関連6件と合わせて全件パス
確認済み。

### 残る既知の限界(追加分)
- 単純なキーワード出現判定のため、本来無関係な文脈での偶然の出現(例:別の意味を持つ
  複合語の一部としての出現)を誤って違反と判定しうる可能性がある。本venture(ボルダリング
  ジムの課題入れ替え告知)の性質上、通常の生成文にこれらの語が登場すること自体が
  想定されないため、既存の厳守事項2・3チェックよりも誤検出リスクは低いと考えられるが、
  実LLM接続後の生成文での検証は引き続き今後の課題として残る。

## 追記(2026-08-09 09:00 UTC): 厳守事項4・5(エリア名の明示漏れ)の機械チェック追加

`check_history_row_counts_mentioned_in_text()`は`history_rows[].count`と本文の本数記載の
整合性を検証していたが、同じ厳守事項4・5が求める「エリア・改訂日の明示」のうち、
エリア名自体が本文に一切登場していないケース(本数だけ書かれてエリア名の記載が
丸ごと抜け落ちている、等)を検出するチェックが無いまま残っていたことに気づいた。

`check_updated_areas_mentioned_in_text()`を新規実装し、`history_rows[].area`
(null以外)の値が`sns_post.body`・`line_web_notice.body`のいずれかに文字列として
登場しているかを確認する。既存の本数チェックと対をなす位置づけで、判定方式
(いずれかのbodyへの単純な文字列一致)も同じ考え方を踏襲した。

`run_all_checks()`に組み込み、`prototype/test_post_generation_checks.py`に新規テスト6件を
追加(既存31件と合わせて37件)。schema検証6件・history_export関連6件と合わせて全件パス
確認済み。

### 残る既知の限界(追加分)
- エリア名の完全一致のみで判定するため、本文側で別の略称・表記ゆれ(例:入力メモの
  「Aエリア」を本文で「A」とだけ表記する等)を使った場合は誤って言及漏れと判定しうる。
  history_rows[].areaと本文中の表記が常に一致する運用(mvp-flow-draft.md想定)を前提とした
  ヒューリスティックであり、実LLM接続後に表記ゆれが実際に発生するかの検証は今後の課題。

## 追記(2026-08-15 13:00 UTC): 厳守事項7a(解約意図検知)の機械チェック追加

フェーズ54(schema/output.schema.jsonへの`subscription_procedure_notice`フィールド新設)で
`status`・`kind`・`includes_portal_link`のクロスフィールド依存関係は
`schema/validate_test_cases.py`側でカバー済みだったが、`厳守事項7a(iv)`が求める
「`cancellation_unclear`のときは手続き完了・Stripeカスタマーポータルへの言及を含めない」
という**本文の文言そのもの**に対する後処理チェックは、既存の`check_no_out_of_scope_topics_in_generated_output()`
(厳守事項7)と同様の抜けとして残っていたことに気づいた。

`check_subscription_notice_consistency()`を新規実装し、以下の2方向を確認する。

- `kind=cancellation_unclear`のとき、本文に`PORTAL_KEYWORDS`(カスタマーポータル・ポータル)
  または`PROCEDURE_COMPLETION_KEYWORDS`(手続き完了・解約が完了 等)が含まれていないか
  (厳守事項7a(iv)違反の疑い)。
- `kind=cancellation_intent`/`downgrade_intent`かつ`includes_portal_link=true`のとき、
  本文に実際にカスタマーポータルへの案内が含まれているか(`check_mentions_photo_consistency()`
  と同じ、構造化フィールドと本文の突き合わせという考え方)。

`run_all_checks()`に組み込み、`prototype/test_post_generation_checks.py`に新規テスト6件を
追加(既存37件と合わせて43件)。schema/validate_test_cases.pyのCI1〜CI3フィクスチャ
(フェーズ54で追加済み)を含む全フィクスチャが新チェックにも違反しないことを
`FixtureCasesTest`で確認済み。

### 残る既知の限界(追加分)
- キーワード出現の有無のみで判定するヒューリスティックであり、厳守事項2・3のような
  近傍の文脈判定は行わない。「カスタマーポータル」という語自体を意思確認の文脈で
  引用する等の例外的な言い回しがあった場合は誤検出しうる。
- 実LLM接続後に生成文の実例が得られた段階で、ここで拾いきれない違反パターン
  (例:「ポータル」を含まない別表現でのリンク案内)が無いか改めて確認する必要がある。

## 追記(2026-08-15 22:00 UTC): 厳守事項7(会員管理・予約受付・決済)キーワードの拡張

フェーズ57で`PORTAL_KEYWORDS`を「ポータル」を含まない実際の言い回し(マイページ・
決済ページ)に拡張したのと同じ考え方で、`OUT_OF_SCOPE_TOPIC_KEYWORDS`(厳守事項7)も
「会員」「決済」「予約」等の直接語のみでは、ボルダリングジムで実際によく使われる
言い回しを取りこぼす疑いがあることに気づいた。「月会費を改定します」のように
会員管理の話題を「会員」を使わず「会費」で表現するケース、「当日キャンセルは
お電話にて」のように予約関連の話題を「予約」を使わず「キャンセル」単独で表現する
ケースが該当する。

`OUT_OF_SCOPE_TOPIC_KEYWORDS`に「会費」「キャンセル」を追加した(「月会費」は
「会費」の部分文字列一致で既に検出できるため別途追加していない)。
`prototype/test_post_generation_checks.py`に新規テスト2件を追加し
(既存47件と合わせて全49件)、`prototype/`配下の全テストファイル(discover実行)でも
全76件パス、schema/validate_test_cases.pyも9件中9件パス確認済み。

### 残る既知の限界(追加分)
- 「会費」「キャンセル」は単純な文字列一致のため、本venture(ボルダリングジムの課題
  入れ替え告知)の生成文に本来無関係な文脈で偶然登場する可能性は低いと考えられるが、
  既存の厳守事項7チェックと同じくヒューリスティックの域を出ない。
- 「解約」「サブスク」等、厳守事項7a(本サービス自体の契約解約・プラン変更)側の語彙
  との切り分けは、`check_no_out_of_scope_topics_in_generated_output()`が
  `status=="generated"`のときのみを対象とする(`cancellation_intent`等の別status
  ケースは対象外)ことで担保している。
- 実LLM接続後に生成文の実例が得られた段階で、他に取りこぼしている言い回し
  (例:「入会金」「月謝」等)が無いか改めて確認する必要がある。
