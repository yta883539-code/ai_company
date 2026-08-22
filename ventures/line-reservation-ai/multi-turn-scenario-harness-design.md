# 複数ターンにまたがる状態遷移の検証ハーネス設計(2026-08-22 13:00 UTC)

## 位置づけ

llm-quality-verification-plan.md「残る未確定事項」に残っていた、複数ターンにまたがる
状態遷移(候補提示→選択→確定)の検証を「実LLM出力を各ターンの入力として連鎖させる」
部分の設計・試作。フェーズ(続き122、llm-turn-context-design.md)までの検討過程で発見した
「各ターンのLLM呼び出しは会話履歴を含まない単発呼び出し」という設計を踏まえ、複数ターンの
シナリオを`ConversationEventProcessor.process()`への複数回の呼び出し列として表現できる
汎用ハーネスを作った。

## 発見: conversation-samples-test-cases.mdのN1→N3は「2ターン」ではなく実装上「3ターン」

conversation-samples-test-cases.mdのN3は「N1の続き」として
「その時間でお願いします」という1回の返信だけで確定に至る、2ターン構成の会話として
記述されている。しかし実装(`ConversationFlowStateMachine`/`ConversationEventProcessor`)は
以下の3段階を必ず踏む設計になっている(candidate-presentation-and-selection-design.md・
booking-slot-manager-design.md準拠)。

1. 検索ターン: 名前・メニュー・大まかな日時希望→候補提示(`candidates_presented`)
2. 選択ターン: 提示した候補一覧から1件を特定し仮押さえ(`held`/`awaiting_details`)
3. 確定ターン: 名前・メニューの最終確認→確定(`confirmed`)

さらに`resolve_candidate_selection()`(engine.py)は選択ターンの特定を**顧客の返信文言
(reply_text)そのもの**(番号・候補ラベルの日付時刻表記との一致)でのみ行い、LLM構造化出力の
フィールド(intent等)は使わない。そのため「その時間でお願いします」という指示語だけの
返信は番号にも日付時刻表記にも一致せず、実装上は選択不能(`resolve_candidate_selection()`が
`None`を返し`format_reconfirm_message()`で聞き直しになる)ことを本ハーネス作成の過程で
確認した。

これは会話サンプル設計(ビジネスレベルの期待挙動の記述)と実装(状態遷移の技術的な粒度)の
間の抽象度の違いであり、どちらかが誤りというわけではない。N3の「その時間で」は
「ユーザーが直前に提示された1件を肯定した」という業務的意図の要約であり、実際にどの文言
パターンなら選択が成立するかはcandidate-presentation-and-selection-design.md 2節の実装詳細
(数字・丸数字・漢数字・日付時刻表記との一致)に委ねられている。

**結論**: ハーネスでN1→N3を再現する場合、選択ターンの返信文言は会話サンプルの原文
(「その時間でお願いします」)をそのまま使わず、`resolve_candidate_selection()`が実際に
解決できる文言(例:「1番で」)に置き換える。これはconversation-samples-test-cases.md自体を
訂正するものではなく、「業務シナリオの記述」と「その業務シナリオを満たす実装上の入力例」を
区別する扱いとする(実LLM接続後、実際に「その時間でお願いします」的な指示語のみの返信が
どの程度の頻度で来るかは未知数であり、選択不能が多発するようであれば
resolve_candidate_selection()側の指示語対応〈直前候補が1件のみなら指示語で確定してよい、等〉
を拡張課題として別途検討する。今回はハーネス設計のスコープ外として残す)。

## ハーネスの設計

`prototype/scenario_harness.py`に以下を実装した。

- `ScenarioTurn`: 1ターン分の入力(`message`)とLLM出力(`llm_output`、スタブでも実API
  レスポンスでも同じ形)、任意の期待値(`expect_action`/`expect_stage`)を持つデータクラス。
- `run_scenario(processor, turns, now, user_id)`: `turns`を順番に
  `ConversationEventProcessor.process()`へ流し込む。各ターンの`llm_output`は投入前に
  `schema/validate_test_cases.py`の`validate_against_schema()`・`validate_cross_field_rules()`で
  机上検証し(実LLM接続後もそのまま同じ経路で使える)、結果を`ScenarioStepResult`のリストとして
  返す。`expect_action`/`expect_stage`が指定されていればその場で`AssertionError`を送出する
  (unittest外からの手動実行にも使える汎用ヘルパーとするため、`unittest.TestCase.assert*`には
  依存しない)。

`llm_output`は現状すべて会話サンプル準拠のスタブだが、`process_llm_output()`へ渡す
`llm_call`の中身を実際のClaude API呼び出しに差し替えるだけで実LLM検証にそのまま流用できる
設計(`ScenarioTurn`はスタブか実APIかを意識しない)。

## 試作: N1→(選択)→N3の3ターンシナリオ

`prototype/test_scenario_harness.py`に、上記の発見を反映した3ターンシナリオを実装した。

1. ターン1: N1の入力(「来週土曜15時にカットお願いしたいです。田中です。」)相当のLLM出力
   (`requested_date_range`=来週土曜、`time_of_day_preference`="afternoon")→
   `candidates_presented`を期待。
2. ターン2: 「1番で」→選択(`held`、`awaiting_details`)を期待。
3. ターン3: N3の期待構造化出力を**そのまま**転記した
   `{intent: "new_booking", name: "田中", menu: "カット", datetime_candidate: "来週土曜15時",
   confirmed: true, needs_owner_check: false}`を投入し、`confirmed`を期待。

3ターン全ての`llm_output`がスキーマ・cross-fieldルールに違反しないこと、最終的に
`flow.stage("U1") == "confirmed"`であることをテストで確認済み(実行結果は
下記「実行結果」参照)。

## 実行結果

`python3 -m unittest test_scenario_harness -v`(prototype/ディレクトリで実行)で
新規追加分がパスすることを確認した(プロトタイプ全体のテスト件数はtest_engine.py・
test_cloud_function_process_event.py等と合わせて別途確認)。

## 追記(2026-08-22 16:00 UTC): E3(二重予約)をハーネスで再現・複数顧客対応の拡張

上記「残る課題」1点目のうちE3(二重予約)をハーネスで再現した(`test_scenario_harness.py`の
`E3BookingConflictScenarioTest`)。この過程で以下2点を行った。

- **ハーネスの拡張**: `ScenarioTurn`に任意の`user_id`フィールドを追加し、`run_scenario()`が
  ターンごとに宛先ユーザーを切り替えられるようにした(未指定時は従来どおり関数引数の
  `user_id`を使うため後方互換)。単一ユーザーの会話(N1→N3等)だけでなく、E3のように
  複数顧客の会話を実際の到着順でinterleaveして検証できるようになった。
- **E3の再現方法の選定**: 既存の`test_cloud_function_process_event.py`の
  `test_booking_conflict_notifies_owner_once_and_represents_fresh_candidates`は
  確定操作時(`provide_details`→`confirm()`)の競合を`flow._slots`への直接操作で人工的に
  再現している。一方`AvailabilitySearcher.find_candidates()`は`booking_slots.status()`が
  `None`の枠のみを候補にするため、後から検索した顧客には既にhold済みの枠は最初から
  候補として出てこない。そのためE3の入力例(「顧客Bが顧客Aの仮押さえ中の枠を指定」)を
  内部操作なしに再現するには、①両顧客がまだ誰も枠を持たない時点で同じ候補一覧を受け取り、
  ②顧客Aが選択・hold成功した「後」に、③顧客Bが(Aの選択を知らないまま)同じ候補ラベルを
  選ぶ、という順序が必要と判明した。これは選択操作時(`select_slot_from_reply`→`hold()`)の
  競合であり、確定操作時競合(action=`booking_conflict`)とは別経路(action=`reask`、
  `SLOT_CONFLICT_MESSAGE_TEMPLATE`)であることを、実装コード(engine.py)の追跡により
  新たに確認した(これまでこの選択時競合の経路には自動テストが無かった)。
- 副次的な発見として、`_handle_candidate_selection()`は「返信文言から候補を特定できな
  かった場合」(reconfirm)と「特定できたが他ユーザーとの競合でhold()に失敗した場合」を
  どちらもDispatchResult.action=`"reask"`として返しており、呼び出し側ログ・分析では
  メッセージ内容(`SLOT_CONFLICT_MESSAGE_TEMPLATE`か`format_reconfirm_message()`か)でしか
  区別できない。実装上の不具合ではないが、実運用後に競合発生頻度を計測したい場合は
  actionの分離を検討余地として残す(現時点では計測要件が無いため見送り)。

テスト2件追加(スロット競合時のメッセージ内容確認・競合後もB側の会話状態が壊れず
別枠を選び直せることの確認)、プロトタイプ全体302件パス。

## 追記(2026-08-22 19:00 UTC): E1をハーネスで再現、および発見(`menu: null`が候補提示に至らない)

上記「残る課題」1点目だったE1(曖昧な日時)を`test_scenario_harness.py`の
`E1AmbiguousDatetimeScenarioTest`として再現した。この過程で、E1の
「期待される構造化出力」(conversation-samples-test-cases.md記載の
`{intent: "new_booking", name: null, menu: null, datetime_candidate: "来週平日午後の
空き候補(複数)", confirmed: false, needs_owner_check: false}`)を一字一句そのまま
`ConversationEventProcessor.process()`へ投入すると、ドキュメントが想定する
`candidates_presented`(複数候補提示)には至らず、`forwarded_to_owner`
(detail=`unregistered_menu`)になることを発見した。

原因は`resolve_menu_duration()`(cloud_function_process_event.py)が
`menu_name`が偽値(未言及でNone、または空文字列)の場合を「未登録メニュー」と
同一のNone返却で扱っている設計(docstring:「未登録メニューはNoneを返し、呼び出し側は
オーナーへのエスカレーションに倒す」)による、意図した挙動である。つまり
「メニュー名が読み取れなかった(未言及)」と「メニュー名は読み取れたが店舗未登録」の
2つのケースが実装上区別されておらず、前者(E1のように日時のみ言及でメニュー未言及の
新規予約)も後者と同じくオーナー転送になる。

これはN1→N3の発見(multi-turn-scenario-harness-design.md本文)と同種の、
「会話サンプル(ビジネスレベルの期待挙動)」と「実装(技術的な判定粒度)」の
抽象度の違いである。E1自体は「日時が曖昧」という状況を示す例として書かれており、
メニューの言及有無は本質ではないため、ドキュメント側が誤りとは言い切れない。
一方、実際の顧客対応では「日時だけ先に聞いてきてメニューは後で伝える」会話は
十分あり得るため、この場合に毎回オーナー転送(=人手対応)になるのは机上の
想定より対応コストが高くなる可能性がある。

`E1AmbiguousDatetimeScenarioTest`では、(1)ドキュメント記載どおり`menu: null`を
投入した場合に実際に`forwarded_to_owner`/`unregistered_menu`になることの確認と、
(2)メニューも判明している場合(例:「来週の平日午後とかでカットお願いしたいです」)
にはE1が意図する「複数候補提示・`confirmed: false`のまま単一ターンで完結」という
挙動を実際に確認できることの、2つに分けてテストした。テスト2件追加、
プロトタイプ全体302件パス。

## 残る課題

- 上記発見(「メニュー未言及」と「メニュー未登録」の未区別)への対応方針は、
  (a)現状維持(メニュー不明時は常にオーナー転送、確実だが人手対応が増えうる)、
  (b)「メニュー未言及」の場合のみ聞き返しメッセージ(reask)で先にメニューを
  確認してから候補提示に進む、(c)メニュー未指定のまま全メニュー共通で空き候補を
  提示し確定前にメニューを確認する、の少なくとも3案があり、いずれもプロンプト設計
  (llm-system-prompt-draft.md)・状態遷移(intent-to-flow-mapping.md)双方への影響が
  あるため、今回はハーネスでの発見の記録にとどめ、対応方針の決定は次回以降の設計課題
  として残す(支払い・外部接続を伴わない設計判断のためオーナー承認事項ではないが、
  プロンプト変更は既存の全会話フローに影響するため慎重な検討が必要と判断)。
- 「その時間でお願いします」のような指示語のみの返信をresolve_candidate_selection()が
  解決できない点(上記「発見」参照)自体は実装上の制約として残っており、実装を拡張するか
  会話サンプル側の記述を「1番で」等の明示的な返信に訂正するかはオーナー確認事項ではなく
  今後の設計判断課題として残す(直前提示候補が1件のみの場合に限定すれば安全に指示語対応
  できる可能性がある)。
- 「その時間でお願いします」のような指示語のみの返信をresolve_candidate_selection()が
  解決できない点(上記「発見」参照)自体は実装上の制約として残っており、実装を拡張するか
  会話サンプル側の記述を「1番で」等の明示的な返信に訂正するかはオーナー確認事項ではなく
  今後の設計判断課題として残す(直前提示候補が1件のみの場合に限定すれば安全に指示語対応
  できる可能性がある)。
- 実LLM接続後、`ScenarioTurn.llm_output`を実際のAPIレスポンスに差し替えて同じハーネスを
  再利用する具体的な接続コード(`process_llm_output()`のllm_call注入)は、
  引き続きAPIキー・課金のオーナー承認待ち(pending-approval.md 2026-07-31 13:58 UTC記載の範囲)。
