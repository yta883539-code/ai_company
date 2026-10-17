# 全件走査→索引付きクエリ切り替え閾値の決定(フェーズ166)

## 位置づけ

aircon-pashaフェーズ323(full-scan-to-indexed-query-threshold-decision.md)の次回候補(2)
「forklift-pasha/firestore-composite-index-plan.md 57〜58行目に残る同種の『未確定』記述への
横展開(forklift-pasha固有の全件走査箇所数・業者あたり操作頻度での再計算が必要)」に対応する。
aircon-pashaの数値をそのまま流用せず、本venture固有の全件走査箇所・頻度で再計算する。

## 1. 現状の全件走査の洗い出し

`fleet_operator`コレクションに対して`all_internal_ids()`(全件列挙)を呼ぶ箇所は2箇所あり、
いずれも日次バッチである(aircon-pashaのような「blocked-but-billing」「payment-suspension」
相当の追加バッチは本venture〈LINE非依存の汎用Webフォーム、tech-stack.md〉には存在しない)。

| 呼び出し元 | 実行頻度 | 1回あたりの全件走査回数 |
|---|---|---|
| `trial_end_email_scheduler.send_trial_end_emails()`(`all_internal_ids()`経由) | 日次 | 1 |
| `cloud_function_send_deletion_confirmations.main()`→`deletion_candidate.list_deletion_candidates()`(`all_internal_ids()`経由、フェーズ163で索引#3へのクエリ統合を設計済みだが実Firestore接続までは`InMemoryFleetOperatorStore`前提の全件列挙のまま) | 日次(deletion-candidate-design.md 78行目) | 1 |

日次バッチ2箇所で、`fleet_operator`総ドキュメント数(=N、総登録事業者数)に対して
**2N回/日**の読み取りが発生する。aircon-pasha(4N回/日、LINE Messaging系の追加バッチを
複数持つ)より全件走査箇所が少ない点が本venture固有の違いである。

## 2. 無料枠予算との照合

aircon-pashaフェーズ323と同じ保守的な配分方針を踏襲する。

- Firestore Sparkプラン(無料枠): 読み取り50,000回/日。
- `usage_counter`操作(生成1回あたり読み取り1回)・Webフォーム提出時の`vehicle`単発検索
  (索引#1)等、ユーザー操作に比例するその場読み取りが同じ無料枠を共有する。
- 保守的に、日次バッチの全件走査には無料枠50,000回の**半分(25,000回/日)**までを上限として
  割り当て、残り半分をその場読み取りに残す方針とする(aircon-pashaフェーズ323と同じ配分)。

## 3. 決定

**`fleet_operator`の総ドキュメント数(総登録事業者数)Nが10,000を超えた時点で、日次バッチ
2箇所(`trial_end_email_scheduler.py`・`cloud_function_send_deletion_confirmations.py`)の
全件走査を、各バッチが本来必要とする条件に対応する索引付きクエリ(firestore-composite-
index-plan.md #2〜#3)への切り替えを検討するトリガーとする。**

根拠: 25,000回/日(2節の割り当て上限) ÷ 2(日次バッチの全件走査回数) = 12,500。aircon-pasha
フェーズ323と同じ考え方(安全マージンを取り、計算結果より小さいキリのよい数値を採用)で
10,000を採用する。

## 4. 残課題・次回候補

- N=10,000という閾値は、2節の「半分を日次バッチに割り当てる」配分自体が机上の保守的な
  仮定であり、実Firestore接続後の実測読み取り件数を踏まえた再検証が必要(aircon-pasha
  フェーズ323と同じ留保)。
- 承認待ち事項(実Stripeアカウント・Firestore/GCPプロジェクト等、pending-approval.md
  2026-10-06 22:00 UTC・2026-10-10 18:00 UTC記載)がオーナーから承認された場合は、
  N=10,000到達前でも実測データに基づく再検証を優先する。
- 本決定によりfirestore-composite-index-plan.md「残る課題」の該当項目(57〜58行目)を
  解消済みとして同ファイルに反映する。
