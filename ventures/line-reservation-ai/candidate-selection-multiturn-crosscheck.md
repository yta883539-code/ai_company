# 候補提示→確定の複数ターン継続フローに関する横断確認(フェーズ続き277の横展開)

## 経緯

フェーズ続き277で、本ventureの`_handle_candidate_selection()`/`_handle_details()`
(候補提示→ユーザーの候補選択→詳細確認→確定、という複数ターンにまたがる予約フロー)に
`suspension_reason`の再チェックを追加した。予約枠のhold開始時(`_start_new_booking()`)
だけでなく、ユーザーが候補を選んだ時点・詳細を確認する時点でも、その間に決済失敗等で
`suspension_reason`が変化していないかを再チェックする必要があったための対応である。

この種のバグ(「複数ターンにまたがって状態を保持する会話フローにおいて、フロー開始時
にのみ可否判定を行い、途中のターンでの状態変化を見落とす」)が他venture(course-set-pasha・
kura-pasha・aircon-pasha)にも同型で存在しうるかを横断確認した(フェーズ続き277の
「次回候補」(2))。

## 確認結果: 該当する複数ターン継続フロー自体が存在しない

3venture(aircon-pasha・course-set-pasha・kura-pasha)いずれの`prototype/`配下にも、
`_handle_candidate_selection`に相当する関数や、予約枠の`hold`・複数ターンにまたがる
`pending_slot`/`change_context`的な状態を持つ実装は存在しないことを確認した
(`candidate_selection`・`hold`・`pending_slot`・`change_context`等のキーワードで
grepし、該当なし)。

3venture共通の会話設計は、LINEの1メッセージ(作業後メモ)を受信した時点で
`process_memo_event()`が生成可否判定(`_is_generation_paused()`/`_is_payment_suspended()`/
`_is_subscription_canceled()`)→LLM生成→即時返信、を単一ターンで完結させる構造であり、
本ventureのような「候補を提示し、後続のターンでユーザーが選択・確定するまで状態を
保持し続ける」予約特有のフローは持たない。したがって、判定と確定の間に時間差が生じる
余地が構造的に無く、フェーズ続き277と同型の「途中のターンでの状態変化の見落とし」は
発生し得ないと判断した。

なお3venture共通で解約確定時の即時ブロックは`_is_subscription_canceled()`等が
`process_memo_event()`の冒頭(生成の都度)で評価されるため、仮に生成直前に解約が
確定していても次のメモ送信時点で即座に反映される(単一ターン構造ゆえ、複数ターンの
状態保持に起因する見落としのリスク自体が存在しない)。

## 結論

フェーズ続き277の「次回候補」(2)は「該当する構造が存在しないことを確認済み」として
解消する。コード変更は無く、確認・文書化のみ。承認が必要なアクション(支払い・
アカウント作成・外部公開・送信等)は今回発生していないためpending-approval.mdへの
追記なし。

最終更新: 2026-09-27 05:00 UTC(横断確認完了。3venture(aircon-pasha・course-set-pasha・
kura-pasha)いずれにも候補提示→確定の複数ターン継続フロー自体が存在せず、
本ventureのフェーズ続き277と同型の見落としは構造的に発生し得ないことを確認)
