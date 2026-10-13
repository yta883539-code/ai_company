# Firestore複合インデックス定義の集約(フェーズ150)

## 位置づけ

vehicle-label-duplicate-handling-design.md(フェーズ114)「6. 未確定・次回候補」に
フェーズ149まで残っていた「`(operatorInternalId, vehicleLabel)`の複合インデックス設計
(firestore-composite-index-plan相当の文書化)」に着手する。line-reservation-ai/
firestore-composite-index-plan.mdの構成方針(本venture全体に分散している複合インデックス
必要箇所を1ドキュメントに集約し、実際にデプロイ可能な`firestore.indexes.json`を先行して
書き出す)を踏襲する。GCPプロジェクト作成・Firestore有効化自体はオーナー承認待ちのため、
本フェーズではJSONの中身を確定するだけの机上作業に留まる。

## 集約した複合インデックス一覧

| # | 対象コレクション | クエリの用途 | フィールド(順序) | クエリスコープ | 出典 |
|---|---|---|---|---|---|
| 1 | `vehicle`(ルートコレクション) | `register_vehicle_from_inspection_memo()`(`prototype/vehicle_registry.py`): 点検メモ受信時に`operatorInternalId == X AND vehicleLabel == Y`の完全一致(トリムのみ正規化)で既存車両を検索 | `operatorInternalId` ASC, `vehicleLabel` ASC | Collection(`vehicle`はルートコレクションで、本venture固有のサブコレクション構造〈line-reservation-aiのような`stores/{storeId}/...`〉を持たないため通常スコープで足りる) | vehicle-label-duplicate-handling-design.md(フェーズ114)2節・4節 |
| 2 | `fleet_operator`(ルートコレクション) | 日次スケジューラ(`cloud_function_send_trial_end_emails.main()`、実体は`prototype/trial_end_email_scheduler.py`の`select_due_trial_end_emails()`): 全事業者から(B)期間到達経路の対象(`trialStartAt`から30日経過かつ`trialEndNotifiedAt`未設定)を抽出 | `trialStartAt` ASC, `trialEndNotifiedAt` ASC | Collection(`fleet_operator`もルートコレクションのため通常スコープで全事業者を横断できる) | trial-end-notification-design.md(フェーズ119)1節「(B)期間到達」・prototype/trial_end_email_scheduler.py |

補足:

- 本ventureは双方向の会話状態管理を持たない単方向バッチ処理(tech-stack.md「全体構成
  イメージ」)であり、`fleet_operator`・`vehicle`・`usage_counter`のいずれもルート
  コレクション構成(firestore-data-model.md「設計方針」)のため、line-reservation-aiの
  索引#1・#2・#5のような**collection group**スコープは本ventureでは不要。両索引とも
  通常の`Collection`スコープで足りる点が、line-reservation-ai向けに書いた補足と異なる
  (`queryScope`は`COLLECTION`のまま、`"COLLECTION_GROUP"`への変更は不要)。
- #1は現状の`prototype/vehicle_registry.py`(`InMemoryVehicleStore`)では単純な線形探索で
  代替しているため、既存テスト18件はいずれも索引の有無に関わらずパスする。実Firestore接続
  後、`InMemoryVehicleStore`相当のFirestoreアダプタ実装時に本索引が必要になる想定。
- #2についても、現状の`prototype/trial_end_email_scheduler.py`は`all_internal_ids()`で
  全事業者を列挙してから`select_due_trial_end_emails()`でインメモリ判定する実装
  (README.mdフェーズ続き記載、`InMemoryFleetOperatorStore`前提)であり、実Firestore接続後に
  規模が大きくなった場合のみ、インメモリ全件走査から本索引を使ったクエリへの切り替えが
  望ましくなる(事業者数が少ない段階では全件取得でも機能上の問題はない)。
- `usage_counter`コレクションは`internal_id`単一キーでのドキュメント取得のみ(複合クエリは
  発生しない、firestore-data-model.md「3. `usage_counter/{internal_id}`」)ため対象外。

## 生成した`firestore.indexes.json`

上記1〜2を`gcloud firestore indexes composite create`相当の宣言的定義として
`firestore.indexes.json`(venture直下)に書き出した。実際の`gcloud firestore deploy
--only firestore:indexes`実行は、GCPプロジェクト作成・Firestore有効化(オーナー承認待ち)
の後に行う。

## 残る課題

- 本表の各インデックスが実際にFirestoreコンソールの「クエリ実行時エラーからの自動提案」と
  一致するかは、実Firestore接続後(オーナー承認待ち)の検証課題として残る。
- #2について、インメモリ全件走査から索引付きクエリへの切り替えタイミング(事業者数の
  閾値等)は未確定のまま次回以降の課題とする。
- firestore-data-model.mdのフィールド一覧(`fleet_operator`)に`trialEndNotifiedAt`が
  未反映であることに気づいた(trial-end-notification-design.md・prototype/trial_management.py
  では既に実装済みだが、データモデル文書側のフィールド表には追記されていなかった)。
  本フェーズの対象外のため次回候補として残す(firestore-data-model.md自体の更新が必要)。

最終更新: 2026-10-13 15:00 UTC(フェーズ150: vehicle-label-duplicate-handling-design.md
〈フェーズ114〉に残っていた複合インデックス設計課題に対応し、本venture全体で必要な
複合インデックス2件〈`vehicle`・`fleet_operator`〉を集約・`firestore.indexes.json`として
書き出した。コード変更なし、文書・JSON作成のみのため回帰テストの実行対象外)
