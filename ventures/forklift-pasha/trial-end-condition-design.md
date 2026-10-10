# 無料トライアル終了判定関数の設計(フェーズ118)

作成日: 2026-10-10(フェーズ118)

pricing-plan.md「無料トライアル条件(仮)」が「詳細な判定ロジックは実装時に設計する」として
先送りにしていた、トライアル終了の具体的な判定ロジックを設計する。他venture
(course-set-pasha/trial-end-condition-a-implementation-design.md、kura-pasha/
trial-end-condition-design.md)と同様の位置づけの文書だが、本venture未着手だった
cross-venture parityギャップの解消でもある。

## 1. 前提の確認: pricing-plan.mdの条件文言

pricing-plan.md「無料トライアル条件(仮)」(フェーズ4)は以下の通り。

> 期間: 初回生成から30日間、またはcourse-set-pasha等と同様の「生成○回到達」のいずれか早い方
> (具体的な回数基準はdaily点検の頻度が高いことを踏まえ、kura-pashaの「生成1回」のような
> 極端に少ない基準ではなく、course-set-pashaの「生成5回」程度を仮の基準とする想定。詳細な
> 判定ロジックは実装時に設計する)。

本フェーズは上記の「仮の基準」を具体的な判定関数として確定する。

## 2. 起点(`trialStartAt`)の確認: 既存設計のまま変更なし

firestore-data-model.mdの`fleet_operator.trialStartAt`は既に「`pricing-plan.md`『無料トライアル
条件(仮)』の起算点(初回生成時に1回だけ設定、以降不変)」と定義済みである
(aircon-pasha・course-set-pashaと同じ「初回生成成功時」起点方式)。kura-pashaのような
「workshop作成時」起点への変更は、本ventureでは次の理由により不要と判断する。

- kura-pashaが起点を「workshop作成時」にした理由は、受注頻度が極端に低い(鞍・馬具の修理)
  業態で「初回生成成功時」起点だと受注が無い限り30日のカウントが始まらず期間条件が機能
  しないことを懸念したためである(trial-end-condition-design.md 2節)。
- 本venture(daily区分=稼働日ごとの始業前点検)は逆にmvp-flow-draft.md想定の中で最も
  生成頻度が高い業態であり、「初回生成成功時」起点でも通常は契約直後(1〜数日以内)に
  初回生成が発生する見込みが高い(kura-pashaが懸念した「無期限化」のリスクは小さい)。
- `trialStartAt`は既にphase97でアクセストークン方式の`internal_id`設計と合わせて確定済みの
  フィールドであり、起点方式自体を変更すると既存のaccess-token-reissue-design.md・
  payment-identity-verification-design.mdの記述との整合確認が追加で必要になる。現時点で
  起点方式を変更する具体的な理由が無いため、既存設計(初回生成成功時)をそのまま維持する。

## 3. 追加フィールド: `trialGenerationCount`(月次リセットされない累積カウント)

「生成5回到達」の回数条件は`usage_counter/{internal_id}`の月間カウント(`count`、月初に
リセットされる、firestore-data-model.md「コレクション構成」3.参照)では表現できない
(トライアル中に月をまたいで合計5回に達した場合もカウントし続ける必要がある)。course-set-pasha
の`trial_generation_count`と同じ位置づけで、月次リセットの影響を受けない累積カウントを
`fleet_operator`に新設する。

```
fleet_operator/{internal_id}:
  ...(既存: accessToken, email, planId, vehicleCount, stripeCustomerId,
      subscriptionStatus, trialStartAt, currentPeriodEnd, lastAccessedAt)
  trialGenerationCount: 0   # 新規追加。生成成功ごとに1加算、5に達した後も加算を続けて良いが
                            # (上限到達後の判定には影響しない)、有償転換後は増分を止める
                            # (5節「実装への影響メモ」参照)
```

## 4. 判定関数

```python
TRIAL_PERIOD_DAYS = 30        # pricing-plan.md「無料トライアル条件(仮)」確定値
TRIAL_GENERATION_LIMIT = 5    # 同上、course-set-pashaと同じ基準

def is_trial_period_over(
    internal_id: str,
    now: datetime,
    operator_store: FleetOperatorStoreProtocol,
) -> bool:
    trial_start_at = operator_store.get_trial_start_at(internal_id)
    if trial_start_at is None:
        # 初回生成がまだ発生していない(firestore-data-model.mdの設計通り、trialStartAtは
        # 初回生成成功時に1回だけ設定される)。初回生成前は常にトライアル中として扱う。
        return False
    if operator_store.get_trial_generation_count(internal_id) >= TRIAL_GENERATION_LIMIT:
        return True
    return now >= trial_start_at + timedelta(days=TRIAL_PERIOD_DAYS)
```

- 「生成5回到達、または初回生成から30日、いずれか早い方」を素直に論理和として実装した
  (kura-pasha/trial-end-condition-design.md 4節と同型)。
- `trialGenerationCount`が今回の呼び出しで初めて5に達したかどうかの通知判定(「1回のみ
  通知」の制御)は、本設計の範囲外とし5節「今後の課題」に残す
  (`determine_usage_limit_notice()`〈overage_notifications.py〉と同型のbefore/after判定を
  想定)。

## 5. トライアル終了後の挙動・実装方針は範囲外

他venture(course-set-pasha/trial-end-condition-a-implementation-design.md等)と同じく、
本設計は「トライアルが終了しているかどうかの判定」のみを扱う。判定結果を使って
(a)生成リクエストを止める(生成一時停止)、(b)通知メッセージを送る、(c)Stripe Checkout
への誘導文言を出す、という後続処理はいずれも次の課題として残す。

## 6. 今後の課題

- `trialGenerationCount`を生成成功時に加算する書き込み処理(`FleetOperatorStoreProtocol`への
  `get_trial_start_at`/`set_trial_start_at`/`get_trial_generation_count`/
  `increment_trial_generation_count`の追加)。本フェーズでは判定関数とProtocol定義のみを
  `prototype/trial_management.py`として実装し、Webフォーム送信時の実際の呼び出し配線
  (`web-form-ui-design.md`・`mvp-flow-draft.md`側の処理フロー)は未着手のまま残す。
- (A)生成5回到達・(B)期間30日到達のいずれの経路で検知した場合も、通知メッセージの文言自体
  (aircon-pasha/trial-end-notification-design.md相当)は本venture未設計。次回候補とする。
- (B)期間到達側の検知には、line-reservation-ai/reminder-scheduler-design.md・
  kura-pasha/daily-scheduler-design.md相当の日次スケジューラが必要だが、本venture側には
  まだ存在しない(usage-and-fleet-overage-notification-design.mdの通知2種と合わせて
  一体設計するのが望ましい。次回候補)。
- `get_subscription_status`等、有償契約状態を判定する手段も本venture未着手(本判定関数は
  トライアル終了判定と有償契約済み判定を混同しないよう、現時点では意図的に
  `is_trial_period_over()`の結果だけを使った生成一時停止の配線は行わない)。
- 実際のGCPプロジェクト作成・Firestore接続・Stripe接続はいずれもオーナー承認待ちの範囲
  (pending-approval.md参照)。本ドキュメントは机上の判定ロジック設計のみ。

最終更新: 2026-10-10 15:00 UTC(フェーズ118: pricing-plan.md「無料トライアル条件(仮)」が
先送りにしていた判定ロジックを確定。起点は既存設計〈初回生成成功時〉を維持し、月次リセット
されない`trialGenerationCount`フィールドを新設、`is_trial_period_over()`を
「生成5回到達、または初回生成から30日、いずれか早い方」の論理和として設計した)
