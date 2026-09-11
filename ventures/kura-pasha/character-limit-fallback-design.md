# LINEテキストメッセージ文字数上限超過時のフォールバック設計(フェーズ83)

「次にやること(候補)」節では明示的に挙げられていなかったが、aircon-pasha/
character-limit-fallback-design.md(フェーズ102)・course-set-pasha側の同種設計と比べて
本ventureに同等の設計が存在しないcross-venture parityのギャップに気付いたため対応する。

## 前提の再確認

- LINE Messaging APIのテキストメッセージ1件あたりの文字数上限は5,000文字、
  UTF-16コード単位でのカウント(aircon-pasha/character-limit-fallback-design.md参照、
  一次情報はLINE Developers公式ドキュメント)。
- 本ventureはaircon-pasha/course-set-pashaと異なり、出力1(受注内容整理メモ)・
  出力2(納品案内下書き)・出力3(お手入れ案内下書き)の3つを**1通のテキストメッセージに
  まとめて**返信する設計(`format_generated_reply()`、mvp-flow-draft.md「出力」節)。
  aircon-pashaは`completion_report`/`care_guide`をそれぞれ独立した送信対象として
  文字数チェックする設計だったが、本ventureは3出力を連結した後の**1通全体**の文字数が
  LINE APIの送信可否を左右するため、チェック対象は連結後の1本のテキストとする点が
  aircon-pasha版との構造上の差分となる。
- 出力2(納品案内下書き)・出力3(お手入れ案内下書き)は、職人が実際の依頼者(エンドカスタマー)
  へ転送する運用を想定した文面(README「概要」節)。出力1(受注内容整理メモ)は職人自身の
  備忘・作業記録用だが、本ventureの返信は3つをまとめた1通の形式であるため、
  職人は必要な部分(出力2・3)のみを選択してコピー&ペーストする運用となる
  (全文をそのまま転送する想定ではない)。

## 想定される超過の原因

- 入力メモ自体が極端に長い(コピー&ペースト時の誤操作、無関係な文章の混入等)。
- LLMが指示から逸脱し、通常想定(mvp-flow-draft.mdの例に見られる数百文字程度)を
  大きく超える長文を生成してしまうケース(プロンプト崩れ・幻覚的な冗長生成)。
- いずれの原因であっても、送信直前の機械チェックでは原因を区別せず一律に「上限超過」として
  扱う(aircon-pasha版と同じ方針)。

## 設計方針: 切り詰めは行わない

aircon-pasha版と同じ理由により、上限に収まるよう末尾を切り詰めて送信する案は採用しない。

- 出力2・3は職人が依頼者へ転送しうる文面であり、末尾を機械的に切り詰めると文が
  不完全な状態のまま転送されてしまう危険がある。これはllm-system-prompt-draft.mdの
  厳守事項(実際の専門的判断への不介入、確定的な内容は職人本人の確認に委ねる)とも
  相容れない。
- よって、上限超過は「切り詰めて送る」のではなく「送らずに生成失敗として扱う」方針とする
  (aircon-pasha/character-limit-fallback-design.md、json-output-retry-fallback.md
  〈line-reservation-ai〉の「フォーマット崩れ時は楽観的に処理を進めず安全側に倒す」という
  既存の設計思想を踏襲)。

## 検知・フォールバックのフロー

1. `process_memo_event()`内で`status == "generated"`の場合、`format_generated_reply()`
   (`format_reply_text()`経由)で組み立てた1本のテキストに対し、`limit_notice`・
   トライアル終了通知を付記する**前**に文字数チェックを行う
   (`check_message_length_within_line_limit()`を新設)。
   `limit_notice`・トライアル終了通知は固定文言で長さの上限が既知(数百文字未満)であり、
   これらを含めても5,000文字を大きく超える余地はほぼ無いため、チェックはLLM生成部分
   (連結後の3出力)のみに対して行えば実用上十分と判断する(境界ぎりぎりのケースを
   際限なく作り込むよりも、既存の他失敗系統〈LlmApiError・検証エラー〉と同じ単純な
   構造を優先する)。
2. 5,000文字(UTF-16コード単位)を超えていた場合、`limit_notice`・トライアル終了通知の
   付記を行わず、既存の`LlmApiError`・検証エラー時と同じ形の早期return(`_reply_with_retry()`
   で`CHARACTER_LIMIT_FALLBACK_MESSAGE`を送信し`MemoProcessResult`を返す)とする。
   - 既存の`LlmApiError`・検証エラー時のフォールバックも`limit_notice`・トライアル終了通知を
     付記していない(既存コード参照)ため、本フォールバックも同じ扱いに揃える。
   - `usage_counter_workshop.process_generation_request()`によるカウント自体は
     LLM呼び出し前に既に確定済み(process_memo_event()docstring 5.参照、「生成
     リクエストを受け付けた時点」でカウントされる既存の設計)であり、本フォールバックは
     この既存の扱いを変更しない。
3. フォールバック文言は職人本人向け(依頼者へ転送されることを想定しない)の定型操作案内とする:
   「生成結果が長くなりすぎたため、下書きを作成できませんでした。お手数ですが、入力
   メモを少し短くして再度お送りください。」(aircon-pasha版のトーンを踏襲)。

## 実装

- `count_utf16_code_units(text: str) -> int`: `len(text.encode("utf-16-le")) // 2`で
  UTF-16コード単位数を数える(サロゲートペアとなる文字〈絵文字等〉を2としてカウントする
  ため、Python標準の`len(str)`〈コードポイント単位〉をそのまま使わない)。
- `check_message_length_within_line_limit(text: str) -> bool`:
  `count_utf16_code_units(text) <= LINE_TEXT_MESSAGE_MAX_LENGTH`(`LINE_TEXT_MESSAGE_MAX_LENGTH
  = 5000`)。
- `CHARACTER_LIMIT_FALLBACK_MESSAGE`定数、`MemoProcessResult.character_limit_exceeded: bool`
  フィールドを新設した。
- `process_memo_event()`の`status == "generated"`かつ`checkout_intent`分岐に該当しない
  経路(`format_reply_text()`でreply_textを組み立てた直後、`limit_notice`付記の前)に
  チェックを挿入した。

## 未検証事項

- 実LLM接続後、実際にどの程度の頻度で5,000文字超が発生しうるかは未検証(APIキー取得は
  オーナー承認待ち、pending-approval.md参照)。
- 本チェックはUTF-16コード単位でのカウントロジック自体はaircon-pasha版と同一のため
  正確性への懸念は低いが、Pythonの`str.encode("utf-16-le")`によるサロゲートペア処理が
  LINE Platform側の実際のカウント方式と完全に一致するかは一次情報未確認(aircon-pasha版
  同様の既知の制約として引き継ぐ)。

最終更新: 2026-09-11 08:00 UTC(フェーズ83: 新規作成)
