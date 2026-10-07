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

### 1. `fleet_operator/{internal_id}`

事業者(倉庫業・運送業・建設業事業者)単位の契約・課金ドキュメント。ドキュメントIDは
Firestore自動生成の`internal_id`(不変、Stripe`client_reference_id`に使用。
access-token-reissue-design.md「1. 前提の見直し」参照)。

```
{
  accessToken: "...",                        // サーバー側ランダム発行、アクセスURL
                                              // (https://<ドメイン>/f/{accessToken})の
                                              // パスパラメータ・単一フィールドクエリでの
                                              // ドキュメント特定に使用。再発行可能
                                              // (access-token-reissue-design.md「2. 再発行
                                              // フローの設計」)
  email: "...",                              // 配布先の連絡手段。識別子としては使わない
  planId: "light" | "standard" | "multi",   // pricing-plan.mdの3プラン(ライト/スタンダード/複数台)
  vehicleCount: 1,                           // 保有台数(プラン上限チェック用、台数超過時はプラン
                                              // 変更を促す導線に使う。実際のアップセル導線設計は
                                              // 次回候補)
  stripeCustomerId: null,                    // string | null。未契約(トライアル中含む)はnull
  subscriptionStatus: "trialing",            // "trialing" | "active" | "past_due" | "canceled"
  trialStartAt: null,                        // Timestamp | null。pricing-plan.md「無料トライアル
                                              // 条件」の起算点(初回生成時に1回だけ設定、以降不変)
  currentPeriodEnd: null,                    // Timestamp | null。次回請求日・トライアル終了予定日
                                              // の判定に使用
  lastAccessedAt: null                       // Timestamp | null。アクセスURL
                                              // (https://<ドメイン>/f/{accessToken})経由で
                                              // 設定ページが開かれた直近の日時。本人が
                                              // トークン漏洩等の異常なアクセスパターンに気づく
                                              // 手がかりとして設定ページ上に表示する
                                              // (access-token-reissue-design.md「6.」参照)。
                                              // 初回アクセス前はnull
}
```

### 2. `vehicle/{vehicle_id}`

点検記録の車両単位マスタ。点検記録本文自体は保持せず、識別情報のみを持つ最小限の構成。

```
{
  operatorInternalId: "...",   // fleet_operator/{internal_id}への参照(旧operatorId。
                                // access-token-reissue-design.mdのID分離に合わせて
                                // 参照先をinternal_idに読み替え)
  vehicleLabel: "2号機" // 入力メモの車両番号表記をそのまま保持(表記ゆらぎの解決は範囲外、
                        // mvp-flow-draft.md「点検結果の良否判断・修理要否の判断はしない」と
                        // 同じく「入力をそのまま扱う」方針を識別情報にも適用)
}
```

### 3. `usage_counter/{internal_id}`

月間生成回数の積算カウンタ。kura-pasha/usage-counter-workshop-key-design.mdと同様、プラン間で
カウンタ参照ロジックを分岐させず`fleet_operator`と同じ`internal_id`キーで一貫させる
(`accessToken`は再発行で値が変わるため、カウンタのキーには使わない)。

```
{
  month: "2026-10",  // "YYYY-MM"
  count: 0           // pricing-plan.mdの課金単位「1メモ送信=1回(daily/monthly/annual問わず
                      // 一律1回)」に対応する積算値。月初にcountをリセットする設計
                      // (他venture同様、繰越なし)
}
```

## 未確定・残課題

- (解消済み 2026-10-06 23:00 UTC・フェーズ95: `fleet_operator`のドキュメントID
  `operator_id`の割り振り方は、payment-identity-verification-design.mdで**サーバー側が
  発行するランダムなアクセストークン方式に確定**した。メールアドレスは`email`フィールドに
  連絡手段として保持するが、識別子そのものには使わない(第三者が他人のメールアドレスを
  入力してCheckout Sessionを起票できてしまうなりすましリスクを避けるため)。LINE前提の
  userId方式は採用しない。本モデルは元々入力チャネルに依存しない抽象的なoperator_idを
  前提にしていたため、スキーマ自体の変更は不要。)
- (解消済み 2026-10-07 02:00 UTC・フェーズ97: 2026-10-07 01:00 UTC・フェーズ96で判明した
  ドキュメントID(`internal_id`)とユーザー配布用アクセストークン(`accessToken`フィールド)の
  分離を、本ファイルのコレクション定義に反映した。`fleet_operator`のドキュメントIDを
  `{operator_id}`から`{internal_id}`に変更し`accessToken`・`email`フィールドを追加、
  `vehicle`コレクションの参照フィールドを`operatorId`から`operatorInternalId`に変更、
  `usage_counter`のキーを`{operator_id}`から`{internal_id}`に変更した。)
- `vehicle_id`の発行・重複チェック(同一事業者内で車両番号表記が重複した場合の扱い)は
  実装時の課題として残す。
- 実際のGCPプロジェクト作成・Firestore有効化はアカウント作成に該当するため、着手時に
  オーナー承認が必要(pending-approval.md参照)。本ファイルは机上のスキーマ整理のみ。
- (解消済み 2026-10-07 04:00 UTC・フェーズ99: access-token-reissue-design.md〈フェーズ98〉
  次回候補の`lastAccessedAt`フィールドを`fleet_operator`に追加した。更新タイミング・
  設定ページでの表示方針はaccess-token-reissue-design.md「6.」参照。)

最終更新: 2026-10-05 22:00 UTC(フェーズ70: tech-stack.mdの入力チャネル暫定決定〈汎用Web
フォーム〉を受け、operator_idの割り振り方針をメールアドレス/発行式に具体化)
最終更新: 2026-10-06 23:00 UTC(フェーズ95: payment-identity-verification-design.mdの
決済時本人確認方式の検討を受け、operator_idの割り振り方針をランダム発行〈アクセス
トークン〉方式に確定)
最終更新: 2026-10-07 02:00 UTC(フェーズ97: access-token-reissue-design.md〈フェーズ96〉の
internal_id/accessToken分離を実ファイルに反映。`fleet_operator`のドキュメントIDを
`internal_id`に変更し`accessToken`・`email`フィールドを追加、`vehicle`の参照フィールドを
`operatorInternalId`に変更、`usage_counter`のキーを`internal_id`に変更)
最終更新: 2026-10-07 04:00 UTC(フェーズ99: access-token-reissue-design.md〈フェーズ98〉
次回候補の`lastAccessedAt`フィールドを`fleet_operator`に追加した)
