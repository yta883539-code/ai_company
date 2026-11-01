# 実LLM接続後の生成品質検証プラン(フェーズ51)

他6venture(aircon-pasha・course-set-pasha・event-komiguai-pasha・forklift-pasha・
kura-pasha・line-reservation-ai)はいずれもllm-quality-verification-plan.mdを作成済みだが、
本ventureには同種の文書が未作成のまま残っていた(フェーズ50のllm-system-prompt-draft.md
「残課題・次回候補」で記録したcross-venture parityギャップ)ため、本フェーズで新規作成する。

## 位置づけ

line-reservation-aiのllm-quality-verification-plan.mdと同じ目的・構成を踏襲する。ただし
本ventureはline-reservation-aiのような複数ターンの会話エンジン型ではなく、course-set-pasha・
aircon-pashaと同じ「当落確定後の一度きりの入力メモ→単発生成」型であり、かつ出力は自由文の
3点セットではなくschema/output.schema.jsonで定義された構造化フィールド(status分岐+
itinerary_draft/day_timetable/cost_estimate/hashigo_checkの4出力)である点が両系統とも異なる。
llm-system-prompt-draft.md「厳守事項」1〜7を実LLMに投入した際の検証観点を、オーナー承認後に
APIキーを取得し実LLM接続に着手する際、迷わず着手できるよう事前に整理する。本ドキュメント
自体の作成はAPIキー取得や課金を伴わないため承認不要な机上作業であり、実際のLLM API呼び出し
は既存の承認待ち事項の範囲内で未実施のまま変わらない。

## 検証観点(厳守事項・出力別)

現時点では他venture(course-set-pashaのoutput-samples-validation.md、line-reservation-aiの
conversation-samples-test-cases.md)に相当する、本venture向けの入力サンプル・期待出力の
対応表はまだ作成されていない(本ドキュメントの残課題として下記に記録)。将来そのサンプル
群を用意した際に、以下の観点ごとに合否判定する設計とする。

| # | 厳守事項(llm-system-prompt-draft.md) | 検証観点 | 判定方法 |
|---|---|---|---|
| 1 | 予約・決済代行は一切行わず、下書きである旨を明示 | 出力文中に「予約しました」「確保しました」等の既完了を装う表現が混入していないか | 人手のみ(否定の証明は機械チェック困難) |
| 2 | 会場名の完全一致照合(venue_matched) | venue-master-draft.mdの会場マスタと入力venue_name_inputが完全一致する場合のみtrueになっているか、false時に具体的な最寄り駅・徒歩目安を推測で補っていないか | 機械チェック(`venue_matched`の値と`nearest_station_note`の文言パターンの突き合わせ)+人手 |
| 3 | 費用見積りは概算・未入力項目はnull | 予算感の言及が無い項目(transport_yen/lodging_yen/goods_yen)がnullのまま保たれているか、`cost_estimate.note`に概算である旨の明記があるか | 機械チェック(各金額フィールドのnull有無と入力の有無の対応) |
| 4 | ハシゴ移動チェックの適用判定(applicable) | 複数公演への言及がある入力でのみ`applicable: true`になっているか、単一公演入力で`risk_level`・`note`がnullのままか | 機械チェック(`applicable`値と`risk_level`/`note`のnull有無の組み合わせ) |
| 5 | 入力不足時のinsufficient_input分岐 | 会場・日時・枚数・予算感等の必須項目が不足する入力で`status: "insufficient_input"`となり、4出力フィールドが全てnullか、`missing_fields_request`が不明項目を推測で埋めず再送を促す文言になっているか | 機械チェック(`status`値と4出力フィールドのnull有無)+人手(`missing_fields_request`の文面が具体的に不明項目を指しているか) |
| 6 | 対応範囲外(out_of_scope)分岐 | 空席・空室確認・予約代行・決済代行・会員管理等の依頼で`status: "out_of_scope"`となり、4出力フィールドが全てnullか、`out_of_scope_message`が断定的な対応可否(「対応できません」以上の具体的な代替案提示等、README.mdが明示していない範囲)に踏み込んでいないか | 機械チェック(`status`値と4出力フィールドのnull有無)+人手 |
| 7 | 入力に無い情報の推測禁止(チケット価格・グッズ価格・ホテル料金等) | 入力に明記されていない具体的な金額・施設名が出力中に新規に出現していないか | 人手のみ(否定の証明は機械チェック困難) |
| - | JSON出力のスキーマ適合性 | 出力が`schema/output.schema.json`の`required`・`additionalProperties: false`・各フィールドの型・enum制約を満たすか | 機械チェック(JSON Schemaバリデータ、他venture同様`validate_test_cases.py`相当の新規実装が必要) |

## 検証手順(承認後に着手する想定)

1. 他venture(line-reservation-aiのconversation-samples-test-cases.md、course-set-pashaの
   output-samples-validation.md)に相当する、本venture向けの入力メモサンプル(正常系:会場名が
   会場マスタに一致/不一致、予算感の記載あり/なし、単一公演/複数公演の組み合わせ、崩れ系:
   必須項目不足、対応範囲外の依頼混入)を新規に用意する(本ドキュメントでは未着手、次回候補
   (1)として記録)。
2. 他venture同様、`schema/output.schema.json`に対するJSON Schemaバリデータ
   (`validate_test_cases.py`相当)を新規実装する(本venture未着手、次回候補(2)として記録)。
   `required`・`additionalProperties`・enum制約に加え、status分岐と4出力フィールドの
   null有無の対応(cross-fieldルール)もline-reservation-aiの`validate_cross_field_rules()`
   と同じ方針で機械チェック対象に含める。
3. 1で用意したサンプルを実際にAPIへ投入し、返ってきた構造化出力を2のバリデータへ通す
   (型・必須項目・cross-fieldルールは機械チェックで即座に合否判定可能)。
4. 上表の「人手」判定項目(厳守事項1・7、`missing_fields_request`・`out_of_scope_message`の
   文面の妥当性)については、各ケースにつき最低3回ずつ生成し、3回中何回意図通りかを記録する。
   3回中1回でも厳守事項1・2・5・6・7に抵触する生成があれば「不合格」とし、プロンプト側の
   指示強化(具体例追加・禁止表現の明示等)を検討する基準とする(line-reservation-ai・
   aircon-pasha・course-set-pashaと統一した基準)。
5. 生成に要したトークン数を計測し、本venture未作成のllm-api-cost-estimate.md相当の
   コスト試算を別途作成する(本ドキュメントでは未着手、次回候補(3)として記録)。

## 他ventureとの差分

- line-reservation-aiは複数ターンにまたがる会話エンジン型だが、本ventureは当落確定後の
  単発入力→単発生成型であり、会話状態管理・複数ターンのシナリオハーネスは不要
  (llm-system-prompt-draft.md「位置づけ」で既に明記済みの方針どおり)。
- course-set-pasha・aircon-pashaは出力が自由文の3点セット(厳守事項9相当の絵文字・文体
  チェックがpost_generation_checks.pyで機械化済み)だが、本ventureの4出力は構造化
  フィールド(status分岐+オブジェクト/配列)であり、自由文の文体チェックより先に
  JSON Schema適合性のチェックが必要になる点がline-reservation-aiの会話エンジン型に近い。
  ただし本venture固有のvenue_matched判定(厳守事項2)・applicable判定(厳守事項4)は
  他venture6件のいずれにも存在しない分岐であり、本venture独自の検証項目となる。

## 残る未確定事項

- 入力サンプル・期待出力の対応表(他venture相当)が未作成(次回候補(1))。
- JSON Schemaバリデータ(他venture相当)が未実装(次回候補(2))。
- トークン数計測・コスト試算(llm-api-cost-estimate.md相当)が未作成(次回候補(3))。
- 「3回中1回でも不合格なら要改善」という基準は暫定であり、実測後に見直す(他venture共通の
  残課題と同じ)。
