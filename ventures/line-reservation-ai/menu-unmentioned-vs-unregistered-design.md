# 「メニュー未言及」と「メニュー未登録」の区別設計

## 背景

multi-turn-scenario-harness-design.md「追記(2026-08-22 19:00 UTC)」で発見した通り、
`resolve_menu_duration()`(cloud_function_process_event.py)は`menu_name`が
未言及(LLM構造化出力の`menu`がNone、顧客がまだメニューに触れていない)場合と、
言及されたが店舗に未登録(例:「フェイシャル」を扱っていない理容店)の場合を
同一視し、いずれもオーナーへの転送(`forwarded_to_owner`/`unregistered_menu`)に
倒していた。

conversation-samples-test-cases.md E1(曖昧な日時表現)は「日時は曖昧だがメニューは
まだ聞いていない」という会話を意図した例だが、この実装ではE1のような「日時だけ
先に聞いてきてメニューは後で伝える」自然な会話パターンが毎回オーナーの人手対応に
なってしまい、机上の想定より対応コストが高くなる可能性がある。

## 検討した選択肢

- (a) 現状維持: メニュー不明時は常にオーナー転送。確実だが人手対応が増えうる。
- (b) 「メニュー未言及」の場合のみ聞き返しメッセージ(reask)で先にメニューを
  確認してから候補提示に進む。「メニュー未登録」(言及されたが店舗に無い)は
  従来通りオーナー転送を維持する。
- (c) メニュー未指定のまま全メニュー共通で空き候補を提示し、確定前にメニューを
  確認する。

## 決定: (b) を採用

理由:
- (a)は日時のみ先行する自然な会話のたびにオーナー人手対応を要求してしまい、
  他のフィールド欠落時(氏名・日時範囲)は既に聞き返しで解決している設計方針
  (`REASK_NAME_MENU_MESSAGE`・`REASK_DATE_RANGE_MESSAGE`)と一貫しない。
- (c)は「メニューによって所要時間が異なる」という前提(`menu_durations`による
  空き枠検索)そのものと矛盾する。メニュー確定前に検索した候補が、実際のメニューの
  所要時間では埋まってしまっているケースが生じうるため採用しない。
- (b)は既存の聞き返しパターン(氏名・日時範囲の聞き返し)と対称であり、実装・
  会話フローともに一貫性が高い。「メニュー未登録」(業者側の対応外)は引き続き
  人間の判断(取り扱い可否の案内)が必要なため、区別してオーナー転送を維持する。

## 実装方針

- `_start_new_booking()`(cloud_function_process_event.py)で、`resolve_menu_duration()`を
  呼ぶ前に`output.get("menu")`の有無を判定する。
  - 未言及(falsy): `resolve_menu_duration()`を呼ばず、`REASK_MENU_MESSAGE`
    (「当店: ご希望のメニューを教えていただけますか?」)を送信し、
    `DispatchResult(action="reask", detail="menu_not_mentioned")`を返す。
  - 言及あり: 従来通り`resolve_menu_duration()`で店舗登録メニューかを判定し、
    未登録なら従来通り`forwarded_to_owner`/`unregistered_menu`。
- 聞き返し時点で`ConversationFlowStateMachine`側のstageは変更しない(`present_candidates()`を
  呼ばないため`None`のまま)。そのため次ターンのメッセージも`process()`の
  `stage in (None, "confirmed")`分岐から`_start_new_booking()`に再度入ってくる。
- 日時範囲(`requested_date_range`/`time_of_day_preference`)を次ターンへ引き継ぐため、
  聞き返し送信時のLLM出力を`_pending_new_booking_context_by_user`(ユーザーIDキー)に
  キャッシュし、次回`_start_new_booking()`呼び出し時に今回の出力で欠けている項目のみ
  補う(`_merge_pending_new_booking_context()`、既存の`_carried_over_menu()`と対称の設計)。
  メニューが判明した時点でキャッシュは消費・破棄する。

## 既知の限界・今回のスコープ外

- (解消済み 2026-08-23 16:00 UTC・フェーズ128: change(予約変更)フロー経由で
  `_start_new_booking()`が呼ばれメニュー未言及だった場合の専用文言を`CHANGE_REASK_MENU_MESSAGE`
  として実装した。`CHANGE_NO_CANDIDATES_MESSAGE`と同じくreleased_old_bookingの有無で
  出し分ける設計。詳細はcloud_function_process_event.pyの`_start_new_booking()`・
  test_cloud_function_process_event.pyの該当テスト参照)
- `_pending_new_booking_context_by_user`にTTL・タイムアウトは設けていない
  (`_search_context_by_user`等の既存キャッシュと同様、会話が長時間放置された場合の
  挙動は今後の課題として残す)。
- llm-system-prompt-draft.md・intent-to-flow-mapping.mdへの反映(プロンプト側で
  「メニュー未言及時はmenuをnullのまま返してよい」という前提を明文化する等)は
  実LLM接続後の検証と合わせて次回以降の課題とする。

## 変更箇所

- `prototype/cloud_function_process_event.py`: `REASK_MENU_MESSAGE`定数追加、
  `_start_new_booking()`のメニュー判定分岐、`_merge_pending_new_booking_context()`新設、
  `resolve_menu_duration()`docstring更新。
- `prototype/test_scenario_harness.py`: `E1AmbiguousDatetimeScenarioTest`を新挙動に
  合わせて更新(旧`test_e1_literal_menu_null_actually_forwards_to_owner_not_candidates`を
  `test_e1_literal_menu_null_reasks_for_menu_instead_of_forwarding`に改名・期待値更新)、
  聞き返し後にメニューが判明すると日時範囲を引き継いで候補提示まで進むことを確認する
  `test_e1_menu_follows_reask_carries_over_date_range_to_candidates`を新規追加。
- プロトタイプ全体303件パス、schema検証25件パスをいずれも確認。

(2026-08-22 22:00 UTC)
