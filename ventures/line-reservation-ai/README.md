# 予約とれる君(LINE公式AI予約アシスタント)

## 概要
個人事業主〜小規模事業者(美容室、整体・エステ、パーソナルジム、学習塾など)向けに、
LINE公式アカウント上でお客様とのやり取りをAIが解釈し、空き時間の確認・予約確定・前日リマインドまで
自動で行うチャットボットSaaS。

## ステータス
- フェーズ: 会話フロー設計 → 二重予約防止ロジック設計 → オーナー向け設定画面ワイヤーフレーム → LINE Messaging API料金調査 → 料金プラン・無料トライアル条件の仮決め → 想定顧客ヒアリング設計 → 保留タイムアウトのUX文言設計 → 顧客接点メッセージ統一トーン&マナーガイドライン作成 → 前日リマインド送信タイミング・再通知ルール設計 → 無断キャンセル発生時の記録・通知設計 → 事前確認強化の要否検討・顧客詳細画面ワイヤーフレーム追記 → 事前決済(デポジット)機能の技術要件・手数料調査 → ヒアリング項目にデポジット機能の需要・抵抗感を確認する設問(E.)を追加 → ヒアリングリハーサル用台本・時間配分の設計 → 2026年10月LINE料金改定内容の再確認(web調査) → ヒアリング対象候補(実店舗)の選定基準・情報源の整理 → 初回コンタクト依頼文面の草案作成(未送信) → 業種ごとの候補数の妥当性・追加候補確保の目安を試算 → 会話フロー・二重予約防止・トーンガイドライン等を統合したLLMシステムプロンプト草案の作成 → 構造化出力(JSON)フォーマット崩れ時のリトライ・フォールバック設計 → 会話サンプル(正常系・崩れ系)を用いたプロンプトテストケース設計 → テストケースで指摘したE6(雑談・スパム)・E9(未実装機能問い合わせ)への対応をシステムプロンプト草案に反映(厳守事項9・10追加) → 厳守事項9(FAQ/雑談)と6(予約以外の相談エスカレーション)の境界線を整理(9a/9bに分割) → owner-settings-wireframe.mdに9a用の「店舗FAQ情報」入力欄(住所・アクセス/駐車場/支払い方法)を追加 → 店舗FAQ情報欄の具体項目(駐車場台数・支払い方法チェックボックス内訳、未入力時の6番エスカレーション)をllm-system-prompt-draft.mdの厳守事項9aに反映 → conversation-samples-test-cases.mdに9a関連の新規テストケース(E10:登録済み情報でのFAQ回答、E11:未入力項目、E12:未チェック支払い方法)を追加し、9a/9b/6の境界整理との整合を確認 → faq-escalation-boundary.mdの残課題だった9aの回答テンプレート(住所・アクセス/駐車場/支払い方法の項目別穴埋め式テンプレート、複合質問の分割送信例)を新規設計 → faq-response-templates.mdの項目別テンプレートをllm-system-prompt-draft.mdの厳守事項9a説明文に反映(「登録値を言い換えない」旨と複合質問の分割送信・部分エスカレーションのルールを明文化) → conversation-samples-test-cases.mdのE10想定出力を項目別テンプレートに揃えて具体化し、複合質問の分割送信テストケースE13(全項目回答可/一部未登録の2パターン)を新規追加 → E13で発見した「1応答内でintentが項目ごとに混在しうる」課題への対応として、構造化出力(JSON)スキーマに任意フィールド`faq_segments`を追加する拡張案を設計し、llm-system-prompt-draft.md・json-output-retry-fallback.md・conversation-samples-test-cases.mdに反映 → 厳守事項6・10(相談エスカレーション・未実装機能問い合わせ)発生時のオーナー通知文面を具体化し、faq_segments一部未解決時の通知文面も設計 → 連続エスカレーション(同一顧客が短時間に複数回)を1通にまとめる集約ロジック(時間窓5分・初回即時+追加分はまとめ通知の2段階方式)を具体設計 → 未登録FAQ件数・未実装機能問い合わせ件数を俯瞰するための通知ログ集計画面のワイヤーフレームをowner-settings-wireframe.mdに追記(営業情報設定ページからの導線、MVPはスプレッドシート集計で代替) → 定休日対応・曜日別営業時間に続き、昼休憩など1日複数営業時間帯へのAvailabilitySearcher対応を設計・実装(business-hours-lunch-break.md) → release_idle_conversations()/archive_completed_conversations()のWebhook便乗トリガー方式を設計・実装(idle-conversation-trigger-design.md) → candidates_presented失効時の能動通知(候補期限切れメッセージ)の要否を検討し、MVPでは送らない方針を採用(candidates-expired-notification-design.md) → llm-system-prompt-draft.mdの厳守事項7に、店舗設定「メッセージトーン」の値に応じてmessage-tone-variants.mdの変換規則を適用する指示を反映 → prototype/engine.pyの主要ロジックをunittestベースの自動テストスイート化(automated-test-suite.md) → ホスティング基盤をGCP Cloud Functions (Python) + Firestoreに選定(hosting-platform-selection.md) → Firestoreのコレクション設計(firestore-data-model.md) → hold()/confirm()・escalationWindows更新をFirestoreトランザクションに置き換える実装方針を詳細化(firestore-transaction-design.md) → 想定トラフィックでのFirestore読み書き回数・無料枠との比較試算(firestore-traffic-cost-estimate.md、残るは実クライアント接続による実測) → MAX_SEARCH_RANGE_DAYSクランプ時のワーストケース試算(無料枠内店舗数目安を約130店舗→約32店舗に下方修正) → サービス紹介ランディングページ(LP)のコピー草案を新規作成(landing-page-copy-draft.md) → 特定商取引法に基づく表記・プライバシーポリシーの文面草案を新規作成(legal-notices-draft.md) → 確定済み予約データの保存期間・削除方針を新規設計(data-retention-policy.md) → interview-candidate-selection-criteria.mdの選定プロセスに基づき、WebSearchでヒアリング対象候補(実店舗)のロングリスト作成に着手(candidate-longlist-draft.md新規作成、パーソナルジム・美容室で試験的に2件特定、学習塾は次回以降) → 学習塾・個人講師業のロングリスト作成にWebSearchで着手(学習塾は塾長直接運営・電話予約制の候補を1件特定、個人講師業は「個人契約」検索が第三者マッチングサイトばかりヒットし除外条件に該当するため候補ゼロ、次回は個人名・SNS軸の検索に切替と申し送り) → 望ましい条件の業種別見直し(パーソナルジム・整体院・美容室は「ポータル予約はあるが電話・LINE個別対応に依存」まで緩和)を経て、緩和後の条件への該当有無を候補ごとにWebSearchで確認する作業に着手(候補6・整体院は電話・LINE相談への個別対応を確認しヒアリング対象候補に復帰、候補1・パーソナルジムは判断材料不足で再確認を申し送り)
- フェーズ(続き): escalation-consolidation-logic.mdの未検討事項だった「医療相談(6-a)の例外的即時通知の要否」「集約ウィンドウ再発火時の上限回数」を検討・結論化(医療相談も例外なくウィンドウ方式を適用、再発火3回目で都度通知に切り替え+30分途絶えでリセット) → 通知ログ集計画面で使う「未実装機能」分類ラベルの設計(構造化出力に`escalation_reason`/`feature_hint`フィールドを追加する案、分類精度の検証方針を策定) → notification-log-classification-labels.mdで挙げた境界ケース(支払い方法FAQ vs デポジット機能、ノーショー方針FAQ vs キャンセル料機能)をconversation-samples-test-cases.mdにE14・E15として追記し、「店舗FAQ情報欄の入力対象か否か」を9a/10の判定基準とする整理を明文化 → `escalation_reason`/`feature_hint`フィールドをjson-output-retry-fallback.mdのリトライ・フォールバック判定に組み込み(スキーマ不一致時は「分類不能」へフォールバックし、`needs_owner_check`によるオーナー通知自体は止めない方針を明確化) → 通知ログ集計画面へのリンクをowner-settings-wireframe.mdの1.営業情報設定ページ本体のワイヤーフレーム図に反映(これまで追記セクションのみだった差分を解消) → json-schema-multi-intent-extension.mdの未検証事項だった「3項目以上の複合質問でfaq_segments配列が破綻しないか」をconversation-samples-test-cases.mdのE16として机上検証(3項目でもスキーマ変更不要と確認、副次的に「同一topicが複合質問内で重複しうる」点が判明し重複許容の設計であることを明文化) → E16で判明した同一topic重複時の通知ログ集計ルールを新規検討(`resolved: false`のセグメントに絞りユニークなtopic数でカウントする方針を結論化、重複解決済みの水増しを回避しつつ短時間の繰り返し問い合わせはescalation-consolidation-logic.md側の集約通知に委ねるすみ分けを整理)
- フェーズ(続き2): README.mdの「次にやること」で繰り返し指摘していた実装フェーズ着手の第一歩として、
  llm-system-prompt-draft.md・json-schema-multi-intent-extension.md・notification-log-classification-labels.mdの
  出力形式を統合したJSON Schema(schema/booking_output.schema.json)と、外部ライブラリ非依存の簡易バリデータ
  (schema/validate_test_cases.py)を新規作成。conversation-samples-test-cases.mdの期待JSON出力15件を
  机上検証し全件パスを確認(schema-validation-report.md)。実LLM呼び出し自体はAPIキー・課金が必要なため未着手。
- フェーズ(続き3): schema-validation-report.mdで次の課題として挙げていた
  N3(候補提示後の確定)・N4(常連客)・E1(曖昧な日時)・E3(二重予約)・E4(保留タイムアウト)・
  E7(JSON構文崩れ)・E8(自然文とJSONの矛盾)の期待構造化出力(JSON)が未明記だった点を解消。
  conversation-samples-test-cases.mdに全7件を明文化し、validate_test_cases.pyのフィクスチャに追加。
  E7・E8はjson-output-retry-fallback.mdのフォールバック方針(構文崩れは一律escalation合成、
  矛盾検知時はconfirmed常にfalse・needs_owner_check常にtrueへ安全側上書き)に沿って設計。
  合計22件全件パスを確認(schema-validation-report.md追記)。
- フェーズ(続き4): duplicate-topic-notification-log-rule.mdに残っていた未検討事項
  「複数の応答にまたがって同一topicが繰り返し未解決になる場合の期間集計方法(日次ユニークか通算か)」
  を検討・結論化(日次×userId×topicでユニーク化する方式を採用。同一顧客・同一topicでも日をまたげば
  別カウントとし、「何日にわたって発生しているか」の広がりを捉えつつ同一日内の連投による水増しを防ぐ)。
  この結論を踏まえ、notification-log-classification-labels.mdに通知ログ集計画面(スプレッドシート版MVP)の
  具体的な集計手順(resolvedでフィルタ→(日付,userId,topic)でユニーク化→件数集計→
  未実装機能問い合わせ件数は内訳として別表示)を確定・追記。
- フェーズ(続き5): duplicate-topic-notification-log-rule.mdに最後まで残っていた未検討事項
  「userIdが取得できないチャネル(将来Web版チャット等)での代替識別子の設計方針」を検討・結論化
  (channel-agnostic-session-id.md新規作成)。MVPはLINE単独提供のため名寄せ用の恒久ID導入は見送り、
  チャネルごとに独立したセッションID(最終メッセージから30分無応答で失効)を発行する方針を採用。
  通知ログ集計の「日次×userId×topic」ルールはチャネル追加時にuserId部分をセッションIDへ
  読み替えるだけで流用できる設計とした。これにより本ventureの通知ログ集計まわりの設計課題は
  一通り出尽くした状態になった。
- フェーズ(続き6): これまで机上(md文章)でのみ記述してきたjson-output-retry-fallback.md・
  escalation-consolidation-logic.md・duplicate-topic-notification-log-rule.md・
  notification-log-classification-labels.mdの3ロジック(リトライ/フォールバック、
  連続エスカレーション集約通知、通知ログのユニーク集計)を、初めて実行可能なPythonコード
  (prototype/engine.py)に落とし込んだ。実LLM呼び出しは行わず(APIキー・課金が必要なため
  未承認)、LLM呼び出し部分は差し替え可能なスタブとした。デモシナリオを実行し設計md通りの
  挙動を確認済み(prototype-engine-design.md)。実装の過程で「5分ウィンドウの起点を固定式に
  する」という、md設計だけでは未決定だった実装判断を新たに確定し、escalation-consolidation-logic.mdに追記して整合を取った。
- フェーズ(続き7): README.mdの「次にやること」で挙げていた会話フロー本体の実装着手として、
  double-booking-prevention.mdで設計した仮押さえ(pending)→確定(confirmed)の2段階予約枠管理を
  prototype/engine.pyに`BookingSlotManager`クラスとして新規実装(booking-slot-manager-design.md)。
  hold/confirm/タイムアウト解放(5分)/競合時の失敗応答をデモシナリオで確認。確定操作自体が競合した
  場合のpendingへの差し戻し+オーナー通知は、呼び出し側(会話フロー本体)実装時の課題として残した。
- フェーズ(続き8): booking-slot-manager-design.mdで残っていた課題「会話フロー本体
  (候補提示→確定)とBookingSlotManagerの接続」「確定操作自体が競合した場合のpending差し戻し+
  オーナー通知」を実装。`prototype/engine.py`に`ConversationFlowStateMachine`クラスを新規追加し、
  candidates_presented→awaiting_details→confirmedの状態遷移をhold()/confirm()に接続した。
  実装の過程で「pending差し戻し(release()呼び出し)」は、確定済みの別ユーザーの正当な予約を
  誤って消してしまうバグになることが判明したため、release()は呼ばずオーナー通知のみ行う設計に
  変更した(詳細はconversation-flow-state-machine-design.md)。デモシナリオ(タイムアウト後の
  横取り+遅延確定の競合)で、横取りした側の確定済み予約が保持されることを確認済み。
- フェーズ(続き9): README.mdの「次にやること」の第一項目として挙げていた、
  ConversationFlowStateMachine.select_slot()失敗時(候補選択時点での競合)への
  pending-timeout-ux.mdの案内文言(文言案4)接続と、LLM構造化出力から
  select_slot()/provide_details()をどのタイミングで呼び出すかの対応付け設計を実施。
  select_slot()の戻り値を`bool`から`SelectSlotResult(success, message)`に変更し、
  失敗時は案内文言(代替候補は呼び出し側が用意)をそのまま返すようにした
  (prototype/engine.py、デモに山田さんの競合シナリオを追加)。対応付けの整理は
  intent-to-flow-mapping.mdに新規作成。整理の過程で「datetime_candidate(自然文)を
  具体的なslot_keyへ変換する空き枠検索コンポーネントが未設計」という新たな残課題が判明した。
- フェーズ(続き10): intent-to-flow-mapping.mdの残課題だった「datetime_candidate(自然文)を
  具体的なslot_keyへ変換する空き枠検索コンポーネント」を設計・実装した
  (slot-search-component-design.md新規作成)。自然文の解釈はLLM(将来のスキーマ拡張、今回は未実装)、
  空き枠の算出(営業時間・メニュー所要時間・BookingSlotManagerとの突き合わせ)は決定的コードで行う
  役割分担とし、`AvailabilitySearcher`クラスをprototype/engine.pyに新規実装した。
  デモで確定済み枠が候補から正しく除外されることを確認済み。schema拡張・システムプロンプトへの
  反映は今後の課題として残した。
- フェーズ(続き11): slot-search-component-design.mdの今後の課題だった、LLM構造化出力への
  `requested_date_range`/`time_of_day_preference`フィールド追加をbooking_output.schema.jsonに
  反映し、llm-system-prompt-draft.mdに「自然文datetime_candidateからこの2フィールドを抽出する」
  指示(intentがnew_booking/changeのときのみ、手がかりがなければ断定せずnull/'none'のまま)を
  追記した。自由記述のdatetime_candidateは顧客への確認メッセージ表示用としてそのまま残す設計は
  維持。この2フィールドをAvailabilitySearcherの引数へ実際に接続する実装(prototype/engine.py、
  intent-to-flow-mapping.mdへの反映)は次の課題として残した。
- フェーズ(続き12): 上記で残っていた、`requested_date_range`/`time_of_day_preference`を
  AvailabilitySearcherの引数へ接続する実装を行った。`search_candidates_from_llm_output()`関数を
  prototype/engine.pyに新規追加し、LLM構造化出力からAvailabilitySearcher.find_candidates()を
  呼び出して空き枠候補一覧を得られるようにした(`requested_date_range`がnullの場合はNoneを返す)。
  デモにLLM構造化出力→検索→present_candidates()→select_slot()までの一連の流れを追加し、
  動作を確認済み(intent-to-flow-mapping.md・slot-search-component-design.mdに反映)。この過程で
  「提示した候補一覧から顧客の返信に対応するslot_keyを1件特定する処理」が未設計であることが
  新たに判明した。
- フェーズ(続き13): candidate-presentation-and-selection-design.mdの残課題だった
  「ConversationFlowStateMachine.select_slot()との接続」を実装した。`present_candidates()`に
  candidates引数を追加して状態に保持できるようにし、`select_slot_from_reply(user_id, reply_text, now)`を
  新規追加(内部でresolve_candidate_selection()→特定できればselect_slot()、特定不能なら
  format_reconfirm_message()をmessageに詰めた失敗結果を返し会話ステージは据え置き)。既存の
  select_slot()(slot_keyを直接受け取る版)は呼び出し側で既にslot_keyが分かっているケース向けに
  併存させた。デモで特定成功(鈴木さん)・特定不能時のステージ据え置き(渡辺さん)を確認済み。
- フェーズ(続き14): README.mdの「次にやること」で1番目に挙げていた、
  select_slot_from_reply()が再確認文言を返した後も特定できない状態が続く場合の
  再確認ループの上限回数・エスカレーション切り替えタイミングを設計・実装した。
  `_ConversationState`に`reconfirm_count`を追加し、特定不能が`RECONFIRM_MAX_ATTEMPTS`(=2)回を
  超えて連続したら、再確認文言の繰り返しをやめて`EscalationConsolidator`経由でオーナーへ通知し
  (`escalation_reason='candidate_selection_unresolved'`、booking_conflict同様スキーマ未反映の
  システム内部イベント)、顧客には担当からの折り返しを案内する定型文を返すようにした。
  会話ステージは`candidates_presented`のまま据え置き、エスカレーション後は`reconfirm_count`を
  リセットして再度2回分の猶予から数え直す設計とした(candidate-presentation-and-selection-design.md
  6節、prototype/engine.pyにデモ追加(高橋さんの3回連続特定不能→3回目でエスカレーション文言に
  切り替わることを確認))。
- フェーズ(続き15): README.mdの「次にやること」で指摘していた
  `_Candidate.label`への曜日追加(`8/9 14:00〜` → `8/9(土) 14:00〜`、
  tone-and-manner-guideline.mdの確定メッセージ・リマインド表記との不一致解消)を実施した。
  `prototype/engine.py`に`_WEEKDAY_JA`を追加しラベル生成に反映。この変更により
  `_label_date_and_time_in_reply()`(顧客の自然文返信からの候補特定)が曜日抜き返信と
  一致しなくなる回帰が生じることが判明したため、日付部分の比較を`(`より前のみで行うよう
  修正した(候補: 曜日付き返信・曜日抜き返信の両方で一致することを確認済み)。
  デモ実行で全シナリオの成功を再確認済み(candidate-label-weekday-fix.md新規作成)。
- フェーズ(続き16): README.mdの「次にやること」に残っていたAvailabilitySearcherのMVP制約
  「店舗全曜日固定の営業時間のみ対応、定休日・曜日別営業時間未対応」のうち、定休日対応に着手した。
  `AvailabilitySearcher`に`closed_weekdays`パラメータ(月=0〜日=6)を新規追加し、
  対象曜日の枠を空き枠検索から除外するようにした(owner-settings-wireframe.mdの営業曜日
  チェックボックスに対応する機能)。曜日別の異なる営業時間の設定はUI側が未設計のため
  引き続きスコープ外として残した(availability-closed-weekday-support.md新規作成)。
- フェーズ(続き17): README.mdの「次にやること」4番目に挙げていた、`escalation_reason='booking_conflict'`
  (確定操作競合時のオーナー通知)をbooking_output.schema.jsonのenumに追加するか、システム内部イベント用の
  別集計軸として扱うかの検討を決着させた。LLMが出力しないイベントのためenum追加は行わず、
  `NotificationLogAggregator`(prototype/engine.py)に`SYSTEM_ESCALATION_REASONS`
  (`booking_conflict`・`candidate_selection_unresolved`)区分を新設し、一般相談(consultation_count)とは
  別枠の`system_event_counts`として集計する方式を採用した。同じ残課題を抱えていた
  candidate-presentation-and-selection-design.md・conversation-flow-state-machine-design.mdにも反映し、
  owner-settings-wireframe.mdの通知ログ集計画面に「システム内部イベント」欄を追加した(2026-08-01決定、
  notification-log-classification-labels.md「システム内部イベントの扱い」参照)。
- フェーズ(続き18): README.mdの「次にやること」に残っていたAvailabilitySearcherのMVP制約
  「曜日別営業時間(例: 土曜だけ短縮営業)未対応」に着手した。`AvailabilitySearcher`に
  `weekday_business_hours`(曜日→(開始,終了)の上書き辞書)を新規追加し、指定した曜日のみ
  既定の`business_hours`を上書きする設計とした。`time_of_day_preference`によるクランプも
  当日の(曜日別上書き後の)営業時間を基準に行うよう修正。owner-settings-wireframe.mdの
  営業時間欄に「曜日ごとに営業時間を変える」トグルを追加(OFF時は従来通り単一欄のみ)。
  デモで土曜10:00-15:00の短縮営業時に、evening(17時〜)希望では候補0件、時間帯希望なしでは
  短縮営業時間内の候補が正しく出ることを確認済み(weekday-specific-business-hours.md新規作成)。
- フェーズ(続き19): business-hours-lunch-break.mdの残課題だった「区間同士が重複・逆転している
  場合のバリデーションが未実装」に対応した。`_normalize_business_hour_ranges()`に開始>=終了・
  隣接区間の重複チェックを追加し、違反時は新設した`BusinessHoursConfigError`
  (ValueError継承)を送出するようにした。`AvailabilitySearcher.__init__`はこの関数を通すため、
  不正な営業時間設定はコンストラクタ呼び出し時点で検出される。隣接するだけ(終了=次の開始)は
  重複扱いにせず許可する。デモに3ケース(重複拒否・逆転拒否・隣接許可)を追加し動作確認済み
  (business-hours-lunch-break.md残課題を解消として反映)。
- フェーズ(続き20): weekday-specific-business-hours.mdに残っていた「曜日別営業時間を0分間にして
  定休日相当を表現でき、closed_weekdaysと二重表現になりうる」問題を検証した。business-hours-lunch-break.md
  で追加済みの区間バリデーション(開始>=終了はBusinessHoursConfigError)が0分間区間にもそのまま
  適用されるため、`weekday_business_hours`経由でも構成時点で例外になり既に防止されていることを確認。
  UI側で別途「定休日と曜日別営業時間の同時設定禁止」バリデーションを追加する必要はないと判断し、
  回帰防止のデモアサーションを`prototype/engine.py`に追加した(weekday-specific-business-hours.md更新)。
- フェーズ(続き21): README.mdの「次にやること」に残っていた、release_idle_conversations()/
  archive_completed_conversations()の実行トリガー未確定という残課題に対応した。専用ホスティング
  基盤(Cloud Scheduler等)の確定を待たずに着手できる案として「Webhook受信便乗トリガー」を
  idle-conversation-trigger-design.mdで検討・選定し(専用スケジューラ案・外部cronサービス案とも
  比較のうえ却下、後者は要オーナー承認のためpending-approval.md行き)、全リクエストでの毎回全件
  スキャンを避けるため最小実行間隔5分での間引きを設計。`ConversationFlowStateMachine`に
  `maybe_run_idle_cleanup()`/`maybe_run_archive()`を実装し、間引きにより2回目呼び出しがスキップ
  されること・間引き期間を超えた3回目で正しく失効することをデモで確認した。
- フェーズ(続き22): tone-and-manner-guideline.md・faq-response-templates.mdで共通の未検証事項として
  残っていた「メッセージトーン(カジュアル/standard/フォーマル)」の出し分けルールを設計した
  (message-tone-variants.md新規作成)。「仮押さえ」「確定」等の固定語彙・日付時刻表記・FAQ回答の
  登録値そのものは3トーン共通で不変とし、語尾の丁寧度・絵文字の有無・感嘆符の使用可否の3点のみを
  トーンに応じて機械的に置き換える方式を採用した。確定メッセージ・前日リマインド・仮押さえ案内・
  FAQ回答テンプレート(駐車場あり)の4例で3トーンの書き換えを確認し、この規則性により新しい
  メッセージを追加する際も個別にトーン別文言を作り込む必要がないことを示した。
  owner-settings-wireframe.mdの営業情報設定ページに「メッセージトーン」選択欄(既定はstandard)を
  追加した。llm-system-prompt-draft.mdへトーン値を受け取って変換規則を適用する指示を追記する作業と
  実LLM検証は今後の課題として残した。
- フェーズ(続き23): README.mdの「次にやること」1番目に挙げていた、conversation-samples-test-cases.md
  へのトーン別(フォーマル/standard/カジュアル)期待出力サンプルの追加に着手した。N3(予約確定メッセージ)
  について、message-tone-variants.mdで設計済みの3トーン書き換え例をテストケース形式に転記し、
  構造化出力(JSON)自体はトーンに関わらず不変であることを明記した。前日リマインド・仮押さえ直後・
  FAQ回答テンプレートのトーン別サンプルは未追加のため引き続き今後の課題として残す。
- フェーズ(続き24): 上記で残っていた前日リマインド・仮押さえ直後・FAQ回答テンプレートのトーン別
  (フォーマル/standard/カジュアル)期待自然文サンプルをconversation-samples-test-cases.mdに追加し、
  4テンプレート全てのトーン別机上サンプルが出揃った。仮押さえ直後・FAQ回答はN3と同じく
  「JSON不変・自然文のみトーン依存」で表現できたが、前日リマインドはLLM出力(JSON)を経由しない
  スケジューラ発火型のプッシュ通知であるため対応するJSON入力自体が存在しないことが新たに判明した。
  実装時にトーン変換ロジックをLLM出力起点の経路とスケジューラ発火の経路の両方で共通化できるかを
  次の課題とした。
- フェーズ(続き25): README.mdの「次にやること」に残っていた、前日リマインド(スケジューラ発火)と
  仮押さえ直後・FAQ回答等(LLM出力起点)の2つの生成経路でmessage-tone-variants.mdのトーン変換
  ロジックを共通の関数として実装できるかの検討に着手し、実装した。`prototype/engine.py`に
  `_render_by_tone(tone, variants)`という単一のディスパッチャを新設し、`format_confirmation_message()`
  ・`format_reminder_message()`・`format_hold_message()`・`format_faq_parking_message()`の
  4つのメッセージ生成関数全てがこれを経由する設計とした。前日リマインドのみ対応するJSON出力を
  経由しない点(引数がLLM構造化出力ではなく呼び出し側が直接渡す値)は変わらないが、
  トーン適用の最終段自体は生成経路によらず共通化できることを確認した(message-tone-variants.md
  に結論を反映)。未知のtone値はstandardへフォールバックする安全側設計とし、デモに
  フォーマル/カジュアル双方の出力例を追加して動作確認済み。
- フェーズ(続き26): prototype/engine.pyの動作確認がこれまで`_demo()`のprint出力の目視のみに
  依存しており、機能追加のたびに既存の振る舞いが壊れていないかを機械的に検知する手段が
  無かった課題に対応した。`unittest`(標準ライブラリのみ)ベースの自動テストスイート
  `prototype/test_engine.py`を新規作成し、リトライ/フォールバック・エスカレーション集約・
  通知ログ集計・予約枠の仮押さえ/確定/タイムアウト・会話フロー状態遷移(競合・再確認ループ・
  無応答失効・アーカイブ・間引きトリガー)・空き枠検索(定休日/曜日別営業時間/昼休憩/
  バリデーション)・候補選択の自然文解決・トーン変換の主要ロジックを31件のテストケースに
  整理した。全件パスを確認済み(automated-test-suite.md新規作成)。`_demo()`は読み物として
  引き続き残置。
- フェーズ(続き27): automated-test-suite.mdの「次の課題」で挙げていた「ホスティング基盤が
  固まった段階でCIでの自動実行を検討する」の前提となる、tech-stack.mdで方向性のみだった
  ホスティング基盤の具体的な選定に着手した。GCP Cloud Functions (Python) + Firestore・
  AWS Lambda + DynamoDB・Cloudflare Workers・Fly.io等のコンテナ常駐PaaSを要件(Python資産の
  流用可否・低トラフィック時コスト・状態ストアとの相性・運用の手軽さ)で比較し、
  prototype/engine.pyがPython標準ライブラリのみで書かれている点を活かせることと無料枠の
  手厚さから、GCP Cloud Functions (Python) + Firestoreを第一候補として決定した
  (hosting-platform-selection.md新規作成)。実際のGCPプロジェクト作成・請求先設定は
  「アカウント作成」に該当するため今回は行わず、着手時に改めてオーナー承認を得る前提とした。
  Firestoreの具体的なデータモデル設計(会話状態・予約枠・通知ログのコレクション分割)は
  次の課題として残した。
- フェーズ(続き28): hosting-platform-selection.mdの次の課題だった、Firestoreの具体的な
  データモデル設計(会話状態・予約枠・通知ログのコレクション分割)に着手した。
  BookingSlotManager・ConversationFlowStateMachine・NotificationLogAggregator・
  EscalationConsolidatorがオンメモリのdict/setで保持している状態を、
  `stores/{storeId}/bookingSlots`・`conversations`・`notificationLogEntries`+
  `notificationLogUniqueTopics`(count()集約クエリでのユニーク集計用)・
  `escalationWindows`の各コレクションに対応付けた(firestore-data-model.md新規作成)。
  hold()/confirm()等の並行書き込みが絡む操作はFirestoreトランザクションへの
  置き換えでMVP時点の「単一プロセス前提」制約を解消できる見込みであることも整理した。
  実装への反映(engine.pyのFirestoreクライアント呼び出しへの書き換え)と、
  想定トラフィックでの読み書き課金試算は次の課題として残した。
- フェーズ(続き29): firestore-data-model.mdの残課題だった、`hold()`/`confirm()`・
  `escalationWindows`更新をFirestoreトランザクションに置き換える実装方針を詳細化した
  (firestore-transaction-design.md新規作成)。`@firestore.transactional`を使った
  read-modify-writeの疑似コードを設計し、Firestore側の楽観的並行性制御により
  BookingSlotManagerに残っていた「単一プロセス前提」制約を解消できることを確認。
  `flush_due_windows()`はドキュメント単位のトランザクションではなく横断クエリが
  必要なため、配列`queued`の非空判定ができないFirestoreの制約に対応する
  `queuedCount`フィールドの併設と、複合インデックスが必要になる点を新たな
  実装時注意点として整理した。実際のFirestoreクライアント接続・動作確認は
  引き続きGCPプロジェクト作成(オーナー承認待ち)後の課題として残した。
- フェーズ(続き30): firestore-traffic-cost-estimate.mdの残課題だった「検索レンジ3日」という
  試算前提の妥当性を確認した。`requested_date_range`はLLMが自然文から抽出する値で実装上は
  上限がなく、顧客が「今月空いてる日」等と広く尋ねると試算前提を大きく超えるレンジで
  Firestoreクエリが発行されうることが判明した。読み取り件数が青天井に増えないよう
  `search_candidates_from_llm_output()`に`MAX_SEARCH_RANGE_DAYS`(暫定14日)による
  クランプを実装し(prototype/engine.py)、自動テストを追加(全32件パス、
  slot-search-component-design.md・firestore-traffic-cost-estimate.mdに反映)。
  14日という値・クランプ時の顧客案内文言は今後の課題として残した。
- フェーズ(続き31): firestore-traffic-cost-estimate.mdの残課題だった「検索レンジ14日
  (MAX_SEARCH_RANGE_DAYS)クランプ時のワーストケースが本試算に未反映」に対応した。
  空き枠検索readsが3日レンジの約4.7倍(14日÷3日)になることを踏まえ、プラン別の
  1店舗1日あたりreads概算を14日ワーストケースで再試算(プロプラン相当で約380reads/日→
  約1,542reads/日)し、無料枠(読み取り50,000回/日)内に収まる店舗数の目安を約130店舗→
  約32店舗に下方修正した。全顧客が常に14日レンジで検索する極端な前提のため、実際の
  検索レンジ分布はcustomer-interview-design.mdのヒアリングで未確認のまま残課題とした。
- フェーズ(続き32): landing-page-copy-draft.mdの「次のステップ候補」で残課題だった、
  特定商取引法に基づく表記・プライバシーポリシーの文面草案を新規作成した
  (legal-notices-draft.md)。事業者名・所在地等の運営主体の実情報が未確定のため
  該当箇所は`【要記入】`のプレースホルダーとした。プライバシーポリシーの第三者提供・
  委託の節では、会話内容を解釈するLLM APIプロバイダへの送信を明記しつつ、契約内容
  (学習利用有無等)はプロバイダ契約後でないと確定できない点を未検証事項として残した。
  文書作成のみにとどめ、LP公開自体は引き続きオーナー承認待ちのため着手していない。
- フェーズ(続き33): legal-notices-draft.mdに残っていた未確定事項のうち、web調査で確認可能な範囲
  (法的助言そのものではなく一般的な傾向整理)に着手した。(1)特定商取引法の所在地表示要否について、
  消費者庁「特定商取引法ガイド」上、有償の情報配信サービス等「役務提供契約」も通信販売の表示義務の
  対象に含まれるとされており本サービスも対象となる可能性が高いこと、特商法自体は2026年1月設置予定の
  検討委員会で見直しが検討中だが正式改正は早くとも2027年以降見込みで現時点は現行法解釈が前提となる
  ことを確認。(2)景品表示法の観点でのAI対応開示要否について、2026年時点の日本法上AI対応の開示を
  一般義務化する法律は見当たらず、広告目的コンテンツはステマ規制との関係で任意開示が推奨される
  という整理があること、EU AI法第50条(2026-08-02本格適用予定)は本サービスがEU域内利用者を
  対象としない前提のため直接適用外と考えられることを確認した。いずれも法的助言ではなく最終判断は
  引き続き法律専門家への確認が必要な事項として残した(legal-notices-draft.md 1節・2.5節に反映)。
- フェーズ(続き34): hosting-platform-selection.mdの「未確定・今後の課題」に残っていた、
  Cloud FunctionsからLINE Messaging API・LLM APIへの外向き通信のタイムアウト設計
  (LLM応答待ちでWebhook応答が遅延した場合の挙動)を検討した。LINEのWebhook応答は
  LLM呼び出し完了を待たずに即時200 OKを返し(reply APIは使わない)、実処理は
  Cloud Tasks経由で非同期起動する第2の関数に委ね、完了後はプッシュメッセージAPIで
  顧客に送信する2段構成を採用した(webhook-async-processing-design.md新規作成)。
  LINE側の再送によるイベント二重処理は、Cloud Tasksのタスク名を決定的なIDにする
  ことで重複排除する方針とした。engine.py側の会話フローロジック(状態遷移・
  メッセージ整形)への変更は不要と確認。Cloud Tasksの実際の導入・push API利用時の
  メッセージ通数試算への影響確認は今後の課題として残した。
- フェーズ(続き35): webhook-async-processing-design.mdに残っていた「タスク名の重複排除キーに
  使える一意なイベントIDの有無」をLINE Developers公式ドキュメント(webhook.yml/Receive messages
  (webhook))のweb調査で確認した。各Webhookイベントには`webhookEventId`(ULID形式)が必ず含まれ、
  これをCloud Tasksの決定的タスク名の生成元にそのまま使えることが判明。加えて
  `deliveryContext.isRedelivery`という真偽値フィールドも同梱されており、LINE側が再送であることを
  明示的に通知してくれるため、Cloud Function A側で早期スキップする追加の防御層も実装できることが
  分かった。設計上の不確定要素はこれで解消し、残るは実装自体(GCPプロジェクト作成後、オーナー承認待ち)。
- フェーズ(続き36): webhook-async-processing-design.mdの残課題だった「Cloud Function A
  (receive_webhook)のハンドラコード実装」に着手した。実際のGCPプロジェクト作成・デプロイは
  引き続きアカウント作成に該当しオーナー承認待ちだが、ハンドラの判断ロジック自体(署名検証・
  webhookEventIdからの決定的タスク名導出・isRedelivery早期スキップ・Cloud Tasks重複排除の模擬)は
  engine.pyのllm_callスタブと同じ考え方でTaskQueueClientを差し替え可能にし、クラウド接続なしで
  実行可能なコードに落とし込んだ(`prototype/cloud_function_webhook.py`新規作成)。
  unittestベースのテスト17件を新規作成し全件パスを確認(`prototype/test_cloud_function_webhook.py`、
  webhook-function-a-implementation.md新規作成)。Cloud Function B
  (process_conversation_event、LLM呼び出し〜push送信)は実LLM呼び出し自体が承認待ちのため
  未着手のまま次の課題として残した。
- フェーズ(続き37): 上記で残していたCloud Function B(process_conversation_event)のうち、
  実LLM呼び出し・実クラウド接続とは切り離せる範囲(Cloud Tasksからデキューしたイベントを
  intent-to-flow-mapping.mdの対応表どおりConversationFlowStateMachineへ振り分け、LINE Push
  Message APIへの送信文言を組み立てる配線ロジック)を実装した。LINE送信部分はCloud Function Aの
  TaskQueueClientと同じ考え方で`LinePushClient`プロトコルとして差し替え可能にした
  (`prototype/cloud_function_process_event.py`新規作成)。new_booking系3パターン(曖昧な日時→
  候補提示、候補選択→hold、氏名/メニュー確定→confirm)を実装し、候補ラベルがhold・confirmの
  案内文言に一貫して引き継がれることを含めunittest 12件で確認(全件パス、既存49件も引き続き
  パス、webhook-function-b-implementation.md新規作成)。escalation/faq intentの顧客向け返信
  (faq_segmentsとの統合)・確定競合時の新候補再提示・前日リマインドのスケジューラ発火経路との
  接続は未着手のまま次の課題として残した。
- フェーズ(続き38): webhook-function-b-implementation.mdの残課題(1)だった、
  escalation/faq intentの顧客向け返信(faq_segmentsとの統合)を実装した。従来
  intent!="new_booking"のイベントは一律オーナー転送のみで顧客には無反応だったが、
  `prototype/cloud_function_process_event.py`に`_handle_faq()`/`_handle_escalation()`を
  新規追加し、複合FAQ(faq_segments付与時)は項目ごとにfaq-response-templates.md準拠の
  テンプレート回答(または保留文言)を1メッセージ1用件で送信、escalation intentは
  共通の保留文言を一次応答として即時送信するようにした。店舗FAQ情報(住所・駐車場・
  支払い方法)を保持する`store_faq_info`をProcessorの新規パラメータとして追加。
  `engine.py`にformat_faq_address_message()・format_faq_payment_message()・
  format_faq_unregistered_message()を新規追加(faq-escalation-customer-reply-implementation.md
  新規作成)。単一項目FAQ(faq_segmentsがnullのケース、E10・E6等)は構造化出力に
  topic情報が無く自動返信できないため、引き続きオーナー転送のみを維持する制約が残った
  (次の課題)。テスト7件追加、既存分含め全68件パス確認済み。
- フェーズ(続き39): webhook-function-b-implementation.mdの残課題(b)だった、確定操作競合時
  (`provide_details()`失敗時)の新しい空き枠の再提示を実装した。初回の候補提示時に使った
  検索条件(`requested_date_range`等)を`_search_context_by_user`にキャッシュしておき、
  競合判明時点(`now`)で同条件のまま再検索する`_represent_candidates_after_conflict()`を
  新規追加。奪われた枠は`BookingSlotManager`側で既に別ユーザーの確定済みのため自然に
  候補から除外され、新しい候補が見つかれば`present_candidates()`で状態を上書きしてその場で
  再提示、顧客はそのまま番号選択で確定操作をやり直せる。検索条件が無い/再検索しても候補
  0件の場合は従来通り謝罪文言のみのフォールバックを維持した(prototype/cloud_function_process_event.py、
  テスト2件追加・既存分含め全69件パス、booking-conflict-candidate-representation.md新規作成)。
  残る課題は(a)単一項目FAQのスキーマ変更検討、(c)前日リマインド経路の呼び出し元、
  (d)実LLM/実LINE API接続自体(オーナー承認待ち)。
- フェーズ(続き40): 上記残課題(c)だった前日リマインド経路の呼び出し元を設計した。
  Cloud Function C(send_reminders)を店舗数に依存しない単一Cloud Scheduler(暫定15分間隔)で
  トリガーする方式を採用し、`reminder-timing-and-resend-rules.md`の目標送信時刻の計算
  (`compute_initial_reminder_target()`)・確定時点で既に目標時刻超過なら送らない判定
  (`should_send_initial_reminder()`)・スケジューラの実行間隔/遅延に自然に追いつける
  冪等な対象抽出(`select_due_initial_reminders()`)・当日朝1回のみの再送判定
  (`select_due_resends()`)をprototype/reminder_scheduler.pyとして実装(テスト21件新規・
  全90件パス、reminder-scheduler-design.md新規作成)。firestore-data-model.mdの
  `conversations`ドキュメントに`reminderSentAt`等4フィールドを追記。残る課題は
  (a)単一項目FAQのスキーマ変更検討、(b)確定後の顧客返信検知(`customerRepliedAt`)の
  配線設計、(c)実LLM/実LINE API/実Cloud Scheduler接続自体(オーナー承認待ち)。
- フェーズ(続き2): reminder-scheduler-design.mdで前日リマインド経路の呼び出し元
  (Cloud Function C: send_reminders)を設計・実装した後、README「次にやること」の
  残課題(a)だった単一項目FAQ(faq_segmentsがnullのケース)のスキーマ変更要否を検討し、
  「厳守事項9aに基づくfaqは単一項目でも1要素配列で必ず付与する」方針に改訂
  (single-item-faq-schema-decision.md新規作成。E10・E14前半の単一項目9a FAQも
  自動返信の対象になった。9b雑談・escalationは引き続きnullのまま。テスト1件新規・全91件パス)
- フェーズ(続き41): change-intent-handling-design.mdの残課題だった、change後の新規候補検索が
  0件だった場合の顧客向け文言をchange専用に出し分ける対応を実施した。旧予約を実際に解放した
  (`awaiting_details`/`confirmed`からの変更)場合のみ`CHANGE_NO_CANDIDATES_MESSAGE`
  (「以前のご予約は取り消し済みです」旨を含む)を送り、解放すべき実体が無かった
  (`candidates_presented`からの変更)場合は従来通りの`REASK_DATE_RANGE_MESSAGE`のままとした
  (`_start_new_booking()`に`change_context`引数を追加、`prototype/cloud_function_process_event.py`)。
  テスト2件追加・全119件パス。これによりintent-to-flow-mapping.mdの主要intent
  (new_booking/cancel/change/faq/escalation)の机上実装は、確認済みの残課題としては
  実LLM/実LINE API/実Cloud Scheduler接続(オーナー承認待ち)とNotificationLogAggregatorの
  システム内部イベント記録ギャップの2点のみを残す状態になった。
- フェーズ(続き42): 前項で最後に残っていたNotificationLogAggregatorのシステム内部イベント
  記録ギャップを修正した(system-event-log-gap-fix.md新規作成)。原因は2つあり、
  (1)`ConversationFlowStateMachine`がbooking_conflict/booking_cancelled/
  booking_change_started/candidate_selection_unresolvedの発火時に`EscalationConsolidator`
  へしか通知しておらず`NotificationLogAggregator`自体を持っていなかった配線漏れ、
  (2)配線を直しても`NotificationLogAggregator.record()`側が`intent == "escalation"`を
  必須条件にしていたため、`intent: "cancel"/"change"`のまま発火するbooking_cancelled/
  booking_change_started/cancel_not_found/change_not_foundが分類されずに素通りしていた
  判定条件の不備。`ConversationFlowStateMachine`に`logs`引数(後方互換のためデフォルトNone)を
  追加し発火箇所を`_notify_system_event()`ヘルパーに統一、`cloud_function_process_event.py`の
  cancel_not_found/change_not_found分岐にも`self._logs.record()`を追加、
  `record()`の分類条件を`needs_owner_check`+`escalation_reason`の値ベースに変更した
  (consultation_countのみ引き続き`intent == "escalation"`を要求)。テスト新規6件+既存5件に
  system_event_counts検証を追加、全125件パス。これによりintent-to-flow-mapping.mdの
  主要intentの机上実装で確認済みの残課題は、実LLM/実LINE API/実Cloud Scheduler接続
  (オーナー承認待ち)のみとなった。
- フェーズ(続き43): これまで動作確認が「コミット前の手動unittest実行」に依存していた点に
  対応し、GitHub Actionsによるテスト自動実行を新規導入した(ci-setup.md新規作成)。
  `.github/workflows/line-reservation-ai-tests.yml`を作成し、`ventures/line-reservation-ai/`
  配下への変更をトリガーにprototype/の自動テストスイート4本(計125件)と
  schema/validate_test_cases.py(22件)を自動実行するようにした。アカウント作成・支払い・
  外部公開のいずれにも該当しない純粋なリポジトリ内設定のため承認不要と判断した。
  実際のActions実行結果(グリーン確認)は次回以降またはオーナー自身の確認に委ねる。
- フェーズ(続き44): 前項で保留していた「実際のGitHub Actions実行結果の確認」を、本セッションで
  利用可能になったGitHub MCPツール(actions_list)経由で実施した。直前のコミット
  (ff80be8、`.github/workflows/line-reservation-ai-tests.yml`初回トリガー分)の
  ワークフロー実行(run id: 30764705150)が`conclusion: success`であることを確認し、
  prototype/自動テスト125件・schema検証22件がCI上でも全件パスすることを実証した
  (ci-setup.mdに結果を追記)。これによりci-setup.mdの「今後の課題」に残っていた
  CI実行結果の閲覧手段の不在は解消された。
- フェーズ(続き45): availability-closed-weekday-support.mdに残っていた「祝日・臨時休業(特定の
  日付を単発で休業にする)への対応」を実装した(ad-hoc-closed-dates-support.md新規作成)。
  `AvailabilitySearcher`に`closed_dates: frozenset[date]`を新設し、既存の`closed_weekdays`
  (曜日単位の定休日)と独立かつ併用可能な形で、対象日がいずれかに該当すればその日の枠を候補から
  除外するようにした。reminder_scheduler.py側への同様の対応とowner-settings-wireframe.mdの
  入力UI追記は影響範囲切り分けのため今回は見送り、次の課題として残した。テスト2件追加・全127件パス。
- フェーズ(続き46): ad-hoc-closed-dates-support.mdに最後まで残っていた
  owner-settings-wireframe.mdへの「臨時休業日リスト」入力欄の追記を行った。「1. 営業情報設定
  ページ」に日付を1件ずつ追加・削除できるシンプルなリスト入力を追加し、曜日単位の定休日
  (営業曜日チェックボックス)とは別枠の設定として両者併用可能である旨を明記した。カレンダーUIや
  祝日データとの自動連携は行わないMVP方針を踏襲。過去日付・重複日付の入力バリデーションは今回は
  未検討のまま新たな残課題とした。これによりad-hoc-closed-dates-support.mdの残課題は解消され、
  本venture全体の残る大きな課題は実LLM/実LINE API/実Cloud Scheduler接続自体(オーナー承認待ち)と
  上記バリデーション設計のみとなった。
- フェーズ(続き47): confirmed-state-archival.md・firestore-data-model.mdの双方で「本文書の
  範囲外」として先送りされていた、永続データストア側(予約実績・会話履歴・通知ログ)の
  個人情報保存期間・削除方針を新規設計した(data-retention-policy.md新規作成)。個人情報保護法の
  一般的な考え方(利用目的達成に必要な範囲を超えた保有を避ける努力義務)を踏まえ、予約実績
  (confirmed)は3年、アーカイブ済み会話状態は`archivedAt`から1年、通知ログは6か月を暫定の
  保存期間として設定。削除の実行自体はホスティング基盤確定後のバッチジョブ実装(オーナー承認待ち)
  に委ね、MVP初期のスプレッドシート運用段階では手動削除で代替する方針とした。法的助言には
  あたらないため最終判断は引き続き法律専門家への確認が必要な事項として残置。
- フェーズ(続き48): interview-candidate-selection-criteria.mdの選定プロセスに基づき、
  WebSearchでヒアリング対象候補(実店舗)のロングリスト作成を継続(2026-08-03 03:00 UTC、
  パーソナルジム・美容室で各1件を試験的に特定、学習塾・個人講師業は次回以降と申し送り)。
- フェーズ(続き49): フェーズ(続き48)の申し送り通り、学習塾・個人講師業のロングリスト作成に
  WebSearchで着手した(2026-08-03 04:00 UTC)。学習塾は塾長直接運営・電話予約制の候補を1件
  特定(世田谷学習塾、candidate-longlist-draft.md参照)。個人講師業(家庭教師)は「個人契約」で
  検索すると教師・生徒を引き合わせる第三者マッチングサイトばかりがヒットし、選定基準の除外条件
  (予約管理自体が主業務ではない仲介事業者)に該当するため候補として採用できるものはゼロ件だった。
  次回は個人名・SNS軸の検索に切り替える方針をinterview-candidate-selection-criteria.mdに追記した。
- フェーズ(続き50): フェーズ(続き49)の申し送り通り、個人講師業(家庭教師)の検索方針を
  「個人契約」から「個人事業主・直接指導」等の独立性を強調する語に切り替えて再挑戦した
  (2026-08-03 05:00 UTC)。仲介サイトを介さない本人発信のブログ・プロフィールを初めて2件特定
  (candidate-longlist-draft.md #4・#5)。整体院は`site:`指定によるブログ限定検索を試したが
  有効な絞り込みにならず未特定のまま次回へ持ち越し、「対象地域の定義(東京都内限定か近隣県含むか)が
  選定基準に未記載」という新たな残課題が判明した。
- フェーズ(続き51): フェーズ(続き50)で判明した残課題に対応した(2026-08-03 06:00 UTC)。
  (1)対象地域の定義をinterview-candidate-selection-criteria.mdに新規決定・明記(東京都内優先、
  近隣県は補完枠、オンライン完結業種は所在地不問)。この決定によりcandidate-longlist-draft.md #5
  (千葉県の家庭教師候補)は除外せず補完枠として残すこととした。(2)整体院の検索手法を`site:`限定から
  個別店舗名+特徴語(「完全予約制」「院長一人」等)検索に切り替え、2件を特定(candidate-longlist-draft.md
  #6・#7)。うち1件(西東京あゆみ整体院)は既にネット予約導線がある可能性があり、望ましい条件を
  満たすかは個別確認が必要な点を明記した。
- フェーズ(続き52): single-item-faq-schema-decision.md・webhook-function-b-implementation.mdの
  「未実装のまま残るもの」で長らく放置されていた厳守事項9aの`hours`(営業時間)・`other`トピックへの
  対応方針を決定した(hours-other-faq-topic-resolution.md新規作成、2026-08-03 08:00 UTC)。
  hoursは、曜日別営業時間・休憩時間を使わないシンプルな店舗のみ登録済みの開始・終了時刻と
  定休日をそのまま案内する自動回答テンプレートを実装(`format_faq_hours_message()`をengine.pyに
  新設、`_render_faq_segment()`にhours分岐を追加)。複雑な店舗(曜日別営業時間・休憩時間あり)は
  安全側で従来通りエスカレーションに倒す設計とした。otherは対応する登録項目が店舗FAQ情報欄に
  存在しないため常にエスカレーションに固定する決定とし、コード変更は不要と結論づけた(既存の
  安全側フォールバックがそのまま機能する)。faq-response-templates.md・llm-system-prompt-draft.md・
  json-schema-multi-intent-extension.mdに反映し、conversation-samples-test-cases.mdにE17
  (営業時間FAQ)を新規追加、schema/validate_test_cases.pyの機械検証は23件全件パス、
  リポジトリ全体のunittestも新規3件を含め132件全件パスを確認済み。
- フェーズ(続き53): candidate-longlist-draft.mdの申し送りだった美容室の候補探しに、学習塾・整体院で
  有効だった「個別店舗名を直接ヒットさせる」検索手法を応用し、引用符付き予約導線フレーズ+
  「個人/プライベートサロン」の組み合わせ検索でポータル一覧を回避、1人経営のプライベートサロン
  2件(to suit、Atelier Queen)を新規に特定した(候補#9・#10)。いずれもサイト自体がWebFetchの
  自動アクセスを403で拒否したため、予約方式・望ましい条件との突き合わせはオーナー自身の目視
  確認に委ねる暫定候補として記録した。pending-approval.md記載の承認範囲(WebSearchでの候補
  リストアップとventureフォルダへの記録のみ)の範囲内で実施し、実店舗への連絡は行っていない。
- フェーズ(続き54): candidate-longlist-draft.mdの申し送りだったパーソナルジム・学習塾の候補積み増しに
  着手した。パーソナルジムは既存候補#1の出典記事(personal-navi.net)内から他の個人経営ジム
  (CUSTOM FIT GYM、代表トレーナー橋本祐樹氏)を新規に特定(候補#11)。学習塾は「塾長が直接指導」等の
  フレーズ検索を試みたが、大手チェーン塾のブランドページが上位を占め除外語での絞り込みが効かず、
  新規候補の特定には至らなかった(次回は運営者個人プロフィール軸の検索に切替と申し送り)。
  引き続きpending-approval.md記載の承認範囲内で実施し、実店舗への連絡は行っていない。
- フェーズ(続き55): フェーズ(続き54)の申し送り通り、学習塾の検索アプローチを運営者個人プロフィール軸
  (「塾長 個人 プロフィール」「完全個別指導」等)に切り替えて再挑戦した。候補3(世田谷学習塾)とは別の
  個人経営塾「世田谷みどり塾」(世田谷区赤堤、塾長・土屋慶氏によるマンツーマン学習塾、固定・携帯の
  2電話番号案内あり)を新規特定(候補#12)。候補3・12とも世田谷区に集中しているため、次回は他区への
  検索対象拡大を申し送った。引き続きpending-approval.md記載の承認範囲内で実施し、実店舗への連絡は
  行っていない(candidate-longlist-draft.md第七弾)。
- フェーズ(続き56): candidate-longlist-draft.mdの申し送り通り、豊田塾(板橋区赤塚)の個人経営可否を
  WebSearchで確認し、塾長個人が運営する単独教室と判断して候補#14として暫定採用した(学習塾候補は
  世田谷区2件・荒川区1件・板橋区1件の計4件に到達し選定基準の目安に近づいた)。パーソナルジムは
  美容室・整体院で有効だった引用符付きフレーズ検索を試したが新規候補は見つからず、既にLINE/Web予約
  対応済みの店舗(プライベートジムMIRO)がヒットするなど新規開拓が3回連続で不調に終わったため、
  次回以降は新規探索よりも既存候補(候補3・11・12・13・14等)のネット予約導線有無の個別確認に
  軸足を移す方針とした(interview-candidate-selection-criteria.mdにも進捗を反映)。
- フェーズ(続き57): 前回申し送り通り、学習塾候補4件(候補3・12・13・14)についてネット予約
  (オンライン予約フォーム・カレンダー式)の導線有無をWebSearchで確認した。いずれも検索結果の
  範囲では電話・メール・問い合わせフォームでの受付が中心で、オンライン予約システムは見当たらず、
  望ましい条件(ネット予約導線なし)に整合的な暫定結果を得た。副次的に豊田塾(候補#14)の
  電話番号(03-6909-9782)を新たに確認し、塾長単独指導という個人経営の確度も上がった
  (candidate-longlist-draft.md第十弾)。整体院候補6・8、美容室候補9・10、パーソナルジム候補1・11の
  ネット予約導線確認は未着手のため次回以降の課題として残した。
- フェーズ(続き58): 前回申し送り通り、整体院候補6・8、美容室候補9・10のネット予約導線有無を
  WebSearchで確認した(candidate-longlist-draft.md第十一弾)。候補6(西東京あゆみ整体院)・
  候補8(霞が関Lead off Health整体院)・候補9(to suit)の3件はいずれも既にポータル経由
  (公式サイト、ホットペッパービューティー、OZmall)のネット予約に対応済みと判明し、望ましい条件
  (ネット予約導線なし)を満たさないことが確認できた。候補10(Atelier Queen)は予約方法を確認
  できず保留。整体院・美容室は「プライベート」「完全予約制」を掲げる個人経営店ほど既にポータル
  予約を導入済みのケースが目立つ傾向が3件連続で裏付けられたため、望ましい条件の運用(緩和の要否)を
  interview-candidate-selection-criteria.mdで整理することを次回以降の課題として残した。パーソナル
  ジム候補1・11のネット予約導線確認、候補10の予約方法再確認も未着手のまま持ち越し。
- フェーズ(続き59): 前回申し送り通り、パーソナルジム候補1(STUDIO NEW CHAPTER)・候補11
  (CUSTOM FIT GYM)のネット予約導線有無をWebSearchで確認した(candidate-longlist-draft.md第十二弾)。
  いずれも既にオンライン予約導線が整備されている可能性が高いことが判明し、望ましい条件(ネット予約
  導線なし)を満たさない疑いが濃厚となった。これでパーソナルジム・整体院・美容室の3業種で「個人経営・
  プライベート志向の店舗ほど既にネット予約を導入済み」という共通傾向が確認され、当初の望ましい条件を
  そのまま適用するとヒアリング対象が学習塾に偏る可能性が浮上した。次回はこの傾向を踏まえた
  interview-candidate-selection-criteria.mdの望ましい条件の業種別見直しに着手する。
- フェーズ(続き60): 前回申し送り通り、interview-candidate-selection-criteria.mdの「望ましい条件」の
  業種別見直しに着手した。学習塾・個人講師業は現行基準を維持し、パーソナルジム・整体院・美容室は
  「ポータル経由のネット予約はあるが、施術相談・キャンセル待ち調整等のきめ細かいやり取りは結局
  電話・LINE個別対応に依存している」ことを望ましい条件とする方針に緩和した(interview-candidate-
  selection-criteria.md「望ましい条件の業種別見直し」節)。これにより候補6・8・9・1・11も、
  電話・LINE個別対応への依存が個別に確認できれば改めて候補になりうる状態に戻った。あわせて
  候補10(Atelier Queen)の予約方法再確認を試みたが、公式サイト(Ameba Ownd)のWebFetch遮断が
  継続しており引き続き未確認(candidate-longlist-draft.md第十三弾)。
- フェーズ(続き61): candidate-longlist-draft.md第十六弾の申し送り通り、業種横断の最終候補
  一覧表(確定6件+保留4件)とinitial-contact-message-draft.mdの依頼文面草案を組み合わせた
  「ヒアリング依頼提示パッケージ」を新規作成した(interview-request-package.md)。優先度A
  (確定6件、学習塾4件・整体院2件)/優先度B(保留4件、美容室2件・パーソナルジム2件、要オーナー
  目視確認)の2段階の依頼順序案、候補ごとの想定連絡チャネルと使用する文面案(A/B/C)の対応表、
  連絡開始前にオーナー判断が必要な未確定事項(謝礼有無・送信者名表記・返信先連絡先・優先度Bの
  依頼可否)を整理した。これでinterview-candidate-selection-criteria.mdの選定プロセス
  ステップ3(絞り込んだ候補リストと依頼文面をセットでオーナーに提示)相当の段階まで到達した。
  実在店舗・個人事業主への実際の連絡・送信は一切行っていない。
- フェーズ(続き62): interview-request-package.mdの「次にやること(候補)」で挙げていた「余力が
  あれば美容室・パーソナルジムの代替候補(第三候補)の探索」に着手した(candidate-longlist-draft.md
  第十七弾)。美容室で新規候補1件(候補17: aane hair、中央区日本橋浜町、女性オーナー1名運営)を
  特定し、interview-request-package.mdの優先度B一覧に追加した(優先度B計4件→5件、母数計10件→
  11件)。パーソナルジムは新規候補を特定できず(「トレーナー個人が経営する東京のパーソナルジム3選」は
  既存候補1・11のみ、「パーソナルジムRat」は複数店舗展開チェーンと判明し必須条件不適合のため除外)、
  引き続き候補1・11の2件のまま。候補17も候補9・10と同様WebFetch遮断のため緩和後の望ましい条件の
  最終確認はできておらず「要オーナー目視確認」の扱い。実店舗への連絡は一切行っていない。
- フェーズ(続き63): candidate-longlist-draft.mdの申し送り通り、美容室の代替候補探索を
  第四弾(Instagram軸、新規0件)・第五弾(ホットペッパービューティー内キーワード経由、新規0件)と
  継続したが、いずれも新規候補は特定できなかった(第五弾では「Ohana」という店名が浮上したが
  同名多店舗のため東京都内の対象店舗を一意特定できず候補化を見送った)。美容室・パーソナルジムの
  新規開拓が5回連続で不調に終わったことを踏まえ、これ以上同角度のWebSearchを重ねる費用対効果は
  逓減していると判断し、次の一歩は新規探索の継続ではなくinterview-request-package.mdの優先度B候補
  (9・11・1・10・17)のオーナー目視確認結果・未確定事項への回答を待つことを最優先にする方針へ
  切り替えた(candidate-longlist-draft.md第十九弾)。実店舗への連絡は一切行っていない。
- フェーズ(続き64): candidate-longlist-draft.mdの申し送り通り新規探索より優先度B候補の
  オーナー目視確認待ちを優先する方針に切り替えたが、確認結果自体は引き続きオーナー側の対応待ちで
  今回のセッションでは進展がないため、別系統で残っていたlanding-page-copy-draft.mdの「次のステップ
  候補」のうち未着手だった「LPコピーに対応するワイヤーフレーム(セクション配置・画像イメージ)の
  作成」に着手した。owner-settings-wireframe.mdと同様のテキストベースのワイヤーフレーム形式で、
  ヒーロー→課題提起→解決策・機能紹介→「いつものLINEのまま」→料金・トライアル→FAQの6セクションを
  モバイル1カラムでレイアウトし、各セクションの画像方針(LINEトーク画面モックアップを軸に統一)を
  整理した(landing-page-wireframe.md新規作成)。実際のHTML/CSS実装・画像制作・公開はスコープ外の
  まま次の課題として残した。
- フェーズ(続き65): 候補のオーナー目視確認待ち・未確定事項の回答待ちは引き続き進展がないため、
  これまで手薄だった技術設計側の残課題に着手した。json-output-retry-fallback.md(LLM応答の中身が
  不正な場合)・webhook-async-processing-design.md(Webhookイベントの重複受信・遅延)のいずれにも
  含まれていなかった、「LLM API/LINE Push API呼び出し自体が失敗する場合(タイムアウト・5xx・
  レート制限・ネットワーク断)」のハンドリング方針を新規設計した(api-call-failure-handling.md
  新規作成)。LLM呼び出し失敗はCloud Tasksの再試行に委ね最終失敗時のみ待機メッセージ+オーナー通知、
  LINE Push送信失敗は状態変更が既に確定済みのため全体再試行はせず即時1回リトライ+失敗時は
  オーナーへ即時通知、という役割分担を整理した。承認不要で着手できる範囲として、
  `SYSTEM_ESCALATION_REASONS`に`llm_unavailable`/`line_push_failed`を新規追加し
  (`prototype/engine.py`)、owner-settings-wireframe.mdの通知ログ集計画面にも表示対象として
  追記した。テスト2件追加・全133件パス、schema検証23件パスを維持。実際のCloud Tasks最大試行回数
  設定・LINE送信リトライの実装自体は実LLM/実LINE API接続(オーナー承認待ち)後の課題として残した。
- フェーズ(続き66): api-call-failure-handling.mdの「次のステップ候補」だった方針2(LINE Push API
  呼び出し失敗時)の実装に着手した。クラウド接続を伴わず机上テスト可能な範囲だったため、
  `prototype/cloud_function_process_event.py`の`LinePushClient`プロトコルに「送信失敗時は
  `LinePushDeliveryError`を送出する」契約を追加し、これまで16箇所に散らばっていた
  `self._push.send_message(...)`の直接呼び出しを、即時1回のみリトライ・それでも失敗すれば
  `NotificationLogAggregator`/`EscalationConsolidator`双方に`escalation_reason: "line_push_failed"`
  を記録してオーナーへ即時通知する`_send()`ヘルパーに集約した(例外は外へ伝播させず、Cloud Tasksに
  タスクを再実行させてhold/confirm等の状態変更を二重実行してしまうのを避ける設計)。テスト用に
  指定回数だけ送信失敗を模擬する`FlakyLinePushClient`スタブを新設し、(1)1回失敗後の即時リトライで
  成功、(2)リトライも失敗しline_push_failedを記録、(3)短時間に複数回発生した場合もログへの記録は
  都度行われることを確認するテスト3件を追加(全136件パス)。残る方針1(LLM呼び出し失敗時にCloud
  Tasksの最大試行回数超過を検知する経路)は実クラウド環境が前提のため引き続き未着手のまま残った。
- フェーズ(続き67): customer-reply-detection-design.mdの「残る課題」に残っていた、confirmed状態
  からの`new_booking` intentが「別日の再訪希望」か「リマインドへの相槌」かの判別未整理に対応した。
  llm-system-prompt-draft.mdに厳守事項11を新設し、「また」「今度」等の語だけでは`new_booking`と
  判定せず、(a)明確な予約要求の言い回し、または(b)独立した具体的日時の言及、のいずれかが
  なければ9b(雑談)として扱う基準を明文化した。conversation-samples-test-cases.mdにE18
  (社交辞令ケース/再訪希望ケースの2パターン)を追加し、schema/validate_test_cases.pyのフィクスチャ
  にも反映(全25件パス)。バックエンド側の`_start_new_booking()`分岐自体は変更していないため、
  プロンプト通りに実LLMが安定分類できるかは実LLM検証(オーナー承認待ち)で確認する必要がある。
- フェーズ(続き68): reminder-scheduler-design.mdの「未解決のまま残る課題」に残っていた、
  Cloud Scheduler起動間隔(暫定15分)がCloud Functions実行回数課金に与える影響を試算した
  (cloud-scheduler-invocation-cost-estimate.md新規作成)。Cloud Function Cは単一Schedulerから
  起動され店舗数に依存しないため、15分間隔でも月2,880回程度にとどまり、GCP Cloud Functions
  無料枠(月200万回)の0.15%程度で無視できる規模と結論。起動間隔の選定は課金額ではなく
  リマインド送信の目標時刻からの最大遅延許容度を基準に決めてよいことを確認した。実際の
  Cloud Schedulerジョブ作成・課金自体は引き続きオーナー承認待ち。
- フェーズ(続き69): precheck-strengthening.mdの「次のステップ候補」に残っていた、MVP
  ターゲット業種ごとの「常連客」の定義(来店回数の閾値)をヒアリングで確認する設問の追加に
  着手した。customer-interview-design.mdにF.常連客の定義に関する質問(Q17)を新設し、
  質問総数を16問→17問に更新。interview-rehearsal-script.mdの時間配分・任意設問の優先順位
  (時間不足時はE.より先にF.を聞く)にも反映した。常連客の実際の閾値定義自体は引き続き
  ヒアリング結果が得られるまで未確定のまま。
- フェーズ(続き70): precheck-strengthening.mdでMVP採用した案A(無断キャンセル歴のない常連客への
  確認メッセージ簡略化)を実際に動かすための店舗側設定欄が、これまでowner-settings-wireframe.mdに
  存在しないという抜け漏れを発見し対応した。営業情報設定ページに「常連客とみなす来店回数」欄
  (既定値3回)を新設し、判定には顧客詳細ページの既存項目「累計予約数」「無断キャンセル確定数」を
  そのまま流用する設計とした。既定値の3回はcustomer-interview-design.mdのQ17ヒアリング結果が
  得られるまでの暫定値であり、業種別に見直す余地を残す。候補探索のcandidate-longlist-draft.mdで
  申し送られていた「回答待ちの間は承認不要な既存ドキュメントの整合性確認に振り向ける」方針に
  沿った作業。
- 最終更新: 2026-08-04 07:00 UTC

## ドキュメント
- data-retention-policy.md: 永続データストア側(予約実績・会話履歴・通知ログ)の個人情報
  保存期間・削除方針(2026-08-03 02:00 UTC新規作成。予約実績3年・アーカイブ済み会話履歴
  archivedAtから1年・通知ログ6か月を暫定値として設定。削除実行の実装は今後の課題)
- ci-setup.md: GitHub Actionsによるテスト自動実行の導入経緯(2026-08-02 20:00 UTC新規作成。
  `.github/workflows/line-reservation-ai-tests.yml`でprototype/の自動テスト4本(125件)と
  schema/validate_test_cases.py(22件)を自動実行。アカウント作成・支払い・公開に該当しないため
  承認不要と判断。2026-08-02 21:00 UTC追記: GitHub MCPツールで実際のワークフロー実行結果
  (run id: 30764705150)を確認し`conclusion: success`(全件パス)を確認済み)
- system-event-log-gap-fix.md: NotificationLogAggregatorのシステム内部イベント
  (booking_conflict/booking_cancelled/cancel_not_found/booking_change_started/
  change_not_found/candidate_selection_unresolved)記録ギャップの原因(配線漏れ+
  record()の分類条件の不備)と修正内容(2026-08-02 19:00 UTC新規作成)
- single-item-faq-schema-decision.md: 単一項目FAQ(faq_segmentsがnullのケース)でも
  自動返信できるようにするスキーマ変更の要否検討(2026-08-02 14:00 UTC新規作成。
  厳守事項9aに基づくfaqは単一項目でもfaq_segmentsを1要素配列で必ず付与する方針を採用。
  9b雑談・escalationは対象外のまま)
- market-research.md: 市場調査・競合整理
- tech-stack.md: 技術構成案
- conversation-flow.md: 顧客⇄AIの会話フロー草案(新規予約・キャンセル・曖昧な日時のすり合わせ)
- double-booking-prevention.md: 二重予約防止ロジック設計(仮押さえ→確定の2段階方式)
- owner-settings-wireframe.md: オーナー向け簡易設定画面のワイヤーフレーム(営業情報・メニュー・予約一覧・顧客詳細ページ・店舗FAQ情報入力欄・通知ログ集計画面、2026-08-01 08:00 UTC更新。通知ログ集計画面に「システム内部イベント」欄を追加(booking_conflict等を一般相談と別枠で表示))
- line-api-pricing.md: LINE Messaging APIの料金プラン・無料枠の調査結果(2026-07-29時点)
- pricing-plan.md: 本サービスの月額サブスク料金プラン案・無料トライアル条件の仮決め(2026-07-30時点)
- customer-interview-design.md: 想定顧客(美容室等)へのヒアリング項目・実施方法の設計(2026-07-30時点、全16問。デポジット機能への需要確認設問(E.)を追加済み。実施自体は未承認)
- pending-timeout-ux.md: 仮押さえ〜タイムアウト時の顧客向け待機・催促・解除メッセージ文言設計(2026-07-30時点)
- tone-and-manner-guideline.md: 顧客接点メッセージ全体の統一トーン&マナールール、確定メッセージ・前日リマインド文言案(2026-07-30時点)
- reminder-timing-and-resend-rules.md: 前日リマインドの送信タイミング決定ロジック、未読時の再送(当日朝1回のみ)ルール設計(2026-07-30時点)
- no-show-handling.md: 無断キャンセル(ノーショー)発生時の検知条件・オーナー向け記録・通知設計(2026-07-30時点)
- precheck-strengthening.md: 無断キャンセル履歴を踏まえた予約時の事前確認強化の要否検討(2026-07-30時点、常連客簡略化とオーナー向け注意書きのみ採用)
- deposit-payment-research.md: 事前決済(デポジット)機能を将来オプション化する場合の技術要件・決済手数料概算調査(2026-07-30時点、MVPには含めずオプション候補として設計のみ)
- interview-rehearsal-script.md: ヒアリング(16問)が15分に収まるかを事前検証するための読み上げ台本・時間配分・チェックリスト(2026-07-30時点)
- line-price-revision-2026-check.md: 2026年10月予定のLINE公式アカウント料金改定の内容をweb調査で再確認(2026-07-30時点、本サービスの料金プラン前提への影響は軽微と判断)
- interview-candidate-selection-criteria.md: ヒアリング対象候補(実店舗)の選定基準・情報源の整理(2026-07-30時点、選定"方法"の設計のみで実店舗の特定・連絡は未実施)
- initial-contact-message-draft.md: ヒアリング協力依頼の初回コンタクト文面草案(メール/LINE/電話用、2026-07-30時点。草案作成のみで実在店舗への送信・連絡は未実施。謝礼有無等の未確定事項あり)
- candidate-buffer-analysis.md: 業種ごとの候補数の妥当性・チャネル別想定承諾率・追加候補確保のトリガー基準の試算(2026-07-30時点、一般論に基づく仮の目安。実測値ではない)
- llm-system-prompt-draft.md: 会話フロー・二重予約防止・トーン&マナー・保留タイムアウト・無断キャンセル対応等の既存設計を統合した、LLM会話エンジン向けシステムプロンプト草案(2026-08-04 04:00 UTC更新、厳守事項11を新設し、confirmed状態からの返信で「また」「今度」等の語だけではnew_bookingと判定せず、明確な予約要求の言い回しか独立した具体的日時の言及がなければ9b雑談扱いとする基準を追加。customer-reply-detection-design.mdの残課題への対応。実装・実LLM検証は未着手)
- json-output-retry-fallback.md: 構造化出力(JSON)がパース失敗・スキーマ不一致・矛盾を起こした場合のリトライ(1回まで)・フォールバック(安全側判定でオーナー通知に転送)方針の設計(2026-07-31 09:59 UTC更新、任意フィールド`escalation_reason`/`feature_hint`のスキーマ不一致も既存の「2. キー不足/余分」判定に含めつつ、分類用メタデータのため不正時も`needs_owner_check`によるオーナー通知は止めず「分類不能」へフォールバックする方針を追記。実装・動作検証は未着手)
- conversation-samples-test-cases.md: LLMシステムプロンプト草案・JSONリトライ設計を検証するための会話サンプル(正常系4件・崩れ系18件)のテストケース設計(2026-08-04 04:00 UTC更新、厳守事項11の判定基準を検証するE18(社交辞令ケース/再訪希望ケースの2パターン)を追加。机上設計のみで実LLM検証は未着手)
- json-schema-multi-intent-extension.md: E13で発見した「1応答内でintentが項目ごとに混在しうる」課題への対応として、構造化出力(JSON)に任意フィールド`faq_segments`(topic/resolved)を追加するスキーマ拡張案(2026-07-31 11:58 UTC更新、未検証事項だった「3項目以上でも破綻しないか」をE16で机上検証済みと反映。トップレベルのintentは単一値のまま維持し「1応答=1 JSON」前提は崩さない設計。実装・実LLM検証は未着手)
- faq-escalation-boundary.md: 厳守事項9(FAQ/雑談)と6(予約以外の相談エスカレーション)の境界線整理(2026-07-30 19:58 UTC更新、営業時間等の店舗登録済み静的情報は9a、未登録・個別判断が必要な相談は6番に振り分け。owner-settings-wireframe.md側のFAQ入力欄の有無を確認し追加済み。llm-system-prompt-draft.mdの厳守事項9a説明文への反映は2026-07-30 20:58 UTC時点で反映済み)
- faq-response-templates.md: 厳守事項9aの回答テンプレート(住所・アクセス/駐車場/支払い方法の項目別穴埋め式文面、未登録時のエスカレーション定型文、複合質問の分割送信例、2026-07-30 22:58 UTC時点。システムプロンプト・テストケースへの反映は未着手)
- escalation-notification-templates.md: 厳守事項6(医療・料金・クレーム・未登録FAQ相談)・10(未実装機能問い合わせ)発生時のオーナー向け通知文面と、faq_segments一部未解決時の通知文面の設計(2026-07-31時点。即時通知を基本方針とし、連続エスカレーション集約ロジックはescalation-consolidation-logic.mdで具体設計済み)
- escalation-consolidation-logic.md: 連続エスカレーション(同一顧客が短時間に複数回)を1通に集約する通知ロジックの設計(2026-07-31 06:58 UTC更新。時間窓5分固定、初回は即時個別通知+ウィンドウ内の追加分はまとめ通知の2段階方式。件数3件以上は優先確認を促す一文を追加。医療相談(6-a)も例外なくウィンドウ方式を適用する結論を追加、再発火3回目で都度通知に切り替え+30分途絶えでリセットする上限ルールを追加。実装方式は概念メモのみで技術選定は未着手)
- owner-settings-wireframe.md: 「通知ログ集計画面」を追記(2026-07-31 05:57 UTC更新。未登録FAQ相談・未実装機能問い合わせ・その他エスカレーションの件数を直近30日で俯瞰する読み取り専用ページ。営業情報設定ページからの導線のみとし常設メニューには出さない方針。MVPはスプレッドシートのCOUNTIF/ピボット集計で代替)
- notification-log-classification-labels.md: 通知ログ集計画面で「未実装機能問い合わせ件数」を独立集計するための分類ラベル設計(2026-08-01 08:00 UTC更新。システム内部イベント(booking_conflict/candidate_selection_unresolved)をbooking_output.schema.jsonのenumに追加せず、通知ログ集計側の別枠(system_event_counts)で扱う方針を決定・追記。構造化出力に任意フィールド`escalation_reason`(consultation/unimplemented_feature)と補助フィールド`feature_hint`を追加する案、境界ケースをE14・E15としてconversation-samples-test-cases.mdに反映済み。duplicate-topic-notification-log-rule.mdの結論を踏まえた具体的な集計手順(resolvedフィルタ→(日付,userId,topic)ユニーク化→件数集計)を確定・追記。実LLM検証は未着手)
- duplicate-topic-notification-log-rule.md: E16で判明した「同一topicが複合質問内で重複しうる」点を踏まえた、通知ログ集計画面での重複topicカウントルールの設計(2026-07-31 16:58 UTC更新。`resolved: false`のセグメントに絞りユニークなtopic数でカウントする方針に加え、複数応答・複数日にまたがる重複は日次×userId×topicでユニーク化する方式を結論化。残っていた未検討事項(LINE以外のチャネル追加時のuserId代替識別子の設計)はchannel-agnostic-session-id.mdで結論化済み)
- channel-agnostic-session-id.md: 将来Web版チャット等の非LINEチャネルを追加する場合に備えた代替顧客識別子の設計方針(2026-07-31新規作成。恒久的な名寄せIDの導入は見送り、チャネルごとに独立したセッションID(30分無応答失効)を発行する方針。通知ログ集計・連続エスカレーション集約への適用方法も整理。実装は非LINEチャネル追加が具体化した時点で着手)
- schema/booking_output.schema.json: 構造化出力(intent/faq_segments/escalation_reason等)を統合したJSON Schema(draft-07、2026-07-31 22:58 UTC更新、AvailabilitySearcher連携用の任意フィールド`requested_date_range`/`time_of_day_preference`を追加。既存フィクスチャは両フィールドとも省略可能なため無影響。実装未着手)
- schema/validate_test_cases.py: 外部ライブラリ非依存の簡易JSON Schemaバリデータ。conversation-samples-test-cases.mdの期待JSON出力を机上検証する(2026-08-04 04:00 UTC更新、E18の2フィクスチャ(E18_social_remark/E18_rebooking_request)を追加し25件に拡充、全件パスを確認。実LLM呼び出しはなし)
- schema-validation-report.md: 上記バリデータによる机上検証結果(2026-07-31 14:58 UTC更新、N3・N4・E1・E3・E4・E7・E8を追加した22件全件パス)と、実LLM検証に向けた次の課題の整理
- prototype/engine.py: リトライ/フォールバック(json-output-retry-fallback.md)・連続エスカレーション集約通知(escalation-consolidation-logic.md)・通知ログのユニーク集計(duplicate-topic-notification-log-rule.md等)・仮押さえ→確定の2段階予約枠管理(double-booking-prevention.md、`BookingSlotManager`)・候補提示→確定の会話フロー状態遷移(conversation-flow.md、`ConversationFlowStateMachine`)・空き枠検索(slot-search-component-design.md、`AvailabilitySearcher`)・候補一覧の採番提示と顧客返信からのslot_key特定(candidate-presentation-and-selection-design.md、`resolve_candidate_selection()`)を実装した実行可能なPythonプロトタイプ(2026-08-01 12:00 UTC更新。`SYSTEM_ESCALATION_REASONS`定数と`NotificationLogAggregator.system_event_counts`/`system_event_total()`を新規追加し、booking_conflict等のシステム内部イベントを一般相談件数と別枠で集計できるようにした。`weekday_business_hours`の0分間区間(定休日相当)が`BusinessHoursConfigError`で拒否されることを確認するデモアサーションを追加。実LLM呼び出しはスタブのまま。2026-08-01 14:00 UTC更新、`release_idle_conversations()`の戻り値を`user_id`のみのリストから、失効時の`stage`も併せ持つ`ReleasedConversation`のリストへ変更し、将来`candidates_presented`失効時のみ能動通知するオプション機能を追加する際にフィルタしやすい形にした。デモに`candidates_presented`のまま失効したケースを追加。2026-08-01 19:00 UTC更新、message-tone-variants.mdのトーン変換を`_render_by_tone()`という共通ディスパッチャとして実装し、`format_confirmation_message()`(LLM出力起点)・`format_reminder_message()`(スケジューラ発火起点)・`format_hold_message()`・`format_faq_parking_message()`の4関数から呼び出す設計とした。未知のtone値はstandardへフォールバック。デモにフォーマル/カジュアル双方の出力例を追加。2026-08-02 01:00 UTC更新、`search_candidates_from_llm_output()`に`MAX_SEARCH_RANGE_DAYS`(暫定14日)によるレンジクランプを追加)
- prototype-engine-design.md: engine.py実装にあたって新たに確定させた実装判断(5分ウィンドウの起点固定方式等)と今後の課題の整理(2026-07-31 17:58 UTC新規作成)
- booking-slot-manager-design.md: double-booking-prevention.mdの仮押さえ→確定2段階管理をprototype/engine.pyの`BookingSlotManager`クラスとして実装した際の設計メモ(2026-07-31 18:58 UTC新規作成。確定操作自体の競合時のpending差し戻し+オーナー通知は呼び出し側実装時の課題として明記)
- conversation-flow-state-machine-design.md: conversation-flow.mdの「候補提示→確定」をBookingSlotManagerに接続するprototype/engine.pyの`ConversationFlowStateMachine`クラスの設計メモ(2026-08-01 08:00 UTC更新。確定競合時は「pending差し戻し」ではなく「オーナー通知のみ」に設計変更した理由を整理。残課題だったescalation_reason='booking_conflict'のスキーマ未反映は、システム内部イベント用の別集計軸(system_event_counts)を新設する方針で解消済み)
- intent-to-flow-mapping.md: LLM構造化出力(intent/datetime_candidate/confirmed等)からConversationFlowStateMachineのselect_slot()/provide_details()をどのタイミングで呼び出すかの対応表(2026-08-01 00:00 UTC更新。`search_candidates_from_llm_output()`実装に伴い対応表を更新。残課題を「提示した候補一覧から顧客の返信に対応するslot_keyを1件特定する処理」に更新。同課題はcandidate-presentation-and-selection-design.mdで対応済み)
- slot-search-component-design.md: datetime_candidate(自然文)から具体的なslot_keyを算出する空き枠検索コンポーネントの設計(2026-08-02 01:00 UTC更新。`requested_date_range`に上限がなかった問題への対応として`MAX_SEARCH_RANGE_DAYS`(暫定14日)によるクランプを追加したことを反映)
- candidate-presentation-and-selection-design.md: 候補一覧の採番提示文言(番号付きリスト)と、顧客の返信(番号/漢数字/丸数字/自然文)からslot_keyを1件特定する`resolve_candidate_selection()`の設計(2026-08-01 08:00 UTC更新。6節の残課題だったescalation_reason='candidate_selection_unresolved'のスキーマ未反映を、システム内部イベント用の別集計軸(system_event_counts)を新設する方針で解消。再確認ループの上限(`RECONFIRM_MAX_ATTEMPTS`=2)・エスカレーション切り替え設計、誤爆防止のため番号指定が明確なパターンのみ数字と解釈する設計は既存のまま)
- candidate-label-weekday-fix.md: 候補ラベルへの曜日表示追加(`8/9` → `8/9(土)`、tone-and-manner-guideline.mdとの表記統一)と、これに伴う`_label_date_and_time_in_reply()`の回帰修正(2026-08-01 04:00 UTC新規作成)
- conversation-state-cleanup.md: candidate-presentation-and-selection-design.md 6節の残課題だった、エスカレーション後に顧客が無応答のまま会話が終了した場合の会話状態クリーンアップ(タイムアウト解放)の設計(2026-08-01 05:00 UTC新規作成。`_ConversationState`に`last_activity_at`を追加し、無応答30分(`CONVERSATION_IDLE_TIMEOUT`、channel-agnostic-session-id.md等と時間感覚を統一)で失効させる`release_idle_conversations()`をprototype/engine.pyに実装。awaiting_detailsで無応答離脱した場合は枠のholdも明示解放、confirmed済み状態は前日リマインド等での参照用に対象外とする方針、デモで動作確認済み。エスカレーション通知は送らない方針(無応答離脱は日常的に発生するため通知過多を避ける))
- availability-closed-weekday-support.md: AvailabilitySearcherのMVP制約のうち定休日対応の設計・実装メモ(2026-08-01 07:00 UTC新規作成。`closed_weekdays`パラメータ追加、owner-settings-wireframe.mdの営業曜日チェックボックスに対応。曜日別営業時間は引き続きスコープ外。祝日・臨時休業の特定日付対応は2026-08-02 22:00 UTCにad-hoc-closed-dates-support.mdへ分離して解消)
- ad-hoc-closed-dates-support.md: availability-closed-weekday-support.mdの残課題だった祝日・臨時休業(特定日付単発の休業)対応の設計・実装メモ(2026-08-03 00:00 UTC更新。`closed_dates`パラメータ追加、`closed_weekdays`と独立かつ併用可能。reminder_scheduler.py側の同様対応(2026-08-02 23:00 UTC実装済み)に続き、owner-settings-wireframe.mdへの入力UI追記(2026-08-03 00:00 UTC)も完了。残る課題は入力欄の過去日付・重複日付バリデーション設計のみ)
- weekday-specific-business-hours.md: AvailabilitySearcherのMVP制約のうち曜日別営業時間(例: 土曜だけ短縮営業)対応の設計・実装メモ(2026-08-01 12:00 UTC更新。`weekday_business_hours`パラメータ追加、owner-settings-wireframe.mdに「曜日ごとに営業時間を変える」トグルを追加。定休日設定との二重表現の懸念は、business-hours-lunch-break.mdの区間バリデーションが0分間区間を既に拒否するため解消済みと確認。残課題は解消済み)
- business-hours-lunch-break.md: AvailabilitySearcherのMVP制約のうち昼休憩など1日複数営業時間帯(例: 9:00-12:00, 15:00-19:00)対応の設計・実装メモ(2026-08-01 11:00 UTC更新。`business_hours`/`weekday_business_hours`が単一区間タプルと区間リストの両方を受け付けるよう`_normalize_business_hour_ranges()`で正規化し、`find_candidates()`を区間ごとにスキャンする三重ループへ変更。owner-settings-wireframe.mdに「+ 休憩時間を追加」を追加。区間の重複・逆転バリデーションを追加し`BusinessHoursConfigError`を送出するようにした(残課題を解消))
- idle-conversation-trigger-design.md: release_idle_conversations()/archive_completed_conversations()の実行トリガー設計(2026-08-01 13:00 UTC新規作成。専用スケジューラ・Webhook便乗・外部cronサービスの3案を比較し、追加インフラ不要で今すぐ実装できるWebhook便乗案を採用。全リクエスト毎回全件スキャンを避けるための最小実行間隔5分での間引き方式を設計。`ConversationFlowStateMachine.maybe_run_idle_cleanup()`/`maybe_run_archive()`として実装・デモ確認済み)
- candidates-expired-notification-design.md: conversation-state-cleanup.md 6節の残課題だった、`candidates_presented`失効時に「候補が期限切れになりました」等のメッセージを能動送信すべきかの検討(2026-08-01 14:00 UTC新規作成。プッシュメッセージ課金・送信タイミングの唐突さ・実測データ不在を理由にMVPでは送らない方針(現状維持)を採用。将来切り替えやすいよう`release_idle_conversations()`の戻り値をstage付きの`ReleasedConversation`に変更、送信文言案も記載)
- message-tone-variants.md: tone-and-manner-guideline.md・faq-response-templates.mdで共通の未検証事項だった「メッセージトーン(カジュアル/standard/フォーマル)」の出し分けルールの設計(2026-08-01 19:00 UTC更新。「仮押さえ」「確定」等の固定語彙・日付時刻表記・FAQ登録値は3トーン共通で不変とし、語尾の丁寧度・絵文字・感嘆符の3点のみをトーンに応じて機械的に置き換える方式を採用。確定メッセージ・前日リマインド・仮押さえ案内・FAQ回答テンプレートの3トーン別文例を作成し、owner-settings-wireframe.mdの営業情報設定ページに「メッセージトーン」選択欄を追加した。前日リマインド(スケジューラ発火起点)とその他(LLM出力起点)の2経路でトーン変換を共通関数化できるかの検討・実装(prototype/engine.pyの`_render_by_tone()`)が完了。実LLM検証は未着手)
- automated-test-suite.md: prototype/engine.pyの主要ロジックを`unittest`ベースの自動テストスイート(prototype/test_engine.py)として整理した経緯・カバー範囲のまとめ(2026-08-01 20:00 UTC新規作成。31件全件パス確認済み)
- prototype/test_engine.py: prototype/engine.pyの自動テストスイート(標準ライブラリのみ、追加依存なし)。`python3 -m unittest test_engine -v`で実行可能(2026-08-01 20:00 UTC新規作成)
- hosting-platform-selection.md: ホスティング基盤(GCP Cloud Functions・AWS Lambda・Cloudflare Workers・Fly.io等)の比較・選定(2026-08-01 21:00 UTC新規作成。Python資産の流用可否・低トラフィック時コスト・状態ストアとの相性・運用の手軽さで比較し、GCP Cloud Functions (Python) + Firestoreを第一候補に決定。実際のアカウント・プロジェクト作成は着手時に別途オーナー承認が必要)
- firestore-data-model.md: Firestoreのコレクション設計(2026-08-01 22:00 UTC新規作成。会話状態・予約枠・通知ログ・エスカレーション集約窓の4系統をengine.pyの既存クラス(BookingSlotManager等)に対応付け。通知ログのユニーク集計はcount()集約クエリで実現する案を採用。実装・課金試算は未着手)
- firestore-transaction-design.md: hold()/confirm()・escalationWindows更新をFirestoreトランザクションに置き換える実装方針の設計(2026-08-01 23:00 UTC新規作成。`@firestore.transactional`によるread-modify-writeの疑似コード、flush_due_windows()横断クエリ用の`queuedCount`フィールド併設・複合インデックス要件を整理。実クライアント接続はGCPプロジェクト作成後の課題として残置)
- firestore-traffic-cost-estimate.md: 想定トラフィック(pricing-plan.mdの3プラン、月間予約50/150/300件)でのFirestore読み書き回数・Sparkプラン無料枠(読み取り5万回/日・書き込み2万回/日)との比較試算(2026-08-02 02:00 UTC更新。MAX_SEARCH_RANGE_DAYS=14日クランプ時のワーストケースを新規節で数値化し、無料枠内に収まる店舗数の目安をプロプラン相当で約130店舗→約32店舗に下方修正。実際の検索レンジ分布はヒアリングで未確認のため残課題)
- landing-page-copy-draft.md: market-research.md・pricing-plan.md・tone-and-manner-guideline.mdを踏まえた、
  サービス紹介ランディングページ(LP)のコピー草案(2026-08-02 03:00 UTC新規作成。ヒーロー・課題提起・
  機能紹介・「新しいアプリはいらない」訴求・料金トライアル・FAQの各セクションを作成。LP公開自体は
  「公開」に該当するためオーナー承認後の課題として残置。AI利用の開示表示義務の要否は法的確認が必要な
  未検証事項として残る)
- landing-page-wireframe.md: landing-page-copy-draft.mdのコピー草案に対応するLPワイヤーフレーム
  (2026-08-04 01:00 UTC新規作成。owner-settings-wireframe.mdと同様のテキストベース形式で
  ヒーロー〜FAQの6セクションをモバイル1カラムでレイアウト。画像はLINEトーク画面モックアップを軸に
  統一する方針。HTML/CSS実装・画像制作・公開はスコープ外)
- webhook-async-processing-design.md: hosting-platform-selection.mdの残課題だった、Cloud Functions
  Webhookハンドラの応答遅延対策の設計(2026-08-02 08:00 UTC更新。即時ACK+Cloud Tasksによる
  非同期処理+LINEプッシュメッセージAPIでの応答という2段構成を採用。reply APIは使わない方針。
  重複排除キーには`webhookEventId`(ULID)を採用でき、`deliveryContext.isRedelivery`による
  早期スキップも追加可能と判明(web調査済み)。Cloud Tasksの実導入は今後の課題(GCPプロジェクト
  作成後、オーナー承認待ち))
- webhook-function-a-implementation.md: Cloud Function A(receive_webhook)のハンドラコード実装の
  経緯・カバー範囲まとめ(2026-08-02 09:00 UTC新規作成。`prototype/cloud_function_webhook.py`・
  `prototype/test_cloud_function_webhook.py`(17件全件パス)を新規作成。Cloud Function Bは
  実LLM呼び出し承認待ちのため未着手)
- webhook-function-b-implementation.md: Cloud Function B(process_conversation_event)のうち
  実LLM呼び出し・実クラウド接続とは切り離せる配線ロジックの実装経緯・カバー範囲まとめ
  (2026-08-02 10:00 UTC新規作成。`prototype/cloud_function_process_event.py`・
  `prototype/test_cloud_function_process_event.py`(12件全件パス)を新規作成。
  escalation/faq intentの顧客向け返信・確定競合時の新候補再提示は未実装のまま残置)
- legal-notices-draft.md: landing-page-copy-draft.mdの残課題だった特定商取引法に基づく表記・
  プライバシーポリシーの文面草案(2026-08-02 05:00 UTC更新。事業者名・所在地等は
  `【要記入】`のプレースホルダー。プライバシーポリシーはLINE連携で取得する情報・LLM API
  プロバイダへの送信・保存期間を整理。所在地表示要否とAI利用開示要否について、法的助言に
  あたらない範囲でweb調査による一般的な傾向整理を追記(特商法上は役務提供契約も表示義務対象と
  なりうること、AI対応開示の一般義務化法令は現状見当たらないこと等)。最終判断は引き続き
  法律専門家への確認が必要な事項として残置。作成は草案のみでLP掲載・公開は未着手)
- faq-escalation-customer-reply-implementation.md: webhook-function-b-implementation.mdの
  残課題だったescalation/faq intentの顧客向け返信(faq_segmentsとの統合)の実装経緯まとめ
  (2026-08-02 11:00 UTC新規作成。複合FAQ(faq_segments付与時)は項目ごとにテンプレート回答、
  escalation intentは共通保留文言を即時送信。単一項目FAQ(faq_segmentsがnull)は自動返信でき
  ない制約が残った旨を明記)
- booking-conflict-candidate-representation.md: webhook-function-b-implementation.mdの
  残課題だった確定操作競合時の新しい空き枠の再提示の実装経緯まとめ(2026-08-02 12:00 UTC
  新規作成。初回検索条件をキャッシュして`now`時点で再検索し、奪われた枠を除いた候補を
  その場で再提示。検索条件が無い/候補0件の場合は謝罪文言のみのフォールバックを維持)
- reminder-scheduler-design.md: README「次にやること」の残課題(c)だった前日リマインド
  経路の呼び出し元の設計(2026-08-02 13:00 UTC新規作成。Cloud Function C(send_reminders)
  を単一Cloud Scheduler(暫定15分間隔)でトリガーし、`reminder-timing-and-resend-rules.md`の
  目標送信時刻(店舗設定 or 営業終了1時間前・20:00上限)を過ぎた未送信予約を抽出する方式を
  採用。厳密な時刻一致ではなく「未送信・目標時刻超過・予約日未到来」の3条件のみで判定する
  ことでスケジューラの実行間隔・遅延に自然に追いつける冪等設計とした。判定ロジックを
  `prototype/reminder_scheduler.py`(`compute_initial_reminder_target()`/
  `should_send_initial_reminder()`/`select_due_initial_reminders()`/
  `select_due_resends()`)として実装し、テスト21件全件パス。firestore-data-model.mdに
  `reminderSentAt`等4フィールドを追記。残課題は確定後の顧客返信検知(`customerRepliedAt`)の
  配線設計、実Cloud Scheduler/LINE Push実送信(オーナー承認待ち))
- customer-reply-detection-design.md: reminder-scheduler-design.mdの残課題だった確定後の
  顧客返信検知(`customerRepliedAt`)の配線設計(2026-08-02 15:00 UTC新規作成。返信内容の
  解釈はせず「confirmed状態の会話へメッセージが届いた事実」自体を記録する方針とし、
  Cloud Function B(`process()`冒頭、LLM呼び出し・intent判定より前)で
  `ConfirmedReplyRecorder`プロトコル(LinePushClient等と同じDIパターン)経由で記録するよう
  `prototype/cloud_function_process_event.py`に実装。複数回返信時は毎回最新時刻で上書き。
  テスト4件追加・全95件パス。2026-08-04 04:00 UTC追記: 残課題のうちcancel/change intentの実処理は
  その後cancel-intent-handling-design.md・change-intent-handling-design.mdで対応済み。
  confirmed状態からのnew_booking intentが再訪希望か相槌かの内容判別も、
  llm-system-prompt-draft.mdの厳守事項11としてプロンプトレベルの判定基準を新設して対応した
  (実LLM検証は未着手)。残る課題はFirestore書き込み自体の実装のみ)
- cancel-intent-handling-design.md: README「次にやること」の残課題だったcancel/change intentの
  実処理のうち、`cancel`(顧客都合でのキャンセル申し出)のみを対象に設計・実装(2026-08-02 16:00 UTC
  新規作成。`change`は「キャンセル+新規予約」より複雑な状態遷移を要するため次回以降の課題として
  スコープ外に。会話のstage(状態なし/candidates_presented/awaiting_details/confirmed)に応じて
  `BookingSlotManager`側の枠解放・顧客への返信文言の出し分け・オーナー通知(confirmed分のみ、
  外部予約記録の更新が必要なため)を行う`ConversationFlowStateMachine.cancel_booking()`を新設し、
  `prototype/cloud_function_process_event.py`のintent振り分けに接続。`escalation_reason`に
  `booking_cancelled`/`cancel_not_found`を追加(`SYSTEM_ESCALATION_REASONS`)。テスト12件追加・
  全107件パス)
- api-call-failure-handling.md: json-output-retry-fallback.md(LLM応答の中身が不正な場合)・
  webhook-async-processing-design.md(Webhookイベントの重複受信・遅延)のいずれにも含まれていなかった、
  LLM API/LINE Push API呼び出し自体の失敗(タイムアウト・5xx・レート制限・ネットワーク断)時の
  ハンドリング方針を新規設計(2026-08-04 02:00 UTC新規作成)。LLM呼び出し失敗はCloud Tasksの
  再試行に委ね最終失敗時のみ待機メッセージ+オーナー通知、LINE Push送信失敗は状態変更(hold/confirm等)
  が既に確定済みのため全体再試行はせず即時1回リトライ+失敗時はオーナーへ即時通知、という役割分担を
  整理。`SYSTEM_ESCALATION_REASONS`に`llm_unavailable`/`line_push_failed`を追加し
  (`prototype/engine.py`)、owner-settings-wireframe.mdの通知ログ集計画面にも表示対象として反映。
  テスト2件追加・全133件パス。実装(Cloud Tasks最大試行回数設定・LINE送信リトライ自体)は
  実LLM/実LINE API接続(オーナー承認待ち)後の課題として残った。2026-08-04 03:00 UTC追記:
  上記のうち方針2(LINE Push送信失敗)はクラウド接続なしで机上テスト可能な範囲だったため実装した。
  `prototype/cloud_function_process_event.py`に、送信失敗時`LinePushDeliveryError`を送出する契約の
  `LinePushClient`プロトコルと、全16箇所のpush送信呼び出しを集約した`_send()`ヘルパー(即時1回のみ
  リトライ、それでも失敗すれば`line_push_failed`を記録しオーナーへ即時通知、例外は外へ伝播させず
  状態変更の二重実行を回避)を追加。テスト用`FlakyLinePushClient`スタブと検証テスト3件を追加
  (全136件パス)。方針1(LLM呼び出し失敗)はCloud Tasksの実試行回数検知が実クラウド環境前提のため
  引き続き未着手のまま残った。
- change-intent-handling-design.md: cancel-intent-handling-design.mdの残課題だった`change`
  (日時変更)の実処理を設計・実装(2026-08-02 17:00 UTC新規作成)。`cancel_booking()`と同じ
  分岐(stageに応じたrelease()・confirmed分のみオーナー通知)を行う
  `ConversationFlowStateMachine.change_booking()`を新設し、cancelと異なり会話を終了させず、
  `_start_new_booking()`(new_bookingと同じ新規候補検索・present_candidates())へそのまま
  接続する設計(「変更 = 旧予約の解放 + 新規予約フローの開始」)。booking_output.schema.jsonが
  `requested_date_range`/`time_of_day_preference`を元々`change`でも使える設計にしていたため
  スキーマ変更は不要だった。`escalation_reason`に`booking_change_started`/`change_not_found`を
  追加(`SYSTEM_ESCALATION_REASONS`)。`prototype/cloud_function_process_event.py`に
  `_handle_change()`を新設しintent振り分けに接続。テスト13件追加・全117件パス)

## 次にやること(候補)
- 上記「ヒアリング依頼提示パッケージ」(interview-request-package.md)で整理した未確定事項
  (謝礼有無・送信者名表記・返信先連絡先・優先度B5件の依頼可否)についてオーナーの回答を待つ。
  回答が得られるまでは、実在店舗・個人事業主への実際の連絡・送信は行わない。
- (解消済み 2026-08-04 00:00 UTC: 前項で「余力があれば」としていたホットペッパービューティー内
  キーワード経由での美容室第五候補探索に着手したが、新規候補は0件だった(同名多店舗の「Ohana」を
  発見したが東京都内対象店舗を一意特定できず候補化見送り)。美容室・パーソナルジムの新規開拓が
  5回連続不調に終わったため、新規探索は費用対効果が逓減していると判断し打ち切り、オーナーの回答
  (未確定事項・優先度B候補の目視確認結果)を待つことを最優先方針に切り替えた
  (candidate-longlist-draft.md第十九弾参照))
- (解消済み 2026-08-03 23:00 UTC: 前項で申し送っていた美容室第四候補探索(Instagram軸)に着手したが、
  新規候補は0件だった。「美容室 個人経営 1人サロン 東京 Instagram」等3パターンで検索したが、
  ポータル一覧・Instagram予約機能解説記事・独立開業ノウハウ記事ばかりが上位を占め、候補17(aane hair)
  発見時のような個別サロン名の紹介記事には行き着かなかった。候補17はホットペッパー内キーワード
  (「東京 オーナー1人 サロン」)経由で発見できていたため、次回以降はInstagram直接検索よりポータル内
  キーワード検索の再現の方が有望と申し送り(candidate-longlist-draft.md第十八弾参照))
- (解消済み 2026-08-03 22:00 UTC: 美容室・パーソナルジムの代替候補(第三候補)探索に着手し、
  美容室で新規候補1件(候補17: aane hair)を特定してinterview-request-package.mdの優先度Bに
  追加した(候補計10件→11件)。パーソナルジムは新規候補を特定できず候補1・11のまま
  (candidate-longlist-draft.md第十七弾参照))
- (解消済み 2026-08-03 20:00 UTC: 確定済み6件(学習塾4件・整体院2件)+
  美容室・パーソナルジムの未確認/保留4件を業種横断の最終候補一覧表としてcandidate-longlist-draft.md
  「第十六弾」にまとめた。保留4件はWebFetch遮断により本エージェントの手段では緩和後の望ましい条件の
  最終確認ができないが、除外すると美容室・パーソナルジムの候補がゼロ〜過小になるため「要オーナー
  目視確認」の付記付きでオーナー提示候補に含める方針とした(interview-candidate-selection-criteria.md
  にも進捗記録を追記)。確定6件+保留4件で計10件となり、customer-interview-design.mdの目標合計
  「10件前後」の母数には一旦到達。次は(1)今回の最終候補一覧表とinitial-contact-message-draft.mdの
  依頼文面草案をあわせた「ヒアリング依頼提示パッケージ」の草案作成、(2)余力があれば美容室・
  パーソナルジムの代替候補(第三候補)の探索、の順で進める想定)
- (解消済み 2026-08-03 19:00 UTC: 候補8(霞が関Lead off Health整体院)は公式LINEアカウントでの相談・簡易
  予約に対応していることが確認でき、緩和後の望ましい条件を満たすと判定(整体院枠は候補6・8の2件が
  確定)。一方、候補9(to suit)・11(CUSTOM FIT GYM)・1(STUDIO NEW CHAPTER)は公式サイト本文が
  WebFetchで一律403拒否されるため、WebSearchのスニペットだけでは電話・LINE個別対応への依存の実態
  確認に限界があると判明し、これ以上同角度のWebSearchを繰り返しても進展は見込みにくい状態。現時点で
  確定しているヒアリング対象候補は学習塾4件(候補3・12・13・14)・整体院2件(候補6・8)のみ。次は
  (1)確定済み6件をまず業種横断の最終候補一覧表としてまとめ始める、(2)美容室・パーソナルジムの未確認
  3件(候補9・11・1)・保留中の候補10を一覧表に「要オーナー目視確認」として含めるか除外するかを
  interview-candidate-selection-criteria.mdで整理する、の順で進める想定)
- (解消済み 2026-08-03 13:00 UTC: 豊田塾の個人経営可否を確認し候補#14として暫定採用(学習塾は計4件に到達)。
  パーソナルジムは新規開拓が3回連続不調のため、次回以降は既存候補のネット予約導線有無の個別確認
  (候補3・6・8・9・10・11・12・13・14)に軸足を移し、確認結果をまとめた一覧表を作成してオーナー提示準備の
  最終段階に進める方針)
- (解消済み 2026-08-03 11:00 UTC: candidate-longlist-draft.mdの学習塾の候補積み増しに、運営者個人
  プロフィール軸の検索で新規1件(#12 世田谷みどり塾)を追加。候補3・12とも世田谷区に集中しているため、
  次回は他区への検索対象拡大、豊田塾が個人経営か否かの確認、パーソナルジムの3件目探索を申し送り)
- (解消済み 2026-08-03 01:00 UTC: 前項の残課題だったowner-settings-wireframe.mdの臨時休業日入力欄
  における過去日付・重複日付の入力バリデーション設計を行った。両者ともAvailabilitySearcher/
  reminder_scheduler.py側のfrozenset[date]構造では機能的なバグにはならないため「入力ミスに
  気づかせるUX上のガード」と位置づけ、追加時のインライン警告方式を採用(登録済み日付が経過後に
  過去日付化しても自動削除はしない)。MVPはNo-codeフォームツール流用が前提のため専用コード実装は
  本格版移行時まで不要と判断し、コード変更なし。これで予約とれる君venture全体の残る大きな課題は
  実LLM/実LINE API/実Cloud Scheduler接続自体(オーナー承認待ち)のみとなった)
- (解消済み 2026-08-03 00:00 UTC: ad-hoc-closed-dates-support.mdに残っていた
  owner-settings-wireframe.mdへの「臨時休業日リスト」入力欄の追記を行った。定休日(曜日単位)欄とは
  別枠で日付の追加/削除リストを設けた。新たな残課題として、過去日付・重複日付の入力バリデーション
  設計が残った)
- (解消済み 2026-08-02 23:00 UTC: ad-hoc-closed-dates-support.mdの残課題だった、
  reminder_scheduler.py側の`closed_dates`対応を実装した。`StoreReminderConfig`に
  `closed_dates`を追加し、`compute_initial_reminder_target()`の前営業日への遡り判定を
  `closed_weekdays`(曜日定休)と`closed_dates`(臨時休業日)のOR条件に拡張。テスト2件追加・
  全129件パス。残る課題はowner-settings-wireframe.mdへの「臨時休業日リスト」入力欄の追記、
  および実LLM/実LINE API/実Cloud Scheduler接続自体(オーナー承認待ち))
- (解消済み 2026-08-02 22:00 UTC: availability-closed-weekday-support.mdに残っていた祝日・
  臨時休業(特定日付単発の休業)への対応を実装した(ad-hoc-closed-dates-support.md)。
  `AvailabilitySearcher`に`closed_dates`を新設。テスト2件追加・全127件パス。残る課題は
  reminder_scheduler.py側の同様対応・owner-settings-wireframe.mdの入力UI追記、および
  実LLM/実LINE API/実Cloud Scheduler接続自体(オーナー承認待ち))
- (解消済み 2026-08-02 20:00 UTC: 動作確認が手動unittest実行に依存していた点を解消し、
  GitHub Actionsでprototype/の自動テスト(125件)とschema検証(22件)を自動実行するようにした
  (ci-setup.md)。残る大きな課題は引き続き実LLM/実LINE API/実Cloud Scheduler接続自体
  (オーナー承認待ち)のみ)
- 実LLM/実LINE API/実Cloud Scheduler接続自体(オーナー承認待ち、pending-approval.md参照)。
  intent-to-flow-mapping.mdの対応表に載っている主要intent(new_booking/cancel/change/faq/
  escalation)の机上実装・NotificationLogAggregatorの記録ギャップ修正まで一通り揃った
  ため、残る大きな一歩は机上検証から実LLM検証への移行のみだが、APIキー取得・従量課金が
  発生するためオーナー承認が前提(pending-approval.md参照)。
- (解消済み 2026-08-02 19:00 UTC: 前項の残課題だったNotificationLogAggregatorのシステム内部
  イベント記録ギャップを修正した(system-event-log-gap-fix.md新規作成)。詳細はフェーズ
  (続き42)参照。全125件テストパス)
- (解消済み 2026-08-02 18:00 UTC: change-intent-handling-design.mdの残課題だった、change後の
  新規候補検索が0件だった場合の顧客向け文言出し分けを実装した。旧予約を実際に解放した場合のみ
  `CHANGE_NO_CANDIDATES_MESSAGE`を送り、解放すべき実体が無かった場合は従来通りの
  `REASK_DATE_RANGE_MESSAGE`のままとした。テスト2件追加・全119件パス。残る大きな課題は
  実LLM/実LINE API/実Cloud Scheduler接続自体(オーナー承認待ち)とNotificationLogAggregatorの
  システム内部イベント記録ギャップ)
- (解消済み 2026-08-02 17:00 UTC: 前項の残課題だった`change`(日時変更)の実処理を実装した
  (change-intent-handling-design.md)。`cancel_booking()`と同じ分岐(stageに応じた
  release()・confirmed分のみオーナー通知、escalation_reasonは`booking_change_started`/
  `change_not_found`で区別)を行う`change_booking()`を新設し、cancelと異なり会話を終了させず
  `_start_new_booking()`(new_bookingと同じ新規候補検索フロー)へそのまま接続する設計
  (「変更 = 旧予約の解放 + 新規予約フローの開始」)。booking_output.schema.jsonは
  `requested_date_range`/`time_of_day_preference`を元々change対応済みだったためスキーマ変更は
  不要だった。テスト13件追加・全117件パス。残る課題は実LLM/実LINE API/実Cloud Scheduler接続
  自体(オーナー承認待ち)のみとなった)
- (解消済み 2026-08-02 16:00 UTC: 前項の残課題だったcancel/change intentの実処理のうち、
  `cancel`のみを対象に実装した(cancel-intent-handling-design.md)。会話のstageに応じて
  `BookingSlotManager`の枠解放・返信文言の出し分けを行う`cancel_booking()`を新設し、
  confirmed状態のキャンセルのみEscalationConsolidator経由でオーナーに通知する(外部予約記録の
  更新が必要なため)。テスト12件追加・全107件パス。残る課題は`change`(日時変更)の設計・実装、
  実LLM/実LINE API/実Cloud Scheduler接続自体(オーナー承認待ち))
- (解消済み 2026-08-02 15:00 UTC: 前項の残課題(b)だった確定後の顧客返信検知
  (customerRepliedAt)の配線設計を実装した(customer-reply-detection-design.md)。
  confirmed状態の会話へメッセージが届いた事実そのもの(内容は問わない)を、
  `ConfirmedReplyRecorder`プロトコル経由でCloud Function Bのprocess()冒頭に記録する設計。
  テスト4件追加・全95件パス。残る課題は(c)実LLM/実LINE API/実Cloud Scheduler接続自体
  (オーナー承認待ち)、cancel/change intentの実処理)
- (解消済み 2026-08-02 14:00 UTC: 前項の残課題(a)だった単一項目FAQ(faq_segmentsがnullの
  ケース)のスキーマ変更要否を検討した。「厳守事項9aに基づくfaqは単一項目でも
  faq_segmentsを1要素配列で必ず付与する」方針を採用し、json-schema-multi-intent-
  extension.md・llm-system-prompt-draft.md・conversation-samples-test-cases.md
  (E10・E14)・schema/booking_output.schema.json・schema/validate_test_cases.mdを更新
  (single-item-faq-schema-decision.md新規作成)。prototype/cloud_function_process_event.pyは
  既存の複合質問向けループがそのまま流用できるためコード変更は不要で、コメント更新と
  デモ・テスト追加のみ(テスト1件新規・全91件パス)。残る課題は(b)確定後の顧客返信検知
  (customerRepliedAt)の配線設計、(c)実LLM/実LINE API/実Cloud Scheduler接続自体
  (オーナー承認待ち))
- (解消済み 2026-08-02 13:00 UTC: 前項の残課題(c)だった前日リマインド経路の呼び出し元を
  設計・実装した(reminder-scheduler-design.md、prototype/reminder_scheduler.py)。残る課題は
  (a)単一項目FAQ(faq_segmentsがnullのケース)でも自動返信できるようにするスキーマ変更の
  要否検討、(b)確定後の顧客返信検知(customerRepliedAt)の配線設計、(c)実LLM/実LINE API/
  実Cloud Scheduler接続自体(オーナー承認待ち))
- (解消済み 2026-08-02 12:00 UTC: 前項の残課題(b)だった確定操作競合時の新しい空き枠の再提示を
  実装した(booking-conflict-candidate-representation.md)。残る課題は(a)単一項目FAQ
  (faq_segmentsがnullのケース)でも自動返信できるようにするスキーマ変更の要否検討
  (json-schema-multi-intent-extension.mdの既存推奨の見直しが必要、影響範囲が
  llm-system-prompt-draft.md・booking_output.schema.json・テストケース群に及ぶため慎重な検討が
  必要)、(c)前日リマインド経路の呼び出し元、(d)実LLM/実LINE API接続自体(オーナー承認待ち))
- (解消済み 2026-08-02 11:00 UTC: webhook-function-b-implementation.mdの残課題(1)だった
  escalation/faq intentの顧客向け返信を実装した(faq-escalation-customer-reply-implementation.md)。
  残る課題は(a)単一項目FAQ(faq_segmentsがnullのケース)でも自動返信できるようにする
  スキーマ変更の要否検討(json-schema-multi-intent-extension.mdの既存推奨の見直しが必要、
  影響範囲がllm-system-prompt-draft.md・booking_output.schema.json・テストケース群に及ぶため
  慎重な検討が必要)、(b)確定操作競合時の新しい空き枠の再提示、(c)前日リマインド経路の
  呼び出し元、(d)実LLM/実LINE API接続自体(オーナー承認待ち))
- (解消済み 2026-08-02 10:00 UTC: 前項の残課題だったCloud Function B
  (process_conversation_event)のうち、実LLM呼び出し・実クラウド接続とは切り離せる配線ロジック
  (Cloud Tasksからデキューしたイベント→intent-to-flow-mapping.md対応表→
  ConversationFlowStateMachine→LINE Push文言組み立て)を実装した
  (prototype/cloud_function_process_event.py、テスト12件全件パス)。残課題は
  (1)escalation/faq intentの顧客向け返信(faq_segmentsとの統合)、(2)確定操作競合時の新しい
  空き枠の再提示、(3)前日リマインド(スケジューラ発火)経路の呼び出し元、(4)実LLM API・実LINE
  API接続自体(いずれもオーナー承認待ち)。次はこのうち(1)か(2)のロジック単体(クラウド接続
  なしで検証可能な範囲)から着手するのが妥当)
- (解消済み 2026-08-02 09:00 UTC: webhook-async-processing-design.mdの残課題だった
  「Cloud Function A(receive_webhook)のハンドラコード実装」に着手した。署名検証・
  webhookEventIdからの決定的タスク名導出・isRedelivery早期スキップ・Cloud Tasks重複排除の
  模擬をクラウド接続なしで実行可能なコードに落とし込んだ(prototype/cloud_function_webhook.py、
  テスト17件全件パス)。残課題はCloud Function B(process_conversation_event)の実装で、
  こちらは実LLM呼び出し自体がAPIキー・課金のオーナー承認待ちのため引き続き未着手)
- (解消済み 2026-08-02 08:00 UTC: webhook-async-processing-design.mdの残課題だった
  タスク名の重複排除キーの生成方法をLINE公式ドキュメントのweb調査で確認した。
  `webhookEventId`(ULID)をそのままタスク名の導出元に使え、`deliveryContext.isRedelivery`
  で再送検知も追加できることが判明。残るはCloud Function実装自体(GCPプロジェクト作成後))
- (解消済み 2026-08-02 06:00 UTC: hosting-platform-selection.mdの残課題だったCloud Functionsの
  Webhook応答遅延対策を設計した(webhook-async-processing-design.md)。即時ACK+Cloud Tasksでの
  非同期処理+push APIでの応答という方式を採用。残課題はCloud Tasksの実導入(GCPプロジェクト
  作成後)と、push API利用がline-api-pricing.md等の既存メッセージ通数試算に与える影響の再確認)
- (解消済み 2026-08-02 05:00 UTC: legal-notices-draft.mdの残課題だった所在地表示要否・AI利用開示要否
  について、web調査による一般的な傾向整理(法的助言ではない)を追記した。特商法は役務提供契約も
  表示義務対象となりうること、AI対応の開示を一般義務化する法律は現状見当たらないことを確認。
  残課題は最終的な該非判断についての法律専門家への相談要否をオーナーと確認すること)
- (解消済み 2026-08-02 04:00 UTC: landing-page-copy-draft.mdの残課題だった特定商取引法に
  基づく表記・プライバシーポリシーの文面草案を作成した(legal-notices-draft.md)。残課題は
  所在地表示要否・AI利用開示要否の法律専門家への確認要否のオーナーとのすり合わせと、
  LLM APIプロバイダ契約後のプライバシーポリシー第三者提供節の更新)
- (解消済み 2026-08-02 03:00 UTC: これまで顧客とのLINE上のやり取りの設計が中心だったが、
  「オーナーが本サービスを知って申し込むまで」の導線で使うランディングページのコピー草案を
  初めて作成した(landing-page-copy-draft.md)。残課題は特定商取引法に基づく表記・プライバシー
  ポリシーの文面草案作成と、AI利用の開示表示義務の要否の法的確認)
- (解消済み 2026-08-02 02:00 UTC: firestore-traffic-cost-estimate.mdの残課題だった
  MAX_SEARCH_RANGE_DAYS=14日クランプ時のワーストケースを数値化した。無料枠内に収まる
  店舗数の目安をプロプラン相当で約130店舗→約32店舗に下方修正。残課題は実際の顧客の
  検索レンジ分布をcustomer-interview-design.mdのヒアリングで確認すること)
- (解消済み 2026-08-02 00:00 UTC: 想定トラフィックでのFirestore読み書き回数・無料枠との比較試算を行った
  (firestore-traffic-cost-estimate.md)。プロプラン相当で約100店舗規模まで無料枠内で運用できる見込みと結論。
  残課題は「検索レンジ3日」等の仮定の妥当性確認と、実クライアント接続による実測(GCPプロジェクト作成後、
  オーナー承認待ち))
- (解消済み 2026-08-01 23:00 UTC: hold()/confirm()・escalationWindows更新をFirestore
  トランザクションに置き換える実装方針を詳細化した(firestore-transaction-design.md)。
  残るのは想定トラフィックでの読み書き課金試算と、実際のFirestoreクライアント接続による
  動作確認で、後者はGCPプロジェクト作成(オーナー承認待ち、pending-approval.md参照)後の課題)
- (解消済み 2026-08-01 22:00 UTC: Firestoreのデータモデル設計(会話状態・予約枠・通知ログの
  コレクション分割)を行った(firestore-data-model.md)。次の課題はhold()/confirm()等を
  Firestoreトランザクションへ置き換える実装方針の詳細化と、想定トラフィックでの読み書き
  課金試算。実際のFirestoreデータベース作成・GCPプロジェクトの請求先設定は「アカウント作成」
  に該当するため着手時に別途オーナー承認が必要)
- (解消済み 2026-08-01 21:00 UTC: tech-stack.mdで方向性のみだったホスティング基盤の具体的な
  選定を行い、GCP Cloud Functions (Python) + Firestoreを第一候補として決定した
  (hosting-platform-selection.md))
- (解消済み 2026-08-01 16:00 UTC: llm-system-prompt-draft.mdの厳守事項7に、店舗設定「メッセージトーン」
  の値に応じてmessage-tone-variants.mdの変換規則(語尾・絵文字・感嘆符)を適用する指示を反映した。
  残るのはconversation-samples-test-cases.mdへのトーン別出力サンプル追加と実LLM検証で、
  後者はpending-approval.md記載のAPIキー取得・課金承認待ち)
- (解消済み 2026-08-01 18:00 UTC: conversation-samples-test-cases.mdに前日リマインド・仮押さえ直後・
  FAQ回答テンプレートについてもN3と同様のトーン別(フォーマル/standard/カジュアル)期待自然文サンプルを
  追加し、4テンプレート全ての机上サンプルが出揃った。この過程で、前日リマインドのみ他の3つと異なり
  「対応するJSON入力が存在しないスケジューラ発火型のプッシュ通知」であることが判明。トーン変換ロジックを
  LLM出力起点の経路とスケジューラ発火の経路の両方で共通化できるかの実装設計が新たな残課題として残った)
- (解消済み 2026-08-01 19:00 UTC: 前日リマインド(スケジューラ発火)と仮押さえ直後・FAQ回答等
  (LLM出力起点)の2つの生成経路で、message-tone-variants.mdのトーン変換ロジックを共通の関数
  として実装できるかを検討し、`prototype/engine.py`に`_render_by_tone()`という共通
  ディスパッチャとして実装した。実LLM呼び出しへの接続(スタブのllm_call差し替え)は
  引き続きオーナー承認待ちの課題として残る)
- (解消済み 2026-08-01 13:00 UTC: release_idle_conversations()/archive_completed_conversations()の
  実行トリガーは、専用ホスティング基盤の確定を待たずに「Webhook受信便乗+最小実行間隔5分での間引き」
  方式(idle-conversation-trigger-design.md)を採用し、`maybe_run_idle_cleanup()`/`maybe_run_archive()`
  として実装・デモ確認済み。将来専用スケジューラに切り替える場合もこの2関数をそのまま呼び出す形に
  流用できる設計とした)
- (解消済み 2026-08-01 14:00 UTC: candidates_presented失効時の能動通知の要否はcandidates-expired-
  notification-design.mdで検討し、プッシュメッセージ課金・送信タイミングの唐突さ・実測データ不在を
  理由にMVPでは送らない方針(現状維持)を採用。将来切り替えやすいよう戻り値の型のみ先行変更済み)
- (解消済み 2026-08-01 12:00 UTC: weekday-specific-business-hours.mdの残課題だった「曜日別営業時間の
  0分間区間とclosed_weekdaysの二重表現」問題は、business-hours-lunch-break.mdの区間バリデーションが
  既に0分間区間を拒否するため解消済みと確認。UI側の追加バリデーションは不要と判断)
- (解消済み 2026-08-01 10:00 UTC: 1日に複数の営業時間帯がある(昼休憩)ケースはbusiness-hours-lunch-break.md参照。
  同ファイルの残課題だった区間同士の重複・逆転バリデーションも2026-08-01 11:00 UTCに実装済み)
- 実LLM呼び出しでの安定生成確認(conversation-samples-test-cases.mdのN1〜N4・E1〜E16を実際にClaude API等へ
  投入するテスト)は、APIキー取得・課金が発生するためオーナー承認後に着手する(pending-approval.md参照)。
  承認が得られ次第、prototype/engine.pyのllm_callスタブに実API呼び出し関数を注入するだけで着手できる状態にしてある。
- escalation-consolidation-logic.mdの「再発火3回目で都度通知に切り替え」「30分途絶えでリセット」の閾値は仮の目安であり、実測データが取れた際に見直す
- 初回コンタクト文面草案の未確定事項(謝礼有無・送信者名表記・返信先連絡先)についてオーナーの方針を確認(顧客ヒアリング関連、実施は別途承認済み範囲内で進行中)
