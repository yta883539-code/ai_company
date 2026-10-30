# 会場マスタの内部データ構造設計(last_verified_dateフィールドの反映)

venue-alias-verification-and-naming-rights-risk.md 次回候補(4)「`last_verified_date`
フィールドを含めたschema/output.schema.json側(内部的な会場マスタデータ構造、ユーザー向け
出力スキーマとは別)への反映方法の検討」に対応する。

## 前提の整理

- `schema/output.schema.json`はLLMが生成するユーザー向け出力(itinerary_draft等)の構造を
  定義するものであり、`venue_matched`等の判定結果を受け取る側のスキーマである。
- 一方、venue-master-draft.md(東京圏・大阪圏・名古屋圏の会場名・最寄り駅・徒歩目安の
  Markdown表)は、その判定の元になる参照データであり、現段階ではコード化・JSON化されて
  いない静的メモに留まっている(venue-master-draft.md既出の検討課題)。
- `last_verified_date`は後者(内部参照データ)に属するフィールドであり、
  `schema/output.schema.json`本体を変更する対象ではない。この区別を明確にすることが
  本フェーズの前提整理である。

## 内部会場マスタのJSON構造案(草案)

venue-master-draft.mdのMarkdown表をJSON化する際の構造案として、以下を設計した(実装は
tech-stack.md記載のCloud Run静的アセット同梱方針に沿って行う想定、本フェーズではコード化・
ファイル生成は行わない)。

```json
{
  "venues": [
    {
      "canonical_name": "バンテリンドーム ナゴヤ",
      "aliases": ["ナゴヤドーム"],
      "region": "名古屋圏",
      "nearest_station": "地下鉄 ナゴヤドーム前矢田駅",
      "walk_minutes_note": "徒歩3分前後",
      "naming_rights": true,
      "last_verified_date": "2026-10-29",
      "naming_rights_review_due": "2027-10-29"
    },
    {
      "canonical_name": "東京ドーム",
      "aliases": [],
      "region": "東京圏",
      "nearest_station": "JR/地下鉄 水道橋駅、後楽園駅",
      "walk_minutes_note": "徒歩5分前後",
      "naming_rights": false,
      "last_verified_date": "2026-10-29",
      "naming_rights_review_due": null
    }
  ]
}
```

## 設計判断

1. `last_verified_date`は会場単位(レコード単位)で持たせる。venue-master-draft.md全体を
   一括更新しても個々の会場の裏取り時期はずれる可能性があるため、一覧単位ではなく
   レコード単位での管理を採用する。
2. `naming_rights`(boolean)を新設し、命名権契約による名称の会場かどうかを明示する。
   venue-alias-verification-and-naming-rights-risk.mdが指摘した「ネーミングライツ会場は
   3〜5年周期で改称されうる」リスクに対応し、`naming_rights=true`の会場のみ
   `naming_rights_review_due`(年1回の再裏取り運用ルールに対応する期日)を設定する方針とした。
   命名権のない会場(東京ドーム等、開業時からの名称を使用)は`naming_rights_review_due`を
   nullとし、不要な再裏取り運用負荷を避ける。
3. `aliases`は配列とし、venue-name-normalization-design.mdの段階的マッチング方針
   (完全一致→エイリアス辞書一致→部分一致→非該当)のうち「エイリアス辞書一致」段階で
   このフィールドを参照する想定とした。
4. `naming_rights_review_due`が過去日付になったレコードをどう扱うか(当日ファン向け応答を
   止めるか、留保付きで案内を続けるか)は、実運用データ・再裏取り体制が整うまで確定できない
   ため、次回以降の課題として残す。
5. 本構造案はあくまで設計レベルのドラフトであり、実際のJSONファイル生成・Cloud Runへの
   アセット同梱・schema/output.schema.jsonとの結合(`itinerary_draft.venue_matched`判定ロジック
   側でこのJSONを参照する実装)は、venture全体の実装着手(オーナー承認後)の際に行う。

コード実装・外部サービス接続は一切行っていない。承認が必要なアクション(支払い・
アカウント作成・外部公開・送信等)は本フェーズでは発生していないためpending-approval.mdへの
新規追記は不要(既存の承認待ち事項の範囲内で扱う)。

## 次回候補

1. エディオンアリーナ大阪の2023年9月以降の命名権契約状況の再確認(契約満了後に再延長された
   か、契約終了により別の愛称・旧名称に回帰したかの最新裏取り)。
2. 異常検知の閾値・対応方針の検討(実利用データ観察後、generation-count-design.md既出の課題)。
3. 都度プラン⇔月額フリーパスのプラン変更時の課金面(残存クレジット等)の扱いの検討
   (plan-change-billing-design.mdで一次結論済みだが、短期間内の連続プラン切替時の初回割引は
   未決のまま残っている)。
4. `naming_rights_review_due`が過去日付になった場合の実運用での扱い(実利用データ観察後)。
