# flush_escalation_windows() の実行トリガー設計

## 背景
owner-notification-channel-design.md・escalation-notification-templates.mdで実装した
`ConversationEventProcessor.flush_escalation_windows()`(5分ウィンドウで貯まったエスカレーション
のまとめ通知をオーナーへpushする関数)は、「Cloud Scheduler等の定期実行トリガーから呼び出す想定」
として実装されたのみで、実際に定期実行する仕組みは無い状態だった(呼び出し元は
`prototype/test_cloud_function_process_event.py`のテストコードのみ)。実際のCloud Scheduler設定は
GCPプロジェクト作成(アカウント作成)に該当し、pending-approval.md記載のとおりオーナー承認待ちの
ままである。

idle-conversation-trigger-design.mdは同種の課題(`release_idle_conversations()`/
`archive_completed_conversations()`の実行トリガー)に対し、「Webhook便乗(案B)」を採用し、
`ConversationFlowStateMachine.maybe_run_idle_cleanup()`/`maybe_run_archive()`として実装済み。
本ドキュメントでは、同じ案Bが`flush_escalation_windows()`にも適用できるかを検討する。

## idle-cleanup/archiveとの違いの検討
idle-conversation-trigger-design.mdの「未解決事項」は、Webhook便乗方式の適用対象外として
「前日リマインド送信など、Webhook受信に依存せず能動的に動く必要がある処理」を挙げていた。
`flush_escalation_windows()`がこちらに該当するかを整理する。

- 前日リマインドは「その日その時刻」に必ず送る必要があり、**当該処理と無関係などんなWebhook
  トラフィックも発生しない可能性がある**(例: 前日にその顧客も他の顧客も一切メッセージを
  送らない日)。Webhook便乗方式では原理的に発火し得ない。
- `flush_escalation_windows()`は、EscalationConsolidatorの全ユーザー分のウィンドウを横断的に
  スキャンする関数であり、特定の1ユーザーのWebhookに紐づく必要はない。**店舗全体で
  (エスカレーションを起こした本人以外の顧客も含め)何らかのWebhookが到着しさえすれば
  発火機会を得られる**。これは`maybe_run_idle_cleanup()`が「全ユーザー分の`_states`を
  スキャンする」設計と同じ性質であり、「Webhook受信に依存せず能動的に動く必要がある処理」
  には該当しない。
- ただし、idle-cleanup/archiveと異なる点として、エスカレーションのまとめ通知は
  **オーナーへの情報伝達の即時性**に関わる。もっとも、5分ウィンドウ内の**1件目は
  `_notify_owner()`により既に即時通知済み**であり、`flush_escalation_windows()`が担うのは
  「同じ5分間に追加で何件届いたか」の後追い集計に過ぎない。1件目の即時性は影響を受けないため、
  遅延の実害はidle-cleanup(メモリ解放の遅延)と同程度に軽微と判断できる。

## 結論
**Webhook便乗方式(案B)を、`flush_escalation_windows()`にも同様に採用する。**
ただし1件目が即時通知済みとはいえ「まとめ通知」自体の情報鮮度はidle-cleanup/archiveより
重要度が高いため、間引き幅(スロットリング間隔)は`IDLE_CLEANUP_MIN_INTERVAL`(5分)より
短い**1分**とする(`ESCALATION_FLUSH_MIN_INTERVAL`)。ウィンドウ自体が5分固定のため、
1分間隔のポーリングであれば「ウィンドウが閉じてから最大1分」程度の遅延に収まる。

## 実装方針
- `ConversationEventProcessor`(cloud_function_process_event.py)に
  `maybe_run_escalation_flush(now)`を新設する。前回実行から`ESCALATION_FLUSH_MIN_INTERVAL`
  (1分)未満の場合は何もせず`None`を返し、それ以外は`flush_escalation_windows(now)`を呼んで
  結果(送信件数)を返す。
- `maybe_run_idle_cleanup()`/`maybe_run_archive()`と同様、**本メソッド自体を`process()`から
  自動的に呼び出す配線は今回は行わない**。idle-cleanup/archiveも同じ理由で`process()`未配線の
  ままであり(実際のCloud Functionsエントリポイント自体がまだ存在しない段階のため)、
  一貫性を優先し本トリガーもテスト・デモでの検証にとどめる。実デプロイ時に、Cloud Function Bの
  エントリポイントで`process()`の呼び出し直後に`maybe_run_idle_cleanup()`/`maybe_run_archive()`/
  `maybe_run_escalation_flush()`をまとめて呼ぶ1行を追加するだけで配線が完了する設計とした。

## 未解決事項
- トラフィックが極端に少ない店舗(1日数件程度)では、エスカレーション発生後1分以内に
  他のWebhookが届かない限りまとめ通知はさらに遅延する。実害は「1件目の即時通知に対する
  補足情報が遅れるだけ」であり予約自体の正しさには影響しないため、MVPでは許容する。
  実際のトラフィック量が判明した時点で、専用スケジューラ(案A)への切り替え要否を再検討する。
- 案A(Cloud Scheduler)への切り替え時は、`flush_escalation_windows()`を直接スケジューラの
  エンドポイントから呼び出すだけで移行でき、`maybe_run_escalation_flush()`側の設計変更は
  不要(idle-cleanup/archiveと同じ「使い捨てにならない」設計方針を踏襲)。
