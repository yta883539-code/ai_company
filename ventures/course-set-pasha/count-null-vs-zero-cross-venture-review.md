# count(本数)のnull/0使い分け設計 — 他venture横展開検討(フェーズ362)

## 1. 背景

フェーズ361(2026-11-07定例更新)で、`schema/output.schema.json`の
`history_rows[].count`について、「null=入力から本数を抽出できない」
「0=removal-only-notice-edge-case-review.mdで新設した『新規追加なし』を
意図的に表す実在の値」という2通りの意味を持つ値であることを踏まえ、
`prototype/post_generation_checks.py`の
`check_history_row_counts_mentioned_in_text()`が「count=0の場合も本文に
数字として登場するはず」という誤った前提のままだったバグを修正した。
同フェーズの次回候補(3)で、この「null=抽出不可/0=意図的な実在のゼロ」
という使い分け方針が、他venture(line-reservation-ai等)の類似スキーマ
設計方針と整合するか、あるいは同種の見落としが他ventureにも存在しないか
の横展開検討を申し送っていたため、本フェーズで確認した。

## 2. 確認方法

各ventureの`schema/*.schema.json`(line-reservation-aiのみ
`schema/booking_output.schema.json`)を対象に、`"integer"`型
フィールド(null許容のもの)の有無を機械的に確認したうえで、該当する
フィールドを持つventureについては対応する`post_generation_checks.py`の
チェック関数を実際に読み、「値が0のときに本文中の言及を要求してしまう」
という本venture同型のバグパターンが存在するかを確認した。

## 3. 確認結果

- aircon-pasha・forklift-pasha・event-komiguai-pasha・kura-pasha・
  line-reservation-aiのいずれのschemaにも、本venture
  `history_rows[].count`(本数)に相当する「null許容の整数型で、かつ
  その値が本文中に数字として登場することをpost_generation_checks.py側で
  検証する」という組み合わせのフィールドは存在しなかった。
- oshien-pashaの`schema/output.schema.json`には`cost_estimate`配下に
  `transport_yen`/`lodging_yen`/`goods_yen`という`["integer", "null"]`型
  フィールドが存在するが(交通・宿泊・物販予算の概算見積り)、
  `prototype/post_generation_checks.py`を確認した結果、これらの値が本文中に
  数字として登場することを要求するチェック関数自体が存在しない(見積り
  金額はnoteへの注記のみを要求する設計)。そのため「0のとき本文言及を
  誤って要求する」という本venture同型のバグは生じ得ない。
- event-komiguai-pashaの`post_generation_checks.py`には
  `check_dispersed_exit_block_count_consistency()`という、分散退場時の
  ブロック数言及を複数フィールド間で突き合わせる関数が存在するが、これは
  「本文中に実際に言及されたブロック数どうしが食い違っていないか」を
  見るものであり、「schema側の数値フィールドの値が0であること」を前提に
  本文言及の有無を判定する設計ではない(ブロック数0=分散退場なし、を
  意味し、その場合はそもそも言及自体が発生しない設計のため、本venture同型
  の「0なのに言及必須」というバグの起こりようがない)。
- kura-pashaの`post_generation_checks.py`には招待コード関連の言及検証
  (60行目付近)はあるが、`count`に相当する数量フィールドではなく整数型
  null許容フィールドとも異なるため対象外。

## 4. 結論

本venture(course-set-pasha)で発見・修正したバグ(フェーズ361)は、
「null=抽出不可」と「0=意図的な実在の値」を区別する必要があるスキーマ
フィールドと、その値が本文中に数字として登場することを機械的に要求する
post_generation_checksの組み合わせが揃って初めて起こりうるものであり、
他6venture(2026-11-08 07:00 UTC時点)にはこの組み合わせ自体が存在せず、
同種の見落としは発見されなかった。したがって本件は構造的な横展開課題では
なく、course-set-pasha固有の設計(本数という「新規追加ゼロ」が意味を持つ
値)に起因する一過性の見落としだったと判断する。他ventureへの追加対応は
不要。

本フェーズはコード・schema変更を伴わない机上レビューのみであり、
回帰確認として既存テスト・schema検証を再実行し、変更なしで全件パスする
ことを確認した。
