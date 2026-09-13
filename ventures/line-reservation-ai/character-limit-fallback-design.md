# LINEテキストメッセージ文字数上限超過時のフォールバック設計(フェーズ続き221)

menu-pricing-faq-topic-decision.md「未解決のまま残す課題」に残っていた「メニュー件数が
多い店舗(10件以上等)で全件列挙が長文になりすぎる場合の省略・要約要否は未検討」に対応する。
併せて、aircon-pasha/course-set-pasha/kura-pashaの3venture全てに存在するのに本venture
だけに存在しなかった「LINE Messaging APIのテキストメッセージ文字数上限超過時のフォールバック
設計」自体の欠落(character-limit-fallback-design.md相当のドキュメント・実装が本venture未着手
だったギャップ)を解消するものでもある。

## 前提の再確認

- LINE Messaging APIのテキストメッセージ1件あたりの文字数上限は5,000文字、UTF-16コード単位
  でのカウント(aircon-pasha/course-set-pasha/kura-pashaのcharacter-limit-fallback-design.md
  と同じ前提)。
- 本venture固有の固定文言・トーン別テンプレート(candidate提示・確定・キャンセル・変更・
  リマインド・エスカレーション保留文言等)は、いずれも顧客名・候補ラベル・メニュー名1件のみを
  差し込む設計で、通常想定でも数百文字程度に収まる。
- 例外は`format_faq_menu_message()`(prototype/engine.py、menu-pricing-faq-topic-decision.md
  フェーズ続き219)のみで、店舗が登録するメニュー件数に比例して際限なく本文が伸びうる
  (owner-settings-wireframe.mdのメニュー設定ページには件数上限が設けられていない)。

## 本ventureとaircon-pasha等との違い

aircon-pasha/course-set-pasha/kura-pashaの3venture(以下「作業報告書系venture」)は、
LLM生成物(`completion_report.body`等)を業者がそのまま依頼者へコピー&ペースト転送する
運用のため、「切り詰めて送る」と依頼者への誤送信事故に直結する。そのため3venture共通で
「切り詰めは行わず、上限超過は送信失敗として扱いオーナー(業者)向けの定型フォールバック文言に
差し替える」方針を採用していた。

本ventureは、LINE公式アカウントが直接エンドカスタマー(予約希望者)とやり取りするチャットボット
であり、そもそも顧客への回答文言はLLMの自由生成ではなく`format_faq_*`系のテンプレート関数が
店舗の登録値を機械的に組み立てるのみ(厳守事項9a、AIによる言い換え・推測を行わない設計)。
かつ、本venture固有の「resolved:falseの未登録FAQ項目は`format_faq_unregistered_message()`
(担当者への確認を案内する保留文言)に自動フォールバックする」という既存の仕組み
(hours-other-faq-topic-resolution.md「決定1」・厳守事項6)が、そのまま「機械的に組み立てた
結果が長くなりすぎた」ケースにも転用できる。よって作業報告書系venture(送信失敗として扱い
定型フォールバック文言を新設)とは異なり、本ventureでは既存の保留文言をそのまま再利用する。

## 決定: メニューFAQのみ対象に、既存の保留文言へフォールバックする

1. `faq_segments`のうち`topic: "menu"`かつ`resolved: true`の項目についてのみ、
   `format_faq_menu_message()`で組み立てた本文のUTF-16コード単位数
   (`count_utf16_code_units()`)が`LINE_TEXT_MESSAGE_MAX_UTF16_UNITS`(5,000)を超えていないか
   確認する。他のFAQトピック(parking/access/payment/hours/other)は登録値・文言構造が
   本質的に有界(住所1件・支払い方法の短い列挙・時間帯の組み合わせ等)であり、対象としない。
2. 超過していた場合、その`seg["resolved"]`をFalseへ書き換える。これにより
   `_render_faq_segment()`の既存分岐(resolved:falseは`format_faq_unregistered_message()`)が
   そのまま適用され、長文のまま送信することも、途中で尻切れにして送信することも発生しない。
   `seg["resolved"]`の書き換えは`NotificationLogAggregator.record()`(未解決topicのユニーク
   集計)よりも前に行う必要がある(後述「実装上の注意」参照)。オーナー側は既存の未登録FAQ相談と
   同じ経路(通知ログ集計・エスカレーション通知)で「メニュー件数が多すぎて自動回答できなかった」
   事実に気づき、必要であれば個別に案内する運用とする。
3. 「省略して一部だけ列挙する」「文字数で機械的に切る」案は採用しない。一部のメニューのみ
   案内すると、案内されなかったメニューの存在自体に顧客が気づけず機会損失になりうる
   (かつどの基準で切るかの設計判断が発生する)ため、全件案内するか、担当者に確認する保留文言に
   倒すかの二択とし、後者を安全側の挙動として採用する。
4. 実運用でこの分岐に到達する店舗(メニュー数百件超)は現実的にはまず想定されないが、
   境界を明確に決めておくことで「対応漏れ」ではなく「意図的な設計」であることを示す。

## 実装上の注意: `_logs.record()`より前に判定する必要がある

`ConversationEventProcessor._process_message_event()`は、`intent`別の分岐
(`_handle_faq()`等)に入る**前**に`self._logs.record(user_id, output, now)`を呼び、
その時点の`output["faq_segments"]`(各`resolved`値)をそのままNotificationLogAggregatorの
未解決topic集計に使う(duplicate-topic-notification-log-rule.md準拠)。

そのため、文字数超過による`resolved`の書き換えを`_handle_faq()`の中(顧客への送信直前)で
行うと、`_logs.record()`は書き換え前の`resolved: true`を見てしまい、「本来は担当者確認が
必要になったのに通知ログ・オーナー通知には反映されない」という不整合が生じる
(new-booking-needs-owner-check-notification-design.mdが警告していたのと同種の「合成した
イベントが集計より後に発生する」落とし穴)。

これを避けるため、`_apply_menu_length_fallback(output, tone)`を`_process_message_event()`
内の`self._logs.record()`呼び出しの直前に新設し、`output["faq_segments"]`を直接ミューテートする
方式を採用した。`_handle_faq()`側は通常の未解決項目と同じ扱いで`_render_faq_segment()`に
委ねるだけでよく、文字数チェックを意識する必要はない。

## 反映箇所

- `prototype/engine.py`: `LINE_TEXT_MESSAGE_MAX_UTF16_UNITS`(定数)・
  `count_utf16_code_units()`(UTF-16コード単位数算出、サロゲートペア対応)を新設。
- `prototype/cloud_function_process_event.py`: `ConversationEventProcessor._process_message_event()`
  内、`self._logs.record()`呼び出し直前に`self._apply_menu_length_fallback(output, tone)`を
  追加。新設した`_apply_menu_length_fallback()`が`topic: "menu"`かつ`resolved: true`の
  セグメントの本文長を確認し、超過時は`seg["resolved"]`をFalseへ書き換える。
- `prototype/test_engine.py`: `CountUtf16CodeUnitsTest`(ASCII・日本語・補助文字面
  サロゲートペア・空文字列の境界値テスト)を新規追加。
- `prototype/test_cloud_function_process_event.py`:
  `test_menu_topic_falls_back_when_message_exceeds_line_text_length_limit`を新規追加
  (メニュー600件で文字数超過を発生させ、保留文言への差し替え・`resolved: false`への
  書き換えによる未解決件数集計への反映を確認)。

venture全体800件(796件→800件)・schema検証27件いずれもパスを確認した。

## 残る課題

- 実際の店舗のメニュー登録件数の実態(customer-interview-design.md)が見えた段階で、
  5,000文字という値より手前のソフトな閾値(実運用上「これは多すぎるのでは」と気づく水準)を
  別途設けるかどうかは、aircon-pashaのcharacter-limit-fallback-design.md「残課題」と同様、
  実LLM接続・実運用データを見ながら再検討する(現時点ではハード上限のみで十分と判断)。
- `format_faq_menu_message()`以外の`format_*`系テンプレート関数についても、将来店舗設定の
  自由記述欄(例: メニュー詳細説明文、menu-pricing-faq-topic-decision.md「未解決のまま
  残す課題」参照)が追加され、店舗が任意の長さの文字列を登録できるようになった場合は、
  同様の文字数チェック対象に加える必要がある。現時点ではそのような自由記述欄は存在しないため
  対象外とする。
