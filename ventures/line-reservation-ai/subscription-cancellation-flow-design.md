# オーナー自らの解約(サブスクリプション解約)時のLINE案内文言・処理フロー設計

作成日: 2026-08-31(フェーズ続き162)

## 背景

course-set-pasha・aircon-pashaにはいずれも`subscription-cancellation-flow-design.md`
(オーナー自らの意思による解約フロー設計)が存在するのに対し、本venture
(line-reservation-ai)には同種のドキュメントが存在しなかった。owner-settings-wireframe.md
「4. プラン・お支払い状況ページ」でスタンダードプラン中のボタンを[お支払い方法の確認・変更]
にしてStripeカスタマーポータルへ遷移させる設計は既にあるが、その先でオーナーが実際に
ポータル上で解約操作をした後、Webhook側(`customer.subscription.updated`の
`cancel_at_period_end`変化・`customer.subscription.deleted`)をどう扱うかは一度も設計・
実装されていなかった。`prototype/cloud_function_payment_webhook.py`
(invoice.payment_failed/succeeded担当)・`prototype/cloud_function_subscription_activated_
webhook.py`(初回登録完了担当)はいずれも`suspension_reason`の値
(なし/`"trial_unselected"`/`"payment_failed"`)を前提に役割分担しているが、
「オーナー自身が能動的に解約した」という4つ目の状態はこれまでどこにも定義されていなかった
(stripe-webhook-signature-verification-design.mdで`customer.subscription.deleted`は
「将来cloud_function_payment_webhook.py等が扱うイベント種別」として名前だけ触れられていたが、
実際のハンドラは未着手のままだった)。

**本ドキュメントは設計・机上実装(テスト付き)にとどめる。実際のStripeアカウント接続・
Webhookエンドポイント公開・LINE Push Message API接続はオーナー承認待ち
(pending-approval.md参照)。**

## 0. 前提の整理(本venture固有、course-set-pashaとの違い)

course-set-pasha/subscription-cancellation-flow-design.mdの前提節が明記する通り、
course-set-pashaは「メッセージ送信→3種類のテキスト生成→返信」という単方向バッチ処理で
進行中の会話・予約枠の状態管理を持たないため、解約時の設計は比較的単純だった。

本ventureは逆に、顧客(店舗の来店客)との間で進行中の予約・確定済み予約・前日リマインドを
抱えるサービスであるため、dormant-mode-renotification-design.md(トライアル終了後に
有料プラン未選択のまま休止モードへ移行する既存フロー)と同様、「解約後、既存の予約を
どう扱うか」を明示的に決める必要がある。billing-upgrade-flow-design.md「4. 未選択時の
挙動」の休止モードが「新規予約受付は停止するが、既存の確定済み予約と前日リマインドは
継続する」という方針を採っているのに対し、解約は「オーナー自身が明確な意思表示をした」
という点で休止モードとは性質が異なる。この違いを踏まえ、以下で解約固有の方針を定める。

もう一つの違いとして、course-set-pashaの解約はLINE上での「解約したい」という自然文の
意図検知(llm-system-prompt-draft.mdの厳守事項7a)を起点としていたが、本ventureの
LLM(intent-to-flow-mapping.md)は**来店客との予約対応専用**であり、オーナー自身の
発話を解約意図として解釈する経路は持たない(そもそも同一LINE公式アカウントに双方が
メッセージを送るため、オーナーの発話を安易に「解約意図」として扱うと来店客のメッセージと
混同するリスクがある)。そのためオーナー起点の解約は、owner-settings-wireframe.md
4節で既に確定済みの「カスタマーポータルへの直接遷移」のみを入口とし、LINE上での
自然文による解約意図検知はスコープ外とする(course-set-pashaとの意図的な設計差異)。

## 1. 解約には2つのStripe Webhookイベントが関わる(新規整理)

course-set-pashaの設計は解約確定(`customer.subscription.deleted`)のみを扱っていたが、
Stripeカスタマーポータルのデフォルト挙動を調査すると、解約操作は通常「今すぐ解約」ではなく
「今の請求期間の終了時に解約」(`cancel_at_period_end=true`)として予約され、実際に
契約が終了するのは請求期間終了時点である。この間、サービスは全て通常通り利用できる
(新規予約受付も含む)。この2段階を区別しないと、「解約を予約しただけなのに即座に
新規予約受付が止まる」という利用者体験の悪化を招く。

| イベント | タイミング | 本ventureでの扱い |
|---|---|---|
| `customer.subscription.updated`(`cancel_at_period_end`が`false→true`) | 解約操作の直後 | 解約予約の受理案内を送るのみ。サービスは通常通り継続(`suspension_reason`は変更しない) |
| `customer.subscription.updated`(`cancel_at_period_end`が`true→false`) | 解約予約の取り消し(ポータルの「更新を再開」操作) | 解約取り消しの案内を送る(下記3節) |
| `customer.subscription.deleted` | 請求期間終了・契約実終了 | `suspension_reason`を`"cancelled"`に設定し、休止モードと同じ「新規予約受付停止・既存確定予約とリマインドは継続」の状態へ移行 |

## 2. `suspension_reason`の4つ目の値として`"cancelled"`を新設

dormant-mode-renotification-design.md 4.1節の3分岐(なし/`"trial_unselected"`/
`"payment_failed"`)に、本ドキュメントで4つ目の値`"cancelled"`を追加する。

- `"trial_unselected"`・`"payment_failed"`はいずれも「オーナーの無反応・意図しない
  決済失敗」による受動的な休止であり、dormant-mode-renotification-design.mdの
  7/30/90日再通知(督促)が意味を持つ。一方`"cancelled"`はオーナーが明確な意思表示を
  した結果であるため、**再通知(督促)は行わない**(1回の解約確定案内のみで終える)。
  再通知を送ると「解約したはずなのにまだ営業メッセージが来る」という不満につながりかねない
  ため、dormant_mode_scheduler.pyの再通知スケジュール(`select_due_dormant_events()`)の
  対象には含めない(既存の対象外条件`suspension_reason == "payment_failed"`と同じ要領で
  `"cancelled"`も対象外とする。詳細は5節)。
- 新規登録(`cloud_function_subscription_activated_webhook.py`の`classify_subscription_
  activated()`)が`"cancelled"`状態の店舗から届いた場合、「解約済みだが再度申し込んだ」
  正当なケースであり、`"trial_unselected"`と同じ「再開通知」を送るのが自然だが、
  `classify_subscription_activated()`は現状`"trial_unselected"`以外を全て
  `OUTCOME_ALREADY_ACTIVE`(何もしない)として扱うため、`"cancelled"`から再契約した店舗には
  再開通知が届かないという新たな欠落が生じる。これは本ドキュメントの「残課題」に記録し、
  `cloud_function_subscription_activated_webhook.py`側の改修は次回以降に回す
  (`classify_subscription_activated()`の分岐に`"cancelled"`を追加するだけの小さな変更に
  なる見込みだが、既存モジュールへの変更は影響範囲の確認が必要なため今回は見送る)。

## 3. 解約予約受理時の案内メッセージ(`cancel_at_period_end: false→true`)

message-tone-variants.mdの店舗設定トーンを適用する。standardトーン文言例:

```
【予約とれる君】解約のお手続きを承りました

解約のお手続きを承りました。以下の点をご確認ください。

・現在のご契約: スタンダードプラン
・ご利用は今回の請求期間の終了日(2026-09-14)まで通常通り継続します
  (新規のご予約受付も含め、機能の制限はありません)
・終了日以降は新規のご予約受付を停止し、その時点で確定済みのご予約と
  前日リマインドのみ引き続き対応します
・日割りでの返金は行っておりません

解約を取り消したい場合は、終了日より前であれば下記から「更新を再開」の
お手続きが可能です。

▼ お手続きはこちら
{Stripeカスタマーポータル URL}

またのご利用をお待ちしております。
```

- course-set-pasha版の「現在のご請求サイクルの終了日まで利用継続」という骨子を踏襲しつつ、
  本venture固有の「終了日以降は新規予約受付停止・既存確定予約とリマインドのみ継続」という
  一文を追加した(0節の方針差異を反映)。

## 3.1 解約取り消し時の案内メッセージ(`cancel_at_period_end: true→false`)

```
【予約とれる君】解約のお取り消しを承りました

解約のお取り消しを承りました。引き続きスタンダードプランをご利用いただけます。
次回請求日: 2026-09-14

ご不明点はこのトークルームにご返信ください。
```

- 本メッセージはpayment-failure-dunning-design.mdの決済成功復旧通知・
  dormant-mode-renotification-design.md 4.2節の休止モード復旧通知と異なり、
  `suspension_reason`は元々変更していない(1節の通り、解約予約中もサービスは通常通り
  継続するため)ため、状態のリセットは発生しない。純粋に案内メッセージのみを送る。

## 4. 解約確定(契約終了)時の案内メッセージ(`customer.subscription.deleted`)

```
【予約とれる君】ご契約が終了しました

ご契約が終了しました。ご利用ありがとうございました。

・新規のご予約受付は停止しました(お客様には自動で受付停止中の旨をご案内します)
・現時点で確定済みのご予約と前日リマインドは、実施日まで引き続き通常通り対応します

またのご利用をお待ちしております。再開をご希望の際は、いつでも新規契約と
同じお手続きでお申し込みいただけます。
```

- dormant-mode-renotification-design.md 1節(休止モード移行時)の文面と構成をそろえ、
  「新規予約受付停止・既存確定予約とリマインドは継続」という利用者への影響を明確に
  伝える点は共通させた。一方、休止モードの再通知(7/30/90日)にあたる文面は用意しない
  (2節の方針どおり、解約は督促の対象外)。

## 5. プロトタイプ実装方針

`cloud_function_subscription_activated_webhook.py`と同じ設計方針(実クラウド接続なしで
検証可能な判断・整形ロジックのみを切り出す、`StoreSubscriptionState`と同型の専用
データクラスを新設)で、`prototype/cloud_function_subscription_cancelled_webhook.py`を
新設する。

`classify_subscription_update(cancel_at_period_end_before, cancel_at_period_end_after,
suspension_reason)`:
- `False→True`: `OUTCOME_CANCELLATION_SCHEDULED`
- `True→False`: `OUTCOME_CANCELLATION_RESCHEDULED`(解約取り消し)
- それ以外(変化なし、または`suspension_reason`が既に`"payment_failed"`
  〈dunning側の担当、本モジュールは触れない〉): `OUTCOME_NO_CHANGE`

`classify_subscription_deleted(suspension_reason)`:
- `suspension_reason == "cancelled"`: `OUTCOME_ALREADY_CANCELLED`(Webhook再送時の冪等性)
- `suspension_reason == "payment_failed"`: `OUTCOME_OUT_OF_SCOPE_PAYMENT_FAILED`
  (dunning側の状態を誤って上書きしない。`cloud_function_subscription_activated_
  webhook.py`と同じ考え方)
- それ以外: `OUTCOME_CANCELLED`(新規に解約確定として処理する。`"trial_unselected"`から
  直接解約されるケースも含む。休止モード中に解約する動線は本ドキュメントでは新規に設計
  しないが、Stripe側では技術的にあり得るため、状態の上書きとして許容する)

`handle_subscription_updated(state, cancel_at_period_end_before, cancel_at_period_end_
after, push_client) -> SubscriptionCancellationUpdateResult`・
`handle_subscription_deleted(state, push_client) -> SubscriptionCancellationResult`の
2関数を実装し、送信失敗時は状態を変更しない(既存2モジュールと同じ`OUTCOME_SEND_FAILED`
方針)。

`suspension_reason`書き換えは`handle_subscription_deleted()`が`OUTCOME_CANCELLED`の
ときのみ行う(`handle_subscription_updated()`は1節の方針通り状態を変更しない、
案内メッセージ送信のみ)。

## 未確定事項・残課題

- `classify_subscription_activated()`(`cloud_function_subscription_activated_
  webhook.py`)が`suspension_reason == "cancelled"`から再契約した店舗を
  `OUTCOME_ALREADY_ACTIVE`(何もしない)として扱ってしまい、再開通知が届かない欠落が
  ある(2節参照)。次回以降、同関数の分岐に`"cancelled"`を追加する改修を優先候補とする。
- dormant_mode_scheduler.pyの`select_due_dormant_events()`に`suspension_reason ==
  "cancelled"`を対象外とする条件を追加する実装は本ドキュメントでは未着手(設計のみ、
  2節)。既存の`suspension_reason == "payment_failed"`除外条件と同じ形で追加できる見込み。
- そもそも`suspension_reason`(なし/`trial_unselected`/`payment_failed`、今回追加した
  `cancelled`含む)を実際に「新規予約受付を停止する」という顧客向け自動応答の分岐に
  読み込ませる配線(`cloud_function_process_event.py`・`cloud_function_webhook.py`側)は、
  本ventureのどのsuspension_reason値についても現時点で未実装であることを本フェーズの
  調査で確認した(billing-upgrade-flow-design.md「4. 未選択時の挙動」・dormant-mode-
  renotification-design.mdはいずれも文面・判断ロジックの設計にとどまり、実際の会話フロー
  〈new-booking intent処理〉側への配線はどの休止要因についても着手されていない)。これは
  本ドキュメント固有の欠落ではなく、休止モード全体に共通する既存の未着手事項であるため、
  本フェーズのスコープには含めず、venture全体の残課題として別途棚卸し候補に加える。
- owner-settings-wireframe.md「4. プラン・お支払い状況ページ」のステータス表示
  (トライアル中/スタンダードプラン/休止モードの3状態)に「解約手続き中」
  (`cancel_at_period_end=true`)・「解約済み」(`suspension_reason == "cancelled"`)の
  表示を追加する反映作業は未着手。
- 実際のStripeアカウント接続・Webhookエンドポイント公開・LINE Push Message API接続は
  オーナー承認待ち(pending-approval.md参照)。
