# 実LLM接続後の生成品質検証プラン(2026-08-21 21:00 UTC)

## 位置づけ

aircon-pashaのllm-quality-verification-plan.md(2026-08-21 20:00 UTC作成)と同じ目的・構成を
course-set-pashaに展開したもの(aircon-pasha README.mdフェーズ98の申し送り「本プランを
course-set-pasha・line-reservation-aiにも同様の形で展開する」に対応)。output-samples-
validation.mdの「残る未検証事項」節、およびllm-system-prompt-draft.mdの「未検証事項」節に
持ち越されていた論点を、オーナー承認後にAPIキーを取得し実LLM接続に着手する際、迷わず着手
できるよう事前に整理する。本ドキュメント自体の作成・整理はAPIキー取得や課金を伴わないため
承認不要な机上作業であり、実際のLLM API呼び出しはこれまで通りオーナー承認待ちのまま未実施。

## 検証観点(厳守事項・出力別)

output-samples-validation.mdの5ケース(G1〜G3・OOS1・II1)およびschema/validate_test_cases.py
に追加済みのCI1〜CI3(厳守事項7a、解約意図検知の分岐)を実LLMに投入し、以下の観点ごとに
合否判定する。schema/validate_test_cases.pyのvalidate_cross_field_rules()、および
prototype/post_generation_checks.py(course-set-pasha配下に既存、後述)で機械チェック可能な
ものと、人手(オーナーまたは本エージェントによる目視)でしか判定できないものを区別する。

| # | 厳守事項 | 検証観点 | 判定方法 | 対象ケース |
|---|---|---|---|---|
| 1 | 厳守事項1(ルートセット作業・安全確認・グレーディングの当否に踏み込まない) | 入力メモのグレード・本数・特徴をそのまま前提とし、難易度や安全性を評価・修正する表現が混入していないか | 人手のみ(機械チェック不可、否定の証明ができないため) | G1〜G3全件 |
| 2 | 厳守事項2(「変更なし」エリアへの誤言及禁止) | unchanged_areasに列挙されたエリアについて、新着課題があるかのような表現が本文に混入していないか | 機械チェック(`unchanged_areas`と本文の突き合わせ、prototype/post_generation_checks.pyの`check_unchanged_areas_not_mentioned_as_new()`として実装済み)+人手 | G2(変更なしエリア2件を明記) |
| 3 | 厳守事項3(写真有無に応じた文面調整) | mentions_photo=true時に「写真の課題」への言及があるか、false時に「写真がない」ことへの言及が無いか | 機械チェック(`sns_post.mentions_photo`のtrue/false分岐)+人手(文面が実際に分岐通りか目視) | G2(写真言及あり) |
| 4 | 厳守事項4(出力1冒頭要約・ハッシュタグ優先順位・複数エリア列挙) | 色・グレード帯・本数のうち入力に明記されている項目のみで冒頭要約を構成しているか、複数組登録時に本文中のジム名言及に対応する組のタグを優先しているか、更新対象エリア3つ以上で簡潔化されているか | 人手のみ(粒度・優先順位の妥当性は機械チェック困難) | G1(明示)・G3(本数・改訂日抽出不可) |
| 5 | 厳守事項5(出力2は端的に箇条書き、出力1との役割重複回避) | エリア・本数・改訂日が箇条書きで整理され、出力1と同一の紹介文的表現を繰り返していないか | 人手のみ | G1〜G3全件 |
| 6 | 厳守事項6(出力3は表形式・history_rowsが更新エリア数と一致) | history_rowsの要素数が実際の更新エリア数と一致しているか | 機械チェック(要素数カウント) | G1(1件)・複数エリア同時更新ケース(要新規サンプル追加) |
| 7 | 厳守事項7(会員管理・予約受付・決済への不応答) | 対象外の定型文言のみを返し、3出力を生成していないか | 機械チェック(`status=="out_of_scope"`時に3出力フィールドが全てnullであることの確認) | OOS1 |
| 7a | 厳守事項7a(解約意図検知、(i)〜(iv)の境界) | 解約明確・プラン変更・雑談・判断不能の4分類が意図通り`status`(cancellation_intent/downgrade_intent/cancellation_unclear)へ反映されているか。特に(iii)雑談を解約意図と誤認しないか、(iv)判断不能時にポータルリンクを含めていないか(`includes_portal_link`) | 機械チェック(`status`値・`includes_portal_link`の一致)+人手((iv)応答文が断定的な案内になっていないかの目視) | CI1〜CI3 |
| 8 | 厳守事項8(入力不足時の再送依頼) | 不足項目を具体的に指摘しているか、推測で埋めていないか | 人手のみ | II1 |
| 9 | 厳守事項9(ですます調・絵文字は出力1のみ1〜2個まで) | 出力2・出力3に絵文字が含まれていないか、出力1の絵文字が2個を超えていないか、文体が統一されているか | 機械チェック(prototype/post_generation_checks.pyの`check_emoji_usage_rules()`として出力別上限つきで実装済み) | 全件 |

## aircon-pashaとの差分

- 訂正(2026-08-21 22:00 UTC): 本節は作成時(フェーズ87)、course-set-pashaにはaircon-pasha
  post_generation_checks.py相当の`unchanged_areas`本文突き合わせ・絵文字上限チェックが
  「まだ存在しない」「移植が必要」と誤って記載していた。実際にはcourse-set-pasha/prototype/
  post_generation_checks.pyに`check_unchanged_areas_not_mentioned_as_new()`(2026-08-09追加)・
  `check_emoji_usage_rules()`(2026-08-09追加、出力ごとに上限を分けて実装済み)が既に存在し、
  対応するテスト(test_post_generation_checks.py)も含め本ventureの既存テスト190件に含まれて
  実行・パス済みであることを確認した(フェーズ87時点でoutput-samples-validation.mdの
  「残る未検証事項」節を参照した際に見落としたことが原因と推測される)。course-set-pashaは
  aircon-pashaより先にpost_generation_checks.pyを持っていたため、今回の「展開」はむしろ
  course-set-pasha側の既存実装がaircon-pashaへの移植元だった可能性がある(要fact確認だが
  優先度は低い)。
- course-set-pashaは出力1のみ絵文字1〜2個を許容する点がaircon-pasha(全出力で絵文字不使用)と
  異なる。上記の通りこの差異は既にcheck_emoji_usage_rules()内で出力ごとの上限分けとして
  実装済み。
- 厳守事項7a(解約意図検知)はcourse-set-pasha固有の分岐であり、aircon-pashaのプランには
  存在しない。CI1〜CI3はcourse-set-pasha向けに新規追加する検証項目。

## 検証手順(承認後に着手する想定)

1. `prototype/`配下のllm_callスタブ相当の関数に実API呼び出し(Claude API)を注入する
   (line-reservation-aiの`engine.py`llm_callスタブと同じ設計方針を踏襲)。
2. output-samples-validation.mdの5ケース+CI1〜CI3の入力メモ文面を実際にAPIへ投入し、
   構造化出力をschema/validate_test_cases.pyのバリデータにそのまま通す。
3. 上表の「人手」判定項目については、各ケースにつき最低3回ずつ生成し、3回中1回でも厳守事項
   1・4・5・8・7a(iv)に抵触する生成があれば「不合格」とし、プロンプト側の指示強化を検討する
   基準とする(aircon-pashaで提案した基準と統一)。
4. 生成に要したトークン数を`count_tokens`(無料エンドポイント)で計測し、llm-api-cost-estimate.md
   の試算に対する実測での裏付けを行う。

## 残る未確定事項

- 「3回中1回でも不合格なら要改善」という基準は暫定であり、実測後に見直す(aircon-pashaと共通)。
- (解消済み 2026-08-22 06:00 UTC: output-samples-validation.mdが作成時(2026-08-07)のG1〜G3・
  OOS1・II1の5件のみを記載したまま、その後追加されたG4(複数エリア同時更新、フェーズ11)・
  CI1〜CI3(厳守事項7a関連、フェーズ54)が未反映だったドキュメント齟齬を発見・修正した。
  schema/validate_test_cases.pyの実装は全9件パス済みで変更なし、output-samples-validation.md
  側の記載を実装に合わせて更新したのみ)。
