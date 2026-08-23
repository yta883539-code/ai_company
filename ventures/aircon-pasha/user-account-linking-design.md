# 申込フォーム・LINE・Stripeのアカウント紐付け設計(フェーズ107)

作成日: 2026-08-23

## 背景・対応する残課題

以下の2箇所で「本ventureは未設計のまま」と繰り返し指摘されていた論点をまとめて整理する。

- tech-stack.md コンポーネント5: 月間生成回数カウント`usage_counter/{user_id}`はLINEの
  `user_id`をキーとする設計まではあるが、そもそも「どの`user_id`が有料契約者か」を判定する
  仕組み自体が未設計だった。
- subscription-cancellation-flow-design.md「実装への反映」: 「`usage_counter`の上限値参照先を
  『Stripe Webhookで受信した最新のプランID』に紐づける必要がある」と指摘されていたが、
  Stripeの`customer`/`subscription`とLINEの`user_id`をどう結び付けるかは本venture未設計の
  ままだった(course-set-pashaはstripe-customer-id-linking-design.md・line-user-id-linking-
  design.mdで先行整理済み)。

course-set-pashaの連携コード方式(line-user-id-linking-design.md)を参考にしつつ、本venture
固有のオンボーディング順序(onboarding-guide.md: 1.申込フォーム → 2.LINE友だち追加 → …→
6.トライアル終了後にプラン選択・課金)を踏まえて設計する。

**本ドキュメントは設計のみ。実際のGoogleフォーム作成・LINE公式アカウント接続・Stripeアカウント
接続はいずれもオーナー承認が必要なアクションのため実施しない(pending-approval.md参照)。**

## 1. course-set-pashaとの違い: 紐付けの向きが逆になる

course-set-pashaは「LINE友だち追加(コード発行)→ 申込フォームでコード入力」の順序だったが、
本ventureのonboarding-guide.mdは「1.申込フォーム(屋号・事業形態・メールアドレス入力)→
2.LINE友だち追加」の順序が既に確定している(フェーズ106以前、course-set-pashaとの相違点として
onboarding-guide.md 4節に明記済み)。したがって連携コードの発行・解決の向きを反転させる必要が
ある。

## 2. 設計方針: フォーム起点の連携コード方式

- 申込フォーム(onboarding-guide.mdステップ1)の送信完了時に、Cloud Function側(GAS Webhook
  経由、course-set-pashaのapplication-form-submission-flow-design.mdと同じ構成を想定)が
  ランダムな連携コード(6文字、course-set-pashaのline-user-id-linking-design.md「3. コード
  仕様」と同じ文字種・視認性除外ルールを採用)を発行し、`pending_links/{code}`に
  `{form_submission_id, business_name, business_type, email, issued_at}`を保存する。
- フォーム送信完了画面(サンクスページ)に連携コードを表示し、「LINE公式アカウントを友だち
  追加後、最初のトークでこのコードを送信してください」という案内を添える。あわせて確認用に
  入力済みメールアドレス宛にも同内容を送る想定(実際のメール送信は送信用サービスのアカウント
  作成が必要なためオーナー承認待ち、data-retention-policy.md相当の課題と同じ扱い)。
- 業者がLINE公式アカウントを友だち追加(`follow`イベント)した時点では、まだ`user_id`と
  フォーム入力内容の紐付けは行わない(course-set-pashaの「follow時にコード発行」とは逆で、
  本ventureは「follow後の最初の受信メッセージがコードかどうかを判定する」フローになる)。
- `follow`イベント直後のウェルカムメッセージは、「連携コードをお持ちの方は、そのままコードを
  送信してください」という案内文のみを返す(course-set-pashaのようにコードそのものを埋め込む
  必要はない)。

## 3. 初回メッセージの分岐: コード判定 vs 施工メモ

本ventureは`follow`後、1:1トークで送られてくるテキストが「連携コード」なのか「通常の
施工メモ(mvp-flow-draft.mdの入力形式)」なのかを判定する必要がある(course-set-pashaには
無い、本venture固有の分岐)。

- 判定方法: 受信テキストが「英大文字・数字混在、6文字、かつ`pending_links`に存在する
  コードと完全一致」する場合のみ連携コードとして扱う。それ以外は通常の施工メモとして
  mvp-flow-draft.mdの生成フローへ渡す(誤って施工メモをコードと誤認しないよう、辞書引き
  一致を必須とし、正規表現の形式一致のみでは連携コードと判定しない)。
- 連携コードと判定された場合: `pending_links`から該当エントリを解決し(course-set-pashaの
  `resolve_linking_code()`と同じ有効期限24時間・使い切り一回限りの方針を踏襲)、
  `user_profile/{user_id}`を新規作成して`business_name`・`business_type`・`email`を書き込む。
  解決成功時はLINEへ「連携が完了しました。テスト送信をお試しください」という案内を返す
  (onboarding-guide.mdステップ3・接続テストへの導線)。
- 解決失敗時(期限切れ・存在しないコード)の案内文言は、course-set-pashaのエラー案内
  (「もう一度フォームを開くと新しいコードが表示されます」等)を本venture向けに読み替えた
  ものを想定するが、確定文言はtone-and-manner-guideline.md整合確認とあわせて次回以降の
  課題とする。
- 連携未完了のまま(`user_profile`に該当`user_id`が存在しない状態で)施工メモを送信された
  場合は、mvp-flow-draft.mdの生成フローへは進めず、「先に連携コードの送信が必要です」という
  案内を返す(トライアル・有料プランいずれの利用回数カウントも、未連携の`user_id`には
  行わない設計とする)。

## 4. Stripe側の紐付け: フォーム・LINE連携より後に発生するため簡素化できる

onboarding-guide.mdのステップ6(トライアル終了後のプラン選択)は、上記2・3の連携が完了した
「後」に発生する。つまりStripe Checkout Sessionを作成する時点では、対象の`user_id`は
既に`user_profile`上で判明済みである。この点はcourse-set-pasha(フォーム入力とStripe決済が
別動線で、決済時点ではuser_id不明という前提)と異なり、本ventureはStripe連携を単純化できる。

- Checkout Session作成時に`client_reference_id`パラメータへ既知の`user_id`をそのまま設定する
  (course-set-pashaのように「決済後に別途user_idへ逆引きする連携コード」を新設する必要は
  ない)。
- `checkout.session.completed`Webhook受信時、`client_reference_id`から`user_id`を直接取得し、
  `session.customer`(Stripe顧客ID)を`user_profile/{user_id}.stripe_customer_id`に書き込む
  (course-set-pashaの`handle_checkout_session_completed()`と同じ処理だが、`resolve_user_id()`
  相当の逆引きロジックは不要で`client_reference_id`をそのまま使える分シンプルになる)。
- 以降の`customer.subscription.updated`・`customer.subscription.deleted`・
  `invoice.payment_failed`等、`customer`IDのみを含みLINEの`user_id`を直接含まないWebhook
  イベントについては、course-set-pashaと同じく`stripe_customer_id → user_id`の逆引きが
  必要になる(`user_profile`を`stripe_customer_id`でクエリする、course-set-pashaの
  `make_resolve_user_id()`と同じ設計をそのまま流用できる)。
- `user_profile/{user_id}`に`current_plan_id`(スモール/スタンダード/繁忙期対応のいずれか、
  未契約時はnull)フィールドを追加し、`customer.subscription.*`受信のたびに更新する。
  subscription-cancellation-flow-design.mdで確定済みの「Stripe Webhookで受信した最新の
  プランIDに紐づける」という指摘は、この`current_plan_id`フィールドで解消される。

## 5. `user_profile`コレクションの確定(tech-stack.mdへの反映が必要)

本フェーズの検討により、tech-stack.mdコンポーネント5が前提としていた「`usage_counter`のみが
唯一の永続データ」という整理は不正確だったと判明した。実際には以下2コレクションが必要になる。

| コレクション | キー | フィールド | 用途 |
|---|---|---|---|
| `pending_links/{code}` | 連携コード | `form_submission_id`・`business_name`・`business_type`・`email`・`issued_at` | フォーム送信〜LINE連携完了までの一時トークン(24時間で失効) |
| `user_profile/{user_id}` | LINE user_id | `business_name`・`business_type`・`email`・`stripe_customer_id`・`current_plan_id`・`linked_at` | 連携済み業者のプロフィール・課金状態 |
| `usage_counter/{user_id}` | LINE user_id | `month`・`count`(既存) | 月間生成回数の積算(tech-stack.md既存設計のまま変更なし) |

tech-stack.mdコンポーネント5の記述(「本ventureにはusage_counterのみ」)は本ドキュメントの
内容を踏まえて次回以降に更新が必要な残課題として残す。

## 未検証・残課題

- フォーム送信完了画面(サンクスページ)へのコード表示、メール送信は、Googleフォーム自体が
  未作成(pending-approval.md 2026-08-18記載の申込フォーム作成案件はcourse-set-pasha分のみで、
  本venture分はまだpending-approval.mdに記録されていない)。本ventureも同様にフォーム作成・
  GAS Webhookデプロイがオーナー承認待ちの範囲であることを明確化しておく必要があり、次回
  pending-approval.mdへの追記を検討する。
- コード判定(3節)の「6文字・辞書引き一致」ロジックが、実際の施工メモの書き出し文言
  (例:「壁掛け2.2kW」等)と偶然一致する可能性はごく低いと見込むが、机上での境界値
  確認(prototype化)は未実施。
- `user_profile`新設に伴い、data-retention-policy.md相当のドキュメント(本ventureは
  legal-notices-draft.md 2.4節で「データ保存方式の確定と合わせて検討する」と保留していた)
  に着手できる前提が整った。次回以降、本ドキュメントの`user_profile`・`pending_links`・
  `usage_counter`の3コレクションを前提としたdata-retention-policy.mdの新規作成を優先候補とする
  (course-set-pasha/data-retention-policy.mdの構成を踏襲予定)。
- (解消済み 2026-08-23 15:00 UTC・フェーズ113: プロトタイプ実装
  (course-set-pashaの`prototype/user_id_linking.py`相当)・テストを実装した。詳細は
  README.mdフェーズ113・prototype/user_id_linking.py・cloud_function_webhook.pyの
  `process_message_event()`参照。連携失敗時の確定文言は本節記載の通り引き続き未確定のまま
  次回以降の課題として残る)
  実装自体は実LINE・実Stripe接続を必要としない机上検証が可能なため、次回以降の候補とする。
