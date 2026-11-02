# 複数会場「ハシゴ」対応のスキーマ改訂方針(設計決定)

input-output-sample-mapping.md「本対応表で明らかになった設計ギャップ」N3(複数会場
「ハシゴ」ケースで`itinerary_draft`・`day_timetable`が会場ごとに複数必要になるか)に
対応する設計決定を行う(README.mdフェーズ57次回候補(1))。

## 決定

- `itinerary_draft`・`day_timetable`を、現行の単一オブジェクトから**会場単位のオブジェクトを
  要素とする配列**に変更する。
- 単一会場ケース(`hashigo_check.applicable: false`)でも配列は常に長さ1とし、
  「単一/複数で型が変わる」ことによるLLM出力の不安定化を避ける(他venture
  〈line-reservation-ai等〉がstatus分岐に合わせ出力の型自体は常に固定している方針を踏襲)。
- 配列内の各要素に`venue_name_input`を持たせ、どの入力会場名に対応する項目かを明示する
  (現行の`itinerary_draft.venue_name_input`はそのまま配列要素内のフィールドとして移植)。
- `cost_estimate`は配列化しない(単一オブジェクトのまま)。遠征全体の予算感(交通・宿泊・
  物販の合計)は会場ごとに分割する入力粒度を通常持たないため、複数会場でも1トリップ分の
  合算見積りとして扱う。複数会場の移動が発生する場合は`transport_yen`に複数区間の移動費が
  含まれる旨を`note`に明記する運用とする(具体的な内訳の会場別分割は行わない)。
- `hashigo_check`自体は配列化しない(トリップ全体の無理チェックという性質上、単一オブジェクトの
  ままが適切)。

## 理由

- itinerary_draft.venue_matchedの名寄せ判定・最寄り駅情報は会場ごとに異なるため、配列化しないと
  N3のような2会場ケースを1レコードで表現できない(現行スキーマの構造的な限界)。
- day_timetableも開場時刻・グッズ列目安等が会場・公演ごとに異なるため同様に配列化が必要。
- 配列の長さを可変にする(1件または複数件)よりも、「常に配列・要素数で単一/複数を表現する」
  ほうが、LLMが`hashigo_check.applicable`の真偽と配列長を一致させる単純なルールで済み、
  thinking_modeの低いLLM呼び出しでも安定しやすいと判断した(line-reservation-aiの
  json-schema-multi-intent-extension.md等が採用した「型は固定、内容で分岐」という既存方針と
  整合する)。
- cost_estimate・hashigo_checkを配列化しない判断は、現行のmvp-flow-draft.md・README.mdの
  入力例(予算感は「交通込みで3万円くらい」のように1トリップ単位でまとめて入力される想定)
  を踏まえ、過剰な構造化(未収集の入力粒度を前提にしたフィールド追加)を避けるため。

## 実装への影響(次回以降に実施)

本フェーズは設計決定のみとし、以下は次回候補として残す(既存フィクスチャ〈N1・N2・N4・E4〉を
配列形式に書き換える作業が発生するため、設計決定と実装を同一フェーズで行わず分離する)。

- schema/output.schema.jsonの`itinerary_draft`・`day_timetable`を配列型に改訂する。
- validate_test_cases.pyの既存7フィクスチャ(N1・N2・N4 join/skip・E1・E2・E3・E4)を
  「配列長1」形式に書き換え、N3(配列長2)の新規フィクスチャを追加する。
- input-output-sample-mapping.mdのN3行・「設計ギャップ」節を「解消済み」に更新する。
- llm-system-prompt-draft.mdに、配列長と`hashigo_check.applicable`の整合を厳守事項として
  追記する(例: 「出力配列の要素数は入力で言及された会場数と一致させる」)。

## 承認について

本フェーズはスキーマ改訂方針の設計文書作成のみであり、コード実装・外部サービス接続・
支払い・アカウント作成・外部公開・送信等は一切発生していないため、pending-approval.mdへの
追記は不要。
