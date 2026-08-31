# 解約・プラン変更時の案内文言・処理フロー設計

作成日: 2026-08-16

## 背景

pricing-plan.mdでプラン体系(スモール/スタンダード/繁忙期対応の3プラン)と無料トライアル
条件・上限超過時の従量課金方式は仮決め済みだが、契約後の「解約」「プラン変更(アップ/
ダウングレード)」の案内文言・処理フローはこれまで未着手だった。course-set-pasha/
subscription-cancellation-flow-design.mdが同種の課題を先行整理しているため、その構成
(解約フロー→案内文言→ダウングレード時の当月上限適用)を踏襲しつつ、本venture固有の
季節性(繁忙期対応プランへの需要が梅雨〜夏に偏る)を反映する。

## 前提

- 決済方式はStripe Billing優先(subscription-billing-cost-estimate.md参照)。course-set-
  pasha同様、月額サブスクリプションのプロレーション(日割り計算)を標準機能として利用する
  前提で設計する。
- 本ventureも「メモ送信→3種類のテキスト生成→返信」という単方向バッチ処理であり、
  line-reservation-aiのような予約枠の状態管理・進行中の会話は存在しない。course-set-pasha
  と同じく、解約時に「進行中の予約をどう扱うか」のような複雑な移行処理は不要。
- tech-stack.mdの`usage_counter`(Firestore等、月間生成回数の積算専用)はcourse-set-pasha
  と同じ設計思想(`get_count`/`increment`の2メソッド)を採用済みのため、course-set-pashaの
  ダウングレード時の結論(当月`count`は維持したまま上限値のみ差し替え)がそのまま適用できる
  かを後段で確認する。

## 解約フロー

```
[業者がLINEで「解約したい」等の解約意図を示すメッセージを送信]
        │
        ▼
[llm-system-prompt-draft.mdの厳守事項6(会員管理等への不応答)の枠組みに「解約」インテントを
 追加し検知(course-set-pashaと同じ考え方)]
        │
        ▼
[解約案内メッセージを送信(下記1.)]
        │
        ▼
[業者が決済ページ(Stripeカスタマーポータル)で解約を確定]
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

standardトーン文言例(course-set-pashaの文面構成を踏襲):

```
【エアコンパシャッと】解約についてのご案内

解約をご希望とのことで承知しました。以下の点をご確認のうえ、下記リンクから
お手続きください。

・現在のご契約: スタンダードプラン(月90回まで/月額5,980円)
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
【エアコンパシャッと】解約手続きが完了しました

ご契約は◯月◯日をもって終了となります。それまでは引き続きご利用いただけます。
またのご利用をお待ちしております。
```

## プラン変更フロー(アップ/ダウングレード共通)

pricing-plan.mdの3プラン(スモール/スタンダード/繁忙期対応)は月額料金・含まれる生成回数が
それぞれ異なるため、上位↔下位どちらの方向の変更もStripeのプロレーション機能で即時反映する
方針とする(course-set-pashaと同じ)。

- タイミング: 変更申込み時点で日割り差額を精算する即時変更。line-reservation-aiのような
  LINE通数按分計算は不要。
- 案内メッセージ: 解約案内と同様にStripeカスタマーポータルへ誘導し、プラン変更自体は
  ポータル内のUIに委ねる(LINE側で独自のプラン変更UIは持たない)。

## 当月生成回数上限の適用方法(確定)

course-set-pasha/subscription-cancellation-flow-design.mdがWebSearchで確認したStripe公式
ドキュメントの結論(同一課金間隔でのプラン変更は`billing_cycle_anchor`を変更しない、
ダウングレードは契約期間を打ち切らず差額をクレジットとして繰り越すプロレーション処理)は
決済方式(Stripe Billing)が共通である以上、本ventureにもそのまま適用できる。

- **確定方式**: プラン変更申込み時点で`usage_counter`の当月`count`はリセットせず、上限
  判定にのみ新プランの上限値(スモール40回/スタンダード90回/繁忙期対応150回)を即時
  適用する。`count`が新上限に既に達している、または超えている場合はpricing-plan.mdの
  従量課金方式でそのまま吸収する(course-set-pashaと同じ結論)。
- 実装への反映: `usage_counter`の上限値参照先を「Stripe Webhookで受信した最新のプランID」
  に紐づける必要がある点は、course-set-pashaと共通の留意点として実装時に反映する
  (実装自体はオーナー承認待ちの範囲)。(解消済み 2026-08-23・フェーズ107:
  user-account-linking-design.mdで`user_profile/{user_id}.current_plan_id`フィールドとして
  設計した。`customer.subscription.*`受信のたびに更新する方針を確定済み)。
  (実装済み 2026-08-31・フェーズ161: `current_plan_id`への実際の書き込み処理
  〈`prototype/subscription_plan_sync.py`・`stripe_dispatch.py`の`plan_store`配線〉を
  実装した。ただし`process_memo_event()`側が`current_plan_id`を読んで`plan`引数へ
  反映する配線〈月間生成回数の上限判定・上限接近通知に実際に使う経路〉はまだ未着手のまま
  次回以降の課題として残る)。
  (実装済み 2026-08-31・フェーズ162: `process_memo_event()`内に
  `_resolve_plan_for_limit_check()`を新設し、`current_plan_id`を上限判定・上限接近通知に
  実際に使う配線を完成させた。`profile.current_plan_id`が設定済みならそれを最優先で使い、
  未設定でも`upgraded_at`設定済み(有料転換済みだがWebhook受信順序次第の一時的な同期漏れ)
  なら最小プラン〈スモール〉を安全側デフォルトとして採用、トライアル中(`upgraded_at`未設定)
  や`profile_store`未接続時は従来通り呼び出し元が渡す`plan`引数を使う〈トライアル中は
  月間プラン上限を適用対象外のままTRIAL_GENERATION_LIMIT側に委ねる、という既存方針を維持〉。
  これにより本節の「後段部分」の残課題は解消済み)。

## 本venture固有の論点: 季節性に伴うダウングレードの偏り

pricing-plan.mdで整理した季節性(繁忙期対応プランへの需要が梅雨〜夏に偏り、閑散期は
施工件数が下回る)を踏まえると、course-set-pashaとは異なり「繁忙期対応プラン→スモール/
スタンダードへのダウングレード」が閑散期(秋〜冬)に集中して発生しうる。この論点は
course-set-pasha側には存在しない、本venture固有の検討事項として次の2点を残す。

- 上記の「当月`count`維持・上限のみ差し替え」方式は単発のダウングレードでは問題ないが、
  季節に応じて年に数回プラン変更を繰り返す利用パターンが定着した場合、Stripe側のプロレー
  ション処理(差額クレジットの繰り越し)が複数回累積し、請求額の説明がオーナー(業者)に
  とって分かりにくくなる可能性がある。この点はpricing-plan.mdの「未検証の仮説」欄にある
  完全従量制(基本料なしの都度課金)案とも関連するため、想定顧客ヒアリングで「季節に応じた
  プラン変更のしやすさ」自体へのニーズを確認する必要がある(解消済み 2026-08-24 00:00 UTC・
  フェーズ117: customer-interview-design.mdに質問7aとして追加した)。
- 閑散期向けの「一時休止(生成停止のみ、契約は維持)」という第三の選択肢(解約でもダウン
  グレードでもない)をline-reservation-aiのdormant-mode-renotification-design.mdの休止
  モードの考え方を参考に本venture向けに設計する余地があるが、既存3プランでも最下位
  (スモール/月2,980円)への一時的なダウングレードで実質同等の効果が得られるため、
  優先度は低いと判断し今回は設計を見送る(将来、顧客ヒアリングで休止ニーズが確認できた
  場合に改めて検討する)。

## 未検証の仮説・次の課題

- (解消済み 2026-08-21 05:00 UTC: 「解約」インテントの検知境界は、llm-system-prompt-draft.md
  厳守事項6aとして(i)解約意図明確/(ii)プラン変更意図/(iii)雑談・愚痴/(iv)判断不能の4区分で
  既に整理済み(course-set-pasha/faq-escalation-boundary.md・厳守事項7aの考え方を踏襲)。
  本フェーズでschema/output.schema.jsonのstatus enumへcancellation_intent/downgrade_intent/
  cancellation_unclearを追加し、subscription_procedure_notice(kind/body/includes_portal_link)
  フィールドを新設。prototype/cloud_function_webhook.pyにPortalLinkProvider Protocol・
  render_subscription_procedure_notice()を実装し、Stripeポータルリンクの解決・未接続時の
  安全側フォールバックまで机上完結した(course-set-pashaのフェーズ54と同じ構成、テスト9件
  追加・全58件パス)。残るのは6a(iii)雑談と(iv)判断不能の境界の実LLM検証(次項参照))。
- 上記のダウングレード時の当月上限適用方式は、course-set-pashaがWebSearchで確認した
  公開ドキュメントの要約を決済方式の共通性のみを根拠に流用した判断であり、本venture
  独自の一次情報確認は行っていない。実際のStripeアカウント接続後(オーナー承認待ち)に
  改めて検証する必要がある。
- 実際のStripe接続・Webhook実装・カスタマーポータルの設定はオーナー承認待ちの範囲
  (アカウント開設・契約が必要)として残る。設計・下書き作成の範囲に留める。
