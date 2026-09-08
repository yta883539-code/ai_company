# 契約者譲渡: 期限切れ後の案内文言 schema・プロンプト設計(フェーズ39)

作成日: 2026-09-08(フェーズ39)

## 背景・対応する残課題

contractor-transfer-confirmation-detection-design.md(フェーズ36)4節で「次回契約者から
のメッセージ受信時に『確認期限切れのため再度ご連絡ください』と案内する受動的な扱いに
留める」と方針決定したものの、同ファイル5節1点目で「この案内文言自体のschema・
プロンプト設計は次回以降の課題」として未着手のまま残っていた。`check_and_expire_
pending_contractor_transfer`(フェーズ38実装済み、期限切れの場合は削除前のPending
ContractorTransferを返す)の戻り値をどう案内文言生成に繋げるかを含め、本ファイルで
設計する。

## 1. 起動条件・文脈注入(フェーズ36 2節への追加)

アプリケーション側は、契約者(`contractor_user_id`と一致する送信者)からのメッセージを
受信するたびに、LLM呼び出しに先立って`check_and_expire_pending_contractor_transfer`を
呼び出す(フェーズ38実装済み、`now`時点で`expires_at`を過ぎたpendingがあれば削除して
その値を返す、無ければNone)。

- 戻り値がNone以外(=直前に期限切れを検出した)の場合: フェーズ36 2節の「pending存在
  かつexpires_at以内」という確認応答コンテキストの条件は満たさない(既に削除済みのため)
  代わりに、本ファイルで新設する「契約者交代確認の期限切れ(候補: `{candidate_member_
  name}`)」という文脈を注入してLLMを呼び出す。この文脈がある場合、受信メッセージの
  内容(何が書かれていたか)に関わらず3節のstatusを強制する。
- 戻り値がNoneの場合: フェーズ36 2節の既存条件(pending存在・期限内)の判定に進む
  (変更なし)。

この2つの文脈注入条件は排他的である(`check_and_expire_pending_contractor_transfer`が
非Noneを返すのは、まさにその呼び出し時点で期限切れと判定されたpendingがあった場合のみ
であり、期限内であればフェーズ36の既存経路に進むため両方の文脈が同時に注入されることは
ない)。

## 2. 「受信メッセージの本来の用件」は今回処理しない

期限切れ検出時、契約者が送ってきたメッセージ自体が新規受注メモや別件の可能性はあるが、
本設計では今回のターンでは処理しない(4節の方針通り「次回のメッセージ受信時」に案内する
という受動的対応に留め、本来の用件がある場合は契約者が案内を読んだ上で改めて送り直す
想定とする)。これはgenerated/out_of_scope/insufficient_input等、既存のstatus分岐が
互いに排他的である(1ターン1status)という既存設計の一貫性を保つための判断であり、
複数の意図を1回のLLM呼び出しで同時に処理する設計は本ventureでは採用していない
(mvp-flow-draft.md『構造化出力の方針』参照)。

## 3. status・schema拡張

`status`のenumへ以下1値を追加する。

- `contractor_transfer_expired_notice`: 1節の期限切れ文脈が注入された場合に必ずこの値
  となる(受信メッセージの内容によらない、アプリケーション側からの強制分岐)。

新規フィールド`contractor_transfer_expired_notice`(トップレベル、他フィールドと同様に
常時出力必須・nullを許容)を追加する。既存のcontractor_transfer_notice/contractor_
transfer_confirmationと同じ設計思想(kindはstatusと1:1で冗長だがbody生成ロジック側の
分岐用に保持)を踏襲する。

```json
{
  "kind": "contractor_transfer_expired_notice",
  "candidate_member_name": "string | null",
  "body": "string"
}
```

- `candidate_member_name`: `check_and_expire_pending_contractor_transfer`が返した
  (削除前の)`PendingContractorTransfer.candidate_member_name`をそのままアプリケーション
  側からプロンプトへ渡し転記させる(member_retention_notice.specified_member_nameと
  同様、LLMが本文中で「○○様への契約者交代の確認期限が過ぎたため」のように具体的に
  言及できるようにするための補助フィールド)。常に非null(この文脈が注入される時点で
  必ず候補者名が存在するため)。
- `body`: 「契約者交代(`{candidate_member_name}`様への変更)の確認期限が過ぎたため、
  手続きを一旦取り消しました。交代をご希望の場合は、お手数ですが改めてご連絡ください」
  相当の一言案内のみ。完了報告(contractor_transfer_confirmed)や取り消し確認
  (contractor_transfer_cancelled)と混同されないよう、「あなたの操作でキャンセルされた」
  のではなく「時間切れで自動的に取り消された」旨が伝わる文言にする(厳守事項として
  プロンプトに明記)。

`status`が`contractor_transfer_expired_notice`以外のときは`contractor_transfer_expired_
notice`は必ずnull(他フィールドと同様、コード側検証で担保)。

## 4. 未検証・残課題

- schema/output.schema.json(status enum・新規フィールド)・validate_test_cases.pyへの
  反映(期待出力テストケース1件、`candidate_member_name`のnull制約違反を検出する
  ネガティブテストケース1件)は次の課題として残す。フェーズ37(contractor_transfer_
  confirmation追加時)と同様の反映パターンを踏襲する想定。
- `check_and_expire_pending_contractor_transfer`の呼び出し元(webhook受信処理相当)への
  配線、および1節の文脈注入条件の実装(`is_contractor_transfer_confirmation_context`と
  対になる新関数、例: `is_contractor_transfer_expired_notice_context`)はprototype/
  usage_counter_workshop.py側で未着手。
- 契約者以外(譲渡候補本人や第三者)が期限切れ後に何かメッセージを送ってきた場合の扱い
  (本ファイルは契約者からのメッセージのみを対象とする、フェーズ36 2節の前提を踏襲)は
  範囲外のまま。
- 実際のLINE公式アカウント接続・実LLM検証は未着手(オーナー承認待ちの範囲、
  pending-approval.md参照)。

最終更新: 2026-09-08 04:00 UTC(フェーズ39)
