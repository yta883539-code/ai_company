# トライアル開始起点(初回生成時)の確定

作成日: 2026-08-27(フェーズ130)

trial-end-notification-design.md(フェーズ129)2節(B)で「course-set-pashaフェーズ100の
結論をそのまま仮置きし、本venture固有の再検討は不要と判断した」としていたが、6節「今後の
課題」1点目で「本venture固有のユーザー動線(フォーム提出→LINE連携→初回生成)に照らして
再確認する必要がある」と留保していた点に対応し、本venture専用の確定ドキュメントとして
起点を正式に確定する。

## 1. 結論: 起点は「初回生成成功時」とする(course-set-pashaと同じ結論)

course-set-pashaのtrial-start-anchor-decision.md(フェーズ100)と同じく、「初回follow時」
ではなく「初回生成成功時」(first-generation-self-check-design.mdが既に`usage_counter`に
`first_generation_notice_sent`として記録している、そのユーザーにとって生涯最初の生成成功
時点)を14日間トライアルの起点として確定する。

## 2. 本venture固有のユーザー動線での再確認

6節の留保に対応し、本venture固有のユーザー動線に照らして結論が変わらないことを個別に確認する。

- 本ventureのユーザー動線は「フォーム提出→LINE連携→初回生成」であり、course-set-pashaの
  「follow→フォーム提出」動線とは順序が異なる(本ventureはフォーム提出が先、course-set-pasha
  はfollowが先)。ただし、いずれの順序であっても「連携コード解決(user_id紐付け)が完了する
  までサービスを一切利用できない」という性質自体は共通しており、動線の順序差はfollow時点
  基準の不公平さ(本人のタイミング次第で利用可能日数が目減りする)という課題の有無を左右
  しない。
- 本venture固有の利用パターンとして、pricing-plan.mdの想定利用量(月60〜100件、繁忙期は
  さらに増加)がある。1件の訪問施工完了ごとに1回生成する運用のため、初回生成は「フォーム
  提出・LINE連携完了後、最初の訪問施工が完了した時点」で発生する。この間隔(連携完了〜
  最初の施工完了)は業者の稼働スケジュール次第で不確定だが、この不確定性はcourse-set-pasha
  の「follow〜フォーム提出」の不確定性と同種であり、「実際に価値(作業完了報告・お手入れ
  案内下書き)を受け取った瞬間」を起点にすることで同様に解消される。
- 生成回数条件(pricing-plan.mdの二重条件のうち「生成10回到達」)は初回生成成功時点を
  カウント開始(`trial_generation_count`相当、6節参照)とする起点と自然に整合する。仮に
  フォーム提出時・LINE連携完了時を起点にすると、「期間は連携完了基準・回数は初回生成基準」
  で2つの条件が別々の起点を持つねじれが生じる点もcourse-set-pashaと同じ。
- 結論: 本venture固有の動線差(フォーム提出とfollowの順序)は起点選択の結論に影響せず、
  「初回生成成功時」で確定する。

## 3. usage_counterドキュメントへのフィールド追加

trial-end-notification-design.md 5節で想定していた`trial_start_at`を、`first-generation-
self-check-design.md`記載の`usage_counter/{user_id}`に以下の通り確定する。

```
usage_counter/{user_id}
  month: string
  count: number
  first_generation_notice_sent: bool
  trial_start_at: timestamp | null   # 新規追加。初回生成成功時に1回だけ設定、以降不変
```

- 書き込みタイミングは`first_generation_notice_sent`と同じ「初回生成成功時
  (`is_first_generation`が真の分岐)」とし、同一書き込みに相乗りさせる(実Firestore接続時、
  単一ドキュメント更新の原子性を保つため。course-set-pashaフェーズ100と同じ方針)。
- `trial_start_at`が`null`のまま(=初回生成がまだ行われていない)ユーザーに対しては、
  trial-end-notification-design.md 2節(B)の期間到達判定用スケジューラは判定対象外とする。

**実装時の変更点(2026-08-28追記、フェーズ134・136):** 実際にコード化する段階で、
`trial_start_at`の格納先は本節が想定した`usage_counter/{user_id}`ではなく
`user_profile/{user_id}`(user_id_linking.pyの`UserProfile`)に変更した。本venture固有の
事情として、`UserProfileStoreProtocol`が既にtrial-end-scheduler-design.md向けの
`trial_end_notified_at`・`upgraded_at`という同種の「一度だけ書き込む」フィールドを
直接保持する設計を採用済み(フェーズ134)であり、`trial_start_at`だけを別ドキュメント
(`usage_counter`)に切り離す理由が無いと判断したため。`first_generation_notice_sent`
フィールドの新設も同じ理由で見送り、`trial_start_at is None`をそのままセルフチェック
案内の要否判定に兼用している(first-generation-self-check-design.md「残課題」参照)。
5節「今後の課題」1点目のとおり書き込みロジック自体はフェーズ136で実装済み。

## 4. pricing-plan.md・trial-end-notification-design.mdへの反映

- pricing-plan.md「無料トライアル条件(仮)」の「期間: 導入から14日間」を、「期間: 初回の
  作業完了報告生成成功から14日間」に表現を確定する(下記の通り本ドキュメント作成と同時に
  反映)。
- trial-end-notification-design.md 2節(B)の「本venture固有の留意点として...暫定的に
  『初回生成成功時』を起点とする前提を本ドキュメントで仮置きする」は、本ドキュメントによる
  正式確定を受けて「仮置き」の表現を削除する(下記の通り反映)。

## 5. 今後の課題

- (解消済み 2026-08-28 03:00 UTC・フェーズ136: `trial_start_at`の実書き込みロジックを
  `cloud_function_webhook.py`の`process_memo_event()`に実装した。格納先は3節末尾の
  「実装時の変更点」の通り`user_profile`に変更している。テスト5件追加、venture全体211件
  全件パス。)
- (B)期間到達判定用の日次スケジューラ本体は、line-reservation-ai/reminder-scheduler-design.md
  やcourse-set-pasha/trial-end-scheduler-design.mdを参考に別途設計する必要があり、引き続き
  未着手。
- trial-end-notification-design.md 6節に残る「浮いた作業時間の目安」試算値未作成・決済導線
  未設計・`prototype/`未実装は、本ドキュメントの範囲外として引き続き残る。
- 実際のCloud Scheduler実行環境の構築・LIFF等の外部サービス接続はオーナー承認待ち
  (pending-approval.md参照)。
