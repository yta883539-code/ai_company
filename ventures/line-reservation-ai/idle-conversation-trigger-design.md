# release_idle_conversations() / archive_completed_conversations() の実行トリガー設計

## 背景
conversation-state-cleanup.md・confirmed-state-archival.mdで設計・実装した
`release_idle_conversations()`(無応答30分での会話状態失効)と
`archive_completed_conversations()`(来店日+1日でのconfirmed状態アーカイブ)は、
どちらも「誰かが呼び出さない限り実行されない」メソッドとして実装されている。
README.mdの「次にやること」に残っていた「実際のホスティング基盤が決まった時点で確定する」
という残課題について、ホスティング基盤の確定を待たずに決められる部分を切り出して検討する。

## 選択肢
| 案 | 概要 | MVPでの採用可否 |
|---|---|---|
| A. 専用スケジューラ(Cloud Scheduler / Vercel Cron / GAS時間主導トリガー等) | 5分おき等の固定間隔でエンドポイントを叩き、内部でクリーンアップ関数を呼ぶ | ホスティング基盤が未確定な現段階では設定できない。基盤決定後に本命として移行。 |
| B. Webhook便乗(opportunistic trigger) | LINE Messaging APIからのWebhook受信(=顧客からのメッセージ到着)のたびに、ついでにクリーンアップ関数を呼ぶ | 追加インフラ不要で今すぐ実装できる。ただし全リクエストで毎回全件スキャンするのは無駄が大きい。 |
| C. 外部無料cronサービスでWebhook URLを定期ping | cron-job.org等が定期的にLINEのWebhook URLへ空リクエストを送る | 外部サービスへの登録(アカウント作成)が必要なため、pending-approval.md行きの案件になる。今回は採用しない。 |

## 結論(MVP向け)
**案B(Webhook便乗)を、呼び出し頻度を間引いた形で採用する。**
理由:
- 「初期投資ほぼ不要・小さく始める」という本ventureの前提と合致し、専用インフラ(A)や
  外部サービス登録(C、要オーナー承認)を待たずに今すぐ実装・検証できる。
- クリーンアップ対象(無応答離脱・来店済みconfirmed)はどちらも「多少実行が遅れても実害が
  小さい」性質(前者はメモリ解放のみ、後者は履歴間引きのみで予約自体の正しさに影響しない)
  ため、Webhookが来たタイミングでの実行で十分に許容できる。
- 将来ホスティング基盤(A)が決まった時点でも、`maybe_run_idle_cleanup()`は
  `release_idle_conversations()`を間引いて呼ぶだけの薄いラッパーなので、そのまま
  スケジューラ側のエンドポイントから呼び出す実装に流用できる(設計の使い捨てが発生しない)。

## 間引き(スロットリング)の設計
Webhookは顧客からのメッセージ到着ごとに発火するため、トラフィックが多い時間帯に毎回
`_states`全件スキャンを行うのは無駄がある。そこで最小実行間隔を設け、前回実行から
一定時間(`IDLE_CLEANUP_MIN_INTERVAL`)経過していない場合はスキップする。

- `IDLE_CLEANUP_MIN_INTERVAL = 5分`: CONVERSATION_IDLE_TIMEOUT(30分)に対して十分小さく、
  失効判定の遅延が実用上気にならない粒度。
- 実行のたびに`_last_idle_cleanup_at`を更新し、次回呼び出し時に経過時間を判定する。
- `archive_completed_conversations()`側は`ARCHIVE_AFTER_VISIT`(1日)に対して間引き幅の
  影響がさらに小さいため、同じ間隔・同じ仕組み(`maybe_run_archive()`)を流用する。
- トラフィックが全く無い時間帯(深夜等)はWebhookが発火しないためクリーンアップも実行
  されないが、次にWebhookが来た時点でまとめて実行されるため、状態が不整合になることはない
  (release/archiveはどちらも冪等であり、遅延実行による副作用はない)。

## 未解決事項
- (解消済み 2026-09-05 フェーズ続き202: 「トラフィックが長時間絶える営業時間外に
  confirmed会話が長時間`_states`に残り続ける点」について、`archive_completed_
  conversations()`に限っては、来店日超過後にその店舗へのWebhookが長期間途絶えると
  (閑散期・廃業間際等)最大遅延が無制限になりうる実害があることが判明した
  (archive-trigger-unification-design.md)。reminder-scheduler-design.mdの
  Cloud Function C(全店舗共通・トラフィック非依存で15分間隔起動)にも同等の判定
  〈`select_confirmed_to_archive()`〉を実装し、こちらを正規のトリガー・本設計の
  Webhook便乗(案B)を補助的な早期実行と位置づけることで、最大遅延をCloud Scheduler
  起動間隔(暫定15分)まで縮めた。`release_idle_conversations()`側(無応答離脱、
  影響がメモリ解放のみ)は実害が小さいため、引き続き本設計(案B単独)のままで良いと
  判断した)
- 前日リマインド送信など「Webhook受信に依存せず能動的に動く必要がある処理」は本設計の
  対象外であり、そちらは案A相当の専用トリガーが必須になる(別途検討、reminder-
  scheduler-design.mdで対応済み)。
