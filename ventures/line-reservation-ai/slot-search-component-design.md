# 空き枠検索コンポーネント設計(datetime_candidate → slot_key)

## 背景・課題
intent-to-flow-mapping.md(2026-07-31 20:58 UTC作成)で判明した残課題:
LLM構造化出力の`datetime_candidate`は「来週土曜のお昼くらい」のような自然文のままであり、
`ConversationFlowStateMachine.select_slot()`が要求する具体的な`slot_key`
(店舗ID・日付・時間帯のタプル、例: `("shop_1", "2026-08-09", "15:30")`)への変換を行う
コンポーネントが未設計だった。本ドキュメントでその設計を行う。

## 設計方針: 自然文の解釈はLLM、空き枠の算出は決定的コードで行う
自然文の日時表現(「来週土曜」「お昼くらい」等)の解釈をコード側の正規表現・自前パーサーで
行うのは、日本語の相対日時表現のゆらぎが大きく壊れやすいため避ける。
一方で「空いているかどうか」の判定(営業時間・メニュー所要時間・既存予約との突き合わせ)は
LLMに委ねず決定的コードで行う(誤りが許されないため)。

そこで役割を次のように分担する。

1. **LLM(将来のスキーマ拡張、今回は未実装)**: `datetime_candidate`の自由記述に加えて、
   構造化された`requested_date_range`(開始日・終了日、ISO8601)と
   `time_of_day_preference`(`morning`/`afternoon`/`evening`/`none`のいずれか)を
   追加フィールドとして出力させる案が有力(詳細は「今後の課題」参照、
   booking_output.schema.jsonへの反映は本ラウンドでは見送り)。
2. **AvailabilitySearcher(決定的コード、本ラウンドでprototype/engine.pyに実装)**:
   店舗の営業時間・メニュー所要時間・`BookingSlotManager`の現在の予約状況(pending/confirmed)
   から、指定された日付範囲・時間帯の希望に合致する空き枠を列挙し、上位N件を返す。

## AvailabilitySearcherの仕様
- 入力:
  - `store_id`
  - `business_hours`: 曜日ごとの営業時間(MVPは全曜日固定の単純な開始・終了時刻のみ対応。
    定休日・曜日別営業時間の対応は今後の課題とする)
  - `menu_duration_minutes`: メニューごとの施術所要時間(所要時間丸ごとが空いている枠のみ候補とする)
  - `slot_interval_minutes`: 候補として提示する時刻の刻み幅(MVPは30分固定)
  - `date_range`: (開始日, 終了日)
  - `time_of_day_preference`: `morning`(9:00-12:00)/`afternoon`(12:00-17:00)/
    `evening`(17:00-営業終了)/`none`(指定なし、終日)。時間帯の境界値はtone-and-manner-guideline.md等
    既存ドキュントとの整合は取れていないため今回新規に定義した仮の区切り。
  - `booking_slots`: `BookingSlotManager`インスタンス(pending/confirmed済みの枠を除外するため)
  - `now`: 現在時刻(過去の枠を候補から除外するため)
  - `max_candidates`: 返す候補数の上限(MVPは3件、pending-timeout-ux.md等の「候補提示」文言と合わせる)
- 出力: `slot_key`と表示用ラベル(例:「8/9(土) 15:30〜」)のペアのリスト。
  日付が近い順に列挙し、`max_candidates`件に達するか`date_range`の終端に達したら打ち切る。
- 除外ルール:
  - `booking_slots.status(slot_key, now)`が`pending`または`confirmed`の枠は除外する。
  - メニュー所要時間が営業終了時刻を超える開始時刻(例: 60分メニューで営業終了30分前の枠)は除外する。
  - `now`より前の時刻は除外する(当日分の過去の時間帯)。

## 今後の課題
- ~~LLM出力への`requested_date_range`/`time_of_day_preference`フィールド追加を
  booking_output.schema.jsonに反映し、llm-system-prompt-draft.mdにも「自然文から
  この2フィールドを抽出する」指示を追記する~~ → 2026-07-31 22:58 UTC対応済み。
- ~~この2フィールドをprototype/engine.py側でAvailabilitySearcherの
  `date_range`/`time_of_day_preference`引数に接続する~~ → 2026-08-01 00:00 UTC対応済み。
  `search_candidates_from_llm_output()`を新規実装し、intent-to-flow-mapping.mdの
  対応表にも反映した。次の課題は、提示した候補一覧から顧客の返信に対応する`slot_key`を
  1件特定する処理(intent-to-flow-mapping.mdの残課題を参照)。
- 店舗ごとの定休日・曜日別営業時間・臨時休業への対応(MVPは固定営業時間のみ)。
- 複数メニュー(スタッフ指名等でメニューごとに対応可能スタッフが異なる場合)の空き枠算出は
  本設計の範囲外(MVPは店舗全体で1本のタイムラインと仮定)。
- `time_of_day_preference`の時間帯境界(9-12/12-17/17-)は本ドキュメントでの仮決めであり、
  実店舗ヒアリング(customer-interview-design.md)や実際の予約傾向データが取れた際に見直す。
