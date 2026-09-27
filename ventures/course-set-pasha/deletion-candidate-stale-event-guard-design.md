# deletion_candidate.pyへのStripe Webhook配信順序入れ替わりガード追加
(deletion-candidate-stale-event-guard-design.md)

## 1. 背景

subscription-event-out-of-order-guard-design.md(フェーズ261)で`subscription_canceled_at`
(生成の即時ブロック)には配信順序入れ替わり(stale event)ガードを追加したが、同フェーズ
4節「残課題」で`deletion_candidate.py`の`mark_deletion_candidate_on_subscription_deleted()`/
`clear_deletion_candidate_on_subscription_reactivated()`は「理論上は同じstale問題が
存在し得るが、実害は365日という長い猶予期間の起点が数日ずれる程度で軽微」として意図的に
スコープ外にしていた。本フェーズでは、実害が軽微であっても実装コスト自体は小さく
既存パターン(hasattr判定によるオプトイン・後方互換)をそのまま踏襲できることから、
このガードを追加した。

## 2. 具体的にどう壊れるか(subscription-event-out-of-order-guard-design.md 2節と同型)

- ケースA(解約→即再契約でdeletedがcreatedより後に届く): 再契約後のユーザーに対し、
  遅れて届いた古いdeletedイベントが`deletion_candidate_at`を(365日後の日付で)誤って
  再設定してしまう。実際には有効な契約者だが、365日後に削除候補として扱われてしまう。
- ケースB(初回createdのリトライが後続deletedより後に届く): 解約済みユーザーに対し、
  遅れて届いた初回createdのリトライが`deletion_candidate_at`を誤ってクリアしてしまう。
  実際には解約済みだが、削除候補化の起点が失われてしまう。

## 3. 修正方針

`ProfileDeletionCandidateStoreProtocol`に`get_deletion_candidate_state_event_time()`/
`set_deletion_candidate_state_event_time()`を追加し、`deletion_candidate_at`を最後に
実際に反映した(mark/clearいずれかを問わない)イベントの`event_time`をuser_idごとに
記録する。`_is_stale_deletion_candidate_event()`が今回のイベント時刻と記録済み時刻を
比較し、今回のイベント時刻が記録済み時刻以前(`<=`)であればstaleと判定して反映を
スキップする。

`mark_deletion_candidate_on_subscription_deleted()`の`event_time`引数は元々必須だった
ためそのまま活用する。`clear_deletion_candidate_on_subscription_reactivated()`は
これまで`event_time`を受け取っていなかったため、`Optional[datetime] = None`として
追加した(省略時はガード自体をスキップし、従来通り無条件にクリアする。既存呼び出し
経路・テストとの後方互換)。`store`が新メソッドに対応していない場合も同様に
`hasattr`相当(`getattr(..., None)`)判定でガードをスキップする。

## 4. スコープ外

- 本ガードはcourse-set-pasha単体への適用に留める。aircon-pashaにも同名の
  `deletion_candidate.py`が存在するが、各venture独立のコピーであり共有モジューールでは
  ないため、横展開は別フェーズで行う(次回候補)。
- `mark_deletion_candidate_on_subscription_deleted()`/
  `clear_deletion_candidate_on_subscription_reactivated()`の実際の呼び出し元
  (Stripe Webhookエンドポイント本体からのcall site)は、design冒頭に記載の通り実
  Stripeアカウント接続待ちのため、本フェーズでも未接続のまま。

## 5. テスト

`test_deletion_candidate.py`に`StaleEventGuardTest`を追加(4件、いずれもパス)。

- ケースAの再現・ガードの効果確認。
- ケースBの再現・ガードの効果確認。
- 正常順序(deleted→created)では従来通り反映されることの回帰確認。
- `clear_deletion_candidate_on_subscription_reactivated()`の`event_time`省略時は
  ガードをスキップし従来通り無条件にクリアすることの後方互換確認。

venture全体670件(`python3 -m unittest discover -s prototype -p "test_*.py"`、
変更前666件+新規4件)・schema検証21件(`python3 schema/validate_test_cases.py`、
変更なし)いずれもパスを確認した。承認が必要なアクション(支払い・アカウント作成・
外部公開・送信等)は今回発生していないため、pending-approval.mdへの追記なし。
