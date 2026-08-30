# コースセットパシャッと

個人経営のボルダリングジム・クライミングジムのオーナーやフリーランスのルートセッター向けに、
課題(ルート)入れ替え作業後の簡単なメモと写真を送るだけで、AIがSNS(Instagram/X)投稿文・
公式LINE/Web告知文・課題入れ替え履歴の記録下書きをまとめて生成するサービス。

## 概要

- 対象顧客: 個人経営・小規模運営のボルダリングジム・リードクライミングジムのオーナー、
  複数ジムを掛け持ちするフリーランスのルートセッター。
- 入力: 課題入れ替え後のメモ(エリア・テープ色・難易度帯・本数・ムーブの特徴・改訂日など)
  + 任意で課題エリアの写真。
- 出力: (1)SNS投稿文下書き、(2)公式LINE/Web告知文下書き、(3)課題入れ替え履歴の簡易記録。
- 実際のルートセット作業・安全確認・グレーディングの最終判断はセッター本人が行う前提とし、
  本サービスは告知文・記録の下書き作成支援のみを行う(会員管理・決済・予約受付は扱わない)。

## ステータス

- フェーズ1(2026-08-07 10:00 UTC): venture新規作成。ideas.mdの原案(2026-08-07 10:00 UTC)を
  ベースに、市場調査の一次整理(market-research.md)とMVPの入出力フォーマット草案
  (mvp-flow-draft.md)を作成した。
- フェーズ2(2026-08-07 11:00 UTC): mvp-flow-draft.mdの入出力フォーマットをもとに、
  LLM生成エンジンのシステムプロンプト草案(llm-system-prompt-draft.md)を作成した。
  「変更なし」エリアの誤記載防止、写真有無に応じた文面調整、会員管理・予約・決済への
  不応答ルールなど、mvp-flow-draft.md・README.mdの前提を厳守事項として明文化した。
- フェーズ3(2026-08-07 12:00 UTC): llm-system-prompt-draft.mdの「次回以降の検討事項」
  だった構造化出力(JSON化)を具体化し、schema/output.schema.jsonを作成した。
  status(generated/out_of_scope/insufficient_input)で厳守事項7・8の分岐を、
  sns_post.mentions_photoで厳守事項3の分岐結果を、unchanged_areasで厳守事項2の
  検証を、それぞれ機械的に確認できる形にした。
- フェーズ4(2026-08-07 13:00 UTC): 「次にやること」1点目だったボルダリングジムのSNS運用実態の
  WebSearch調査を実施(sns-tone-research.md)。投稿頻度「週2〜3回」の目安と、ハッシュタグは
  「一般タグ+ジム独自のブランドタグ+地域タグ」の組み合わせが定石という知見を得て、
  llm-system-prompt-draft.mdの厳守事項4(ハッシュタグ候補)に反映した。個人経営ジムに
  特化した投稿実例・作成時間の定量データは公開情報からは見つからず、引き続き未検証。

- フェーズ5(2026-08-07 14:00 UTC): 「次にやること」1点目だった料金プラン・無料トライアル条件を
  仮決めした(pricing-plan.md)。line-reservation-aiのpricing-plan.mdの設計方針を踏まえつつ、
  双方向会話・予約状態管理が不要な単方向バッチ処理という特性から「月間生成回数」ベースのシンプルな
  3プラン(ライト/スタンダード/セッター複数)を設計し、sns-tone-research.mdの「投稿頻度週2〜3回」を
  想定利用回数の目安として反映した。課金単位は「1メッセージ送信=1回」と暫定決定。
- フェーズ6(2026-08-07 15:00 UTC): 「次にやること」1点目だったschema/output.schema.jsonの
  allOf条件分岐(if/then)が実際のLLM構造化出力機能でそのまま利用可能かを机上検証した
  (schema-structured-output-compat-check.md新規作成)。Claude Platform Docsの公開情報を
  確認したところ、Claude APIのStructured Outputsは`if`/`then`/`else`・`oneOf`を非対応と
  判明。schema/output.schema.jsonからallOf/if-thenを撤去し、トップレベル全プロパティを
  常時`required`化(該当しない場合は`null`を許容)する設計に改訂した。`status`の値に応じた
  null/非nullの依存関係は、line-reservation-aiのvalidate_test_cases.pyと同様にスキーマ単体
  ではなくコード側検証で担保する方針とした。

- フェーズ7(2026-08-07 16:00 UTC): 「次にやること」1点目だった改訂後のschema/output.schema.json
  に対応する期待JSON出力サンプルを作成し(schema/validate_test_cases.py新規作成)、line-reservation-ai
  のvalidate_test_cases.pyと同じ設計の机上バリデータでstatus⇔null/非nullの依存関係違反が
  ないか検証した(status別5パターン、全件パス。output-samples-validation.md参照)。schema単体
  では表現しない依存関係(status=generatedならsns_post等が非null、等)をコード側検証で
  機械的にチェックできることを確認した。実LLMでの生成安定性・厳守事項遵守率の検証は
  引き続きオーナー承認後のAPI接続時の課題として残る。
- フェーズ8(2026-08-07 17:00 UTC): 「次にやること」1点目だった実在の個人経営ボルダリング
  ジムの公式SNSアカウント・ブログの投稿例をWebSearchで観察した(sns-post-example-observation.md
  新規作成)。冒頭で色・グレード帯範囲+合計本数を要約する型と、「課題入れ替え」「ホールド替え」の
  語が同義に使われている実態を確認し、llm-system-prompt-draft.mdの厳守事項4に反映した。
  個人経営ジム単体の投稿頻度・作成時間等の定量データは引き続き公開情報からは見当たらず、
  sns-tone-research.mdと同じ結論(実ヒアリングでしか検証できない可能性が高い)となった。

- フェーズ9(2026-08-07 18:00 UTC): 「次にやること」1点目だった冒頭要約(色・グレード帯範囲+
  合計本数)指示のエッジケース机上検証を実施した(header-summary-edge-case-review.md新規作成)。
  正常系1件・エッジケース3件(一部エリアのみ更新/本数のみ欠落/全項目欠落)を検証し、
  (1)複数エリア中の一部更新時にエリア名の前置きが指示に無かった点、(2)合計本数・グレード帯の
  「両方欠けたら省略」なのか「片方だけでも省略」なのか曖昧だった点、の2つの改善点を発見。
  llm-system-prompt-draft.mdの厳守事項4を、エリア名前置きの明示と、片方のみ欠落時は
  明記されている項目だけで要約する部分省略ルールに改訂した。

- フェーズ10(2026-08-07 19:00 UTC): 「次にやること」1点目だった3エリア以上・項目の
  有無が混在する複合ケースの机上検証を実施した(multi-area-mixed-case-review.md新規作成)。
  更新対象エリアが2つ以上の場合はエリアごとに区切って列挙し、3つ以上の場合は各エリアの
  記述を「色(またはグレード帯)+本数」程度に簡潔化するルールを厳守事項4に追記した。
  派生課題として、出力3(履歴記録)がmvp-flow-draft.mdの「1メモ=1行」を暗黙の前提に
  しており、1回のメモで複数エリアを同時更新する場合の仕様が未整備な点を発見した。
- フェーズ11(2026-08-07 20:00 UTC): フェーズ10で発見した派生課題(出力3の複数エリア対応)
  に対応し、schema/output.schema.jsonの`history_row`(単一オブジェクト)を`history_rows`
  (配列)に改訂した。1メモ=1エリアの場合は要素数1、複数エリア同時更新の場合は要素数を
  更新エリア数に一致させる仕様とし、status=generatedのとき空配列は不可というルールを
  validate_test_cases.pyのクロスフィールド検証に追加した。3エリア同時更新の期待出力
  サンプル(G4_multi_area_single_memo)を新設し、全6件パスを確認。llm-system-prompt-draft.md
  内の`history_row`表記も`history_rows`に合わせて更新した。

- フェーズ12(2026-08-07 21:00 UTC): ドキュメント間の整合性を点検し、
  header-summary-edge-case-review.md・multi-area-mixed-case-review.mdの2ファイルに
  「次回以降の課題」「未着手」と記載されたまま残っていた、出力3(履歴記録)の複数行対応が
  実際にはフェーズ11(2026-08-07 20:00 UTC)で既にschema/output.schema.json改訂・
  schema/validate_test_cases.py(G4ケース)追加により解消済みだったことを確認し、
  両ファイルの記載を訂正した(実装・スキーマ自体への変更は無し。line-reservation-aiの
  「残課題の記載ミス」訂正と同種のドキュメント整合性メンテナンス)。

- フェーズ13(2026-08-07 22:00 UTC): 「次にやること」1点目だったpricing-plan.mdの価格帯・
  生成回数上限・課金単位の妥当性を検証するための想定顧客ヒアリングを設計した
  (customer-interview-design.md新規作成)。line-reservation-ai/customer-interview-design.mdの
  構成を踏襲し、個人経営ボルダリングジムオーナー3〜4件・複合ジムオーナー1〜2件・複数ジム
  掛け持ちセッター2〜3件を対象に、現状把握・価格感覚・体験内容・導入障壁・スコープ限定の
  受け止めの5カテゴリ全14問を設計した。実際の対象店舗・セッターへの連絡はオーナー許可が
  必要なアクションのため、設計のみにとどめ実施はしていない。

- フェーズ14(2026-08-07 23:00 UTC): 「次にやること」1点目だった対象候補の選定基準を
  line-reservation-ai/interview-candidate-selection-criteria.mdの構成を踏襲して新規作成した
  (interview-candidate-selection-criteria.md)。続けてWebSearchによる公開情報ベースの
  ロングリスト作成に着手し、個人経営ボルダリングジムオーナー区分で候補2件(FRICTION FREAKS・
  AT WALL)を特定した(candidate-longlist-draft.md第一弾)。複合ジムオーナー・複数ジム掛け持ち
  セッターの2区分は未着手として次回に持ち越した。実際の連絡は行っていない。
- フェーズ15(2026-08-08 00:00 UTC): 「次にやること」1点目だった複合ジムオーナー・複数ジム
  掛け持ちフリーランスセッターの2区分のロングリスト作成にWebSearchで着手した
  (candidate-longlist-draft.md第二弾)。いずれの区分も検索上位を大手・著名運営者の施設や
  著名セッターが占め、選定基準を満たす無名〜中堅の個人経営複合ジム・フリーランスセッターの
  新規候補は特定できなかった。複合ジム区分の保留候補として千葉市西千葉の「登攀道場」
  (個人事業主オーナー、SNS運用実績あり)を発見したが、リード壁の有無が公開情報から未確認の
  ため確定は次回に持ち越した。フリーランスセッター区分は、著名人名からの検索ではなく個人
  経営ジムの投稿から「ゲストセッター」等のタグ付けを辿る逆引きアプローチへの切替を申し送った。

- フェーズ16(2026-08-08 02:00 UTC): 「次にやること」1点目だった登攀道場のリード壁有無を
  WebSearchで確認した(candidate-longlist-draft.md第三弾)。CLIMBERS・CLIMBING-net・
  千葉市観光協会公式サイト等いずれも「ボルダリングジム」表記で一貫し、壁高4m(リード壁の
  一般的な高さ10m前後に対し、ボルダリング壁の標準的な高さ)・ロープ/ハーネス設備への
  言及なしと判明したため、複合ジム区分の候補からは除外と判断した。複合ジム区分は選定基準を
  満たす候補が引き続き0件のまま次回に持ち越し。

- フェーズ17(2026-08-08 03:00 UTC): 「次にやること」1点目だった候補1(FRICTION FREAKS)・
  候補2(AT WALL)の除外条件(大手チェーン該当性)・必須条件(課題入れ替え告知を自分で作成
  しているか)への該当有無をWebSearchで確認した(candidate-longlist-draft.md第四弾)。
  候補1は新潟市西区の単独店舗・セッター個人名入りの新課題投稿実績を確認し、個人経営
  ボルダリングジムオーナー区分の有力候補として確定。候補2は「AT WALL/SUN WALL/ESCAPE」
  という福岡市内3店舗展開の系列であることが新たに判明し、営業時間中はスタッフ常駐体制
  である可能性が高いことも判明したため、運営体制(スタッフ数)をヒアリング時に直接確認する
  必要がある留意点として記録した(候補からは除外せず保留条件付きで維持)。

- フェーズ18(2026-08-08 04:00 UTC): 「次にやること」1点目だったフリーランスセッター区分の
  逆引きアプローチ(「ゲストセッター」「セット協力」タグ付け人物を辿る探索)をWebSearchで
  実施した(candidate-longlist-draft.md第五弾)。複数のゲスト出演事例は見つかったが、いずれも
  別ジムの店長・スタッフの単発出演で、複数ジムを常時掛け持ちする個人事業主フリーランス
  セッターは3回連続(第二弾・逆引き含め)で特定できず。ルートセッター業界解説記事から、
  仕事の紹介経路がSNS発信より業界内人脈に依存する可能性が高いとの示唆を得た。個人のSNS
  公開情報探索での限界と判断し、フリーランスセッター区分を当面保留、個人経営ジムオーナー
  区分(候補1 FRICTION FREAKS確定済み)を優先する方針に切替を提案。

- フェーズ19(2026-08-08 05:00 UTC): 「次にやること」2点目だった、候補1(FRICTION FREAKS)を
  想定回答者とするヒアリングリハーサル台本(interview-rehearsal-script.md)をline-reservation-ai
  の構成(想定タイムテーブル→オープニング台本→質問ごとの補足ト書き→クロージング台本→
  確認ポイント)を踏襲して新規作成した。14問(A〜E)を目標13分に配分し、想定時間10〜15分の
  範囲内に収まる見込みであることを机上で確認した。候補1は単独店舗運営のためD.のQ13
  (掛け持ちセッターのアカウント分割)が該当しない可能性が高く、その場合の時間短縮余地も
  記録した。

- フェーズ20(2026-08-08 06:00 UTC): 「次にやること」だった候補2(AT WALL)の運営体制
  確認をWebSearchで追加実施した(candidate-longlist-draft.md第五弾)。運営主体が個人事業
  ではなく法人「株式会社ATWALL」(福岡県行橋市)であり、AT WALL・SUN WALL・ESCAPEの
  3店舗を運営していることが確定した。3店舗合計の従業員数は公開情報からは特定できず、
  必須条件「スタッフ数5名以下、またはオーナー1人でルートセットも兼ねる」を満たすかが
  不確実なため、候補1(FRICTION FREAKS)を主軸としAT WALLは目標件数未達時の予備候補に
  格下げした。これ以上の公開情報での深掘りは費用対効果が低いと判断し、AT WALLの運営体制
  調査はここで打ち切る。

- フェーズ21(2026-08-08 08:00 UTC): これまでschema/output.schema.jsonのフィールド
  説明に「本文中の言及との突き合わせ検証」という意図のみ記述され、実行可能なコードが
  存在しなかった2点(厳守事項2「変更なしエリアへの誤言及防止」・厳守事項3「写真有無に
  応じた文面調整」)を、初めて実行可能なPythonコードに落とし込んだ
  (`prototype/post_generation_checks.py`新規作成)。`check_mentions_photo_consistency()`は
  `sns_post.mentions_photo`の値と本文中の実際の写真言及有無の一致を、
  `check_unchanged_areas_not_mentioned_as_new()`は`unchanged_areas`に含まれるエリア名が
  本文中で「新着」「追加」等の語の近傍(かつ「変更なし」等の語が近傍に無い)に登場して
  いないかを、それぞれキーワード近傍探索のヒューリスティックで検証する。
  schema/validate_test_cases.pyの既存フィクスチャ(G1〜G4・OOS1・II1)全件が両チェックを
  パスすることと、意図的に違反させた入力(mentions_photo不一致・変更なしエリアの誤言及)が
  正しく検出されることを`prototype/test_post_generation_checks.py`(7件)で確認した
  (全件パス)。あくまでキーワード近傍探索であり違反を確実に検出できるわけではない点、
  実LLM接続後に拾いきれない違反パターンの収集・ルール改善が必要な点は今後の課題として残る。
  併せて、llm-system-prompt-draft.mdの「次の課題」一覧に残っていた、フェーズ11で既に
  解消済みだった項目(出力3の複数行対応)の記載漏れを訂正した(line-reservation-aiの
  「残課題の記載ミス」訂正と同種のドキュメント整合性メンテナンス)。

- フェーズ22(2026-08-08 11:00 UTC): mvp-flow-draft.md・schema/output.schema.jsonの
  history_rows説明で「スプレッドシート等へ手動転記する運用」とだけ記述され、実際の変換処理が
  存在しなかった点に対応し、`prototype/history_export.py`を新規作成した。history_rows配列を
  ヘッダー付きCSVテキスト(改訂日/エリア/テープ色・グレード帯/本数/特徴キーワード)に変換する
  `history_rows_to_csv_text()`を実装し、revision_date/countがnull(未抽出)の場合は
  「未記入」「不明」という統一プレースホルダーで表示することで、手動転記時にどの項目が
  未確認かを一目で分かるようにした。schema/validate_test_cases.pyの既存フィクスチャ
  (G1〜G4)をそのまま流用し、`prototype/test_history_export.py`(6件)で単一エリア・
  複数エリア(G4)・null値混在(G3)のいずれでも行数・プレースホルダーが期待通りになることを
  確認した(全件パス、既存のpost_generation_checks.pyのテスト7件・schema検証6件も
  引き続き全件パス)。line-reservation-aiのengine.pyと異なり、本ventureはLLM生成後の
  自然文組み立て(sns_post/line_web_notice本文)自体はLLMが担う設計のため、コード側で
  実装すべき決定的処理はhistory_rowsのCSV変換・post_generation_checksの検証系に限られる
  ことが改めて確認できた。

- フェーズ23(2026-08-08 13:00 UTC): 「次にやること」1点目だった、history_export.pyが
  生成するCSVテキストをオーナーが実際にスプレッドシートへ貼り付ける際の運用手順を
  `history-export-usage-guide.md`として新規文書化した。LINE返信メッセージ本文からの
  コピー範囲、Google スプレッドシート貼り付け時の自動列分割の挙動(Excelとの違い)、
  ヘッダー行重複防止、プレースホルダー(「未記入」「不明」)行の扱いを手順化した。
  併せて、複数エリア同時改訂時に貼り付け先セルを誤ると既存行を上書きするリスクを
  既知の限界として明記した(モバイルアプリ版・Excelでの自動列分割挙動は未検証のため
  今後の確認課題として残る)。本フェーズはドキュメント整備のみでコード変更は無し。

- フェーズ24(2026-08-08 14:00 UTC): 「次にやること」2点目だった、post_generation_checks.pyの
  ヒューリスティックの見直しに着手した。固定文字数の近傍窓(前後15文字)では、対象エリアとは
  無関係な**別エリア**の「変更ありません」が窓内に入り込み、対象エリア自身が新着扱いされている
  本物の違反(厳守事項2違反)を誤って見逃す(false negative)ケースがあることを机上レビューで
  発見した(例:「エリアDは変更ありません。エリアCに新着課題を追加しました。」で
  unchanged_areas=["エリアC"]としても検出漏れになっていた)。`_find_suspicious_area_mentions()`を
  固定文字数窓から「。」区切りの文単位判定に変更し、無関係な別文の言及が混入しないようにした。
  回帰テスト1件を追加し、既存分含め全8件・schema検証6件・history_export関連6件、いずれもパス
  確認済み(post-generation-checks-cross-area-review.md新規作成)。読点区切りで1文にまとまる
  ケース(「エリアDは変更なし、エリアCは新着」等)は文単位判定でも見逃しうる既知の限界として
  残した。実LLM接続後の実際の生成文での検証は引き続き今後の課題。

- フェーズ25(2026-08-08 15:00 UTC): 「次にやること」2点目だった、
  post_generation_checks.pyの読点区切りケース(「エリアDは変更なし、エリアCは新着課題を
  追加」)への対応に着手した。読点そのものでの分割は対象エリア自身の説明文中の読点
  (「エリアCは、新着課題を...」)まで誤って分断するリスクがあるため、代わりに
  `unchanged_areas`∪`history_rows[].area`の「既知のエリア名一覧」を境界として文を
  セグメント分割する方式(`_split_into_area_segments()`)を新規実装した。回帰テスト4件を
  追加し、既存分含め全12件・schema検証6件・history_export関連6件、いずれもパス確認済み
  (post-generation-checks-cross-area-review.md追記)。既知のエリア名一覧に無い第三の
  エリア名が混在するケースは引き続き見逃しうる既知の限界として残した(詳細は同ファイル参照)。

- フェーズ26(2026-08-08 17:00 UTC): 「次にやること」だった、個人経営ボルダリングジムオーナー
  区分の候補が候補1(FRICTION FREAKS)のみで選定プロセスの目安(区分ごとに1.5倍程度、
  個人経営ジム4〜6件)に不足している点に対応し、同区分の新規候補探索をWebSearchで再開した
  (candidate-longlist-draft.md第六弾)。神奈川県横浜市戸塚区の小規模ジム「Speedy」
  (2006年営業開始、公式Instagram運用あり)を候補3(暫定)として発見したが、指導者「田島さん」が
  オーナー本人か雇われインストラクターか、運営が個人事業主か法人かは公開情報からは特定できず、
  保留候補として記録した。新潟市の「8GRADE」は個人経営ジムの候補として挙がったが2022年12月に
  閉業済みと判明し除外。地域・キーワードを変えた複数回の検索でも、無名の個人経営ジムオーナーの
  SNS発信・紹介記事は開業ガイド記事やジム比較ポータルに埋もれて上位に出てきにくい傾向が
  フリーランスセッター区分と同様に見られ、これ以上の同方式での深掘りは費用対効果が下がりつつある。

- フェーズ27(2026-08-08 18:00 UTC): 「次にやること」1点目だった候補3(暫定)Speedy
  (横浜市戸塚区)の運営体制(オーナー本人か個人事業主か法人か)をWebSearchで追加確認した
  (candidate-longlist-draft.md第七弾)。「個人事業主」「運営会社」等のキーワードを変えた
  複数回の検索を試みたが、施設紹介記事以外に運営体制へ言及した情報は見つからず、公式サイトに
  特定商取引法に基づく表記等のページも存在しないことを確認した。候補2(AT WALL)の調査時と
  同様、これ以上の同方式での深掘りは費用対効果が低いと判断し調査を打ち切り、Speedyを候補2と
  同じ「予備候補」の位置づけに確定した。個人経営ボルダリングジムオーナー区分は確度の高い
  候補が候補1(FRICTION FREAKS)の1件のみという状態が3フェーズ連続で変わっておらず、
  同区分のこれ以上の探索はWebSearchでのスニペット調査ではなく、候補1へのヒアリング実施後に
  紹介・口コミ経由で追加候補を探す等、より直接的な手段への切り替えを検討課題とする。

- フェーズ28(2026-08-08 20:00 UTC): 「次にやること」2点目だった、history-export-usage-guide.md
  の手順3(自動列分割)がGoogle スプレッドシートのブラウザ版限定の未検証手順だった点に対応した。
  WebSearchでGoogle スプレッドシートのモバイルアプリ版・Excelでの挙動を調査し、(1)モバイル
  アプリ版はブラウザ版と異なり自動列分割機能・「テキストを列に分割」メニュー自体が存在せず
  `SPLIT`関数での代替が必要、(2)Excelは常時自動分割されるわけではなく、直近で「区切り位置」を
  カンマ区切りで実行した操作履歴がある環境でのみ自動適用される「学習型」の挙動、と判明した。
  手順3をブラウザ版/モバイルアプリ版/Excelの3パターンに具体化し、オーナーが実際に使う環境が
  未確定でもいずれのパターンでも迷わず対応できる案内にした(history-export-usage-guide.md更新)。
  コード変更は無し。

- フェーズ29(2026-08-08 21:00 UTC): line-reservation-aiで導入済みのGitHub Actionsによる
  テスト自動実行(ci-setup.md)が本ventureには未導入だった点に対応し、
  `.github/workflows/course-set-pasha-tests.yml`を新規作成した。
  `ventures/course-set-pasha/`配下への変更をトリガーに、prototype/のunittestスイート2本
  (test_history_export.py・test_post_generation_checks.py、計18件)と
  schema/validate_test_cases.py(6件)を自動実行する構成とし、ローカルで全件パスを確認済み
  (ci-setup.md新規作成)。実際のGitHub Actions上での実行結果(グリーン確認)は次回以降の
  セッションで確認する。アカウント作成・支払い・外部公開のいずれにも該当しないリポジトリ内
  設定のため承認不要と判断した。

- フェーズ30(2026-08-08 22:00 UTC): 「次にやること」1点目だった、フェーズ29で新設した
  course-set-pasha-tests.ymlの実際のGitHub Actions実行結果を、GitHub MCPツール
  (actions_list、method: list_workflow_runs)で確認した。run id 31280800500
  (head_sha: 3305297、フェーズ29のコミット)が`conclusion: success`であることを確認済み
  (line-reservation-aiのci-setup.mdで行った確認と同じ手順)。フェーズ29で新規作成した
  ci-setup.mdに、この確認結果を追記した。コード変更は無し。

- フェーズ31(2026-08-09 01:00 UTC): line-reservation-aiには存在しinitial-contact-message-draft.md
  として結実していた「ヒアリング候補への初回コンタクト依頼文面」の草案が本ventureには未作成
  だった点に対応し、interview-rehearsal-script.mdで想定回答者としていた候補1(FRICTION FREAKS)
  向けに新規作成した(initial-contact-message-draft.md)。メール用(長め)・Instagram DM用
  (短め)・電話用トーク要点の3パターンに加え、候補1が公式Instagramで新着課題を継続発信している
  実績(candidate-longlist-draft.md第四弾)を踏まえInstagram DMを第一候補チャネルとする方針を
  明記した。候補2(AT WALL)の法人・複数店舗展開という留意点も反映済み。実在店舗への実際の送信は
  一切行っておらず、pending-approval.mdに実施の承認可否を新規記録した(2026-08-09 01:00 UTC)。
- フェーズ32(2026-08-09 03:00 UTC): post_generation_checks.pyが厳守事項2・3のみを
  機械チェック化しており、厳守事項9(絵文字は出力1のみ1〜2個程度まで、出力2・3は不使用)が
  方針の記述のみで検証コードが無いまま残っていた点に対応した。`check_emoji_usage_rules()`を
  新規実装し、絵文字が集中する主要Unicodeブロックを対象としたヒューリスティック
  (`EMOJI_PATTERN`)で、sns_post.bodyの絵文字が2個を超える場合・line_web_notice.bodyに
  絵文字が含まれる場合・history_rows[].feature_keywordsに絵文字が含まれる場合を検出する。
  `run_all_checks()`に組み込み、テスト7件を新規追加(既存12件と合わせて19件)。
  schema検証6件・history_export関連6件と合わせて全件パス確認済み
  (post-generation-checks-cross-area-review.md追記)。絵文字の完全網羅ではないヒューリスティック
  である点は既存の厳守事項2・3チェックと同じ限界として残した。

- フェーズ33(2026-08-09 05:00 UTC): post_generation_checks.pyが厳守事項2・3・9のみを
  機械チェック化しており、厳守事項4・5(SNS投稿文・LINE/Web告知文それぞれで本数を明示する
  指示)について、history_rows(構造化データ)側のcountと本文側の記載が食い違っていないかを
  確認するチェックが無いまま残っていた点に対応した。`check_history_row_counts_mentioned_in_text()`
  を新規実装し、history_rows[]の各行のcount(null以外)が、sns_post.body・line_web_notice.body
  のいずれかに数字として登場しているかを確認する(OR判定、G2フィクスチャのように出力1・
  出力2で本数の記載場所が分かれるケースに対応)。`run_all_checks()`に組み込み、テスト6件を
  新規追加(既存19件と合わせて25件)。schema検証6件・history_export関連6件と合わせて
  全件パス確認済み(post-generation-checks-cross-area-review.md追記)。数字の文字列一致による
  緩いヒューリスティックであり、同じcount値を持つ複数エリアの厳密な対応関係までは検証しない
  点は既知の限界として残した。
- フェーズ34(2026-08-09 06:00 UTC): フェーズ32のpost-generation-checks-cross-area-review.md
  「残る既知の限界」に残っていた、`EMOJI_PATTERN`が地域指示記号(国旗絵文字を構成する
  U+1F1E6-U+1F1FF)・囲みCJK文字(🈵🈲等、U+1F200-U+1F2FF)を対象範囲外としていた点に対応した。
  日本語が主要な出力言語である本ventureでは囲みCJK記号の見落としが実害になりやすいと判断し、
  この2ブロックを`EMOJI_PATTERN`に追加した。`prototype/test_post_generation_checks.py`に
  新規テスト2件を追加(既存25件と合わせて27件)。schema検証6件・history_export関連6件と
  合わせて全件パス確認済み(post-generation-checks-cross-area-review.md追記)。Unicode絵文字の
  完全網羅ではない点(囲み英数字補助の一部・将来のUnicode改定分は未対応)は既知の限界として残した。

- フェーズ35(2026-08-09 07:00 UTC): post_generation_checks.pyが厳守事項2・3・4・5・9のみを
  機械チェック化しており、厳守事項7(会員管理・予約受付・決済に関する記述への不応答)に
  ついて、status=out_of_scope分岐そのものの妥当性(schema/validate_test_cases.py)しか
  検証されておらず、status=generatedと判定されたケースの本文自体にこれらの話題が
  紛れ込んでいないかを確認するチェックが無いまま残っていた点に対応した。
  `check_no_out_of_scope_topics_in_generated_output()`を新規実装し、status=generatedの
  ときのみsns_post.body・line_web_notice.bodyを対象に会員・予約・決済等のキーワード出現を
  検出する(status=out_of_scopeのout_of_scope_message自体がこれらの語を含意的に使う
  ケースは対象外として誤検出を回避)。`run_all_checks()`に組み込み、テスト4件を新規追加
  (既存27件と合わせて31件)。schema検証6件・history_export関連6件と合わせて全件パス
  確認済み(post-generation-checks-cross-area-review.md追記)。

- フェーズ36(2026-08-09 09:00 UTC): フェーズ33で追加したcheck_history_row_counts_mentioned_in_text()が
  history_rows[].countと本文の本数記載の整合性のみを検証しており、同じ厳守事項4・5が求める
  「エリア・改訂日の明示」のうち、エリア名自体が本文に一切登場していないケース(本数だけ
  書かれてエリア名の記載が丸ごと抜け落ちている等)を検出するチェックが無いまま残っていた点に
  対応した。`check_updated_areas_mentioned_in_text()`を新規実装し、history_rows[].area
  (null以外)の値がsns_post.body・line_web_notice.bodyのいずれかに登場しているかを確認する
  (既存の本数チェックと対をなす位置づけ)。`run_all_checks()`に組み込み、テスト6件を新規追加
  (既存31件と合わせて37件)。schema検証6件・history_export関連6件と合わせて全件パス
  確認済み(post-generation-checks-cross-area-review.md追記)。エリア名の完全一致のみで
  判定するため、本文側での表記ゆれ(略称化等)は誤検出しうる既知の限界として残した。

- フェーズ37(2026-08-09 18:00 UTC): mvp-flow-draft.md「会話フロー・技術構成に関する方針」で
  「技術構成の具体化は次回以降の課題」とされたまま未着手だった点に対応し、
  line-reservation-ai/tech-stack.mdの構成を踏襲して`tech-stack.md`を新規作成した。
  本ventureは双方向の会話状態管理・予約枠管理が不要な単方向バッチ処理であるため、
  ConversationFlowStateMachine相当の仕組みやFirestoreのような永続データストアは不要とし、
  「LINE Messaging API ⇄ Webhook(GCP Cloud Functions) ⇄ LLM(3出力生成) ⇄ 返信」という
  シンプルな構成を採用する方針を整理した。画像添付は内容解析せず「有無」のみを判定材料とする
  設計方針も明記した。ホスティング基盤(GCP Cloud Functions)・LINE料金体系は
  line-reservation-aiの既存調査結果を流用できる旨も記録した。コード変更は無し。
- フェーズ38(2026-08-09 22:00 UTC): tech-stack.mdの「次のステップ候補」で挙げていた
  Webhook受信〜LLM呼び出し〜返信のバックエンド処理フロー(line-reservation-aiの
  prototype/cloud_function_webhook.py相当)を設計・実装した(webhook-processing-flow-design.md
  新規作成)。line-reservation-aiと異なり会話状態を持たない単発リクエスト/レスポンス型のため、
  Cloud Function A/B分離やCloud Tasksは不要と判断し1フローに統合。`prototype/
  cloud_function_webhook.py`に`process_memo_event()`を新規実装し、
  schema/validate_test_cases.pyのvalidate_against_schema()・validate_cross_field_rules()と
  prototype/post_generation_checks.pyのrun_all_checks()を組み合わせた3段階検証、
  検証失敗時の安全側フォールバック(定型の再送依頼文言)、status別の返信文組み立て
  (generated時は出力1・2・3を1通にまとめる、prototype/history_export.pyのCSV変換を再利用)を
  実装した。テキストのみのメッセージのみを処理対象とし、画像単体イベントは素通り(処理対象外)
  とする設計とした。テスト12件新規追加(全55件パス)。テキスト+画像が別イベントで届く場合の
  束ね方は、tech-stack.mdから引き続き残課題として持ち越した。
- フェーズ39(2026-08-09 23:00 UTC): webhook-processing-flow-design.md「残課題」(2)
  検証失敗時のリトライ機構に対応した。line-reservation-aiのjson-output-retry-fallback.mdの
  「同一入力で1回だけ再生成、無限リトライは避ける」方針を踏襲し、`process_memo_event()`に
  1回のみのリトライを実装した。`LlmCallClient.generate()`に`retry_context`(検証エラー概要、
  実LLM接続後にプロンプトへ添える想定)引数を追加し、1回目の検証エラー後に
  `retry_context`付きで再生成をリクエスト、2回目も検証エラーが残る場合のみ安全側の
  再送依頼フォールバックに倒す。本ventureは`confirmed`・二重予約防止のような確定状態を
  持たないため、line-reservation-ai側にある「フォールバック経路は`confirmed`を常にfalse
  扱いにする」といった分岐は不要と判断し実装しなかった。`MemoProcessResult.retried`を
  追加しリトライ発生を呼び出し側で判別可能にした(json-output-retry-fallback.mdの
  「ログ・監視」方針同様、実運用時にリトライ発生件数を集計する用途を想定)。テスト3件を
  新規追加(既存55件と合わせて58件、全件パス)。矛盾検知(自然文とJSONの内容不一致)は
  本venture出力に確定/未確定のような対立フィールドが無いため対象外とした。
- フェーズ40(2026-08-10 07:00 UTC): webhook-processing-flow-design.md「残課題」だった
  テキスト+画像が別イベントで届く場合の束ね方を設計した(text-image-bundling-design.md
  新規作成)。「同一Webhookリクエスト内で複数イベントが届く場合(ケースA)」と
  「別リクエストに分かれる場合(ケースB)」に分け、ケースAは`prototype/
  cloud_function_webhook.py`に`merge_text_and_photo_events()`として実装(`source.userId`
  単位でグルーピングし、テキスト1件+画像0件以上のグループを`hasPhoto`付き単一メモへ統合、
  誤統合を避けるためテキスト0件・2件以上のグループは統合しない)。ケースBは、本ventureが
  意図的に会話状態マシンを持たない単発リクエスト/レスポンス型を選んだ設計方針
  (tech-stack.md)と衝突するFirestore等の永続化・TTL管理が必要になるため、実LINE接続後の
  実測データで頻度が無視できない水準と分かるまで実装を見送る判断とした。テスト6件新規追加
  (既存58件と合わせて64件、全件パス)。
- フェーズ41(2026-08-10 11:00 UTC): 「次にやること」に残っていたLINE Messaging APIの
  画像メッセージ受信時のコンテンツ取得API仕様確認・複数画像添付時の扱いを
  line-image-content-api-review.mdで整理した。本venture既存実装
  (merge_text_and_photo_events())を確認した結果、画像の有無判定はWebhookイベントの
  `message.type`のみで行っており画像バイナリ自体は使わない設計のため、コンテンツ取得API
  (GET /v2/bot/message/{messageId}/content)自体がMVPスコープでは不要と結論づけた。複数
  画像添付時もLINEアプリの複数枚送信は画像ごとに個別イベントとして届く(WebSearchで確認、
  developers.line.biz一次情報はWebFetchのegressプロキシ制約により未確認)想定と整合しており、
  既存のhasPhoto(有無フラグ)方式で追加実装なしに対応済みと確認した。tech-stack.mdの
  該当項目を解消済みとして更新した。
- フェーズ42(2026-08-10 14:00 UTC): これまで「顧客とのSNS投稿文・告知文生成」の設計が
  中心だったが、line-reservation-aiのlanding-page-copy-draft.mdを参考に「オーナー・セッターが
  本サービスを知って申し込むまで」の導線で使うLPコピー草案を初めて作成した
  (landing-page-copy-draft.md)。market-research.mdのペインポイント・競合仮説とpricing-plan.mdの
  料金プラン・無料トライアル条件をそのまま反映。残課題は特定商取引法に基づく表記・プライバシー
  ポリシー文面(本venture未着手、line-reservation-aiのlegal-notices-draft.md相当)の作成と、
  LPワイヤーフレームの作成。実際のLP実装・公開はオーナー承認待ちの範囲。
- フェーズ43(2026-08-13 18:00 UTC): フェーズ42の残課題1点目だった特定商取引法に基づく表記・
  プライバシーポリシーの文面草案(legal-notices-draft.md)を新規作成した。
  line-reservation-ai/legal-notices-draft.mdの構成(前提・未確定事項→特商法表記→
  プライバシーポリシー→次のステップ候補)を踏襲しつつ、本venture固有の差異(双方向の会話・
  予約枠管理を持たない単方向バッチ処理のため会員個人のLINEユーザーID等は原則取得しない設計、
  SNS投稿文の対外発信という性質からステルスマーケティング規制との関係を独自論点として追加)を
  反映した。決済代行サービスの選定(line-reservation-aiのdeposit-payment-research.md相当)は
  本ventureで未着手のため、支払方法欄は暫定の想定にとどめた。事業者名・所在地等の運営主体情報は
  引き続き【要記入】のまま、実際の文面確定・LP掲載はオーナー承認待ちの範囲とした。
- フェーズ44(2026-08-13 23:59 UTC): フェーズ42の残課題2点目だったLPワイヤーフレーム
  (landing-page-wireframe.md)を新規作成した。aircon-pasha/line-reservation-aiと同様に
  テキストベースのモバイル1カラムワイヤーフレームとし、画像コンセプトは他2ventureと役割が
  重複しないよう「Instagram投稿プレビュー(完成済み投稿を1枚で見せる)」をヒーロー画像に
  採用した(aircon-pashaはメモ→完了報告文のビフォーアフター、line-reservation-aiはLINEトーク
  画面が軸)。セクション構成・CTA文言・料金表記はlanding-page-copy-draft.md・pricing-plan.mdと
  整合させた。実際の画像制作・HTML/CSS実装・公開は未着手のままオーナー承認待ちの範囲とした。
- フェーズ45(2026-08-14 04:00 UTC): legal-notices-draft.mdの残課題だった「決済代行サービスの
  選定(line-reservation-aiのdeposit-payment-research.md相当の調査)は未着手」に対応し、
  line-reservation-ai/subscription-billing-cost-estimate.mdの構成・観点を踏襲した
  月額サブスク決済手数料試算(subscription-billing-cost-estimate.md)を新規作成した。
  本venture固有の料金水準(1,980円/3,480円/5,980円)に当てはめ、クレジットカード継続課金
  (3.6%と仮定)で手数料71〜215円/月・インフラ原価を大きく上回る規模と試算した。本venture
  はデポジット徴収を持たず決済経路が1本のみである点、月間生成回数の上限超過時の挙動が
  未設計である点をline-reservation-aiとの差異として整理し、後者はpricing-plan.mdの
  「未検証の仮説」に追記した。
- フェーズ46(2026-08-14 07:00 UTC): フェーズ45・subscription-billing-cost-estimate.mdで
  優先度の高い未決事項として挙げていた「月間生成回数の上限超過時の挙動」を仮決めした
  (pricing-plan.md「月間生成回数の上限超過時の挙動(仮決め)」節)。aircon-pasha/
  pricing-plan.mdの月固定枠+超過分従量課金の方針を踏襲しつつ、aircon-pashaが前提とする
  構造的な繁忙期需要増とは異なり本ventureは月間利用回数が比較的安定していると見込まれる点を
  踏まえ、超過を「稀なスパイク」として利用制限ではなく従量課金(150円/120円/100円、プランが
  上がるほど単価を下げる)で機会損失なく吸収する設計を採用した。上限接近時の事前通知設計は
  未着手のまま次の課題とし、従量課金には決済代行サービス側の都度課金対応可否確認が必要な点を
  新たな論点としてsubscription-billing-cost-estimate.mdの決済方式選定に紐づけた。
- フェーズ47(2026-08-14 09:00 UTC): フェーズ46の残課題だった上限接近時の事前通知設計に
  着手した(limit-approaching-notification-design.md新規作成)。設計に着手した時点で、
  月間生成回数を積算するにはtech-stack.mdが前提とする「永続データストア不要」という方針を
  一部見直す必要があることに気づき、Firestore等の軽量データストアをユーザー1人=1
  ドキュメント(month・countのみ)という最小構成で新規導入する方針とした。通知は新規の
  プッシュメッセージ課金を避けるため、残り2回に達した生成完了時の通常返信に1文追記する
  方式を採用し、line-reservation-ai/candidates-expired-notification-design.mdの
  「プッシュ通知は課金・体験の両面でコストが高い」という論点を踏襲した。実装
  (`usage_counter`インターフェースの追加、Firestore接続)はオーナー承認待ちの範囲として
  設計のみに留め、tech-stack.md本体・subscription-billing-cost-estimate.mdへの反映
  (Firestore読み書き課金の原価試算追加)は次回以降の課題として残した。
- フェーズ48(2026-08-14 11:00 UTC): フェーズ47の残課題だった、月間生成回数カウント導入に
  伴うtech-stack.md本体への反映とsubscription-billing-cost-estimate.mdへの原価試算追加を
  行った。tech-stack.mdには「永続データストア不要」の例外としてコンポーネント5(月間生成回数
  カウントの保存先)を追記し、MVPスコープにも反映した。subscription-billing-cost-estimate.md
  には、1回の生成あたり読み取り1回・書き込み1回のみという最小操作量を前提に、
  line-reservation-ai/firestore-traffic-cost-estimate.mdと同じ観点で試算を行い、
  書き込み無料枠(20,000回/日)基準で仮に1オーナーあたり上限一杯の20回/日利用でも
  約1,000オーナー分まで無料枠内に収まる見込みであることを確認した。決済手数料
  (71〜215円/月)に比べFirestore原価は無視できる水準という結論を得た。実際のFirestore
  接続・計測は引き続きオーナー承認待ちの範囲として残る。
- フェーズ49(2026-08-14 14:00 UTC): フェーズ46・subscription-billing-cost-estimate.mdで
  新たな論点として残していた「従量課金には決済代行サービス側の都度課金対応可否確認が必要」に
  対応し、WebSearchでStripe Billing・Squareの2社を比較調査した
  (payment-processor-metered-billing-usage-research.md新規作成)。Stripe Billingは
  「Metered billing」「Flat fee with overages」を標準機能として提供しており、本ventureが
  仮決めした「月固定枠+超過分従量課金・プラン別単価」構成をそのまま実現できる可能性が高いと
  判断した。一方Squareは従量課金の自動化に相当する機能が日本語公開情報からは見当たらず、
  超過分の請求には「定期請求書」の都度手動発行に近い運用が必要になる見込みで、本venture
  用途にはStripe Billingを優先候補とした。WebFetchのegressプロキシ制約で一次情報
  (開発者ドキュメント)への直接アクセスができず検索結果の要約ベースの判断にとどまる点は
  既知の限界として明記した。実際の契約・アカウント開設・API接続は引き続きオーナー承認待ち。
- フェーズ50(2026-08-14 15:00 UTC): フェーズ49の「次の課題」だった、国内決済代行サービス
  (GMOペイメントゲートウェイ/fincode byGMO・Univapay)の従量課金対応可否をWebSearchで追加
  調査した(payment-processor-metered-billing-usage-research.md追記)。両社ともサブスクリプション
  (定額継続課金)機能自体は確認できたが、Stripe Billingの「Metered billing」に相当する
  利用量に応じた自動従量課金機能を裏付ける一次情報にはWebSearchの範囲では到達できず、
  「未確認・要精査」にとどめた。暫定結論(Stripe Billing優先)を覆す材料は得られなかった。
  あわせて、フェーズ49で「次の課題」としていたStripe Billing採用時の超過課金分の決済手数料
  試算をsubscription-billing-cost-estimate.mdに追記した(超過単価150円/120円/100円に3.6%を
  仮定適用し、手数料控除後の実質超過単価を算出)。実際の料率・国内2社の従量課金対応の一次情報
  確認は、アカウント開設(オーナー承認待ち)後の課題として残る。
- フェーズ51(2026-08-14 19:00 UTC): ドキュメント間の整合性を点検し、
  payment-processor-metered-billing-usage-research.mdの「次の課題」に「Stripe Billingの
  従量課金採用時の決済手数料試算をsubscription-billing-cost-estimate.mdに追記する」が未着手
  として残っていたが、実際にはフェーズ50(2026-08-14 15:00 UTC)で
  subscription-billing-cost-estimate.md「超過課金分の決済手数料試算」節として既に対応
  済みだったことを確認し、記載を訂正した(実装・試算内容自体への変更は無し。フェーズ12・
  フェーズ22と同種のドキュメント整合性メンテナンス)。
- フェーズ52(2026-08-15 04:00 UTC): これまで未着手だった解約・ダウングレード時のLINE案内
  文言・処理フローを新規設計した(subscription-cancellation-flow-design.md)。
  line-reservation-ai/billing-upgrade-flow-design.mdがトライアル→有料移行(拡大方向)を
  扱っていたのに対し、本フェーズは解約・プラン縮小という逆方向を扱う。Stripeのプロレーション
  (日割り精算)標準機能を前提に、解約意図検知→案内メッセージ→Stripeカスタマーポータルでの
  手続き→Webhook受信→完了メッセージ、という流れを設計した。新規の未確定事項として、
  (1)「解約」インテントの誤検知防止境界の設計、(2)ダウングレード時の当月生成回数上限の
  適用方法(変更前/変更後どちらを適用するか)が残った。
- フェーズ53(2026-08-15 05:00 UTC): フェーズ52の未確定事項(1)だった「解約」インテントの
  誤検知防止境界を、line-reservation-ai/faq-escalation-boundary.mdの「店舗登録済みの
  固定情報かどうか」で線引きする考え方を参考にllm-system-prompt-draft.mdの厳守事項7aとして
  新設した。解約意思が明確な場合(i)・プラン変更の意思表示(ii)・雑談の域を出ない表現
  (iii、解約案内を送らない)・判断がつかない場合(iv、意思確認のみ返し断定案内はしない)の
  4分類とした。schema/output.schema.jsonへの反映(status enum拡張案の設計)は未着手のまま
  次の課題として残した。
- フェーズ54(2026-08-15 08:00 UTC): フェーズ53の残課題だった、厳守事項7a(解約意図検知)の
  schema/output.schema.jsonへの反映を行った。`status`のenumへ`cancellation_intent`
  (i.解約意思明確)・`downgrade_intent`(ii.プラン変更)・`cancellation_unclear`(iv.判断不能)
  の3値を追加し(iii.雑談は新規enum値を設けず既存3値に帰着)、これらのときのみ非nullとなる
  `subscription_procedure_notice`オブジェクト(kind/body/includes_portal_link)を新設した。
  `includes_portal_link`は厳守事項7a(iv)の「ポータルリンク・解約完了前提の文言を含めない」を
  機械的に検証する補助フィールドとして追加した。schema/validate_test_cases.pyにCI1〜CI3
  (解約明確・ダウングレード・判断不能の3ケース)を追加し、既存6ケースへの
  `subscription_procedure_notice: null`追記とあわせ計9件全件パスを確認した。実LLM接続後の
  分類精度検証(厳守事項7a(iii)雑談と(iv)判断不能の切り分けの妥当性含む)は引き続き
  オーナー承認待ちの範囲として残る。
- フェーズ55(2026-08-15 12:00 UTC): 「次にやること」に残っていた、ダウングレード時の
  当月生成回数上限の適用方法(変更前/変更後どちらを適用するか)をWebSearchでStripe公式
  ドキュメント(Prorations・Change the price of existing subscriptions等)を調査し確定した
  (subscription-cancellation-flow-design.md「ダウングレード時の当月生成回数上限の適用方法
  (確定)」節新設)。同一課金間隔のプラン変更では`billing_cycle_anchor`(請求サイクル基準日)が
  リセットされないというStripeの挙動を確認し、当初の仮決め(変更後プランの上限を即時適用し
  `count`はリセットしない)がそのまま成立することを確認した。実装への反映点(`usage_counter`の
  上限値参照先をStripe Webhookの最新プランIDに紐づける必要がある点)を留意点として追記した。
  WebFetchのegressプロキシ制約で一次情報への直接アクセスはできず検索結果の要約ベースの
  判断にとどまる点は既知の限界として残した。
- フェーズ56(2026-08-15 13:00 UTC): post-generation-checks-cross-area-review.mdで
  気づいた、厳守事項7a(iv)「cancellation_unclearのときは手続き完了・Stripeカスタマー
  ポータルへの言及を含めない」が本文の文言レベルでは未チェックだった点に対応し、
  `check_subscription_notice_consistency()`をprototype/post_generation_checks.pyに新規実装した。
  cancellation_unclear時にポータル・手続き完了系キーワードが混入していないか、
  cancellation_intent/downgrade_intent時にincludes_portal_link=trueと本文の言及が
  食い違っていないかの2方向を検証する。test_post_generation_checks.pyに新規テスト6件を
  追加し既存37件と合わせて全43件パス確認済み(schema/validate_test_cases.pyのCI1〜CI3
  フィクスチャを含む)。
- フェーズ57(2026-08-15 20:00 UTC): フェーズ56の残課題だった「『ポータル』を含まない
  別表現でのリンク案内を拾いきれるか」を検証した。line-reservation-aiの
  billing-upgrade-flow-design.mdが実際に「マイページ」「決済ページ」表記を使っている
  ことを確認し、`PORTAL_KEYWORDS`に両語と「手続きページ」を追加。あわせて
  subscription-cancellation-flow-design.mdの文言例(「▼ 解約手続きはこちら
  {Stripeカスタマーポータル URL}」)のようにURLプレースホルダのみでキーワードを含まない
  ケースも拾えるよう、`{...URL}`形式のプレースホルダ・http(s)リンクを検出する
  `LINK_PLACEHOLDER_PATTERN`を新設し`body_mentions_portal`判定に合流させた
  (prototype/post_generation_checks.py)。test_post_generation_checks.pyに新規テスト4件
  (マイページ表記のみでのcancellation_unclear違反検知、URLプレースホルダのみでの
  cancellation_unclear違反検知、マイページ表記のみでのcancellation_intent許容、
  URLプレースホルダのみでのcancellation_intent許容)を追加し、test_post_generation_checks.py
  は既存43件と合わせて全47件パス。prototype/配下の全テストファイル(discover実行)でも
  全74件パス、schema/validate_test_cases.pyも9件中9件パス確認済み。
  残る既知の限界は、キーワード・URLのいずれも含まない「短縮リンクサービス名のみ」
  「こちらまでご連絡ください」等の婉曲表現は依然未検出な点で、実LLM接続後に実際の
  生成文パターンが得られた段階で語彙・パターンを追加していく方針とする。
- フェーズ58(2026-08-15 22:00 UTC): 厳守事項7(会員管理・予約受付・決済への不応答)の
  機械チェック`check_no_out_of_scope_topics_in_generated_output()`が「会員」「決済」
  「予約」等の直接語のみを対象としており、ボルダリングジムで実際によく使われる
  言い回し(「月会費を改定します」のように「会員」を使わない会員管理の話題、
  「当日キャンセルはお電話にて」のように「予約」を使わない予約関連の話題)を取りこぼす
  疑いがあった点に対応した。フェーズ57のPORTAL_KEYWORDS拡張と同じ考え方で
  `OUT_OF_SCOPE_TOPIC_KEYWORDS`に「会費」「キャンセル」を追加した(「月会費」は
  「会費」の部分文字列一致で既に検出可能なため別途追加せず)。
  `prototype/test_post_generation_checks.py`に新規テスト2件を追加し
  (既存47件と合わせて全49件)、`prototype/`配下の全テストファイル(discover実行)でも
  全76件パス、schema/validate_test_cases.pyも9件中9件パス確認済み
  (post-generation-checks-cross-area-review.md追記)。残る既知の限界(「入会金」
  「月謝」等、他に取りこぼしている言い回しが無いかの確認)は実LLM接続後の生成品質
  検証に委ねる。
- フェーズ59(2026-08-16 05:00 UTC): フェーズ57の残課題だった「短縮リンクサービス名のみ」
  (httpスキームなしでbit.ly等のドメイン名のみを本文に貼るケース)の取りこぼしに対応した。
  `LINK_PLACEHOLDER_PATTERN`のhttps?://判定はスキームを省略した短縮URL表記
  (例:「手続きはこちら bit.ly/xxxxx」)を素通りしてしまうため、主要な短縮URLサービス
  (bit.ly・lin.ee・tinyurl.com・t.co・x.gd・is.gd)のドメイン名を検出する
  `SHORT_URL_DOMAIN_PATTERN`を新設し、`body_mentions_portal`判定に合流させた
  (prototype/post_generation_checks.py)。LINE公式のURL短縮サービスであるlin.eeを
  含めたのは、本ventureの配信チャネル(LINE公式アカウント)との親和性を踏まえたもの。
  test_post_generation_checks.pyに新規テスト2件(bit.ly短縮URLのみでの
  cancellation_unclear違反検知、lin.ee短縮URLのみでのcancellation_intent許容)を追加し、
  既存49件と合わせて全51件パス。prototype/配下の全テストファイル(discover実行)でも
  全78件パス、schema/validate_test_cases.pyも9件中9件パス確認済み。
  残る既知の限界は、ドメイン・URLの手がかりを一切伴わない「こちらまでご連絡ください」
  のような純粋な婉曲表現で、本文中に検出可能な文字列が存在しないため機械チェックでは
  原理的に検出できない。実LLM接続後に実際の生成文パターンが得られた段階で、この種の
  表現が実際に出現するか・出現した場合にどう扱うか(許容/システムプロンプト側での
  抑制)を改めて検討する。
- フェーズ60(2026-08-16 08:00 UTC): これまで料金プラン・技術構成・生成ルールは個々に
  設計してきたが、「申込から実際にLINE公式アカウントで課題入れ替え下書きの生成が始まるまで、
  オーナー・セッターは何をどの順番で行うのか」という一連の導入フロー自体は未文書化だった。
  line-reservation-ai/onboarding-guide.mdの構成を踏襲し、本venture固有の単方向バッチ処理・
  最小限の初期設定(ジム名・地域名は任意入力)を反映したonboarding-guide.mdを新規作成した。
  ジム名・地域名の入力を申込フォームに統合するか専用設定ページを持つかは方針未確定のまま
  次の課題として残した。
- フェーズ61(2026-08-16 10:00 UTC): フェーズ60で未確定のまま残した2点を設計した
  (onboarding-settings-and-self-check-design.md新規作成)。(1)ジム名・地域名は専用設定
  ページを持たず申込フォームへ統合する方針で確定。複数ジム掛け持ちセッター向けにカンマ
  区切りの自由記述欄で複数組を許容する案とした。(2)接続テスト(ステップ4)省略時の
  フォールバックは、line-reservation-aiのfirst-booking-self-check-notification-design.mdを
  参考に「そのユーザーにとって最初の生成成功時にのみ確認案内を1回付記する」設計とした。
  本ventureは会話状態機械のようなインメモリの継続インスタンスを持たないため、
  line-reservation-aiと異なりフラグは`usage_counter`ドキュメントへの永続化が必要になる
  という構造的な違いも整理した。実装(`first_generation_notice_sent`フィールド追加・
  webhook処理への配線)は実Firestore/実LINE API接続と合わせてオーナー承認待ちとして残る。
- フェーズ62(2026-08-16 13:00 UTC): フェーズ61・onboarding-settings-and-self-check-design.md
  の残課題だった「ジム名・地域名の複数組入力(カンマ区切り)をLLMシステムプロンプト側で
  どう構造化して優先順位ルールを適用するか」を設計し、llm-system-prompt-draft.mdの
  厳守事項4に反映した。入力メモの本文中にいずれかのジム名への言及があればそのジム名に
  対応する組のブランドタグ・地域タグを優先採用し、言及が無ければ登録順で先頭の組を
  既定値として採用するルールを追記した。残るのは`usage_counter`への
  `first_generation_notice_sent`フィールド追加・実配線(実Firestore/実LINE API接続と
  合わせてオーナー承認待ち)のみとなり、onboarding-settings-and-self-check-design.mdの
  残課題2点はいずれも設計完了した。
- フェーズ63(2026-08-16 16:00 UTC): フェーズ62の残課題だった`usage_counter`への
  `first_generation_notice_sent`フィールド追加・webhook処理への配線について、
  実際のFirestore/LINE API接続とは切り離せる範囲(フィールド定義・書き込みタイミングの
  疑似コード)を設計した(first-generation-notice-implementation-design.md新規作成)。
  `count`が0か否かで初回判定を行い、count増分とフラグ更新を単一ドキュメント更新に
  まとめることで重複送信を防ぐ設計とした。実際のFirestore接続・実装への反映は
  引き続きオーナー承認待ちの範囲として残る。
- フェーズ65(2026-08-17 07:00 UTC): line-reservation-aiのapi-call-failure-handling.mdに
  相当する「LLM API/LINE API呼び出し自体の失敗時(タイムアウト・5xx・429等)のハンドリング」
  設計が本ventureには未着手だった点に対応し、api-call-failure-handling.mdを新規作成した。
  本ventureはCloud Tasksを持たない単発リクエスト/レスポンス型でPush APIではなくReply API
  (トークンは1回限り・短時間で失効)のみを使う点、送信者が顧客ではなく事業者本人であり
  状態変更を一切伴わない点がline-reservation-aiとの本質的な違いであり、これを踏まえ
  「即時1回のみリトライ、2回とも失敗時はフォールバック文言(LLM側)または諦めて
  reply_sent=Falseで返す(Reply側、Push APIによる代替送達は導入しない)」という
  簡素な方針とした。設計に対応するコードも実装し、`prototype/cloud_function_webhook.py`に
  `LlmApiError`/`ReplyApiError`例外・`_generate_with_api_retry()`/`_reply_with_retry()`・
  `API_FAILURE_FALLBACK_MESSAGE`・`MemoProcessResult.api_failure`を追加、
  `prototype/test_cloud_function_webhook.py`に4パターン(LLM/Reply各々のリトライ成功・
  リトライ後も失敗)のテストを追加した(全25件パス、venture全体で82件パス)。
  Reply APIトークンの有効期限・失敗時消費有無の一次情報確認は未検証事項として残る
  (WebFetchのegress制約、実LINE接続後の課題)。
- フェーズ66(2026-08-17 10:00 UTC): フェーズ65の未検証事項だったReply APIトークンの
  有効期限について、WebSearchによる二次情報調査を行った。「Webhook受信から約1分以内・
  1回限りで、失効後または使用済み後は`Invalid reply token`エラーとなる」旨の複数の
  検証記事(Qiita等)を確認し、api-call-failure-handling.mdの「数十秒〜1分程度」という
  概数記載を「約1分以内(2019年頃は約30秒だったが延長された)」に更新した。この値は
  既存方針(即時1回のみリトライ)の妥当性を裏付ける材料になる。一方、失敗レスポンス時に
  トークン自体が消費済み扱いになるかは二次情報でも確認できず、LINE公式ドキュメントへの
  WebFetchは引き続きegress制約でブロックされることを再確認した(line-image-content-api-review.md
  と同様の制約)。実LINE接続後に一次情報での最終確認が必要な点は変わらない。
- フェーズ67(2026-08-17 14:00 UTC): aircon-pashaが2026-08-17 09:00 UTCに新規作成した
  llm-api-cost-estimate.mdと同種の試算が本ventureには未着手だった点に対応し、
  llm-api-cost-estimate.mdを新規作成した。llm-system-prompt-draft.md(18,036文字)・
  schema/output.schema.json(9,854文字)の現行ドラフト規模からトークン数を概算し、
  Claude Sonnet 5・シナリオB・プロンプトキャッシュ利用時で生成1回あたり約3.26円という
  試算結果を得た。pricing-plan.mdの従量単価(100〜150円/回)・基本料実質単価
  (約199〜248円/回)と比較していずれも1.3〜3.3%程度にとどまり、subscription-billing-
  cost-estimate.mdが結論づけた「決済手数料が粗利率を左右する優先コスト項目」という結論を
  補強する形で、LLM API原価も事業性を圧迫する主要因にはならないと確認した。正確な
  トークン数の実測(`count_tokens`)・プロンプトキャッシュの1時間TTL採用可否は、
  実LLM接続後の課題として残る(オーナー承認待ち)。
- フェーズ68(2026-08-17 20:00 UTC): これまでsubscription-billing-cost-estimate.md
  (決済手数料+Firestore原価)とllm-api-cost-estimate.md(LLM API原価)に分かれていた
  原価試算を統合し、unit-economics-estimate.mdを新規作成した。3プランとも「含まれる
  生成回数を使い切る」前提で月次粗利を試算した結果、キャッシュなしでも粗利率91.9〜92.8%、
  プロンプトキャッシュ(1時間TTL)導入時は94.8〜95.1%まで改善する見込みと確認し、
  line-reservation-aiと同様に決済手数料・LLM API原価いずれも単体では事業性を左右しない
  水準であることを合算ベースでも裏付けた。プラン間で粗利率にほぼ差がないことから、
  pricing-plan.mdの従量単価設計(上位プランほど単価を下げる)は粗利率を大きく損なわずに
  成立していることも確認できた。
- フェーズ69(2026-08-17 22:00 UTC): limit-approaching-notification-design.md「6. 今後の課題」
  に残っていた、「残り2回」通知閾値がプラン(ライト/スタンダード/セッター複数)間で固定で
  よいかをnotification-threshold-per-plan-review.mdで机上検討した。ライト・スタンダードは
  想定利用頻度から4〜7.5日の猶予があり妥当だが、セッター複数プランは複数セッターの一斉
  更新により猶予が数時間〜1日に圧縮されるリスクが構造的に高いと判明。実測データが取れる
  までは全プラン「残り2回」を維持しつつ、`usage_counter`実装時に「プラン→閾値」マッピング
  として外だし設計しておき、将来セッター複数プランのみ引き上げが必要と判明した場合も設定
  変更のみで対応できる方針とした。
- フェーズ70(2026-08-18 02:00 UTC): フェーズ69の暫定方針に沿って、月間生成回数カウント・
  上限接近通知(limit-approaching-notification-design.md 5節)を`prototype/cloud_function_webhook.py`
  に実装した。`UsageCounterProtocol`(`get_count`/`increment`)と検証用スタブ
  `InMemoryUsageCounter`、`PLAN_MONTHLY_LIMITS`/`PLAN_OVERAGE_UNIT_PRICE_JPY`/
  `PLAN_NOTICE_THRESHOLDS`という「プラン→値」マッピング3種、通知文言を組み立てる
  `build_usage_notice()`を新規追加し、`process_memo_event()`にキーワード専用引数
  `usage_counter`/`plan`/`month`を追加して統合した(status=="generated"時のみカウント、
  未接続時・userId不明時は従来通りスキップする後方互換設計)。境界値テスト10件を追加し
  既存分含め全95件パス。実Firestore接続は引き続きオーナー承認待ち(pending-approval.md参照)。
- フェーズ71(2026-08-18 05:00 UTC): line-reservation-aiには存在するがcourse-set-pashaには
  未着手だったデプロイ手順書(deployment-runbook.md)を新規作成した。GCPプロジェクト作成〜
  Firestore(usage_counter専用)有効化〜Cloud Functionsデプロイ〜LINE公式アカウント開設〜
  結合テストの手順を、line-reservation-aiのdeployment-runbook.mdを踏襲しつつ本venture固有の
  差分(会話状態を持たない単発リクエスト/レスポンス型のためCloud Tasksへの非同期化・複数
  Function分割が不要、Firestoreはusage_counter専用の最小構成のみでline-reservation-aiのような
  複合インデックスが不要)を反映して整理した。本ドキュメント作成自体は机上整理のみで、
  実際のGCPプロジェクト作成・課金は一切行っていない(引き続きオーナー承認待ち)。
- フェーズ72(2026-08-18 09:00 UTC): subscription-cancellation-flow-design.mdの
  「未検証の仮説・次の課題」に残っていた、schema/output.schema.json(フェーズ54)で
  定義済みだったstatus=cancellation_intent/downgrade_intent/cancellation_unclearが
  `prototype/cloud_function_webhook.py`側では未実装(`format_reply_text()`に分岐が無く
  ValueErrorになる)という実装ギャップに対応した。CI1・CI2のbody文言に含まれる
  `{Stripeカスタマーポータル URL}`プレースホルダを実URLへ置換する
  `PortalLinkProvider`Protocol・`InMemoryPortalLinkProvider`スタブ・
  `render_subscription_procedure_notice()`を新規実装し、`process_memo_event()`に
  キーワード専用引数`portal_link_provider`を追加して統合した(llm_call・reply_client・
  usage_counterと同じ「差し替え可能なスタブ」設計方針を踏襲)。provider未接続・
  provider がNoneを返す・userId不明のいずれの場合も、壊れたプレースホルダ文字列を
  そのまま顧客に見せないよう`PORTAL_LINK_UNAVAILABLE_FALLBACK`(問い合わせ導線への
  差し替え)を返す安全側フォールバックとした。あわせて、デモ関数`_demo()`の
  `StubLlmClient`が`subscription_procedure_notice`フィールド欠落によりスキーマ検証に
  常時失敗し、生成成功パターンのデモが実際には検証失敗フォールバック文言を表示していた
  既存の実装漏れも発見・修正した。テスト7件(SubscriptionProcedureNoticeTest)を追加し
  既存分含め全45件パス(schema/validate_test_cases.pyの9件も引き続き全件パス)。
  実際のStripe Billing Portal Session API呼び出しへの接続(providerの実装差し替え)は
  引き続きオーナー承認待ちの範囲として残る。
- フェーズ73(2026-08-18 13:00 UTC): first-generation-notice-implementation-design.md
  (フェーズ61〜63で設計のみ・実装は残課題としていた「そのユーザーにとって生涯で最初の
  生成成功時のみ1回だけ確認案内を付記する」機能)を、フェーズ72までと同じ「差し替え可能な
  スタブ」方針で`prototype/cloud_function_webhook.py`に実装した。`FirstGenerationNoticeStoreProtocol`
  (`has_sent`/`mark_sent`)・検証用スタブ`InMemoryFirstGenerationNoticeStore`・確認案内本文を
  組み立てる`append_first_generation_notice()`を新規追加し、`process_memo_event()`に
  キーワード専用引数`first_generation_notice_store`/`gym_area_configured`(既定値True)を
  追加して統合した。判定は既存の`usage_counter.get_count()`(月間カウント)がincrement前に
  0かどうかで行い、`first_generation_notice_store`側の送信済みフラグと組み合わせて二重送信を
  防ぐ設計とした(design 2節の疑似コード準拠)。ただし設計3節が求める「count増分と
  notice_sent更新の単一書き込みでの原子性」は、本スタブ実装ではcount取得(判定用)→
  確認案内追記→フラグ更新→(plan指定時のみ)count増分、という複数ステップのままであり、
  実Firestore接続時に単一ドキュメント更新へまとめる作業は引き続き未着手として残る
  (現状はいずれもインメモリスタブのため実運用上の不整合リスクはない)。テスト8件
  (AppendFirstGenerationNoticeTest 2件・ProcessMemoEventFirstGenerationNoticeTest 6件)を
  追加し既存分含め全53件パス(schema/validate_test_cases.pyの9件も引き続き全件パス)。
  `gym_area_configured`は本来ユーザーごとの申込内容(ジム名・地域名設定有無)から
  決まる値だが、その永続化・参照経路(user設定ストア)自体は未設計のため、当面は
  呼び出し側が明示的に渡す前提の引数として残した(実Firestore接続後の課題)。
- フェーズ74(2026-08-18 16:00 UTC): フェーズ73の残課題だった`gym_area_configured`の
  実データ参照経路を、first-generation-notice-implementation-design.md 5節として設計した。
  申込フォーム提出時に書き込まれる`user_profile/{user_id}.gym_area_pairs`(usage_counterとは
  別ドキュメント、書き込み側は申込フォーム提出フロー自体で本venture対象外)の読み取り専用
  Protocol`GymAreaConfigStoreProtocol.is_configured(user_id)`として抽象化し、
  `prototype/cloud_function_webhook.py`に`InMemoryGymAreaConfigStore`(検証用スタブ)を実装した。
  `process_memo_event()`の引数を`gym_area_configured: bool = True`から
  `gym_area_config_store: Optional[GymAreaConfigStoreProtocol] = None`へ差し替え、
  未接続時(None)は従来通り「設定済み」を既定値として扱う安全側の挙動を維持した。
  テスト5件(InMemoryGymAreaConfigStoreTest 3件・ProcessMemoEventFirstGenerationNoticeTest
  2件)を追加し既存分含め全58件パス(schema/validate_test_cases.pyの9件も引き続き全件パス)。
  実際の申込フォーム提出フロー・実Firestore接続への配線自体は引き続きオーナー承認待ち。
- フェーズ75(2026-08-18 19:00 UTC): フェーズ74で残っていた、count増分と
  `first_generation_notice_sent`更新の単一書き込みでの原子性
  (first-generation-notice-implementation-design.md 3節)を実装した。`InMemoryUsageCounter`に
  `has_sent()`/`mark_sent()`(`FirstGenerationNoticeStoreProtocol`互換)と
  `increment_and_mark_notice(user_id, month, mark_notice_sent)`を新規追加し、
  `process_memo_event()`は`usage_counter`と`first_generation_notice_store`に**同一インスタンス**
  (実Firestoreの単一ドキュメントに相当)が渡された場合のみこの原子的経路を使うよう変更した
  (異なる2つのストアを渡す既存の呼び出し方は従来通り2ステップのまま、後方互換を維持)。
  `increment()`/`mark_sent()`が単体(原子的経路を介さず)で呼ばれたら失敗するスパイ
  (`_AtomicOnlyUsageCounter`)を新設し、原子的経路が実際に使われていることをテストで実証した。
  テスト10件新規追加(InMemoryUsageCounterAtomicNoticeTest 3件・
  ProcessMemoEventAtomicNoticeWriteTest 3件、既存分の一部見直し含め)、既存分含め全64件パス
  (schema/validate_test_cases.pyの9件・post_generation_checks/history_export関連も含め全121件パス)。
  実Firestoreでの単一ドキュメント`update()`呼び出しへの最終反映自体は、実Firestore接続
  (オーナー承認待ち)後の課題として引き続き残る。`user_profile/{user_id}.gym_area_pairs`を
  書き込む側(申込フォーム提出フロー自体の実装)も引き続き別課題として残る。
- フェーズ76(2026-08-18 20:00 UTC): フェーズ75で残っていた、`user_profile/{user_id}.gym_area_pairs`
  の書き込み側(申込フォーム提出フロー自体)を`application-form-submission-flow-design.md`として
  設計した。フォームツールはGoogleフォーム+Google Apps Script(GAS)Webhookを第一候補とし
  (無料・追加の有料SaaS契約不要、LP実装着手時にLP自前フォームへの切替を再検討する二段階移行)、
  GAS Webhookペイロードの想定形・正規化ルール(前後空白除去、カンマ区切り各要素の空白除去、
  `,,,`等の実質空入力を空文字列へ落とし込む安全側処理)・書き込み先(`user_profile`ドキュメントの
  `gym_area_pairs`フィールドへの全体上書き、追記ではない)を整理した。`prototype/`に新規モジュール
  `application_form_submission_flow.py`(`UserProfileStoreProtocol`・`InMemoryUserProfileStore`・
  `normalize_gym_area_pairs_raw()`・`handle_form_submission()`)を実装し、既存の
  `GymAreaConfigStoreProtocol`(cloud_function_webhook.py、読み取り専用)への依存を増やさず
  独立したモジュールとした。`InMemoryUserProfileStore`は`is_configured()`も同時に提供し、
  実Firestore接続後は単一の`FirestoreUserProfileStore`が両Protocolを満たす設計を見越した
  作りとした。テスト16件新規追加(`test_application_form_submission_flow.py`)、既存分含め
  prototype配下で全137件パス(schema/validate_test_cases.pyの9件も引き続き全件パス)。
  Googleフォーム自体の作成・GAS配置の実設定はオーナー承認待ちとして残る。
- フェーズ77(2026-08-20 21:00 UTC): フェーズ76で残っていた、LINE友だち追加時のuser_id
  事前紐付け経路を`line-user-id-linking-design.md`として設計した。検討の過程で、フェーズ76が
  暫定採用していた「フォームへのuser_id手入力」は誤入力リスク以前の問題として、一般の
  LINEユーザーがアプリUI上から自分のuser_idを確認する手段を持たず運用として成立しない
  ことが判明した。friend追加(`follow`イベント)時に短い連携コード(6文字・紛らわしい文字を
  除いた英数字・有効期限24時間・使い切り)を発行し、申込フォーム側の入力項目を
  「user_id」から「連携コード」に変更する方式へ切り替えた。`prototype/user_id_linking.py`に
  `issue_linking_code_on_follow()`・`resolve_linking_code()`・
  `handle_form_submission_with_linking_code()`を実装(既存の`handle_form_submission()`
  〈user_id版〉へ委譲する薄いオーケストレーターとし、フェーズ76のモジュールへの変更は
  行わなかった)。テスト11件新規追加、既存分含め全148件パス。実際の`follow`イベント受信・
  ウェルカムメッセージ送信・Googleフォーム項目名変更はいずれも実LINE API接続/フォーム実設定
  自体がオーナー承認待ちのため未着手として残る。
- フェーズ78(2026-08-20 22:00 UTC): フェーズ77の`line-user-id-linking-design.md`残課題で
  「実Firestore接続後の課題」として先送りしていた`pending_links`期限切れドキュメントの定期
  パージについて、掃除ロジック自体を`prototype/user_id_linking.py`に`purge_expired_links()`
  として実装した(有効期限24時間超のエントリを削除し削除件数を返す)。あわせて
  `LinkingCodeStoreProtocol`/`InMemoryLinkingCodeStore`に列挙用の`items()`を追加。Firestore
  ネイティブTTLは削除が最大24〜72時間遅延しうるため、スケジューラ発火型Cloud Functionや
  followイベント便乗でこの関数を明示的に呼ぶ経路も持てる設計とした(line-reservation-aiの
  `release_idle_conversations()`と同じ「実スケジューラ確定前に掃除ロジックだけ検証しておく」
  位置づけ)。`resolve_linking_code()`側の遅延削除と冪等に共存することも含めテスト4件新規追加、
  全152件パス。実Firestore接続・TTLポリシー設定自体はオーナー承認待ちのまま。
- フェーズ79(2026-08-20 23:00 UTC): フェーズ78で未確定だった`purge_expired_links()`の
  実行トリガー(スケジューラ発火型かfollowイベント便乗か)を`linking-code-purge-trigger-design.md`
  として検討した。実GCPスケジューラ設定・follow イベントハンドラ自体はいずれも実LINE API/GCP接続が
  前提でオーナー承認待ちのため今すぐ設定できない一方、本ventureの主要トラフィックである
  `process_memo_event()`(生成依頼Webhook)への便乗であれば既存エントリポイントに引数を足すだけで
  今すぐ実装できると判断し、line-reservation-aiの`maybe_run_idle_cleanup()`と同じ「前回実行から
  一定時間未満はスキップ」方式を採用した。状態を持たない関数群である`user_id_linking.py`に
  間引き状態を保持する小さなクラス`LinkingCodePurgeThrottle`(MIN_INTERVAL=1時間)を新設し、
  `cloud_function_webhook.py`の`process_memo_event()`に`linking_store`・`purge_throttle`・`now`の
  3つをオプション引数として追加、いずれかがNoneの場合(未接続時・既存呼び出し元)は従来通り
  スキップする後方互換設計とした。テスト8件新規追加(LinkingCodePurgeThrottle単体4件・
  process_memo_event配線4件)、course-set-pasha配下計160件パス。実Firestore接続・実follow
  イベントハンドラの実装自体はオーナー承認待ちのまま残る。
- フェーズ80(2026-08-21 01:00 UTC): フェーズ79で残っていた「実follow イベントハンドラの実装」
  のうち、実LINE API接続に依存しない処理ロジック自体(コード発行〜ウェルカムメッセージ組み立て〜
  返信)を`follow-event-welcome-message-design.md`として設計し、`cloud_function_webhook.py`に
  `process_follow_event()`・`format_welcome_message()`・`ApplicationFormLinkProvider`
  (Protocol、`PortalLinkProvider`と同型)として実装した。ウェルカムメッセージは(1)サービス概要、
  (2)連携コード、(3)申込フォームへの入力依頼、(4)有効期限、の4点を伝える固定テンプレートとし、
  実フォームURL確定までは`PORTAL_LINK_PLACEHOLDER`と同じ考え方のプレースホルダ
  (`APPLICATION_FORM_URL_PLACEHOLDER`)で埋める設計とした。linking-code-purge-trigger-design.mdの
  未解決事項だった「案B(followイベント便乗パージ)を実装時に追加するか」は、引数
  (`purge_throttle`)自体は`process_memo_event()`と同型で用意しつつ、MVP初期の呼び出し元では
  渡さず案Cのみ稼働を維持する(将来コード変更なしで有効化できる)形で解消した。テスト7件新規追加
  (正常系・プレースホルダ/実URL切替・非followイベント無視・userId欠落時・返信失敗時のコード
  保持・案B配線)、course-set-pasha配下計167件パス。実LINE API接続・Webhook本体でのイベント種別
  ディスパッチ(現状`event["type"]`によるfollow/message振り分け処理自体が未実装)は
  オーナー承認待ち・別途設計課題として残る。
- フェーズ81(2026-08-21 03:00 UTC): フェーズ80の残課題だった「Webhook本体でのfollow/message
  イベント種別ディスパッチの実装」を`webhook-event-dispatch-design.md`として設計し、
  `cloud_function_webhook.py`に`dispatch_webhook_events()`・`DispatchResult`(dataclass)として
  実装した。`events`配列を`event["type"]`で仕分け、followイベントは`process_follow_event()`へ
  そのまま、messageイベントは`merge_text_and_photo_events()`で束ねてから`process_memo_event()`へ
  渡す(followイベントが束ね処理に混入しないよう事前に絞り込む設計)。未対応種別
  (`unfollow`等)は`ignored_types`に記録するのみに留め、`reply_client`・`linking_store`・
  `llm_call`が未接続の場合は該当種別を処理せず素通りする安全側の挙動とした。テスト5件新規追加
  (follow/message混在時の振り分け、text-image束ねへのfollow混入なし確認、未対応種別の記録、
  未接続時の素通り2パターン)、course-set-pasha配下計172件パス。実HTTPリクエストボディの
  JSONパース〜`verify_line_signature()`との結線・実Cloud Functionsデプロイはいずれも実LINE API
  接続自体がオーナー承認待ちのため未着手のまま残る。
- フェーズ82(2026-08-21 06:00 UTC): フェーズ81の残課題だった「実HTTPリクエストボディの
  JSONパース〜`verify_line_signature()`との結線」を`receive-webhook-http-entry-point-design.md`
  として設計し、`cloud_function_webhook.py`に`receive_webhook()`・`WebhookReceiverResult`
  (dataclass)として実装した。生のリクエストボディ(bytes)を受け取り、署名検証失敗時は
  `dispatch_webhook_events()`を呼ばず401を返す、署名検証通過後に`json.loads()`でパースし
  失敗時は400(`invalid_json`)、`events`キーが配列でない場合も400(`missing_events`)を返す、
  検証・パースに成功した場合のみ`dispatch_webhook_events()`に委譲し200を返す、という
  line-reservation-aiの`webhook_receiver()`と同型の設計とした(違いはJSONパース自体を
  この関数内で行う点)。テスト4件新規追加(署名不正時401・dispatch不実行、不正JSON時400、
  events欠落時400、正常系での200・dispatch結果反映)、course-set-pasha配下計176件パス。
  実`functions_framework`のリクエストオブジェクトからのbody/署名ヘッダ取り出し配線・
  実Cloud Functionsデプロイ自体はオーナー承認待ちのため未着手のまま残る。
- フェーズ83(2026-08-21 09:00 UTC): フェーズ82の残課題だった、実`functions_framework`の
  リクエストオブジェクトからの`body`/署名ヘッダ取り出し配線を`main(request)`として実装した
  (receive-webhook-http-entry-point-design.md「残課題」追記)。`functions_framework`自体は
  インポートせず`request.get_data()`・`request.headers.get(...)`という同じインターフェースにのみ
  依存する設計としたため、実パッケージのインストール・実デプロイなしにローカルで単体テスト可能に
  した(テストは`_StubFlaskRequest`という軽量スタブで代替)。`channel_secret`は環境変数
  `LINE_CHANNEL_SECRET`から取得する設計とした。実LINE/実LLM/実Firestoreクライアントの組み立ては
  `get_runtime_dependencies()`という差し替え可能なファクトリ関数に切り出し、現時点
  (オーナー承認待ち)では空辞書(全依存未接続)を返す実装とした。`dispatch_webhook_events()`側の
  既存の「`reply_client`/`llm_call`が`None`ならイベント処理をスキップする」安全側フォールバックに
  より、未接続のまま呼び出しても例外にはならないことを確認済み。テスト5件新規追加
  (正常系でのbody/署名抽出・200返却、署名不正・ヘッダ欠落・環境変数未設定時の401、
  `get_runtime_dependencies()`の戻り値が`receive_webhook()`にそのまま渡せること)、
  course-set-pasha配下計190件パス。実Cloud Functionsデプロイ自体・`channel_secret`の実際の
  取得/保管方法(Secret Manager等)・`get_runtime_dependencies()`の実クライアントへの差し替えは、
  実GCPプロジェクト作成・実LINE公式アカウント接続を伴うためオーナー承認待ちのまま残る。
- フェーズ84(2026-08-21 15:00 UTC): webhook-event-dispatch-design.md(フェーズ81)の残課題
  だった「`unfollow`イベント受信時の扱い(連携コード・利用状況データの扱いをどうするか)」を
  unfollow-event-handling-design.mdとして決定した。要旨: (1)LINEのブロックとStripe
  サブスクリプション課金は別レイヤーの事象であり、本サービスがunfollowを検知して自動解約
  することはしない(ユーザー本人の明示的操作を要する事項のため)、(2)該当user_id宛の
  未使用連携コード(`pending_links`)は有効期限を待たず即時削除する(実害はないが不要と
  確定した時点で片付ける)、(3)`user_profile`・`usage_counter`・履歴データは一切削除・
  変更しない(再フォロー時に設定し直す手間を省く)。実装として`user_id_linking.py`に
  `delete_pending_links_for_user()`、`cloud_function_webhook.py`に`process_unfollow_event()`・
  `UnfollowProcessResult`を新設し、`dispatch_webhook_events()`の`unfollow`を`ignored_types`
  行きから専用の`unfollow_results`への振り分けに変更した(`postback`・`join`等の真に未対応な
  種別のみ引き続き`ignored_types`に記録)。テスト9件追加(`delete_pending_links_for_user()`3件、
  `process_unfollow_event()`5件、`dispatch_webhook_events()`のunfollow振り分け1件。既存の
  「未対応種別は無視される」テストは例示イベントを`unfollow`から`postback`へ差し替え)、
  course-set-pasha配下計190件パス。「ブロックしたのに課金だけ続く」状態への運用対応
  (オーナー向けFAQ整備等)、`user_profile`等の長期保存期間の上限整理(line-reservation-aiの
  data-retention-policy.mdに相当する文書が本ventureにまだ無い)は次の課題として残る。
- フェーズ85(2026-08-21 16:00 UTC): フェーズ84の残課題だった「`user_profile`・
  `usage_counter`等の長期保存期間の上限整理」をdata-retention-policy.mdとして新規作成した。
  line-reservation-ai/data-retention-policy.mdの構成を踏襲しつつ、本ventureが会話状態・
  履歴を永続化しない単方向バッチ処理である点(tech-stack.md)を踏まえ、対象を`user_profile`・
  `usage_counter`の2コレクションに絞って整理(`pending_links`は既存方針で確定済みのため
  対象外)。Stripeサブスクリプションの解約日を起点に1年保有後を削除候補とする方針、
  削除候補化後の最終確認経路(LINE push主経路・unfollow中は送達不可なため代替経路が必要な
  点)、`user_profile`/`usage_counter`はいずれもトップレベル単独ドキュメントで削除順序の
  論点が生じない点を整理した。残るのは、legal-notices-draft.mdへの反映、Stripe解約webhookを
  起点とする削除候補洗い出しの具体的トリガー設計(実Stripe接続後)、代替連絡経路の実際の
  収集項目確定(application-form-submission-flow-design.md実装確定後)、および
  unfollow-event-handling-design.md由来の「ブロックしたのに課金だけ続く」FAQ整備
  (本文書のスコープ外)で、いずれも次の課題として残る。
- フェーズ86(2026-08-21 18:00 UTC): フェーズ84・85で2回連続スコープ外として持ち越されていた
  「ブロックしたのに課金だけ続く」状態へのオーナー向けFAQ・問い合わせ対応文言整備を
  unfollow-billing-faq.mdとして新規作成した。ブロック中はLINE経由の能動的な案内が
  送達不可(unfollow-event-handling-design.md)であるため、(1)LP掲載用のFAQ文面
  (ブロックのみでは解約にならない旨の事前周知)、(2)ユーザーがメール等の別経路から
  問い合わせてきた場合にオーナー本人がそのまま使える返信テンプレート(subscription-
  cancellation-flow-design.mdの解約案内メッセージの要旨をメール向けに書き換えたもの)の
  2本立てで整理した。(1)は実際にlanding-page-copy-draft.mdのFAQセクションに4問目として
  反映した。残るのは、本サービス側から能動的に「ブロック中かつ契約継続中」のユーザーを
  検知して案内するプロアクティブな通知バッチの要否・設計(実LINE・実Stripe接続後の課題)、
  問い合わせ対応テンプレートの宛先メールアドレス確定(legal-notices-draft.mdの【要記入】
  項目確定後の課題)で、いずれも次の課題として残る。本フェーズはドキュメント作成のみで
  コード変更を伴わないため、既存テストへの影響なし(course-set-pasha配下既存190件は
  フェーズ83時点の確認から変更なしのはずだが、念のため再実行し確認する)。
- フェーズ87(2026-08-21 21:00 UTC): aircon-pasha README.mdフェーズ98の申し送り
  「実LLM接続後の生成品質検証プランをcourse-set-pasha・line-reservation-aiにも同様の形で
  展開する」に対応し、llm-quality-verification-plan.mdを新規作成した。output-samples-
  validation.mdの5ケース(G1〜G3・OOS1・II1)とschema/validate_test_cases.pyの解約意図
  検知ケース(CI1〜CI3)を対象に、厳守事項1〜9・7a別の検証観点・判定方法(機械チェック/
  人手)を整理した。aircon-pashaとの差分として、(1)course-set-pashaにはunchanged_areas
  本文突き合わせ・出力別絵文字上限チェックに相当する機械チェックスクリプト
  (post_generation_checks.py相当)がまだ存在しない点、(2)出力1のみ絵文字1〜2個を許容する
  点がaircon-pasha(全出力絵文字不使用)と異なる点、(3)厳守事項7a(解約意図検知)は
  course-set-pasha固有でCI1〜CI3が新規検証項目である点、を明記した。ドキュメント整理のみで
  APIキー取得・課金を伴わないため承認不要な範囲にとどめ、実際のLLM API呼び出しは引き続き
  オーナー承認待ち。次回はpost_generation_checks.py相当のunchanged_areas突き合わせ・
  絵文字上限チェックスクリプトの移植、または同プランのline-reservation-aiへの展開を検討する。
- フェーズ88(2026-08-21 22:00 UTC): フェーズ87の「次回」候補だった移植作業に着手する前に
  prototype/post_generation_checks.pyの現状を確認したところ、フェーズ87で「まだ存在しない」
  「移植が必要」としていたunchanged_areas本文突き合わせ(`check_unchanged_areas_not_mentioned_
  as_new()`)・出力別絵文字上限チェック(`check_emoji_usage_rules()`)は、実際には2026-08-09
  時点で既に実装・テスト済み(test_post_generation_checks.pyに対応するテストあり)であることが
  判明した。この誤りはフェーズ87作成時にoutput-samples-validation.mdの記述のみを参照し、
  prototype/配下の実装状況を直接確認しなかったことに起因すると考えられる。llm-quality-
  verification-plan.mdの該当箇所(検証観点表の#2・#9、「aircon-pashaとの差分」節、
  「残る未確定事項」節)を実装済みである旨に訂正し、移植不要であることを明記した。
  念のためprototype配下の全テスト(190件)を再実行しパスを確認した(コード変更は伴わないため
  想定通り)。次回はフェーズ87のもう一方の申し送りだった同プランのline-reservation-aiへの
  展開に着手する(その際は今回の教訓を踏まえ、着手前に必ずline-reservation-ai/prototype配下の
  既存実装を確認してから「未実装」判定を行う)。
- フェーズ89(2026-08-22 03:00 UTC): 「次にやること」に残っていたdata-retention-policy.md
  (フェーズ85)の「今後の課題」1点目、legal-notices-draft.mdへの保存期間・削除方針の反映を
  行った。legal-notices-draft.md 2.4節(保存期間・削除)を、data-retention-policy.mdが定めた
  内容(永続保存対象は`user_profile`・`usage_counter`の2種類のみ、Stripe解約日起点で1年保有後に
  削除候補化、削除候補化後はLINE push/申込フォーム収集の連絡先で最終確認、連絡不能時は
  オーナーが個別判断)で具体化した。ドキュメント整理のみでコード変更・外部接続を伴わないため
  承認不要な範囲にとどめた。次回はStripe解約イベント(webhook)起点の削除候補洗い出し
  トリガー設計(実Stripe接続後の課題として残置)以外の未着手領域、または本プランの
  line-reservation-aiへの展開状況の確認を優先する。
- フェーズ90(2026-08-22 06:00 UTC): フェーズ89の「次回」候補のうち、まず
  line-reservation-aiへの本プラン(llm-quality-verification-plan.md)展開状況を確認した。
  line-reservation-ai/llm-quality-verification-plan.md(2026-08-22 00:00 UTC作成済み)が
  既に存在し、会話エンジン型という特性差(自由文の下書き生成ではなく毎ターンの構造化出力
  分類)を踏まえた形で展開済みであることを確認した(追加対応不要)。あわせてoutput-samples-
  validation.mdを見直したところ、作成時(フェーズ7、2026-08-07)のG1〜G3・OOS1・II1の5件
  記載のまま、その後追加されたG4(複数エリア同時更新、フェーズ11)・CI1〜CI3(厳守事項7a、
  フェーズ54)が反映されていないドキュメント齟齬を発見した(llm-quality-verification-plan.md
  「残る未確定事項」でも指摘されていた点)。schema/validate_test_cases.pyを実行し全9件パスを
  再確認した上で、output-samples-validation.mdのサンプルケース一覧・結果を9件分に更新し、
  llm-quality-verification-plan.mdの該当箇所も解消済みとして訂正した。コード変更・外部接続は
  伴わずドキュメント整合性の修正のみのため承認不要な範囲。次回はStripe解約イベント起点の
  削除候補洗い出しトリガー設計(実Stripe接続後の課題として引き続き残置)以外の未着手領域を
  優先する。
- フェーズ91(2026-08-22 11:00 UTC): data-retention-policy.md(フェーズ85)の残課題だった
  Stripe解約webhook起点の削除候補洗い出しトリガー設計を
  stripe-cancellation-deletion-candidate-trigger-design.mdで行った。`customer.subscription.deleted`
  受信時に`user_profile/{user_id}`へ`deletion_candidate_at`(解約日+365日)を書き込む
  `mark_deletion_candidate_on_subscription_deleted()`、再契約時に取り消す
  `clear_deletion_candidate_on_subscription_reactivated()`、月次バッチから呼ぶ読み出し専用の
  `list_deletion_candidates()`の3関数を設計した。data-retention-policy.md時点では未整理
  だった「解約後1年以内に再契約した場合に削除候補フラグを取り消す」経路を新たに整理できた
  点が今回の主な進展。実際のStripe Webhook受信エンドポイント(署名検証・エンドポイント設計)
  自体はcourse-set-pashaにまだ存在せず、これは実Stripeアカウント接続後の課題として残置。
  設計のみでコード実装・外部接続は伴わないため承認不要な範囲にとどめた。
- フェーズ92(2026-08-22 14:00 UTC): フェーズ91・stripe-cancellation-deletion-candidate-
  trigger-design.mdで設計のみだった3関数(`mark_deletion_candidate_on_subscription_deleted()`・
  `clear_deletion_candidate_on_subscription_reactivated()`・`list_deletion_candidates()`)を
  `prototype/deletion_candidate.py`として実装した。`user_id_linking.py`の
  `LinkingCodeStoreProtocol`/`InMemoryLinkingCodeStore`と同じ「Protocol + インメモリ
  スタブ」構成で`ProfileDeletionCandidateStoreProtocol`/
  `InMemoryProfileDeletionCandidateStore`を用意し、実Firestore接続なしで机上検証できる
  形にした。テストは(1)解約日+365日の書き込み、(2)2回目解約時の最新解約日での上書き、
  (3)再契約時の取り消しと冪等性(初回契約時の`created`イベントでも実害がないこと)、
  (4)`list_deletion_candidates()`の境界値(ちょうどnow時点は含む/未来は除外)・複数
  user_id時のuser_id昇順ソート、をカバーした(テスト12件追加、course-set-pasha配下
  計202件パス)。design 4節で明示されていたとおり、実際のStripe Webhook受信エンドポイント
  (署名検証・イベント種別ディスパッチ、`receive-webhook-http-entry-point-design.md`の
  LINE版に相当するもの)はまだ存在せず、次の課題として引き続き残る。
- フェーズ93(2026-08-22 17:00 UTC): フェーズ92「次にやること」候補だった実Stripe
  Webhook受信エンドポイントのうち、実Stripeアカウント接続なしでも先行実装できる
  署名検証部分を`stripe-webhook-signature-verification-design.md`で設計し、
  `prototype/stripe_webhook.py`に`verify_stripe_signature()`として実装した。
  `Stripe-Signature`ヘッダ(`t=<timestamp>,v1=<sig>[,v1=<sig>...],v0=...`)を解析し、
  HMAC-SHA256で計算した期待署名といずれかの`v1`が一致するか(シークレットローテーション
  中の複数`v1`にも対応)、かつタイムスタンプが許容範囲(デフォルト300秒、公式ライブラリの
  既定値を踏襲)内かの両方を確認する。LINE版`verify_line_signature()`との違いとして、
  Stripe側はヘッダにタイムスタンプが埋め込まれておりリプレイ対策の許容範囲チェックが
  必要になる点、シークレットローテーション中は複数`v1`のいずれか一致で検証成功とする点、
  廃止済みの`v0`方式は一切参照しない点を整理した。`cloud_function_webhook.py`(LINE側)
  とは独立した新規ファイルとし、既存コードへの影響はゼロ。テストは
  `prototype/test_stripe_webhook.py`に8件新設(正常系、ヘッダ欠落・不正形式、署名不一致、
  タイムスタンプ許容範囲外(過去・未来)、シークレットローテーション時の後方一致、
  `v0`のみ存在時の拒否をカバー、course-set-pasha配下計210件パス)。設計時にあわせて、
  `follow-event-welcome-message-design.md`と`linking-code-purge-trigger-design.md`の
  残課題に記載が古いまま残っていた「followイベントのディスパッチ振り分け先が未実装」
  という記述が、フェーズ81〜83で既に`dispatch_webhook_events()`→`process_follow_event()`→
  `issue_linking_code_on_follow()`という経路として実装済みであることを確認し、両ファイルの
  記載を解消済みとして訂正した(コード変更なし、ドキュメント整合性の修正のみ)。
- フェーズ94(2026-08-22 20:00 UTC): フェーズ93「次にやること」候補だった実Stripe
  Webhook受信エンドポイントのうち、イベント種別(`customer.subscription.deleted`等)
  ディスパッチ〜`prototype/deletion_candidate.py`の3関数呼び出しを結ぶ部分を
  `stripe-webhook-event-dispatch-design.md`で設計し、`prototype/stripe_webhook.py`に
  `dispatch_stripe_event()`として実装した。Stripeの`customer`(カスタマーID)から内部
  `user_id`への解決は`resolve_user_id`という注入可能な関数として切り出し、実際の
  対応付けストア(未設計、実Stripe接続後の課題)を待たずに振り分けロジック自体を
  検証可能にした。`customer.subscription.deleted`→削除候補化、
  `customer.subscription.created`→常に取り消し(冪等)、`customer.subscription.updated`→
  status が`active`/`trialing`の時のみ取り消し、それ以外のイベント種別は無視、
  という分岐をカバーした。テストは`test_stripe_webhook.py`に`DispatchStripeEventTest`として
  9件追加(正常系3種・不正`created`・未解決customer・対象外status・未対応type、
  course-set-pasha配下計219件パス)。実際のHTTPエントリポイント
  (`verify_stripe_signature()`との結線)・`resolve_user_id`の実装・実Stripe接続は
  次の課題として残る。
- フェーズ95(2026-08-22 23:00 UTC): フェーズ94「次にやること」候補(1)だった、
  `verify_stripe_signature()`と`dispatch_stripe_event()`を結ぶHTTPエントリポイント本体を
  `stripe-webhook-http-entry-point-design.md`で設計し、`prototype/stripe_webhook.py`に
  `receive_stripe_webhook()`として実装した(LINE版`cloud_function_webhook.py`の
  `receive_webhook()`と対称の位置づけ)。署名検証失敗時は401(JSONパース・dispatch自体を
  呼ばない)、JSONパース失敗時は400(`error="invalid_json"`)、パース結果がdict以外の
  場合も400(`error="invalid_event"`)、それ以外は`dispatch_stripe_event()`に委譲し200を
  返す(`resolve_user_id`未解決・対象外イベント種別でもStripe再送ループを避けるため200)。
  テストは`test_stripe_webhook.py`に`ReceiveStripeWebhookTest`として5件追加(署名不正・
  JSON不正・非dictイベント・正常系での削除候補化・customer未解決時も200、course-set-pasha
  配下計224件パス)。実際の`main(request)`相当の配線(`functions_framework`リクエストからの
  `body`・`Stripe-Signature`ヘッダ取り出し)・`resolve_user_id`の実装・`webhook_secret`の
  実際の取得/保管方法は次の課題として残る。
- フェーズ96(2026-08-23 01:00 UTC): フェーズ95「残課題」(1)だった、
  `receive_stripe_webhook()`を実Cloud Functionsのリクエストオブジェクトに接続する
  `main(request)`本体を`stripe-webhook-cloud-function-entry-point-design.md`で設計し、
  `prototype/stripe_webhook.py`に実装した(LINE版`cloud_function_webhook.main()`と
  対称の構成)。`webhook_secret`は環境変数`STRIPE_WEBHOOK_SECRET`から取得。
  `get_stripe_runtime_dependencies()`を新設し、`store`は
  `InMemoryProfileDeletionCandidateStore()`、`resolve_user_id`は
  常に`None`を返す暫定実装とした。テストは`test_stripe_webhook.py`に
  `MainEntryPointTest`として5件追加(正常系・署名不正・ヘッダ欠落・環境変数未設定・
  `get_stripe_runtime_dependencies()`との結線、course-set-pasha配下計229件パス)。
  `resolve_user_id`の実装本体・`store`のFirestore化・`webhook_secret`の実際の
  保管方法は次の課題として残る。
- フェーズ97(2026-08-23 02:00 UTC): フェーズ96「残課題」(1)だった、
  `resolve_user_id`(`stripe_customer_id → user_id`変換)の実装本体を
  `stripe-customer-id-linking-design.md`で設計した。Stripe Checkout Session作成時に
  `client_reference_id`へ内部`user_id`を埋め込む前提で、`checkout.session.completed`
  イベントの`client_reference_id`・`customer`を`user_profile`ストアへ書き込む
  `handle_checkout_session_completed()`を`prototype/stripe_webhook.py`に新設し、
  `receive_stripe_webhook()`にこのイベント種別を`dispatch_stripe_event()`とは別経路で
  振り分ける分岐を追加した(`user_profile_store`引数を新設、未指定時は何もせず200)。
  `application_form_submission_flow.UserProfileStoreProtocol`/
  `InMemoryUserProfileStore`に`set_stripe_customer_id`/
  `get_user_id_by_stripe_customer_id`(逆引き)を追加し、この逆引きをそのまま返す
  `make_resolve_user_id()`ファクトリを新設。`get_stripe_runtime_dependencies()`は
  `InMemoryUserProfileStore()`を1つ生成して`resolve_user_id`・`user_profile_store`
  両方に共有させる構成に更新した。テストは`test_stripe_webhook.py`・
  `test_application_form_submission_flow.py`に計11件追加
  (`checkout.session.completed`の正常系・欠落系、`make_resolve_user_id()`、
  checkout完了後の`customer.subscription.*`解決を通しで確認するテストを含む、
  course-set-pasha配下計240件パス)。Stripe Checkout Session作成時に
  `client_reference_id`を設定する決済導線自体(申込フォーム提出後、どのUIから
  Checkoutを開始するか)は未設計のまま次の課題として残る。
- フェーズ98(2026-08-23 08:00 UTC): フェーズ97の残課題だった、Stripe Checkout Session
  作成時に`client_reference_id`へ内部`user_id`を設定する決済導線を設計した
  (`checkout-initiation-flow-design.md`)。トリガーはpricing-plan.mdの無料トライアル条件
  (カード登録不要・自動課金なし)に基づき「本人が有料プランへ進むボタンを押した時」のみとし、
  なりすまし決済導線を避けるためLINE LIFF経由でLINEのuserIdを取得する方式を採用した(LIFF
  アプリ自体の実登録はオーナー承認待ちとして扱う)。パラメータ組み立て部分を
  `build_checkout_session_params()`(`prototype/checkout_session.py`)として実装し、既存
  `stripe_customer_id`の再利用判定に使う`get_stripe_customer_id()`(順引き)を
  `application_form_submission_flow.py`に追加した。テスト5件新規追加(course-set-pasha配下
  計245件パス)。IDトークン検証・実Stripe API呼び出し・トライアル終了通知メッセージ自体は
  未着手のまま次の課題として残る。
- フェーズ99(2026-08-23 09:00 UTC): フェーズ98の残課題だった、トライアル終了通知メッセージ
  自体を設計した(`trial-end-notification-design.md`新規作成)。pricing-plan.mdの
  トライアル条件(14日間 or 生成5回到達のいずれか早い方)を踏まえ、(A)生成完了時の
  回数到達検知(便乗方式、aircon-pasha/course-set-pashaのlimit-approaching-notification-design.md
  と同じ手法)と(B)日次スケジューラによる期間到達検知の2経路のうちいずれか早い方で1回のみ
  送信する設計とし、通知メッセージ文言案(実績報告+checkout-initiation-flow-design.mdの
  LIFF決済導線へのCTA、自動課金なしの旨を明記)を作成した。「浮いた作業時間の目安」の
  試算値自体が未作成、トライアル開始起点(follow時 or 初回生成時)の確定、期間到達判定用の
  スケジューラ実装・生成一時停止判定の実装はいずれも次回以降の課題として残る。LIFFアプリの
  実登録・Cloud Scheduler実行環境の構築はオーナー承認待ちのため本フェーズでは机上設計のみ。
- フェーズ100(2026-08-23 11:00 UTC): フェーズ99の残課題だった、トライアル開始起点
  (初回follow時 or 初回生成時)を確定した(`trial-start-anchor-decision.md`新規作成)。
  follow時点ではまだ連携コード発行のみでサービス利用不可(申込フォーム提出・連携完了まで
  利用不能)なため、follow起点だと本人のタイミング次第で実質利用可能日数が目減りする不公平が
  生じる点、および生成回数条件(5回到達)が自然に初回生成時点をcount=1とする点を踏まえ、
  「初回生成成功時」を起点に確定した。first-generation-notice-implementation-design.mdが
  既に`usage_counter`に実装済みの`first_generation_notice_sent`判定(`is_first_generation`)に
  `trial_start_at`を便乗させる設計とし、pricing-plan.md「無料トライアル条件(仮)」・
  trial-end-notification-design.md 2節(B)の記述を確定内容に更新した。`trial_start_at`の
  実書き込みロジック(`increment_and_mark_notice()`への引数追加・テスト)、および
  (B)期間到達判定用の日次スケジューラ本体の設計はいずれも次回以降の課題として残る。
- フェーズ101(2026-08-23 12:00 UTC): フェーズ100の残課題だった、`trial_start_at`の実書き込み
  ロジックを実装した。`UsageCounterProtocol`に`set_trial_start_at_if_unset()`・
  `get_trial_start_at()`を追加(2ステップ書き込み経路用)、`AtomicNoticeUsageCounterProtocol.
  increment_and_mark_notice()`に`trial_start_at`引数(既定None)を追加し、trial-start-anchor-
  decision.md 3節の方針通り原子的書き込みに相乗りさせた。`InMemoryUsageCounter`側で両経路とも
  「既に値がある場合は上書きしない」冪等性を実装(初回生成成功時に1回だけ設定、以降不変という
  契約を保証)。`process_memo_event()`は既存の`should_mark_notice_sent`(初回生成成功時のみ真)
  をそのままtrial_start_atの書き込みトリガーとして再利用し、値は既存の`now`引数(JST、未指定時は
  `datetime.now()`)から算出する新規追加イベント・スケジューラなしの構成とした(first-generation-
  notice-implementation-design.mdと同じ「既存の生成完了フローに便乗」方針を踏襲)。テスト10件
  新規追加(`InMemoryUsageCounterTrialStartAtTest`・`ProcessMemoEventTrialStartAtTest`、
  course-set-pasha配下計255件パス)。次の課題である(B)期間到達判定用の日次スケジューラ本体の
  設計(`trial_start_at`から14日経過したユーザーの抽出・プッシュ送信)は未着手のまま残る。
- フェーズ102(2026-08-23 13:00 UTC): フェーズ101の残課題だった(B)期間到達判定用の日次
  スケジューラ本体を設計した(`trial-end-scheduler-design.md`新規作成)。line-reservation-ai/
  reminder-scheduler-design.mdと同じく「全ユーザー共通の単一日次ジョブ+範囲条件による
  抽出」の方式を採用し、`prototype/trial_end_scheduler.py`に選定ロジック
  `select_due_trial_end_notifications()`を実装した(trial_start_at設定済み・
  trial_end_notified_at未設定・upgraded_at未設定・14日以上経過の4条件)。設計の過程で、
  「有料転換済みユーザーを条件(B)の対象から除外する」ために必要な`upgraded_at`
  フィールドがusage_counter側にもstripe_webhook.py側にも存在しない既存ギャップを発見し、
  trial-end-scheduler-design.md 2節に対応方針(フィールドを新設し選定ロジックは先に
  実装、実際の書き込み配線は次回以降の課題とする暫定運用)として明文化した。テスト8件
  新規追加(`SelectDueTrialEndNotificationsTest`、course-set-pasha配下計263件パス)。
  次回はCloud Function D(`send_trial_end_notifications`)本体の実装、または
  `upgraded_at`書き込み配線(stripe_webhook.py `handle_checkout_session_completed()`)
  への着手を優先候補とする。
- フェーズ103(2026-08-23 18:00 UTC): フェーズ102の残課題だった`upgraded_at`書き込み配線
  (stripe_webhook.py `handle_checkout_session_completed()`)を実装した。
  `UsageCounterProtocol`/`InMemoryUsageCounter`(cloud_function_webhook.py)に
  `set_trial_start_at_if_unset()`と対称の`set_upgraded_at_if_unset()`・
  `get_upgraded_at()`を追加し、`handle_checkout_session_completed()`に
  `usage_counter`引数(省略可、デフォルトNoneで従来動作を維持)を追加して、紐付け成功時に
  `upgraded_at`を書き込むよう配線した。stripe_webhook.pyモジュール冒頭の「LINE側コードとは
  独立したファイル」という位置づけを踏まえ、`cloud_function_webhook.py`の具象クラスに
  直接依存させず、構造的部分型付け用の最小限のProtocol(`UpgradedAtWriterProtocol`、
  `set_upgraded_at_if_unset()`のみ要求)を新設して満たす形にした。`receive_stripe_webhook()`
  にも同引数を追加して素通しし、`get_stripe_runtime_dependencies()`のみ
  `InMemoryUsageCounter()`をimportして生成・返却するようにした(store・
  user_profile_storeと同じくプロセス起動ごとの初期化のため、実Firestore接続までは
  LINE側インスタンスと共有されない既知の限界がある点をtrial-end-scheduler-design.md
  2節に明記)。テスト5件新規追加(upgraded_at書き込み・冪等性・未指定時の非書き込み・
  紐付け失敗時の非書き込み・receive_stripe_webhook経由の配線確認、course-set-pasha配下
  計268件パス)。これによりtrial-end-scheduler-design.md 5節の残課題2点のうち1点が解消し、
  残るはCloud Function D(`send_trial_end_notifications`)本体の実装のみとなった。
- フェーズ104(2026-08-23 22:00 UTC): フェーズ103の残課題だったCloud Function D
  (`send_trial_end_notifications`)本体を`prototype/trial_end_scheduler.py`に実装した。
  trial-end-notification-design.md 3節の通知文面を`format_trial_end_notification_message()`
  として実装(line-reservation-aiのcloud_function_process_event.pyに存在しなかったLINE
  Push Message API用クライアント`LinePushClient`/`InMemoryLinePushClient`/
  `LinePushDeliveryError`を本venture向けに新規定義)、`select_due_trial_end_notifications()`
  (フェーズ102)と組み合わせて`send_trial_end_notifications()`として配線した。送信成功時
  のみ`usage_counter.set_trial_end_notified_at()`(本フェーズで新設、
  `UsageCounterProtocol`/`InMemoryUsageCounter`に`set_trial_start_at_if_unset`と対称の
  形で追加)を書き込み、送信失敗時は書き込まずに次回起動時の再試行に委ねる冪等性設計とした
  (line-reservation-ai/cloud_function_send_reminders.pyのsend_reminders()と同じ方式)。
  通知文面中の「投稿文生成: ○回」「浮いた作業時間の目安: 約○分」は、trial-end-
  notification-design.md 5節で試算値自体が未作成と明記されている通り、本フェーズでも
  プレースホルダ文字列のまま残した(実際の値を埋めるには期間集計ロジック・作業時間試算の
  別途設計が必要で、次回以降の課題)。CTAリンクは、checkout-initiation-flow-design.mdの
  LIFF方式決済導線がCheckout Session個別URLではなくLIFFアプリ自体の固定URLである点を
  踏まえ、`cloud_function_webhook.py`の`PORTAL_LINK_PLACEHOLDER`と同じ考え方の
  `LIFF_URL_PLACEHOLDER`とした。テスト9件新規追加(course-set-pasha配下計277件パス)。
  残る課題は3点: (1)通知文面の「○回」「○分」を実際の集計値・試算値に置き換える作業、
  (2)実際のCloud Scheduler新規作成・LIFFアプリ実登録〈いずれもオーナー承認待ち、
  pending-approval.md 2026-08-23 09:00 UTC記載分参照〉、(3)実Firestore接続後にLINE側・
  Stripe側で`usage_counter`インスタンスを共有できるようにする点(フェーズ103から継続)。
- フェーズ105(2026-08-24 01:00 UTC): フェーズ104の残る課題3点のうち(1)
  「通知文面の『○回』を実際の集計値に置き換える」に対応した。trial-end-notification-design.md
  5節が指摘していた「trial_start_atからの期間が月をまたぐため`usage_counter.get_count()`の
  単純な月次集計では正確に求まらない」問題に対し、月次カウンタとは別立ての専用カウンタ
  `trial_generation_count`(`increment_trial_generation_count()`/
  `get_trial_generation_count()`、`UsageCounterProtocol`に追加・`InMemoryUsageCounter`に実装)を
  新設した。`process_memo_event()`内で、生成成功時(status=="generated")かつ
  `plan`指定時の既存カウント処理ブロックに、`get_upgraded_at()`がNone(未アップグレード)の
  ユーザーのみを対象に積み増す1行を追加した(hasattr()判定による後方互換は既存の
  `set_trial_start_at_if_unset`等と同じパターン)。`trial_end_scheduler.py`側は
  `TrialUserState`に`trial_generation_count`フィールドを追加し、
  `format_trial_end_notification_message()`に`generation_count`引数を追加して「○回」を
  実値に置換、`send_trial_end_notifications()`は全ユーザー共通の文面を1回だけ組み立てる
  従来方式から、ユーザーごとに`trial_generation_count`が異なる値を持ちうるため1ユーザーずつ
  文面を組み立てる方式に改めた。テスト11件新規追加(course-set-pasha配下計288件パス)。
  「○分」(浮いた作業時間の目安)は、投稿作成時間の試算値自体が本venture未着手のため
  引き続きプレースホルダのまま残した(trial-end-notification-design.md 5節参照、次回以降の
  課題)。
- フェーズ106(2026-08-24 02:00 UTC): フェーズ105で残った「○分」(浮いた作業時間の目安)の
  試算値作成に対応した。sns-tone-research.mdが既に「個人経営ジムの投稿作成時間の定量データは
  公開情報から見当たらない」と結論づけていたため、追加のWebSearch調査より先に、1回の生成で
  作られる3点セット(SNS投稿文・LINE/Web告知文・課題入れ替え履歴記録、llm-api-cost-
  estimate.md「出力(3件の下書き)」節参照)を手動作成する場合の作業時間を項目別に積み上げる
  仮置き試算(content-generation-time-estimate.md新規作成)を行い、1回あたり平均15分
  (幅12〜18分)という値を採用した。`prototype/trial_end_scheduler.py`に
  `MINUTES_SAVED_PER_GENERATION`定数(=15)を新設し、`format_trial_end_notification_message()`
  に`minutes_per_generation`引数(デフォルト15)を追加して`generation_count × 15分`を
  「浮いた作業時間の目安」欄に埋め込むよう配線した。仮置き値であることを利用者にも透明にする
  ため、文言内に「1回あたり平均15分と仮定」という前提をそのまま残す設計とした。テスト3件
  新規追加(course-set-pasha配下計291件パス)。実ヒアリングによる検証は未実施のまま残る
  (content-generation-time-estimate.md「残課題」参照)。
- フェーズ107(2026-08-24 05:00 UTC): フェーズ106の残課題だった
  content-generation-time-estimate.md「残課題」1点目、「customer-interview-design.mdの
  想定ヒアリング項目に『投稿文作成にかかる時間』を追加する」の要否を確認した。
  customer-interview-design.md「ヒアリング項目」A.現状把握の質問3「告知文の作成に、1回
  あたりどのくらいの時間をかけていますか?」が既にこの検証観点をカバーしており、追加の
  質問新設は不要と判明した。content-generation-time-estimate.md「残課題」1点目に
  (解消済み)注記を追加し、customer-interview-design.md「未検証の仮説」節に、質問3の
  回答をMINUTES_SAVED_PER_GENERATION(=15分、フェーズ106)の妥当性検証にも直結させる旨を
  追記した(実ヒアリング自体はオーナー承認・実連絡待ちの範囲、既存のpending-approval.md
  記載事項の範囲内で変更なし)。ドキュメント整合性確認のみのため新規テスト追加なし
  (course-set-pasha配下は引き続き291件パス)。
- フェーズ108(2026-08-24 07:00 UTC): content-generation-time-estimate.md「残課題」に残って
  いた「15分という値の時給換算訴求軸への展開」(本ドキュメントの範囲外として保留していた項目)
  に対応した。landing-page-copy-draft.mdの料金・トライアル訴求セクション直後に「『時給換算』
  訴求(補足コピー案)」節を新設し、MINUTES_SAVED_PER_GENERATION(=15分、フェーズ106)×
  pricing-plan.mdの各プラン上限生成回数(ライト8回/スタンダード15回/セッター複数30回)から、
  ライト990円/時・スタンダード928円/時・セッター複数797円/時という「浮いた時間の価値」の
  試算コピー案を作成した。15分自体が実ヒアリング未検証の仮置き値である点はコピー内・
  「未検証の仮説」節の両方に明記し、見直し時は本節の金額も再計算が必要と記録した。
  content-generation-time-estimate.mdの当該残課題項目に(解消済み)注記を追加。ドキュメント
  作成のみのため新規テスト追加なし(course-set-pasha配下は引き続き291件パス)。
- フェーズ109(2026-08-24 10:00 UTC): content-generation-time-estimate.md「残課題」に残って
  いた、複数エリア同時更新時の(1)SNS投稿文・(2)LINE/Web告知文・(3)課題入れ替え履歴記録の
  按分方法を設計した。multi-area-mixed-case-review.mdの採用方針(エリアごとに区切って
  列挙・3エリア以上はさらに簡潔化)を踏まえ、(1)(2)は1エリア目が支配的で追加エリアは
  短い差分のみ(追加1エリアあたり仮置き2.5分)、(3)はhistory_rowsの要素数=更新エリア数に
  一致するため線形(1エリアあたり仮置き2.5分)とし、1回の生成イベント(更新対象エリア数n)
  あたり`minutes(n) = 10 + 5n`分という式を導出した(n=1で元のMINUTES_SAVED_PER_GENERATION=
  15と一致)。ただし本フェーズは設計のみにとどめ、prototype/trial_end_scheduler.py・
  cloud_function_webhook.pyへの実装反映(トライアル期間中のエリア更新総数を積み上げる
  専用カウンタ新設が必要)は次の課題として残した。ドキュメント作成のみのため新規テスト
  追加なし(course-set-pasha配下は引き続き291件パス)。
- フェーズ110(2026-08-24 13:00 UTC): フェーズ109の残課題だった按分式`minutes(n) = 10 + 5n`の
  実装反映を行った。cloud_function_webhook.pyのUsageCounterProtocolに
  `increment_trial_area_count(user_id, area_count)`/`get_trial_area_count(user_id)`を
  increment_trial_generation_countと対になる専用カウンタとして新設し(InMemoryUsageCounterにも
  実装)、process_memo_event()内でincrement_trial_generation_countと同じトリガー条件
  (status==generated・plan指定・未有料転換)で`len(instance["history_rows"])`を積み上げる
  よう配線した。trial_end_scheduler.pyはTrialUserStateに`trial_area_count`(既定None、
  未対応usage_counter実装からの後方互換用)を追加し、format_trial_end_notification_message()に
  `area_count`引数を新設。area_count指定時は`10×generation_count + 5×area_count`分・
  「1エリアの更新につき平均15分、複数エリア同時更新時は1エリア追加ごとにさらに約5分と仮定」
  という新文言、area_count未指定(None)時はフェーズ109以前の`15×generation_count`分・
  従来文言のまま、という後方互換のフォールバックにした。テスト14件追加
  (course-set-pasha配下305件パス・schema検証9件パス)。content-generation-time-estimate.md
  「現状の実装との差分・次の課題」に解消済み注記を追加。
- フェーズ111(2026-08-24 16:00 UTC): stripe-webhook-cloud-function-entry-point-design.md
  「残課題」がフェーズ96時点の記述のまま更新されておらず、`resolve_user_id`が「常時Noneを
  返す暫定実装」であるかのように読める状態だった点を点検・訂正した。実際には
  `prototype/stripe_webhook.py`の`get_stripe_runtime_dependencies()`はフェーズ97
  (`make_resolve_user_id()`導入)以降、`InMemoryUserProfileStore()`を1つ生成して
  `resolve_user_id`と共有し、`checkout.session.completed`で書き込んだ紐付けを同一プロセス内の
  `customer.subscription.*`解決で読める設計になっていたため、常時Noneを返す暫定実装ではないこと
  をコードで確認した。回帰防止として`GetStripeRuntimeDependenciesResolutionTest`
  (test_stripe_webhook.py)を新設し、(1)同一の`get_stripe_runtime_dependencies()`結果を使い回した
  場合はcheckout→subscription.deletedでcus_A→U1が解決されmarked_user_ids=["U1"]になること、
  (2)呼び出しごとに別インスタンスを生成した場合は紐付けが共有されずunresolved_customers=["cus_A"]
  になること(同一プロセス限定という既知の限界の明示)の2件を追加した。あわせて既存の
  `test_get_stripe_runtime_dependencies_output_is_accepted_by_receive_stripe_webhook`の
  「resolve_user_idが常にNoneを返す暫定実装のため」というコメントが誤解を生む記述だったため、
  「cus_Aは一度も紐付けられていないため未解決」という正しい説明に訂正した。テスト2件追加
  (course-set-pasha配下307件パス・schema検証9件パス)。design側「残課題」も現状(resolve_user_id
  は解決済み、残るのはFirestore化・webhook_secret保管方法)に更新した。承認不要な
  ドキュメント訂正・テスト追加のみで、外部サービスへの公開・アカウント作成等は今回発生して
  いないためpending-approval.mdへの追記なし。
- フェーズ112(2026-08-24 19:00 UTC): checkout-initiation-flow-design.md(フェーズ98)「残課題」
  3点目、IDトークン検証結果を受け取ってから`build_checkout_session_params()`(フェーズ98)へ
  橋渡しするエントリポイント本体が未設計だった点に対応した。stripe-webhook-http-entry-point-
  design.md(フェーズ95)の`receive_stripe_webhook()`と同じ考え方(検証・解決の実装は呼び出し元
  から注入し、エントリポイント自体は薄い配線とテスト可能な純粋関数にする)で
  `create_checkout_session()`を設計・実装した(checkout-session-endpoint-design.md、
  `prototype/checkout_session.py`)。`verify_id_token`(LIFF IDトークン検証、実LINE Platform
  API呼び出しは実LIFF登録後の課題として引き続き残る)・`user_profile_store`
  (`get_stripe_customer_id`)を注入依存とし、Authorizationヘッダ欠落・非Bearer形式・
  トークン無効の3パターンはいずれも401、成功時は200で`checkout_session_params`を返す設計
  とした。テスト6件追加(course-set-pasha配下313件パス・schema検証9件パス)。承認不要な
  設計・実装・テスト追加のみで、外部サービスへの公開・アカウント作成等は今回発生していないため
  pending-approval.mdへの追記なし。
- フェーズ113(2026-08-24 20:00 UTC): trial-end-notification-design.md「5. 今後の課題」に
  残っていた「(A)生成回数到達側の実装」に対応した。`process_memo_event()`の
  `increment_trial_generation_count()`呼び出し直後に、返り値が`TRIAL_GENERATION_LIMIT`
  (新設、`trial_end_scheduler.py`に`=5`。pricing-plan.md「生成5回到達」と一致)に達し、
  かつ`get_trial_end_notified_at()`が未設定の場合のみ、`format_trial_end_notification_message()`
  で組み立てた通知文を返信本文に便乗追記し`set_trial_end_notified_at()`を書き込む処理を追加した
  (`trial-end-condition-a-implementation-design.md`)。(B)期間到達側の日次スケジューラ
  (`select_due_trial_end_notifications()`)は既に`trial_end_notified_at is not None`を除外する
  設計だったため、どちらが先に発火しても「いずれか早い方で1回のみ」が保たれることを確認した。
  トライアル終了後の「生成一時停止」自体(4節で範囲外とされた部分)は本フェーズでも未実装のまま
  次回以降の課題として残す。テスト5件追加(course-set-pasha配下318件パス・schema検証9件パス)。
  承認不要な実装・テスト追加のみで、外部サービスへの公開・アカウント作成等は今回発生していないため
  pending-approval.mdへの追記なし。
- フェーズ114(2026-08-25 03:00 UTC): フェーズ113で未実装のまま残っていたtrial-end-
  notification-design.md「4. トライアル終了後(未アップグレード)の挙動」の「生成一時停止」を
  実装した。`process_memo_event()`の冒頭(LLM呼び出しより前)に`_is_generation_paused()`を
  追加し、`get_trial_end_notified_at()`が設定済み(条件A/Bいずれかの終了通知が送信済み)かつ
  `get_upgraded_at()`がNone(未アップグレード)の場合のみ、LLM呼び出し・月間カウント・
  トライアル生成回数カウントのいずれも行わず`GENERATION_PAUSED_MESSAGE`(有料プラン登録
  LIFF URLプレースホルダ入り)を即座に返信する分岐を追加した。`MemoProcessResult`に
  `generation_paused`フラグを新設し呼び出し元から一時停止か否かを判別できるようにした。
  usage_counterが該当メソッド未対応の場合(未接続時)は既存の後方互換パターンを踏襲し常に
  Falseとし挙動は変わらない。テスト5件追加(LLM呼び出しが一切行われないことを検証する
  スタブ`_MustNotBeCalledLlmClient`を使用、course-set-pasha配下323件パス・schema検証9件パス)。
  実際の有料プラン登録LIFF URL・Checkout Session実装への差し替え(checkout-initiation-
  flow-design.md参照)は引き続きオーナー承認待ちの範囲として残る。承認不要な実装・テスト
  追加のみで、外部サービスへの公開・アカウント作成・支払い等は今回発生していないため
  pending-approval.mdへの追記なし。
- フェーズ115(2026-08-25 06:00 UTC): checkout-session-endpoint-design.md(フェーズ112)
  「残課題」2点目だった、`create_checkout_session()`を実Cloud Functionsのリクエスト
  オブジェクトに接続する`main(request)`本体を実装した
  (checkout-session-cloud-function-entry-point-design.md新規作成、stripe_webhook.main()と
  対称の構成)。`verify_id_token`実装本体(LINE Platform API実HTTPリクエスト)自体は
  LIFFアプリ実登録待ちで実装できないため、呼ばれたら`NotImplementedError`を送出する
  プレースホルダ`_verify_id_token_not_implemented()`を用意し、`main()`側で捕捉して
  `status_code=501`・`error="verify_id_token_not_implemented"`を返す設計とした
  (Authorizationヘッダ欠落・不正形式は従来通り401でverify_id_token未呼び出し、未実装は
  501で切り分け)。`get_checkout_runtime_dependencies()`も新設し、
  `user_profile_store`は`InMemoryUserProfileStore()`を使用(stripe側と同様、実運用では
  実Firestore接続後にプロセスをまたいだ引き継ぎが必要になる既知の限界が残る)。テスト4件
  追加(course-set-pasha配下327件パス・schema検証9件パス)。承認不要な設計・実装・
  テスト追加のみで、外部サービスへの公開・アカウント作成・支払い等は今回発生していないため
  pending-approval.mdへの追記なし。
- フェーズ116(2026-08-28 06:00 UTC): 直近3日間aircon-pashaへ作業が集中していたため、
  course-set-pashaの棚卸しに戻り、llm-quality-verification-plan.md「残る未確定事項」に
  対応した。aircon-pashaがフェーズ118で先行して作成したllm-quality-verification-results-
  template.mdと同じ考え方をcourse-set-pashaに展開し、同名ドキュメントを新規作成した。
  course-set-pasha固有の検証観点表(厳守事項1〜9・7a、aircon-pashaより1項目多い)・
  9ケース(G1〜G4・OOS1・II1・CI1〜CI3)にあわせて記録表を分割し(G1〜G4共通観点、
  G2固有の厳守事項2・3、複数エリア同時更新ケース固有の厳守事項6、OOS1・II1、
  CI1〜CI3の4グループ)、厳守事項7a(解約意図検知)はaircon-pashaに存在しない
  course-set-pasha固有の分岐であるためaircon-pasha側の記録と直接比較できない旨を
  総合結果サマリ欄に明記した。llm-quality-verification-plan.mdにも解消済みの旨を追記した。
  本ドキュメント自体はAPIキー取得・課金を伴わない空のテンプレートであり承認不要。次回は
  他venture・アイデア領域の前進、または本venture内で実LLM・実Firestore・実LIFF登録待ち
  (オーナー承認待ち)以外の残課題の棚卸しを優先候補とする。
- フェーズ117(2026-08-28 09:00 UTC): aircon-pashaがフェーズ139で指摘した「line-reservation-ai
  にのみ存在し本venture・aircon-pashaには無かった決済失敗(カード継続課金エラー)時の案内」
  設計の欠落に、本venture側でも対応した(payment-failure-dunning-design.md新規作成)。
  aircon-pashaのフェーズ139版を土台に、本venture固有の前提(`UserProfile`ではなく
  `UsageCounterProtocol`への状態管理メソッド追加という設計、postback方式ではなくLIFF経由の
  Checkout Session導線をCTAに使う既存方針、message-tone-variants.md相当の複数トーン切り替えを
  導入していない単一トーン)へ翻案し、業者向け通知文言4種(検知時・終了直前リマインド・
  制限モード移行時・復旧時)を作成した。既存の生成一時停止(`_is_generation_paused()`/
  `GENERATION_PAUSED_MESSAGE`、フェーズ114)と同じ骨格を流用しつつ、支払い方法更新には
  新規Checkout Session発行とは別にStripe Customer Portalが必要になる見込みがある点、
  および本venture自体のStripe Webhookイベント種別ディスパッチ機構がまだ`resolve_user_id`
  止まりで未整備なため決済失敗対応の前提として先にそちらの整備が必要になりうる点を、
  次回以降の検討課題として明記した。設計のみで、`UsageCounterProtocol`へのメソッド追加・
  `stripe_dispatch.py`相当への実装・Webhook配線はいずれも未着手のまま次回以降の課題として
  残した。承認不要な設計・ドキュメント作成のみで、外部サービスへの公開・アカウント作成・
  支払い等は今回発生していないためpending-approval.mdへの追記なし。
- フェーズ118(2026-08-28 10:00 UTC): フェーズ117の申し送りだった
  payment-failure-dunning-design.md「残課題」の実装着手として、`UsageCounterProtocol`へ
  `get_payment_failure_detected_at()`/`set_payment_failure_detected_at()`/
  `clear_payment_failure_detected_at()`を追加し`InMemoryUsageCounter`にも実装した。
  制限モード(段階3)の判定は、design 6節が状態管理メソッドを3つしか挙げていなかった
  意図を汲み、別立ての状態フラグを追加せず検知時刻+猶予日数(`PAYMENT_FAILURE_GRACE_
  PERIOD_DAYS`=7日)から都度算出する`_is_payment_suspended()`として新設し(既存の
  `_is_generation_paused()`は変更せず、前提条件が排他的な別関数として追加)、
  `process_memo_event()`に`PAYMENT_SUSPENDED_MESSAGE`を返す分岐として配線した
  (`MemoProcessResult`に`payment_suspended`フィールドを新設)。また申し送りにあった
  「Stripe Webhookイベントディスパッチ機構が`resolve_user_id`止まり」という記述を
  `stripe_webhook.py`で確認したところ、`dispatch_stripe_event()`自体は
  `customer.subscription.*`3種別を既に処理しておりディスパッチ機構は存在するが、
  `invoice.payment_failed`・`invoice.payment_succeeded`の2種別が未対応という結論は
  正しかったと判明したため、payment-failure-dunning-design.md 6節に訂正を反映した。
  テスト7件追加、venture全体334件全件パス・schema検証9件パスを確認した。承認不要な
  設計・実装・テスト追加のみで、外部サービスへの公開・アカウント作成・支払い等は
  今回発生していないためpending-approval.mdへの追記なし。
- フェーズ119(2026-08-28 14:00 UTC): フェーズ118の申し送りだった、Stripe Webhook
  イベントディスパッチ機構(`stripe_webhook.py`の`dispatch_stripe_event()`)への
  `invoice.payment_failed`・`invoice.payment_succeeded`ハンドラ追加に対応した。
  `_HANDLED_EVENT_TYPES`に2種別を追加し、aircon-pashaの`stripe_dispatch.py`
  (`payment_store`引数によるオプトイン方式)と同じ設計思想で`usage_counter`引数
  (未指定時は`ignored_types`扱いとする後方互換)を新設した。本ventureは
  `UsageCounterProtocol`に`payment_suspended_at`のような別立てフラグを持たない設計
  (フェーズ118で確定済み)のため、`invoice.payment_failed`受信時は
  `set_payment_failure_detected_at()`を呼ぶのみ、`invoice.payment_succeeded`受信時は
  `get_payment_failure_detected_at()`が非nullの場合のみ`clear_payment_failure_
  detected_at()`を呼ぶ(何も設定されていない場合は`payment_recovered_user_ids`に
  追加しない冪等設計)、という薄い実装にとどめた。`receive_stripe_webhook()`から
  `usage_counter`を`dispatch_stripe_event()`へも渡すよう配線し、
  `PaymentFailureUsageCounterProtocol`という薄いProtocolを新設して既存の
  `UpgradedAtWriterProtocol`と同じ「構造的部分型付けによる独立性」の方針を踏襲した。
  テスト9件新規追加(既存334件と合わせて343件、全件パス)、schema検証9件も引き続き
  パス確認済み。承認不要な設計・実装・テスト追加のみで、外部サービスへの公開・
  アカウント作成・支払い等は今回発生していないためpending-approval.mdへの追記なし。
- フェーズ120(2026-08-28 19:00 UTC): フェーズ119の申し送りだった、payment-failure-
  dunning-design.md 6節「猶予期間終了直前リマインドを送信するスケジューラ」の設計・実装に
  対応した(payment-failure-reminder-scheduler-design.md新規作成)。aircon-pashaの
  payment_failure_reminder_scheduler.py(フェーズ143)と同じ全体構成を踏襲しつつ、
  本ventureは`payment_suspended_at`のような別立て状態フラグを持たない設計(フェーズ118)
  のため、`select_due_payment_failure_reminders()`の抽出条件に上限側の条件
  (`経過日数 < 猶予期間7日`)を追加してaircon-pasha版の`payment_suspended_at is None`条件の
  代わりとした。`UsageCounterProtocol`に`payment_failure_reminder_sent_at`の
  get/set/clearを新設(`cloud_function_webhook.py`)し、`stripe_webhook.py`の
  `invoice.payment_succeeded`ハンドラでも決済失敗検知時刻とあわせてクリアするよう拡張した。
  CTAは本venture一貫のLIFF経由プレーンテキストリンク方式とし、Flex Message化は行わなかった。
  `prototype/payment_failure_reminder_scheduler.py`新規作成、テスト16件追加、
  venture全体358件全件パス・schema検証9件パスを確認した。次点は5節のStripe Customer
  Portal要否検討、または制限モード移行自体を能動的にオーナーへ知らせる通知の要否検討。
- フェーズ121(2026-08-29 01:00 UTC): payment-failure-dunning-design.md 4節末尾に先送りして
  いた「猶予期間中に決済が成功した場合の復旧通知の3分岐(制限モードからの復旧/猶予期間中の
  解消/状態リセットのみ)」の詳細設計・実装を行った。aircon-pashaのフェーズ146
  (`payment_recovery_notification.py`)と同じ考え方を移植したが、本ventureは
  `payment_suspended_at`のような保存済みフラグを持たず`_is_payment_suspended()`同様に
  検知時刻からの経過日数を都度算出する設計のため、`classify_payment_recovery()`は
  `payment_suspended_at`ではなく`now`(イベント受信時刻)を引数に取る点がaircon-pasha版
  との相違点。新規`prototype/payment_recovery_notification.py`に`classify_payment_
  recovery()`・`build_payment_recovery_message()`・`handle_payment_succeeded()`を実装、
  「制限モードからの復旧」は既存の「再開しました」文言、「猶予期間中の解消」は新設した
  `PAYMENT_CONFIRMED_IN_GRACE_MESSAGE`(「再開」ではなく「解消されました」と表現)を使用。
  テスト15件追加、venture全体373件全件パス・schema検証9件パスを確認した。承認不要な設計・
  実装・テスト追加のみで、外部サービスへの公開・アカウント作成・支払い等は今回発生していない
  ためpending-approval.mdへの追記なし。`stripe_webhook.py`の`dispatch_stripe_event()`を
  本モジュールへ差し替える実配線、および5節のStripe Customer Portal要否検討は次回以降の
  課題として残る。
- フェーズ122(2026-08-29 03:00 UTC): フェーズ121の申し送りだった、`stripe_webhook.py`の
  `dispatch_stripe_event()`を`payment_recovery_notification.handle_payment_succeeded()`へ
  差し替える実配線を行った。`dispatch_stripe_event()`・`receive_stripe_webhook()`に
  `push_client`引数(省略時は後方互換で通知なし)を新設し、`invoice.payment_succeeded`
  受信時に指定されていれば本モジュールへ委譲する設計とした。aircon-pashaはフェーズ147で
  同種の配線を`invoice.payment_failed`側のみ行い、`payment_failure.py`・
  `payment_recovery_notification.py`が別クラスの`LinePushDeliveryError`を持つ慣習上
  `invoice.payment_succeeded`側は次回以降の課題として残していたが、本ventureは
  `payment_recovery_notification.py`が`trial_end_scheduler.py`の
  `LinePushClient`/`LinePushDeliveryError`をそのまま再利用しているため、この制約なしに
  そのまま配線できた。送信失敗時(`OUTCOME_SEND_FAILED`)は状態を変更せずWebhookリトライに
  委ねる。テスト6件追加、venture全体379件全件パス・schema検証9件パスを確認した。承認不要な
  設計・実装・テスト追加のみで、外部サービスへの公開・アカウント作成・支払い等は今回発生して
  いないためpending-approval.mdへの追記なし。
- フェーズ123(2026-08-29 06:00 UTC): payment-failure-dunning-design.md「残課題」に
  残っていた、5節「CTAリンクの実装課題」(Stripe Customer Portal(支払い方法更新用URL発行)の
  要否・実装方式の検討)に対応した。aircon-pashaフェーズ142と同じ結論で、既存の
  `PortalLinkProvider`Protocol(`render_subscription_procedure_notice()`が解約・
  ダウングレード案内向けに既に使用)をそのまま再利用でき、新規クライアント種別は不要と
  判明した。`cloud_function_webhook.py`の`PAYMENT_SUSPENDED_MESSAGE`(制限モード移行時の
  応答文言)が従来誤って新規Checkout用の`LIFF_URL_PLACEHOLDER`を埋め込んでいた
  (決済失敗からの復旧に必要なのは既存サブスクリプションのStripeカスタマーポータルであり、
  新規申込用のLIFFリンクとは別物という5節の指摘どおりの不整合)ため、`PORTAL_LINK_
  PLACEHOLDER`へ差し替えた上で、新設した`render_payment_suspended_message(portal_link_
  provider, user_id)`が`render_subscription_procedure_notice()`と同じ契約(未接続・
  user_id不明・URL取得失敗時は`PORTAL_LINK_UNAVAILABLE_FALLBACK`へ全文差し替え)で実URLへ
  置換する設計とした。`process_memo_event()`の制限モード分岐をこの関数経由に差し替えた
  (引数追加なし、既存の`portal_link_provider`引数をそのまま使う)。`PORTAL_LINK_
  PLACEHOLDER`/`PORTAL_LINK_UNAVAILABLE_FALLBACK`の定義位置をファイル前方へ移動し、
  解約案内・制限モード案内の両方から共有する構成に整理した。テスト3件追加(実URL置換/
  provider未接続時フォールバック/URL取得失敗時フォールバック)、venture全体382件全件パス・
  schema検証9件パスを確認した。承認不要な設計・実装・テスト追加のみで、外部サービスへの
  公開・アカウント作成・支払い等は今回発生していないためpending-approval.mdへの追記なし。
- フェーズ124(2026-08-29 10:00 UTC): フェーズ123末尾に残っていた「決済失敗検知時通知は
  未対応のまま残る」を解消し、`invoice.payment_failed`受信時(段階1)の実送信配線を実装
  した。aircon-pashaフェーズ147の`handle_payment_failure_detected()`と同じ「送信成功時
  のみ状態を書き込む(送信失敗時はWebhookリトライに委ねる)」設計だが、aircon-pashaが
  Flex Message+ボタン形式なのに対し、本ventureは`payment_failure_reminder_scheduler.py`
  と同じプレーンテキスト+LIFF URL差し込み形式(design 4節「決済失敗検知時(猶予期間開始)」の
  文言をそのまま踏襲)を採った。`payment_recovery_notification.py`に`build_payment_
  failure_detected_message()`・`handle_payment_failure_detected()`を追加し、
  `stripe_webhook.py`の`dispatch_stripe_event()`の`invoice.payment_failed`分岐を
  `push_client`指定時はこの関数へ委譲するよう差し替えた(`StripeDispatchResult`に
  `payment_failure_detection_notification_failed_user_ids`を追加)。`push_client`は
  `invoice.payment_succeeded`側(フェーズ122)と共通の引数をそのまま使い回せた。3日前
  リマインド(`payment_failure_reminder_scheduler.py`)は既存対応済みのため、design 4節の
  3種類の通知(段階1検知時・3日前リマインド・制限モード移行時)のうち残るは制限モード
  移行時(段階3)の能動的通知のみとなった(README「残課題」参照)。テスト9件追加
  (`payment_recovery_notification`側4件・`stripe_webhook`側3件・メッセージ整形2件)、
  venture全体391件全件パス・schema検証9件パスを確認した。承認不要な設計・実装・テスト
  追加のみで、外部サービスへの公開・アカウント作成・支払い等は今回発生していないため
  pending-approval.mdへの追記なし。
  なお`payment_failure_reminder_scheduler.py`の3日前リマインド文言・決済失敗検知時通知は
  同じ`LIFF_URL_PLACEHOLDER`誤用が残ったままで、いずれも全ユーザー共通の1回限りメッセージ
  整形をユーザーごとのポータルURL解決に対応させる改修が必要なため、次回以降の課題として残す。
- フェーズ125(2026-08-29 15:00 UTC): フェーズ124末尾で残った「design 4節の3種類の通知
  のうち残るは制限モード移行時(段階3)の能動的通知のみ」を解消した。これまでの通知は
  すべて顧客(ボルダリングジムオーナー)向けだったが、本フェーズが扱うのは本venture自体を
  営む運営者(オーナー)向けの通知であり、顧客への受動的な`PAYMENT_SUSPENDED_MESSAGE`返信
  (フェーズ118)とは別に、猶予期間超過(制限モード移行)を検知したら運営者へ能動的に
  知らせる仕組みが無いままだった点に対応した。本ventureは`payment_suspended_at`のような
  専用フラグを持たず`_is_payment_suspended()`の都度算出のみで判定しているため
  (フェーズ118)、`payment-suspension-owner-notification-design.md`を新規作成し、
  検知条件(`payment_failure_detected_at`から`grace_period_days`(7日)以上経過かつ
  `payment_suspension_owner_notified_at`未設定)・固定の送信先(`OWNER_LINE_USER_ID_
  PLACEHOLDER`、顧客ごとのuser_idではなく運営者1件固定)・冪等性(送信成功時のみ書き込み)
  ・復旧時のクリアを設計した。`prototype/payment_suspension_owner_notification.py`
  (`select_due_payment_suspension_owner_notifications()`・`send_payment_suspension_
  owner_notifications()`)を新規実装し、`cloud_function_webhook.py`の
  `UsageCounterProtocol`/`InMemoryUsageCounter`に`payment_suspension_owner_notified_at`
  の3メソッド(set/get/clear)を追加、`payment_recovery_notification.py`の
  `handle_payment_succeeded()`の2つの復旧分岐(`OUTCOME_SILENT_RESET`・通知成功時)双方に
  `clear_payment_suspension_owner_notified_at()`を追加して、将来の再決済失敗時にも
  オーナー通知が再度飛ぶようにした。テスト14件追加、venture全体405件全件パス・schema検証
  9件パスを確認した。承認不要な設計・実装・テスト追加のみで、外部サービスへの公開・
  アカウント作成・支払い等は今回発生していないためpending-approval.mdへの追記なし
  (実際のオーナーLINEユーザーIDの取得・実LINE API接続自体は既存の「実LLM呼び出し・実LINE
  API接続」承認待ち範囲に含まれるため新規追加なし)。
- フェーズ126(2026-08-29 18:00 UTC): payment-failure-dunning-design.md 5節末尾
  (フェーズ123追記分)に残っていた、`payment_failure_reminder_scheduler.py`の3日前
  リマインド文言の`LIFF_URL_PLACEHOLDER`誤用を解消した。詳細は下記「次にやること」の
  フェーズ126項目を参照。
- フェーズ127(2026-08-29 20:00 UTC): フェーズ126の残課題だった
  `payment_recovery_notification.py`の`build_payment_failure_detected_message()`の
  `LIFF_URL_PLACEHOLDER`誤用を解消した。詳細は下記「次にやること」のフェーズ127項目を参照。
- フェーズ128(2026-08-30 00:00 UTC): 各設計docの残課題を棚卸しした結果、
  payment-failure-reminder-scheduler-design.md 7節「今後の課題」に、既に実装済み
  (フェーズ123・125・126)にもかかわらず未対応扱いのまま残っていたドキュメント記載漏れを
  2点発見・解消した。(1)「制限モードへの移行を検知してオーナーへ知らせる能動通知が無い」
  という記載は、フェーズ125の`payment-suspension-owner-notification-design.md`・
  `prototype/payment_suspension_owner_notification.py`で既に実装済みだった。
  (2)「決済失敗リマインドの案内先URLを新規Checkout用LIFFか既存契約の支払い方法更新用
  Customer Portalかまだ未決着で、本ドキュメントは暫定でLIFF_URL_PLACEHOLDERをそのまま
  使う」という記載は、フェーズ123でCustomer Portal採用の決着がつき、フェーズ126で
  `payment_failure_reminder_scheduler.py`が実際に`PORTAL_LINK_PLACEHOLDER`・
  `PortalLinkProvider`ベースへ移行済みだった。コード変更は無し(ドキュメント整理のみ)、
  venture全体413件全件パスを再確認した。承認不要なドキュメント整理のみで、外部サービスへの
  公開・アカウント作成・支払い等は今回発生していないためpending-approval.mdへの追記なし。
- フェーズ129(2026-08-30 03:00 UTC): payment-failure-dunning-design.mdの棚卸しを続け、
  フェーズ126末尾に残っていたドキュメント記載漏れを発見・解消した。「`payment_recovery_
  notification.py`の`build_payment_failure_detected_message()`も同じ`LIFF_URL_
  PLACEHOLDER`誤用が残っており、次回以降の課題として残す」という記載は、実際には
  フェーズ127で`render_payment_failure_detected_message(portal_link_provider,
  user_id)`への差し替えが既に完了しており(`prototype/payment_recovery_
  notification.py`163行目)、フェーズ128と同種の「実装済みなのに未対応扱いのまま」の
  記載漏れだった。コード変更は無し(ドキュメント整理のみ)、venture全体413件全件パス・
  schema検証9件パスを再確認した。承認不要なドキュメント整理のみで、外部サービスへの
  公開・アカウント作成・支払い等は今回発生していないためpending-approval.mdへの追記なし。
- フェーズ130(2026-08-30 05:00 UTC): trial-end-scheduler-design.md 2節で「有料転換済み
  ユーザーの除外」用に新設した`upgraded_at`フィールドについて、`stripe_webhook.
  handle_checkout_session_completed()`が書き込む配線(フェーズ103)自体は完了していたが、
  それを`trial_end_scheduler.select_due_trial_end_notifications()`側の抽出条件へ実際に
  反映する経路(`TrialUserState`をusage_counterから読み取って組み立てる関数)が
  存在しなかった配線漏れを発見・解消した。`trial_end_scheduler.py`に
  `build_trial_user_states(usage_counter, user_ids)`を新設し、同一の
  `InMemoryUsageCounter`インスタンスを介して`handle_checkout_session_completed()`の
  書き込みが`select_due_trial_end_notifications()`の除外条件に実際に反映されることを
  確認する結線テスト(`StripeWebhookUpgradedAtToTrialEndSchedulerWiringTest`)を新設した。
  テスト4件追加、venture全体417件全件パス・schema検証9件パスを確認した。承認不要な
  設計・実装・テスト追加のみで、外部サービスへの公開・アカウント作成・支払い等は
  今回発生していないためpending-approval.mdへの追記なし。
- フェーズ131(2026-08-30 12:00 UTC): trial-end-notification-design.md・
  limit-approaching-notification-design.mdの棚卸しを続け、既に実装済みにもかかわらず
  未対応扱いのまま残っていたドキュメント記載漏れを2点発見・解消した。
  (1)limit-approaching-notification-design.md 1節「tech-stack.md本体の更新は次回以降の
  課題として残す」という記載は、実際にはtech-stack.md「次のステップ候補」
  2026-08-14 11:00 UTC分で月間生成回数カウント用のコンポーネント5として既に反映済み
  だった。(2)trial-end-notification-design.md 5節「(B)期間到達判定用の日次スケジューラ
  実装、および『生成一時停止』判定の実装は次回以降の課題として残す」という記載は、
  (B)は`prototype/trial_end_scheduler.py`の`select_due_trial_end_notifications()`として、
  「生成一時停止」判定はフェーズ114で`_is_generation_paused()`として、いずれも同ドキュメント
  4節に記載済みの通り既に実装済みだった。コード変更は無し(ドキュメント整理のみ)、
  venture全体419件全件パス・schema検証9件パスを再確認した。承認不要なドキュメント整理のみで、
  外部サービスへの公開・アカウント作成・支払い等は今回発生していないため
  pending-approval.mdへの追記なし。
- フェーズ132(2026-08-30 15:00 UTC): onboarding-settings-and-self-check-design.mdの
  「残課題」節の棚卸しを行い、既に実装・反映済みにもかかわらず未着手扱いのまま残っていた
  ドキュメント記載漏れを2点発見・解消した。(1)「`usage_counter`への
  `first_generation_notice_sent`フィールド追加・`cloud_function_webhook.py`側での配線は
  実Firestore・実LINE API接続待ちのため未着手」という記載は、実際にはフェーズ73
  (スタブ/InMemory実装)・フェーズ74(`gym_area_configured`実データ参照経路)・フェーズ75
  (count増分とフラグ更新の単一書き込み原子性)で既に実装済みで、first-generation-notice-
  implementation-design.mdには正しく反映されていたが本ドキュメント側が未更新のままだった。
  (2)「ジム名・地域名の複数組入力の優先順位ルールをllm-system-prompt-draft.mdへ反映するのは
  次の課題」という記載は、実際にはフェーズ62で厳守事項4への反映が完了済みだった。いずれも
  コード変更は無し(ドキュメント整理のみ)、venture全体419件全件パス・schema検証9件パスを
  再確認した(フェーズ12・22・51・131と同種のドキュメント整合性メンテナンス)。承認不要な
  ドキュメント整理のみで、外部サービスへの公開・アカウント作成・支払い等は今回発生していない
  ためpending-approval.mdへの追記なし。
- 最終更新: 2026-08-30 15:00 UTC

## 次にやること(候補)

- (解消済み 2026-08-30 15:00 UTC・フェーズ132: onboarding-settings-and-self-check-design.mdの
  「残課題」節に残っていたドキュメント記載漏れ2点(first_generation_notice_sentフィールド・
  ジム名地域名優先順位ルールの反映状況)を解消した。詳細は上記フェーズ132参照)
- (解消済み 2026-08-30 12:00 UTC・フェーズ131: trial-end-notification-design.md・
  limit-approaching-notification-design.mdに残っていたドキュメント記載漏れ2点を解消した。
  詳細は上記フェーズ131参照)
- (解消済み 2026-08-30 00:00 UTC・フェーズ128: payment-failure-reminder-scheduler-design.md
  7節に残っていた2点のドキュメント記載漏れ(オーナー能動通知・PortalLinkProvider移行の
  未反映)を解消した。詳細は上記フェーズ128参照)
- (解消済み 2026-08-28 23:00 UTC: CI(`.github/workflows/course-set-pasha-tests.yml`)が
  `test_history_export test_post_generation_checks`の2ファイルのみを個別指定する方式のため、
  以降に追加された8本のテストファイル(test_checkout_session.py・test_stripe_webhook.py・
  test_trial_end_scheduler.py・test_user_id_linking.py等、計340件)がCI上で一切実行されて
  いなかった陳腐化バグを発見・修正した。aircon-pashaのCIが採用していた
  `python3 -m unittest discover -p "test_*.py" -v`方式に統一し、prototype/配下10本・
  計358件全件パスをローカルで確認(詳細はci-setup.md追記参照)。line-reservation-aiの
  CIにも同型のバグがあることに気づき、あわせて修正した(同venture側のci-setup.md参照)。
  承認不要なリポジトリ設定・ドキュメント更新のみで、外部サービスへの公開・アカウント作成・
  支払い等は今回発生していないためpending-approval.mdへの追記なし。)
- (解消済み 2026-08-28 19:00 UTC: 猶予期間終了直前リマインドを送信するスケジューラの設計・
  実装はフェーズ120で対応した。詳細は上記フェーズ120参照)
- (解消済み 2026-08-28 14:00 UTC: Stripe Webhookイベントディスパッチ機構への
  `invoice.payment_failed`・`invoice.payment_succeeded`ハンドラ追加はフェーズ119で
  対応した。詳細は上記フェーズ119参照)
- (解消済み 2026-08-29 01:00 UTC・フェーズ121: 猶予期間中に決済が成功した場合の復旧通知
  3分岐の詳細設計・実装は上記フェーズ121で対応した。詳細は上記フェーズ121・
  payment-failure-dunning-design.md 4節参照)
- (解消済み 2026-08-29 03:00 UTC・フェーズ122: `stripe_webhook.py`の`dispatch_stripe_event()`を
  `payment_recovery_notification.handle_payment_succeeded()`へ差し替える実配線は
  上記フェーズ122で対応した。詳細は上記フェーズ122参照)
- (解消済み 2026-08-29 06:00 UTC・フェーズ123: payment-failure-dunning-design.md 5節で
  残っていたStripe Customer Portal(支払い方法更新用URL発行)の要否・実装方式の検討は
  `PAYMENT_SUSPENDED_MESSAGE`(制限モード移行時応答)についてのみ対応した。詳細は上記
  フェーズ123参照。3日前リマインド・決済失敗検知時通知は未対応のまま残る)
- (解消済み 2026-08-29 10:00 UTC・フェーズ124: 決済失敗検知時(段階1)通知の実送信配線は
  上記フェーズ124で対応した。詳細は上記フェーズ124参照。残るのは制限モード移行時(段階3)の
  能動的通知のみ)
- (解消済み 2026-08-29 15:00 UTC・フェーズ125: payment-failure-reminder-scheduler-design.md
  7節で指摘されていた、制限モード移行時にオーナー(運営者、顧客であるジムオーナーとは別)へ
  能動的に知らせる通知の設計・実装は、上記フェーズ125・payment-suspension-owner-
  notification-design.mdで対応した。詳細は上記フェーズ125参照。実際のオーナーLINE
  ユーザーIDの設定・実LINE API接続は既存の承認待ち範囲に含まれるため新規追加なし)
- (解消済み 2026-08-29 18:00 UTC・フェーズ126: payment-failure-dunning-design.md 5節末尾
  (フェーズ123追記分)に残っていた、`payment_failure_reminder_scheduler.py`の3日前
  リマインド文言の`LIFF_URL_PLACEHOLDER`誤用(新規Checkout用リンクを既存サブスクリプション
  の支払い方法更新案内に使ってしまっていた)を解消した。フェーズ123の
  `render_payment_suspended_message()`と同じ`PortalLinkProvider`Protocolを再利用する
  設計とし、新設した`render_payment_failure_reminder_message(portal_link_provider,
  user_id)`はプレースホルダを`PORTAL_LINK_PLACEHOLDER`へ差し替え、未接続・取得失敗時は
  `PORTAL_LINK_UNAVAILABLE_FALLBACK`へ全文差し替える。`send_payment_failure_reminders()`
  は`liff_url`引数を`portal_link_provider`引数へ差し替え、ポータルURLがユーザーごとに
  個別発行される値であるため、メッセージ整形をループ外の1回限りからユーザーごとの
  呼び出しへ変更した(全ユーザー共通固定文言だった旧`format_payment_failure_reminder_
  message()`は削除)。テスト7件追加、venture全体408件全件パス・schema検証9件パスを
  確認した。承認不要な設計・実装・テスト追加のみで、外部サービスへの公開・アカウント
  作成・支払い等は発生していないためpending-approval.mdへの追記なし。なお同種の誤用が
  `payment_recovery_notification.py`の`build_payment_failure_detected_message()`
  (決済失敗検知時〈段階1〉の初回案内)にも残っており、次回以降の課題として残る)
- (解消済み 2026-08-29 20:00 UTC・フェーズ127: 上記フェーズ126末尾の残課題だった
  `payment_recovery_notification.py`の`build_payment_failure_detected_message()`の
  `LIFF_URL_PLACEHOLDER`誤用を解消した。フェーズ126の`render_payment_failure_reminder_
  message()`と同じ`PortalLinkProvider`Protocolを再利用し、`build_payment_failure_
  detected_message(liff_url)`を`render_payment_failure_detected_message(portal_link_
  provider, user_id)`へ差し替え(契約はフェーズ126と同一: 未接続・user_id不明・URL取得
  失敗時は`PORTAL_LINK_UNAVAILABLE_FALLBACK`)、`handle_payment_failure_detected()`・
  `dispatch_stripe_event()`(`stripe_webhook.py`)にも`portal_link_provider`引数を追加して
  実配線した(`portal_link_provider`未指定時は従来通りフォールバック文言、既存呼び出し
  経路への後方互換を維持)。これでdesign 4節の3通知(決済失敗検知時・3日前リマインド・
  制限モード移行時)すべてが同じPortalLinkProviderベースのURL解決に揃った。テスト
  (`test_payment_recovery_notification.py`のBuildPaymentFailureDetectedMessageTestsを
  RenderPaymentFailureDetectedMessageTestsへ差し替え5件・HandlePaymentFailureDetectedTests
  に1件追加、`test_stripe_webhook.py`に2件追加、既存1件を`portal_link_provider`指定へ更新)、
  venture全体413件全件パス・schema検証9件パスを確認した。承認不要な設計・実装・テスト
  追加のみで、外部サービスへの公開・アカウント作成・支払い等は今回発生していないため
  pending-approval.mdへの追記なし。)
- フェーズ110で反映した按分式の実Firestore接続後の検証。実際のトライアルユーザーの
  複数エリア同時更新頻度が仮定(追加1エリアあたり2.5分)と乖離していないか、実ヒアリングでの
  確認が必要(実LLM・実Firestore接続はオーナー承認待ちの範囲)。
- (解消済み 2026-08-24 07:00 UTC: 「時給換算」訴求軸への展開はlanding-page-copy-draft.md・
  フェーズ108で対応した。詳細は上記フェーズ108参照。残るのは15分という前提値自体の実
  ヒアリングによる検証)
- (解消済み 2026-08-24 02:00 UTC: 「浮いた作業時間の目安」(○分)の試算値作成は
  content-generation-time-estimate.md・フェーズ106で対応した。詳細は上記フェーズ106参照。
  残るのは実ヒアリングによる15分という仮置き値の検証)
- (解消済み 2026-08-24 01:00 UTC: 通知文面の「○回」の実値化は`trial_generation_count`
  (フェーズ105)で対応した。詳細は上記フェーズ105参照)
- (解消済み 2026-08-23 22:00 UTC: Cloud Function D本体の実装は`prototype/
  trial_end_scheduler.py`の`send_trial_end_notifications()`(フェーズ104)で対応した。
  詳細は上記フェーズ104参照。残るのは通知文面の「○回」「○分」の実値化・実際のCloud
  Scheduler作成〈オーナー承認待ち〉)
- (解消済み 2026-08-23 13:00 UTC: 期間到達判定用の日次スケジューラ本体の設計は
  `trial-end-scheduler-design.md`(フェーズ102)で対応した。詳細は上記フェーズ102参照。
  残るのはCloud Function D本体の実装・`upgraded_at`書き込み配線・実際のCloud Scheduler
  作成〈オーナー承認待ち〉)
- (解消済み 2026-08-23 18:00 UTC: `upgraded_at`書き込み配線はフェーズ103で対応した。
  詳細は上記フェーズ103参照。残るのはCloud Function D本体の実装・実際のCloud Scheduler
  作成〈オーナー承認待ち〉)

- (解消済み 2026-08-23 11:00 UTC: トライアル開始起点〈初回follow時 or 初回生成時〉の確定は
  `trial-start-anchor-decision.md`(フェーズ100)で対応した。詳細は上記フェーズ100参照。
  残るのは`trial_start_at`の実書き込みロジック実装〈フェーズ101で対応済み〉・期間到達判定用の
  日次スケジューラ設計〈フェーズ102で対応済み〉)

- (解消済み 2026-08-23 09:00 UTC: トライアル終了通知メッセージ自体の設計は
  `trial-end-notification-design.md`(フェーズ99)で対応した。詳細は上記フェーズ99参照。
  残るのは「浮いた作業時間の目安」試算・トライアル開始起点の確定・期間到達判定スケジューラ
  実装・生成一時停止判定の実装)
- (解消済み 2026-08-23 08:00 UTC: `client_reference_id`を設定する決済導線の設計は
  `checkout-initiation-flow-design.md`(フェーズ98)で対応した。詳細は上記フェーズ98参照。
  IDトークン検証結果を橋渡しするエントリポイント本体はフェーズ112・
  checkout-session-endpoint-design.mdで対応済み。残るのはLIFFアプリの実登録〈オーナー承認待ち〉・
  `verify_id_token`実装本体〈実LIFF登録後〉)
- (解消済み 2026-08-23 02:00 UTC: `resolve_user_id`〈`stripe_customer_id → user_id`変換〉の
  実装本体を、フェーズ97・`stripe-customer-id-linking-design.md`/
  `handle_checkout_session_completed()`/`make_resolve_user_id()`で行った
  (フェーズ96の残課題(2)。詳細は上記フェーズ97参照)。また`main(request)`本体の実装は
  フェーズ96・`stripe-webhook-cloud-function-entry-point-design.md`で行った
  (フェーズ95の残課題(1)。詳細は上記フェーズ96参照)。残るのは(1)Stripe Checkout
  Session作成時に`client_reference_id`へ内部`user_id`を設定する決済導線自体
  (申込フォーム提出後、どのUIからCheckoutを開始するか未設計)、(2)`store`・
  `user_profile_store`のFirestore化(実GCPプロジェクト作成、オーナー承認待ち)、
  (3)`webhook_secret`の実際の値の取得・保管方法(Secret Manager等、実Stripeアカウント
  接続後)。(1)は接続前でも設計できるため次回の優先候補とする)
- (解消済み 2026-08-22 23:00 UTC: `verify_stripe_signature()`と`dispatch_stripe_event()`を
  結ぶHTTPエントリポイント本体をフェーズ95・`stripe-webhook-http-entry-point-design.md`/
  `receive_stripe_webhook()`で実装した。詳細は上記フェーズ95参照。残るのは(1)実
  `functions_framework`リクエストからの`body`/`Stripe-Signature`ヘッダ取り出し配線
  (`main(request)`のStripe版に相当)、(2)`resolve_user_id`
  (`stripe_customer_id → user_id`)の実装(申込フォーム提出フローのどこで
  `stripe_customer_id`を`user_profile`に書き込むかの設計も必要)、(3)`webhook_secret`の
  実際の値の取得・保管方法(Secret Manager等)。(1)は接続前でも設計・実装できるため
  次回の優先候補とする)
- (解消済み 2026-08-22 20:00 UTC: イベント種別ディスパッチ〜
  `mark_deletion_candidate_on_subscription_deleted()`等の呼び出しを結ぶ部分を
  フェーズ94・`stripe-webhook-event-dispatch-design.md`/`dispatch_stripe_event()`で
  実装した。詳細は上記フェーズ94参照。残るのは(1)`verify_stripe_signature()`と
  `dispatch_stripe_event()`を結ぶHTTPエントリポイント本体(`receive_webhook()`の
  Stripe版に相当、JSONパース・署名検証失敗時の早期リターンを含む)、(2)`resolve_user_id`
  (`stripe_customer_id → user_id`)の実装(申込フォーム提出フローのどこで
  `stripe_customer_id`を`user_profile`に書き込むかの設計も必要)、(3)`webhook_secret`の
  実際の値の取得・保管方法(Secret Manager等)。いずれも実Stripeアカウント接続
  (オーナー承認待ち)後、または接続前でも設計可能な(1)から先に着手できる)
- (解消済み 2026-08-22 17:00 UTC: 実Stripe Webhook受信エンドポイントのうち署名検証部分を
  フェーズ93・`stripe-webhook-signature-verification-design.md`/
  `prototype/stripe_webhook.py`で先行実装した。詳細は上記フェーズ93参照)
- (解消済み 2026-08-22 14:00 UTC: フェーズ91で設計のみだった3関数の実装を
  フェーズ92・`prototype/deletion_candidate.py`で行った。詳細は上記フェーズ92参照。
  残るのは実際のStripe Webhook受信エンドポイント(署名検証・イベント種別ディスパッチ)の
  設計自体で、これはcourse-set-pashaのLINE版`receive-webhook-http-entry-point-design.md`
  と同様、実Stripeアカウント接続なしでも署名検証方式(HMAC-SHA256、`Stripe-Signature`
  ヘッダのタイムスタンプ許容範囲チェックを含む)自体は机上設計・実装できるため、次回の
  優先候補とする)

- (解消済み 2026-08-22 11:00 UTC: 上記(2)Stripe解約webhookを起点とする削除候補洗い出しの
  トリガー設計をフェーズ91・stripe-cancellation-deletion-candidate-trigger-design.mdで
  行った。詳細は上記フェーズ91参照。残るのは実Stripe Webhook受信エンドポイント自体の設計・
  (3)代替連絡経路の収集項目確定(application-form-submission-flow-design.md実装確定後)で、
  いずれも実接続確定後の課題として残る)
- (解消済み 2026-08-22 03:00 UTC: フェーズ85「今後の課題」1点目のlegal-notices-draft.mdへの
  本方針の反映をフェーズ89で行った。詳細は上記フェーズ89参照。残る(2)Stripe解約webhookを
  起点とする削除候補洗い出しのトリガー設計(実Stripe接続後)、(3)代替連絡経路の収集項目確定
  (application-form-submission-flow-design.md実装確定後)は引き続き次の課題として残る)
- (解消済み 2026-08-21 18:00 UTC: フェーズ84・85で2回持ち越されていた「ブロックしたのに
  課金だけ続く」状態へのオーナー向けFAQ・問い合わせ対応文言整備をフェーズ86・
  unfollow-billing-faq.mdで行った。詳細は上記フェーズ86参照。残るのはプロアクティブな
  検知・通知バッチの要否検討(実接続後)と、問い合わせ対応テンプレートの宛先メール
  アドレス確定(legal-notices-draft.md【要記入】確定後)のみ)
- (解消済み 2026-08-21 16:00 UTC: フェーズ84の残課題だった`user_profile`・`usage_counter`の
  長期保存期間上限整理をフェーズ85・data-retention-policy.mdで行った。詳細は上記フェーズ85
  参照。「ブロックしたのに課金だけ続く」状態へのオーナー向けFAQ整備は引き続き未着手のまま
  次の課題として残る)
- (解消済み 2026-08-21 09:00 UTC: フェーズ82の残課題だった、実`functions_framework`の
  リクエストオブジェクトからのbody/署名ヘッダ取り出し配線を`main(request)`として実装した。
  詳細は上記フェーズ83参照。残るのは実Cloud Functionsデプロイ自体・`channel_secret`の実際の
  取得/保管方法・`get_runtime_dependencies()`の実クライアントへの差し替え〈いずれもオーナー
  承認待ち〉、実フォームURL確定後の`ApplicationFormLinkProvider`実装のみ)
- (解消済み 2026-08-21 06:00 UTC: 実HTTPリクエストボディのJSONパース〜
  `verify_line_signature()`との結線をフェーズ82・receive-webhook-http-entry-point-design.mdで
  設計し、`receive_webhook()`として実装した。詳細は上記フェーズ82参照。残るのは実
  `functions_framework`のリクエストオブジェクトからのbody/署名ヘッダ取り出し配線、
  実LINE API接続・実Cloud Functionsデプロイ〈いずれもオーナー承認待ち〉、
  実フォームURL確定後の`ApplicationFormLinkProvider`実装のみ)

- (解消済み 2026-08-21 03:00 UTC: Webhook本体でのfollow/messageイベント種別ディスパッチを
  フェーズ81・webhook-event-dispatch-design.mdで設計し、`dispatch_webhook_events()`として
  実装した。詳細は上記フェーズ81参照。残るのは実HTTPリクエストのJSONパース〜
  `verify_line_signature()`との結線、実LINE API接続〈オーナー承認待ち〉、
  実フォームURL確定後の`ApplicationFormLinkProvider`実装のみ)

- (解消済み 2026-08-21 01:00 UTC: follow イベント受信時のウェルカムメッセージ組み立て・
  連携コード発行〜返信の処理ロジックをフェーズ80・follow-event-welcome-message-design.mdで
  設計し、`process_follow_event()`として実装した。詳細は上記フェーズ80参照。残るのは実LINE API
  接続〈オーナー承認待ち〉、Webhook本体でのfollow/messageイベント種別ディスパッチの実装、
  実フォームURL確定後の`ApplicationFormLinkProvider`実装のみ)

- (解消済み 2026-08-20 23:00 UTC: `purge_expired_links()`の実行トリガーをフェーズ79・
  `linking-code-purge-trigger-design.md`で検討し、`process_memo_event()`便乗(1時間間引き、
  `LinkingCodePurgeThrottle`)として設計・実装した。詳細は上記フェーズ79参照。残るのは実Firestore
  接続・実follow イベントハンドラの実装〈いずれもオーナー承認待ち〉のみ)

- (解消済み 2026-08-20 22:00 UTC: `pending_links`期限切れドキュメントの定期パージの掃除ロジックを
  フェーズ78・`purge_expired_links()`として実装・検証した。詳細は上記フェーズ78参照。残るのは
  実Firestore接続・TTLポリシー設定/スケジューラ配線〈いずれもオーナー承認待ち〉のみ)

- (解消済み 2026-08-20 21:00 UTC: LINE友だち追加時のuser_id事前紐付け経路をフェーズ77・
  line-user-id-linking-design.mdで設計・prototype/user_id_linking.pyとして実装した。詳細は
  上記フェーズ77参照。残るのはGoogleフォーム・GAS Webhookの実設定〈オーナー承認待ち〉、
  実Firestore接続〈オーナー承認待ち〉、実LINE API接続によるfollowイベント受信・
  ウェルカムメッセージ送信〈オーナー承認待ち〉のみ)
- (解消済み 2026-08-18 20:00 UTC: 申込フォーム提出フロー自体〈`user_profile.gym_area_pairs`の
  書き込み側〉をフェーズ76・application-form-submission-flow-design.mdで設計・
  prototype/application_form_submission_flow.pyとして実装した。残るのはGoogleフォーム・GAS
  Webhookの実設定〈オーナー承認待ち〉、実Firestore接続〈オーナー承認待ち〉、LINE友だち追加時の
  user_id事前紐付け経路の未設計〈フォーム側user_id手入力運用の是非〉のみ)
- (解消済み 2026-08-18 19:00 UTC: count増分と`first_generation_notice_sent`更新の単一書き込みでの
  原子性をフェーズ75で実装した。詳細は上記フェーズ75・first-generation-notice-implementation-design.md
  参照。残るのは実Firestore接続〈オーナー承認待ち〉と、申込フォーム提出フロー自体
  〈`user_profile.gym_area_pairs`の書き込み側〉の設計のみ)
- (解消済み 2026-08-18 16:00 UTC: `gym_area_configured`の実データ参照経路
  (`GymAreaConfigStoreProtocol`・`InMemoryGymAreaConfigStore`)をフェーズ74で設計・実装した。
  詳細は上記フェーズ74・first-generation-notice-implementation-design.md 5節参照。残るのは
  実Firestore接続〈オーナー承認待ち〉、count増分とnotice_sent更新の単一書き込みでの原子性の
  実装反映、申込フォーム提出フロー自体(`user_profile.gym_area_pairs`の書き込み側)の設計のみ)
- (解消済み 2026-08-18 13:00 UTC: `first_generation_notice_sent`の実装ギャップを
  フェーズ73で解消した。詳細は上記フェーズ73参照)
- (解消済み 2026-08-18 02:00 UTC: 月間生成回数カウント・上限接近通知のコード実装を
  フェーズ70で行った。詳細は上記フェーズ70参照。残るのは実Firestore接続〈オーナー承認待ち〉と、
  接続後のセッター複数プランの実際の一斉更新パターンの実測のみ)
- (解消(暫定方針決定) 2026-08-17 22:00 UTC: 「残り2回」通知閾値のプラン間固定可否を
  フェーズ69・notification-threshold-per-plan-review.mdで検討した。詳細は上記フェーズ69参照。
  残るのはセッター複数プランの実際の一斉更新パターンの実測〈実LLM接続後の課題、オーナー
  承認待ち〉のみ)
- (2026-08-17 20:00 UTC: 決済手数料・Firestore原価・LLM API原価を統合したユニット
  エコノミクス試算をフェーズ68・unit-economics-estimate.mdで実施した。最も保守的な
  ケースでも粗利率91.9%以上を確保できる見込み。残るのは実際の利用分布〈上限未満で
  終わるオーナー vs 超過が常態化するオーナー〉の実測、決済手数料率・キャッシュTTLの
  一次情報確認で、いずれも実LLM・実決済接続後の課題〈オーナー承認待ち〉)
- (2026-08-17 14:00 UTC: LLM API利用コスト試算をフェーズ67・llm-api-cost-estimate.mdで
  行った。生成1回あたり原価はpricing-plan.mdの従量単価・基本料実質単価に対し1.3〜3.3%
  程度と十分な粗利が残る見込み。残るのは`count_tokens`エンドポイントでの正確なトークン数
  実測とプロンプトキャッシュのTTL方針確定で、いずれも実LLM接続後の課題〈オーナー承認待ち〉)
- (一部解消 2026-08-17 10:00 UTC: Reply APIトークンの有効期限についてWebSearchで
  二次情報を確認した。詳細は上記フェーズ66参照。残るのはトークン失効時の消費有無の
  一次情報確認〈実LINE接続後の課題、WebFetchのegress制約により本エージェントからは
  取得不可〉のみ)
- (解消済み 2026-08-17 07:00 UTC: LLM API/LINE Reply API呼び出し自体の失敗時
  〈タイムアウト・5xx・429等〉のハンドリング設計・実装をフェーズ65・
  api-call-failure-handling.mdで行った。詳細は上記フェーズ65参照。残るのは
  Reply APIトークンの一次情報確認〈実LINE接続後の課題〉のみ)
- (解消済み 2026-08-16 16:00 UTC: `usage_counter`への`first_generation_notice_sent`
  フィールド追加・webhook配線について、フェーズ63・
  first-generation-notice-implementation-design.mdでフィールド定義・書き込みタイミングの
  疑似コードを設計した。詳細は上記フェーズ63参照。残るのは実Firestore/実LINE API接続後の
  実装反映のみ〈オーナー承認待ち〉)
- (解消済み 2026-08-16 13:00 UTC: onboarding-settings-and-self-check-design.mdの残課題だった
  「ジム名・地域名の複数組入力をllm-system-prompt-draft.mdへ反映する作業」をフェーズ62で
  行った。詳細は上記フェーズ62参照。残るのは`usage_counter`への
  `first_generation_notice_sent`フィールド追加・実配線〈実Firestore/実LINE API接続と
  合わせてオーナー承認待ち〉のみ)
- (解消済み 2026-08-16 10:00 UTC: onboarding-guide.mdの残課題だった「申込フォーム統合か
  専用設定ページか」の方針確定と、ステップ4省略時のフォールバック設計をフェーズ61で行った。
  詳細は上記フェーズ61・onboarding-settings-and-self-check-design.md参照。残るのは
  `usage_counter`への`first_generation_notice_sent`フィールド追加・実配線〈オーナー承認待ち〉と、
  ジム名・地域名の複数組入力をllm-system-prompt-draft.mdへ反映する作業のみ)
- (2026-08-16 08:00 UTC: onboarding-guide.mdをフェーズ60で新規作成した。残課題は
  「ジム名・地域名入力を申込フォームに統合するか専用設定ページを持つか」の方針確定、
  ステップ4〈接続テスト〉省略時のフォールバック設計の要否検討)
- (解消済み 2026-08-16 05:00 UTC: 厳守事項7a(iv)の本文文言チェックについて、「短縮リンク
  サービス名のみ」〈bit.ly・lin.ee等〉のケースをフェーズ59で追加検出できるようにした。
  残るのはドメイン・URLの手がかりを一切伴わない純粋な婉曲表現〈「こちらまでご連絡ください」等〉
  で、本文中に検出可能な文字列が存在しないため機械チェックでは原理的に検出できない既知の限界
  として残る。実LLM接続後に実際の生成文パターンが得られた段階で改めて検討する)
- (解消済み 2026-08-15 20:00 UTC: 厳守事項7a(iv)の本文文言チェックについて、「ポータル」を
  含まない別表現〈マイページ・決済ページ・手続きページ表記、URLプレースホルダのみのケース〉
  をフェーズ57で追加検出できるようにした。残るのは短縮リンクサービス名のみ等のさらに
  婉曲的な表現への対応で、実LLM接続後の生成文実例を待って次の課題とする)
- (解消済み 2026-08-15 13:00 UTC: 厳守事項7a(iv)の本文文言チェック
  〈check_subscription_notice_consistency()〉をフェーズ56で実装した。「ポータル」を
  含まない別表現でのリンク案内等、実LLM接続後に拾いきれない違反パターンが無いか
  改めて確認する必要は次の課題として残る)
- (解消済み 2026-08-15 05:00 UTC: 解約意図検知の誤検知防止境界をフェーズ53・
  llm-system-prompt-draft.md厳守事項7aで設計した。schema/output.schema.jsonへの反映
  〈status enum拡張案〉、実LLM接続後の判定精度検証は次の課題として残る)
- (解消済み 2026-08-15 08:00 UTC: schema/output.schema.jsonへの厳守事項7a反映をフェーズ54で
  実施した。`status`enum拡張・`subscription_procedure_notice`フィールド新設・
  validate_test_cases.pyへのテストケース追加まで完了。実LLM接続後の判定精度検証は
  引き続き次の課題として残る)
- (解消済み 2026-08-15 12:00 UTC: ダウングレード時の当月生成回数上限の適用方法を
  フェーズ55・subscription-cancellation-flow-design.mdで確定した。Stripeの請求サイクルが
  ダウングレード操作で途切れないことを確認し、`count`維持・上限即時差し替え方式で
  確定。実装時の`usage_counter`上限参照先の紐づけ方法、実Stripe接続後のテスト環境での
  最終検証は次の課題として残る)
- (解消済み 2026-08-14 15:00 UTC: 国内他社(GMOペイメントゲートウェイ・Univapay等)の従量課金
  対応可否比較、超過課金導入後の決済手数料試算をフェーズ50で行った。国内2社はいずれも
  「未確認・要精査」にとどまり暫定結論は変わらず。残るのは一次情報(開発者ドキュメント)での
  最終確認で、アカウント開設(オーナー承認待ち)後の課題として残る)
- (解消済み 2026-08-14 14:00 UTC: 従量課金の決済代行サービス都度課金対応可否をフェーズ49・
  payment-processor-metered-billing-usage-research.mdで調査した。Stripe Billingを優先候補と
  したが、超過課金導入後の決済手数料試算(subscription-billing-cost-estimate.mdへの反映)、
  国内他社(GMOペイメントゲートウェイ・Univapay等)との比較は次の課題として残る)
- (解消済み 2026-08-14 09:00 UTC→2026-08-14 11:00 UTC: 上限接近時の事前通知設計をフェーズ47・
  limit-approaching-notification-design.mdで行った。tech-stack.md本体への
  「永続データストア不要」方針の見直し反映、subscription-billing-cost-estimate.mdへの
  Firestore読み書き課金の原価試算追加はフェーズ48で完了。実際のFirestore接続実装は
  オーナー承認待ちの範囲として残る)
- (解消済み 2026-08-13 18:00 UTC: 特定商取引法に基づく表記・プライバシーポリシーの文面草案を
  フェーズ43・legal-notices-draft.mdで作成した。事業者名・所在地等の【要記入】項目確定、
  決済代行サービス選定、法律専門家への確認要否は引き続き未確定事項として残る)
- (解消済み 2026-08-13 23:59 UTC: LPワイヤーフレームをフェーズ44・landing-page-wireframe.mdで
  作成した。ビフォーアフター画像・Instagram投稿プレビュー画像そのものの制作、実際のLP実装・
  公開はオーナー承認待ちの範囲として残る)
- post_generation_checks.pyは厳守事項2・3・4・5・7・9を機械チェック化済み(フェーズ36時点)。
  厳守事項6(履歴記録の表形式・1行生成、schemaのhistory_rows構造で担保)・厳守事項8
  (入力不足時の再送依頼、schema/validate_test_cases.pyのstatus分岐で担保)は既存の仕組みで
  カバーされていると判断し、厳守事項1(実際の安全確認・グレーディングへの不介入)は
  「AIが何かを追加で判断・評価しないこと」の確認であり生成文からの機械的な違反検出になじまない
  ため、現時点で新規の機械チェック候補は見当たらない。実LLM接続後に生成文の実例が得られた
  段階で、ここで拾いきれない違反パターンが無いか改めて確認する。
- 個人経営ボルダリングジムオーナー区分の追加候補探索は、WebSearchのスニペット調査では
  頭打ちになりつつあるため、候補1(FRICTION FREAKS)へのヒアリング実施後に紹介・口コミ
  経由で追加候補を探す方針への切り替えを検討する(具体的なヒアリング実施自体は本ventureの
  設計・下書き作成の範囲を超えるため、実施要否・時期はオーナーと相談)。
- (解消済み 2026-08-08 20:00 UTC: history-export-usage-guide.mdの手順3をブラウザ版/モバイル
  アプリ版/Excelの3パターンに具体化した。オーナーが実際に使うツール・環境が判明した際は、
  該当パターンの手順のみを案内すればよい状態になった)
- post_generation_checks.pyの読点区切りケースはフェーズ25で対応済み。厳守事項9(絵文字ルール)の
  機械チェックはフェーズ32で対応済み、対象ブロックの拡張(地域指示記号・囲みCJK記号)は
  フェーズ34で対応済み。残る既知の限界(既知のエリア名一覧に無い第三のエリア名が混在する
  ケース、絵文字パターンの完全網羅性、post-generation-checks-cross-area-review.md
  「残る既知の限界」参照)は実LLM接続後の生成品質検証に委ねる。
- フリーランスセッター区分は当面保留(3回連続で公開情報から候補特定に至らず)。複合ジム
  オーナー区分も候補0件のままのため、いずれも優先度を下げる。
- interview-rehearsal-script.mdのチェックリストに沿った社内リハーサル(時間計測)は
  オーナー内部で完結する作業のため、実施結果が得られた場合は台本の時間配分修正に反映する。
- 候補2(AT WALL)の運営体制調査は法人格の確認までで打ち切り、候補1のみで目標件数に
  届かない場合の予備候補としてのみ扱う(連絡要否は別途オーナーに確認)。
- 実LLM呼び出し・SNS API連携等、外部サービスとの実接続はオーナー承認が必要なため、
  設計・下書き作成の範囲に留める。
- (解消済み 2026-08-09 22:00 UTC: Webhook受信〜LLM呼び出し〜返信のバックエンド処理フロー
  設計・試作をフェーズ38で実装した。詳細は上記フェーズ38・webhook-processing-flow-design.md参照)
  (解消済み 2026-08-09 23:00 UTC: 検証失敗時のリトライ機構をフェーズ39で実装した。
  詳細は上記フェーズ39・webhook-processing-flow-design.md参照)
  (解消済み 2026-08-10 07:00 UTC: テキスト+画像の束ね方(ケースA)をフェーズ40で
  実装した。詳細は上記フェーズ40・text-image-bundling-design.md参照。ケースB
  (別リクエストに分かれる場合)の永続化要否は実LINE接続後の実測データ待ちとして
  引き続き残る)
- (解消済み 2026-08-10 11:00 UTC: LINE Messaging APIの画像メッセージ受信時のコンテンツ取得
  API仕様確認・複数画像添付時の扱いをフェーズ41・line-image-content-api-review.mdで整理した。
  本ventureはコンテンツ取得API自体が不要、複数画像添付も既存のhasPhoto方式で対応済みと
  結論。LINE公式ドキュメントの一次情報での最終確認のみ実LINE接続後の課題として残る)
- 実LLM呼び出し・実LINE API接続は、line-reservation-aiと同様にAPIキー取得・アカウント作成が
  必要でありオーナー承認待ちの範囲。
- (解消済み 2026-08-14 04:00 UTC: 決済代行サービス選定の前段として、月額サブスク決済手数料
  試算をフェーズ45・subscription-billing-cost-estimate.mdで実施した。実際の決済代行サービス
  との契約・アカウント開設はオーナー承認待ちの範囲として残る)
- (解消済み 2026-08-14 07:00 UTC: 月間生成回数の上限超過時の挙動をフェーズ46・pricing-plan.mdで
  従量課金方式に仮決めした。従量単価の妥当性検証、上限接近時の事前通知設計、決済代行サービス側の
  都度課金対応可否確認は引き続き未確定事項として残る)
- フェーズ64(2026-08-16 20:58 UTC): 個人経営ボルダリングジムオーナー区分の新規候補探索を、
  第六弾・第七弾とは異なるキーワード(「note.com 開業 個人経営 売上」「一人 運営 個人事業主
  ブログ 開業」)でWebSearchにより再試行した(candidate-longlist-draft.md第八弾)。候補1
  (FRICTION FREAKS)関連の情報のみが上位に返り、4回連続で新規候補ゼロという結果となった。
  WebSearchのスニペット調査による同区分の候補探索は実質的に頭打ちと判断し一旦打ち切り、
  次の一手は候補1へのヒアリング実施(実施自体はオーナー承認・実連絡が必要、pending-approval.md
  記載の承認待ち事項の範囲内)後に紹介・口コミ経由で追加候補を探す方針への切替を改めて
  提案する形で記録した。
