# 結果ページ `page_state` ごとの表示文言ドラフト(フェーズ113)

get-result-page-http-entry-point-design.md(フェーズ112)次回候補(3)「`page_state`ごとの
実際の案内文言当て込み(フロントエンド側)」に対応する。`receive_result_page_request()`は
`page_state`の値のみを返す設計(バックエンドの責務はそこまで)のため、本文書で
フロントエンド(`landing-page/`配下の結果ページテンプレート、実装は次回候補)が
`page_state`ごとに表示すべき文言を確定する。

## 1. 対象の8状態と文言の出典

| page_state | 文言の出典 | 本文書で新規確定するか |
| --- | --- | --- |
| `generated` | `generated_output`(LLM構造化出力、schema/output.schema.json準拠)をそのまま整形表示。固定文言ではない。 | 否(整形方針のみ2節に記載) |
| `out_of_scope` | `generated_output.out_of_scope_message`(LLM出力)をそのまま表示。 | 否(表示枠のみ2節に記載) |
| `insufficient_input` | `generated_output.missing_fields_request`(LLM出力)をそのまま表示。 | 否(表示枠のみ2節に記載) |
| `generating` | 固定文言 | 要(3節) |
| `generation_failed` | 固定文言 | 要(3節、`operational_message_templates.generation_failed_refund_email`とは別物) |
| `refunded` | 固定文言 | 要(3節) |
| `expired_after_payment` | 固定文言 | 要(3節) |
| `ttl_expired_or_invalid` | `operational_message_templates.TEMPLATES["ttl_expired_notice"]`(既存、フェーズ81確定分)を流用 | 否(既存流用) |

## 2. LLM出力系3状態の表示方針

- `generated`: `checklist`(配列)は箇条書き、`staffing_plan`・`notice_board_text`・
  `near_miss_record_template`・`fee_inquiry_note`は見出し+本文のブロックとして並べる
  (見出し自体はフロントエンドの固定ラベルであり、tone-and-manner-guideline.md方針4
  〈本文中の見出し記法【】不使用〉はLLM出力本文側の制約であって、フロントエンドの
  UI見出し〈`<h2>`等のマークアップ〉には及ばないと解釈する)。
- `out_of_scope` / `insufficient_input`: `mvp-flow-draft.md`が想定する「主催者側の入力・
  対象外の問い合わせであり異常ではない」という位置づけに合わせ、エラー表示(赤色・
  警告アイコン等)ではなく通常の案内表示として扱う。
- 3状態いずれも、本文書では表示の「枠」(どのフィールドをどう並べるか)のみを確定し、
  実際のHTML/CSSマークアップはフロントエンド実装時の次回候補とする。

## 3. 固定文言4件(新規確定)

tone-and-manner-guideline.md(フェーズ80)の方針(絵文字不使用・見出し記号〈【】〉
不使用・ですます調)に従う。

### `generating`

ご入力いただいた内容を確認し、生成の準備中です。生成が完了すると、ご登録のメール
アドレスにご案内をお送りします。今しばらくお待ちください。

(決済Webhook受信前〈`awaiting_payment`〉・受信済みだがLLM生成未完了〈同design 2節が
2意味を統合済みの状態〉のいずれでも同一の文言を表示する。両者を主催者向けに区別する
必要が生じた場合は、get-result-page-http-entry-point-design.md 4節に記載済みの
`status`遷移設計変更が前提となるため、本文書では区別しない)

### `generation_failed`

生成処理に不具合が発生したため、生成が完了しませんでした。お支払いいただいた金額は
全額返金の手続きを進めております。別途メールでも返金完了のご案内をお送りします。

(`operational_message_templates.generation_failed_refund_email`〈返金完了を確定事実
として伝えるメール文面〉とは異なり、結果ページ表示時点では返金処理が「進行中」の
場合もあるため「進めております」と手続き中の表現にとどめる。返金完了後に結果ページを
再度開いた場合の表示は`refunded`状態に遷移済みのため本文言の対象外)

### `refunded`

ご返金の手続きが完了しております。お手数ですが、ご入力内容を修正の上、再度お申し込み
いただけますと幸いです。

### `expired_after_payment`

決済完了後、保存期間(24時間)が終了したため結果を閲覧できません。既にお支払い済みの
場合、再生成(無料)または返金についてこちらの問い合わせフォームよりご連絡ください。

(`ttl_expired_notice`〈未決済・無効なURLも含む汎用文言〉と文面を分け、決済済みである
ことを明示した上で再生成・返金の案内を含める。`mark_expired_after_payment()`の呼び出し
元自体は未実装〈get-result-page-http-entry-point-design.md 2節(2)参照〉のため、本状態
自体がまだ到達しない点は変わらない)

## 4. 実装状況

- `prototype/operational_message_templates.py`のTEMPLATESに`result_page_generating`・
  `result_page_generation_failed`・`result_page_refunded`・
  `result_page_expired_after_payment`の4件を追加した。
- `prototype/test_operational_message_templates.py`は既存のEMOJI_PATTERN・
  HEADING_BRACKET_PATTERN検証が`TEMPLATES`辞書全体を走査する実装のため、コード変更
  不要で新規4件も自動的に検証対象に入ることを確認した(`python3 -m unittest discover
  -s prototype -p "test_*.py"`で既存182件+新規0件〈テストメソッド数は変わらず、
  各メソッド内のsubTestの反復対象が4件増えた〉、回帰なしでパスすることを確認した)。
- 実際のHTML/CSSマークアップ、`generated`/`out_of_scope`/`insufficient_input`の
  フィールド整形ロジックの実装は次回候補として残す。

## 5. 残課題・次回候補

- (1) 承認待ち事項(実GCPプロジェクト作成等)がオーナーから承認された場合はその着手を
  最優先。
- (2) `landing-page/`配下への実際のHTML/CSSマークアップ実装(2節で確定した表示方針の
  コード化)。
- (3) `generating`状態の「決済待ち」と「決済済み生成中」の区別要否(get-result-page-
  http-entry-point-design.md 4節で次回候補化済み、未解消のまま残す)。
- (4) 他venture・アイデア領域の前進。

最終更新: 2026-11-12 18:00 UTC(フェーズ113: `page_state`ごとの表示文言ドラフトを新規
確定。固定文言4件〈`generating`・`generation_failed`・`refunded`・
`expired_after_payment`〉をTEMPLATESに追加、既存の絵文字・見出し記法チェックが
自動的に対象に含むことを確認。コード変更はテンプレート定数の追加のみ、既存テストは
回帰なしでパス)
