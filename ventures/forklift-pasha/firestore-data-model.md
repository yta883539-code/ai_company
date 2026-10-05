# Firestoreデータモデル設計(フェーズ11)

tech-stack.md(フェーズ10)「コンポーネント4」で初回設計のみに留めていた課金・契約単位の
データストア(Firestore)を、実ファイルとして切り出し確定する。line-reservation-ai/
firestore-data-model.mdの構成方針(店舗単位ドキュメントに課金フィールドを直接持たせる単純
構造)を参考にしつつ、本ventureはkura-pashaのような複数ユーザー共同利用構造ではなく
「1事業者(operator)=1契約」であるため、より単純な2コレクション構成とする。

## 設計方針

- 本ventureは双方向の会話状態管理が不要な単方向バッチ処理(tech-stack.md「全体構成イメージ」)
  のため、line-reservation-aiのような予約スロット・会話状態等の複雑なコレクションは不要。
  課金・契約単位の最小限の状態保持のみを設計対象とする。
- pricing-plan.mdの課金軸が「保有台数」であるため、プラン変更時に保有台数の変更を伴う
  (course-set-pashaの「生成回数」主軸よりもaircon-pashaの「屋号単位・複数台保有」構造に近い)。
- 点検記録そのもの(inspection_record、schema/output.schema.json参照)は、他「パシャッと」
  シリーズと同様に点検担当者への返却(整形済みテキストの返却)のみを目的とし、恒久的な
  記録原本の保管義務は事業者側の運用(スプレッドシート等への貼り付け)に委ねる方針
  (mvp-flow-draft.md「範囲外」)のため、Firestore側には点検記録本文の永続化は行わない。

## コレクション構成

### 1. `fleet_operator/{operator_id}`

事業者(倉庫業・運送業・建設業事業者)単位の契約・課金ドキュメント。

```
{
  planId: "light" | "standard" | "multi",   // pricing-plan.mdの3プラン(ライト/スタンダード/複数台)
  vehicleCount: 1,                           // 保有台数(プラン上限チェック用、台数超過時はプラン
                                              // 変更を促す導線に使う。実際のアップセル導線設計は
                                              // 次回候補)
  stripeCustomerId: null,                    // string | null。未契約(トライアル中含む)はnull
  subscriptionStatus: "trialing",            // "trialing" | "active" | "past_due" | "canceled"
  trialStartAt: null,                        // Timestamp | null。pricing-plan.md「無料トライアル
                                              // 条件」の起算点(初回生成時に1回だけ設定、以降不変)
  currentPeriodEnd: null                     // Timestamp | null。次回請求日・トライアル終了予定日
                                              // の判定に使用
}
```

### 2. `vehicle/{vehicle_id}`

点検記録の車両単位マスタ。点検記録本文自体は保持せず、識別情報のみを持つ最小限の構成。

```
{
  operatorId: "...",   // fleet_operator/{operator_id}への参照
  vehicleLabel: "2号機" // 入力メモの車両番号表記をそのまま保持(表記ゆらぎの解決は範囲外、
                        // mvp-flow-draft.md「点検結果の良否判断・修理要否の判断はしない」と
                        // 同じく「入力をそのまま扱う」方針を識別情報にも適用)
}
```

### 3. `usage_counter/{operator_id}`

月間生成回数の積算カウンタ。kura-pasha/usage-counter-workshop-key-design.mdと同様、プラン間で
カウンタ参照ロジックを分岐させずoperator_idキーで一貫させる。

```
{
  month: "2026-10",  // "YYYY-MM"
  count: 0           // pricing-plan.mdの課金単位「1メモ送信=1回(daily/monthly/annual問わず
                      // 一律1回)」に対応する積算値。月初にcountをリセットする設計
                      // (他venture同様、繰越なし)
}
```

## 未確定・残課題

- `fleet_operator`のドキュメントIDの割り振り方は、tech-stack.md(フェーズ70)で入力
  チャネルを汎用Webフォーム(LINE非依存)に暫定決定したことを受け、**メールアドレス
  (またはフォーム入力時に発行するランダムなoperator_id)を軸とする方式を第一候補**とする
  (LINE前提のuserId方式は採用しない)。本モデルは元々入力チャネルに依存しない抽象的な
  operator_idを前提にしていたため、スキーマ自体の変更は不要。
- `vehicle_id`の発行・重複チェック(同一事業者内で車両番号表記が重複した場合の扱い)は
  実装時の課題として残す。
- 実際のGCPプロジェクト作成・Firestore有効化はアカウント作成に該当するため、着手時に
  オーナー承認が必要(pending-approval.md参照)。本ファイルは机上のスキーマ整理のみ。

最終更新: 2026-10-05 22:00 UTC(フェーズ70: tech-stack.mdの入力チャネル暫定決定〈汎用Web
フォーム〉を受け、operator_idの割り振り方針をメールアドレス/発行式に具体化)
