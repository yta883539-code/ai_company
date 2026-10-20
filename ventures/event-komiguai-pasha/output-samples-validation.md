# 期待JSON出力サンプルの机上検証(2026-10-20 17:00 UTC)

## 位置づけ

README.md「次回候補」(フェーズ29)「厳守事項4に追記した『分散退場』知見を踏まえた出力
サンプル(output-samples-validation.md相当、本venture未着手)の作成」に対応する。
aircon-pasha/output-samples-validation.md・course-set-pasha・kura-pasha等の同名ドキュメントと
同じ位置づけで、schema/validate_test_cases.py(フェーズ5作成、既に18件保持)の内容を1箇所に
まとめ、かつ分散退場知見(llm-system-prompt-draft.md厳守事項4、フェーズ29追加)を反映した
サンプルG7を新規追加した。

## 検証方法

course-set-pasha/schema/validate_test_cases.pyと同じ設計。外部ライブラリ非依存(pure stdlib)の
簡易バリデータで、output.schema.jsonのサブセット(type/enum/required/additionalProperties)を
解釈してフィールド単位の型・必須項目違反を検出する。スキーマ単体では表現できない
`status`⇔null/非null制約(厳守事項7・8)、`staffing_plan.focus=both`時の主催者判断委任の明示
(厳守事項4)、`notice_board_text.includes_road_use_permit_note`と本文キーワードの整合性
(厳守事項2)、`near_miss_record_template.fields`の固定5項目(厳守事項6)、料金額の具体的言及の
禁止(厳守事項7)、入力に含まれる個人名の転記禁止(厳守事項10)は`validate_cross_field_rules()`・
`check_personal_name_leakage()`で個別にチェックする。

## サンプルケース(19件。2026-10-20 17:00 UTC定例更新でG7を新規追加)

| ケースID | status | 想定シナリオ |
|---|---|---|
| G1_free_admission_indoor | generated | 自由入場(整理番号なし)・屋内収容のケース。focus=entry、道路使用許可注記なし |
| G2_reserved_seat_with_outdoor_queue | generated | 全席指定・待機列が屋外(公道)に及ぶ可能性ありのケース。focus=exit、道路使用許可注記あり |
| G3_mixed_admission_type | generated | 自由入場エリアと指定席エリアが混在するケース。focus=both、主催者判断委任の明示を含む |
| G4_advance_reservation_admission_type | generated | 事前予約制(時間枠制)のケース。予約枠が単一か複数か入力から一意に決まらないためfocus=both |
| OOS1_external_contractor_request | out_of_scope | 警備会社への発注契約・所轄警察署への届出代行を求める入力への不応答ケース(厳守事項1・7) |
| OOS2_fee_and_payment_inquiry | out_of_scope | 料金プランについての問い合わせのみのケース(厳守事項7、具体的な料金額への言及なし) |
| G5_staffing_memo_with_personal_name_generalized | generated | 入力メモに氏名(「田中」)が含まれるが、出力のどこにも転記せず一般化して記述するケース(厳守事項10) |
| G6_generated_with_incidental_fee_mention | generated | 会場情報(capacity・entry_exit_points等)は十分で通常の4出力が生成されるが、料金プランへの言及も混在するケース。fee_inquiry_noteに定型応答(具体的な料金額への言及なし) |
| G7_exit_focus_staggered_block_announcement | generated | 全席指定・退場口3箇所でブロック分けが物理的に成立する会場のケース。llm-system-prompt-draft.md厳守事項4(フェーズ29追加)の「ブロック・エリア別に時間差を設けて段階的に退場を案内する(分散退場)」を出力2(staffing_plan.body・announcement_text)・出力3(notice_board_text.body)の双方で言及する(2026-10-20 17:00 UTC追加) |
| II1_missing_capacity_and_entry_exit | insufficient_input | capacity・entry_exit_pointsがいずれも未入力で再送を促すケース(厳守事項8) |
| NEG1_road_use_note_missing_is_detected | generated | ネガティブテスト。includes_road_use_permit_note=trueなのに本文に「道路使用許可」への言及がない不整合(厳守事項2違反)が検出されることの確認用 |
| NEG2_near_miss_fields_wrong_is_detected | generated | ネガティブテスト。near_miss_record_template.fieldsが固定5項目(厳守事項6)と一致しない(2項目のみ)不整合が検出されることの確認用 |
| NEG3_both_focus_no_deferral_is_detected | generated | ネガティブテスト。focus=bothなのにbody内に主催者自身への判断委任の記載がない(厳守事項4違反)が検出されることの確認用 |
| NEG4_road_use_note_false_but_present_is_detected | generated | ネガティブテスト。includes_road_use_permit_note=falseなのに本文に「道路使用許可」への言及が残っている冗長な注記(厳守事項2違反)が検出されることの確認用 |
| NEG5_undefined_top_level_field_is_detected | generated | ネガティブテスト。スキーマに存在しないトップレベルフィールド(`venue_name`)の混入(additionalProperties違反)が検出されることの確認用 |
| NEG6_missing_required_status_is_detected | generated | ネガティブテスト。必須フィールド`status`自体が欠落している不整合が検出されることの確認用 |
| NEG7_personal_name_leaked_is_detected | generated | ネガティブテスト。入力に含まれていた氏名(「田中」)が出力本文にそのまま転記されている(厳守事項10違反)が検出されることの確認用 |
| NEG8_fee_price_leaked_is_detected | out_of_scope | ネガティブテスト。out_of_scope_messageに具体的な料金額(「500円/回」)への言及が含まれている(厳守事項7違反)が検出されることの確認用 |
| NEG9_fee_price_leaked_in_generated_is_detected | generated | ネガティブテスト。fee_inquiry_noteに具体的な料金額(「500円/回」)への言及が含まれている(厳守事項7違反)が検出されることの確認用 |

## 結果(2026-10-20 17:00 UTC定例更新時点)

```
19/19 件パス
```

G1〜G7・OOS1〜OOS2・II1の10件が違反なくパスし、NEG1〜NEG9の9件は意図通りエラーが検出される
ことを確認した(`python3 schema/validate_test_cases.py`で実行内容を確認できる)。回帰確認として
`python3 -m unittest discover -s prototype -p "test_*.py"`(33件)も変更なしでパスすることを
確認した。

G7(今回追加)は、llm-system-prompt-draft.md厳守事項4が「ブロック・エリア別に時間差を設けて
段階的に退場を案内する(分散退場)」を提示してよいとする条件(`entry_exit_points`の数・配置が
1箇所のみ等でブロック分け自体が物理的に成立しない入力でないこと)を満たす入力(退場口3箇所)を
想定し、出力2(staffing_plan.body・announcement_text)・出力3(notice_board_text.body)の
いずれにも「分散退場」のキーワードを含めた。これにより、分散退場知見が実際にstatus=generated
の出力3箇所すべてに反映できる形でスキーマ・既存のクロスフィールドチェックと矛盾しないことを
机上確認した。

## 残る未検証事項

- 上記はあくまで机上検証であり、実際にLLMがこの形式(特に分散退場への言及を含むG7)で安定して
  構造化出力を生成できるかは未確認(実LLM呼び出しはAPIキー取得・課金がオーナー承認待ちのため、
  他venture同様に実装フェーズ・API接続時の検証に持ち越し)。
- G7は「退場口3箇所」という具体例のみを固定している。退場口が2箇所の場合にブロック分けを
  2分割とするか、あるいは退場口数とブロック数の対応関係自体をどう決めるかは
  llm-system-prompt-draft.md厳守事項4未確定のまま残る(次回以降、他venture・アイデア領域の
  前進を優先しつつ、優先度が上がった時点で検討する)。
- 層2・層3の候補探索(候補1〜14)は依然として実名候補の特定に至っていないため、G7が想定する
  ような大規模・複数退場口会場の実在候補との紐付けは引き続き未着手。
