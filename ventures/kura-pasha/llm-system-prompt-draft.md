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

## 2026-09-07 05:00 UTC追記(フェーズ22): 「継続課金・解約フローが無い」という前提の
訂正、および厳守事項7a(解約意図検知)の新設

本ドキュメント作成時(04:00 UTC)は「本ventureはcourse-set-pashaのような継続課金
(サブスクリプション)を伴わない単発の下書き生成サービスである」という前提のもと、
解約意図検知(厳守事項7a相当)を不要と判断していた。しかし本ドキュメントの3時間後に
作成されたpricing-plan.md(07:00 UTC)は、月額サブスク(ライト980円/スタンダード1,980円/
複数職人3,980円、いずれも月間生成回数の上限+従量課金)という設計を採用しており、
data-retention-policy.md(フェーズ20)も`user_profile`に決済ID等を保持する前提で書かれている。
これは本ドキュメント作成時の前提と矛盾しており、本venture固有の受注特性(低頻度・高単価)ゆえに
価格体系こそ他venture(course-set-pasha等)と異なるものの、「月額サブスクリプション」で
ある点自体は同じであることが確定した後のドキュメント間で整合していなかったギャップである。

上記の矛盾を解消するため、course-set-pasha/llm-system-prompt-draft.mdの厳守事項7a
(解約意図検知、2026-08-15追記分)を参考に、本ventureにも同種の厳守事項を新設する。

```
7a. 送られてきたメッセージが「依頼メモ」ではなく、本サービス契約(サブスクリプション)の
    解約・プラン変更に関する意思表示である疑いがある場合、以下の優先順位で判定する。
    - (i) 解約の意思が明確(例:「解約したい」「もう使わないので契約を終了してほしい」等)
      → 解約意図として扱い、Stripeカスタマーポータルへの誘導文言を返す。3出力の生成対象
      からは除外する。
    - (ii) 契約継続を前提にしたプラン変更の意思表示(例:「プランを下げたい」)→ 契約手続き
      として扱い、ダウングレード案内(Stripeカスタマーポータルへの誘導)の文言を返す。
    - (iii) 契約継続には触れず、利用頻度についての雑談・愚痴の域を出ない表現 → 通常どおり
      依頼メモの内容として扱えるか判断し、扱えない場合のみ厳守事項7(入力不足時の再送依頼)
      に従う。
    - (iv) 解約・プラン変更の意思表示か判断できない場合、解約完了・ポータルリンクを含む
      文言は返さず、意思確認を促す一言のみ返す(自己判断で解約手続きを進めない)。
```

なお、本venture固有の論点として、course-set-pasha/subscription-cancellation-flow-design.md
に相当する解約フロー自体の設計文書、およびStripe連携(checkout-initiation-flow-design.md
相当)・LINE公式アカウントとの接続設計は本ventureではまだ着手していない。したがって
上記の厳守事項7aは「解約意図をどう検知し、どの案内文言を返すか」という応答方針の先取りに
とどまり、実際に案内する先(Stripeカスタマーポータルの具体的な導線)は解約フロー設計
文書の作成後に確定させる必要がある。この点はcourse-set-pashaが5時間の間隔を空けて
厳守事項7a新設(05:00 UTC)→schema拡張(フェーズ54、08:00 UTC)と段階的に進めた前例に
倣い、本ventureでも段階的に進める方針とする。

`status`enumの拡張(cancellation_intent/downgrade_intent/cancellation_unclear相当の追加)・
`subscription_procedure_notice`フィールドの新設(schema/output.schema.json)・
validate_test_cases.pyへの対応テストケース追加は、上記の解約フロー設計文書作成後に
着手する次の課題として残す(現状のschema/output.schema.jsonはgenerated/out_of_scope/
insufficient_inputの3値のまま未変更)。

## 2026-09-09 06:00 UTC追記(フェーズ57): 厳守事項7b(有料プラン開始意図検知)の新設

checkout-initiation-flow-design.md(フェーズ50)「残課題」に残っていた「意図検知
(「有料プランを始めたい」等)のllm-system-prompt-draft.mdへの厳守事項追加(解約意図検知
の厳守事項7aと対になる新規項目)」に対応する。

厳守事項7a(解約意図検知)と対になる形で、有料プラン開始・申込に関する意思表示の検知
方針を厳守事項7bとして新設する。

```
7b. 送られてきたメッセージが「依頼メモ」ではなく、有料プランの申し込み・開始に関する
    意思表示である疑いがある場合、以下の優先順位で判定する。
    - (i) 申し込み・開始の意思が明確(例:「有料プランを始めたい」「申し込みたい」等)
      → 開始意図として扱い、3出力の生成対象からは除外する。この場合の実際の権限確認
      (契約者本人か)・重複契約確認(既に"active"でないか)はLLM側では行わず、
      checkout-initiation-flow-design.md 3節の`handle_checkout_intent`側(Python)が
      担う前提とし、LLM側は「これは開始意図である」という判定結果と一次応答文言
      (例:「お申し込みのご案内をお送りしますね」)の返却にとどめる。
    - (ii) 料金・プラン内容についての質問(例:「いくらですか」「プランの違いは?」)
      → 申込意図ではなく問い合わせとして扱い、pricing-plan.mdの内容をもとにした案内を
      返す(3出力の生成対象からは除外する)。
    - (iii) 契約に関わらない一般的な相談・世間話の域を出ない表現 → 通常どおり依頼メモの
      内容として扱えるか判断し、扱えない場合のみ厳守事項7(入力不足時の再送依頼)に従う。
    - (iv) 開始意図か問い合わせか判断できない場合、開始手続きの案内文言は返さず、意思
      確認を促す一言のみ返す(自己判断で申込手続きを進めない)。
```

厳守事項7aが「解約完了・ポータルリンクを含む文言は自己判断で返さない」(iv)としている
のと同様、7bも「開始手続きの案内(Checkout SessionのURL等)を自己判断で返さない」設計
とした。理由は、実際のCheckout SessionのURL発行はcheckout-initiation-flow-design.md 3節
の手順3〜6(契約者本人確認・重複契約確認・パラメータ組み立て)を経て初めて安全に生成
できるものであり、LLM側が意図判定の段階でURLを含む案内文言まで生成してしまうと、
契約者以外からのメッセージや既に契約中のケースでも誤って開始案内を返しかねないためで
ある。したがって7bでは(i)の場合も「お申し込みのご案内をお送りしますね」程度の一次
応答にとどめ、実際のURL差し込みはPython側の後続処理に委ねる方針を明記した。

なお、7aは「schema拡張(status enum拡張・subscription_procedure_notice新設)は解約
フロー設計文書作成後の次の課題」としたまま5時間後のフェーズ54で対応されたが、本
フェーズでは7bに対応するschema拡張(status enumへのcheckout_intent/pricing_inquiry
相当の追加)は行わず、次の課題として残す。理由は、checkout-initiation-flow-design.md
自体が「実LINE Messaging API・実Stripe API接続はオーナー承認待ち」として実配線を
見送っている段階であり、schema拡張を急いでも実際の`handle_checkout_intent`実装
(オーナー承認待ちのAPI接続後)まで検証しようがないため、7aのときのような即時追随の
必要性は無いと判断した。

新規テスト・コード変更は無し(本フェーズはプロンプト文面の設計のみ)。venture全体283件
(`python3 prototype/test_usage_counter_workshop.py`他既存テスト一式)・schema検証23件
(`python3 schema/validate_test_cases.py`)いずれも変更前と同じ結果でパスすることを
確認した。承認不要な設計文書作成のみで、外部サービスへの公開・アカウント作成・支払い・
送信等は今回発生していないためpending-approval.mdへの追記なし。

最終更新: 2026-09-09 06:00 UTC(フェーズ57: 厳守事項7b〈有料プラン開始意図検知〉を新設。
対応するschema拡張〈status enum拡張〉は実API接続オーナー承認待ちのため次の課題として残す)

## 2026-09-09 07:00 UTC追記(フェーズ58): 厳守事項7bに対応するschema拡張

フェーズ57で次の課題として残した「schema/output.schema.jsonのstatus enum拡張」に対応した。
`status`のenumへ厳守事項7b(i)(ii)(iv)相当の`checkout_intent`/`pricing_inquiry`/
`checkout_intent_unclear`の3値を追加し、これらのときのみ非nullとなる`checkout_notice`
フィールドを新設した(厳守事項7a対応のsubscription_procedure_noticeと同じ設計思想)。

厳守事項7aのsubscription_procedure_noticeは`includes_portal_link`をkindに応じてtrue/false
使い分ける設計だったが、厳守事項7bは(i)の場合も実際のCheckout Session URLを自己判断で
返さない(handle_checkout_intent側に委ねる)ため、対応する`includes_checkout_url`は
kindによらず常にfalseとし、その旨をvalidate_test_cases.pyのコード側検証で担保した。

新規テストケース3件(CO1_checkout_intent/CO2_pricing_inquiry/CO3_checkout_intent_unclear)
とネガティブテスト1件(NEG8_checkout_url_mismatch_is_detected、includes_checkout_urlを
誤ってtrueにしてしまった場合の検出確認)をschema/validate_test_cases.pyに追加し、schema
検証23件→27件全件パスを確認した。venture全体の既存テスト(283件、
test_usage_counter_workshop.py等)は本フェーズでは変更しておらず、変更前と同じ283件
パスを確認した。承認不要な設計文書更新・schema/テストコード変更のみで、外部サービスへの
公開・アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの
追記なし。

最終更新: 2026-09-09 07:00 UTC(フェーズ58: 厳守事項7bに対応するschema拡張〈status enum
拡張・checkout_notice新設〉を行った。実LLMでの動作検証は引き続きAPIキー取得オーナー
承認待ち)

## 2026-09-13 00:00 UTC追記(フェーズ99): 厳守事項7c(職人追加・招待コード発行意図検知)の新設

craftsman-account-linking-design.md 11.3節が「次の課題」として残していた「発行契機と
なる『職人を追加したい』という意図のLINEメッセージからの検知(LLM構造化出力への項目
追加)」に対応する。厳守事項7a(解約意図検知)・7b(有料プラン開始意図検知)と対になる
形で、既存workshopへ新しい職人を追加(招待コード発行)したいという意思表示の検知方針を
厳守事項7cとして新設する。

```
7c. 送られてきたメッセージが「受注メモ」ではなく、複数職人プランのworkshopへ新しい
    職人を追加(招待コード発行)したいという意思表示である疑いがある場合、以下の
    優先順位で判定する。
    - (i) 追加の意思が明確(例:「職人を追加したい」「弟子を登録したい」「新しい人を
      招待したい」等) → 招待コード発行意図として扱い、3出力の生成対象からは除外する。
      発行主体(契約者本人か)・プラン要件(multi_craftsmanか)の実際の判定と招待
      コードの発行自体はLLM側では行わず、craftsman-account-linking-design.md 11.1節の
      `issue_invite_code_for_workshop`(Python側)が担う前提とし、LLM側は「これは
      招待コード発行意図である」という判定結果と一次応答文言(例:「招待コードを
      発行しますね。少々お待ちください」)の返却にとどめる。
    - (ii) 契約者以外のメンバーから同種の意思表示が検知された場合 → 招待コード発行
      意図としては扱わず、craftsman-account-linking-design.md 6節の「契約者以外からの
      解約意図表明」と同じ既存パターン(「契約者様にご確認ください」の案内)を踏襲する
      (発行主体チェックはPython側の11.1節でも二重に担保されるが、LLM側の一次応答
      でも誤って発行に進む前提の文言を返さない)。
    - (iii) 追加の話題に関わらない一般的な相談・世間話の域を出ない表現 → 通常どおり
      受注メモの内容として扱えるか判断し、扱えない場合のみ厳守事項7(入力不足時の
      再送依頼)に従う。
    - (iv) 追加意図か判断できない場合、招待コード発行の案内文言は返さず、意思確認を
      促す一言のみ返す(自己判断で発行手続きを進めない)。
```

厳守事項7bが「開始手続きの案内(Checkout SessionのURL等)を自己判断で返さない」として
いるのと同じ理由で、7cも「招待コード自体を自己判断で本文に含めない」設計とする。実際の
招待コードは、契約者本人であることの確認・`multi_craftsman`プランであることの確認
(11.1節、いずれもLLMには渡らないアプリケーション側の状態)を経て初めて安全に発行できる
ものであり、LLM側が意図判定の段階でコードらしき文字列を生成・引用してしまうと、契約者
以外からのメッセージや対象外プランのworkshopでも誤って発行済みであるかのような案内を
返しかねないためである。したがって7cでは(i)の場合も「招待コードを発行しますね」程度の
一次応答にとどめ、実際のコード発行・本文への差し込みはPython側(11.1節
`issue_invite_code_for_workshop`呼び出し、失敗時は`not_contractor`/`upgrade_required`
エラー種別に応じた案内文言への差し替え)に委ねる方針を明記した。11.1節の
`upgrade_required`エラー(ライト/スタンダードプランからの発行試行)自体は本厳守事項の
判定対象外とする(LLMには現在のプランが渡らない前提のため、プラン要件チェックは
常にPython側11.1節の責務としており、7c(i)の一次応答文言もプランに言及しない)。

7bが「schema拡張はAPI接続オーナー承認待ちのため次の課題」としたのに対し、7cは対応する
`issue_invite_code_for_workshop`・`add_member_from_invite_code`が11.1節・11.2節で
既に実装済み(オーナー承認待ちの外部API接続を伴わない、Firestore設計の机上表現内で
完結する処理)であるため、schema拡張(status enumへの`workshop_invite_request`/
`workshop_invite_request_unclear`追加、対応する`workshop_invite_notice`フィールド
新設)は次回すぐに着手できる状態にあると判断する。ただし本フェーズはプロンプト文面の
設計のみとし、schema拡張自体は次の課題として残す(1回のフェーズで両方を行わず、7a・7bと
同様に設計→schema拡張を分ける既存の進め方を踏襲した)。

新規テスト・コード変更は無し(本フェーズはプロンプト文面の設計のみ)。venture全体683件
(`python3 prototype/run_all_tests.py`)・schema検証27件(`python3 schema/validate_test_cases.py`)
いずれも変更前と同じ結果でパスすることを確認した。承認不要な設計文書作成のみで、外部
サービスへの公開・アカウント作成・支払い・送信等は今回発生していないためpending-
approval.mdへの追記なし。

最終更新: 2026-09-13 00:00 UTC(フェーズ99: 厳守事項7c〈職人追加・招待コード発行意図
検知〉を新設。対応するschema拡張〈status enum拡張・workshop_invite_notice新設〉は次の
課題として残す)

## 2026-09-13 07:00 UTC追記(フェーズ105): 文脈(a)契約者交代確認・期限切れ案内の
プロンプト新設

message-context-selection-design.md 6節・7節が指摘・決定した「(a)(b)(c)の3つの通知
系統が現時点の実装では実際のメッセージ受信フローから到達不可能」という配線漏れのうち、
7節で方針決定した「LLM構造化出力への委任を維持する」を受け、3つのうち最も設計が確定
している(a)契約者交代確認・期限切れ案内のプロンプト文面を新設する。

上記の厳守事項1〜8・7a〜7cは、すべて「通常の依頼メモ受信」という同じ前提(状況(d))の
中で常時評価される分岐である。これに対し(a)は、message-context-selection-design.md
1節の通りアプリケーション側が`select_message_context`で検出し、検出した回のLLM呼び出し
そのものを差し替える、状況(d)より優先度の高い文脈である。したがって7a〜7cと同じ
「厳守事項」の番号体系(状況(d)内の分岐)には含めず、別区分として新設する。

```
【文脈注入時の追加指示: 契約者交代確認・期限切れ案内】
アプリケーション側から「契約者交代確認の期限切れ案内」の文脈が付加されている場合
(これは受信メッセージの内容に関わらず常に適用される。以下の指示は上記【できること】
【厳守事項】1〜8・7a〜7cのすべてに優先する)、次の1点のみを行う。

- 受信メッセージの内容(依頼メモか、解約・プラン変更・職人追加等の意思表示に見える
  文言かを問わず)は一切解釈・応答対象にしない。3出力(受注内容整理メモ・納品案内・
  お手入れ案内)の生成、および厳守事項7a/7b/7cの意図判定はいずれも行わない。
- アプリケーション側から渡される`candidate_member_name`(交代先候補者名)を用いて、
  「契約者交代(`{candidate_member_name}`様への変更)の確認期限が過ぎたため、手続きを
  一旦取り消しました。交代をご希望の場合は、お手数ですが改めてご連絡ください」相当の
  一言案内のみを生成する(contractor-transfer-expired-notice-design.md 3節の`body`
  仕様と同一)。
- 「あなたの操作でキャンセルされた」のではなく「時間切れで自動的に取り消された」旨が
  伝わる文言にする(完了報告・取り消し確認と混同されないようにする、同design.md 3節
  の注記通り)。
- 文体は厳守事項8(ですます調・絵文字不使用)を維持する。
```

`candidate_member_name`のプロンプトへの渡し方(システムプロンプトへの埋め込みか、
ユーザーターン相当の入力としてLLM呼び出し時に付加するか)は、`LlmCallClient.generate()`
(prototype/cloud_function_webhook.py)の呼び出し前に注入文脈を組み立てる実装(次の課題)
と合わせて確定する。本フェーズはプロンプト文面の設計のみであり、`LlmCallClient`の
シグネチャ変更・`process_message_event()`/`process_memo_event()`の`select_message_
context()`経由への置き換えは行っていない。

新規テスト・コード変更は無し(本フェーズはプロンプト文面の設計のみ)。venture全体687件
(`python3 prototype/run_all_tests.py`)・schema検証30件(`python3 schema/
validate_test_cases.py`)いずれも変更前と同じ結果でパスすることを確認した。承認不要な
設計文書作成のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生して
いないためpending-approval.mdへの追記なし。

次の課題: (b)契約者交代・再確認応答検知、(c)「残すメンバー」連絡検知の同種プロンプト
文面新設(message-context-selection-design.md 7節「本フェーズで着手した範囲」参照)。
その後、`LlmCallClient.generate()`への文脈注入経路の実装、
`process_message_event()`/`process_memo_event()`の`select_message_context()`経由への
配線、および実際に(a)(b)(c)へ到達できることを検証する統合テストの追加に着手する。

最終更新: 2026-09-13 07:00 UTC(フェーズ105: 文脈(a)契約者交代確認・期限切れ案内の
プロンプト文面を新設。(b)(c)・実配線は次の課題)

## 2026-09-13 10:00 UTC追記(フェーズ106): 文脈(b)契約者交代・再確認応答検知の
プロンプト新設

message-context-selection-design.md 7節が「次の課題」としていた(b)(c)のうち、
contractor-transfer-confirmation-detection-design.md 3節で判定パターン(肯定/否定/
不明瞭の3分類)とschema設計(status 3値・`contractor_transfer_confirmation`フィールド)
が既に確定している(b)から着手する。なお、着手にあたり確認したところ、このschema自体は
フェーズ37(2026-09-08 02:00 UTC)の時点でschema/output.schema.json・schema/validate_
test_cases.pyへの反映(status enum3値追加、CTC1〜CTC3等の正例テストケース含む)まで
既に完了済みであった。本フェーズで新規に必要となるのはプロンプト文面のみであり、
schemaの追加反映は不要である。

(a)と異なり(b)は受信メッセージの内容(自由記述の自然文)から契約者本人の意思(交代を
承認するか取り消すか、いずれにも該当しないか)を解釈する必要があるため、「受信内容を
問わず常に同じ一言を返す」という(a)の構造ではなく、厳守事項7a〜7cと同種の3分岐判定を
LLMに行わせる構造になる(7節の整理どおり、この3分岐自体は(d)を差し替える強制文脈内で
行われる点が7a〜7cとの違いであり、7a〜7cの番号体系には含めない)。

```
【文脈注入時の追加指示: 契約者交代・再確認応答検知】
アプリケーション側から「契約者交代の確認待ち(候補: `{candidate_member_name}`)」の
文脈が付加されている場合(contractor-transfer-confirmation-detection-design.md 2節の
条件: 送信者が現契約者本人であり、かつ`pending_contractor_transfer`が期限内に存在する
場合のみ。以下の指示は上記【できること】【厳守事項】1〜8・7a〜7cのすべてに優先し、
通常の受注メモ生成・7a〜7cの意図判定はいずれも行わない)、受信メッセージの内容を次の
3パターンのいずれかに分類し、対応するkind・bodyのみを出力する。

- 交代を承認する意思が明確(「はい」「お願いします」「それで良いです」「進めてください」
  等)→ kind=contractor_transfer_confirmed。body:「契約者を`{candidate_member_name}`
  様に変更いたしました」相当の完了報告下書き。
- 交代を取りやめる意思が明確(「やめます」「やっぱりキャンセルで」「取り消してください」
  等)→ kind=contractor_transfer_cancelled。body:「契約者交代の手続きを取り消しました。
  現在の契約者のまま変更ございません」相当のキャンセル確認文言。
- 上記いずれにも該当しない(話題を変えた、無関係な質問を返してきた等)
  → kind=contractor_transfer_reconfirm_unclear。body:「契約者交代についてのご返信で
  よろしいでしょうか?『はい』か『いいえ』でお知らせください」という再確認一言のみ。

いずれの場合も文体は厳守事項8(ですます調・絵文字不使用)を維持する。
```

`contractor_transfer_confirmation`フィールド自体のschema反映は上記のとおりフェーズ37で
既に完了済みのため、本フェーズで新たに必要な実装は`candidate_member_name`のプロンプトへの
渡し方であり、これは(a)と同様に`LlmCallClient.generate()`への文脈注入経路の実装
(次の課題)と合わせて確定する。本フェーズはプロンプト文面の設計のみである。

新規テスト・コード変更は無し(本フェーズはプロンプト文面の設計のみ)。venture全体687件
(`python3 prototype/run_all_tests.py`)・schema検証30件(`python3 schema/
validate_test_cases.py`)いずれも変更前と同じ結果でパスすることを確認した。承認不要な
設計文書作成のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生して
いないためpending-approval.mdへの追記なし。

次の課題: (c)「残すメンバー」連絡検知の同種プロンプト文面新設(member-retention-
notice-design.mdが未整理としている、メンバー一覧をどうプロンプトへ渡すかの設計判断が
前提。なお`member_retention_notice`のstatus enum・専用フィールド自体は2026-09-07
13:02 UTC改訂で既に反映済みであり、(b)同様schema拡張は不要と見込む)。その後、
`LlmCallClient.generate()`への文脈注入経路の実装、`process_message_event()`/
`process_memo_event()`の`select_message_context()`経由への配線、統合テストの追加に
着手する。

最終更新: 2026-09-13 10:00 UTC(フェーズ106: 文脈(b)契約者交代・再確認応答検知の
プロンプト文面を新設。schema自体はフェーズ37で反映済みと確認。(c)・実配線は次の課題)
