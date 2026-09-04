# 営業時間raw値→AvailabilitySearcher構造化値の変換設計

conversation-event-processor-assembly-design.md 4節の残課題「`searcher`
(`AvailabilitySearcher`)の組み立てに必要な店舗の営業時間・スロット間隔データは、
`StoreProfileStoreProtocol`(実際には`StoreSettingsStoreProtocol`)経由でどう読み出すかは
まだ未設計」に対応した。store-settings-save-flow-design.md 8.3節でも「本フローの範囲外」と
明記されていた変換処理そのものにあたる。

## 1. 前提: 既に保存されているraw値

`store_settings_save_flow.py`(`InMemoryStoreSettingsStore`)には、owner-settings-wireframe.md
の営業情報設定ページから届く生値(raw)がそのまま保存されている。

| フィールド | 型 | 例 |
|---|---|---|
| `business_hours_raw` | `str` | `"10:00-19:00"` |
| `weekday_business_hours_raw` | `dict[int, str]` | `{5: "10:00-15:00", 6: "定休日"}` |
| `closed_weekdays` | `list[int]` | `[0]` |
| `closed_dates` | `list[str]`(`YYYY-MM-DD`) | `["2026-09-15"]` |
| `slot_interval_minutes` | `Optional[int]` | `30` |

これらは全て文字列またはJSON安全な単純型のまま保存されており、`AvailabilitySearcher`
(prototype/engine.py)が要求する分単位の構造化値(`list[tuple[int,int]]`・
`dict[int, list[tuple[int,int]]]`・`frozenset[date]`)への変換は未実装だった。

## 2. business_hours_rawの書式(複数区間対応、本設計で新規定義)

これまでどのdesign docにも「昼休憩など複数区間の場合、raw文字列としてどう表現するか」の
定義がなかった(business-hours-lunch-break.mdは構造化後の`AvailabilitySearcher`側の対応のみ
定義済み)。owner-settings-wireframe.mdの入力欄がテキスト1行である前提を踏まえ、
`"09:00-12:00,15:00-19:00"`のようにカンマ区切りで複数区間を表現する書式を採用する
(単一区間は従来通り`"10:00-19:00"`のまま、後方互換)。各区間は`"H:MM-H:MM"`
(時は1〜2桁、分は2桁固定)とし、区間同士の重複・順序チェックは行わない
(`_normalize_business_hour_ranges()`が`AvailabilitySearcher`構築時に検証するため、
本モジュールでは書式(`\d{1,2}:\d{2}-\d{1,2}:\d{2}`)の妥当性のみを見る)。

## 3. weekday_business_hours_rawの「定休日」値の扱い

`normalize_weekday_business_hours_raw()`(store_settings_save_flow.py)は`"定休日"`という
文字列値をそのまま素通しする(意味の解釈はしない)。`AvailabilitySearcher`には
`weekday_business_hours`(営業時間の曜日別上書き)と`closed_weekdays`(終日休業)という
別々の引数があるため、変換時に`"定休日"`の曜日は`weekday_business_hours`ではなく
`closed_weekdays`側へ振り分ける。既存の`closed_weekdays`(店舗設定の定休日チェックボックス
由来)と`weekday_business_hours_raw`経由の`"定休日"`は役割としては同じ「終日休業」なので、
両者を`frozenset`の和集合として扱う(どちらか一方だけの入力でも、両方の入力でも同じ結果)。

## 4. 実装方針

新規モジュール`prototype/business_hours_assembly.py`に以下を実装する。

- `parse_business_hours_segments(raw: str) -> list[tuple[int,int]]`: 2節の書式でカンマ区切り
  区間文字列を`[(開始分,終了分), ...]`へ変換。書式に合わない区間があれば
  `BusinessHoursRawFormatError`を送出する。
- `parse_weekday_business_hours_raw(weekday_business_hours_raw: dict[int,str]) ->
  tuple[dict[int, list[tuple[int,int]]], frozenset[int]]`: 3節の方針で`"定休日"`の曜日を
  `closed_weekdays`側へ分離し、`(上書きdict, 追加の終日休業曜日集合)`を返す。
- `parse_closed_dates(closed_dates_raw: list[str]) -> frozenset[date]`: `YYYY-MM-DD`文字列を
  `date.fromisoformat()`で変換。不正な書式があれば`BusinessHoursRawFormatError`を送出する
  (`normalize_closed_dates()`は書式検証をしない方針だったため、ここで初めて検証する)。
- `build_availability_searcher_for_store(store_id: str, settings_store:
  StoreSettingsStoreProtocol) -> AvailabilitySearcher`: 上記3関数を組み合わせ、
  `settings_store`の各getterから読み出した値を`AvailabilitySearcher`のコンストラクタへ渡す
  最上位の組み立て関数。`business_hours_raw`が未設定(空文字列)の場合は
  `BusinessHoursRawFormatError`を送出する(オンボーディング未完了の店舗を暗に示すため、
  呼び出し元でオンボーディング完了判定と組み合わせて使う想定)。

## 5. 引き続き残る課題

- `menu_durations`・`store_faq_info`(既に実装済み)と`searcher`が揃った後の、
  `ConversationEventProcessor`本体を組み立てる最上位ファクトリ関数
  (`build_conversation_event_processor_for_payload()`相当)自体はまだ実装していない。
  `push_client`・`conversation_state_store`等の実クラウド接続に依存する引数がある間は
  実際にCloud Functions上で動作させられないため、優先度は引き続き低いと判断する。
- 実際のFirestore接続(GCPプロジェクト作成、オーナー承認待ち)自体は引き続き残る課題。
- (訂正 2026-09-04 23:00 UTC: 上記で「3区間以上(朝・昼・夜の3部制)の営業時間はowner-settings-
  wireframe.mdのUI自体が現時点で対象外」と記載していたが誤りだった。business-hours-lunch-
  break.md「追記: 曜日別営業時間×複数休憩区間のレイアウト(2026-08-07)」の通り、「+ 休憩時間を
  追加」は既に複数回押せる設計に変更済みで、UI側も区間数を制限していない。本モジュールの
  `parse_business_hours_segments()`(カンマ区切りである限り区間数上限なし)と合わせて、
  3区間以上の営業時間はUI・変換処理の双方で対応済みであり、追加のUI対応は不要。business-hours-
  lunch-break.mdが2026-08-07時点で既に解消済みとしていた課題を、本designが古い文言のまま
  再掲していたのが原因。今後この項目を「残課題」として再掲しないこと)
