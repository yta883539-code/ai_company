# アカウント登録なし単発決済の実装方式設計(フェーズ10)

tech-stack.md(フェーズ7)「未検証・残課題」1点目、「アカウント登録なしの単発決済(500円/回
プラン)の具体的な実装方式(Stripe Checkoutのone-time payment modeとFirestore上の利用回数
カウントの紐付け方)は未検討」に対応する。

## 1. 前提・方針

- pricing-plan.md(フェーズ4)の単発利用プラン(500円/回、アカウント登録不要)が対象。
- 他venture(aircon-pasha・course-set-pasha・kura-pasha・forklift-pasha)はいずれもLINEの
  `user_id`を主キーとする継続課金(サブスクリプション)モデルのため、`stripe_customer_id`を
  `organizer_account/{account_id}`に保存しアカウント単位で紐付ける設計(course-set-pasha/
  stripe-customer-id-linking-design.md等)を採用している。本ventureの単発利用プランは
  アカウント登録自体が存在しない前提のため、同じ紐付け方式は使えない。
- Stripe Checkoutの「one-time payment mode」(`mode: "payment"`)を用い、決済完了イベント
  (`checkout.session.completed`)と生成実行を1対1で紐付ける「セッション単位のワンタイム
  トークン」方式を採用する。

## 2. 処理フロー(案)

1. 主催者がWebフォーム(tech-stack.mdフェーズ7想定)で5入力要素
   (`capacity`・`entry_exit_points`・`admission_type`・`staffing`・`outdoor_queue`)を
   入力し「生成する(500円)」ボタンを押す。
2. バックエンド(Cloud Run functions)が、入力内容のハッシュ値またはUUID(draft-id-last4-
   collision-design.md〈フェーズ53〉でUUID4に確定済み)を`draft_id`として発行し、
   Firestore `one_time_draft/{draft_id}`に入力内容をステータス`awaiting_payment`
   として一時保存する(TTL想定: 24時間、未決済のまま期限切れとなったレコードは生成不可とし
   そのまま失効させる。自動削除処理の設計はFirestore TTLポリシーの活用を次回検討課題とする)。
   同時に、オーナーの問い合わせ対応用検索フィールド`draft_id_last4`(`draft_id`の末尾4文字
   をそのまま複製した文字列値、admin-search-ui-necessity-design.md〈フェーズ57〉で確定)
   も同タイミングで導出・保存する。
3. バックエンドがStripe Checkout Session(`mode: "payment"`、`amount: 500`、
   `currency: "jpy"`)を作成する。`client_reference_id`に`draft_id`を設定し、入力フォームと
   決済・生成処理を紐付ける(アカウントではなく「下書き」を主キーとする点が継続課金モデルと
   の最大の違い)。
4. 主催者をStripe Checkoutページへ遷移させ決済を完了させる。
5. Stripe Webhook(`checkout.session.completed`)受信時、`client_reference_id`から
   `draft_id`を取得し、`one_time_draft/{draft_id}`のステータスを`paid`に更新する
   (stripe-webhook-signature-verification-design.md相当の署名検証・
   stripe-event-idempotency-design.md相当の冪等性チェックを他venture同様に適用する前提)。
6. ステータスが`paid`になったことを確認後、保存済みの入力内容でLLM生成(4出力)を実行し、
   結果を主催者へ返す。返却方式は(a)Checkout Session完了後のリダイレクト先URLで`draft_id`を
   引き継いだ結果表示ページ、または(b)決済完了メール内のリンク、のいずれかを想定する
   (メールアドレス収集が必要になる(b)は本人確認の観点で有利だが、Stripe Checkoutの
   `customer_email`取得で足りるためアカウント登録とは区別される)。

## 3. 継続課金モデルとの主な相違点

| 項目 | 継続課金モデル(他venture) | 単発決済(本案) |
|---|---|---|
| 主キー | `account_id`(LINE `user_id`またはメール+認証) | `draft_id`(入力内容と1対1の一時トークン) |
| Stripe紐付け先 | `organizer_account/{account_id}`に`stripe_customer_id`を保存 | `one_time_draft/{draft_id}`に`checkout_session_id`を保存(`stripe_customer_id`は保存不要) |
| 利用回数カウント | `usage_counter/{account_id}`で月間累積 | 不要(1決済=1生成で完結、カウント管理自体が不要) |
| 未決済時の扱い | トライアル中は生成可能(無料) | `awaiting_payment`のまま生成不可、TTL失効 |
| 本人識別の持続性 | 次回利用時も同一account_idで継続 | 次回利用時は新規`draft_id`を再発行(再利用なし) |

本案は「生成1回=決済1回=トークン1個」を使い切りにする設計のため、アカウント管理・利用回数
カウンタの両方が不要になり、他venture比でFirestoreスキーマが簡素化される点が利点である。

## 4. 未検証・残課題

- ~~`one_time_draft`のTTL失効(24時間想定)の具体的な実装方式~~: ttl-expiry-result-
  delivery-refund-design.md(フェーズ12)1節で解消済み。Firestore TTLポリシーを採用し
  `expires_at`フィールドを設計、Webhook側の防御的チェックも整理した(フェーズ51でこの
  残課題欄の記載漏れを是正)。
- ~~決済完了後の結果返却方式~~: ttl-expiry-result-delivery-refund-design.md(フェーズ12)
  2節で解消済み。(a)リダイレクトURL方式を主経路、(b)メールリンク方式を併用経路とする
  ハイブリッド方式を採用した(フェーズ51でこの残課題欄の記載漏れを是正)。
- ~~返金・決済失敗時(カード拒否等)の挙動~~: ttl-expiry-result-delivery-refund-design.md
  (フェーズ12)3節で解消済み。決済自体の失敗はStripe標準フロー内で完結、決済完了後の
  生成失敗は2回リトライ後にStripe Refund APIで全額自動返金する方針を確定した(フェーズ51
  でこの残課題欄の記載漏れを是正)。
- 実際のStripeアカウント接続・Webhookエンドポイント登録・GCPプロジェクト作成はアカウント
  作成・支払いが発生するためオーナー承認待ちの範囲(pending-approval.md参照)。今回は実装
  方式の机上設計のみに留める。

最終更新: 2026-10-19 12:00 UTC(フェーズ10: one-time-checkout-no-account-design.md新規作成。
`draft_id`を主キーとするワンタイムトークン方式でStripe Checkout one-time payment modeと
Firestoreを紐付ける設計をまとめた)
追記: 2026-10-25 01:00 UTC(フェーズ51: 本節の残課題棚卸し。TTL失効実装方式・結果返却方式・
返金/決済失敗時の挙動の3点はいずれもttl-expiry-result-delivery-refund-design.md〈フェーズ12〉
で既に解消済みだったにもかかわらず本節への反映が漏れていた記載漏れを是正した)
追記: 2026-10-25 20:00 UTC(フェーズ53: 2節「入力内容のハッシュ値またはUUID」のまま
未確定だった`draft_id`生成方式をUUID4に確定した。理由・末尾4文字の衝突確率試算・
衝突時の照合手順はdraft-id-last4-collision-design.md参照。あわせて`one_time_draft/
{draft_id}`に`customer_email`フィールドを追加保存する方針を確定した〈Webhook受信時の
決済完了メール送信用の値をそのまま書き込む。既存のWebhook処理自体の変更は不要〉)
