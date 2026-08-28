# トライアル終了通知メッセージ設計

作成日: 2026-08-27(フェーズ129)

checkout-session-completed-handling-design.md(フェーズ128)「未検証・残課題」2点目、
「`usage_counter`側の`upgraded_at`書き込み配線(course-set-pashaのtrial-end-scheduler-design.md
2節相当)は、本venture側にまだ`usage_counter`のトライアル終了通知の実装自体が無いため今回は
対象外」に対応し、本venture未着手だったトライアル終了通知そのものを設計する。
course-set-pashaのtrial-end-notification-design.md(フェーズ99)を参考にしつつ、本ventureの
無料トライアル条件(pricing-plan.md「無料トライアル条件(仮)」)固有の
「期間(14日)と生成回数(10回)のいずれか早い方で終了」という二重条件を踏まえて設計する。

## 1. limit-approaching-notification-design.mdとの違い

本venture既存のlimit-approaching-notification-design.md(フェーズ不明・月間上限接近通知)は
「有料契約継続中のユーザーが月間生成回数の上限(プランごとの35/85/145回目)に近づいた」場合の
通知だが、本ドキュメントが扱うのは「無料トライアル中のユーザーがトライアル終了(=そのままでは
生成不可になる)に近づいた、または到達した」場合の通知であり、対象ユーザーの契約状態
(トライアル中 vs 有料契約中)もカウント基準(月次`count` vs トライアル専用カウンタ)も異なる
別物である。course-set-pashaと同様、両者は将来的に同じ`usage_counter`Protocolの上に実装され
うるが、通知文言・CTA(有料プランへの誘導有無)は明確に区別する。

## 2. トリガー条件(二重条件のいずれか早い方)

pricing-plan.mdの無料トライアル条件により、以下2つのいずれかを検知した時点で通知を1回送信する。

- **(A) 生成回数到達**: `process_memo_event()`等の生成完了処理内で、当該ユーザーのトライアル中
  生成回数が10回に達した時点(10回目の生成完了時、返信メッセージの直後)。
  limit-approaching-notification-design.md 5節と同じく「生成完了時の返信に便乗させる」方式を
  踏襲し、追加のプッシュAPI呼び出し・課金を発生させない。
- **(B) 期間到達**: トライアル開始(初回生成成功時)から14日経過した時点。起点は
  trial-start-anchor-decision.md(フェーズ130)で本venture固有のユーザー動線
  (フォーム提出→LINE連携→初回生成)に照らして正式に確定済み(「初回生成成功時」、
  course-set-pashaフェーズ100と同一の結論)。期間到達は生成イベントに便乗できない
  ため、line-reservation-ai/reminder-scheduler-design.md相当の日次スケジューラ実行
  (Cloud Scheduler)によるプッシュメッセージ送信が必要になる(実際のCloud Scheduler設定は
  オーナー承認待ちの範囲、6節参照)。
- **いずれか早い方で1回のみ送信**し、もう一方の条件はその後判定しない
  (`trial_end_notified_at`のようなフラグを`user_profile`ストアに1つ持たせ、既に送信済みなら
  以降両条件とも判定をスキップする設計とする。checkout-session-completed-handling-design.mdの
  `UserProfileStoreProtocol`への追加フィールドとして次回以降のコード実装時に反映する)。
- (A)(B)いずれの経路で送信された場合も、後続で行うのは3節の同一メッセージ内容とする
  (「回数到達だから」「期間到達だから」で文言を分けない。トライアル終了という結果は同じで
  あり、分岐を増やすとメッセージ・実装の複雑さに見合わないと判断。course-set-pashaと同じ判断)。

## 3. 通知メッセージ内容(草案)

```
[エアコンパシャッと] 14日間の無料トライアル、お疲れさまでした!

これまでの生成実績:
・作業完了報告・お手入れ案内の生成: ○回

引き続きご利用いただく場合は、下のボタンから有料プランをお選びください。
このまま何もしなければ自動課金は発生せず、生成のみ一時停止となります。

▼ 有料プランへ進む(カード登録)
[postbackボタン]
```

(解消済み 2026-08-27・フェーズ131: `[決済導線リンク]`はプレーンテキストリンクではなく
Flex Messageのpostbackアクションボタン〈`data="action=start_checkout"`〉として実現する
ことをcheckout-initiation-flow-design.mdで確定した。詳細は同ドキュメント・下記の追記参照)

- pricing-plan.mdの「トライアル終了時: 自動課金はせず...継続を希望する場合のみ本人がプランを
  選択する形にする」という条件をそのまま踏まえ、「何もしなければ自動課金なし」である旨を
  明記する(tone-and-manner-guideline.mdの絵文字不使用・ですます調方針を踏襲)。
- course-set-pashaの「浮いた作業時間の目安」相当の一文は、本venture向けのcontent-generation-
  time-estimate.md相当の試算ドキュメントが未作成のため今回は含めない(4節の「今後の課題」に
  切り出す)。生成実績(回数)のみを事実として提示するにとどめる。
- (解消済み 2026-08-27・フェーズ131: CTAの遷移方式は、本venture固有の決済導線設計
  checkout-initiation-flow-design.mdで「LINEのpostbackアクションボタン方式・LIFF不要」に
  確定した。user-account-linking-design.md 4節の前提〈Checkout Session作成時点でuser_idは
  `user_profile`上で判明済み〉を活かし、course-set-pashaのようなLIFF IDトークン検証を
  経由せず、postbackイベントの`source.userId`〈署名検証済みのため認証済み〉をそのまま
  使う設計とした。ただし`dispatch_webhook_events()`への`postback`種別振り分け・
  `process_postback_event()`本体の実装は次回以降の課題として残る。checkout-session-
  completed-handling-design.md 4節で扱っているのはあくまでWebhook受信側〈Checkout Session
  作成後の紐付け〉のみで、Checkout Session作成自体の起動方式は本ドキュメントの対応範囲
  だった)

## 4. トライアル終了後(未アップグレード)の挙動

- 通知送信後、実際にトライアル終了条件(A/Bいずれか)に達した以降の生成リクエストは、課金なしで
  従来通り生成を続けるのではなく「生成一時停止」とする(pricing-plan.mdのトライアル条件と
  整合させるため)。course-set-pashaの`_is_generation_paused()`(フェーズ114)と同様、
  `trial_end_notified_at`設定済みかつ`upgraded_at`が未設定の場合はLLM呼び出しを行わず固定文言の
  一時停止案内を返信する設計を採用する。
  (実装済み・フェーズ138: `prototype/cloud_function_webhook.py`の`_is_generation_paused(profile)`
  ・`GENERATION_PAUSED_MESSAGE`・`process_memo_event()`冒頭〈LLM呼び出しより前〉への短絡分岐と
  して実装した。詳細はventures/aircon-pasha/README.mdフェーズ138参照。)
- 一時停止中に本人が決済導線リンクから有料プランへ進んだ場合は、Checkout Session作成〜Stripe
  決済完了(checkout-session-completed-handling-design.mdの`handle_checkout_session_completed()`)
  により`stripe_customer_id`が`user_profile`へ紐付けられ、通常の有料ユーザーへ遷移する想定。
  ただし現状の`handle_checkout_session_completed()`は`stripe_customer_id`の書き込みのみを行い、
  `upgraded_at`(有料転換日時)そのものは書き込んでいないため、この点も次回以降の実装課題として
  残る。

## 5. 実装への影響メモ(設計のみ、実装は次回以降)

- `user_id_linking.py`の`UserProfile`・`UserProfileStoreProtocol`に、`trial_start_at`
  (初回生成成功時に1回だけ設定)・`trial_end_notified_at`(本ドキュメント2節の通知送信時に
  1回だけ設定)・`upgraded_at`(有料転換時に設定)の3フィールド追加が必要になる想定。
  いずれもcourse-set-pashaの`InMemoryUsageCounter`/`user_profile`設計と同じ位置づけ。
- トライアル中生成回数(2節(A)の「10回」判定)は、月次カウンタ(`usage_counter/{user_id}.count`)
  とは別立ての専用カウンタが必要(月をまたいでトライアル期間が続く場合に月次カウンタでは
  正確に集計できないため)。course-set-pashaの`trial_generation_count`と同じ考え方を踏襲する。
- テスト(`prototype/test_user_id_linking.py`・`test_stripe_webhook.py`)では、3フィールド追加後の
  `InMemoryUserProfileStore`の挙動(未設定時のデフォルト`None`、二重送信防止)を検証する方針とする。
  実装自体は本フェーズでは着手しない。

## 6. 今後の課題

- (解消済み・フェーズ130: trial-start-anchor-decision.mdで本venture専用の起点確定を行った。
  詳細は同ドキュメント参照)
- (解消済み・フェーズ131: 決済導線設計をcheckout-initiation-flow-design.mdとして新規作成し、
  3節のCTAの実現方式をpostbackアクションボタン方式〈LIFF不要〉に確定した。詳細は同ドキュメント
  参照。`process_postback_event()`本体の実装・実Stripe接続はなお次回以降の課題)
- 「生成実績」に浮いた作業時間の目安を加えるかどうかは、content-generation-time-estimate.md
  相当のドキュメント作成後に再検討する。
- (解消済み・フェーズ133: (B)期間到達判定用の日次スケジューラの選定ロジック・構成を
  trial-end-scheduler-design.mdとして設計した。詳細は同ドキュメント参照。`prototype/`への
  実装、および4節の「生成一時停止」判定の実コード実装はなお次回以降の課題として残る)
- 実際のCloud Scheduler実行環境の構築(GCPプロジェクトの課金設定を伴う)、決済導線・LIFF等の
  外部サービス接続はいずれもオーナー承認待ちの範囲(pending-approval.md参照)。本ドキュメントは
  メッセージ文言・トリガー条件の机上設計にとどめる。
