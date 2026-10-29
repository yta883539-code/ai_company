# 月額フリーパスの生成回数カウント設計(フェーズ8)

monthly-pass-identity-design.md「6. 残課題」1点目で次回以降の検討課題として残されていた、
月額フリーパス利用者の生成回数カウント(tech-stack.md「7. 月額フリーパスの生成回数カウント」、
course-set-pashaの`UsageCounterProtocol`相当)を、本フェーズで確定した`internal_id`を前提に
設計する。

## 1. 前提の再確認

- pricing-plan.md「課金単位の仮決め」(2026-10-28 11:00 UTC)が既に明記しているとおり、月額
  フリーパスは生成回数「無制限」であり、course-set-pasha・kura-pasha等が持つ「月3回/8回/20回」
  のような上限判定ロジックは本venture月額フリーパスには存在しない。したがって本フェーズの
  設計対象は「上限判定」ではなく、pricing-plan.md同箇所が課題として残した「生成回数の異常な
  増加(想定外のbot的利用等)を検知するための内部ログ」である。
- 都度プランは1決済=1回で完結し(monthly-pass-identity-design.md 1節)、都度プラン側に
  横断的な回数カウントは発生しない。本設計は月額フリーパスのみを対象とする。

## 2. 記録先の構造

course-set-pasha等の`usage_counter/{workshop_id}`(月単位でリセットされる固定枠カウンタ)
とは目的が異なるため、同じ「月次リセットして上限と比較する」構造をそのまま流用するのは
適切ではない。本venture固有の目的(異常検知用の内部ログ)に合わせ、以下の構造を採る。

- `monthly_pass/{internal_id}`ドキュメントに、サブコレクション`generation_log`を追加する。
- 1回の生成リクエストごとに`generation_log`配下へ1ドキュメントを追記する(自動生成ID)。
  記録するフィールドは`requestedAt`(生成要求時刻)・`venueMatched`(output.schema.jsonの
  `itinerary_draft.venue_matched`と同値、どの程度会場マスタと一致した入力かの参考情報)・
  `inputPerformanceCount`(ハシゴ判定目的で1回の入力に含まれた公演数)の3項目とする。
- あわせて`monthly_pass/{internal_id}`ドキュメント自身に`currentMonthGenerationCount`
  (当月の`generation_log`件数を都度加算するカウンタフィールド)を持たせ、`generation_log`を
  都度全件集計しなくても当月の総回数を即座に参照できるようにする(course-set-pashaの
  `usage_counter.count`と同じ「加算のみ・読み取りは1フィールド」という設計を踏襲)。
- `currentMonthGenerationCount`のリセット判定は、course-set-pasha踏襲の「`month`フィールドが
  当月文字列(例: `2026-11`)と一致しなければ`count`を0にリセットしてから加算する」方式を
  そのまま採用し、`monthly_pass/{internal_id}`に`generationCountMonth`フィールドを追加する。

## 3. 異常検知の一次方針

- 「異常な増加」の具体的な閾値(1日あたり何回を超えたら異常とみなすか等)は、実際の利用
  データが存在しない現時点では仮値を置いても検証不能であるため、本フェーズでは閾値の確定は
  見送る。代わりに、閾値判定を後から追加しやすくするためのログ構造(2節)の整備までを本
  フェーズの範囲とする。
- `generation_log`に`requestedAt`を1件ごとに記録する構造であれば、将来的に「直近1時間の
  件数」「直近24時間の件数」等、任意の時間窓での集計・閾値判定を事後的に追加できる
  (事前に時間窓を決めて専用カウンタを持つ必要がない)。
- 異常検知が実際に作動した場合の対応(アクセストークンの一時停止等)は、月額フリーパスが
  「生成回数無制限」という料金プラン上の約束であるため、不用意に正規利用者の利用を止めない
  よう慎重な設計が必要になる。この対応方針自体は実利用データなしに決めるべきではないため、
  次回以降の検討課題として明記したまま残す(本フェーズでは記録構造の整備のみ)。

## 4. schema/output.schema.json・validate_test_cases.pyへの影響

usage-counter-workshop-key-design.md(kura-pasha、3節)と同様の確認を行った結果、
`generation_log`・`currentMonthGenerationCount`はLLMの構造化出力そのものではなく生成リクエスト
処理のサーバー側ログ・カウンタであるため、schema/output.schema.jsonの`required`/`properties`
定義への変更は発生しない。validate_test_cases.pyの各TEST_CASESフィクスチャ(1回の生成リクエスト
に対する出力形の検証)にも影響はない。よって本フェーズでは両ファイルへの編集は不要と結論づける。

## 未検証・残課題

- 異常検知の具体的な閾値・検知時の対応方針(3節)は、実利用データが存在しないため本フェーズ
  では確定を見送った。実LLM呼び出し開始(オーナー承認後)後、一定期間の実利用データを観察
  してから閾値を検討する。
- venue-master-draft.mdの各会場のアクセス情報精査(WebSearchでの裏取り)は未着手のまま。
- 会場名表記揺れの名寄せ方法の検討は未着手のまま。
- 都度プラン⇔月額フリーパスのプラン変更時の課金面(残存クレジット等)の扱いは本フェーズの
  範囲外。

実LLM呼び出し・Stripe等決済代行サービスとの実接続、実際のFirestore・GCPプロジェクト作成自体は
オーナー承認が必要なアクションに該当するため、本メモは設計・仮説の検討に留める(コード実装・
外部サービスへの接続は一切行っていない)。承認が必要なアクション(支払い・アカウント作成・
外部公開・送信等)は本フェーズでは発生していないためpending-approval.mdへの新規追記は不要
(既存の承認待ち事項〈Stripe/GCPアカウント開設等〉の範囲内で扱う)。

最終更新: 2026-10-29 19:00 UTC(フェーズ8: monthly-pass-identity-design.md「6. 残課題」1点目に
対応し、月額フリーパスの生成回数カウントを「上限判定」ではなく「異常検知用の内部ログ」として
設計した。`generation_log`サブコレクション+`currentMonthGenerationCount`集計フィールドという
構造を確定させたが、異常検知の具体的な閾値・対応方針は実利用データがないため次回以降の課題
として残した)
