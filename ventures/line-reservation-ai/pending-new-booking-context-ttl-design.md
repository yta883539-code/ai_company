# `_pending_new_booking_context_by_user` のTTL設計

## 背景

menu-unmentioned-vs-unregistered-design.mdの「既知の限界・今回のスコープ外」に、
`_pending_new_booking_context_by_user`(cloud_function_process_event.pyの
`Dispatcher`)にTTL・タイムアウトが無く、「会話が長時間放置された場合の挙動は
今後の課題」と記載されたまま残っていた。フェーズ128(2026-08-23 16:00 UTC)で
同じ既知の限界一覧のもう1点(change経由の専用文言)を解消した際、残る最後の
1点として明記されたため、本ドキュメントで設計・実装する。

## 問題の具体化

`_start_new_booking()`はメニュー未言及時、その時点のLLM出力(`requested_date_range`/
`time_of_day_preference`)を`_pending_new_booking_context_by_user[user_id]`へ
保持し、次ターンの`_merge_pending_new_booking_context()`で今回の出力に無い項目のみ
補う設計になっている。この聞き返し(reask)の時点では`ConversationFlowStateMachine.
present_candidates()`をまだ呼んでいないため、`_states`にエントリが作られない
(`_flow.stage(user_id)`は`None`のまま)。

これは`_candidates_by_user`/`_held_label_by_user`/`_search_context_by_user`
(いずれも`present_candidates()`後、つまり`_states`にエントリが存在する状態で
初めて書き込まれる)と決定的に異なる。もし将来`release_idle_conversations()`の
戻り値(失効したuser_idの一覧)を使ってDispatcher側の各キャッシュを一括で
間引く方式を採用しても、「メニュー未言及の聞き返し中に会話が放置された」
ユーザーは`_states`に一度もエントリを持たないため、その一覧に載らず
救えない。つまりengine.py側の`_states`失効の仕組みに相乗りする方式では
このケースを解決できず、`_pending_new_booking_context_by_user`単体で
時刻を持たせる必要がある。

具体的な実害: 顧客が「メニュー教えてください」への返信をせず長期間(数日〜)
放置した後、全く別の要件で再度話しかけてきた場合(例:2週間後に「来月の
第一週の午前で空いてますか」と改めて聞き直す等)、`stage`は`None`のままのため
`_start_new_booking()`に再度入り、`_merge_pending_new_booking_context()`が
数日前の`requested_date_range`/`time_of_day_preference`を「今回の出力に
無い項目」として誤って引き継いでしまう可能性がある。顧客の最新の発言が
これらの項目に触れていない限り、古い(既に無関係な)日時条件で候補検索が
行われてしまう。

## 決定

`_pending_new_booking_context_by_user`の値を`output`単体から
`(output, set_at: datetime)`のタプルに変更し、`_merge_pending_new_booking_context()`
で読み出す際に`now - set_at`が`CONVERSATION_IDLE_TIMEOUT`(engine.py、30分。
channel-agnostic-session-id.mdのセッション失効・escalation-consolidation-logic.mdの
30分リセットと時間感覚を統一)以上経過していれば、期限切れとして扱い
マージせず(=古い日時条件を引き継がず)、エントリ自体もその場でpopする。

- 専用のバックグラウンド間引き処理(idle-conversation-trigger-design.mdの
  Webhook便乗トリガーのような定期スキャン)は設けない。読み出し時(次に
  同じユーザーが`_start_new_booking()`に入ってきた時)の遅延評価(lazy
  expiry)のみで十分と判断した。理由:
  - このキャッシュの唯一の実害は「古い条件を誤って引き継ぐ」ことであり、
    実際に引き継ぎが発生しうるのは次に`_start_new_booking()`が呼ばれた
    瞬間のみ。その瞬間に判定すれば実害を防げる。
  - 一度も戻ってこないユーザーのエントリがメモリに残り続ける点は、
    idle-conversation-trigger-design.mdの「未解決事項」で許容している
    `_states`自体の長時間残留(MVP規模ではメモリ量が小さく実害なし)と
    同種のトレードオフであり、新たに定期スキャンを追加するコストに
    見合わない。
- タイムアウト値は新設せず`CONVERSATION_IDLE_TIMEOUT`(engine.py)を
  再利用する。「メニュー未言及のまま放置」も広義には他の会話状態の
  無応答離脱と同じ性質(顧客がその場を離れた)であり、別の値を設ける
  理由がないため。

## 実装方針

- `cloud_function_process_event.py`: `engine`から`CONVERSATION_IDLE_TIMEOUT`を
  追加import。`_pending_new_booking_context_by_user`の型注釈を
  `dict[str, tuple[dict, datetime]]`に変更。
  - `_start_new_booking()`の書き込み箇所: `(output, now)`を格納。
  - `_merge_pending_new_booking_context(user_id, output, now)`: `now`引数を
    追加。取得した`(pending, set_at)`について`now - set_at >=
    CONVERSATION_IDLE_TIMEOUT`なら`pop()`して`output`をそのまま返す
    (マージしない)。期限内ならこれまで通りマージする。
- `test_cloud_function_process_event.py`: 期限内(29分後)はこれまで通り
  マージされること、期限切れ(30分後・31分後)はマージされず古い条件が
  破棄されること、期限切れ判定と同時にエントリがpopされる(=`stage`が
  変わらないまま3ターン目でも古い条件が復活しない)ことをそれぞれ確認する
  テストを追加する。

## 影響範囲

- `_carried_over_menu()`・`_search_context_by_user`・`_candidates_by_user`・
  `_held_label_by_user`は`present_candidates()`後の`_states`エントリと
  ライフサイクルが対応しており、既存の`.pop()`呼び出し(確定・キャンセル時)で
  実質的にカバーされているため、本設計の対象外とする(将来
  `release_idle_conversations()`の戻り値を使ったDispatcher側の一括間引きを
  検討する際に合わせて見直す)。
- 実LLM・実LINE API接続とは独立した机上ロジックの変更のみで、オーナー承認は
  不要。

(2026-08-23 19:00 UTC)
