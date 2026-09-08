# 契約者譲渡: 再確認応答の検知プロンプト設計(フェーズ36)

作成日: 2026-09-08(フェーズ36)

## 背景・対応する残課題

contractor-transfer-design.md(フェーズ33)で確定した2段階確定方式のうち、1段階目
(契約者からの譲渡意図検知→名指し一致判定→確認文言下書き生成)はフェーズ34(schema
拡張)・フェーズ35(prototypeコード化)で実装済みだが、2段階目「契約者からの再確認応答
(『はい』等の自由記述)をどう検知するか」の具体的なプロンプト設計は同ファイル4節の
残課題として未着手のまま残っていた。本ファイルで設計する。

## 1. 状態管理: pending_contractor_transfer

member-retention-notice-design.md・downgrade-excess-member-handling-design.mdで
確立した「一時状態はLLM側ではなくアプリケーション側で保持する」という既存方針を踏襲する。

`craftsman_workshop/{workshop_id}.pending_contractor_transfer`:

```json
{
  "candidate_user_id": "string",
  "candidate_member_name": "string",
  "requested_at": "timestamp",
  "expires_at": "timestamp"
}
```

- `status=contractor_transfer_selection`の確認文言生成(フェーズ33の1段階目)と同時に、
  アプリケーション側でこの一時状態を書き込む。
- 確定処理(`apply_contractor_transfer`)実行時、またはキャンセル時、または期限切れ時に
  この一時状態を削除する。
- `expires_at`は`requested_at`+24時間とする。member-retention-notice-design.mdの猶予
  期間(次回請求サイクルまで、数週間単位)とは性質が異なる短期の操作待ち状態であり、
  line-reservation-aiのBookingSlotManagerのholdタイムアウト(5分)よりは長いが、本
  venture固有の受注頻度の低さ(即応性を求めない業態)を踏まえた暫定値とする。

## 2. LLM呼び出し前のコンテキスト注入

アプリケーション側で、メッセージ送信者(`user_id`)が`contractor_user_id`と一致し、かつ
`pending_contractor_transfer`が存在し`expires_at`以内である場合に限り、「契約者交代の
確認待ち(候補: `{candidate_member_name}`)」という文脈をプロンプトへ埋め込んだ上でLLMを
呼び出す。この文脈が無い場合は通常のメッセージ(受注メモ・解約意図・残すメンバー連絡等)
と同じ判定ルールを適用し、3節の3パターンの判定対象にはしない(既存の厳守事項6〈対象外
業務〉・7a等はそのまま維持される)。

## 3. 検知パターン・schema拡張

course-set-pashaの解約意図検知、および本venture既存のmember_retention検知と同型の
パターンで、契約者からの自由記述の返信を3パターンに分類する。

1. **肯定**: 「はい」「お願いします」「それで良いです」「進めてください」等、交代を
   承認する意思が明確な表現。
2. **否定**: 「やめます」「やっぱりキャンセルで」「取り消してください」等、交代を
   取りやめる意思が明確な表現。
3. **不明瞭**: 上記いずれにも該当しない表現(話題を変えた、無関係な質問を返してきた等)。

`status`のenumへ以下3値を追加する。

- `contractor_transfer_confirmed`: 上記1(肯定)に該当。
- `contractor_transfer_cancelled`: 上記2(否定)に該当。
- `contractor_transfer_reconfirm_unclear`: 上記3(不明瞭)に該当。

新規フィールド`contractor_transfer_confirmation`(トップレベル、他フィールドと同様に
常時出力必須・nullを許容)を追加する。

```json
{
  "kind": "contractor_transfer_confirmed | contractor_transfer_cancelled | contractor_transfer_reconfirm_unclear",
  "body": "string"
}
```

- `kind=contractor_transfer_confirmed`のとき: 「契約者を◯◯様に変更いたしました」相当の
  完了報告下書き。実際の`craftsman_workshop.contractor_user_id`更新はアプリケーション側が
  このkindを検知して`apply_contractor_transfer`(フェーズ35実装済み)を呼び出すことで
  行う。LLM側は文言生成のみを担い、更新処理自体には関与しない。
- `kind=contractor_transfer_cancelled`のとき: 「契約者交代の手続きを取り消しました。
  現在の契約者のまま変更ございません」相当のキャンセル確認文言。アプリケーション側は
  `pending_contractor_transfer`を削除するのみで`contractor_user_id`は更新しない。
- `kind=contractor_transfer_reconfirm_unclear`のとき: 「契約者交代についてのご返信で
  よろしいでしょうか?『はい』か『いいえ』でお知らせください」という再確認一言のみ
  (member-retention-notice-design.mdの意思確認一言パターンを踏襲)。`pending_contractor_
  transfer`は削除せず維持し、期限内であれば再度この3パターンの判定対象とする。

`status`が上記3値以外のときは`contractor_transfer_confirmation`は必ずnull(他フィールド
と同様、コード側検証で担保する)。

## 4. 期限切れの扱い

`pending_contractor_transfer.expires_at`を過ぎた後に契約者から返信があった場合、2節の
条件を満たさなくなるためアプリケーション側は文脈注入を行わず、LLMは3節の3パターンの
判定対象にしない(通常メッセージとして扱われる)。期限切れを契約者へ能動的にプッシュ
通知すべきかは、line-reservation-aiのcandidates-expired-notification-design.md(プッシュ
課金・送信タイミングの唐突さ・実測データ不在を理由にMVPでは送らない方針)と同種の論点
であり、本ventureでも同様に能動通知は行わない方針とする。次回契約者からのメッセージ
受信時に「確認期限切れのため再度ご連絡ください」と案内する受動的な扱いに留める(この
案内文言自体のschema設計は5節の残課題とする)。

## 5. 未検証・残課題

- (解消済み 2026-09-08 04:00 UTC・フェーズ39: 4節の「期限切れ後の案内文言」自体の
  schema・プロンプト設計はcontractor-transfer-expired-notice-design.mdで設計した。
  新たなstatus値`contractor_transfer_expired_notice`を追加する方針とし、既存の
  insufficient_input等では代替せず専用の文脈注入条件・フィールドを新設した。schema/
  output.schema.json・validate_test_cases.py・prototypeへの反映は同ファイル4節の
  残課題として引き続き残る)
- schema/output.schema.json・validate_test_cases.pyへの反映(新規enum値3つ・
  `contractor_transfer_confirmation`フィールド追加、クロスフィールド検証、新規テスト
  ケース・ネガティブテストケース追加)は次の課題として残す。
- prototype/usage_counter_workshop.py側の`pending_contractor_transfer`一時状態の
  読み書き(`WorkshopStoreProtocol`への追加、`apply_contractor_transfer`呼び出し時・
  キャンセル時・期限切れ時の削除処理)の実装も次の課題として残す。
- `expires_at`=24時間という値は暫定であり、実運用データが無いため未検証。
- 実際のLINE公式アカウント接続・実LLM検証は未着手(オーナー承認待ちの範囲、
  pending-approval.md参照)。

最終更新: 2026-09-08 01:00 UTC(フェーズ36)
