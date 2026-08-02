# 予約とれる君(LINE公式AI予約アシスタント)

## 概要
個人事業主〜小規模事業者(美容室、整体・エステ、パーソナルジム、学習塾など)向けに、
LINE公式アカウント上でお客様とのやり取りをAIが解釈し、空き時間の確認・予約確定・前日リマインドまで
自動で行うチャットボットSaaS。

## ステータス
- フェーズ: 会話フロー設計 → 二重予約防止ロジック設計 → オーナー向け設定画面ワイヤーフレーム → LINE Messaging API料金調査 → 料金プラン・無料トライアル条件の仮決め → 想定顧客ヒアリング設計 → 保留タイムアウトのUX文言設計 → 顧客接点メッセージ統一トーン&マナーガイドライン作成 → 前日リマインド送信タイミング・再通知ルール設計 → 無断キャンセル発生時の記録・通知設計 → 事前確認強化の要否検討・顧客詳細画面ワイヤーフレーム追記 → 事前決済(デポジット)機能の技術要件・手数料調査 → ヒアリング項目にデポジット機能の需要・抵抗感を確認する設問(E.)を追加 → ヒアリングリハーサル用台本・時間配分の設計 → 2026年10月LINE料金改定内容の再確認(web調査) → ヒアリング対象候補(実店舗)の選定基準・情報源の整理 → 初回コンタクト依頼文面の草案作成(未送信) → 業種ごとの候補数の妥当性・追加候補確保の目安を試算 → 会話フロー・二重予約防止・トーンガイドライン等を統合したLLMシステムプロンプト草案の作成 → 構造化出力(JSON)フォーマット崩れ時のリトライ・フォールバック設計 → 会話サンプル(正常系・崩れ系)を用いたプロンプトテストケース設計 → テストケースで指摘したE6(雑談・スパム)・E9(未実装機能問い合わせ)への対応をシステムプロンプト草案に反映(厳守事項9・10追加) → 厳守事項9(FAQ/雑談)と6(予約以外の相談エスカレーション)の境界線を整理(9a/9bに分割) → owner-settings-wireframe.mdに9a用の「店舗FAQ情報」入力欄(住所・アクセス/駐車場/支払い方法)を追加 → 店舗FAQ情報欄の具体項目(駐車場台数・支払い方法チェックボックス内訳、未入力時の6番エスカレーション)をllm-system-prompt-draft.mdの厳守事項9aに反映 → conversation-samples-test-cases.mdに9a関連の新規テストケース(E10:登録済み情報でのFAQ回答、E11:未入力項目、E12:未チェック支払い方法)を追加し、9a/9b/6の境界整理との整合を確認 → faq-escalation-boundary.mdの残課題だった9aの回答テンプレート(住所・アクセス/駐車場/支払い方法の項目別穴埋め式テンプレート、複合質問の分割送信例)を新規設計 → faq-response-templates.mdの項目別テンプレートをllm-system-prompt-draft.mdの厳守事項9a説明文に反映(「登録値を言い換えない」旨と複合質問の分割送信・部分エスカレーションのルールを明文化) → conversation-samples-test-cases.mdのE10想定出力を項目別テンプレートに揃えて具体化し、複合質問の分割送信テストケースE13(全項目回答可/一部未登録の2パターン)を新規追加 → E13で発見した「1応答内でintentが項目ごとに混在しうる」課題への対応として、構造化出力(JSON)スキーマに任意フィールド`faq_segments`を追加する拡張案を設計し、llm-system-prompt-draft.md・json-output-retry-fallback.md・conversation-samples-test-cases.mdに反映 → 厳守事項6・10(相談エスカレーション・未実装機能問い合わせ)発生時のオーナー通知文面を具体化し、faq_segments一部未解決時の通知文面も設計 → 連続エスカレーション(同一顧客が短時間に複数回)を1通にまとめる集約ロジック(時間窓5分・初回即時+追加分はまとめ通知の2段階方式)を具体設計 → 未登録FAQ件数・未実装機能問い合わせ件数を俯瞰するための通知ログ集計画面のワイヤーフレームをowner-settings-wireframe.mdに追記(営業情報設定ページからの導線、MVPはスプレッドシート集計で代替) → 定休日対応・曜日別営業時間に続き、昼休憩など1日複数営業時間帯へのAvailabilitySearcher対応を設計・実装(business-hours-lunch-break.md) → release_idle_conversations()/archive_completed_conversations()のWebhook便乗トリガー方式を設計・実装(idle-conversation-trigger-design.md) → candidates_presented失効時の能動通知(候補期限切れメッセージ)の要否を検討し、MVPでは送らない方針を採用(candidates-expired-notification-design.md) → llm-system-prompt-draft.mdの厳守事項7に、店舗設定「メッセージトーン」の値に応じてmessage-tone-variants.mdの変換規則を適用する指示を反映 → prototype/engine.pyの主要ロジックをunittestベースの自動テストスイート化(automated-test-suite.md) → ホスティング基盤をGCP Cloud Functions (Python) + Firestoreに選定(hosting-platform-selection.md) → Firestoreのコレクション設計(firestore-data-model.md) → hold()/confirm()・escalationWindows更新をFirestoreトランザクションに置き換える実装方針を詳細化(firestore-transaction-design.md) → 想定トラフィックでのFirestore読み書き回数・無料枠との比較試算(firestore-traffic-cost-estimate.md、残るは実クライアント接続による実測) → MAX_SEARCH_RANGE_DAYSクランプ時のワーストケース試算(無料枠内店舗数目安を約130店舗→約32店舗に下方修正) → サービス紹介ランディングページ(LP)のコピー草案を新規作成(landing-page-copy-draft.md) → 特定商取引法に基づく表記・プライバシーポリシーの文面草案を新規作成(legal-notices-draft.md)
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
- 最終更新: 2026-08-02 04:00 UTC

## ドキュメント
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
- llm-system-prompt-draft.md: 会話フロー・二重予約防止・トーン&マナー・保留タイムアウト・無断キャンセル対応等の既存設計を統合した、LLM会話エンジン向けシステムプロンプト草案(2026-08-01 16:00 UTC更新、厳守事項7を書き換え、店舗設定「メッセージトーン」の値に応じてmessage-tone-variants.mdの変換規則(語尾・絵文字・感嘆符)を適用する指示を反映。固定語彙・日付時刻表記・FAQ実質情報はトーンに関わらず変更しない旨も明記。実装・実LLM検証は未着手)
- json-output-retry-fallback.md: 構造化出力(JSON)がパース失敗・スキーマ不一致・矛盾を起こした場合のリトライ(1回まで)・フォールバック(安全側判定でオーナー通知に転送)方針の設計(2026-07-31 09:59 UTC更新、任意フィールド`escalation_reason`/`feature_hint`のスキーマ不一致も既存の「2. キー不足/余分」判定に含めつつ、分類用メタデータのため不正時も`needs_owner_check`によるオーナー通知は止めず「分類不能」へフォールバックする方針を追記。実装・動作検証は未着手)
- conversation-samples-test-cases.md: LLMシステムプロンプト草案・JSONリトライ設計を検証するための会話サンプル(正常系4件・崩れ系16件)のテストケース設計(2026-08-01 18:00 UTC更新、N3に続き前日リマインド・仮押さえ直後・FAQ回答テンプレートについてもフォーマル/standard/カジュアルの3トーン別期待自然文サンプルを追加し4テンプレート全て出揃った。前日リマインドのみJSON入力を経由しないスケジューラ発火型である点が新たに判明。机上設計のみで実LLM検証は未着手)
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
- schema/validate_test_cases.py: 外部ライブラリ非依存の簡易JSON Schemaバリデータ。conversation-samples-test-cases.mdの期待JSON出力を机上検証する(2026-07-31 14:58 UTC更新、N3・N4・E1・E3・E4・E7・E8のフィクスチャを追加し22件に拡充、実LLM呼び出しはなし)
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
- availability-closed-weekday-support.md: AvailabilitySearcherのMVP制約のうち定休日対応の設計・実装メモ(2026-08-01 07:00 UTC新規作成。`closed_weekdays`パラメータ追加、owner-settings-wireframe.mdの営業曜日チェックボックスに対応。曜日別営業時間は引き続きスコープ外)
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
- legal-notices-draft.md: landing-page-copy-draft.mdの残課題だった特定商取引法に基づく表記・
  プライバシーポリシーの文面草案(2026-08-02 04:00 UTC新規作成。事業者名・所在地等は
  `【要記入】`のプレースホルダー。プライバシーポリシーはLINE連携で取得する情報・LLM API
  プロバイダへの送信・保存期間を整理。所在地表示要否とAI利用開示要否は法律専門家への
  確認が必要な未検証事項として残置。作成は草案のみでLP掲載・公開は未着手)

## 次にやること(候補)
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
