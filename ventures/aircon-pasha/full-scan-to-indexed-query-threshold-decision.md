# 全件走査→索引付きクエリ切り替え閾値の決定(フェーズ323)

## 位置づけ

firestore-composite-index-plan.md「残る課題」節が「インメモリ全件走査から索引付きクエリへの
切り替えタイミング(ユーザー数の閾値等)は、forklift-pasha版と同様、未確定のまま次回以降の
課題とする」と記していた項目に対応する。本フェーズではフェーズ322の次回候補(2)「他の設計
文書にも同種の記載漏れ・陳腐化した『残る課題』記述が残っていないかの棚卸し」を実施した結果、
記載漏れ・誤記自体は見つからなかった(multi-technician-shared-usage-design.md・
blocked-but-billing-detection-design.md・blocked-but-billing-owner-notification-design.md
はいずれも既に解消済みの注記が正しく反映されている)が、この「切り替え閾値未確定」は記載漏れ
ではなく実際に数値化されていない設計判断そのものであったため、本フェーズで数値化する。

forklift-pasha/firestore-composite-index-plan.md 57〜58行目も同じ「未確定」のまま残って
いることを確認したが、forklift-pasha側は対象コレクション・業者あたりの操作頻度が本venture
とは異なるため、本フェーズでは本venture(aircon-pasha)分のみを対象とし、forklift-pashaへの
横展開は次回候補として残す。

## 1. 現状の全件走査の洗い出し

`all_user_ids()`(`user_profile`コレクション全件の`stream()`)を呼ぶ箇所は4箇所あるが、
実行頻度が異なる。

| 呼び出し元 | 実行頻度 | 1回あたりの全件走査回数 |
|---|---|---|
| `daily_scheduler.build_payment_failure_reminder_states()` | 日次 | 1 |
| `daily_scheduler.build_payment_suspension_states()` | 日次 | 1 |
| `daily_scheduler.build_trial_user_states()` | 日次 | 1 |
| `blocked_but_billing_candidates.list_blocked_but_billing_candidates()` | 日次(blocked-but-billing-detection-design.md 90行目) | 1 |
| `deletion_candidate.list_deletion_candidates()` | 月次(data-retention-policy.md想定) | 1 |
| `deletion_candidate_final_confirmation.*` | 月次(daily_schedulerのdocstring、308フェーズで別個の月次Cloud Scheduler) | 1 |

日次バッチ分だけで、`user_profile`総ドキュメント数(=N、全登録ユーザー数)に対して
**4N回/日**の読み取りが発生する(月次バッチの2回は日次予算への影響が1/30に薄まるため、
本決定では無視できるほど小さいとみなす)。

## 2. 無料枠予算との照合

subscription-billing-cost-estimate.md(85〜103行目)が既に確立した前提をそのまま流用する。

- Firestore Sparkプラン(無料枠): 読み取り50,000回/日。
- 日次バッチ4Nの読み取りに加え、`usage_counter`操作(1回の生成あたり読み取り1回)・
  LINE Webhook受信時の`user_profile`単発取得(フォロー/アンフォール・支払いイベント等)
  といった「ユーザー操作に比例するその場読み取り」が同じ無料枠を共有する。
  subscription-billing-cost-estimate.mdの試算では書き込み側を基準に「1,000業者分まで
  無料枠内」という結論だったが、読み取り側はusage_counter分(1回/生成)に加えて本決定で
  新たに日次バッチ4N分を計上する必要がある。
- 保守的に、日次バッチの全件走査には無料枠50,000回の**半分(25,000回/日)**までを上限として
  割り当て、残り半分をusage_counter・Webhook等のその場読み取りに残す方針とする
  (pending_links/items()の「無料枠に収まる前提」判断〈firestore-provider-adapter-design.md
  3節〉と同じ保守的な配分方針)。

## 3. 決定

**`user_profile`の総ドキュメント数(総登録ユーザー数)Nが5,000を超えた時点で、日次バッチ
4箇所(`daily_scheduler.py`内3箇所・`blocked_but_billing_candidates.py`)の全件走査を、
各バッチが本来必要とする条件に対応する索引付きクエリ(firestore-composite-index-plan.md
#1〜#4)への切り替えを検討するトリガーとする。**

根拠: 25,000回/日(2節の割り当て上限) ÷ 4(日次バッチの全件走査回数) = 6,250。安全マージンを
取り、計算結果より小さいキリのよい数値として5,000を採用する(6,250のままでは閾値到達の
検知が遅れた場合に無料枠超過に直結するため、切り替え着手の判断・実装に要する時間を
考慮した前倒しの閾値とする)。

月次バッチ2箇所(`deletion_candidate.py`・`deletion_candidate_final_confirmation.py`)は
月間無料枠(50,000回/日 × 30日 = 1,500,000回/月相当)に対する影響が小さいため、本決定の
対象外とし、日次バッチと同じN=5,000到達時点で合わせて見直す運用とする(個別の閾値は設けない)。

## 4. 残課題・次回候補

- N=5,000という閾値は、2節の「半分を日次バッチに割り当てる」という配分自体が机上の
  保守的な仮定であり、実Firestore接続後の実測読み取り件数・他の読み取り要因
  (LIFF認証確認等、本決定では未算入のもの)を踏まえた再検証が必要。
- forklift-pasha/firestore-composite-index-plan.md 57〜58行目に残る同種の「未確定」
  記述への本決定と同じ方法論の横展開(forklift-pasha固有の全件走査箇所数・業者あたり
  操作頻度での再計算が必要なため、数値をそのまま流用することはできない)。
- 承認待ち事項(実Firestore/GCPプロジェクト等)がオーナーから承認された場合は、
  N=5,000到達前でも実測データに基づく再検証を優先する。
