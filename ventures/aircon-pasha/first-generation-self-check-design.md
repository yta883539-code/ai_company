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

料金プランの変更・解約方法などよくあるご質問は、トークルームで「FAQ」と送信すると
いつでもご確認いただけます。
```

(2026-09-17追記・フェーズ226: owner-faq-routing-design.md 5節が残課題としていた
「FAQコマンドの存在をどう周知するか」に対応し、末尾2文を追記した。詳細は6節参照。)

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

- (解消済み 2026-08-28 03:00 UTC・フェーズ136: `cloud_function_webhook.py`の
  `process_memo_event()`に実配線した。ただし`usage_counter`側に別立ての
  `first_generation_notice_sent`フラグを新設する当初案は採らず、
  trial-start-anchor-decision.md 3節で確定した`user_profile.trial_start_at`
  (初回生成成功時に1回だけ設定・以降不変、フェーズ134で実装済み)が未設定かどうかを
  そのままセルフチェック案内の要否判定に兼用する設計に変更した。理由:
  本ventureはcourse-set-pashaと異なりtrial_start_at自体を`usage_counter`ではなく
  `user_profile`が直接保持する設計(フェーズ134の判断)であり、かつtrial_start_atは
  既に「生涯1回だけ書き込む」不変フィールドとして実装済みのため、同じ性質を持つ
  フラグを`usage_counter`側に重複して新設する必要が無いと判断した。実Firestore接続・
  実LINE API接続自体は引き続きオーナー承認待みだが、判定ロジック・文言組み立て・
  `trial_start_at`書き込み自体はコード上で検証済み〈テスト5件追加、
  test_cloud_function_webhook.py `ProcessMemoEventFirstGenerationSelfCheckTest`〉)
- 「試験生成のつもりで送ったメモが実は最初の生成ではなかった」ケースはシステム側で区別できない
  既知の限界として残る(course-set-pashaと同じ)。

## 6. FAQコマンドの周知(2026-09-17追記・フェーズ226)

owner-faq-routing-design.md(フェーズ225)は4venture全てへのFAQコマンド方式(「FAQ」→
「Q1」〜「Q7」)実装完了時点で、「FAQという単語自体を契約者が思いつかない可能性があり、
コマンドの存在をどう周知するかは別課題として残る」「既存の固定文言の変更を伴うため
本フェーズでは見送った」と残課題化していた。本フェーズでこれに対応する。

- **周知の場所として本ドキュメントのSELF_CHECK_NOTICE_TEXT(初回生成時セルフチェック
  案内)を選んだ理由**: (1)`trial_start_at`が未設定の全業者が生涯に一度は必ず受け取る、
  システム上唯一確実な導線であること(オンボーディング完了フォーム提出自体はLPからの
  申込フォーム入力であり本システムの外で完結するため、LINE側から確実に送れるタイミングは
  実質この初回生成成功時のみ)、(2)この案内は既に「業者様向け・依頼者への転送不要」という
  文脈が確立しており、FAQコマンド(同じく業者向け機能)の案内を追記しても文脈の混在が
  起きないこと、(3)completion_report・care_guideのbody自体には触れないため、2節の
  安全設計(依頼者への誤送信防止)を壊さないこと、による。
- **既存の固定文言を変更する」ことへの懸念(残課題の原文)への回答**: 文言の変更ではなく
  末尾への2文追記のみとし、既存の確認依頼部分(セルフチェックの目的・内容)は一切変更
  していない。test_cloud_function_webhook.pyの既存アサーション(`assertIn`/`assertNotIn`
  でSELF_CHECK_NOTICE_TEXT定数そのものを比較)は定数の変更に自動追従するため、テスト側の
  修正は不要だった。
- **見送った代替案**: オンボーディング完了時点(LPの申込フォーム送信直後)にFAQ案内を
  別送する案も検討したが、本venture(course-set-pashaと同じくバッチ処理・会話状態を
  持たない設計)はLPフォーム送信がシステム外(申込フォーム)で完結し、LINE公式アカウントと
  友だち追加した直後にメッセージを自動送信する仕組み自体が未設計(onboarding-guide.mdにも
  該当ステップなし)であるため、新規のトリガー・実装を要する分、本フェーズのスコープを
  超えると判断し見送った。将来的にLINE公式アカウントの「あいさつメッセージ」機能
  (友だち追加時の自動応答、LINE Developers標準機能)を使えば追加実装なしでも実現できる
  可能性があり、実LINE API接続時(オーナー承認待ち)にあわせて検討する候補として残す。
- 実装は`prototype/cloud_function_webhook.py`の`SELF_CHECK_NOTICE_TEXT`定数末尾に
  「料金プランの変更・解約方法などよくあるご質問は、トークルームで「FAQ」と送信すると
  いつでもご確認いただけます。」を追記し、`test_cloud_function_webhook.py`に
  `test_self_check_notice_mentions_faq_keyword`(定数が"FAQ"というトリガー文言を含み、
  それが`owner_faq_router.is_owner_faq_menu_trigger()`の判定するキーワードと一致することを
  検証)を1件追加した。回帰確認としてventure全体・schema検証いずれもパスを確認した
  (詳細はREADME.mdフェーズ226参照)。
- **残課題**: あいさつメッセージ機能を使った、初回生成前(友だち追加直後)の周知は
  実LINE API接続後の検討課題として残る。
- (解消済み 2026-09-20 01:00 UTC定例更新: 上記「他3venture(course-set-pasha・
  kura-pasha・line-reservation-ai)の同種セルフチェック案内・初回案内文言への同じ追記の
  要否は、各ventureの担当フェーズで横展開を検討する」という記載が古い状態のまま残って
  いたことを発見した。各venture側のコード・設計文書を確認したところ、course-set-pasha
  (`format_welcome_message()`末尾、2026-09-17 19:00 UTCコミットd040375で追記済み)・
  kura-pasha(`format_follow_welcome_message()`末尾、2026-09-17 20:00 UTCで追記済み)・
  line-reservation-ai(オンボーディング完了メッセージ末尾、フェーズ続き234で追記済み)の
  いずれも既に同種の周知文言(「FAQ」と送信すると案内する旨)を追記済みであり、
  course-set-pashaのowner-faq-routing-design.md 5節にも「2026-09-18時点で4venture全ての
  周知対応が完了している」と記録されていることを確認した。本venture(aircon-pasha)自身も
  フェーズ226でSELF_CHECK_NOTICE_TEXTへの追記により対応済みのため、結果として4venture
  全ての周知対応は2026-09-18時点で完了しており、追加の横展開作業は不要と判断した。コード
  変更は無く、回帰確認としてventure全体515件・schema検証21件いずれもパス(変更前と同じ
  結果)を確認した。承認不要なドキュメント記載訂正のみで、外部サービスへの公開・
  アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし)

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
  超過時のフォールバック処理(切り詰め・エラー応答等)は、当初は未設計のまま残課題として
  いた。(解消済み 2026-08-22: character-limit-fallback-design.md(フェーズ102)で
  「切り詰めは行わず送信失敗として扱う」方針を設計し、フェーズ105で
  `check_message_length_within_line_limit()`(`prototype/post_generation_checks.py`)・
  `cloud_function_webhook.py`側のフォールバック分岐として実装・テスト済み。詳細は
  character-limit-fallback-design.md参照)。

出典: LINE Developers「Send messages」
(https://developers.line.biz/en/docs/messaging-api/sending-messages/)、
LINE Developers「Character counting in a text」
(https://developers.line.biz/en/docs/messaging-api/text-character-count/)。
