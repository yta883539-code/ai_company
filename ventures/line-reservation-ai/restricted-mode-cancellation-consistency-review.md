# 制限モード中の解約予約案内メッセージ整合性レビュー(フェーズ続き224)

作成日: 2026-09-14(フェーズ続き224)

## 背景

course-set-pashaのrestricted-mode-cancellation-message-copy-review.md(フェーズ211)は、
「残課題」節で次を今後の確認候補として残していた。

> line-reservation-aiは本フェーズ時点でも解約予約受理時点の顧客向け通知自体が制限モード
> との整合性を考慮した設計になっているか未確認であり、cross-venture parityの観点から
> 今後の確認候補として残す。

本フェーズではこれを確認した。

## 1. 確認結果: 文言レビューではなく実装上の欠落を発見

course-set-pasha/aircon-pashaの制限モードは「生成停止」だが、本ventureの制限モード
(`suspension_reason == "payment_suspended"`、payment-failure-dunning-design.md 3節
「段階3」)は「新規予約受付停止」である。

`subscription-cancellation-flow-design.md`(フェーズ続き162)の
`classify_subscription_update()`は、猶予期間中(`suspension_reason == "payment_failed"`、
同design「段階2」)の店舗のみを対象外(`OUTCOME_NO_CHANGE`)としており、制限モード
(`"payment_suspended"`、「段階3」)は対象外条件に含まれていなかった。

このため、制限モード中(新規予約受付が既に停止済み)の店舗がStripeカスタマーポータルで
解約を予約すると、`render_cancellation_scheduled_message()`が送る通常の解約予約受理
メッセージ「・ご利用は今回の請求期間の終了日まで通常通り継続します(新規のご予約受付も
含め、機能の制限はありません)」がそのまま送信されていた。これは制限モード中の実際の
状態(新規予約受付は既に停止中)と矛盾する誤った案内であり、course-set-pasha/aircon-pasha
の「文言レビュー」とは異なる種類の問題(判定ロジック自体の欠落)だった。

## 2. 対応方針の検討

course-set-pasha/aircon-pashaのレビューは「文言をどう分岐させるか」を検討し現行維持と
結論したが、本ventureでは既に`suspension_reason == "payment_failed"`という同種の状態
(猶予期間中、dunning側が案内文言を担当)を`classify_subscription_update()`が
`OUTCOME_NO_CHANGE`として除外する前例があった。制限モードはこの猶予期間の延長線上の
状態であり、同じ理由(この状態の店舗への案内文言・状態遷移はdunning側/blocked-but-billing
側の設計に委ね、本モジュールは触れない)がそのまま当てはまるため、文言を制限モード対応に
分岐させる新規デザインではなく、既存の除外条件に`"payment_suspended"`を追加する方が
一貫性が高く変更も最小限で済むと判断した。

制限モード中に解約予約操作をした店舗への案内自体が完全に無くなる点は、猶予期間中
(`"payment_failed"`)の既存の扱いと同じ割り切りであり、本フェーズで新たに生じる劣化では
ない。

## 3. 実施内容

`prototype/cloud_function_subscription_cancelled_webhook.py`の
`classify_subscription_update()`のガード条件を`suspension_reason == "payment_failed"`から
`suspension_reason in ("payment_failed", "payment_suspended")`に拡張した。docstringに
理由(誤った「制限はありません」案内を防ぐため)を追記した。

あわせて、同ファイルの`_demo()`内にあった「6) 決済失敗で制限モード中の店舗への誤配信」という
コメントが、実際には猶予期間中(段階2、`"payment_failed"`)を指しているにもかかわらず
「制限モード」(段階3の呼称)と誤って表記していた既存の用語混同を修正し(「決済失敗の猶予
期間中の店舗」に訂正)、新たに`"payment_suspended"`(真の制限モード)のデモケースを追加した。

テスト2件追加(`ClassifySubscriptionUpdateTests.test_payment_suspended_store_is_out_of_scope`・
`HandleSubscriptionUpdatedTests.test_payment_suspended_store_is_untouched`)、venture全体
803件(801件→803件)・schema検証27件いずれもパスを確認した。

## 4. 残課題

- 制限モード中に解約予約操作をした店舗への案内自体が完全に無くなる(猶予期間中と同じ
  割り切り)点について、実際にLINE公式アカウント・Stripeが稼働し当該ケースが発生する
  頻度を見た上で、専用の案内文言を用意すべきかは実測データを見てから再検討する。
- `classify_subscription_deleted()`側は`"payment_failed"`のみを対象外とし
  `"payment_suspended"`は対象外にしていない(制限モード中に契約が実終了した場合は
  通常の解約確定として処理される)。これは制限モードが「契約は継続中だが新規予約受付を
  停止している状態」であり、契約が実際に終了した以上は通常の解約確定通知が適切という
  判断のもとで意図的に据え置いた(本フェーズのスコープ外、変更不要と判断)。
