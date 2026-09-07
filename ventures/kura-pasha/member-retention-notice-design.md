# 猶予期間中の「残すメンバー」連絡導線 設計

downgrade-excess-member-handling-design.md(フェーズ28)「4. 未検証・残課題」1点目、
すなわち複数職人プランからライト/スタンダードプランへダウングレードした際の猶予期間中
(ダウングレード確定〜`pending_member_reduction_effective_at`まで)に、契約者が
「継続してご利用いただくメンバーを1名選んでご連絡ください」という案内(同設計書
「3. 確定する設計」2点目)に応えて実際に連絡してくる場面のLINE上での意図検知文言・
schema拡張を検討する。

## 1. 前提の整理

- downgrade-excess-member-handling-design.md「3. 確定する設計」で確定した通り、猶予期間の
  デフォルトルールは「契約者(`contractor_user_id`)のみを残し、他の`member_user_ids`は
  全員解除する」である。契約者からの連絡は、このデフォルトルールを上書きしたい場合の
  任意入力(契約者自身を残しつつ、加えてもう1名程度を明示したいケースは本venture未対応。
  同設計書2節選択肢2の通りプラン上限は1名のため、契約者からの指定があっても最終的に
  残せるのは1名のみ)。
- 本メッセージは通常の受注メモ入力(区分・型・革の種類等)とは全く異なる文面パターンで
  あり、他venture(course-set-pasha)の解約/ダウングレード意図検知(厳守事項7a)と
  同様、LLMのstatus分岐で検知する方式を踏襲する。

## 2. 検知パターンの整理

契約者からのメッセージのうち、以下のいずれかに該当するものを「残すメンバー連絡」関連
として扱う。

1. **明確な指定**: 「◯◯さんを残してください」「継続は◯◯でお願いします」等、
   残したい相手が名前・呼称で特定できる表現。
2. **不明確**: 「メンバーの件ですが」「さっきの連絡について」等、残すメンバーの話題には
   触れているが、誰を残すか特定できない表現。この場合は厳守事項7a(iv)相当の
   意思確認一言(「どなたを継続利用としてご希望か、お名前をお知らせください」)のみを
   返し、機械的な指定確定は行わない。

なお、本メッセージがそもそも猶予期間中の契約(`pending_member_reduction_effective_at`
設定済み)から送られてきたものかどうかは、LLM呼び出し前にアプリケーション側で
`craftsman_workshop/{workshop_id}.pending_member_reduction_effective_at`の有無を
確認した上でLLMへ渡すプロンプト文脈に含める想定とする(course-set-pashaの
webhook-event-dispatch-design.md同様、状態に応じた文脈埋め込みは呼び出し元の責務とし、
schema自体はLLM出力形式の定義に留める)。猶予期間外の契約からのメンバー名らしき発言は
`out_of_scope`として扱う(厳守事項6の対象外業務)。

## 3. schema拡張

course-set-pashaの解約意図検知パターン踏襲(フェーズ24)と同様、`status`のenumへ
以下2値を追加する。

- `member_retention_selection`: 上記1(明確な指定)に該当。
- `member_retention_unclear`: 上記2(不明確)に該当。

新規フィールド`member_retention_notice`(トップレベル、他フィールドと同様に常に出力
必須・値としてnullを許容)を追加する。

```json
{
  "kind": "member_retention_selection | member_retention_unclear",
  "specified_member_name": "string | null",
  "body": "string"
}
```

- `kind`: statusと1:1対応(subscription_procedure_notice.kindと同じ設計思想、
  body生成ロジック側の分岐補助用)。
- `specified_member_name`: kind=member_retention_selectionのときのみ非null。
  入力メッセージから抽出した名前・呼称をそのまま転記する(LLMによる本人確認・
  workshop内メンバーとの突き合わせは行わない。突き合わせはアプリケーション側の
  責務とし、`member_user_ids`に紐づくLINE表示名等との一致判定はここでは扱わない
  次の課題とする)。kind=member_retention_unclearのときは必ずnull。
- `body`: kind=member_retention_selectionのときは「◯◯様を継続利用メンバーとして
  承りました。◯月◯日の切り替え時に反映いたします」相当の受付確認文言
  (この時点ではまだ`member_user_ids`は変更しない。downgrade-excess-member-handling-
  design.md「3. 確定する設計」の通り、実際の反映は次回生成リクエスト受信時の
  都度チェックで行う。本フィールドは受付確認のみを担う)。kind=
  member_retention_unclearのときは上記2.で定めた意思確認一言のみ。

`status`が上記2値以外のときは`member_retention_notice`は必ずnull
(他フィールドと同様、コード側検証で担保する)。

## 4. 未検証・残課題

- `specified_member_name`と`craftsman_workshop/{workshop_id}.member_user_ids`
  (実際にはLINE表示名の突き合わせが必要なため、`member_user_ids`だけでなく
  表示名を保持する別フィールドが必要になる可能性がある)との突き合わせロジックは
  本ファイルでは扱わず、prototype拡張時の次の課題とする。
- 「契約者から連絡があった場合の`member_user_ids`縮小ロジック」自体(受付確認後、
  次回請求サイクル開始時点でその指定を反映する都度チェック処理)は
  `pending_member_reduction_effective_at`の都度チェック実装
  (downgrade-excess-member-handling-design.md残課題)側でまとめて扱う。
- 猶予期間外からの同種メッセージをout_of_scope扱いとする方針の妥当性(むしろ
  insufficient_inputや別の案内が適切な可能性)は実運用データが無いため未検証。
- 実際のLINE公式アカウント接続・実LLM検証は未着手(オーナー承認待ちの範囲、
  pending-approval.md参照)。

最終更新: 2026-09-07 13:02 UTC
