# LINEテキストメッセージ文字数上限超過時のフォールバック設計(フェーズ138)

aircon-pashaには存在する`character-limit-fallback-design.md`(フェーズ102・103・105、
LINE Messaging APIのテキストメッセージ文字数上限超過時のフォールバック設計)が本venture
には一度も設計されていなかった点に対応する。実装未着手・動作未検証(実LLM・実LINE API接続は
オーナー承認待ちのため)。

## 前提の再確認

- LINE Messaging APIのテキストメッセージ1件あたりの文字数上限は5,000文字、UTF-16コード
  単位でのカウント(aircon-pasha/character-limit-fallback-design.md参照。本venture側での
  一次情報再確認はWebFetchのegressプロキシ制約により未実施だが、同一プラットフォーム
  (LINE Messaging API)を利用するため同じ制約が適用されると判断する)。
- aircon-pashaとの本質的な違い: aircon-pashaは`completion_report.body`・`care_guide.body`
  の2通を**別々のメッセージとして**送信するため、フィールドごとに上限を判定すればよかった。
  一方本ventureはwebhook-processing-flow-design.md(フェーズ38)の設計方針により、
  出力1(sns_post.body+hashtags)・出力2(line_web_notice.body)・出力3(history_rowsの
  CSV変換)の3つを**見出し付きで1通のテキストメッセージにまとめて**返信する
  (`format_generated_reply()`、prototype/cloud_function_webhook.py)。そのため本venture
  では、個々のフィールド単体ではなく、見出し文字列・改行・CSVテキストまで含めた**組み立て後の
  1通全体**の文字数が上限を超えていないかを判定する必要がある(aircon-pashaより超過しやすい
  構造的リスク)。

## 想定される超過の原因

- 入力メモ自体が極端に長い(コピー&ペースト時の誤操作、無関係な文章の混入等)。
- LLMが指示から逸脱し、通常想定(mvp-flow-draft.md想定の数百文字程度)を大きく超える長文を
  生成してしまうケース(プロンプト崩れ・幻覚的な冗長生成)。
- 3エリア以上の同時更新(multi-area-mixed-case-review.md参照)で`history_rows`の要素数が
  増え、CSV変換後のテキスト(history_export.py)が長くなるケース。1メモで多数のエリアを
  同時報告する運用ほど超過しやすい、本venture固有のリスクパターン。
- いずれの原因であっても、送信直前の機械チェックでは原因を区別せず一律に「上限超過」として
  扱う(aircon-pashaと同じ方針)。

## 設計方針: 切り詰めは行わない

aircon-pashaと同じ結論を採用する。`sns_post.body`はSNS投稿としてオーナーがそのまま
コピー&ペーストして公開する運用が正規ルート(README.md「概要」参照)であり、
`line_web_notice.body`も公式LINE/Web告知にそのまま転用される想定のため、末尾を機械的に
切り詰めると文が不完全なまま公開・転用されてしまう危険がある。よって上限超過は「切り詰めて
送る」のではなく「送らずに生成失敗として扱う」方針とする(json-output-retry-fallback.md
(line-reservation-ai)・character-limit-fallback-design.md(aircon-pasha)と同じ設計思想)。

## 検知・フォールバックのフロー

1. LLM生成後、検証エラーの一部として`check_message_length_within_line_limit()`
   (prototype/post_generation_checks.py新規関数、`run_all_checks()`に組み込み)で判定する。
   本venture固有の事情として、この関数は`instance`の各フィールドを直接見るのではなく、
   実際に1通として送信される`format_generated_reply()`相当の組み立て済みテキスト
   (見出し・区切り改行・`history_rows_to_csv_text()`の出力を含む)の長さをUTF-16コード
   単位で算出する。
2. 5,000文字を超えていた場合、`LENGTH_LIMIT_ERROR_PREFIX`で始まるエラーメッセージを
   返す(aircon-pashaと同じ、呼び出し元が他の検証エラーと区別し専用フォールバック文言を
   選択するための目印)。
3. `process_memo_event()`(cloud_function_webhook.py)は、1回の同一入力再生成後も
   `LENGTH_LIMIT_ERROR_PREFIX`のエラーが残る場合、汎用の`VALIDATION_FAILURE_FALLBACK_MESSAGE`
   ではなく専用の`LENGTH_LIMIT_FALLBACK_MESSAGE`を返す。例:
   「生成結果が長くなりすぎたため、下書きを作成できませんでした。恐れ入りますが、入力
   メモを少し短くして再度お送りください(1回のメモでの更新エリア数を減らしていただくのも
   有効です)。」
   aircon-pashaの例文と異なり、本venture固有の超過原因(複数エリア同時更新)を踏まえ、
   「更新エリア数を減らす」という具体的な回避策を末尾に追記した。

## UTF-16コード単位カウントの実装上の注意

aircon-pashaと同じ注意点がそのまま当てはまる。Pythonの`len(str)`はUnicodeコードポイント数を
返すため、補助文字面(U+10000以降)の文字はUTF-16では2コード単位(サロゲートペア)として
カウントされるがPythonの`len()`では1文字として数えられる。本venture出力は厳守事項9により
絵文字を原則使用しない方針(ただしsns_post.bodyのみ1〜2個まで許容)だが、稀な人名・地名漢字
等が補助文字面に該当する可能性はゼロではないため、`len(text.encode('utf-16-le')) // 2`で
UTF-16コード単位数を算出する実装とする。

## 残課題

- 5,000文字という値自体はLINE APIのハード上限であり、実運用上はその手前でソフトな閾値を
  設けるかどうかは、実LLM接続後の生成品質検証(llm-quality-verification-plan.md)の中で
  実測データを見ながら検討する(aircon-pashaと同じ位置づけ)。
- 実装(`check_message_length_within_line_limit()`のprototype/post_generation_checks.pyへの
  追加、cloud_function_webhook.pyへの`LENGTH_LIMIT_FALLBACK_MESSAGE`分岐の配線)は、
  純粋なテキスト処理・分岐ロジックであり実LLM・実LINE API接続を必要としないため、承認待ちの
  ままでも着手可能(aircon-pashaフェーズ105と同じ考え方)。本フェーズに続けて着手する。
