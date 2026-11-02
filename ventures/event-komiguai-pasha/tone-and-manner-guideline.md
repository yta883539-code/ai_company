# メッセージ統一トーン&マナーガイドライン(フェーズ80)

forklift-pashaフェーズ200の定例更新で発見されたcross-venture parityギャップ
(tone-and-manner-guideline.md未作成)は、同フェーズでaircon-pasha・course-set-pasha・
kura-pasha・line-reservation-aiの4ventureについては解消済みと確認されたが、oshien-pasha・
本venture(event-komiguai-pasha)の2ventureは対象外のまま残っていた。oshien-pashaは
フェーズ50で別ギャップ(llm-system-prompt-draft.md未作成)を優先して解消したため、本フェーズで
本venture側の同ギャップを解消する。line-reservation-aiの構成(基本方針→用途別メッセージ
文言→未検証の仮説→次のステップ候補)を踏襲しつつ、aircon-pashaが整理した「依頼者向け/
業者向け」の宛先区分の考え方を、本venture固有の事情に合わせて再検証する。

## 他venture(aircon-pasha等)との前提の違い: 宛先は常に主催者本人1種類のみ

aircon-pasha・course-set-pashaは「業者が依頼者へ転送する文面」と「業者本人向けの操作案内」の
2種類の宛先を区別することが基本方針の出発点だった。本ventureはREADME.md・
one-time-checkout-no-account-design.md(フェーズ10)が前提とする通り、単発決済・アカウント
登録なしのB2C型サービスであり、主催者自身が入力し主催者自身が結果を受け取る構造しか持たない
(業者が依頼者へ転送する、のような第三者への転送ステップが存在しない)。したがって、本venture
には「宛先の区別」という基本方針そのものが不要であり、この点が他ventureとの最大の構造的差異
となる。その代わり、本venture固有の論点は「LLM生成物(4出力+定型応答3種)」と「LLM生成物以外の
運用メッセージ(結果ページ案内・問い合わせ返信・返金メール)」という"出典の異なる2系統の文言"が
同一の主催者へ送られる点であり、両系統でトーンがずれないことを本ガイドラインの主眼とする。

## 基本方針

1. **宛先区別は不要(上記の通り)。代わりに「LLM生成物系」と「運用メッセージ系」の出典が
   異なる文言群を、同一トーンに統一することを基本方針の中心に置く。**
   - LLM生成物系: `checklist`/`staffing_plan`/`notice_board_text`/
     `near_miss_record_template`(4出力)、`out_of_scope_message`・`missing_fields_request`・
     `fee_inquiry_note`(定型応答3種)。いずれもllm-system-prompt-draft.md(フェーズ3)・
     schema/output.schema.json(フェーズ5)で定義され、prototype/post_generation_checks.py
     (フェーズ28)の`check_no_emoji_anywhere()`で絵文字不使用が機械的に検証されている。
   - 運用メッセージ系: 結果ページの「保存期間終了」案内(result-page-ttl-access-design.md
     フェーズ14・47)、問い合わせ返信の下書き(inquiry-handling-design.mdフェーズ15・61)、
     生成失敗時の全額返金案内メール(ttl-expiry-result-delivery-refund-design.mdフェーズ12)。
     いずれも設計文書内の地の文として書かれており、LLM生成物系と異なり
     schema/output.schema.jsonの対象外、かつ`check_no_emoji_anywhere()`の検証対象外。
2. **文体は「ですます調」、絵文字は使用しない(厳守事項9)を両系統で統一する。**
   LLM生成物系は厳守事項9・`check_no_emoji_anywhere()`により機械的に保証されている
   (下記「既存文言の整合確認」参照)。運用メッセージ系は機械チェックの対象外のため、
   現時点では執筆時の目視確認のみに依存している(「未検証の仮説」参照)。
3. **謝罪表現の使いどころを、主催者側の過失の有無で区別する。**
   - 主催者側の過失によらない失敗(生成処理失敗による全額返金、TTL失効)は、
     ttl-expiry-result-delivery-refund-design.mdの「生成処理に失敗したため全額返金した」旨の
     案内のように、失敗した事実を率直に伝えたうえで次のアクション(再入力案内)を示す。
     line-reservation-ai・aircon-pasha同様「謝罪はしつこくしすぎない」方針を踏襲し、
     過度な謝罪(「大変申し訳ございません」等の重い表現)は用いない。
   - 主催者側の追加操作で足りる案件(再入力・再送、missing_fields_request)は、
     result-page-ttl-access-design.mdの「再度ご利用いただく場合はお手数ですが最初から
     お申し込みください」のように「お手数ですが」程度の軽い言い回しに留め、
     missing_fields_requestの既存文言(「これらをご入力の上、再度お送りください」)の通り
     謝罪語自体を含めない運用も許容する(事務的な再送依頼であり謝罪の要素が薄いため)。
4. **見出し記法(【】)は、主催者へ送る文言には使用しない。**
   aircon-pashaは業者向け注記に【ご確認のお願い】のような見出しを使う方針を持つが、本venture
   で実際に主催者へ送られる文言(4出力・定型応答3種・運用メッセージ系)を確認した結果、
   いずれも【】見出しは使用されていなかった。legal-notices-draft.mdの「【要記入】」は
   オーナー自身が記入する社内ドラフト用のプレースホルダーであり主催者への送信文言ではない
   ため対象外、initial-contact-message-draft.mdの件名「【ご協力のお願い】」はヒアリング
   候補者への初回コンタクト文面(主催者=顧客への送信ではない、別の宛先)であり、本venture
   サービス自体の出力メッセージには該当しないため、同様に対象外として区別する。したがって
   本venture全体の既定ルールを「主催者向け送信文言では見出し記号を使わない」と明文化する。
5. **安全管理に関する断定的な表現を避ける(厳守事項1・3由来)をトーンの一部として集約する。**
   警備計画の最終確定・入場制限の実施判断は主催者・警備責任者自身が行う一次案である旨を
   必ず明示し(厳守事項1)、入力メモから機械的に導ける強調であっても「このままでは危険です」
   等のAIによる独自の安全/危険の最終判定表現は用いない(厳守事項3)。この制約は4出力の
   トーンそのものの一部であり、運用メッセージ系には適用されない(運用メッセージ系は決済・
   データ保存期間等の事務連絡であり、安全判定に関する表現は元々含まれない)。

## 用途別文言一覧(既存文言の集約・確認)

| 用途 | 系統 | 出典 | 絵文字機械チェック | 見出し記号【】機械チェック | 謝罪度合い |
|---|---|---|---|---|---|
| 4出力(checklist等) | LLM生成物系 | llm-system-prompt-draft.md | 有(check_no_emoji_anywhere) | 有(check_no_heading_brackets_anywhere、フェーズ82) | なし(事務的注記のみ、厳守事項1明示) |
| out_of_scope_message | LLM生成物系 | 厳守事項7/schema OOS1・OOS2 | 有 | 有 | なし |
| fee_inquiry_note | LLM生成物系 | 厳守事項7/schema G6 | 有 | 有 | なし |
| missing_fields_request | LLM生成物系 | 厳守事項8/schema II1 | 有 | 有 | なし(再送依頼のみ) |
| 結果ページ「保存期間終了」案内 | 運用メッセージ系 | result-page-ttl-access-design.mdフェーズ14・47 | 有(test_operational_message_templates.py、フェーズ82) | 有(同上) | 「お手数ですが」 |
| 問い合わせ返信下書き(再送/再生成・返金提示) | 運用メッセージ系 | inquiry-handling-design.mdフェーズ15・61・83 | 有(同上) | 有(同上) | 類型1:謝罪語なし/類型2:率直な事実提示+謝罪は控えめ/類型3:顧客向け文言なし(要約のみ) |
| 生成失敗時の全額返金案内メール | 運用メッセージ系 | ttl-expiry-result-delivery-refund-design.mdフェーズ12 | 有(同上) | 有(同上) | 率直な事実提示+謝罪は控えめ |

## 既存文言の整合確認

- LLM生成物系7フィールドは、prototype/test_post_generation_checks.py(フェーズ28)の
  `test_emoji_in_out_of_scope_message_is_flagged`等6件のテストケースが、意図的に絵文字
  (🙏)を混入させた入力でエラー検出されることを確認済みであり、厳守事項9との整合は機械的に
  保証されている。見出し記号(【】)・謝罪語の過不足についても、schema/validate_test_cases.py
  の既存サンプル(例: `missing_fields_request`「会場キャパシティ(capacity)と入退場口数
  (entry_exit_points)の記載が見当たりません。これらをご入力の上、再度お送りください。」)を
  確認した結果、方針3・4と矛盾しないことを確認した。
- 運用メッセージ系3件(結果ページ案内・問い合わせ返信下書き・返金案内メール)は、設計文書内の
  地の文を確認した結果、いずれも絵文字不使用・見出し記号不使用で方針2・4と矛盾しないことを
  目視で確認した。フェーズ81でこれらをoperational_message_templates.TEMPLATESとして定数化
  した後、フェーズ82で`post_generation_checks.py`の`EMOJI_PATTERN`・
  `HEADING_BRACKET_PATTERN`を再利用する`test_operational_message_templates.py`の機械チェック
  (`TestOperationalMessageTemplatesNoEmoji`・`TestOperationalMessageTemplatesNoHeadingBrackets`)
  を追加し、「目視確認のみ」の限界を解消した。あわせてLLM生成物系7フィールドについても、
  従来は絵文字のみ機械チェック対象だった`post_generation_checks.py`に
  `check_no_heading_brackets_anywhere()`(フェーズ82新設)を追加し、`run_all_checks()`
  経由で見出し記号【】不使用も機械的に保証されるようにした。

## 未検証の仮説(要検証)

- 問い合わせ返信下書き(inquiry-handling-design.mdフェーズ15・61・83)は、フェーズ83で
  類型1・2の顧客向け文言を固定文言として確定し(都度のAI生成に委ねる範囲は再送用リンク等の
  差し込みのみに縮小)、類型3は顧客向け文言自体を生成しない設計であることを明確化した。
  一方、固定文言化した文例が実際の問い合わせフロー実装・実LLM接続後も意図通りに機械的検証
  (絵文字・見出し記号不使用)の対象として組み込まれるかは、問い合わせフォーム自体が未実装
  (inquiry-handling-design.md 4節)のため引き続き未検証のまま残る。
- 本ventureの対象顧客(警備・安全管理の専任担当者を置かない個人〜小規模主催者)が、
  事務的・断定を避けるトーン(方針2・5)をどう受け取るか(安心材料として好意的に受け取るか、
  逆に「踏み込みが浅い」と感じるか)は、customer-interview-design.mdのヒアリング実施
  (オーナー承認待ち)まで引き続き未検証のまま残る。

## 次のステップ候補

- 問い合わせフォーム自体の実装後、類型1・2の固定文言(inquiry-handling-design.md 3-1節)が
  post_generation_checks.pyまたはoperational_message_templates.py系の機械チェック対象に
  正しく組み込まれるかを検証する(フェーズ83の未検証事項、上記参照)。
- 承認待ち事項(実GCP/Firestore作成、候補1〈奈良NEVER LAND〉への連絡等)がオーナーから
  承認された場合はその着手を最優先、他venture・アイデア領域の前進。

最終更新: 2026-11-02 06:00 UTC(フェーズ83: inquiry-handling-design.md(フェーズ83、
3-1節新規追加)に対応し、問い合わせ返信下書き3類型の「謝罪度合い」を用途別文言一覧表に
反映し、「未検証の仮説」・「次のステップ候補」を更新。コード変更なし(設計文書の更新のみ))

---

最終更新(旧): 2026-11-01 10:00 UTC(フェーズ80: tone-and-manner-guideline.md新規作成。
forklift-pashaフェーズ200で発見されたcross-venture parityギャップを解消。本ventureは
宛先区別が不要な単一宛先(主催者本人)構造である一方、LLM生成物系(機械チェック有)と
運用メッセージ系(機械チェック無・目視のみ)という出典の異なる2系統の文言が存在する点を
整理し、両系統の整合確認と未解消のギャップ〈運用メッセージ系の機械チェック未整備〉を
記録した。コード変更なし、回帰確認として`python3 -m unittest discover -s prototype -p
"test_*.py"`・`python3 schema/validate_test_cases.py`を実行し変更なしでパス)
