# Stripe解約webhook起点の削除候補洗い出しトリガー設計

作成日: 2026-08-22(フェーズ91)

## 背景

data-retention-policy.md(フェーズ85)「今後の課題」で、「Stripe解約イベント(webhook)を
起点に削除候補を洗い出す具体的なトリガー設計は、実Stripe Webhook接続後の課題として残す」
としていた点に対応する。実際のStripe接続自体はオーナー承認待ちの範囲だが、線引き・データ
構造・判定ロジックの設計と机上検証は接続前でも進められるため、本フェーズで行う。

## 前提の再確認

data-retention-policy.md「保存期間ポリシー(案)」表のとおり、削除候補化の起点は常に
「Stripe解約日」であり、unfollow(LINEブロック)単独では削除候補化しない。また
「トライアル中・有料プラン中(active/trialing)」は保有継続であり、解約後に再契約した
場合は削除候補化を取り消す必要がある(この「取り消し」経路はdata-retention-policy.md
時点では明示されておらず、本フェーズで新たに整理する派生課題)。

## 1. 対象とするStripe Webhookイベント

| イベント種別 | 扱い |
|---|---|
| `customer.subscription.deleted` | 削除候補化のトリガー。イベントの発生時刻(`event.created`、Unix time)を解約日として、`deletion_candidate_at = 解約日 + 365日`を`user_profile/{user_id}`に記録する。 |
| `customer.subscription.created` / `customer.subscription.updated`(status が`active`または`trialing`に戻る場合) | 削除候補化の取り消しトリガー。既に`deletion_candidate_at`が設定されていれば削除する(フィールド自体を消す)。再契約は新規契約と同じ手順で行われる想定(pricing-plan.md)だが、Stripe側のカスタマーIDが継続する再契約(同一カスタマーの再開)であれば`customer.subscription.created`が発火するため、これを取り消しの契機とする。 |

`customer.subscription.updated`のうち解約以外の変更(プラン変更・支払い方法更新等)は
本設計の対象外(既存のsubscription-cancellation-flow-design.mdのダウングレード処理が
別途扱う)。

## 2. データ構造

`user_profile/{user_id}`に新規フィールド`deletion_candidate_at`(nullable, Unix timestamp
またはISO8601文字列)を追加する。

- 未設定(フィールド自体が存在しない、またはnull): 削除候補ではない(通常状態)。
- 値が設定されている: その時刻以降、削除候補として洗い出し対象になる。

`usage_counter/{user_id}`側には削除候補フラグを持たない(data-retention-policy.mdの
「同じ`user_id`をキーとするため削除時は2ドキュメントをまとめて対象にできる」設計を
踏襲し、判定の起点は`user_profile`側の1箇所に集約する)。

## 3. 関数設計(プロトタイプ方針)

line-user-id-linking-design.md・unfollow-event-handling-design.mdと同じく、実Firestore
接続なしで机上検証できる薄い純粋関数として設計する。

```python
def mark_deletion_candidate_on_subscription_deleted(
    profile_store, user_id: str, event_time: datetime,
) -> None:
    """customer.subscription.deleted 受信時に呼ぶ。
    event_time + 365日 を deletion_candidate_at として書き込む。
    既に deletion_candidate_at が設定済みの場合も上書きする(同一ユーザーへの
    2回目以降の解約イベントは通常発生しない想定だが、万一届いた場合は
    最新の解約日を基準に再計算する方が安全側)。
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

- `mark_deletion_candidate_on_subscription_deleted()`と
  `clear_deletion_candidate_on_subscription_reactivated()`はいずれも
  unfollow-event-handling-design.mdの`purge_expired_links()`型の「読み書きが
  薄い1レコード更新関数」パターンを踏襲し、Webhook本体(将来のStripe Webhook用
  Cloud Function)からevent種別ディスパッチ後にそのまま呼べる形にする。
- `list_deletion_candidates()`は実装時、Firestoreの範囲クエリ
  (`deletion_candidate_at <= now`)にそのまま対応させられる形を想定するが、
  MVPの`InMemoryProfileStore`(プロトタイプ用)では単純な線形走査で代替する。

## 4. 未解決事項・次の課題

- 実際のStripe Webhook受信エンドポイント(署名検証・イベント種別ディスパッチ)は
  course-set-pashaにまだ存在しない(LINE Webhook用の`dispatch_webhook_events()`
  (webhook-event-dispatch-design.md)はあるが、Stripe側のWebhook受信口は未設計)。
  本フェーズはStripeイベント受信後に呼ばれる中身の関数設計にとどめ、受信口自体の
  設計(署名検証方式・エンドポイントURL)は実Stripeアカウント接続後の課題として残す。
- `customer.subscription.created`が「再契約」と「(同一ユーザーの)初回契約」の
  どちらでも発火する点をどう区別するかは、実Stripe接続後にWebhookペイロードの
  `customer`フィールド(既存顧客IDかどうか)を確認して切り分ける必要がある。
  初回契約時は`deletion_candidate_at`が最初から未設定のため`clear_...()`は
  実質的に何もしない(冪等)ため、区別を誤っても実害はない設計にしている。
- 月次バッチ(Cloud Scheduler)からの`list_deletion_candidates()`呼び出し配線、
  および削除候補化後の最終確認(LINE push / 代替連絡経路)への引き渡しは、
  data-retention-policy.md「削除候補化後の最終確認」節の設計をそのまま使う想定だが、
  実際の呼び出し配線は実Firestore/実Stripe接続後の課題として残す。

## 5. Cloud Scheduler `retry_config`方針(月次バッチ、フェーズ340)

line-reservation-aiフェーズ続き357(2026-10-28 02:00 UTC)からの申し送り
「course-set-pasha・forklift-pasha側での同種のretry_config横断確認」(申し送り元:
aircon-pashaフェーズ349〜350、deletion-candidate-final-confirmation-scheduler-design.md
2.1節・2.2節・4節)に対応する。

aircon-pashaが確立した判断基準(フェーズ349 2.1節・2.2節)は「1回の起動失敗で次回
再試行が月単位で遅れ、data-retention-policy.mdが定める猶予期間の実効性が下がる実害が
生じる低頻度(月次等)バッチ」には`retry_config`を設定し、日次・15分間隔等の高頻度
ジョブ(次回起動が自然に再試行として拾われる)には設定不要、というものである。これを
本venture側に適用する。

本ventureのCloud Schedulerジョブを棚卸しした結果:

| ジョブ | 頻度 | 判定 |
|---|---|---|
| `trial_end_scheduler`(trial-end-scheduler-design.md) | 日次1回 | 失敗しても翌日の実行で自然に再試行される冪等設計のため対応不要(kura-pasha・line-reservation-aiと同じ結論)。 |
| `payment_failure_reminder_scheduler`(payment-failure-reminder-scheduler-design.md) | 日次1回 | 同上、対応不要。 |
| 削除候補化後の最終確認〜削除実行バッチ(`list_deletion_candidates()`、本ファイル3節) | **月次程度**(data-retention-policy.md「削除の実行方法(MVP)」節) | aircon-pashaのdeletion-candidate-final-confirmation-scheduler-design.mdが扱う「削除候補の最終確認」バッチと同種・同頻度のジョブであり、1回の起動失敗で次回再試行が最大約1ヶ月後になる点も同じ。**`retry_config`の設定価値がある**と判断する。 |

本venture側は唯一、aircon-pashaと同種の低頻度バッチを持つことが判明したため、
aircon-pashaの確定値(deletion-candidate-final-confirmation-scheduler-design.md 4節)を
そのまま採用する方針とする: `retry_count: 5`、指数バックオフ
(`min_backoff_duration: 300s`〜`max_backoff_duration: 3600s`、`max_doublings: 3`)。
5回失敗時はオーナーへのアラート通知(cloud-monitoring-alert-policy-design.md相当、
本venture側は未作成のため今後の課題とする)に委ね、手動実行を促す運用とする。

本バッチ自体の実装(Cloud Scheduler構築・`list_deletion_candidates()`の呼び出し配線)は
実Firestore/実Stripe接続後の課題として既に3節・4節で保留されているため、本節は
その実装時に反映すべき`retry_config`パラメータを先行して確定したものであり、
現時点でコード変更やCloud Scheduler自体の作成(オーナー承認が必要なアクション)は
一切行っていない。forklift-pasha側への同種確認は本venture側からは申し送るに留め、
直接の書き込みは行わない。
