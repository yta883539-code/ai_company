# エスカレーション(厳守事項6・10・9a未登録項目)発生時のオーナー通知文面

作成日: 2026-07-31

## 目的
llm-system-prompt-draft.md 次のステップ候補にあった
「エスカレーション(6・10番)発生時のオーナー通知文面の具体化(no-show-handling.mdの通知設計と統合)」を進める。
no-show-handling.mdは「無断キャンセル」検知時の通知(翌朝ダイジェスト)を設計済みだが、
厳守事項6(予約以外の相談・未登録FAQ)・10(未実装機能問い合わせ)は会話中に即時発生するため、
通知タイミング・文面ともに別設計とする。

## 通知タイミングの整理

no-show-handling.mdの通知は「当日中に1回・翌朝ダイジェスト」だったが、6・10のエスカレーションは
llm-system-prompt-draft.mdの厳守事項3・6の通り「即座にエスカレーション」が前提のため、
検知した会話ごとに都度・即時通知する(ダイジェスト化しない)。
理由: 医療相談やクレームは対応の初動が遅れるほど顧客体験・トラブルリスクが大きくなるため。

ただし同一顧客から短時間(目安5分以内)に複数回連続でエスカレーションが発生した場合は、
通知の連投を避けるため1通にまとめる(具体的な集約ロジックは実装時に検討、今回は方針のみ)。

## 通知文面の基本形

tone-and-manner-guideline.mdの「主語は店ではなくシステム管理側」の例外として、
オーナー向け通知は内部管理画面からの事務連絡として「AI」「システム」の主語を使ってよい
(顧客向けメッセージのみ「お店主語」ルールが適用される)。

共通フォーマット:
```
【要確認】[顧客名]様より{時刻}にお問い合わせがありました。
種別: {種別ラベル}
内容: {会話要約(1〜2文)}
対応: 店舗から直接ご連絡または次回来店時にご案内をお願いします。
```

## 種別ごとの文面

### 厳守事項6-a: 医療・健康相談
```
種別: 医療・健康相談
内容: 「[施術後の腫れについて相談したい]」といった内容です。AIは回答せずお待たせしています。
対応: 医療に関わる内容のため、可能な範囲で早めのご連絡をお願いします。
```

### 厳守事項6-b: 料金交渉
```
種別: 料金・割引のご相談
内容: 「[常連なので少し安くならないか]」といった内容です。AIは金額判断を行わずお待たせしています。
対応: 店舗の判断で回答内容をご検討のうえご連絡ください。
```

### 厳守事項6-c: クレーム
```
種別: クレーム・ご意見
内容: 「[前回の施術の仕上がりについて不満]」といった内容です。AIは謝罪・返金等の判断を行わずお待たせしています。
対応: 内容の性質上、できるだけ早いご連絡を推奨します。
```

### 厳守事項6-d: 9a未登録項目についてのFAQ質問
```
種別: 未登録FAQへのお問い合わせ
内容: 「[電子マネー(iD)は使えるか]」というお問い合わせですが、店舗FAQ情報が未登録の項目です。
対応: 店舗からご案内のうえ、今後同様の質問が増えるようであればFAQ情報欄への登録をご検討ください。
```
- 「今後同様の質問が増えるようであれば登録を検討」の一文は、未登録項目の通知が続く場合に
  オーナーが設定画面(owner-settings-wireframe.md)への入力を思い出すきっかけとして毎回付与する。

### 厳守事項10: 未実装機能(デポジット決済等)の問い合わせ
```
種別: 未対応機能に関するお問い合わせ
内容: 「[予約時にクレジットカードで前払いできるか]」というお問い合わせです。
    現在は未提供の機能のため、AIは「対応可否は確認中」とだけ回答し保留しています。
対応: 対応予定がある場合はその旨、予定がない場合はその旨を、店舗から直接ご案内ください。
```
- deposit-payment-research.mdで検討中のデポジット機能そのものの要否判断とは別に、
  問い合わせ件数を記録しておくことで「需要の裏付けデータ」としてオーナーの導入判断材料にもなる
  (顧客詳細画面ではなく、店舗全体の通知ログとして件数を集計する想定。詳細設計は次回以降)。

## 複合FAQ質問(faq_segments)が一部未解決の場合の通知

json-schema-multi-intent-extension.mdの`faq_segments`で`resolved: false`が含まれる場合、
どの項目が未回答だったかを通知に明記する(項目名だけでは店舗側が分かりにくいため日本語ラベルに変換する)。

topicラベル対応表:
- access → 「アクセス・行き方」
- parking → 「駐車場」
- payment → 「支払い方法」
- hours → 「営業時間・定休日」
- other → 「その他FAQ」

文面例(E13aを想定、駐車場が未登録で他は9aで回答済みのケース):
```
種別: 複合質問の一部未回答
内容: アクセス・支払い方法はご案内済みですが、「駐車場」は店舗FAQ情報が未登録のため保留中です。
対応: 駐車場についてのみ店舗からご案内をお願いします(他項目は回答済みのため再送不要です)。
```
- 「回答済みの項目は再送不要」と明記するのは、オーナーが全項目に対応し直してしまい
  顧客に同じ内容が二重に案内される事故を防ぐため。

## 未検討・要検討事項
- 「短時間の連続エスカレーションを1通にまとめる」の具体的な時間窓・実装方法は未設計(方針のみ)。
  → (解消 2026-08-01: escalation-consolidation-logic.mdで5分ウィンドウ方式として具体設計済み)
- 未登録FAQの通知件数集計(店舗全体の通知ログ)の画面設計はowner-settings-wireframe.mdに未反映。
  → (解消: notification-log-classification-labels.md・owner-settings-wireframe.mdに反映済み)
- 本文面のトーン(「〜をお願いします」等)がtone-and-manner-guideline.mdの顧客向けトーンと
  混同されないよう、実装時にオーナー向け通知用と顧客向けメッセージ用でテンプレートファイルを
  明確に分けるべきという設計メモを残す(今回はドラフトの文面整理のみ)。
  → (解消 2026-08-06 20:00 UTC: prototype/engine.pyのformat_escalation_notification()/
  format_escalation_digest_message()を顧客向けformat_*関数群とは別に新設し、明確に分離した)
- 本文面(基本形)の「内容」欄は会話要約の生文言を想定していたが、現状の構造化出力
  (booking_output.schema.json)には会話要約フィールドが無い(`feature_hint`のみ自由記述)。
  実装(prototype/engine.pyのformat_escalation_notification())では暫定的に
  「詳細はLINEトーク画面で内容をご確認ください」への案内に留めている。会話要約フィールドの
  追加要否は今後の課題として残す。
  → (解消 2026-08-06 22:00 UTC: 構造化出力へのLLM生成要約フィールド追加は「行わない」と結論した。
  理由は(1)医療相談・クレーム等の機微な内容をLLMが要約する過程で誤読・言い換えが混入するリスクが
  あり、オーナーが実際の顧客発言と異なる内容を信じてしまう事故につながりうること、(2)Cloud
  Function Bの`process()`は既にLINE Webhookイベントから顧客の生メッセージ本文(`reply_text`)を
  取得済みで、要約せずそのまま引用すれば内容欄の目的(オーナーが概要を即座に把握できること)を
  追加のLLM出力なしに満たせること。実装状況を参照。)

## 実装状況(2026-08-06 20:00 UTC追記)
- prototype/engine.pyに`format_escalation_notification()`(個別即時通知)・
  `format_escalation_digest_message()`(ウィンドウ集約分のまとめ通知)を実装し、
  prototype/cloud_function_process_event.pyの`ConversationEventProcessor._notify_owner()`/
  `flush_escalation_windows()`から呼び出す配線を実装した(owner-notification-channel-design.md参照)。
  これまで`EscalationConsolidator.on_event()`の戻り値(即時通知すべきアクション)は
  全ての呼び出し箇所で破棄されており、実際にオーナーへpushされることは一度も無かった
  (first-booking-self-check-notification-design.md由来の初回予約通知を除く)。
- `needs_owner_check: false`のイベント(9b雑談等)は`EscalationConsolidator`のウィンドウ管理
  対象にはなるが、`is_escalation_event_owner_notable()`によりオーナーへの実push対象からは除外する
  (schema/validate_test_cases.pyのクロスフィールド検証で「faq_segmentsに未解決項目があれば
  needs_owner_check必須true」が保証されているため、この判定を信頼できる)。
- 残課題(解消 2026-08-06 21:00 UTC): `ConversationFlowStateMachine`内部(engine.py)から発火する
  システムイベント(booking_conflict/candidate_selection_unresolved/booking_cancelled/
  booking_change_started)をCloud Function B側へ伝播させる仕組みを実装した。engine.py自体は
  引き続きLINE Push等のI/Oを持たないPurely-logic層のまま、`select_slot_from_reply()`/
  `provide_details()`/`cancel_booking()`/`change_booking()`の戻り値に`owner_notify_actions`
  フィールド(`EscalationConsolidator.on_event()`が返す即時通知アクションをそのまま運ぶ)を追加した
  (`provide_details()`は戻り値をbool単体から`ProvideDetailsResult`に変更)。
  `prototype/cloud_function_process_event.py`に新設した`_dispatch_flow_notify_actions()`が
  これを受け取りpushする。Flow側が既に`consolidator.on_event()`を呼び済みのため、
  `_notify_owner()`(LLM構造化出力起点のイベント用)とは別経路にして`on_event()`の二重呼び出し
  (ウィンドウ状態の二重更新)を避けた。テスト9件追加(engine.py側4件・
  cloud_function_process_event.py側4クラス)・既存分含め全155件パス。
- 残る課題(解消 2026-08-06 22:00 UTC): 会話要約フィールド(構造化出力への追加要否)を検討し、
  上記「未検討・要検討事項」の通り「追加しない」と結論した。代わりにCloud Function Bが既に
  保持している顧客の生メッセージ本文(`process()`の`reply_text`)を、`format_escalation_notification()`
  の「内容」欄にそのまま引用するよう実装した。`_escalation_detail_text()`に`reply_text`引数を追加し、
  `_notify_owner()`(LLM構造化出力起点のイベント: escalation/faq未解決/cancel_not_found/
  change_not_found/unregistered_menu等)経由の通知はreply_textを渡して引用付きにした。一方、
  `_dispatch_flow_notify_actions()`経由のシステム内部イベント(booking_conflict等)は、顧客の
  1メッセージに1対1で対応する内容ではない(状態遷移の結果であり特定の発言の引用では説明できない)
  ため、意図的にreply_textを渡さず従来通り「詳細はLINEトーク画面で内容をご確認ください」の
  案内文言のままとした(_dispatch_flow_notify_actions()のdocstring参照)。テスト3件追加
  (engine.py側の変更はcloud_function_process_event.py側の統合テストで間接的に検証)・
  既存分含め全157件パス。
  残る課題は`flush_escalation_windows()`を定期実行するCloud Scheduler自体の設定
  (オーナー承認待ち、pending-approval.md参照、reminder_scheduler.pyと同じ位置づけ)のみ。

## 次のステップ候補
- (解消済み 2026-08-07 09:00 UTC: 本ファイルの文面をllm-system-prompt-draft.mdの厳守事項6・10・9a
  未登録項目の説明文から参照するリンクを追記した。厳守事項6→6-a/6-b/6-c節、9a未登録項目→6-d節+
  複合FAQ一部未解決時の通知節、厳守事項10→10節、の対応で相互参照を張った。文面自体の変更は無し)
