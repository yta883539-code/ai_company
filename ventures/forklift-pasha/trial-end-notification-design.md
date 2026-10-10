# トライアル終了通知メッセージ設計(フェーズ119)

trial-end-condition-design.md(フェーズ118)「6. 今後の課題」2点目「(A)生成5回到達・(B)期間30日
到達のいずれの経路で検知した場合も、通知メッセージの文言自体(aircon-pasha/trial-end-
notification-design.md相当)は本venture未設計。次回候補とする」に対応し、本venture未着手だった
トライアル終了通知の文言・配信方法を設計する。aircon-pasha/trial-end-notification-design.md
(フェーズ129)を参考にしつつ、本venture固有の事情(入力チャネルがLINEではなく汎用Webフォーム、
tech-stack.mdフェーズ70)を踏まえて設計する。

## 1. 配信方法の確定: LINE pushが使えないことへの対応

既存シリーズ(aircon-pasha・course-set-pasha・kura-pasha・line-reservation-ai)はいずれも
LINE公式アカウントを入力チャネルとするため、期間到達(生成イベントに便乗できない条件)の
通知は日次スケジューラからのLINE pushメッセージで配信できる。本venture(forklift-pasha)は
tech-stack.md(フェーズ70)で入力チャネルを汎用Webフォーム(LINE非依存)に確定しているため、
この配信手段を持たない。トリガー条件(A)(B)それぞれで配信方法を分ける。

- **(A) 生成回数到達**: usage-and-fleet-overage-notification-design.md(フェーズ115)2節・
  3節が既に採用している「生成完了時の返却テキスト(整形済み点検記録簿)への追記」方式を
  そのまま踏襲する。生成イベントに便乗できるため、新たな配信経路を追加しない。
- **(B) 期間到達**: 生成イベントに便乗できないため、payment-identity-verification-design.md
  (フェーズ95)2節で確定済みの、初回登録時に入力されたメールアドレス宛のメール配信を使う。
  line-reservation-ai/reminder-scheduler-design.md・kura-pasha/daily-scheduler-design.md相当の
  日次スケジューラ(Cloud Scheduler)で対象者(`trialStartAt`から30日経過かつ
  `trialEndNotifiedAt`未設定の`fleet_operator`)を抽出し、メール送信する設計とする。
  実際のCloud Scheduler実行環境の構築(GCPプロジェクトの課金設定を伴う)、およびメール送信自体
  (外部への送信)はいずれもオーナーの許可が必要なアクションに該当するため、本フェーズでは
  トリガー判定ロジック・メール文言の机上設計のみを行い、6節の通り新規にpending-approval.mdへ
  記録する。

## 2. トリガー条件(二重条件のいずれか早い方)

trial-end-condition-design.md(フェーズ118)4節の`is_trial_period_over()`が真となった時点で、
以下いずれかの経路に応じて通知する。

- **(A) 生成回数到達**: `record_generation_for_trial()`等の生成完了処理内で、当該事業者の
  `trialGenerationCount`が5(`TRIAL_GENERATION_LIMIT`)に達した時点(5回目の生成完了時、
  返却テキストの直後)。
- **(B) 期間到達**: トライアル開始(`trialStartAt`、初回生成成功時に1回だけ設定)から30日
  経過した時点。日次スケジューラ実行時に判定する。
- **いずれか早い方で1回のみ送信**し、もう一方の条件はその後判定しない。aircon-pasha
  フェーズ129と同じく`trialEndNotifiedAt`(Timestamp、未設定時はNone)を`fleet_operator`に
  新設し、既に設定済みの場合は両条件とも判定をスキップする。
- (A)(B)いずれの経路で送信された場合も、内容面では同一の事実(トライアル終了・利用実績・
  CTA)を伝える。配信先(返却テキストへの追記 vs メール本文)が異なるため文面の体裁のみ
  分ける(3節)。

## 3. 通知メッセージ内容(草案)

### (A) 生成回数到達時: 返却テキストへの追記文(1文、usage-and-fleet-overage-notification-
design.md 3節と同じ「末尾に追記」方式)

```
※無料トライアルの生成回数(5回)に達しました。引き続きご利用いただくには、登録時にお送りした
アクセスURLからプランをお選びください。このまま何もしなければ自動課金は発生せず、生成のみ
一時停止となります。
```

### (B) 期間到達時: メール本文(日次スケジューラから送信)

```
件名: 【フォークリフトパシャっと】無料トライアル終了のお知らせ

いつもフォークリフトパシャっとをご利用いただきありがとうございます。
本日で無料トライアル期間(30日間)が終了しました。

これまでの点検記録整形実績: ○回

引き続きご利用いただく場合は、以下のアクセスURLからプランをお選びください。
このまま何もしなければ自動課金は発生せず、生成のみ一時停止となります。

▼ アクセスURL
https://<ドメイン>/f/{accessToken}
```

- pricing-plan.md「トライアル終了時: 自動課金はせず...継続を希望する場合のみ本人がプランを
  選択する形にする」をそのまま踏まえ、両文面で「何もしなければ自動課金なし」を明記する
  (llm-system-prompt-draft.md 7節のですます調・絵文字不使用方針を踏襲)。
- 「浮いた作業時間の目安」(aircon-pashaのcontent-generation-time-estimate.md相当)は、本
  venture向けの試算ドキュメントが未作成のため今回は含めない(6節「今後の課題」に残す)。
  利用実績(生成回数)のみを事実として提示するにとどめる。
- アクセスURLの遷移先(プラン選択・決済導線)自体は、本venture側にcheckout-initiation-
  flow-design.md相当のStripe決済導線設計がまだ存在しないため未確定。5節に次回候補として
  残す。

## 4. トライアル終了後(未アップグレード)の挙動

既存シリーズ(aircon-pashaの`_is_generation_paused()`等)と同様、通知送信後に実際にトライアル
終了条件(A/Bいずれか)へ達した以降のWebフォーム送信は、課金なしで従来通り記録整形を続けるの
ではなく「生成一時停止」とし、固定文言の一時停止案内を返す設計を想定する。`trialEndNotifiedAt`
設定済みかつ`upgradedAt`(有料転換時に設定、本venture未設計のフィールド)が未設定の場合に
短絡する分岐を設ける方針とするが、実装・`upgradedAt`の書き込み元(Stripe Checkout完了処理、
本venture未設計)はいずれも次回以降の課題とする(6節)。

## 5. 実装への影響メモ(設計のみ、実装は次回以降)

- `trial_management.py`の`FleetOperatorStoreProtocol`・`InMemoryFleetOperatorStore`に、
  `trialEndNotifiedAt`(2節の通知送信時に1回だけ設定)フィールドの追加が必要になる想定。
  `get_trial_end_notified_at`/`set_trial_end_notified_at`の2メソッドを追加し、未設定時の
  既定値は`None`とする(他venture同様の設計)。
- (A)経路の判定・返却テキストへの追記は、`record_generation_for_trial()`の呼び出し元
  (Webフォーム送信処理、mvp-flow-draft.md)側で、生成完了直後に`trialGenerationCount`が
  ちょうど5に達したかどうかを確認する実装が必要(usage-and-fleet-overage-notification-
  design.md 2節の90%閾値判定と同型の「today's increment後にちょうど到達したか」判定)。
- (B)経路の日次スケジューラ本体・メール送信処理の実装は、実行環境(Cloud Scheduler)・
  メール送信手段(送信元ドメイン・SMTP/メールAPIの選定)がいずれも未確定のため、設計のみに
  留め実装は次回以降とする。

## 6. 今後の課題

- 本venture向けの「浮いた作業時間の目安」試算ドキュメント(content-generation-time-estimate.md
  相当)は未作成。作成後、両文面に1行追加する(aircon-pashaフェーズ192と同型の対応)。
- 生成一時停止(4節)の実コード実装、`upgradedAt`書き込み元となるStripe決済導線設計
  (checkout-initiation-flow-design.md相当、本venture未着手)。
- 日次スケジューラ(Cloud Scheduler)実行環境の構築・メール送信手段の確定・実際のメール送信
  は、いずれも外部サービス側のアカウント作成・課金設定・送信行為に該当するためオーナー承認
  待ちの範囲。本フェーズでpending-approval.mdに新規記録した(forklift-pashaの既存記録は
  2026-10-05 21:00 UTC〈建荷協等への顧客ヒアリング連絡〉・2026-10-06 22:00 UTC〈Stripe
  アカウント開設〉の2件のみで、Cloud Scheduler・メール送信に関する承認依頼はまだ記録されて
  いなかった)。

最終更新: 2026-10-10 18:00 UTC(フェーズ119: トライアル終了通知の配信方法〈入力チャネルが
汎用Webフォームのため、生成回数到達は返却テキスト追記・期間到達はメール配信に分ける〉・
トリガー条件・メッセージ文言草案を設計。コード変更なし)
