# 厳守事項9a「hours」「other」トピックの扱い決定(2026-08-03 08:00 UTC)

single-item-faq-schema-decision.mdの「未解決のまま残した課題」、およびjson-schema-multi-intent-
extension.mdの「未検証・要検討事項」で指摘されていた、`faq_segments[].topic`の列挙値
(access/parking/payment/hours/other)のうち、店舗FAQ情報の登録項目とテンプレートが
まだ無かった`hours`・`other`の2つについて、対応方針を決定する。

## 背景

- webhook-function-b-implementation.md・single-item-faq-schema-decision.mdの「未実装のまま
  残るもの」に記載の通り、`hours`・`other`はresolved: trueが返っても安全側で保留文言に
  フォールバックする既存挙動のまま放置されていた。
- llm-system-prompt-draft.mdの厳守事項9a説明文には元々「営業時間・定休日」が9a対象として
  明記されていた(店舗が事前登録した静的情報の一つ)が、faq-response-templates.mdの
  項目別テンプレートには反映されておらず、説明文とテンプレートの間に食い違いがあった。

## 決定1: hours

owner-settings-wireframe.mdの営業情報設定ページには、既に営業曜日・営業時間(単一区間)・
「曜日ごとに営業時間を変える」トグル・「休憩時間を追加」の各項目が登録されている
(weekday-specific-business-hours.md・business-hours-lunch-break.md参照)。これらを
そのまま組み合わせて自然文を自動生成することは、区間が可変長(曜日別・休憩時間区切り)に
なるため、「登録値をそのまま埋め込むだけ」というfaq-response-templates.mdの基本方針
(AIによる言い換え・推測を排除する)を素朴なテンプレートでは満たせない。

そのため、対応範囲を以下のように分ける:
- **シンプルな店舗**(曜日別営業時間トグルOFF・休憩時間未設定): 単一の開始・終了時刻と
  定休日(曜日)のみで正確に案内できるため、`format_faq_hours_message()`
  (prototype/engine.py)による自動テンプレート回答の対象とする。
- **複雑な店舗**(曜日別営業時間トグルON、または休憩時間設定あり): 単一区間のテンプレートでは
  不正確な案内になるため、自動回答の対象外とする。実装上は、Cloud Function B呼び出し側
  (店舗設定を`ConversationEventProcessor`に渡す層、GCPプロジェクト作成後に実装予定)が
  この判定を行い、複雑な店舗では`store_faq_info`に`hours`キーを設定しない運用とする。
  `_render_faq_segment()`(cloud_function_process_event.py)は`hours`キーが無ければ既存の
  安全側フォールバック(保留文言→厳守事項6のエスカレーション)にそのまま乗るため、
  トピック別の追加分岐は不要。
- 将来、曜日別営業時間・休憩時間にも対応した自然文生成(例:
  「月〜金10:00〜19:00、土10:00〜15:00、日定休」のような複数区間の列挙)を追加する余地は
  あるが、区間数が増えるほど「言い換えではなく登録値の機械的な組み立て」を保つロジックが
  複雑化するため、MVPでは見送り別課題とする。

## 決定2: other

owner-settings-wireframe.mdの「店舗FAQ情報」欄はaccess/parking/payment(+今回追加のhours算出元)
のみで、`other`に対応する登録項目は存在しない。`other`が何を指すかの定義自体が
json-schema-multi-intent-extension.md時点でも未確定だった。

登録項目が無い以上、`other`に対して安全に返せる登録値は存在しないため、
**`other`は常に厳守事項6のエスカレーション(保留文言)に倒す**と決定する。これは実装上は
「`_render_faq_segment()`に`other`用の分岐を追加しない」という既存コードのままで実現できる
(未知のtopic文字列は既存の安全側フォールバックに自然に落ちるため、コード変更は不要)。

`other`向けの専用入力欄を店舗FAQ情報に追加すべきかどうかは、実際の店舗ヒアリング
(customer-interview-design.md)で「access/parking/payment/hours以外によく聞かれる質問」が
具体的に見えてから検討する方が、当てずっぽうの項目設計を避けられるため、現時点では
入力欄の追加を見送る。

## 反映箇所

- `prototype/engine.py`: `format_faq_hours_message()`を新設。
- `prototype/cloud_function_process_event.py`: `_render_faq_segment()`に`hours`トピックの
  分岐を追加。`other`は分岐を追加せず既存フォールバックのまま。
- `prototype/test_cloud_function_process_event.py`: `hours`が登録済み/未登録(複雑な店舗)双方の
  挙動、`other`が常にフォールバックする挙動をそれぞれテストで固定(全132件パス)。
- `faq-response-templates.md`: 「営業時間」テンプレート・「その他(other)」節を追加。
- `conversation-samples-test-cases.md` / `schema/validate_test_cases.py`: E17(営業時間FAQ)を
  新規追加。

## 未解決のまま残す課題

- (解消済み 2026-08-07 08:00 UTC: 曜日別営業時間・休憩時間を使う店舗向けの自然文生成ロジックを
  `format_faq_hours_message_weekly()`(prototype/engine.py)として実装した。各曜日の登録区間
  (開始,終了)をそのまま機械的に列挙し、同一の区間構成が連続する曜日は「月〜金」のようにまとめる
  (非連続な一致はまとめない設計)。`_render_faq_segment()`
  (prototype/cloud_function_process_event.py)は`store_faq_info["hours"]`に
  `default_ranges`/`weekday_ranges`キーがあればこの新関数を、無ければ従来の単一区間版
  `format_faq_hours_message()`を呼び分けるよう変更した。テスト8件追加(engine 4件・
  process_event 1件の新規テストに加え、上記呼び分けの既存テストは無変更で通過)、
  全168件パス、schema検証25件も全件パス。これにより「複雑な店舗は自動回答の対象外」という
  制約はエンジン側では解消された)
- Cloud Function B呼び出し側で店舗設定(Firestore)から`store_faq_info["hours"]`に
  `default_ranges`/`weekday_ranges`形式を実際に組み立てて渡す配線は、GCPプロジェクト作成
  (オーナー承認待ち、pending-approval.md参照)後の着手となる。上記の通りengine側の関数と
  呼び分けロジックは実装済みのため、配線自体は「渡す値を組み立てる」だけで完了する状態にある。
- `other`向け入力欄の要否は、実顧客ヒアリング後に再検討する。
