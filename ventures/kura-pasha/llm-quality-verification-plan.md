# 実LLM接続後の生成品質検証プラン(2026-09-12 19:00 UTC)

## 位置づけ

aircon-pasha/llm-quality-verification-plan.md(2026-08-21作成)・course-set-pasha/
llm-quality-verification-plan.mdと同じ位置づけの文書を、本ventureにはまだ存在していな
かったため新規作成する。schema/validate_test_cases.pyに机上検証用フィクスチャとして
既に27件(正常系19件+ネガティブ8件)が揃っているが、これらを実際にAPIキー取得・課金の
承認が下りた際にどう検証へ転用するかを事前に整理しておく文書が本venture単独では未着手
だった(kura-pasha自体はフェーズ93まで進み他venture並みの成熟度に達しているが、この
文書種別だけが横展開されていなかった)。本ドキュメントの作成・整理はAPIキー取得や課金を
伴わないため承認不要な机上作業であり、実際のLLM API呼び出しはこれまで通りオーナー承認
待ちのまま未実施(pending-approval.md参照)。

## 検証観点(厳守事項・出力別)

llm-system-prompt-draft.mdの厳守事項1〜8・7a・7bを対象に、schema/validate_test_cases.py
の19正常系ケースを実LLMに投入し、以下の観点ごとに合否判定する。

| # | 厳守事項 | 検証観点 | 判定方法 | 対象ケース |
|---|---|---|---|---|
| 1 | 厳守事項1(採寸・型紙作成・革選定等の専門判断に踏み込まない) | 入力メモの型・革の種類・金具仕様をそのまま前提とし、AIが独自に評価・提案する文言が混入していないか | 人手のみ(機械チェック不可、否定の証明ができないため) | G1・G2全件 |
| 2 | 厳守事項2(修理可否の判断をしない、備考欄はそのまま転記) | G2の備考欄(鐙革の縫い目のほつれ・金具のさび)が`order_summary.body`にそのまま転記され、修理可否についての評価的表現が付け足されていないか | 人手のみ | G2 |
| 3 | 厳守事項3(区分必須、欠落時は再送依頼) | II1(区分欠落)で`status=insufficient_input`となり区分の追記を促す文言になっているか、推測で区分を埋めていないか | 機械チェック(`status`値の一致)+人手(`missing_fields_request`の文言が区分を名指ししているかの目視) | II1 |
| 4 | 厳守事項4(納品案内は区分で出し分け) | `delivery_notice.category`が`order_summary.category`と一致し(new/repair)、本文が該当区分の内容(新規制作:皮革のなじませ方・締め具合調整・雨天時注意/修理:修理箇所説明・慣らし不要の旨)になっているか | 機械チェック(既存の`validate_cross_field_rules()`のcategory一致検証)+人手(本文が実際に区分どおりの内容かの目視) | G1(new)・G2(repair) |
| 5 | 厳守事項5(お手入れ案内は区分に関わらず共通、3要素を含む) | `care_notice`にオイル・クリームでの保湿、保管環境(カビ・ひび割れ防止)、金具のさび防止の3要素が含まれているか | 人手のみ(自由文であり機械チェックでの網羅確認は困難) | G1・G2共通 |
| 6 | 厳守事項6(会員管理等への不応答) | OOS1で3出力が全てnullのまま定型文言のみ返しているか | 機械チェック(`status=="out_of_scope"`時に`order_summary`/`delivery_notice`/`care_notice`が全てnullであることの確認) | OOS1 |
| 7 | 厳守事項7(入力不足時の再送依頼) | II1・II2で不足項目(区分/鞍の型)を具体的に指摘しているか、推測で埋めていないか | 人手のみ | II1・II2 |
| 7a | 厳守事項7a(解約意図検知、(i)〜(iv)の境界) | 解約・ダウングレード・雑談・判断不能の4分類が`status`(cancellation_intent/downgrade_intent等)へ意図通り反映されているか、特に(iv)判断不能時に解約完了・ポータルリンクを含む文言を自己判断で返していないか | 機械チェック(`status`値の一致)+人手((iv)応答文の目視) | C1・C2・C3 |
| 7b | 厳守事項7b(有料プラン開始意図検知、(i)〜(iv)の境界) | 開始意図・料金問い合わせ・雑談・判断不能の4分類が`status`(checkout_intent/pricing_inquiry等)へ反映され、`checkout_notice.includes_checkout_url`が常にfalseになっているか(実URLはPython側`handle_checkout_intent`に委ねる設計、7b(i)でもLLM側は自己判断でURLを含めない) | 機械チェック(`status`値+`includes_checkout_url`の一致)+人手((iv)応答文の目視) | CO1・CO2・CO3 |
| 8 | 厳守事項8(ですます調・絵文字不使用) | 絵文字が一切含まれていないか、文体が統一されているか | 機械チェック(post_generation_checks.py相当の絵文字パターン検出、本venture未実装分は本検証時に流用可否を確認) | 全件 |

上記に加え、member-retention-notice-design.md(M1・M2)・contractor-transfer-design.md系
(CT1・CT2・CTC1〜CTC3・CTE1)は、llm-system-prompt-draft.mdの番号付き厳守事項とは別の
専用設計文書で個別に検知ルールが定義されているため、各設計文書の「判定基準」節を参照した
上で同様に機械チェック+人手判定を行う(本表では割愛、実施時に各設計文書側へ検証結果を
追記する運用とする)。

## 検証手順(承認後に着手する想定)

1. 【2026-09-13 09:00 UTC確認済み】本venture固有の実装状況を確認した。
   `prototype/cloud_function_webhook.py`には既に`LlmCallClient(Protocol)`
   (`generate(memo_text, retry_context=None) -> dict`、失敗時`LlmApiError`送出)が
   aircon-pasha・course-set-pashaと同一のシグネチャ・契約で実装済みであることを確認した
   (差分なし)。よって本項の前提作業(Protocol差し替え口の整理)は完了しており、承認が
   下り次第、実クライアント実装(`LlmCallClient`を満たすAPI呼び出しラッパー)を用意する
   だけで本検証に着手できる状態にある。追加の前提作業は不要。
2. schema/validate_test_cases.pyの19正常系ケースの入力メモ文面(各ケースの
   `order_summary.body`相当の元メモ)を実際にAPIへ投入し、構造化出力を
   `validate_against_schema()`・`validate_cross_field_rules()`にそのまま通す(型・
   必須項目・cross-fieldルールは機械チェックで即座に合否判定可能)。
3. 上表の「人手」判定項目については、各ケースにつき最低3回ずつ生成し(同一入力でも生成
   結果がばらつく可能性があるため)、3回中何回意図通りかを記録する。3回中1回でも
   厳守事項1・2・5・7・7a(iv)・7b(iv)に抵触する生成があれば「不合格」とし、プロンプト
   側の指示強化を検討する基準とする(aircon-pasha・course-set-pashaの実LLM検証着手時と
   同じ基準を採用)。
4. 生成に要したトークン数を`count_tokens`(無料エンドポイント)で計測し、
   llm-api-cost-estimate.mdの想定シナリオに近いかを確認する(本venture固有の低頻度・
   高単価の受注特性を踏まえたコスト試算の実測による裏付け)。

## 記録先

aircon-pasha/course-set-pashaはllm-quality-verification-results-template.mdを別ファイル
として先に用意している。本ventureは検証未着手のため、実際に着手する段階で記録量を見て
本ファイルへの追記か別ファイル切り出しかを判断する(aircon-pashaフェーズ118と同じ判断
基準を踏襲)。

## 残る未確定事項

- 「3回中1回でも不合格なら要改善」という基準は他venture同様に暫定であり、実際の生成
  結果を見た上で緩め・厳しめのいずれに調整すべきかは実測後に見直す。
- 同一入力での生成ばらつきの許容範囲(temperature設定等)は実LLM接続時に検討する(本
  ドキュメントの範囲外)。
- member-retention-notice-design.md・contractor-transfer-design.md系のケース(M1・M2・
  CT1・CT2・CTC1〜CTC3・CTE1)を本表と同じ形式(厳守事項番号・検証観点・判定方法)で
  一覧化するかどうかは、各設計文書側の記述量が既に十分詳細なため、本文書に重複掲載せず
  参照のみにとどめるか次回以降に判断する。
