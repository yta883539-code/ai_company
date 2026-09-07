# 複数職人プラン→ライト/スタンダードプラン ダウングレード時の余剰メンバー扱い設計(フェーズ28)

作成日: 2026-09-07(フェーズ28)

## 背景・対応する残課題

craftsman-account-linking-design.md(フェーズ25)「未検証・残課題」2点目、および
subscription-cancellation-flow-design.md(フェーズ23)108行目で既に指摘されていた、
複数職人プランからライト/スタンダードプランへダウングレードした際に
`craftsman_workshop/{workshop_id}.member_user_ids`が2名以上のまま残ってしまう
「余剰メンバーの扱い」を検討する。本venture固有の論点であり、course-set-pasha・
aircon-pashaには複数人契約の概念自体が存在しないため参照できる既存踏襲元がない。

## 1. 前提の整理

- ライト/スタンダードプランは「1人だけのworkshop」という設計
  (craftsman-account-linking-design.md 3節)である。したがって
  `member_user_ids`が2名以上のworkshopをライト/スタンダードのまま存続させることは
  設計上の前提と矛盾する。
- ダウングレード自体はStripeカスタマーポータル側の操作であり、本venture(LINE Bot)
  側はStripeのWebhook(`customer.subscription.updated`、`plan_id`変更を検知)を
  受けて`craftsman_workshop/{workshop_id}.plan_id`を更新する形になる
  (subscription-plan-change-design.md相当は本venture未着手だが、course-set-pasha側の
  設計思想を踏襲する前提)。
- 即座に契約者以外のメンバーのLINEアカウントとの紐付けを強制解除すると、そのメンバーは
  何の予告もなく突然サービスを使えなくなる。一方、他venture(course-set-pasha等)の
  ダウングレード方針(即時変更、日割り精算)との整合も考慮する必要がある。

## 2. 検討した選択肢

1. **即時強制解除**: ダウングレード確定と同時に契約者以外の全メンバーを
   `member_user_ids`から削除する。実装は単純だが、予告なくメンバーがサービスを
   失うため利用者体験として望ましくない。
2. **猶予期間付き解除(採用)**: ダウングレードは即時反映するが、`member_user_ids`の
   縮小(契約者のみへの絞り込み)は次回請求サイクルの開始時点まで猶予する。
3. **契約者による選択制**: 契約者に「誰を残すか」をLINE上で選ばせる。柔軟だが、
   本venture固有の低頻度利用特性(受注件数が少ない)を踏まえると実装・UI設計の
   コストに見合わないと判断し採用しない。

## 3. 確定する設計(選択肢2を採用)

- Webhookで`plan_id`がライト/スタンダードへ変更されたことを検知した時点で、
  `craftsman_workshop/{workshop_id}`に`pending_member_reduction_effective_at`
  (次回請求サイクル開始日時、Stripeの`current_period_end`相当)フィールドを設定する。
  この時点では`member_user_ids`はまだ変更しない(猶予期間中は全員が引き続き利用可能)。
- 契約者宛のダウングレード完了案内メッセージ(subscription-cancellation-flow-design.md
  「2. 解約確定Webhook受信時の案内メッセージ」相当のダウングレード版)に、
  「◯月◯日以降は本プランの上限人数(1名)を超えるメンバーはご利用いただけなく
  なります。継続してご利用いただくメンバーを1名選んでご連絡ください」という
  一文を追加する。
- `pending_member_reduction_effective_at`を過ぎた時点(次回の生成リクエスト受信時に
  日時を比較する簡易実装とし、専用のスケジューラは設けない。本venture固有の低頻度
  利用特性〈受注件数が少ない〉ゆえ、専用バッチより都度チェックの方が実装コストに
  見合うと判断)で、`member_user_ids`が2名以上のままであれば以下のルールで機械的に
  縮小する。
  - 契約者が「残すメンバー」を連絡してきていた場合はその1名(契約者+指定メンバー、
    ただし上限1名なので契約者のみになる。指定メンバー自身を契約者に変更したい場合は
    契約者譲渡機能〈MVP範囲外、craftsman-account-linking-design.md残課題〉が必要な
    ため今回は対象外)。
  - 連絡がなかった場合のデフォルトルールは**契約者(`contractor_user_id`)のみを
    残し、他の`member_user_ids`は全員解除する**(契約者本人が契約の名義人であり
    最も明確な残留基準であるため)。
  - 解除されたメンバーには、次回そのuser_idから生成リクエストが来た時点で
    「所属していたworkshopのプラン変更により、現在はご利用いただけません。
    利用を続けるには契約者様に新規のworkshopへの再招待をご依頼ください」という
    案内を返す設計とする(`WorkshopNotLinkedError`相当の扱いに準じる。
    prototype/usage_counter_workshop.pyの既存例外設計を拡張する形で次のステップで
    実装する)。
- `usage_counter/{workshop_id}`のcountは本変更の影響を受けない
  (usage-counter-workshop-key-design.mdの既定方針〈ダウングレード時もcount維持〉を
  そのまま踏襲)。

## 4. 未検証・残課題

- 猶予期間中(ダウングレード確定〜次回請求サイクル開始まで)に契約者が「残す
  メンバー」を連絡する導線(LINEでの意図検知)の具体的な文言・schema拡張は
  本ファイルでは扱わず次の課題とする。
- 契約者本人がダウングレード後に自分自身を交代したいケース(契約者譲渡)は
  craftsman-account-linking-design.mdの既存残課題のままとし、本ファイルでは
  解決しない。
- `pending_member_reduction_effective_at`の都度チェック実装(prototype拡張)は
  本ファイルでは机上設計にとどまり、実コードは未着手。
- 実際のStripe接続・LINE公式アカウント接続は未着手(オーナー承認待ちの範囲、
  pending-approval.md参照)。

最終更新: 2026-09-07 12:02 UTC
