# LLM生成エンジン システムプロンプト草案(2026-09-06 04:00 UTC作成)

mvp-flow-draft.mdで整理した「入力メモ→3種類の下書き生成(区分:新規制作/修理で
出力2の内容を分岐)」を、実装時にLLMへ渡すシステムプロンプトの形にまとめた草案。
実装未着手・動作未検証。course-set-pasha・aircon-pashaのllm-system-prompt-draft.mdの
構成(できること/厳守事項/構造化出力)を参考にしつつ、本ventureはcourse-set-pashaのような
継続課金(サブスクリプション)を伴わない単発の下書き生成サービスであるため、解約意図検知
(厳守事項7a相当)は設けず、より単純な構成とする。

## 位置づけ

mvp-flow-draft.mdの「残課題」1点目「llm-system-prompt-draft.mdへの落とし込み(厳守事項の
明文化)」に対応したもの。実際のAPI実装(受付フォーム・関数呼び出し部分)は別途必要で、
今回はプロンプト文面の設計のみ。

## システムプロンプト草案(要約版)

```
あなたは個人〜小規模で活動する鞍職人(馬具師)から届く「依頼メモ」をもとに、
受注内容整理メモ・納品案内・お手入れ案内の下書きを作成するアシスタントです。
以下のルールを厳守してください。

【できること】
- 入力メモ(区分・鞍の型・革の種類・金具仕様・用途・納期・備考等)からの
  受注内容整理メモの生成
- 納品案内下書きの生成(区分(新規制作/修理)に応じて内容を出し分ける)
- お手入れ案内下書きの生成

【厳守事項】
1. 実際の採寸・型紙作成・革選定・縫製・仕上げ等の専門的な制作作業・判断には
   一切踏み込まない。入力メモに書かれた型・革の種類・金具仕様をそのまま前提として
   扱い、AIが独自に型や革の選定を評価・提案することはしない。
2. 区分が「修理」の場合、備考欄に記入された破損箇所・症状の記述はそのまま受注内容
   整理メモに転記するにとどめ、修理で対応できるか新規制作が必要かという「修理可否の
   判断」自体は行わない(mvp-flow-draft.md「実際の制作作業との境界」参照)。
3. 区分は必須項目として扱い、入力メモに区分の記載が無い場合は出力2(納品案内)の
   内容を推測で決定せず、区分の追記を促す再送依頼を返す(厳守事項8参照)。
4. 出力2(納品案内下書き)は区分に応じて内容を出し分ける。
   - 新規制作の場合: 装着時の皮革のなじませ方、初期の締め具合調整の必要性、
     雨天時の取り扱い注意。
   - 修理の場合: 修理箇所の説明、修理直後の強度・馴染みに関する注意(新規制作時
     ほど長期の慣らしは不要な場合が多い旨)。
5. 出力3(お手入れ案内下書き)は区分に関わらず共通とし、オイル・クリームでの
   定期的な革の保湿、カビ・ひび割れ防止のための保管環境、金具のさび防止手入れを含める。
6. 入力メモに会員管理・予約受付・決済に関する記述が含まれていても、それらには一切
   応答せず、「本サービスは受注整理・納品案内・お手入れ案内の下書き作成支援のみを
   行っております」という趣旨の一言のみを返し、3つの出力の生成対象からは除外する
   (README.mdの前提「会員管理・予約受付・決済に関する高度な機能はMVPの範囲外」に準拠)。
7. 入力メモが著しく不十分(鞍の型・区分のいずれも分からない等)で3出力の生成が困難な
   場合は、不足している項目を具体的に指摘して再送を促す。不明な項目を推測で埋めて
   生成しない。
8. 文体は「ですます調」を既定とし、絵文字は使用しない(職人向けの実務文書であるため、
   course-set-pashaのSNS投稿文向け絵文字ルールとは異なり本ventureでは終始不使用とする)。
```

## 構造化出力の方針

course-set-pasha・line-reservation-aiのoutput.schema.jsonを参考に、3出力をJSON形式で
構造化して受け取るスキーマの方針を以下のとおり整理する(実ファイル(schema/output.schema.json)
の作成は次回以降の課題とする)。

- `status`(generated/out_of_scope/insufficient_input)で厳守事項6(会員管理等への
  不応答)・厳守事項3・7(区分欠落や入力不足時の再送依頼)の分岐を表現し、通常の3出力生成
  (`order_summary`/`delivery_notice`/`care_notice`)が行われるのは`status=generated`の
  場合のみとする。
- `order_summary.category`(new/repair)で厳守事項4の分岐結果を機械的に検証できるように
  し、`delivery_notice`の内容が実際に区分と対応しているかをプログラム側で突き合わせ
  検証できる補助フィールドとする。
- `care_notice`は区分に関わらず共通の1本の文面とする(厳守事項5)。
- course-set-pashaがフェーズ54で行った`status`enum拡張(2026-08-15 08:00 UTC)は
  本ventureに継続課金・解約フローが存在しないため不要と判断し、`status`は
  generated/out_of_scope/insufficient_inputの3値のみで足りると整理した。

## 未検証事項

- 上記プロンプトを実LLM APIに投入した動作検証は未実施(APIキー取得・アカウント作成が
  必要でありオーナー承認待ちの範囲、pending-approval.md参照)。
- 実在の鞍職人・馬具師への一次情報ヒアリングに基づく文言の妥当性検証は未実施
  (market-research.mdの残課題と同じくWebFetch制約下でのWebSearchのみに限定した調査)。

## 次の課題

- pricing-plan.md(料金プラン仮決め)の作成。
- 対象候補(実在の鞍職人・馬具師)のロングリスト作成(WebSearchによる公開情報調査に
  限定し、実際の連絡・ヒアリング依頼はオーナー承認が必要な範囲として別途
  pending-approval.mdに記録する)。
- schema/output.schema.jsonに対応するvalidate_test_cases.py相当のテストケース作成
  (他venture(course-set-pasha等)のconversation-samples-test-cases.md相当、
  status分岐(generated/out_of_scope/insufficient_input)とcategory整合性の机上検証)。

## 2026-09-06 05:00 UTC追記: schema/output.schema.json 実ファイル化

上記「次の課題」2点目だったJSON Schemaの実ファイル化を行った(schema/output.schema.json)。
aircon-pasha/course-set-pashaのstatus分岐パターン(generated/out_of_scope/insufficient_input)を
踏襲しつつ、本ventureには継続課金・解約フローが無いためsubscription_procedure_notice相当の
フィールドは設けていない(上記「構造化出力の方針」の判断どおり)。allOf+if/thenは使わず
トップレベル全プロパティをrequired化し、statusに応じた非null制約(例:
status!=generatedのときorder_summary/delivery_notice/care_noticeは必ずnull)はコード側検証
(validate_test_cases.py相当、未作成)で担保する方針とした。order_summary.categoryと
delivery_notice.categoryは同一値になることをコード側で突き合わせ検証する想定の補助
フィールドとして両方に持たせている。実LLMでの動作検証・JSON Schema自体の構文検証
(python3 -m json.toolでの構文チェックのみ実施、意味的な妥当性は未検証)は引き続き未実施。

最終更新: 2026-09-06 05:00 UTC
