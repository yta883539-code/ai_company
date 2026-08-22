# 初回生成時セルフチェック案内の要否・設計

作成日: 2026-08-22

onboarding-guide.mdの「次のステップ候補」に残っていた「ステップ3(接続テスト)省略時の
フォールバック設計(course-set-pashaのonboarding-settings-and-self-check-design.md・
first-generation-notice-implementation-design.md相当)の要否・内容」について検討する。

## 1. course-set-pashaとの構造的な類似点

本ventureはtech-stack.md・mvp-flow-draft.mdの通り、course-set-pashaと同じく双方向の会話・
予約状態管理を持たない単方向バッチ処理(1メモ受信→LLM呼び出し→3出力生成→返信)であり、
line-reservation-aiのような`ConversationFlowStateMachine`インスタンスも持たない。したがって
「試験生成」を専用フラグ・別エンドポイントで判別する手段が無い点、判別不能な以上は
**そのユーザー(業者)にとって最初の生成成功時**を暗黙のテストとみなす他ない点は、
course-set-pashaの結論(onboarding-settings-and-self-check-design.md)がそのまま当てはまる。
→ **本ventureも同じ設計方針(初回生成成功時のみレスポンス末尾に確認案内を1回だけ付記)を
採用する。**

## 2. course-set-pashaとの重要な相違点: 出力1・出力2は依頼者へ直接転送される

course-set-pashaの出力1(SNS投稿文下書き)は、ジムオーナーが内容を確認・自分の言葉で
微修正してから自身のSNSアカウントに投稿する一手間が挟まる。一方、本ventureの出力1
(作業完了報告メッセージ下書き)・出力2(お手入れ案内下書き)は、onboarding-guide.mdステップ5の
通り「業者が返ってきた下書きをそのまま依頼者への報告・案内として送付する」運用を明示的に
許容している(コピー&ペーストでそのまま顧客に転送される想定)。

これは、確認案内の実装位置に関して course-set-pasha より一段強い制約を意味する。

- **確認案内は`completion_report.body`・`care_guide.body`(依頼者に転送されうるフィールド)の
  内部に一切混入させてはならない。** もし混入すれば、業者が中身を精査せずそのまま転送した
  場合に「【ご確認のお願い】…」という業者向け内部メッセージが依頼者(エンドカスタマー)に
  届いてしまう事故になる。これはcourse-set-pashaでも望ましくないが、本ventureは「そのまま
  転送」が正規の運用として明示されている分、事故が起きた際の実害(顧客への誤送信)が
  より直接的である。
- したがって、course-set-pashaが既に採用していた「出力組み立て側(webhook処理の最終ステップ)で
  レスポンス全体の末尾に付記し、`completion_report`・`care_guide`・`history_rows`の各フィールド
  自体は一切変更しない」という実装方針を、本ventureでは**必須の安全設計**として明記する
  (course-set-pashaでは「責務分離が望ましい」という設計上の理由だったが、本ventureでは
  それに加えて「依頼者への誤送信を防ぐ」という機能要件になる)。
- 確認案内はLINE返信メッセージを複数吹き出しに分ける場合、`completion_report`・`care_guide`とは
  **別の吹き出し(別メッセージ)**として送る設計が望ましい(1つの吹き出しに混在させると
  業者が全文を丸ごとコピーしてしまうリスクが残るため)。1メッセージにまとめる場合は、
  区切り線と「※本メッセージのこの部分は依頼者へ転送しないでください」という明示的な注記を
  付ける。実際のLINE API接続時にメッセージ分割の可否を確認する必要があり、これは実装時の
  課題として残す。

## 3. course-set-pashaとの相違点2: 設定項目未入力時の分岐は不要

course-set-pashaは確認案内に加えて「ジム名・地域名が未設定です」という分岐文言を付記する
設計だったが、onboarding-guide.md 4節の通り本ventureにはそもそも屋号・エリア相当の設定項目が
無い(申込フォーム入力のみで出力に必要な情報が完結する)。したがって本ventureの確認案内には
course-set-pashaのような「未設定項目の案内」分岐は不要で、確認案内は常に同一文面でよい。

## 4. 確認案内の文面案

```
【ご確認のお願い(業者様向け・依頼者への転送不要)】
これが最初の生成です。分解洗浄の範囲や次回推奨時期の記載が実際の作業内容と合っているか、
この機会にご確認ください。冷媒・電気系統についての専門的な当否評価が混ざっていないかも
あわせてご確認いただくと安心です。問題がなければ今後この案内はありません。
```

## 5. 実装方針(疑似コード)

course-set-pashaのfirst-generation-notice-implementation-design.mdと同じ`usage_counter`拡張
パターンを踏襲する。

```
usage_counter/{user_id}
  month: string                       # "2026-08" 形式、既存
  count: number                       # 既存
  first_generation_notice_sent: bool  # 新規追加。既定値 false
```

```python
def handle_webhook(event):
    # ...既存の入力検証・LLM呼び出し・post_generation_checks...
    outputs = build_outputs(llm_result)  # completion_report / care_guide / history_rows

    counter = usage_counter.get(user_id)  # 不在なら {count: 0, first_generation_notice_sent: False}
    is_first_generation = (counter.count == 0)

    reply_messages = [outputs.completion_report_message, outputs.care_guide_message]
    if is_first_generation and not counter.first_generation_notice_sent:
        reply_messages.append(SELF_CHECK_NOTICE_TEXT)  # 別吹き出しとして追加、body自体は不変
        usage_counter.set(user_id, first_generation_notice_sent=True)

    return reply_messages
```

`month`繰り上がり時も`first_generation_notice_sent`はリセットしない(生涯1回のみ、
limit-approaching-notification-design.mdの月次リセット対象フィールドとは独立)方針も
course-set-pashaと同じ。

## 残課題

- `usage_counter`への`first_generation_notice_sent`フィールド追加、および
  `cloud_function_webhook.py`側での実配線は、実Firestore接続・実LINE API接続自体が
  オーナー承認待ちのため未着手のまま残す。
- 「試験生成のつもりで送ったメモが実は最初の生成ではなかった」ケースはシステム側で区別できない
  既知の限界として残る(course-set-pashaと同じ)。

## LINE Messaging API のメッセージ数・文字数上限確認(フェーズ101で解消)

2.で述べた「別吹き出し必須」という制約が、実際のLINE Messaging APIのメッセージ数上限と
衝突しないかを、LINE Developers公式ドキュメントの記載に基づき確認した。

- 1回の応答(reply token使用)で送信できるメッセージオブジェクトは最大5件まで。本venture
  は`completion_report_message`・`care_guide_message`・(初回のみ)`SELF_CHECK_NOTICE_TEXT`
  の最大3件で、上限5件に対して余裕があり、初回生成での3件同時送信は仕様上問題なく可能と
  確認できた。将来history_row関連の通知等を追加する場合も、上限5件を超えないことを
  設計時に都度確認する必要がある点は留意事項として残す。
- テキストメッセージ1件あたりの文字数上限は5,000文字(UTF-16コード単位でのカウント、
  絵文字・一部の漢字は2文字以上としてカウントされる点に注意)。completion_report・
  care_guideの本文はいずれも数百文字程度の想定(mvp-flow-draft.md参照)であり、通常の
  入力メモの範囲では上限に達する可能性は低いが、極端に長いメモが入力された場合の文字数
  超過時のフォールバック処理(切り詰め・エラー応答等)は未設計のまま残課題とする。

出典: LINE Developers「Send messages」
(https://developers.line.biz/en/docs/messaging-api/sending-messages/)、
LINE Developers「Character counting in a text」
(https://developers.line.biz/en/docs/messaging-api/text-character-count/)。
