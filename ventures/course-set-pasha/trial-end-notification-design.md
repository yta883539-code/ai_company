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
・浮いた作業時間の目安: 約○分(1回あたり平均○分と仮定)

引き続きご利用いただく場合は、下のボタンから有料プランをお選びください。
このまま何もしなければ自動課金は発生せず、生成のみ一時停止となります。

▼ 有料プランへ進む(カード登録)
[LIFF経由の決済導線リンク]
```

- pricing-plan.mdの「トライアル終了時: 自動課金はせず...継続を希望する場合のみ本人が
  有料プランを選択する形にする」という条件をそのまま踏まえ、「何もしなければ自動課金なし」
  である旨を明記する(course-set-pashaのですます調・絵文字不使用方針を踏襲。line-reservation-ai/
  message-tone-variants.mdのような複数トーン切り替えは本ventureでは未導入のため単一トーンのまま)。
- 「浮いた作業時間の目安」はunit-economics-estimate.md等で試算済みの生成1回あたりの想定作業
  時間(投稿文を手動で書く場合の目安)を参照する想定だが、現時点でその試算値自体が未作成のため、
  本フェーズでは文言テンプレートのプレースホルダ(「○分」)にとどめる。実際の値は
  別途試算が必要(5節「今後の課題」参照)。
- CTAリンクは checkout-initiation-flow-design.md で設計したLIFF経由のCheckout Session作成
  導線(1(b): 「オンボーディング完了メッセージ等に常設する...セルフサービスリンク」と同じ
  仕組み)をそのまま再利用する。本ドキュメントで新たなCheckout Session作成方式を追加設計
  する必要はない。

## 4. トライアル終了後(未アップグレード)の挙動

- 通知送信後、実際にトライアル終了条件(A/Bいずれか)に達した以降の生成リクエストは、
  課金なしで従来通り生成を続けるのではなく「生成一時停止」とする(pricing-plan.mdの
  トライアル条件と整合させるため)。ただし本フェーズでは一時停止の実装(生成リクエスト
  受信時にトライアル終了済み判定を行う分岐)は範囲外とし、通知メッセージ文言の設計のみに
  とどめる。実装は次回以降の課題とする。
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
- 「浮いた作業時間の目安」の試算値そのものが未作成(3節)。line-reservation-ai/
  unit-economics-estimate.mdのような形で、投稿文を手動作成する場合の目安時間を
  market-research.mdの想定顧客像から仮置きする作業が必要。sns-tone-research.mdの時点で
  「個人経営ジムの投稿作成時間の定量データは公開情報から見当たらず、実ヒアリングでしか
  検証できない可能性が高い」と既に結論づけているため、WebSearchでの追加調査より先に、
  一般的な文章作成速度等からの仮置き試算(値が仮置きである旨を明記した上で)を検討する。
- (解消済み 2026-08-23フェーズ100: トライアル開始起点は「初回生成成功時」に確定した。
  詳細はtrial-start-anchor-decision.md参照。)
- (B)期間到達判定用の日次スケジューラ実装、および4節で範囲外とした「生成一時停止」判定の
  実装は次回以降の課題として残す。
- (A)(B)いずれの経路かをuser_profileストアにどう記録するか(`trial_end_notified_at`の
  具体的なフィールド設計・Firestoreドキュメント構造への反映)はfirestore-data-model.md
  相当のドキュメントが本venture未作成のため、tech-stack.md側の整理と合わせて次回行う。
- LIFFアプリの実登録・Cloud Scheduler実行環境の構築(GCPプロジェクトの課金設定を伴う)は
  いずれもオーナー承認待ちの範囲(pending-approval.md参照)。本ドキュメントはメッセージ
  文言・トリガー条件の机上設計にとどめる。
