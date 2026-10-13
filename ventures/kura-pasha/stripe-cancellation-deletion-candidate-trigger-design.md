# Stripe解約webhook起点の削除候補洗い出しトリガー設計(kura-pasha)

作成日: 2026-10-13(フェーズ232)

## 背景

line-reservation-aiフェーズ319(2026-10-13 04:00 UTC)の次回候補(2)「他venture
(aircon-pasha・course-set-pasha・kura-pasha)の`deletion_candidate.py`にも同種の
『連絡不能オーナーレビュー用レポート』機能が欠けていないかの横断点検・展開」を受けて
本venture(kura-pasha)を確認した結果、aircon-pasha・course-set-pashaにはいずれも
`deletion_candidate.py`(Stripe解約を起点とする削除候補化トリガー本体、
stripe-cancellation-deletion-candidate-trigger-design.mdフェーズ123・91)が存在するのに
対し、kura-pashaにはこの削除候補化トリガー自体がまだ一切実装されていない(`prototype/`に
`deletion_candidate.py`が存在しない)ことが判明した。本ventureの`stripe_webhook.py`の
`handle_customer_subscription_deleted()`は`subscription_status`を`"canceled"`へ更新する
のみで、`craftsman_workshop/{workshop_id}`を削除候補として洗い出すための`deletion_
candidate_at`フィールドへの書き込みは行っていない。

あわせて、data-retention-policy.md(フェーズ20)が保存期間ポリシーの対象として記載する
コレクション名`user_profile`は、実際にtech-stack.md相当の設計(workshop-store-firestore-
adapter-design.md等)が確定した結果の正式なコレクション名`craftsman_workshop`とは異なる
(data-retention-policy.md自身が「残課題」として、本文書がtech-stack.md相当の設計文書が
未作成の段階での想定に基づくため、実際のデータモデル設計を行う際は想定との整合を確認する
必要があると明記していた、フェーズ20時点の記載)。本フェーズはこの残課題の解消も兼ねる。

course-set-pasha/stripe-cancellation-deletion-candidate-trigger-design.md(フェーズ91)・
aircon-pasha側の同名ドキュメント(フェーズ123)の構成・判定ロジックを踏襲しつつ、本venture
固有の差異(後述4節)を反映する。実際のStripe Webhook受信自体は既にkura-pashaで実装済み
(他2ventureがフェーズ91・123時点ではWebhook受信口自体が未設計だったのとは異なる)ため、
本フェーズは設計と同じフェーズ内でコード実装・テストまで行う。

## 1. 対象とするStripe Webhookイベント

| イベント種別 | 扱い |
|---|---|
| `customer.subscription.deleted` | 削除候補化のトリガー。`handle_customer_subscription_deleted()`が`subscription_status`を`"canceled"`へ実際に更新した場合(既存の`_is_stale_subscription_status_event`ガードを通過した場合)に限り、イベントの発生時刻(`event_time`)を解約日として`deletion_candidate_at = 解約日 + 365日`を記録する。 |
| `checkout.session.completed` | 削除候補化の取り消しトリガー。`handle_checkout_session_completed()`が`subscription_status`を`"active"`へ実際に更新した場合(同じく既存ガードを通過した場合)に限り、既に`deletion_candidate_at`が設定されていれば削除する。 |

aircon-pasha・course-set-pashaの設計は取り消しトリガーを`customer.subscription.created`/
`updated`(statusがactive/trialingに戻る場合)としているが、kura-pashaの
`handle_customer_subscription_updated()`(フェーズ55)は`subscription_status`の書き込みを
一切行わない設計(`cancel_at_period_end`の前後比較通知と`current_period_end`/`plan_id`の
同期のみを行う)であり、`subscription_status`を`"active"`へ書き込むのは
`handle_checkout_session_completed()`のみである(2節「本venture固有の差異」参照)。
したがって取り消しトリガーは本venture側の実際の書き込み箇所に合わせて
`checkout.session.completed`とする。

## 2. データ構造

`craftsman_workshop/{workshop_id}`に新規フィールド`deletion_candidate_at`(nullable,
datetime)を追加する。

- 未設定(フィールド自体が存在しない、またはnull): 削除候補ではない(通常状態)。
- 値が設定されている: その時刻以降、削除候補として洗い出し対象になる。

`usage_counter/{workshop_id}`側には持たせない(course-set-pashaと同じく、判定の起点は
主体データ〈本ventureでは`craftsman_workshop`〉側の1箇所に集約する)。

## 3. 本venture固有の差異: 既存ガードへの相乗り

aircon-pasha・course-set-pashaの`deletion_candidate.py`は、`mark_deletion_candidate_on_
subscription_deleted()`・`clear_deletion_candidate_on_subscription_reactivated()`自身が
`event_time`ベースの専用staleガード(`_is_stale_deletion_candidate_event()`相当)を持つ
(本体側の`subscription_status`更新ガードとは独立に、deletion_candidate_at専用の
`deletion_candidate_state_event_time`フィールドで順序保証する設計)。

kura-pashaでは、`mark_...()`/`clear_...()`の呼び出し自体を「`subscription_status`が
実際に書き換わった分岐の内側」に置くことで、既存の`_is_stale_subscription_status_event()`
ガード(subscription-status-event-order-guard-design.md、フェーズ197/198系で確立済み)に
そのまま相乗りする。これにより`deletion_candidate_at`専用のstaleガード・専用の
イベント時刻記録フィールドは追加不要になる(2ventureより少ない状態で同じ順序保証を
達成できる、本venture固有の簡略化)。トレードオフとして、将来`subscription_status`の
更新ロジックと`deletion_candidate_at`の更新ロジックが分岐条件レベルで分離された場合は
この前提が崩れるため、変更時は本節を再確認すること。

## 4. 関数設計(実装: `prototype/deletion_candidate.py`)

```python
RETENTION_DAYS = 365  # data-retention-policy.md「保存期間ポリシー(案)」

def mark_deletion_candidate_on_subscription_deleted(
    workshop_store, workshop_id: str, event_time: datetime,
) -> datetime:
    """event_time + 365日 を deletion_candidate_at として書き込み、書き込んだ値を返す。
    呼び出し元(stripe_webhook.handle_customer_subscription_deleted)が既に
    _is_stale_subscription_status_event() を通過した後にのみ呼ぶ前提のため、
    本関数自体はstale判定を行わない(3節)。"""

def clear_deletion_candidate_on_subscription_reactivated(workshop_store, workshop_id: str) -> bool:
    """deletion_candidate_at が設定されていれば削除してTrueを返す。未設定ならFalse
    (冪等)。呼び出し元のstale判定前提は上と同じ。"""

def list_deletion_candidates(workshop_store, now: datetime) -> list[str]:
    """all_workshop_ids()を走査し、deletion_candidate_at が now 以前に設定されている
    workshop_idの一覧を返す(読み出し専用、削除・通知は行わない)。"""
```

`WorkshopStoreProtocol`(usage_counter_workshop.py)に`get_deletion_candidate_at`・
`set_deletion_candidate_at`・`clear_deletion_candidate_at`の3メソッドを追加し、
`InMemoryWorkshopStore`に実装する(既存の`payment_failure_detected_at`系と同じ
get/set/clearの3メソッド方式)。

## 5. 未解決事項・次の課題

- `list_deletion_candidates()`を日次バッチ(`daily_scheduler.py`・
  `cloud_function_run_daily_workshop_checks.py`)から呼び出し、削除候補化後の最終確認
  (data-retention-policy.md「削除候補化後の最終確認」節: LINE push主経路・メール代替経路)
  へつなぐ配線は本フェーズのスコープ外とし、次回候補として残す(aircon-pasha・
  course-set-pashaの`cloud_function_send_deletion_candidate_final_confirmations.py`・
  `list_unreachable_deletion_candidates()`相当の機能も同様に未着手)。
- data-retention-policy.md自体の`user_profile`表記を`craftsman_workshop`へ訂正する作業は
  本フェーズでは行わない(本設計ドキュメントで正しいコレクション名を明記することで実務上の
  混同は防げるため、data-retention-policy.md本体の訂正は次回候補とする)。
- 実Firestore接続後、`craftsman_workshop`コレクションの範囲クエリ
  (`deletion_candidate_at <= now`)実装が必要になる点はcourse-set-pashaと同じ(firestore-
  provider-adapter-design.md側の残課題として引き続き残る)。

最終更新: 2026-10-13 08:00 UTC(フェーズ232: 新規文書化)
