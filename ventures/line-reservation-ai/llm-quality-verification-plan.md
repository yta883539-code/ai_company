# 実LLM接続後の生成品質検証プラン(2026-08-22 00:00 UTC)

## 位置づけ

aircon-pashaのllm-quality-verification-plan.md(2026-08-21 20:00 UTC作成)・course-set-pashaの
同名ファイル(2026-08-21 21:00 UTC作成、22:00 UTC訂正)と同じ目的で、line-reservation-aiに
展開したもの(aircon-pasha README.mdフェーズ98の申し送り「本プランをcourse-set-pasha・
line-reservation-aiにも同様の形で展開する」に対応)。

ただしline-reservation-aiは他2ventureと異なり、自然文の完了報告・案内文を生成する
「メモ→複数下書き」型ではなく、予約会話の意図分類・構造化出力(intent/confirmed/faq_segments等)
を毎ターン返す会話エンジン型である。そのため機械チェックの主対象もpost_generation_checks.py
相当の自由文チェックではなく、schema/validate_test_cases.py・prototype/engine.pyの
`process_llm_output()`が扱う構造化フィールドの妥当性検証が中心になる。llm-system-prompt-
draft.mdの「未検証・要検討事項」節に持ち越されていた論点を、オーナー承認後にAPIキーを取得し
実LLM接続に着手する際、迷わず着手できるよう事前に整理する。本ドキュメント自体の作成・整理は
APIキー取得や課金を伴わないため承認不要な机上作業であり、実際のLLM API呼び出しはこれまで通り
オーナー承認待ちのまま未実施(pending-approval.md 2026-07-31 13:58 UTC記載の範囲)。

## 検証観点(厳守事項・出力別)

conversation-samples-test-cases.mdの正常系(N1〜N4・N3-トーン・トーン別サンプル)・崩れ系
(E1〜E18)を実LLMに投入し、以下の観点ごとに合否判定する。schema/validate_test_cases.pyの
`validate_against_schema()`・`validate_cross_field_rules()`で機械チェック可能なものと、
人手(オーナーまたは本エージェントによる目視)でしか判定できないものを区別する。

| # | 厳守事項 | 検証観点 | 判定方法 | 対象ケース |
|---|---|---|---|---|
| 1 | 厳守事項1(名前・メニュー・日時の3点が揃うまで確定文言を使わない) | 3点が未充足の間、自然文に「予約を確定しました」等の確定表現が出ていないか、`confirmed`がfalseのままか | 機械チェック(`confirmed`フィールドの値)+人手(自然文が実際に確定を匂わせる表現になっていないかの目視) | N2(情報不足) |
| 2 | 厳守事項2(候補提示→選択→確定の2ステップを必ず踏む) | 顧客が初回メッセージで日時・メニューを両方明示していても、いきなり確定せず候補提示ステップを経ているか | 人手のみ(会話が複数ターンにまたがるため機械チェック困難、`confirmed`の遷移タイミングは補助的に確認可能) | N1・N3 |
| 3 | 厳守事項3(キャンセル・変更検知時は即確定回答せず保留+通知フラグ) | `intent`が`cancel`/`change`のとき`needs_owner_check`がtrueになっているか、自然文が断定的な処理完了を装っていないか | 機械チェック(`intent`と`needs_owner_check`の組み合わせ)+人手 | E2 |
| 4 | 厳守事項4(仮押さえ中の枠への競合予約に確定処理をしない) | 二重予約の競合検知時に確定処理へ進んでいないか(`confirmed`がfalseのまま) | 機械チェック(`confirmed`) | E3 |
| 6 | 厳守事項6(予約外相談は即エスカレーション、AIは断定回答しない) | `intent: "escalation"`、`needs_owner_check: true`になっているか、自然文が医療・料金交渉等に独自回答していないか | 機械チェック(`intent`・`needs_owner_check`)+人手(断定回答の混入有無) | E5 |
| 7 | 厳守事項7(トーン設定に応じた語尾・絵文字・感嘆符の変換、固定語彙は不変) | standard/フォーマル/カジュアルで語尾・絵文字数が message-tone-variants.mdの規則通りに変化し、かつ「仮押さえ」「確定」等の固定語彙・日付表記・FAQ実質情報が3トーンで不変か | 人手のみ(表現の妥当性は機械チェック困難、固定語彙の不変性は文字列突き合わせで補助的に機械チェック可能) | N3-トーン、仮押さえ/リマインド/FAQのトーン別サンプル |
| 8 | 厳守事項8(常連客でも確定3条件は省略しない) | precheck-strengthening.md該当客への簡略化で、名前・メニュー・日時の確認自体は省略されていないか | 人手のみ | N4 |
| 9a | 厳守事項9a(店舗登録済み静的情報のFAQ回答、登録値をそのまま案内・言い換えない) | `faq_segments`が1要素以上の配列で付与され、`topic`が正しく分類され、回答文言がfaq-response-templates.mdのテンプレートに沿い登録値を改変していないか。複合質問は項目ごとに分割送信され未登録項目のみ6相当のエスカレーション文言に差し替わっているか | 機械チェック(`faq_segments`配列の要素数・`topic`・`resolved`)+人手(登録値の言い換え有無、分割送信の体裁) | E10・E11・E12・E13・E16・E17 |
| 9b | 厳守事項9b(挨拶・雑談・スパムへの一言定型応答) | `intent: "faq"`、`faq_segments: null`、`confirmed: false`、`needs_owner_check: false`で、断定回答や予約確定に進んでいないか | 機械チェック(各フィールド値) | E6 |
| 10 | 厳守事項10(未実装機能の問い合わせは断定せず保留+エスカレーション) | `intent: "escalation"`、`confirmed: false`、`needs_owner_check: true`で、「対応可能」「対応不可」のいずれにも断定していないか | 機械チェック(各フィールド値)+人手(断定表現の混入有無) | E9・E14・E15 |
| 11 | 厳守事項11(社交辞令のみのメッセージをnew_bookingと誤判定しない) | 「ありがとうございました」等の御礼メッセージが`new_booking`ではなく9b(faq)として扱われ、明確な予約要求文言・独立した具体的日時言及がある場合のみnew_bookingになっているか | 機械チェック(`intent`値)+人手(境界事例の妥当性) | E18 |
| - | JSON出力の安定性(json-output-retry-fallback.md) | 構造化出力がスキーマ通りに毎回パース可能か、崩れた場合にリトライ・フォールバックが機能するか | 機械チェック(`process_llm_output()`のリトライ結果、`validate_against_schema()`) | E7・E8 |
| - | requested_date_range・time_of_day_preferenceの抽出精度 | `intent`がnew_booking/changeで日時の手がかりがある場合のみ抽出され、手がかりが無い場合はnull/noneのままか(断定推測をしていないか) | 機械チェック(値の有無)+人手(抽出内容の妥当性) | N1・N3・E1(曖昧な日時表現) |

## 検証手順(承認後に着手する想定)

1. `prototype/engine.py`の`process_llm_output(llm_call, max_retries)`へ渡す`llm_call`に、実際の
   Claude API呼び出し関数を注入する(現状はテスト用のスタブ関数を渡す設計になっている)。
2. conversation-samples-test-cases.mdの各ケースの入力(顧客からのメッセージ・会話履歴)を実際に
   APIへ投入し、返ってきた構造化出力を`schema/validate_test_cases.py`の`validate_against_schema()`・
   `validate_cross_field_rules()`にそのまま通す(型・必須項目・cross-fieldルールは機械チェックで
   即座に合否判定可能)。
3. 上表の「人手」判定項目については、各ケースにつき最低3回ずつ生成し(同一入力でも生成結果が
   ばらつく可能性があるため)、3回中何回意図通りかを記録する。3回中1回でも厳守事項1・2・6・7・8・
   9aの登録値言い換えに抵触する生成があれば「不合格」とし、プロンプト側の指示強化(具体例追加・
   禁止表現の明示等)を検討する基準とする(aircon-pasha・course-set-pashaで提案した基準と統一)。
4. トーン別サンプル(厳守事項7)は3トーン×同一シナリオで比較し、固定語彙・日付表記・FAQ実質情報が
   完全一致(文字列突き合わせ)しているかを機械チェックで補助した上で、語尾・絵文字数の妥当性を
   人手で確認する。
5. 生成に要したトークン数を`count_tokens`(無料エンドポイント)で計測し、llm-api-cost-estimate.md
   相当の試算(line-reservation-aiには専用のコスト試算ファイルが無いため、本検証結果をもとに
   新規作成を検討する)との比較に用いる。

## aircon-pasha・course-set-pashaとの差分

- 出力形態が根本的に異なる: aircon-pasha・course-set-pashaは「メモ入力→自由文3点セット」の
  1回生成型だが、line-reservation-aiは会話エンジンとして毎ターン`intent`等の構造化フィールドを
  返す設計であり、確定に至るまでの複数ターンにまたがる状態遷移(候補提示→選択→確定等)の妥当性が
  検証の中心になる。そのため単発の生成品質だけでなく、`ConversationFlowStateMachine`
  (prototype/engine.py)を介した複数ターンのシナリオ検証が必要な点が異なる。
- post_generation_checks.py相当の専用チェック関数群は現時点でline-reservation-aiには存在しない。
  `schema/validate_test_cases.py`の`validate_cross_field_rules()`が構造化フィールド間の整合性
  チェックを担っており、自由文側(顧客への返信メッセージ)の文言チェックは今のところ人手判定に
  委ねる設計になっている。将来的に自由文側の機械チェック(絵文字不使用の検証等)を追加するかは
  次回以降の検討課題とする。
- トーン変換(厳守事項7)はline-reservation-ai固有の検証項目であり、aircon-pasha・course-set-pasha
  には存在しない(両ventureは応対トーンの3段階変換という概念自体がない)。

## 残る未確定事項

- 「3回中1回でも不合格なら要改善」という基準は暫定であり、実測後に見直す(aircon-pasha・
  course-set-pashaと共通)。
- 複数ターンにまたがる状態遷移の検証(候補提示→選択→確定の一連の流れ)をどのように自動化するか
  (`ConversationFlowStateMachine`をテストハーネスとして流用する想定だが、実LLM出力を各ターンの
  入力として連鎖させる具体的な実装は未設計)。
- トーン変換の固定語彙不変性チェックを機械化する際、どの文字列を「固定語彙」として突き合わせ対象に
  するかのリスト化(message-tone-variants.md「3トーン共通で変えてはいけないもの」節を参照して
  今後整理する)。
