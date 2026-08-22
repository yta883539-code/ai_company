# LLMターンごとの入力コンテキスト設計(2026-08-22 10:00 UTC)

## 位置づけ

llm-quality-verification-plan.md(2026-08-22 00:00 UTC作成)フェーズ(続き111)・
フェーズ(続き121)で残課題として持ち越されていた「複数ターンにまたがる状態遷移
(候補提示→選択→確定)の検証をどう自動化するか」を検討する過程で見つかった、
より根本的な未設計事項を扱う。

## 発見した設計ギャップ

`ConversationEventProcessor.process()`(prototype/cloud_function_process_event.py)は
`intent`による分岐ではなく、`ConversationFlowStateMachine.stage(user_id)`
(Firestore側は`stores/{storeId}/conversations/{sessionId}`ドキュメントの`stage`
フィールド、firestore-data-model.md参照)によって`_start_new_booking()`/
`_handle_candidate_selection()`/`_handle_details()`のどれを呼ぶかを決定する設計に
なっている。つまり「今どのステップにいるか」はサーバー側(Firestore)が構造的に
保持しており、LLMがそれを会話履歴から推測する必要はない。ここまではdouble-booking-
prevention.md・candidate-presentation-and-selection-design.mdの設計通りで問題ない。

しかし、`llm_call: Callable[[], dict]`(engine.py `process_llm_output()`)は
**引数を取らないクロージャ**であり、`process()`はイベントごとに1回だけ`llm_call()`を
呼ぶ。この`llm_call`が実際には何を渡してLLM APIを呼ぶのか(システムプロンプトに加えて、
直近の顧客メッセージだけを渡すのか、過去の会話ターンも含めて渡すのか)は、
llm-system-prompt-draft.md・conversation-samples-test-cases.mdのどこにも明記されて
いなかった。

この点を、既存のテスト(test_cloud_function_process_event.py
`CandidateSelectionAndDetailsTests`)のスタブ`llm_call`実装で確認したところ、
以下のように**暗黙に「LLMが前のターンの内容を覚えている」ことを前提にしたスタブ**に
なっていることが判明した。

```python
def llm_call_select():
    return {
        "intent": "new_booking", "name": None, "menu": "カット",  # ← turn1のメニューを
        "datetime_candidate": "1番目", "confirmed": False, "needs_owner_check": False,  #   再掲している
    }
processor.process(_event("U1", "1番で"), llm_call_select, NOW)
```

顧客の実際の発言は「1番で」だけであり「カット」というメニュー名を含んでいない。
もし実LLM APIをこのターンだけの単発呼び出し(直近メッセージのみを渡す設計)で行うと、
LLMは`menu`を`null`で返す可能性が高い。これまでのスタブテストは、テスト作成者が
「本来LLMが返すべき正解」を手で埋めていたため、この抜け漏れが表面化していなかった。

同様の問題は氏名・メニュー確認ターン(`_handle_details`)にも存在する。顧客が
「山田です」とだけ返信し、メニュー(「カットで」)を再掲しなかった場合、旧実装
(`name, menu = output.get("name"), output.get("menu")`)では`menu`が`None`となり
`REASK_NAME_MENU_MESSAGE`(氏名・メニューの再質問)が返ってしまう。これは、既に
turn1で「カット」と明示的に伝えている顧客に対して同じ情報を繰り返し尋ねる、
実際のLINE会話としては不自然なUXバグになりうる。

## 対応方針の検討

検討した2案:

1. **LLMに会話履歴(過去の顧客メッセージ・アシスタント返信)を毎ターン渡し、LLMの
   記憶に委ねる。** Claude APIのMessages APIは複数ターンの`messages`配列をサポート
   しており技術的には可能。ただし(a)ターンが進むほどトークン数が線形に増えコストが
   増加する、(b)LLMの記憶頼みだと「まれにmenuを思い出せず`null`を返す」不安定性が
   残り厳守事項1(3点揃うまで確定しない)の判定基準がLLMの記憶精度に依存してしまう、
   (c)firestore-data-model.mdの会話状態ドキュメントには現状メッセージ本文の履歴を
   保存する設計が無く、追加が必要になる。
2. **サーバー側(ConversationEventProcessor)が、turn1で確定済みの情報を構造的に
   引き継ぎ、LLMには「まだ確定していない情報」だけを埋めてもらう。** 既に
   `_search_context_by_user`(確定操作競合時の再検索用にturn1のLLM出力とメニュー
   所要時間をキャッシュする仕組み、booking-slot-manager-design.md「今後の課題」で
   実装済み)にturn1のメニュー名が残っているため、これをそのまま流用できる。

aircon-pasha・course-set-pashaと同様、本venture全体の設計方針として「LLMの記憶や
安定性に頼れる箇所は最小化し、構造的に保証できるところはサーバー側ロジックで担保する」
一貫した方向性を取ってきた(mandatory-two-step-order-enforcement-design.md、
fixed-vocabulary-tone-check-design.md等)ため、**案2(サーバー側の構造的引き継ぎ)を
採用**した。会話履歴をLLMに渡す設計(案1)は、トーン変換の一貫性判定など他の目的で
将来必要になる可能性はあるが、その場合も「厳守事項1の確定条件判定」のような安全性に
直結する箇所は案2の構造的引き継ぎを主とし、LLMへの履歴提供は補助的な文脈情報
(自然な受け答えの流暢さ向上)にとどめるべきという考え方を残す。

## 実装した内容

`ConversationEventProcessor`に`_carried_over_menu(user_id)`を新設し、
`_start_new_booking()`が検索直前に`_search_context_by_user[user_id] = (output,
menu_minutes)`でキャッシュしているturn1のLLM出力からメニュー名を取り出せるようにした。

- `_handle_candidate_selection()`: `menu = output.get("menu") or ""` を
  `menu = output.get("menu") or self._carried_over_menu(user_id) or ""` に変更。
  LLMがmenuを返さなかった場合もhold文言のメニュー欄が空欄化しない。
- `_handle_details()`: `name, menu = output.get("name"), output.get("menu")` を
  `name = output.get("name")` / `menu = output.get("menu") or
  self._carried_over_menu(user_id)` に変更。LLMがmenuを返さなかった場合も
  再質問(`REASK_NAME_MENU_MESSAGE`)に落とさず、turn1のメニューで確定処理へ進む。
  氏名(`name`)は毎ターン新規に聞く情報のため引き継ぎの対象外のまま。

`_search_context_by_user`は`_start_new_booking()`(通常予約・change経由の再検索
いずれも含む)で必ず設定されるため、`awaiting_details`/`candidates_presented`
ステージに到達している時点でキャッシュが欠けているケースは想定していない
(欠けていた場合は`_carried_over_menu()`が`None`を返し、従来通りLLM出力のみに
依存する安全側の挙動になる)。

テストはtest_cloud_function_process_event.py `CandidateSelectionAndDetailsTests`に
2件追加(`test_candidate_selection_carries_over_menu_when_llm_omits_it`・
`test_details_carries_over_menu_when_llm_omits_it_and_confirms`)。既存の
`test_missing_name_or_menu_reasks_without_calling_provide_details`
(氏名・メニューとも`None`のケース)は、メニューが引き継がれても氏名は依然`None`のため
再質問に落ちる挙動が維持されることを確認済み(全298件パス)。

## 残る課題

- 本設計は「turn1で一度確定した情報をturn2・turn3で引き継ぐ」という限定的な範囲の
  修正であり、turn1自体(初回メッセージでの`intent`・`requested_date_range`等の
  抽出)の精度は引き続き実LLM検証(オーナー承認待ち)でしか確認できない。
- トーン変換(厳守事項7)・雑談対応(厳守事項9b)等、会話の自然さに関わる判定は
  引き続きLLM単発呼び出しの範囲内で行う設計のままであり、本ドキュメントの対象外。
- 案1(会話履歴をLLMに渡す設計)を将来的に採用する場合は、firestore-data-model.mdの
  会話状態ドキュメントへのメッセージ履歴フィールド追加、トークン増加によるコスト
  試算(llm-api-cost-estimate.md相当、line-reservation-aiには現状専用ファイルが
  無い)の見直しが必要になる。今回はスコープ外とした。
- llm-quality-verification-plan.mdの検証観点表(厳守事項1)に、「LLMがmenu/nameを
  再掲しなかった場合にサーバー側の引き継ぎで確定条件が正しく揃うか」という観点を
  追加するかは次回以降の検討課題とする。
