# 解約・ダウングレード時のLINE案内文言・処理フロー設計

作成日: 2026-08-15

## 背景

pricing-plan.mdでプラン体系(ライト/スタンダード/セッター複数)と無料トライアル条件・
上限超過時の従量課金方式は仮決め済みだが、契約後の「解約」「プラン変更(ダウングレード)」の
案内文言・処理フローはこれまで未着手だった。line-reservation-ai/billing-upgrade-flow-design.md
がトライアル→有料移行(アップグレード方向)のフローを扱っていたのに対し、本ファイルは
その逆方向(縮小・終了方向)を扱う。

## 前提

- 決済方式はStripe Billing優先(payment-processor-metered-billing-usage-research.md参照)。
  Stripeの月額サブスクリプションは日割り計算(プロレーション)を標準機能として提供している
  ため、本設計もプロレーションを前提に組み立てる。
- 本ventureは「メッセージ送信→3種類のテキスト生成→返信」という単方向バッチ処理で、
  line-reservation-aiのような予約枠の状態管理・進行中の会話が存在しない。そのため解約時に
  「進行中の予約をどう扱うか」のような複雑な移行処理は不要で、比較的シンプルな設計が
  成立する。

## 解約フロー

```
[オーナーがLINEで「解約したい」等の解約意図を示すメッセージを送信]
        │
        ▼
[llm-system-prompt-draft.mdの意図判定に「解約」インテントを追加し検知]
        │
        ▼
[解約案内メッセージを送信(下記1.)]
        │
        ▼
[オーナーが決済ページ(Stripeカスタマーポータル)で解約を確定]
        │
        ▼
[Webhook経由でStripeから解約確定通知(customer.subscription.deleted等)を受信]
        │
        ▼
[LINEで解約完了メッセージを送信(下記2.)]
        │
        ▼
[当月の生成回数カウントは維持したまま、次回生成リクエスト時は無料プラン相当(生成不可)として扱う]
```

## 1. 解約意図検知時の案内メッセージ

message-tone-variants.mdの店舗設定トーンを適用する。standardトーン文言例:

```
【コースセットパシャッと】解約についてのご案内

解約をご希望とのことで承知しました。以下の点をご確認のうえ、下記リンクから
お手続きください。

・現在のご契約: スタンダードプラン(月15回まで/月額3,480円)
・解約手続き完了後も、今回のご請求サイクルの終了日(◯月◯日)まではサービスを
  引き続きご利用いただけます。
・日割りでの返金は行っておりません(Stripeカスタマーポータルの表示に従います)。
・解約後、再開をご希望の場合はいつでも新規契約と同じ手順で再度お申し込みいただけます。

▼ 解約手続きはこちら
{Stripeカスタマーポータル URL}

このまま継続をご希望の場合は、このメッセージへの返信は不要です。
```

## 2. 解約確定Webhook受信時の案内メッセージ

```
【コースセットパシャッと】解約手続きが完了しました

ご契約は◯月◯日をもって終了となります。それまでは引き続きご利用いただけます。
またのご利用をお待ちしております。
```

## ダウングレード(プラン変更)フロー

上位プランから下位プラン(例: スタンダード→ライト)への変更は、解約と異なり
サービス継続が前提のため、以下の点を解約フローと分けて設計する。

- タイミング: Stripeのプロレーション機能を用い、変更申込み時点で日割り差額を精算する
  (即時変更)。line-reservation-aiのようなLINE通数按分計算は不要なため、Stripe標準機能
  でそのまま対応できると判断する。
- 当月の生成回数上限: 変更申込み時点で「変更前プランの上限」と「変更後プランの上限」の
  どちらを当月に適用するかが未確定事項として残る。両プランとも上限超過分は従量課金で
  吸収する設計(pricing-plan.md)のため、実務上は「変更後プランの上限を即時適用し、
  変更前にすでに消費した回数分は変更後上限から差し引く」方式が利用者にとって分かりやすいと
  仮決めするが、実装時にStripe側の請求サイクルとの整合を再確認する必要がある。
- 案内メッセージ: 解約案内と同様にStripeカスタマーポータルへ誘導し、プラン変更自体は
  ポータル内のUIに委ねる(LINE側で独自のプラン変更UIは持たない)。

## ダウングレード時の当月生成回数上限の適用方法(確定)

WebSearchでStripe公式ドキュメント(Prorations / Change the price of existing
subscriptions / Update a subscription)を調査した結果、以下の2点を確認した。

- 同一課金間隔(月次→月次)のプラン変更では`billing_cycle_anchor`(請求サイクルの
  基準日)は変更されない。`billing_cycle_anchor`がリセットされるのは課金間隔自体を
  変更する場合(例: 月次→年次)のみ。
- ダウングレード(下位プランへの変更)は、Stripe側では即座に新料金へ切り替えつつ
  差額をクレジットとして次回請求に繰り越す「プロレーション」処理であり、契約期間
  (請求サイクル)そのものを打ち切って再スタートさせる処理ではない。

この2点から、Stripe側の請求サイクル(`billing_cycle_anchor`起点の期間)は
ダウングレード操作によって途切れない、という結論が得られる。本ventureの月間生成
回数カウンタ(limit-approaching-notification-design.md・tech-stack.mdで設計した
Firestoreの`usage_counter`、ユーザー1人=1ドキュメントで`month`・`count`のみを
保持)はStripeの請求サイクルそのものではなく暦月(calendar month)を単位として
設計している。両者は起点が異なりうるが、いずれも「ダウングレード操作それ自体では
期間の途中で強制リセットされない」という性質は共通するため、次の方式を確定する。

- **確定方式**: ダウングレード申込み時点で`usage_counter`の当月`count`はリセット
  せずそのまま維持し、上限判定にのみ新プラン(下位プラン)の上限値を即時適用する。
  これは当初の仮決め(変更後プランの上限を即時適用)と同じ結論だが、「変更前に
  消費した回数分を変更後上限から差し引く」という表現は`count`を維持したまま上限を
  差し替えるだけで自動的に満たされるため、そのままの実装で成立することを確認した
  (`count`が新上限に既に達している、または超えている場合は、pricing-plan.mdの
  従量課金方式でそのまま吸収する)。
- 実装への反映: `usage_counter`の上限値参照先を「契約時点のプランID」ではなく
  「Stripe Webhookで受信した最新のプランID」に紐づける必要がある点を、Firestore
  接続実装時の留意点として明記する(実装自体はオーナー承認待ちの範囲)。

## 未検証の仮説・次の課題

- (解消済み 2026-08-15 08:00 UTC・フェーズ54: 「解約」インテントの検知は
  llm-system-prompt-draft.mdの厳守事項7aとして新設し、誤検知境界(7a(iii)、雑談の域を
  出ない表現は解約意図として扱わない)を整理した。schema/output.schema.jsonの`status`
  enumへcancellation_intent/downgrade_intent/cancellation_unclearを追加し、
  schema/validate_test_cases.pyにCI1〜CI3として期待出力を明文化済み。詳細は
  llm-system-prompt-draft.md 2026-08-15追記部分参照)
- (解消済み 2026-08-18 09:00 UTC: 上記CI1・CI2のbody文言に含まれる
  `{Stripeカスタマーポータル URL}`プレースホルダは、これまでformat_reply_text()側の
  実装が無くstatus=cancellation_intent/downgrade_intent/cancellation_unclearを渡すと
  ValueErrorになる状態だった。`prototype/cloud_function_webhook.py`に
  `PortalLinkProvider`Protocol(llm_call・reply_client・usage_counterと同じ「差し替え
  可能なスタブ」の設計方針)と`render_subscription_procedure_notice()`を新規実装し、
  プレースホルダを実URLへ置換する処理を追加した。providerが未接続、providerがNoneを
  返す、またはuser_id不明の場合は、壊れたプレースホルダ文字列をそのまま顧客に見せることを
  避けるため`PORTAL_LINK_UNAVAILABLE_FALLBACK`(問い合わせ導線への差し替え)を返す設計と
  した(api-call-failure-handling.mdの「呼び出し失敗時は安全側の定型文言」と同じ考え方)。
  cancellation_unclear(includes_portal_link=False)はプレースホルダを含まないため
  bodyをそのまま返す。テスト7件(SubscriptionProcedureNoticeTest)を追加し、
  既存分含め全45件パスを確認。実際のStripe Billing Portal Session API呼び出しへの
  接続(providerの実装差し替え)は引き続きオーナー承認待ちの範囲として残る)
- 上記「ダウングレード時の当月生成回数上限の適用方法」はWebSearchで得た公開ドキュメント
  の要約に基づく判断であり、WebFetchのegressプロキシ制約により一次情報(Stripe API
  リファレンスの`subscription_proration_behavior`パラメータの詳細挙動等)への直接
  アクセスでの最終確認はできていない。実際のStripeアカウント接続後(オーナー承認待ち)に
  テスト環境で実際の請求サイクル・`usage_counter`上限差し替えのタイミングを検証する
  必要がある。
- 実際のStripe接続・Webhook実装・カスタマーポータルの設定はオーナー承認待ちの範囲
  (アカウント開設・契約が必要)として残る。設計・下書き作成の範囲に留める。
