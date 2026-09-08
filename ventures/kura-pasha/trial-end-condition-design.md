# 無料トライアル終了判定関数の設計(フェーズ47)

作成日: 2026-09-08(フェーズ47)

subscription-billing-data-model-design.md(フェーズ46)「4. 未検証・残課題」に残っていた、
pricing-plan.md「無料トライアル条件(仮)」を`trial_start_at`起算でどう判定するかの具体的な
関数設計(他venture`trial-end-condition-a-*-design.md`相当)に対応する。

## 1. 前提の確認: pricing-plan.mdの条件文言

pricing-plan.md「無料トライアル条件(仮)」は以下の通り(初回メモ時点の文言)。

> 期間: 初回の生成成功から1回無料、または30日間のいずれか早い方まで(受注頻度が低い業態の
> ため、course-set-pashaの「生成5回到達」のような回数基準は本ventureでは緩すぎる―数ヶ月
> 受注が無ければトライアルが実質無期限になってしまう―と判断し、期間上限を優先する設計と
> した)。

## 2. 起点(`trial_start_at`)の確定: 他ventureと異なり「workshop作成時」とする

aircon-pasha・course-set-pashaのtrial-start-anchor-decision.mdはいずれも起点を「初回生成
成功時」に確定しているが、本ventureではそのまま踏襲せず「workshop作成時
(craftsman-account-linking-design.mdでLINE連携・workshop新規作成が完了した時点)」を
起点として確定する。理由は以下の通り。

- pricing-plan.md自身の記載理由(上記引用の括弧内)が、まさに「回数基準だけだと受注が
  数ヶ月無い場合にトライアルが無期限化する」ことを懸念して30日の期間上限を設けたという
  ものである。ここで期間の起点を他venture同様「初回生成成功時」にしてしまうと、初回生成が
  数ヶ月発生しない限り30日のカウント自体が始まらず、懸念していた「無期限化」を全く防げない
  (期間条件が回数条件と同じ弱点を持ってしまい、期間上限を設けた意味が失われる)。
- 期間上限が機能するためには、生成の有無に関わらず必ず発生するイベント(=workshop作成、
  すなわち契約・LINE連携完了)を起点にする必要がある。これにより「契約はしたが受注が
  無く一度も生成しないまま30日経過した」workshopも、期間条件により有償化(またはトライ
  アル終了)の判定対象になる。
- 一方「1回無料」という回数条件は、workshop作成後いつ初回生成が行われても関係なく
  「生涯最初の1回」を無料にするという意味であり、起点をworkshop作成時にしても回数条件
  の実質(最初の1回だけ無料)は変わらない。

以上より、`trial_start_at`は`craftsman_workshop`の新規作成時(craftsman-account-linking-
design.md「workshop新規作成」処理)に1回だけ設定し、以降不変とする(subscription-billing-
data-model-design.md 1節で既に確定済みのフィールド位置・型`Optional[datetime]`はそのまま
変更しない)。

## 3. 追加フィールド: `trial_generation_used`(workshop単位の一度切りフラグ)

「1回無料」の回数条件は`usage_counter/{workshop_id}`の月間カウント(月替わりで0にリセット
される)では表現できない(トライアル分の1回は月をまたいでも「使用済み」のまま保持する
必要がある)。そのため、月次リセットの影響を受けない一度切りのフラグを`craftsman_workshop`
に新設する。

```
craftsman_workshop/{workshop_id}:
  ...(既存: contractor_user_id, member_user_ids, plan_id,
      stripe_customer_id, subscription_status, trial_start_at, current_period_end 等)
  trial_generation_used: bool   # 新規追加。生涯最初の生成成功時に1回だけTrueへ、以降不変
```

## 4. 判定関数

```python
TRIAL_PERIOD_DAYS = 30  # pricing-plan.md「無料トライアル条件(仮)」確定値

def is_trial_period_over(
    workshop_id: str,
    now: datetime,
    workshop_store: WorkshopStoreProtocol,
) -> bool:
    trial_start_at = workshop_store.get_trial_start_at(workshop_id)
    if trial_start_at is None:
        # workshop作成時に必ず設定される想定だが、未設定(データ不整合・移行中)の
        # workshopに対しては安全側に倒しトライアル終了とは判定しない。
        return False
    if workshop_store.get_trial_generation_used(workshop_id):
        return True
    return now >= trial_start_at + timedelta(days=TRIAL_PERIOD_DAYS)
```

- 「1回無料、または30日、いずれか早い方」を素直に「いずれかの条件が真になった時点で
  トライアル終了」という論理和として実装した。
- `trial_generation_used`が真になるタイミング(生成成功時にTrueへ更新する処理)は本設計の
  範囲外とし、5節「今後の課題」に残す(course-set-pasha/aircon-pashaの
  `increment_trial_generation_count`相当の処理を、本ventureでは月次カウントと分離した
  一度切りフラグ用に別途用意する必要がある)。

## 5. トライアル終了後の挙動は範囲外

他venture(course-set-pasha/trial-end-condition-a-implementation-design.md等)と同じく、
本設計は「トライアルが終了しているかどうかの判定」のみを扱う。判定結果を使って実際に
(a)生成リクエストを止める(生成一時停止)、(b)通知メッセージを送る、(c)Stripe Checkout
への誘導文言を出す、という後続処理はいずれも次の課題として残す。

## 6. 今後の課題

- `trial_generation_used`を生成成功時にTrueへ更新する書き込み処理、および
  `process_generation_request`/`select_message_context`への`is_trial_period_over`の
  組み込み(トライアル終了後の生成一時停止・案内文言への切り替え)は未着手。
- `trial_start_at`をworkshop作成時に書き込む実処理(craftsman-account-linking-design.mdの
  workshop新規作成フロー側)は未実装。本設計は判定関数側のみをプロトタイプコード化する。
- 実Stripe接続・Checkout Session発行フロー自体は引き続きオーナー承認待ちの範囲
  (pending-approval.md参照)。

最終更新: 2026-09-08 19:00 UTC
