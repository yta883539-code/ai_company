# Stripe解約webhook起点の削除候補洗い出しトリガー設計

作成日: 2026-08-24(フェーズ123)

## 背景

data-retention-policy.md「今後の課題」に残っていた「削除候補化トリガー(Stripe解約Webhook
受信時の`deletion_candidate_at`マーク付け等、course-set-pashaの
stripe-cancellation-deletion-candidate-trigger-design.md相当の設計)は本ventureでは未着手」
に対応する。course-set-pashaの同名ドキュメント(フェーズ91)の構成・判定ロジックを踏襲しつつ、
本venture固有の差異(Checkout Session作成時点で`user_id`が既知であるためStripe連携が
単純化されている点、プラン体系がスモール/スタンダード/繁忙期対応の3段階である点)を反映する。
実際のStripe Webhook接続自体はオーナー承認待ちの範囲だが、線引き・データ構造・判定ロジックの
設計と机上検証は接続前でも進められるため、本フェーズで行う。

## 前提の再確認

data-retention-policy.md「保存期間ポリシー(案)」表のとおり、削除候補化の起点は常に
「Stripe解約日」であり、unfollow(LINEブロック)単独では削除候補化しない
(フェーズ109・111・112で確定済み)。また「トライアル中・有料プラン中(active/trialing)」は
保有継続であり、解約後に再契約した場合は削除候補化を取り消す必要がある(この「取り消し」経路は
data-retention-policy.md時点では明示されておらず、course-set-pashaと同様に本フェーズで
新たに整理する派生課題)。

## 1. 対象とするStripe Webhookイベント

| イベント種別 | 扱い |
|---|---|
| `customer.subscription.deleted` | 削除候補化のトリガー。イベントの発生時刻(`event.created`、Unix time)を解約日として、`deletion_candidate_at = 解約日 + 365日`を`user_profile/{user_id}`に記録する。 |
| `customer.subscription.created` / `customer.subscription.updated`(status が`active`または`trialing`に戻る場合) | 削除候補化の取り消しトリガー。既に`deletion_candidate_at`が設定されていれば削除する(フィールド自体を消す)。 |

`customer.subscription.updated`のうち解約以外の変更(プラン変更・支払い方法更新等)は
本設計の対象外(既存のsubscription-cancellation-flow-design.mdのダウングレード処理が
別途扱う)。365日という値はdata-retention-policy.md「保存期間ポリシー(案)」表が既に
採用している1年をそのまま踏襲する(line-reservation-ai・course-set-pashaと揃えた暫定値)。

## 2. データ構造

`user_profile/{user_id}`に新規フィールド`deletion_candidate_at`(nullable, Unix timestamp
またはISO8601文字列)を追加する。

- 未設定(フィールド自体が存在しない、またはnull): 削除候補ではない(通常状態)。
- 値が設定されている: その時刻以降、削除候補として洗い出し対象になる。

`usage_counter/{user_id}`側には削除候補フラグを持たない
(data-retention-policy.mdの「同じ`user_id`をキーとするため削除時は2ドキュメントを
まとめて対象にできる」設計を踏襲し、判定の起点は`user_profile`側の1箇所に集約する)。
`pending_links/{code}`は本トリガーの対象外(24時間で自然失効する別ライフサイクル、
user-account-linking-design.md 3節)。

user-account-linking-design.md 5節で確定済みの`user_profile`スキーマ
(`business_name`・`business_type`・`email`・`stripe_customer_id`・`current_plan_id`・
`linked_at`)に、本フェーズで`deletion_candidate_at`を追加する形になる。

## 3. 関数設計(プロトタイプ方針)

course-set-pashaの`mark_deletion_candidate_on_subscription_deleted()`と同じ考え方で、
実Firestore接続なしで机上検証できる薄い純粋関数として設計する。

```python
def mark_deletion_candidate_on_subscription_deleted(
    profile_store, user_id: str, event_time: datetime,
) -> None:
    """customer.subscription.deleted 受信時に呼ぶ。
    event_time + 365日 を deletion_candidate_at として書き込む。
    既に deletion_candidate_at が設定済みの場合も上書きする(最新の解約日を
    基準に再計算する方が安全側)。
    """

def clear_deletion_candidate_on_subscription_reactivated(
    profile_store, user_id: str,
) -> None:
    """customer.subscription.created、または updated で status が
    active/trialing に戻ったことを検知した際に呼ぶ。
    deletion_candidate_at が設定されていれば削除する。未設定なら何もしない
    (冪等)。
    """

def list_deletion_candidates(
    profile_store, now: datetime,
) -> list[str]:
    """deletion_candidate_at が now 以前に設定されている user_id の一覧を返す。
    data-retention-policy.md「削除の実行方法(MVP)」の月次バッチから呼ばれる
    想定の読み出し専用関数(削除・通知そのものは行わない)。
    """
```

- 2つの更新関数は`follow-unfollow-event-handling-design.md`の`purge_expired_links()`型の
  「読み書きが薄い1レコード更新関数」パターンを踏襲し、Webhook本体(将来のStripe Webhook用
  Cloud Function)からevent種別ディスパッチ後にそのまま呼べる形にする。
- `list_deletion_candidates()`は実装時、Firestoreの範囲クエリ
  (`deletion_candidate_at <= now`)にそのまま対応させられる形を想定するが、
  MVPの`InMemoryProfileStore`(プロトタイプ用)では単純な線形走査で代替する。

## 4. 本venture固有の留意点: Webhook受信口の単純さ

user-account-linking-design.md 4節で確定済みのとおり、本ventureはCheckout Session作成時に
`client_reference_id`へ既知の`user_id`を設定できるため、`checkout.session.completed`の
処理はcourse-set-pashaの`resolve_user_id()`相当の逆引きロジックが不要でシンプルになっている。
一方、本フェーズが扱う`customer.subscription.deleted`/`created`/`updated`は`customer`
(Stripe顧客ID)のみを含み`user_id`を直接含まないため、これらのイベントについては
`stripe_customer_id → user_id`の逆引き(`make_resolve_user_id()`相当、
user-account-linking-design.md 4節に設計済み)が引き続き必要になる。この逆引きを経た後に
本フェーズの2関数を呼び出す構成となる。

## 5. 未解決事項・次の課題

- 実際のStripe Webhook受信エンドポイント(署名検証・イベント種別ディスパッチ)は本venture
  にまだ存在しない(LINE Webhook用の`receive_webhook()`/`dispatch_webhook_events()`
  (webhook-http-entry-point-design.md)はあるが、Stripe側のWebhook受信口は未設計)。
  本フェーズはStripeイベント受信後に呼ばれる中身の関数設計にとどめ、受信口自体の設計
  (署名検証方式・エンドポイントURL)は実Stripeアカウント接続後の課題として残す
  (course-set-pashaも同じ制約を残したまま)。
- `customer.subscription.created`が「再契約」と「(同一ユーザーの)初回契約」のどちらでも
  発火する点をどう区別するかは、実Stripe接続後にWebhookペイロードの`customer`フィールド
  (既存顧客IDかどうか)を確認して切り分ける必要がある。初回契約時は`deletion_candidate_at`が
  最初から未設定のため`clear_...()`は実質的に何もしない(冪等)ため、区別を誤っても実害は
  ない設計にしている(course-set-pashaと同じ整理)。
- 月次バッチ(Cloud Scheduler)からの`list_deletion_candidates()`呼び出し配線、および
  削除候補化後の最終確認(LINE push / 代替連絡経路)への引き渡しは、
  data-retention-policy.md「削除候補化後の最終確認」節の設計をそのまま使う想定だが、
  実際の呼び出し配線は実Firestore/実Stripe接続後の課題として残す。
- 本ドキュメント自体はプロトタイプ関数の設計のみで、`prototype/`配下への実コード化・
  テスト追加は次回以降の候補とする。
