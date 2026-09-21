# チャットボット一次受付: 意図分類LLMシステムプロンプト草案(2026-09-21 定例更新フェーズ237)

chatbot-intent-classification-escalation-design.md(フェーズ235)「残課題」に
「自由入力テキストを実際に5分類へ振り分けるLLM呼び出し自体は引き続き未実装」として
残っていた論点に着手する。フェーズ236で実装した`prototype/chatbot_intent_router.py`
(分類結果の文字列を受け取った後段のマッピング・通知処理)の前段にあたる、
LLMへ渡す分類用システムプロンプトの文面を設計する。実装・実LLM呼び出し・実LINE接続は
行わない、机上のプロンプト文面設計のみとする。

## 位置づけ

- 入力: 顧客(ボルダリングジムオーナー・セッター)からのLINEメッセージ本文(自由文)。
- 出力: `chatbot-intent-classification-escalation-design.md` 1節で定義した5分類
  (`post_generation_request` / `faq_pricing` / `faq_howto` / `faq_cancel_change` /
  `other_needs_human`)のいずれか1つを表す構造化出力(JSON)。
- 出力を受け取った後段の処理(FAQコードへのマッピング・エスカレーション通知)は
  フェーズ236で実装済みの`chatbot_intent_router.py`側の役割であり、本ドキュメントは
  分類そのものを行うLLM呼び出し部分のみを対象とする。

## システムプロンプト草案

```
あなたは個人経営のボルダリングジム・クライミングジムのオーナー・ルートセッターから
LINE公式アカウントに届いたメッセージを読み、次の5つのカテゴリのいずれか1つに
分類するアシスタントです。分類結果のみを判定し、メッセージへの返答文自体は生成
しません。以下の判定順位を厳守してください。

【分類カテゴリ】
- post_generation_request: 課題(ルート)入れ替え後のメモ(エリア・テープ色・
  グレード帯・本数・ムーブの特徴・改訂日等)を含む、投稿文生成依頼。
- faq_pricing: 料金プラン・トライアル条件に関する質問。
- faq_howto: 使い方(入力の仕方、生成結果の確認方法等)に関する質問。
- faq_cancel_change: 解約・プラン変更に関する質問。
- other_needs_human: 上記いずれにも明確に該当しない、または判定に確信が持てない
  場合。

【判定順位(厳守)】
1. メモらしき内容(種目名・エリア名・色・グレード帯・本数・ムーブの特徴・改訂日
   等、課題入れ替えを示唆する要素)が少しでも含まれる場合は、他のカテゴリの
   言い回し(「プランについて」等)が同時に含まれていても、必ず
   post_generation_requestと判定する。本サービスの中核機能を妨げないことを
   最優先する。
2. 1に該当しない場合、料金・使い方・解約のいずれかのFAQトピックに明確に一致する
   ときのみ、対応するfaq_*カテゴリと判定する。複数のFAQトピックにまたがる、
   または特定のトピックを絞り込めない曖昧な質問・不満は、誤ったFAQ定型文を
   返すよりother_needs_human側へ倒す。
3. 1にも2にも該当しない場合はother_needs_humanと判定する。

【出力形式】
次のJSON形式のみを出力し、他の文字列(説明・挨拶等)は一切含めないこと。

{
  "category": "post_generation_request" | "faq_pricing" | "faq_howto" |
    "faq_cancel_change" | "other_needs_human"
}
```

## 設計上の要点

1. **返答文生成との役割分離**: 本プロンプトは分類のみを担い、実際の返答文(投稿文・
   FAQ定型文・エスカレーション時の顧客向け定型応答)は生成しない。分類結果を
   `chatbot_intent_router.py`の`faq_intent_to_code()`・
   `render_chatbot_faq_response_message()`・`send_chatbot_escalation_notification()`
   に渡し、後段の関数が定型文を組み立てる設計を維持する(分類とテンプレート文言の
   二重管理を避けるという既存方針、chatbot-intent-classification-escalation-design.md
   1節を踏襲)。
2. **判定順位の明文化**: chatbot-intent-classification-escalation-design.md 2節の
   フェイルセーフ方針(「post_generation_requestを最優先」「FAQとother_needs_human
   の判別に迷えばother_needs_human」)を、そのままプロンプト内の【判定順位】として
   逐語的に反映した。モデルの暗黙の判断に委ねず明示的に記述する方針は、
   line-reservation-aiのllm-system-prompt-draft.md群が確立した「厳守事項の明文化」
   と同じ考え方(本ドキュメント冒頭でも参照した既存方針)。
3. **構造化出力の単純化**: 投稿文生成本体のllm-system-prompt-draft.mdが多段の
   構造化出力(SNS投稿文・LINE告知文・履歴表の3出力)を要求するのに対し、本プロンプトは
   単一のcategoryフィールドのみを返す単純な分類タスクにとどめた。理由は、分類自体を
   複雑にするとpost_generation_request最優先の判定順位が埋もれやすくなり、フェイル
   セーフの信頼性が下がるおそれがあるため。
4. **想定される誤判定パターン(未検証)**: 「新しい課題の写真だけ送って料金プランも
   知りたい」のような複合的な入力は、判定順位1によりpost_generation_requestに
   判定される想定だが、この場合FAQ部分(料金プラン)への回答が欠落する。実運用では
   post_generation_request判定時の返答文の末尾に「他にご質問があれば」等の一言を
   添えて再度問い合わせを促す運用回避が必要になる可能性があり、~~次回以降の検討課題と
   する。~~ → フェーズ238で`prototype/chatbot_intent_router.py`の
   `append_faq_followup_hint()`として実装済み(下記「残課題」参照)。

## 残課題

- 本プロンプトは実LLM呼び出し・実顧客サンプルなしの机上設計にとどまる。実際の
  分類精度(特にpost_generation_requestとfaq_howtoの境界、判定順位1の複合入力時の
  挙動)は、llm-quality-verification-plan.mdに準じた形での実LLM検証が別途必要。
- ~~「想定される誤判定パターン」節で挙げたFAQ部分の欠落への運用回避(返答文への
  一言追加)は未設計。~~ → フェーズ238で解消。`append_faq_followup_hint()`は
  どの入力がFAQ相当を含んでいたかを判定せず、post_generation_request判定時の返答文に
  常に一言を追加する設計とした(判定を試みるとpost_generation_request最優先という
  フェイルセーフの単純さが崩れるため)。ただし本関数自体はまだ実際の投稿文生成結果の
  返答文組み立て処理(実LLM接続待ちのため未実装)からは呼び出されておらず、接続時に
  忘れずに組み込む必要がある点は残課題として残す。
- `prototype/chatbot_intent_router.py`側への本プロンプトの接続(実際にLLM APIを
  呼び出しcategoryを取得する処理)は、他の投稿文生成本体と同様、実LLM API接続
  自体がオーナー承認が必要なアクション(APIキー取得・従量課金)に該当するため
  未着手。line-reservation-aiのAPIキー取得に関する承認待ち事項(pending-approval.md
  2026-07-31 13:58 UTC記載)と同種の位置づけとなる。
- 他venture(aircon-pasha・kura-pasha)への同種チャットボット一次受付検討の横展開は
  引き続き未着手(chatbot-intent-classification-escalation-design.md 4節と同じ残課題)。
