# Firestoreデータモデル設計(フェーズ36)

フェーズ35の次回候補(1)「`fan_pass/{internal_id}`(名称一本化含む)コレクション定義の新規
作成」に対応する。monthly-pass-identity-design.md(フェーズ7)・generation-count-design.md
(フェーズ8)・fan-pass-canceled-access-block-design.md(フェーズ35)の3文書がこれまで個別に
設計してきたフィールド・サブコレクションを、本ファイルで実コレクション定義として一箇所に
統合する。forklift-pasha/firestore-data-model.md・line-reservation-ai/firestore-data-model.md
の構成方針(ドキュメント単位にフィールド一覧をコメント付きで列挙する形式)を踏襲する。

## 0. コレクション名の一本化(フェーズ35の指摘事項への対応)

fan-pass-canceled-access-block-design.md「5. フィールド名の揺れに関する指摘」が記録した、
本venture内の表記揺れ(フェーズ7・8は`monthly_pass`、フェーズ34次回候補(2)は`fan_pass`)を
本フェーズで解消する。

- 本ファイル以降、コレクション名を**`fan_pass`**に一本化する(都度プランは識別子を持たない
  ためコレクション自体が存在せず、本venture内で永続化が必要なのは月額フリーパスのみである
  ため、プラン名ではなく「ファンの通行証」を意味する`fan_pass`の方が本venture全体の呼称
  〈おしえんパシャっと〉・ユーザー向け名称〈月額フリーパス〉のどちらとも矛盾しない)。
- フェーズ7(monthly-pass-identity-design.md)・フェーズ8(generation-count-design.md)の
  本文中の`monthly_pass/{internal_id}`という表記は、過去の設計判断の記録として原文を変更
  しない(他venture既存文書の慣例どおり、確定後の表記修正は新規ファイル側で行い旧文書は
  そのまま残す)。実装着手時のコレクション名は本ファイルの`fan_pass`を正とする。

## 1. コレクション構成

### 1.1 `fan_pass/{internal_id}`

月額フリーパス契約者単位の識別・課金・アクセス制御ドキュメント。ドキュメントIDはFirestore
自動生成の`internal_id`(不変、forklift-pasha/line-reservation-ai同様Stripe
`client_reference_id`に使用)。

```
{
  accessToken: "...",              // サーバー側ランダム発行。アクセスURL
                                    // (https://<ドメイン>/m/{accessToken})のパスパラメータ・
                                    // 単一フィールドクエリでのドキュメント特定に使用
                                    // (monthly-pass-identity-design.md 2節)。クロスデバイス
                                    // 再発行時は新しい値で上書きし旧トークンは即時失効
                                    // (同3節)
  email: "...",                    // Stripe Checkoutが標準収集する購入者メールアドレス。
                                    // クロスデバイス時のアクセスURL再送・識別子の再発行の
                                    // 際にStripe顧客検索のキーとして使うが、識別子そのもの
                                    // には使わない(同2節・3節)
  stripeCustomerId: "...",         // string。都度プランとは異なり月額フリーパスは
                                    // Checkout Session完了時に必ず発行される
  stripeSubscriptionId: "...",     // string。customer.subscription.*系Webhookの照合キー
  subscriptionStatus: "active",    // "active" | "canceled"。fan-pass-canceled-access-
                                    // block-design.md(フェーズ35)のページ表示分岐判定に
                                    // 使用する専用フィールド(他の判定より最優先、
                                    // aircon-pashaの判定パターンを踏襲)。トークンの
                                    // ライフサイクルとは分離し、解約後も`accessToken`自体は
                                    // 失効させない(monthly-pass-identity-design.md 4節)
  currentPeriodEnd: null,          // Timestamp | null。次回請求日の参考情報(本venture
                                    // は期間終了時解約〈cancel_at_period_end〉方式を
                                    // 採らず即時解約のため、課金可否の判定には使わず
                                    // 表示用の参考値に留める)
  currentMonthGenerationCount: 0,  // generation-count-design.md(フェーズ8)2節。当月の
                                    // generation_log件数の加算カウンタ。異常検知用の
                                    // 内部ログ目的(生成回数の上限判定には使わない、
                                    // 月額フリーパスは無制限)
  generationCountMonth: "2026-10" // "YYYY-MM"。course-set-pasha踏襲のリセット判定キー。
                                    // 当月文字列と不一致ならcurrentMonthGenerationCountを
                                    // 0にリセットしてから加算する(同2節)
}
```

### 1.2 `fan_pass/{internal_id}/generation_log/{auto_id}`

generation-count-design.md(フェーズ8)2節で設計したサブコレクション。1回の生成リクエスト
ごとに1ドキュメントを追記する(自動生成ID)。

```
{
  requestedAt: Timestamp,       // 生成要求時刻
  venueMatched: true,           // schema/output.schema.jsonのitinerary_draft.venue_matchedと
                                  // 同値
  inputPerformanceCount: 1      // 1回の入力に含まれた公演数(ハシゴ判定目的)
}
```

## 2. 都度プランに専用コレクションを持たない理由(再確認)

monthly-pass-identity-design.md「1. 前提の整理」のとおり、都度プラン(`mode=payment`)は
決済1回=利用1回で完結し横断的な識別が不要なため、`fan_pass`相当の永続ドキュメントを作らない。
都度プランのアクセスURLはevent-komiguai-pashaと同型の「一度限りアクセスURL(TTL付き)」方式
(monthly-pass-user-identification-design.md、フェーズ34)であり、本ファイルの対象外とする。

## 3. 他venture構成との対比

forklift-pasha(`fleet_operator`+`vehicle`+`usage_counter`の3コレクション)と異なり、本venture
は(a)点検記録本文に相当する永続データを持たない、(b)異常検知用ログが月次カウンタ上限判定
ではなく内部観測目的に留まる、という2点から`usage_counter`を独立コレクションとせず
`fan_pass`ドキュメント自身にカウンタフィールドを持たせる単純構成とした
(generation-count-design.md 2節の判断を踏襲)。

## 4. 未確定・残課題

- 本ファイルは机上のコレクション定義整理のみであり、実際のFirestoreプロジェクト作成・
  コレクションへのデプロイ自体はオーナー承認が必要なアクションに該当する
  (pending-approval.md既存の承認待ち事項〈GCPプロジェクト・Firestoreデータベース作成〉の
  範囲内で扱う。本フェーズで新規の承認依頼は発生しない)。
- `subscriptionStatus`の値遷移(`customer.subscription.deleted`→`canceled`、
  `customer.subscription.created`→`active`復帰)は設計済み(fan-pass-canceled-access-
  block-design.md 4節)だが、実コードでの読み書き(forklift-pashaの`upgradedAt`等の
  個別フィールド判定方式を採るか、本venture案のとおり専用フィールドのまま使うか)は
  prototypeコード着手時に確定する。
- クロスデバイス時のアクセスURL再発行フロー(monthly-pass-identity-design.md 3節)で
  `accessToken`を上書きする際、`generation_log`サブコレクションの参照キーは`internal_id`で
  一貫しているため影響を受けないことを確認した(forklift-pashaの`usage_counter`設計と
  同じ理由、1.2節参照)。
- venue-master-draft.mdの各会場アクセス情報精査・会場名表記揺れの名寄せ方法の検討は
  本フェーズの範囲外、未着手のまま持ち越し。

実LLM呼び出し・Stripe等決済代行サービスとの実接続、実際のGCPプロジェクト・Firestore
データベースの開設自体はオーナー承認が必要なアクションに該当するため、本メモは設計の
整理に留める(コード実装・外部サービスへの接続は一切行っていない)。

最終更新: 2026-10-31 14:00 UTC(フェーズ36: fan-pass-canceled-access-block-design.md
〈フェーズ35〉が指摘したコレクション名表記揺れ〈monthly_pass/fan_pass〉を`fan_pass`に
一本化し、monthly-pass-identity-design.md〈フェーズ7〉・generation-count-design.md
〈フェーズ8〉・fan-pass-canceled-access-block-design.md〈フェーズ35〉の3文書に分散していた
フィールド・サブコレクション設計を`fan_pass/{internal_id}`コレクション定義として統合した)
