# 新規予約受付停止ガードの棚卸し(他応答経路・継続ターンへの適用範囲確認)

作成日: 2026-09-26(フェーズ続き276)

## 背景

suspension-reason-new-booking-block-design.md(フェーズ続き274)「今回のスコープに含めなかった
もの・次の課題」が残していた、「`owner_faq_router.py`等、他の応答経路への同種の配線が必要か
どうかは未確認」という棚卸し候補、および候補longlist-draft.md側の申し送り「待機中に生産的な
作業として、これまで作成済みの各種md間の記述に矛盾・古い情報が残っていないかの棚卸しを他venture
同様に継続する」を受けて、`_is_new_booking_blocked_by_suspension()`ガードの適用範囲を
`cloud_function_process_event.py`の他の応答経路・継続ターンについて確認した。

## 確認1: owner_faq_router.py への配線は不要(結論: 対象外で正しい)

`owner_faq_router.py`はオーナー自身がLINEトークルームで「FAQ」「Q1」等を送信した際に参照する
コマンド方式の実装であり、`owner-operation-self-service-faq.md`のQ1〜Q7を返すだけの純粋関数
(LLM呼び出し・予約作成を一切含まない)。suspension_reasonが`payment_suspended`(制限モード)の
状態こそ、オーナー自身がQ3(プラン変更・解約)やQ4(トライアル)を確認して対応する必要が最も
高い場面であり、ここをブロックするとオーナーが自己解決する手段を失ってしまう。よって
suspension_reasonによるブロック対象外とする現状の実装(ガード無し)は意図通りであり、
配線漏れではないと結論づけた。コード変更は無く確認のみ。

## 確認2: `_handle_candidate_selection`/`_handle_details`(継続ターン)は理論上のギャップが残る

`_start_new_booking()`のガードは、その呼び出し時点(顧客が最初に日時・メニューを伝えたターン)
でのみsuspension_reasonを評価する。その後の`_handle_candidate_selection()`(候補選択)・
`_handle_details()`(氏名・メニュー確認→確定)は、`stage`が`candidates_presented`/
`awaiting_details`であることだけを見て処理を続行し、これらの継続ターンの時点で
suspension_reasonを再評価していない。

このため、「候補提示後・確定前のごく短い時間差でサブスクリプションが解約/決済停止に至った」
という理論上のケースでは、`_start_new_booking()`時点では未停止だったため候補提示まで進み、
その後のターンで停止済みになっていても、`_handle_details()`側の再チェックが無いため確定
(`action="confirmed"`)まで進んでしまう。

### 今回対応しない判断とその理由

- 発生条件が「候補提示から確定までの1〜数ターンの間に決済失敗・解約が確定する」という
  極めて狭い時間窓に限られ、実運用上の発生頻度は非常に低いと判断した。
- 修正には`change_context`(現在は`_start_new_booking()`呼び出し内でのみ有効なローカル引数で
  ターンをまたいで保持されない)と同様に、「このフローがchange経由で開始されたか」をターンを
  またいで保持する新しい状態を追加する必要がある。理由: change経由フローが`awaiting_details`
  まで進んだ後にsuspension_reasonで再ブロックすると、旧予約を解放済みの顧客が新旧どちらの
  予約も持たない状態に陥る(suspension-reason-new-booking-block-design.md「change_context=True
  の場合はブロックしない(重要な例外)」と同じ懸念)。この状態追加は既存の`_search_context_by_
  user`等と同様の per-user 辞書を増やす設計判断を伴い、今回の棚卸しの範囲を超える実装作業となる
  ため、次回以降の課題として切り出す。
- 確定直後の一貫性(既に確定した予約自体)はowner-settings-wireframe.md 4節が言う
  「既存確定予約とリマインドは継続」の対象であり、たとえこの理論上のケースで確定してしまっても
  致命的な不整合ではない(オーナーへの新規確定通知は別途first-booking-self-check-notification-
  design.md等で従来通り届く)。

### 次回以降の課題として残す内容

- `_handle_candidate_selection()`/`_handle_details()`到達時点でのsuspension_reason再チェックを
  追加するかどうかの設計判断(change経由フローの識別状態をターン間で保持する方法を含む)。
  優先度は低(発生頻度が極めて低い理論上のケースのため)と位置づける。

## 確認3: `_handle_faq`(顧客向けFAQ)・`_handle_escalation`・`_handle_cancel`は対象外で正しい

これらはいずれも新規予約を作成しない応答経路(質問応答・オーナー転送・予約取消)であり、
suspension-reason-new-booking-block-design.mdが対象とする「新規予約受付」には当たらない。
特に`_handle_cancel`(取消)を停止すると、休止モード中の顧客が既存予約を取消したくても
できなくなり、owner-settings-wireframe.md 4節の「既存確定予約とリマインドは継続」方針とも
矛盾するため、ブロック対象外であるべきという結論に変わりはない。コード変更は無く確認のみ。

## 影響・実行結果

本フェーズはmd記述の棚卸し・設計判断の確認のみであり、コード変更は無い。テストの追加・実行も
不要(既存のventure全体866件・schema検証28件のテスト結果に変化はない)。承認が必要なアクション
(支払い・アカウント作成・外部公開・送信等)は今回発生していないためpending-approval.mdへの
追記なし。
