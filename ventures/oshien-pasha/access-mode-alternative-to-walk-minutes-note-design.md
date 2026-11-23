# `walk_minutes_note`が実態と合わない会場向けの代替表示形式設計(フェーズ157)

README.mdフェーズ156次回候補(2)「徒歩圏外(バス/車移動が前提)の会場を会場マスタに
追加する場合の表示形式(`walk_minutes_note`に代わるバス/車アクセス表記の設計)の検討」に
対応する。本フェーズは設計のみであり、`schema/venue-master.json`・
`prototype/venue_matcher.py`のコード変更は行わない(次フェーズ以降の実コード化候補とする)。

## 前提となった事実関係

フェーズ156で高知県立県民体育館(高知市桟橋通2丁目1番53号、JR高知駅から車で7分)を
調査した結果、公式資料から得られたのは「車で7分」という所要時間のみで、徒歩分数の一次
情報は見つからなかった。既存51件の大半は「徒歩3〜10分前後」の駅近接型であり、
`walk_minutes_note`はその前提で設計されたフィールドである。車で7分は一般に徒歩20〜30分
程度に相当すると推定され、仮にこの推定値をそのまま`walk_minutes_note`に入れると、
他の51件と同じ形式でありながら性質の異なる情報(一次情報に基づく実測値 vs 二次的な推定値)
が混在し、利用者に実態以上の確からしさを伝えてしまうリスクがある。

## 設計方針

1. 会場マスタ(内部データ、`schema/venue-master.json`)に、任意フィールドとして
   `access_mode`(値: `"walk"` | `"car_or_bus"`、省略時は`"walk"`とみなす後方互換)を
   新設する。既存51件はいずれも駅近接型のため`access_mode`を省略してよく、
   スキーマ変更によるマイグレーション作業は発生しない。
2. `access_mode`が`"car_or_bus"`の会場には、`walk_minutes_note`の代わりに
   `access_note`(自由記述)を設定する。`access_note`には、一次情報として確認できた
   移動手段・所要時間(例:「車で7分」)と、それが徒歩分数の確定情報ではない旨を
   tone-and-manner-guideline.mdの非断定トーンで併記する。
   例:「JR高知駅から車で7分(公式の徒歩分数情報は確認できていません。公共交通機関や
   送迎バスの有無は主催者発表をご確認ください)」。
   推定値(徒歩20〜30分程度)自体はテンプレート文言に含めない方針とした。推定の精度が
   施設・経路ごとに大きくばらつくため、根拠の薄い数値を本文に出すよりも「徒歩分数は
   未確認」である事実を明示する方が、tone-and-manner-guideline.mdの「断定しない」
   方針およびvenue-name-normalization-design.mdの既存トーンと整合する。
3. `prototype/venue_matcher.py`の`_station_note()`は、`access_mode == "car_or_bus"`かつ
   `access_note`が設定されている場合はそちらを使い、それ以外は従来どおり
   `walk_minutes_note`(未設定時は「徒歩目安不明」)を使う分岐を追加する想定とする
   (疑似コード):

   ```python
   def _station_note(venue):
       if venue.get("access_mode") == "car_or_bus" and venue.get("access_note"):
           return f"{venue['nearest_station']}({venue['access_note']})"
       return f"{venue['nearest_station']}({venue.get('walk_minutes_note', '徒歩目安不明')})"
   ```

4. `output.schema.json`(LLM生成物のユーザー向け出力スキーマ)側は変更しない。
   `nearest_station_note`は引き続き`_station_note()`の戻り値をそのまま差し込む既存の
   結線のままでよく、出力フィールドの型・意味に変更は生じないため。

## 適用範囲・次フェーズへの申し送り

- 高知県立県民体育館は、本フェーズでは会場マスタに未追加のまま据え置く(フィールド設計が
  固まった段階で、次フェーズ以降に`access_mode: "car_or_bus"`として追加する想定)。
- `check_venue_master_parity.py`(51件/51件の差分チェック)は、新フィールドが任意項目で
  既存51件に影響しないため、本設計時点では変更不要と見込む(実コード化時に確認する)。
- 宮崎県体育館・宮崎市総合体育館についても、今後の調査で徒歩分数の一次情報が得られなければ
  同じ`access_mode: "car_or_bus"`の枠組みを適用できるか検討する。

コード実装・外部サービス接続・データ変更は本フェーズでは一切行っていない。承認が必要な
アクション(支払い・アカウント作成・外部公開・送信等)は発生していない。
