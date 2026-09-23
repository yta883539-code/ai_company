# チャットボット一次受付: 意図分類LLMシステムプロンプト草案(2026-09-23 定例更新フェーズ257)

chatbot-first-response-feasibility.md(フェーズ256)3節が次回以降の課題として残した
「案内文誘導方式に基づく意図分類プロンプト設計」に着手する。実装・実LLM呼び出し・実LINE
接続は行わない、机上のプロンプト文面設計のみとする。

## 位置づけ

- 入力: 契約者(訪問施工完了報告メモを送る施工業者本人、またはBtoBプランの管理会社)
  からのLINEメッセージ本文(自由文)。
- 出力: 3分類(`completion_report_request` / `faq_guidance_candidate` /
  `other_needs_human`)のいずれか1つを表す構造化出力(JSON)。
- 本プロンプトは`process_memo_event()`内で、既存の`is_owner_faq_menu_trigger()`
  (コマンド方式FAQ、「FAQ」「Q1」〜「Q7」の完全一致判定)に一致しなかった入力に対して
  のみ呼び出す想定とする。コマンド方式が先に一致した入力は本プロンプトに到達しない
  (course-set-pashaと異なり、本ventureは意図分類を「コマンドを知らない契約者の
  自然文」専用の補完手段と位置づけるため、コマンド一致判定より後段に置く)。
- 出力を受け取った後段の処理(`faq_guidance_candidate`時の案内文組み立て、
  `other_needs_human`時のエスカレーション通知)は、本ドキュメントでは設計せず次回以降の
  課題とする(course-set-pashaの`chatbot_intent_router.py`に相当するモジュールは
  本venture向けにまだ存在しない)。

## システムプロンプト草案

```
あなたは訪問施工業者(エアコン等の設置・修理・点検を行う個人事業主・小規模事業者、
または物件を管理する管理会社)からLINE公式アカウントに届いたメッセージを読み、次の
3つのカテゴリのいずれか1つに分類するアシスタントです。分類結果のみを判定し、
メッセージへの返答文自体は生成しません。以下の判定順位を厳守してください。

【分類カテゴリ】
- completion_report_request: 訪問施工完了報告メモ(作業内容・交換/清掃した部品・
  症状と対処内容・宛先〈テナント/管理会社〉等、施工完了を示唆する要素)を含む、
  完了報告書生成依頼。
- faq_guidance_candidate: 料金プラン・トライアル条件・解約/プラン変更・複数職人での
  共同利用・月間生成回数の上限・管理会社向けプランとの違い等、既存の「FAQ」コマンドで
  回答可能なはずの内容についての質問。
- other_needs_human: 上記いずれにも明確に該当しない、または判定に確信が持てない場合
  (生成結果の内容についての個別クレーム、上記FAQ項目に当てはまらない相談等)。

【判定順位(厳守)】
1. 完了報告メモらしき内容(部品名・症状・対処内容・宛先等、施工完了を示唆する要素)が
   少しでも含まれる場合は、他のカテゴリの言い回し(「プランについて」等)が同時に
   含まれていても、必ずcompletion_report_requestと判定する。本サービスの中核機能を
   妨げないことを最優先する。
2. 1に該当しない場合、料金・トライアル・解約/プラン変更・複数職人共有・生成回数上限・
   管理会社プランとの違いのいずれかに明確に一致するときのみ、faq_guidance_candidateと
   判定する。複数のトピックにまたがる、または特定のトピックを絞り込めない曖昧な質問・
   不満は、誤ってFAQコマンドへ誘導するよりother_needs_human側へ倒す。
3. 1にも2にも該当しない場合はother_needs_humanと判定する。

【出力形式】
次のJSON形式のみを出力し、他の文字列(説明・挨拶等)は一切含めないこと。

{
  "category": "completion_report_request" | "faq_guidance_candidate" |
    "other_needs_human"
}
```

## 設計上の要点

1. **返答文生成との役割分離**: 本プロンプトは分類のみを担い、実際の返答文
   (完了報告書・FAQコマンドへの案内文・エスカレーション時の顧客向け定型応答)は
   生成しない。course-set-pashaのchatbot-intent-classification-llm-prompt-draft.md
   (フェーズ237)と同じ設計方針。
2. **`faq_guidance_candidate`判定時の応答はFAQ回答文そのものではなく案内文**:
   chatbot-first-response-feasibility.md 3節の判断(既存のコマンド方式FAQ回答資産
   〈`owner_faq_router.py`のQ1〜Q7〉をそのまま活かし、意図分類はコマンドへの案内文
   誘導に絞る)を反映し、分類カテゴリ名を`faq_pricing`/`faq_howto`/`faq_cancel_change`
   のようなFAQ項目別の細分類にはしていない。理由は、細分類してもLLMには回答文を
   生成させず「FAQ」コマンドへの案内文(定型文、項目を問わず同一)を返すだけであれば、
   項目を特定する分類粒度自体が不要になり、誤判定リスク(判定順位2の複合トピック等)を
   減らせるため。
3. **判定順位の明文化**: course-set-pasha方式(chatbot-intent-classification-
   escalation-design.md 2節)と同じ「中核機能〈完了報告書生成〉を最優先」「FAQと
   other_needs_humanの判別に迷えばother_needs_human」の優先順位を踏襲した。
4. **コマンド方式との二重判定を避ける前提**: 本プロンプトは「FAQ」「Q1」〜「Q7」の
   完全一致に外れた入力のみを受け取る前提(上記「位置づけ」節)であるため、プロンプト
   自身にコマンド文字列の除外ロジックは含めていない。仮に本プロンプトの呼び出し順序が
   将来変更され、コマンド判定より先に本プロンプトが呼ばれる構成になった場合、
   「FAQ」という1単語のみの入力は`faq_guidance_candidate`と判定される可能性が高いが、
   その場合でも案内文(「よくある質問は『FAQ』と送信すると一覧から選べます」)を
   返すだけであり、契約者が既に送った「FAQ」を再度促す冗長な応答にとどまる
   (誤った情報を返すわけではない)ため、実害は小さいと判断する。
5. **想定される誤判定パターン(未検証)**: 「新しい完了報告メモと一緒にプランのことも
   聞きたい」のような複合入力は、判定順位1によりcompletion_report_requestに判定される
   想定だが、この場合FAQ案内文の提示が欠落する。course-set-pashaが
   `append_faq_followup_hint()`(フェーズ238)で解消したのと同じ運用回避
   (completion_report_request判定時の返答文末尾に「ご質問があれば『FAQ』とお送り
   ください」等の一言を添える)が本venture向けにも必要になる可能性が高いが、本
   ドキュメントでは設計せず次回以降の課題とする。

## 残課題

- 本プロンプトは実LLM呼び出し・実顧客サンプルなしの机上設計にとどまる。実際の分類精度
  (特にcompletion_report_requestとfaq_guidance_candidateの境界、判定順位1の複合入力時の
  挙動)は、実LLM接続後の検証が別途必要。
- `faq_guidance_candidate`判定時に実際に返す案内文の具体的な文面、および
  completion_report_request判定時への一言追加(上記「設計上の要点」5参照、
  course-set-pashaの`append_faq_followup_hint()`相当)の実装は未着手。
- `other_needs_human`判定時のエスカレーション導線(運営者への通知文言・送信経路)は、
  course-set-pashaのchatbot-intent-classification-escalation-design.md 3節に相当する
  設計が本venture向けにまだ存在しない。本venture既存の
  `payment-suspension-owner-notification-design.md`(フェーズ255)の通知先
  (`OWNER_LINE_USER_ID_PLACEHOLDER`)・文言パターンを流用できる可能性が高いが、次回
  以降の課題とする。
- `prototype/`配下への実装(分類結果の文字列を受け取り案内文・エスカレーションへ
  振り分けるマッピング層、course-set-pashaの`chatbot_intent_router.py`相当)は未着手。
- 実LLM API接続自体がオーナー承認が必要なアクション(APIキー取得・従量課金)に該当する
  ため、実際の呼び出し配線は未着手(line-reservation-aiのAPIキー取得に関する承認待ち
  事項、pending-approval.md 2026-07-31 13:58 UTC記載と同種の位置づけ)。
- kura-pashaも同型のコマンド方式FAQ実装済み(kura-pashaフェーズ126)であり、
  chatbot-first-response-feasibility.md(本venture版)4節が申し送った通り、本ドキュメント
  と同種の意図分類プロンプト設計はkura-pasha側でも同様に有効な可能性が高いが、
  kura-pasha固有のFAQ項目・顧客層(職人向け)を踏まえた検討は同venture側の次回以降の
  フェーズとして申し送る。
