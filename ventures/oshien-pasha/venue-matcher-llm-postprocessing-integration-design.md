# venue_matcher.pyをLLM構造化出力の後処理に結線する設計(フェーズ81)

README.mdフェーズ79/80「次回候補(1)」venue_matcher.pyをCloud Functionsの実エントリポイント・
LLM呼び出し結果の後処理に結線する設計、に対応する。本フェーズでは実際のCloud Functions配線・
実LLM接続は行わず(いずれもオーナー承認が必要なアクションに該当するため)、LLM構造化出力
(schema/output.schema.jsonのitinerary_draft配列)を受け取った後にvenue_matcher.pyを適用する
後処理関数の設計・机上コード化・テストまでを行う。post_generation_checks.py(トーン検証)と
同じ「LLM出力を受け取った後にプログラム側で機械的に補正する後処理」という位置づけだが、
post_generation_checks.pyは違反の検出のみ(出力を書き換えない)に対し、本後処理は
venue_matched・nearest_station_noteの値そのものを書き換える点が異なる。

## 1. なぜLLMの自己申告ではなくvenue_matcher.pyの判定を優先するか

itinerary_draft.venue_matched/nearest_station_noteは元々LLMが生成する想定のフィールド
(output.schema.json)だが、LLMは会場マスタ(schema/venue-master.json)全件をプロンプトに
含めない前提(venue-name-normalization-design.md「schemaへの反映について」節、会場数が
増えるほどプロンプトが肥大化するため)である。したがってLLM自身の「この会場は知っている」
という自己申告は、学習データ由来の不確かな知識に基づく可能性があり、特に次の2点で
venue_matcher.pyの決定的な突き合わせ結果より信頼性が低い。

- 表記揺れ・改称・命名権契約による愛称変更(GMOアリーナさいたま、愛知県体育館→
  ドルフィンズアリーナ→IGアリーナ等)はvenue-master.jsonの方が最新かつ出典付きで管理されて
  いるため、LLMの学習時点の知識より新しい可能性が高い。
- 休館・機能移転等のoperational_status(venue_matcher.py `_operational_status_note()`)は
  venue-master.json側にのみ存在する情報であり、LLMが自発的に言及する保証がない。

したがって本設計では、itinerary_draft各要素のvenue_matched・nearest_station_noteは
**常にvenue_matcher.pyの判定結果で上書きする**方針とする(LLMの生成値は判定の入力には使わず、
venue_name_inputのみを突き合わせキーとして使う)。

## 2. `apply_venue_match_postprocessing()`

`prototype/itinerary_draft_postprocessor.py`に机上実装した。

```python
def apply_venue_match_postprocessing(itinerary_draft, venue_master, ambiguity_watchlist=None):
    # itinerary_draft: output.schema.jsonのitinerary_draft配列、またはNone
    #   (status!=generatedのとき。1節参照、何もせずそのまま返す)
    # 戻り値: (上書き後のitinerary_draft, conflictsリスト)
```

処理内容:

1. `itinerary_draft`が`None`の場合は何もせず`(None, [])`を返す(status=out_of_scope/
   insufficient_inputのとき、1節の上書き対象フィールド自体がnullであるため)。
2. 各要素について`venue_matcher.match_venue(venue_name_input, venue_master,
   ambiguity_watchlist)`を呼び、`venue_matched`・`nearest_station_note`を結果で上書きする
   新しいdictを作る(入力の`itinerary_draft`要素自体は変更しない、`lodging_area_candidates`・
   `transport_note`は上書き対象外でそのまま保持)。
3. `operational_status_note`が非Noneの場合、`nearest_station_note`の末尾に半角スペース区切り
   で追記する。schema/output.schema.jsonにはoperational_status用の別フィールドが無く
   (venue-operational-status-output-reflection-design.md 3節、schema拡張は実LLM安定生成未検証
   のため見送り中の既存方針)、新フィールドを追加しない前提を踏襲するため、既存の
   `nearest_station_note`に文として結合する。
4. 上書き前のLLM自己申告`venue_matched`とvenue_matcher.pyの判定が異なる場合、
   `conflicts`リストに`{venue_name_input, llm_claimed_matched, matcher_matched,
   match_confidence}`を記録する。出力本体(itinerary_draft)には混入させず、呼び出し側が
   Cloud Monitoring等へのログ出力に使う想定の別戻り値とする(3節参照)。

## 3. conflictsの用途

conflictsはLLMの会場認識が実際の会場マスタとどの程度ずれているかを観測するための計測値であり、
利用者への応答には使わない。将来、conflictsの発生率が高い場合はvenue-name-normalization-
design.mdのプロンプト設計(会場マスタを一部プロンプトに含めるか等)の見直し材料とする想定だが、
実LLM接続前の現段階では計測基盤(Cloud Monitoringカスタムメトリクス等)の整備自体が未着手の
ため、本フェーズではconflictsを戻り値として保持するところまでに留める(ログ出力先の結線は
次回以降の課題、cloud-monitoring-alert-policy-design.mdの既存設計と合わせて検討する)。

## 4. 残課題

- Cloud Functionsの実エントリポイント(LLM API呼び出し自体の実装、`apply_venue_match_
  postprocessing()`をどのタイミングで呼ぶか等のリクエストハンドラ配線)は、実LLM接続・
  実際のAPIキー取得(オーナー承認が必要なアクション)後に行う。
- conflictsのログ出力先(Cloud Monitoring等)の結線は未設計のまま次回以降の課題として残す。
- `day_timetable`・`cost_estimate`・`hashigo_check`は会場マスタの突き合わせ対象外
  (venue_matched/nearest_station_noteを持たない)ため、本後処理の対象外のままとする。

実LLM呼び出し・Cloud Functionsへの実配線・APIキー取得自体はオーナー承認が必要なアクションに
該当するため、本メモは設計・机上コード化・テストに留める(外部サービスへの接続は一切行って
いない)。承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は本フェーズでは
発生していないためpending-approval.mdへの新規追記は不要(既存の承認待ち事項の範囲内で扱う)。

最終更新: 2026-11-04 13:00 UTC(フェーズ81: venue_matcher.pyをLLM構造化出力の後処理に適用する
`apply_venue_match_postprocessing()`を設計し、prototype/itinerary_draft_postprocessor.pyに
コード化した)
