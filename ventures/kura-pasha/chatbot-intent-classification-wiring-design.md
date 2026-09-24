# チャットボット一次受付: 意図分類レイヤーの配線設計・0節前提の再検証(フェーズ171)

作成日: 2026-09-24(フェーズ171)

フェーズ170の「次回候補」に残っていた「`prototype/chatbot_intent_router.py`の
3関数を実際のLINEメッセージ受信ハンドラ(`cloud_function_webhook.py`)へ配線する設計」に
着手する。配線先の`process_message_event()`・`process_memo_event()`の既存実装
(フェーズ64〜フェーズ170時点)を読み直したところ、配線設計そのものより先に解決すべき、
chatbot-intent-classification-design.md(フェーズ167)0節の前提に関わるギャップを
発見したため、本ドキュメントは(1)ギャップの指摘、(2)修正方針、(3)修正を踏まえた
配線設計、の3部構成とする。実装・実LLM呼び出しは行わない、机上の設計のみとする。

## 1. 発見したギャップ: 0節が前提とする「既存の意図検知」は独立した事前チェックではない

chatbot-intent-classification-design.md 0節は、次の2つを「メッセージ受信時に既に
稼働している既存の意図検知ロジック」とし、新設の意図分類(6分類)より**常に手前で
実行される**ものと位置づけていた。

- 解約意図検知(厳守事項7a相当)
- 契約者譲渡意図検知(contractor-transfer-design.md 3節)

しかし実装を辿ると、この2つはいずれも**独立した事前チェック関数ではなく、
`process_generation_request()`が呼び出す一つの受注メモ生成LLMコール(厳守事項1〜8・
7a〜7cを含む単一のシステムプロンプト、schema/output.schema.jsonの19通りのstatus
enumの一部として出力される)の内部でのみ判定される**。

- 解約意図(`cancellation_intent`/`downgrade_intent`/`cancellation_unclear`):
  llm-system-prompt-draft.md 105〜138行目、厳守事項7aとしてメモ生成プロンプトに
  同居している。
- 契約者譲渡意図(`contractor_transfer_selection`/`contractor_transfer_unclear`):
  contractor-transfer-design.md 3節「確定する設計」自体が「`status`のenumへ
  `contractor_transfer_selection`/`contractor_transfer_unclear`の2値を
  schema/output.schema.jsonへ追加する」と明記しており、同じ単一LLMコールの出力の
  一部である。

つまり「解約したい」という自由文が来たとき、それが解約意図であると判定できるのは
**受注メモ生成LLMコールを実際に呼び出した後**であり、これより手前で(かつ、それとは
別の軽量な6分類LLMコールとして)解約意図か否かを知る術は現時点で存在しない。
0節の「先に実行してから意図分類を行う」という処理順序は、実装上そのままの形では
成立しない前提だったことになる。

## 2. 実害の具体例: `faq_cancel`による誤誘導

上記ギャップが実害を生む具体的なケースは次の通り。契約者が「もう解約したいです」
とだけ送信した場合(受注メモらしき内容を一切含まない):

- **現状(意図分類レイヤー未配線)**: `process_memo_event()`がそのまま受注メモ生成
  LLMコールへ渡し、厳守事項7aにより`status=cancellation_intent`と判定され、
  `render_subscription_procedure_notice()`が`portal_link_provider`から取得した
  実際のStripeカスタマーポータルURLを本文に埋め込んだ案内を返す(design 0節が
  意図した通りの、既存の解約フローそのもの)。
- **意図分類レイヤーを0節の想定通り「手前で」配線した場合**: フェイルセーフ方針
  2節ルール1(「メモらしき内容が少しでも含まれる場合はmemo_processing_requestを
  優先」)は"解約したい"のみのメッセージには適用されない(メモらしき内容が無い
  ため)。この文言は「解約」という語を含むため`faq_cancel`に分類される可能性が高く、
  `render_chatbot_faq_response_message("faq_cancel")`
  (`owner_faq_router.render_owner_faq_answer_message("Q3")`)が返る。
  owner-operation-self-service-faq.md Q3の回答文(「Stripeカスタマーポータルから
  契約者自身が解約手続きできる」という**説明文のみ**で、実際のポータルURLは
  含まない)がそのまま返信され、契約者は実際の解約手続きへ進む具体的な導線
  (実URL)を受け取れない。

これはchatbot-intent-classification-design.md自身が`faq_cancel`新設の理由として
挙げていた「既存の解約意図検知フローへの誘導文言に帰着させるため」という意図とも
矛盾する(Q3の回答文は「誘導」ではなく単なる制度説明であり、実際の解約フローへの
再入口を持たない)。`faq_contractor_transfer_overview`(Q7)についても同様の
リスクがあるが、契約者譲渡は「後継ぎに変更したい」等の言い回しが比較的
定型的でmemo_processing_requestの語彙(馬体のサイズ・鞍の型等)と混同しにくい分、
実害の頻度は解約意図より低いと見込む。

## 3. 修正方針: フェイルセーフ方針2節ルール1の適用範囲を拡張する

0節の処理順序自体を撤回し、次のルールをchatbot-intent-classification-design.md
2節(フェイルセーフ方針)ルール1の適用範囲拡張として追記する(次フェーズで
当該ドキュメントへの反映を行う。本フェーズでは方針の確定のみ)。

> ルール1拡張: 「メモらしき内容」に加え、解約・ダウングレード・契約者交代の
> **意思表示そのもの**(「解約したい」「後継ぎに変更したい」等、単なる制度説明の
> 質問ではなく具体的なアクションの申し出)が含まれる場合も`memo_processing_request`
> を優先する。これにより、当該メッセージは新設の意図分類レイヤーでは
> `faq_cancel`/`faq_contractor_transfer_overview`に振り分けず、既存の受注メモ生成
> LLMコール(厳守事項7a・contractor-transfer-design.md 3節を内包する単一コール)へ
> そのまま到達させ、実URL・確認フロー付きの既存の解約/譲渡フローを引き続き
> 利用させる。
>
> `faq_cancel`/`faq_contractor_transfer_overview`は、「解約するとどうなるの?」
> 「契約者交代の仕組みってどうなってる?」のような**制度理解目的の質問**
> (アクションの申し出を伴わないもの)にのみ分類される、という当初の1節の
> 想定(`faq_contractor_transfer_overview`側は既に「制度概要説明のみ」と
> 明記済み)を、`faq_cancel`側にも明示的に同じ限定を課す形で統一する。

この拡張により、0節が想定していた「新設の意図分類より手前で既存ロジックが処理
済み」という結果自体は(実装の形は変わるが)最終的に維持される: 実際に解約/譲渡の
意思表示を含むメッセージは、新設の意図分類レイヤーの中で(手前の別チェックとしてで
はなく、分類ルールの一部として)`memo_processing_request`側へ振り分けられ、
既存の受注メモ生成LLMコールに一本化されたまま処理される。

## 4. 配線設計: `process_message_event()`への配置

上記の修正方針を前提に、`route_chatbot_intent()`等3関数を`cloud_function_webhook.py`
へ配線する設計は次の通り。既存の分岐順序(フェーズ68〜170で確立済み)を変更しない
範囲に新設のステップを1つ挿入する形とする。

1. `linking_enabled`判定・連携コード解決(既存、変更なし)。
2. 連携済みuser_idの場合、`_maybe_handle_owner_faq_command()`
   (契約者本人からの明示的な「FAQ」「Q1」〜「Q9」コマンド、フェーズ126)を
   既存通り最優先で判定する(変更なし)。この明示コマンドは自由文の意図分類とは
   独立した完全一致トリガーであり、新設レイヤーとは競合しない。
3. 上記2つに該当しない場合、**新設: `chatbot_intent_classification_client`
   (新設Protocol、5節参照)が渡されている場合のみ**、受信テキストを渡して
   意図分類コールを実行する。
   - `memo_processing_request`と判定された場合(3節の拡張ルールにより解約/譲渡の
     意思表示を含む場合もここに含まれる): 通常通り`process_memo_event()`へ
     委譲する(変更なし、意図分類コールの結果は`append_faq_followup_hint()`用に
     生成後の返信文へ渡す。8節参照)。
   - `faq_plan`/`faq_howto`/`faq_cancel`/`faq_contractor_transfer_overview`と
     判定された場合: `route_chatbot_intent()`が返す定型回答をそのまま返信し、
     受注メモ生成LLMコール自体を呼び出さない(コスト削減がこのレイヤー新設の
     本来の目的、chatbot-first-response-feasibility.md 5節「メリット」)。
   - `other_needs_human`と判定された場合: `route_chatbot_intent()`が
     `send_chatbot_escalation_notification()`を呼び、運営者通知用の
     `push_client`(新設の実行時依存、5節参照)が必要。
   - `chatbot_intent_classification_client`が渡されていない場合(実LLM接続が
     オーナー承認待ちの間の既定状態): このステップ自体を丸ごとスキップし、
     フェーズ170時点までと全く同じ挙動(常に`process_memo_event()`へ委譲)を
     維持する(usage_counter_store等、他の任意依存と同じ「Noneなら既存動作」の
     後方互換パターンを踏襲)。

## 5. 新設Protocol: `ChatbotIntentClassificationClient`

```python
class ChatbotIntentClassificationClient(Protocol):
    def classify(self, memo_text: str) -> str:
        """chatbot_intent_router.CHATBOT_INTENT_VALUES のいずれかを返す。
        呼び出し自体が失敗した場合はLlmApiError(既存の例外を再利用)を送出する契約。
        分類の失敗時(2回リトライ後も失敗)はフェイルセーフとして
        memo_processing_request 扱いにフォールバックし、既存の受注メモ生成LLM
        コールへ委ねる(意図分類は「コスト削減のための前段フィルタ」であり、
        分類自体が信頼できない場合は安全側〈= より高機能な既存フロー〉に倒す)。
        """
        ...
```

`LlmCallClient.generate()`とは別のProtocolとする(既存のgenerate()は受注メモ
生成専用の19-status構造化出力契約であり、意図分類は6分類の単純な文字列出力
契約のため、契約の形が異なる)。

## 6. 未解決・次の課題

- ~~本ドキュメント3節の拡張ルール自体を、次フェーズでchatbot-intent-classification-
  design.md 2節・chatbot-intent-classification-llm-prompt-draft.mdへ正式に反映する。~~
  → フェーズ172で両ドキュメントへ正式反映済み(design.md 0節・1節`faq_cancel`・
  2節ルール1、llm-prompt-draft.md 判定順位1・分類カテゴリ説明をあわせて訂正)。
- `faq_contractor_transfer_overview`側についても、2節と同様の実害シナリオ
  (「契約者を交代したい、田中さんにお願いします」のような、名指しを含む具体的な
  譲渡依頼が`faq_contractor_transfer_overview`に誤分類されるケース)がないか、
  contractor-transfer-design.md 3節の語彙パターンと突き合わせた再検証が必要
  (本フェーズは解約意図側の実害の特定を優先したため未着手。フェーズ172でも
  design.md・llm-prompt-draft.md側に申し送り事項として明記したが、再検証自体は
  依然未着手)。
- 4節3.の意図分類コール自体(自由入力→6分類)は引き続き実LLM接続が
  オーナー承認待ちの領域であり、本ドキュメントは配線設計にとどまる。

## 回帰確認

本フェーズはドキュメントの新規作成のみでコード変更を行っていない。念のため
`python3 prototype/run_all_tests.py`(16ファイル全件[OK])・
`python3 schema/validate_test_cases.py`(32件中32件パス)がいずれも変更前と
同じ結果であることを確認した。承認が必要なアクション(支払い・アカウント作成・
外部公開・送信等)は今回発生していないためpending-approval.mdへの追記なし。

追記(フェーズ172、2026-09-24 20:00 UTC): 本節1点目の「次フェーズで正式反映する」
申し送りに対応し、chatbot-intent-classification-design.md・chatbot-intent-
classification-llm-prompt-draft.mdへ本ドキュメント3節の拡張ルールを反映した。
本ドキュメント自体への変更は上記の取り消し線追記のみ。回帰確認として同じ2コマンド
(venture全体16ファイル全件・schema検証32件)を再実行し変更前と同じ結果であることを
確認した。承認が必要なアクションは今回も発生していないためpending-approval.mdへの
追記なし。
