# 解約予約受理案内メッセージと制限モード状態の整合性対応(フェーズ185)

course-set-pashaのsubscription-cancellation-scheduled-message-suspension-consistency-
design.md(フェーズ157)を本ventureへ横展開する。subscription-cancellation-notification-
design.md(フェーズ184)6節「残課題」に明記されていた「制限モード中(`payment_suspended_at`
設定済み)の解約予約受理案内の文言整合性チェック」に対応する。

## 1. 問題

`render_subscription_cancellation_scheduled_message()`(フェーズ184)が組み立てる解約予約
受理案内メッセージには、次の一文が固定で含まれる。

> ・ご利用は今回の請求期間の終了日({period_end_date})まで通常通り継続します
> (作業完了報告・お手入れ案内の生成に制限はありません)

一方、本ventureにはpayment-failure-dunning-design.md 3節の段階3「制限モード」
(`cloud_function_webhook._is_payment_suspended()`が`user_profile.payment_suspended_at`の
設定有無で判定、作業完了報告・お手入れ案内の生成そのものを一時停止する状態)が既に存在する。
したがって、

- 顧客が決済失敗により既に制限モードへ移行済み(生成が既に一時停止中)の状態で
- Stripeカスタマーポータル等から解約予約(`cancel_at_period_end: false → true`)を行うと

「生成に制限はありません」という案内が、実際の状態(生成は既に停止中)と矛盾したまま顧客に
送信されてしまう。course-set-pashaフェーズ157と同じ問題である。

## 2. 本venture固有の設計判断: `_is_payment_suspended_now()`の実装は course-set-pasha と異なる

course-set-pashaフェーズ157の`_is_payment_suspended_now(usage_counter, user_id, now)`は、
`invoice.payment_failed`検知時刻と`PAYMENT_FAILURE_GRACE_PERIOD_DAYS`(猶予日数)から
「猶予期間を超過したかどうか」を都度計算する(course-set-pashaの`_is_payment_suspended()`が
そういう判定方式のため)。

これに対し本ventureの`cloud_function_webhook._is_payment_suspended(profile)`は、猶予期間
経過を都度計算せず、`payment_suspension_scheduler.send_payment_suspensions()`
(フェーズ145)が猶予期間経過後に1回だけ書き込む`user_profile.payment_suspended_at`
フィールドの設定有無のみで判定する、という別方式を既に採っている
(cloud_function_webhook.py 582-589行目のコメント参照)。したがって本フェーズの
`_is_payment_suspended_now()`は、course-set-pashaのように猶予日数の定数
(`PAYMENT_FAILURE_GRACE_PERIOD_DAYS`)や検知時刻・`now`を扱わず、**`payment_suspended_at`
の設定有無のみを見る**、`_is_payment_suspended()`そのままの判定条件を再利用する形にした
(「相当の関数」であって「同一の実装」ではない。course-set-pashaフェーズ157設計docの
「_is_payment_suspended_now()相当の判定ロジックの横展開を検討すべき」という記載は、猶予日数
計算そのものの複製ではなく判定"条件"の横展開を指すと解釈した)。

さらに、この判定に必要な状態(`payment_suspended_at`)を読み出すストアも、既に
`stripe_dispatch.dispatch_stripe_event()`が`invoice.payment_failed`/
`invoice.payment_succeeded`向けに受け取っている`payment_store`
(`payment_failure.PaymentFailureStoreProtocol`、`get_payment_suspended_at(user_id)`を
持つ)をそのまま再利用できる。course-set-pashaのように新規のstore引数
(`usage_counter`)を追加する必要が無い。

## 3. 実装

`prototype/subscription_cancellation_notification.py`に以下を追加した。

- `_is_payment_suspended_now(payment_store, user_id)`: `payment_failure.
  PaymentFailureStoreProtocol`を受け取り、`payment_store.get_payment_suspended_at(user_id)
  is not None`で判定する(2節参照、`now`引数は持たない)。`payment_store`が`None`・
  `user_id`が`None`/空文字列・`payment_store`が`get_payment_suspended_at`に対応していない
  場合は安全側デフォルトとして`False`を返す(`_is_payment_suspended(profile)`が
  `profile is None`で`False`を返すのと同じ考え方)。
- `render_subscription_cancellation_scheduled_message()`に`is_currently_suspended: bool =
  False`引数を追加。`True`の場合のみ、該当の一文を「契約自体は終了日まで継続するが、
  お支払い方法のご確認が必要な状態のため生成は既に一時停止しており、解約予約とは別に
  お支払い方法のご確認が必要」という趣旨の文言に差し替える。デフォルト`False`のため
  既存呼び出し経路への後方互換を保つ。
- `handle_subscription_cancellation_update()`に`payment_store: Optional[
  PaymentFailureStoreProtocol] = None`引数を追加。`OUTCOME_CANCELLATION_SCHEDULED`の
  場合のみ`_is_payment_suspended_now()`を評価してメッセージ生成へ渡す
  (`OUTCOME_CANCELLATION_RESCHEDULED`側のメッセージは制限モードの有無に関わらず文言が
  変わらないため参照しない、course-set-pashaフェーズ157と同じ判断)。

`prototype/stripe_dispatch.py`の`dispatch_stripe_event()`
`customer.subscription.updated`分岐では、既存の`payment_store`引数(フェーズ140で
`invoice.payment_failed`/`invoice.payment_succeeded`向けに追加済み)を、そのまま
`handle_subscription_cancellation_update()`へ追加で渡すよう配線した。新規の引数は
追加していない。`payment_store`未指定(`None`)時は`_is_payment_suspended_now()`が
安全側で`False`を返すため、フェーズ184時点の呼び出し経路(制限モード判定なし)と同じ
挙動が保たれる。

## 4. メッセージ文言(制限モード中)

```
・契約自体は今回の請求期間の終了日({period_end_date})まで継続しますが、お支払い方法の
  ご確認が必要な状態のため作業完了報告・お手入れ案内の生成は既に一時停止しています
  (解約予約とは別に、お支払い方法をご確認いただくまで生成は再開しません)
```

course-set-pashaフェーズ157の文言(「投稿文の生成」)を本venture固有の業務内容
(「作業完了報告・お手入れ案内の生成」)に翻案したもの。それ以外の箇条書き(終了日以降の
利用不可・日割り返金なし)・ポータルURL案内は変更しない。

## 5. テスト

- `test_subscription_cancellation_notification.py`:
  - `_is_payment_suspended_now()`: `payment_suspended_at`設定済み時に`True`、未設定時に
    `False`、`payment_store`/`user_id`(`None`・空文字列)未指定時・未知の`user_id`時・
    `get_payment_suspended_at`未対応ストア時に`False`を返すことを確認するテスト。
  - `render_subscription_cancellation_scheduled_message()`: `is_currently_suspended=True`
    時に新しい文言(「生成は既に一時停止しています」)を含み、従来の「生成に制限は
    ありません」という一文を含まないことを確認するテスト。`is_currently_suspended`
    未指定(デフォルト`False`)時は従来通りの文言のままであることを確認する既存テストは
    変更しない(後方互換の確認を兼ねる)。
  - `handle_subscription_cancellation_update()`: `payment_store`で制限モード中と判定
    される状態を渡した場合に送信される文面が制限モード向けの文言に切り替わること、
    制限モードでない状態・`payment_store`未指定時は従来通りの文言のままであること、
    `OUTCOME_CANCELLATION_RESCHEDULED`側では`payment_store`を渡しても文面が変化しない
    ことを確認するテスト。
- `test_stripe_dispatch.py`: `customer.subscription.updated`(`cancel_at_period_end`
  `false→true`)受信時に`payment_store`が制限モード中の顧客を記録している場合、送信される
  メッセージが制限モード向けの文言に切り替わることを確認する結合テスト
  (制限モード中でない場合・`payment_store`未指定の場合はいずれも従来通りの文言のまま
  であることを確認するテストもあわせて追加)。

venture全体459件全件(`python3 -m unittest discover -s prototype -p "test_*.py"`、実行前
420件+新規39件)パス・schema検証9件(`python3 schema/validate_test_cases.py`)パスを確認した。

## 6. 対応しなかった項目とその理由

subscription-cancellation-notification-design.md(フェーズ184)6節に残っていたもう一つの
残課題「`stripe_webhook.receive_stripe_webhook()`(実HTTPエントリポイント)への
`cancellation_push_client`/`portal_link_provider`引数の配線」は、本フェーズのスコープ外
とした。理由: 本ドキュメントが対応する「文言整合性チェック」は顧客に矛盾した案内が届く
という実害が既に存在する不具合の修正であるのに対し、HTTPエントリポイント配線は
`dispatch_stripe_event()`単体では既に検証済みの機能を実際の受信経路へ接続する作業であり、
実LINE Push Message API・実Stripeアカウント接続がオーナー承認待ちで止まっている現状では
実質的な価値の差が小さい(`payment_store`等の先行フィールドも同じ理由で後続フェーズに
配線を持ち越す前例がある)。優先度としては文言矛盾の解消を先に行うべきと判断した。

## 7. 残課題

- ~~`stripe_webhook.receive_stripe_webhook()`への`cancellation_push_client`/
  `portal_link_provider`引数の配線(実HTTPエントリポイント経由での検証、6節参照)。~~
  → フェーズ186で解消済み。`receive_stripe_webhook()`に両引数を追加し
  `dispatch_stripe_event()`へ委譲する配線を実装、テスト3件追加(README.mdフェーズ186参照)。
- 制限モード中の解約予約受理案内メッセージの具体的な文言(お支払い方法確認と解約予約という
  2つの手続きが並行して存在する状態の説明)は、実際の顧客からの問い合わせ実績が無い
  ため、初期案として妥当性を検証する必要がある(course-set-pashaフェーズ157と同じ課題)。
- 解約取り消し案内メッセージの問い合わせ導線文言の見直し(subscription-cancellation-
  notification-design.md 4節参照、フェーズ184から持ち越し)。
- 実LINE Push Message API・実Stripeアカウント接続はいずれも実アカウント作成
  (オーナー承認待ち)後の課題として引き続き残る。
