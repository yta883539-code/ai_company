# `customer.subscription.updated`の`past_due`マッピング再検討(フェーズ99)

README.mdフェーズ98次回候補(1)「design.md次回候補2: 暫定ステータスマッピング(`past_due`
即`canceled`扱い)の妥当性の再検討」に対応する。

## 1. 旧設計の前提と、その前提の誤り

stripe-webhook-entry-point-design.md 3-5節(フェーズ95)は、`past_due`・`unpaid`・
`canceled`・`incomplete_expired`の4状態をまとめて即座に`canceled`扱いとする理由として
「都度利用中心でLTVが低いB2C想定のため、督促より即時停止を優先する」を挙げていた。

しかし、`customer.subscription.updated`イベントが発生するのは本venture唯一の継続課金
対象である**月額フリーパス**(pricing-plan.md)契約者に限られる。都度プラン(1回480円、
Stripe Checkout `mode=payment`)は単発決済のためサブスクリプションそのものが存在せず、
本イベントの対象にならない。

pricing-plan.mdは月額フリーパスの対象者を「月2回以上現場参加する頻度の高いファン、
複数公演『ハシゴ』を繰り返すファン」と定義しており、これは都度プラン利用者より
利用頻度・継続利用意向が高い層である。つまり旧設計が根拠とした「都度利用中心で
LTVが低いB2C想定」という前提は、`customer.subscription.updated`が実際に影響する
対象(月額フリーパス契約者)には当てはまらない。旧設計は「本venture全体の平均的な
利用者像」と「このイベントが実際に影響する利用者像」を混同していた。

## 2. aircon-pasha等との比較

aircon-pasha・course-set-pasha・line-reservation-ai(いずれもB2B・LINE公式アカウント
経由の月額サブスク)は、決済失敗(`invoice.payment_failed`)検知後も7日間の猶予期間を
設け、即座にはサービスを止めない設計(payment-failure-dunning-design.md)を採用している。
理由は「決済失敗は意図的な解約ではなく大半はカード更新のし忘れ等の事務的な理由」という
判断であり、これは業態(B2B/B2C)を問わず一般的に成立する判断である。

本venture旧設計はこの判断枠組みを採用せず「安全側に倒す」という理由だけで即時停止を
選んでいたが、1節の検証により、即時停止を正当化する業態固有の根拠(低LTV)は
`customer.subscription.updated`の対象者には当てはまらないことが判明した。したがって
猶予期間の考え方自体は本ventureにも適用すべきと判断する。

## 3. 採用する修正方針(軽量化)

aircon-pashaと同じ`_is_payment_suspended`相当の専用タイムスタンプフィールド・
日次スケジューラ・3段階の通知文言(猶予期間開始・終了直前リマインド・制限モード移行)を
そのまま持ち込むことは、以下の理由から本venture規模では見送る(オーバーエンジニアリング、
フェーズ95時点の判断を維持)。

- 本ventureはWeb単体・会員登録なし(payment-method-design.md)で、aircon-pasha等のような
  LINE Push通知の送信経路を持たない。猶予期間中の「3日前リマインド」のような能動的な
  通知は、本venture現状の構成では実装コストに対して得られる効果が薄い。
- Stripe BillingのスマートリトライはStripe側で既に最大2週間・最大8回(標準設定、
  line-reservation-aiのpayment-failure-dunning-design.md 5節で確認済みの一次情報)の
  再試行を自動的に行っており、`past_due`状態である間は「Stripe側の督促がまだ続いている」
  ことを意味する。この期間中`fan_pass.subscriptionStatus`を`active`のまま維持するだけで、
  自前のタイムスタンプ管理・スケジューラなしに実質的な猶予期間を得られる。

よって、修正は`_map_stripe_status_to_fan_pass_status()`(prototype/stripe_webhook.py)の
マッピングテーブルを次のように変更するのみとした。

| Stripeステータス | 旧マッピング | 新マッピング |
|---|---|---|
| `active` | `active` | `active`(変更なし) |
| `trialing` | `active` | `active`(変更なし) |
| `past_due` | `canceled` | **`active`(変更)** |
| `unpaid` | `canceled` | `canceled`(変更なし。Stripe側のリトライが尽きた状態) |
| `canceled` | `canceled` | `canceled`(変更なし) |
| `incomplete_expired` | `canceled` | `canceled`(変更なし。初回決済が確定しなかった状態) |

`unpaid`・`canceled`・`incomplete_expired`は引き続き即時`canceled`とする。これらは
いずれもStripe側のリトライが尽きた後、または決済自体が成立しなかった状態であり、
1節の再検討後も即時停止の判断を変更する理由がないため。

## 4. 実装

`prototype/stripe_webhook.py`の`_ACTIVE_STRIPE_STATUSES`に`"past_due"`を追加した
(`{"active", "trialing"}` → `{"active", "trialing", "past_due"}`)。これにより
`_map_stripe_status_to_fan_pass_status()`の分岐自体(「`_ACTIVE_STRIPE_STATUSES`に
含まれるかどうかの2値判定」という構造)は変更不要で、集合の内容変更のみで対応できた。

`prototype/test_stripe_webhook.py`の`test_subscription_updated_maps_status()`を
更新し、既存の`past_due maps to canceled`アサーションを`past_due stays active`に
変更したうえで、`unpaid`・`incomplete_expired`が引き続き`canceled`になることを示す
アサーションを新規に2件追加した(旧設計では`past_due`のみテストしており、
`unpaid`・`incomplete_expired`の実動作を検証するテストが無かったことも本フェーズで
判明した抜けである)。

## 5. 確認したテスト

- `python3 -I -m unittest discover -s prototype -p "test_*.py"`: 27件全件PASS。
- `python3 -I validate_test_cases.py`: 9件全件PASS。
- `python3 -I schema/check_venue_master_parity.py`: 36/36件PASS。

いずれも既存テストに変更なしでパスすることを確認した(回帰なし、変更ファイルは
`prototype/stripe_webhook.py`・`prototype/test_stripe_webhook.py`・設計文書のみ)。

## 6. 残課題

- `past_due`状態が長期化した場合(Stripe側のリトライが最終的に`unpaid`へ遷移する前に
  利用者が別の理由で利用を続ける等)の実運用上の挙動は、実Stripeアカウント接続後でないと
  検証できない(実Stripeアカウント・実GCP接続はオーナー承認待ち、pending-approval.md参照)。
- 本venture唯一の継続課金対象である月額フリーパスの契約者数が少ない前提のため、本フェーズの
  判断は実運用データに基づかない仮説のままである。実運用開始後、`past_due`のまま長期間
  (Stripe側のリトライ上限である2週間を超えて)経過する契約が確認された場合は、
  aircon-pasha同等の専用フィールド・通知配線の導入を再検討する。
