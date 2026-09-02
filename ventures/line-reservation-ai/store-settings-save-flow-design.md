# 店舗設定保存フロー設計(owner-settings-wireframe.mdフォーム保存処理→オンボーディング完了判定への結線)

作成日: 2026-08-31(定例更新)

onboarding-completion-message-design.md「残課題」に最後まで残っていた
「owner-settings-wireframe.mdのフォーム保存処理自体(実Firestore書き込み・実UI)からの
実呼び出し配線」に着手する。course-set-pasha/application-form-submission-flow-design.md
と同じ考え方で、No-codeフォームツールから届く想定のペイロードを検証・正規化し、
`stores/{storeId}`ドキュメントへの書き込みと`evaluate_onboarding_completion_message_
dispatch()`(store_profile_store.py)呼び出しまでを結線するロジックを設計する。

## 1. フォームツールの選定

owner-settings-wireframe.md「実装メモ」で既に「MVP段階ではNo-codeフォームツール
(例: Googleフォーム+スプレッドシート連携、またはノーコードDB系サービスの管理画面機能)を
流用し、専用フロントエンド開発を避ける」方針が明記済み。course-set-pasha/application-
form-submission-flow-design.md 1節と同じ理由(追加の有料SaaS契約を伴わずゼロ初期投資を
維持できる)により、Googleフォーム+Google Apps Script(GAS)Webhookを第一候補とする。
実際のGoogleフォーム作成・GAS配置(外部サービスへの実設定)自体はpending-approval.mdの
承認待ち事項として扱う(本ドキュメントは設計のみ)。

## 2. スコープ

owner-settings-wireframe.mdの営業情報設定ページは項目数が多い(営業曜日・営業時間・
曜日別営業時間・休憩時間・臨時休業日・予約枠の間隔・同時受付可能数・メッセージトーン・
常連客とみなす来店回数・FAQ情報)。本ドキュメントはこのうち、onboarding-completion-
message-design.mdの発火判定(`evaluate_onboarding_completion_message_dispatch()`)に
必要な入力値の算出――「MVPの最低限必須項目」(営業曜日・営業時間・予約枠の間隔・
同時受付可能数・メニュー一覧最低1件)が保存の都度揃ったかどうか――に範囲を絞る。

以下は本ドキュメントの対象外とし、既存の個別設計ドキュメントに委ねる(重複設計を避ける):

- 曜日別営業時間の複数区間・重複区間バリデーション: weekday-specific-business-hours.md・
  business-hours-lunch-break.mdが既に担当。本モジュールは「営業時間欄が空でないか」の
  存在チェックのみを行い、区間の妥当性検証には踏み込まない。
- 臨時休業日の入力バリデーション: ad-hoc-closed-dates-support.md・本ワイヤーフレーム
  「臨時休業日」欄の追記が既に担当。
- メッセージトーン・常連客とみなす来店回数・FAQ情報の保存: MVP必須項目ではないため
  (onboarding-guide.mdステップ3の必須項目に含まれない)、発火判定(3節の入力には含めない)には
  影響させない。ただしFirestoreへの書き込み自体は7節で結線する(次回以降の課題として残していた
  ものへの対応、2026-08-31定例更新)。

## 3. ペイロード形状

想定GAS Webhookペイロード(簡略化、実フィールド名はフォーム実装時に確定):

```json
{
  "user_id": "Uowner1234567890abcdef",
  "closed_weekdays": [6],
  "business_hours_raw": "10:00-19:00",
  "slot_interval_minutes_raw": "30分",
  "concurrent_capacity_raw": "1",
  "menus": [{"name": "カット", "duration_minutes": 60}]
}
```

- `user_id`: line-user-id-linking-design.md相当の連携経路で事前に取得済みの値を
  フォームに埋め込む想定(course-set-pashaの連携コード方式と同様の課題は、本venture側では
  friend-add時に発行するuser_idをオーナー向け設定画面のURLに埋め込む形で既に前提としており
  〈owner-settings-wireframe.mdはLINEトークルーム内の設定画面という位置づけ〉、追加の
  連携課題は生じない)。
- `closed_weekdays`: 「曜日ごとに営業時間を変える」トグルOFF時の単一営業時間欄を対象とし、
  availability-closed-weekday-support.mdの定休日チェックボックス(月=0〜日=6)から
  GAS側で組み立てた配列をそのまま受け取る(本モジュールでは曜日番号への変換ロジックは
  持たない。2節の通り既存設計に委ねる)。
- `business_hours_raw`: 単一営業時間欄の文字列表現(例: "10:00-19:00")。曜日別営業時間
  トグルON時の複数区間ケースは2節の通り対象外。
- `slot_interval_minutes_raw`/`concurrent_capacity_raw`: owner-settings-wireframe.mdの
  プルダウン(例: "30分 ▼"、"1 ▼")から届く表示文字列そのもの。
- `menus`: メニュー設定ページ(owner-settings-wireframe.md 2.)の一覧。

## 4. 正規化ルール

- `business_hours_configured`(bool): `business_hours_raw`が空文字列でなく、かつ
  `closed_weekdays`が7曜日(月〜日)未満(=最低1曜日は営業日)である場合にTrue。
  区間の妥当性(重複・逆転等)は2節の通り検証しない。
- `slot_interval_minutes`/`concurrent_capacity`: `"30分"`・`"1"`のような表示文字列から
  数字部分を正規表現で抽出し`int`化する。数字が抽出できない、または0以下の場合は
  `None`(未設定として扱う、`evaluate_onboarding_completion_message_dispatch()`は
  `None`を必須項目未充足として扱う既存仕様のためそのまま連携できる)。
- `menus`: 各要素の`name`が空文字列・非文字列の要素は不正入力として除外してから件数を
  数える(誤ってカウントし通知が早まることを防ぐ、application-form-submission-flow-
  design.md 2節の「誤ったタグ付けより安全側を優先する」方針を踏襲)。

## 5. 書き込み先・結線

`stores/{storeId}`ドキュメント(firestore-data-model.md 1節)のうち、`businessHours`
(単一営業時間欄相当の生値)・`closedWeekdays`・`slotIntervalMinutes`・
`concurrentCapacity`・`menus`へ全体上書きする(申込フォームと同じく差分マージは行わない、
application-form-submission-flow-design.md 3節と同じ「スプレッドシート感覚の全件
再入力」前提)。書き込み後、正規化済みの値で
`cloud_function_send_onboarding_completion_message.handle_onboarding_completion_
message_dispatch()`を呼び出す(判定→整形→送信までは実装済み、フェーズ続き157)。
`payment_page_url`・`push_client`は本モジュールの呼び出し元(Cloud Function本体)が
注入する想定。

## 6. プロトタイプ実装方針

`prototype/store_settings_save_flow.py`に以下を実装する。

- `StoreSettingsStoreProtocol`: `StoreProfileStoreProtocol`(store_profile_store.py)を
  継承し、MVP必須項目フィールドの書き込みメソッド(`set_business_hours_raw`・
  `set_closed_weekdays`・`set_slot_interval_minutes`・`set_concurrent_capacity`・
  `set_menus`)を追加する(実Firestore化時に単一ドキュメントアクセスへ統合できるよう、
  application-form-submission-flow-design.md 4節と同じ考え方)。
- `InMemoryStoreSettingsStore`: `InMemoryStoreProfileStore`を継承し、上記フィールドを
  `dict`で保持する検証用スタブ。
- `handle_store_settings_submission(payload, store, *, payment_page_url, push_client,
  tone="standard") -> StoreSettingsSubmissionResult`: 3節のペイロードを検証・4節の
  正規化を行い、5節の書き込み・結線までを行うエントリポイント。

## 7. メッセージトーン・常連客閾値・FAQ情報の保存(2節「対象外」への対応)

2節で「発火判定に影響しないため次回以降の課題」としていたメッセージトーン・常連客とみなす
来店回数・FAQ情報について、保存処理(書き込みのみ)を本フローに結線する。発火判定
(`evaluate_onboarding_completion_message_dispatch()`への入力)には引き続き含めない
(3節のペイロードのうち`user_id`〜`menus`の5項目のみが判定対象という2節の方針は変更しない)。

### 7.1 追加ペイロード項目

```json
{
  "message_tone_raw": "standard",
  "repeat_customer_visit_threshold_raw": "3回",
  "faq_address": "○○駅から徒歩5分",
  "faq_parking_available": "あり",
  "faq_parking_capacity_raw": "3",
  "faq_payment_methods": ["現金", "クレジット"]
}
```

- `message_tone_raw`: owner-settings-wireframe.mdのプルダウン値(`standard`/`formal`/
  `casual`のいずれか、message-tone-variants.md参照)。想定外の値は`standard`(既定値)に
  フォールバックする(誤ったトーンで送信するより既定の安全な文体を優先する)。
- `repeat_customer_visit_threshold_raw`: `"3回"`のような表示文字列。4節の
  `_extract_positive_int()`を再利用して抽出する。抽出できない場合は`firestore-data-model.md`の
  既定値3を書き込む(未入力によりprecheck-strengthening.mdの簡略化判定が機能しなくなることを
  避けるため、`slot_interval_minutes`等とは異なり`None`のまま放置しない)。
- `faq_address`/`faq_parking_available`/`faq_parking_capacity_raw`/`faq_payment_methods`:
  owner-settings-wireframe.md「店舗FAQ情報の入力欄」に対応。`faq_parking_available`が
  `"あり"`以外の場合は`faq_parking_capacity_raw`を無視する(ワイヤーフレームの条件分岐と
  同じ)。`faq_payment_methods`は`["現金", "クレジット", "電子マネー", "QRコード決済"]`の
  部分集合以外の値は不正入力として除外する(faq-response-templates.mdのテンプレート項目と
  一致しない値を回答に使わせないため)。未入力の項目は`faqInfo`の対応キーを空文字列/空配列
  のまま書き込む(owner-settings-wireframe.md 232行目の「空欄は未登録として扱う」方針どおり、
  未登録扱いにするのが正しい挙動であり、エラーにはしない)。

### 7.2 書き込み先

`stores/{storeId}`ドキュメントの`messageTone`・`repeatCustomerVisitThreshold`・`faqInfo`
(`{address, parking, paymentMethods}`、firestore-data-model.md 1節)へ、5節と同じ全体上書きで
書き込む。発火判定への結線(5節)より後に実行する順序上の制約はない(判定対象外のため)。

### 7.3 プロトタイプ実装方針

`StoreSettingsStoreProtocol`に`set_message_tone`・`set_repeat_customer_visit_threshold`・
`set_faq_info`を追加し、`InMemoryStoreSettingsStore`に対応する保持先を追加する。
`normalize_message_tone()`・`normalize_repeat_customer_visit_threshold()`・
`normalize_faq_info()`を新設し、`handle_store_settings_submission()`から6節のフィールドと
同じ検証済みストアへの書き込み処理として呼び出す(発火判定ロジックへの入力には含めない)。

## 8. 曜日別営業時間・臨時休業日の生値(raw)の保存(2節「対象外」への統合、2026-09-02追記)

2節で「別課題として残す」としていた曜日別営業時間・臨時休業日について、7節と同じ考え方
(発火判定には使わないが書き込みだけ本フローに結線する)で、生値(raw)のみの保存を統合する。
区間の妥当性検証自体(重複区間・0分間区間チェック等)は引き続きweekday-specific-business-
hours.md・ad-hoc-closed-dates-support.md側の担当のまま変更しない。

### 8.1 追加ペイロード項目

```json
{
  "weekday_business_hours_raw": {"5": "10:00-15:00", "6": "定休日"},
  "closed_dates": ["2026-09-15", "2026-12-31"]
}
```

- `weekday_business_hours_raw`: 「曜日ごとに営業時間を変える」トグルON時のみ届く想定
  (owner-settings-wireframe.md)。キーは`date.weekday()`準拠0(月)〜6(日)、値は
  `business_hours_raw`と同じ表記の生文字列。トグルOFF・未入力時はフィールド自体が省略される
  想定で、その場合は空dictとして扱う。キーが0〜6の整数として解釈できない、または値が
  空文字列・非文字列の要素は不正入力として黙って除外する(区間としての妥当性検証には
  踏み込まない、7節のFAQ情報未入力時と同じ「エラーにせず空のまま扱う」方針)。
- `closed_dates`: 臨時休業日入力欄(日付追加/削除リスト)。`YYYY-MM-DD`形式を想定するが
  本フローでは書式検証は行わず、非文字列・空文字列の除外と重複排除(入力順維持)のみ行う。
  過去日付・重複日付のインライン警告はNo-codeフォームツールのUX側に委ねる方針
  (ad-hoc-closed-dates-support.md「残課題」)のため、専用のバリデーションコードは実装しない。

### 8.2 書き込み先

`stores/{storeId}`ドキュメントの`weekdayBusinessHoursRaw`・`closedDates`へ、7節と同じく
5節の発火判定用フィールドとは独立に(判定への結線順序制約なしで)全体上書きする。

### 8.3 構造化値への変換は対象外

`AvailabilitySearcher`(prototype/engine.py)が実際に要求する分単位の構造化済み値
(`weekday_business_hours: dict[int, tuple[int,int]]`・`closed_dates: frozenset[date]`)への
変換・パースは、本フローの範囲外のまま残す。`business_hours_raw`同様、生値の保存までが
本モジュールの責務であり、実際の変換は
store-id-resolution-and-owner-identity-design.md「残課題」に記載の
`ConversationEventProcessor`組み立てファクトリ関数(実Firestore接続待ちのため未着手)側で
行う想定。

### 8.4 プロトタイプ実装方針

`StoreSettingsStoreProtocol`に`set_weekday_business_hours_raw`・`set_closed_dates`を追加し、
`InMemoryStoreSettingsStore`に対応する保持先を追加した。`normalize_weekday_business_hours_raw()`・
`normalize_closed_dates()`を新設し、`handle_store_settings_submission()`から7節と同じ
「発火判定ロジックへの入力には含めない」書き込み処理として呼び出す。テスト9件追加。

## 残課題

- Googleフォーム自体の作成・GAS配置(外部サービスへの実設定)はオーナー承認待ち。
- 実Firestore接続後、`FirestoreStoreSettingsStore`が`StoreSettingsStoreProtocol`と
  `StoreProfileStoreProtocol`の両方を満たす実装になることの最終確認(実接続はオーナー
  承認待ち)。
- 8.3節の通り、raw値から`AvailabilitySearcher`向けの構造化済み値への変換自体は引き続き
  未着手(ConversationEventProcessor組み立てファクトリ関数側の課題として残す)。
