# 期待JSON出力サンプルの机上検証(2026-10-20 17:00 UTC作成、20:00 UTCフェーズ31で更新)

## 位置づけ

README.md「次回候補」(フェーズ29)「厳守事項4に追記した『分散退場』知見を踏まえた出力
サンプル(output-samples-validation.md相当、本venture未着手)の作成」に対応する。
aircon-pasha/output-samples-validation.md・course-set-pasha・kura-pasha等の同名ドキュメントと
同じ位置づけで、schema/validate_test_cases.py(フェーズ5作成、既に18件保持)の内容を1箇所に
まとめ、かつ分散退場知見(llm-system-prompt-draft.md厳守事項4、フェーズ29追加)を反映した
サンプルG7を新規追加した。フェーズ31(2026-10-20 20:00 UTC)では、フェーズ30「残る未検証
事項」で未確定だった「退場口数とブロック数の対応関係」を確定し(llm-system-prompt-draft.md
厳守事項4に追記: 退場口2〜4箇所はブロック数と1対1対応、5箇所以上はブロック数を4に上限設定)、
この上限ルールを反映したサンプルG8を新規追加した。

## 検証方法

course-set-pasha/schema/validate_test_cases.pyと同じ設計。外部ライブラリ非依存(pure stdlib)の
簡易バリデータで、output.schema.jsonのサブセット(type/enum/required/additionalProperties)を
解釈してフィールド単位の型・必須項目違反を検出する。スキーマ単体では表現できない
`status`⇔null/非null制約(厳守事項7・8)、`staffing_plan.focus=both`時の主催者判断委任の明示
(厳守事項4)、`notice_board_text.includes_road_use_permit_note`と本文キーワードの整合性
(厳守事項2)、`near_miss_record_template.fields`の固定5項目(厳守事項6)、料金額の具体的言及の
禁止(厳守事項7)、入力に含まれる個人名の転記禁止(厳守事項10)は`validate_cross_field_rules()`・
`check_personal_name_leakage()`で個別にチェックする。

## サンプルケース(20件。2026-10-20 17:00 UTC定例更新でG7、20:00 UTCフェーズ31でG8を新規追加)

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
| G8_exit_focus_capped_block_count | generated | 全席指定・キャパシティ3,000人・退場口6箇所のケース。退場口数(6)のままブロック化せず、厳守事項4(フェーズ31追記)の上限ルールに基づき隣接する退場口を組にして4ブロックに集約した分散退場案を出力2・出力3で言及する(2026-10-20 20:00 UTC追加) |
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

## 結果(2026-10-20 20:00 UTCフェーズ31時点)

```
20/20 件パス
```

G1〜G8・OOS1〜OOS2・II1の11件が違反なくパスし、NEG1〜NEG9の9件は意図通りエラーが検出される
ことを確認した(`python3 schema/validate_test_cases.py`で実行内容を確認できる)。回帰確認として
`python3 -m unittest discover -s prototype -p "test_*.py"`(33件)も変更なしでパスすることを
確認した。

G7(フェーズ30追加)は、llm-system-prompt-draft.md厳守事項4が「ブロック・エリア別に時間差を
設けて段階的に退場を案内する(分散退場)」を提示してよいとする条件(`entry_exit_points`の数・
配置が1箇所のみ等でブロック分け自体が物理的に成立しない入力でないこと)を満たす入力(退場口
3箇所)を想定し、出力2(staffing_plan.body・announcement_text)・出力3(notice_board_text.body)
のいずれにも「分散退場」のキーワードを含めた。

G8(フェーズ31追加)は、フェーズ30「残る未検証事項」で未確定だった「退場口数とブロック数の
対応関係」を確定したうえで作成した。厳守事項4に追記した上限ルール(退場口2〜4箇所はブロック数
と1対1対応、5箇所以上はブロック数を4に上限設定)に基づき、退場口6箇所の入力に対して出力2・
出力3のいずれも「4ブロックに集約した分散退場」を言及する内容とした。これにより、分散退場知見が
退場口数の大小にかかわらずstatus=generatedの出力3箇所すべてに矛盾なく反映できる形を机上確認
した。

## 残る未検証事項

- 上記はあくまで机上検証であり、実際にLLMがこの形式(特に分散退場への言及を含むG7・G8)で安定
  して構造化出力を生成できるかは未確認(実LLM呼び出しはAPIキー取得・課金がオーナー承認待ちの
  ため、他venture同様に実装フェーズ・API接続時の検証に持ち越し)。
- G8の「5箇所以上は4ブロックに上限設定」という具体的な上限値(4)は、会場の収容人数・退場口の
  配置(隣接か分散か)を考慮せず机上で仮決めしたものであり、実在候補(層1候補1・候補2等)との
  接点確立後、実際の会場構造に照らした妥当性の再検証が必要(llm-system-prompt-draft.md厳守事項4
  フェーズ31追記分参照)。
- 層2・層3の候補探索(候補1〜14)は依然として実名候補の特定に至っていないため、G7・G8が想定する
  ような大規模・複数退場口会場の実在候補との紐付けは引き続き未着手。

## フェーズ32追記(2026-10-21 02:00 UTC定例更新): G8上限値(4ブロック)の妥当性検証準備

「残る未検証事項」2点目(G8の上限値4の妥当性検証)の準備として、退場口数とブロック数の対応に
関する公的・学術的な数値基準の有無をWebSearchで調査した。南山大学の卒業論文・情報処理学会
デジタルプラクティス論文(論文番号242323)等の群集安全管理・群集シミュレーション関連資料では、
座席をブロック単位に分け退場案内があったブロックから順次退場させる方式が「規制退場」という
用語で整理されていることを確認したが、ブロック数そのものの具体的な人数・退場口数対応の数値
目安を示す公開資料は見つからなかった。この結果は、(a)本venture独自の「退場口2〜4箇所は1対1、
5箇所以上は4に上限」という上限ルール(llm-system-prompt-draft.md厳守事項4フェーズ31追記分)が
参照すべき公的な数値基準がそもそも存在しない中での机上の仮決めであり、実在候補の会場構造に
照らした再検証は引き続き層2・層3(または層1候補1・候補2)の実名候補確立後でなければ行えない
という結論を補強するものであること、(b)本サービスが扱う手法の一般名称が「分散退場」に加えて
「規制退場」であることを確認できた、という2点を明らかにした。(b)を踏まえ、llm-system-prompt-
draft.mdの用語自体は「分散退場」のまま維持しつつ(既存のG7・G8テストケース・出力文言との整合を
優先し、用語変更によるテストケース全面見直しのコストを避けるため)、本ファイルに「規制退場」が
同義の専門用語であることを記録に残す。実際のWebSearchによる調査のみで、コード変更
(output.schema.json・validate_test_cases.py)・プロンプト文面変更はいずれも行っていないため、
`python3 schema/validate_test_cases.py`(20件)・`python3 -m unittest discover -s prototype -p
"test_*.py"`(33件)はいずれも無変更でパスすることを確認した(回帰なし)。承認が必要なアクション
(支払い・アカウント作成・外部公開・送信等)は今回発生していないためpending-approval.mdへの
追記なし。
次回候補: (1)層1候補1(奈良NEVER LAND)・候補2(那覇市)はヒアリング実施(オーナー承認後)まで
追加調査を保留、(2)層2・層3の探索継続(候補が得られた時点でG8上限値の実会場照合に着手)、
(3)他venture・アイデア領域の前進。
