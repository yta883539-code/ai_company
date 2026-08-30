# トライアル終了通知メッセージ設計

作成日: 2026-08-23(フェーズ99)

checkout-initiation-flow-design.md(フェーズ98)「残課題」2点目、「トライアル終了通知
メッセージ自体(1(a): トライアル終了が近づいた際の『有料プランへ進む』リンクを含む通知)は
本venture未設計」に対応する。aircon-pasha/limit-approaching-notification-design.mdの構成を
参考にしつつ、本ventureのトライアル条件(pricing-plan.md「無料トライアル条件(仮)」)
固有の「期間(14日)と生成回数(5回)のいずれか早い方で終了」という二重条件を踏まえて設計する。

## 1. limit-approaching-notification-design.md(月間上限接近通知)との違い

aircon-pasha/course-set-pasha既存のlimit-approaching-notification-design.mdは「有料契約
継続中のユーザーが月間生成回数の上限に近づいた」場合の通知だが、本ドキュメントが扱うのは
「無料トライアル中のユーザーがトライアル終了(=そのままでは生成不可になる)に近づいた、
または到達した」場合の通知であり、対象ユーザーの契約状態(トライアル中 vs 有料契約中)が
異なる別物である。両者は将来的に同じ`usage_counter`Protocolの上に実装されうるが、通知文言・
CTA(有料プランへの誘導有無)は明確に区別する。

## 2. トリガー条件(二重条件のいずれか早い方)

pricing-plan.mdの無料トライアル条件により、以下2つのいずれかを検知した時点で通知を1回送信する。

- **(A) 生成回数到達**: `process_visit_memo_event()`等の生成完了処理内で、当該ユーザーの
  トライアル中生成回数が5回に達した時点(5回目の生成完了時、返信メッセージの直後)。
  aircon-pasha/course-set-pashaのlimit-approaching-notification-design.mdと同じく
  「生成完了時の返信に便乗させる」方式を踏襲し、追加のプッシュAPI呼び出し・課金を発生させない。
- **(B) 期間到達**: トライアル開始(初回生成成功時、`trial_start_at`。起点の確定経緯は
  trial-start-anchor-decision.md フェーズ100参照)から14日経過した時点。生成イベントに便乗できないため、
  line-reservation-ai/reminder-scheduler-design.mdやaircon-pasha/dormant-mode-scheduler相当の
  日次スケジューラ実行(Cloud Scheduler)によるプッシュメッセージ送信が必要になる
  (実際のCloud Scheduler設定はオーナー承認待ちの範囲、6節参照)。
- **いずれか早い方で1回のみ送信**し、もう一方の条件はその後判定しない
  (`trial_end_notified_at`のようなフラグをuser_profileストアに1つ持たせ、既に送信済みなら
  以降両条件とも判定をスキップする設計とする)。
- (A)(B)いずれの経路で送信された場合も、後続で行うのは3節の同一メッセージ内容とする
  (「回数到達だから」「期間到達だから」で文言を分けない。トライアル終了という結果は同じで
  あり、分岐を増やすとメッセージ・実装の複雑さに見合わないと判断)。

## 3. 通知メッセージ内容(草案)

```
[コースセットパシャッと] 14日間の無料トライアル、お疲れさまでした!

これまでの生成実績:
・投稿文生成: ○回
・浮いた作業時間の目安: 約○分(1回あたり平均15分と仮定)

引き続きご利用いただく場合は、下のボタンから有料プランをお選びください。
このまま何もしなければ自動課金は発生せず、生成のみ一時停止となります。

▼ 有料プランへ進む(カード登録)
[LIFF経由の決済導線リンク]
```

- pricing-plan.mdの「トライアル終了時: 自動課金はせず...継続を希望する場合のみ本人が
  有料プランを選択する形にする」という条件をそのまま踏まえ、「何もしなければ自動課金なし」
  である旨を明記する(course-set-pashaのですます調・絵文字不使用方針を踏襲。line-reservation-ai/
  message-tone-variants.mdのような複数トーン切り替えは本ventureでは未導入のため単一トーンのまま)。
- 「浮いた作業時間の目安」は content-generation-time-estimate.md (フェーズ106) で試算した
  「1回あたり平均15分(仮置き、幅12〜18分)」を採用する。`generation_count × 15分`で算出し、
  仮置き値であることを利用者にも透明にするため「1回あたり平均15分と仮定」という前提を
  文言内に明記する。この15分という値自体はあくまで一般的な文章作成時間からの仮置きであり、
  実ヒアリングによる検証は未実施(content-generation-time-estimate.md「残課題」参照)。
- CTAリンクは checkout-initiation-flow-design.md で設計したLIFF経由のCheckout Session作成
  導線(1(b): 「オンボーディング完了メッセージ等に常設する...セルフサービスリンク」と同じ
  仕組み)をそのまま再利用する。本ドキュメントで新たなCheckout Session作成方式を追加設計
  する必要はない。

## 4. トライアル終了後(未アップグレード)の挙動

- 通知送信後、実際にトライアル終了条件(A/Bいずれか)に達した以降の生成リクエストは、
  課金なしで従来通り生成を続けるのではなく「生成一時停止」とする(pricing-plan.mdの
  トライアル条件と整合させるため)。
  (解消済み 2026-08-25フェーズ114: `process_memo_event()`冒頭に`_is_generation_paused()`を
  追加し実装した。`get_trial_end_notified_at()`設定済みかつ`get_upgraded_at()`がNoneの
  場合、LLM呼び出しを行わず`GENERATION_PAUSED_MESSAGE`を返信する。詳細はREADME.md
  フェーズ114・prototype/cloud_function_webhook.py参照。実際の有料プラン登録LIFF URLへの
  差し替えは引き続きオーナー承認待ちの範囲として残る)
- 一時停止中に本人がLIFFリンクから有料プランへ進んだ場合は、checkout-initiation-flow-design.md
  のCheckout Session作成〜Stripe決済完了(course-set-pashaのStripe Webhook設計、
  stripe-webhook-event-dispatch-design.md等)により通常の有料ユーザーへ遷移する想定。

## 5. 今後の課題

- (解消済み 2026-08-24フェーズ105: 「投稿文生成: ○回」は、`usage_counter`に月次カウンタ
  (`get_count()`/`increment()`)とは別立ての専用カウンタ`trial_generation_count`
  (`increment_trial_generation_count()`/`get_trial_generation_count()`)を新設して解消した。
  `trial_start_at`からの期間が月をまたいでも正確に集計できる。有料転換済み
  (`get_upgraded_at()`が非None)のユーザーは積み増し対象外とする。詳細は
  README.mdフェーズ105・prototype/cloud_function_webhook.py参照。)
- (解消済み 2026-08-24フェーズ106: 「浮いた作業時間の目安」の試算値は
  content-generation-time-estimate.mdで「1回あたり平均15分(仮置き、幅12〜18分)」として
  作成し、prototype/trial_end_scheduler.pyの`format_trial_end_notification_message()`に
  配線した。実ヒアリングによる検証は未実施のまま残る。詳細はcontent-generation-time-
  estimate.md「残課題」参照。)
- (解消済み 2026-08-23フェーズ100: トライアル開始起点は「初回生成成功時」に確定した。
  詳細はtrial-start-anchor-decision.md参照。)
- (解消済み 2026-08-30 12:00 UTC・フェーズ続き: 「(B)期間到達判定用の日次スケジューラ実装、
  および4節で範囲外とした『生成一時停止』判定の実装は次回以降の課題として残す」という記載が
  更新されないまま取り残されていた記載漏れを解消した。実際には(B)は
  `prototype/trial_end_scheduler.py`の`select_due_trial_end_notifications()`として、
  「生成一時停止」判定は4節に記載の通りフェーズ114で`_is_generation_paused()`として、
  いずれも既に実装済みだった。)
- (A)(B)いずれの経路かをuser_profileストアにどう記録するか(`trial_end_notified_at`の
  具体的なフィールド設計)は、trial-end-scheduler-design.mdおよび
  `prototype/trial_end_scheduler.py`の`TrialUserState`/`build_trial_user_states()`で
  対応済み。Firestoreドキュメント構造への実際の反映(実接続)はオーナー承認待ちの範囲として残る。
- LIFFアプリの実登録・Cloud Scheduler実行環境の構築(GCPプロジェクトの課金設定を伴う)は
  いずれもオーナー承認待ちの範囲(pending-approval.md参照)。本ドキュメントはメッセージ
  文言・トリガー条件の机上設計にとどめる。
