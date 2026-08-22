# purge_expired_links() の実行トリガー設計

## 背景
フェーズ78で実装した`prototype/user_id_linking.py`の`purge_expired_links()`は、
`line-user-id-linking-design.md`の残課題(「`pending_links`期限切れドキュメントの定期
パージ」)のうち、掃除ロジック自体(期限切れエントリの判定・削除・削除件数の返却)のみを
実接続なしで検証可能な形に落とし込んだものだった。フェーズ78時点では「スケジューラ発火型
Cloud Functionやfollowイベント便乗でこの関数を明示的に呼ぶ経路も持てる設計」とだけ記し、
どちらの経路を採用するかは未確定のまま残していた。本ドキュメントはその選択を行う。

line-reservation-aiの`idle-conversation-trigger-design.md`(release_idle_conversations()/
archive_completed_conversations()の実行トリガー選定)と同種の検討であり、選択肢の整理は
そちらの型を踏襲する。

## 選択肢
| 案 | 概要 | 採用可否 |
|---|---|---|
| A. 専用スケジューラ(Cloud Scheduler等) | 一定間隔でエンドポイントを叩き、内部でpurge_expired_links()を呼ぶ | 実GCP接続・スケジューラ設定自体がオーナー承認待ちのため今は設定できない。将来の本命。 |
| B. `follow`イベント便乗 | LINE友だち追加のたびに、ついでにpurge_expired_links()を呼ぶ | 友だち追加の頻度は想定顧客規模(小規模ジムオーナー向け)では低く、かつ最初にfollowイベントを受信できるようになるのも実LINE API接続後のため、これ単独では長時間パージが走らない期間が生じうる。 |
| C. `process_memo_event`(既存のメモ処理Webhook)便乗 | ユーザーからのメモ送信(生成依頼)イベントのたびに、ついでにpurge_expired_links()を呼ぶ | 本ventureの主要トラフィック(生成依頼)は`follow`より高頻度に発生する想定で、cloud_function_webhook.pyに既に存在するエントリポイントにオプション引数を足すだけで実装できる。line-reservation-aiのWebhook便乗(案B相当)と同じ考え方。 |

## 結論
**案C(process_memo_event便乗)を、呼び出し頻度を間引いた形で採用する。**

理由:
- 「初期投資ほぼ不要・小さく始める」という本ventureの前提と合致し、専用インフラ(A)を
  待たずに今すぐ実装・検証できる。
- `pending_links`の期限切れは「多少パージが遅れても実害が小さい」性質(`resolve_linking_code()`
  自体も期限切れを検知した時点で遅延削除するため、パージが遅れてもコード再利用や誤紐付けの
  リスクはない。単にFirestore上に空きドキュメントが残るだけ)であり、生成依頼Webhookが来た
  タイミングでの実行で十分に許容できる。
- 友だち追加(案B)は本ventureのユーザー層では生成依頼そのものより低頻度になりうるため、
  唯一のトリガーにすると長時間パージされない期間が生じる。案Cを主、案B(実装時にfollow
  イベントハンドラを作る際、そこでも同じ`maybe_run()`を呼ぶ)を副とする二重便乗も将来的に
  妨げない設計にする。
- 将来スケジューラ(A)が決まった時点でも、`LinkingCodePurgeThrottle.maybe_run()`は
  `purge_expired_links()`を間引いて呼ぶだけの薄いラッパーなので、そのままスケジューラ側の
  エンドポイントから呼び出す実装に流用できる(設計の使い捨てが発生しない、
  idle-conversation-trigger-design.mdと同じ狙い)。

## 間引き(スロットリング)の設計
- `LINKING_CODE_PURGE_MIN_INTERVAL = 1時間`: 連携コードの有効期限(24時間)に対して十分小さく、
  パージ遅延が実用上問題にならない粒度。line-reservation-aiの5分間隔(30分TTL基準)より緩めて
  よいのは、本パージが「掃除」目的のみでresolve側の遅延削除と役割が重複しているため、より低頻度
  でも実害がないから。
- line-reservation-aiの`ConversationFlowStateMachine.maybe_run_idle_cleanup()`と異なり、
  `user_id_linking.py`は状態を持たない関数群として実装されているため、間引き状態
  (`_last_purge_at`)を保持する小さなクラス`LinkingCodePurgeThrottle`を新設する。
  Cloud Functionのウォームインスタンス間でメモリが保持される限り間引きが機能し、コールド
  スタート直後は次回実行が走る(=多少早めにもう一度パージされるだけで、冪等なので問題ない)。
- `process_memo_event()`に`linking_store`・`purge_throttle`・`now`を追加のキーワード専用
  オプション引数として渡す。いずれかがNoneの場合(未接続時・テストで不要な場合)は既存の
  他のオプション引数(usage_counter等)と同様にパージ処理自体をスキップする
  (既存コードへの影響ゼロ、後方互換)。

## 未解決事項
- (解消済み 2026-08-22 17:00 UTC・フェーズ93での確認: `issue_linking_code_on_follow()`の
  呼び出し元となる`follow`イベントハンドラは、フェーズ81〜83で`process_follow_event()`として
  既に実装済みだった。`purge_throttle`引数も用意済みで、渡された場合のみ案B(follow便乗
  パージ)が動く設計になっている。本項目は記載が古いまま残っていた点を訂正する。案Bを
  実際に有効化する(呼び出し側で`purge_throttle`を渡す)かどうかは、実LINE接続後のfollow
  頻度の実測データを見て判断する未解決事項として引き続き残る)
- 実Firestore接続後、`LinkingCodePurgeThrottle`の状態(`_last_purge_at`)をインスタンス変数
  ではなく永続ストア側に持たせるべきか(Cloud Functionsは複数インスタンスが並行起動しうるため、
  インスタンスごとの間引きが揃わない可能性がある)は、実接続後の課題として残る。ただし冪等な
  掃除処理であるため、間引きがインスタンス間でずれても二重実行になるだけで実害はない。
