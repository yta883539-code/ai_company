# エアコンパシャッと

フランチャイズ加盟・独立系を問わず個人〜小規模で活動するエアコンクリーニング(訪問分解洗浄)
専門業者向けに、作業後の簡単なメモを送るだけで、AIが(1)依頼者向け作業完了報告メッセージ下書き、
(2)お手入れ案内下書き、(3)簡易な作業履歴記録、の3つをまとめて生成するサービス。

## 概要

- 対象顧客: フランチャイズ加盟・独立開業を問わず個人事業主として活動するエアコンクリーニング
  (分解洗浄)専門業者、ハウスクリーニング業者の中でもエアコン分解洗浄を主力メニューとする
  個人事業主。
- 入力: 作業後のメモ(例:「壁掛け型2.2kW、フィルター・熱交換器・送風ファンまで分解洗浄、
  カビ・ホコリ汚れ中程度、防カビコート施工あり、次回推奨は来年同時期」等)。
- 出力: (1)作業完了報告メッセージ下書き(実施範囲・使用した洗浄剤や防カビコートの有無・
  分解洗浄前後の状態の説明)、(2)お手入れ案内下書き(フィルターの自己清掃目安、次回分解洗浄の
  推奨時期、自己分解洗浄のリスクについての一般的な注意喚起)、(3)簡易な作業履歴記録
  (号数・機種系統・汚れ状況・防カビコート有無の推移が追える形)。
- 実際の分解洗浄作業自体、エアコンの型式判別・冷媒に関する専門的判断は業者本人が行う前提とし、
  本サービスは作業完了報告・お手入れ案内文の下書き作成支援のみを行う(冷媒ガスの取り扱いや
  電気系統に関する専門的助言は行わない)。会員管理・予約受付・決済は扱わない。

## ステータス

- フェーズ140(2026-08-28 11:00 UTC): フェーズ139のpayment-failure-dunning-design.md
  「残課題」のうち、外部サービス接続・アカウント作成を伴わない範囲(状態フィールド追加・
  Webhookイベント種別ディスパッチ)に着手した。`UserProfile`(prototype/user_id_linking.py)へ
  `payment_failure_detected_at`・`payment_suspended_at`の2フィールドを追加し、
  `UserProfileStoreProtocol`/`InMemoryUserProfileStore`にも対応するget/setメソッドを
  追加した。新規`prototype/payment_failure.py`(deletion_candidate.pyと同じ位置づけの
  薄いProtocol・純粋関数)を新設し、`mark_payment_failure_detected()`
  (`invoice.payment_failed`受信時に検知時刻を記録)・`clear_payment_failure_on_success()`
  (`invoice.payment_succeeded`受信時に決済失敗・制限モードの両状態をクリア)の2関数を
  実装した。`stripe_dispatch.py`の`dispatch_stripe_event()`に`payment_store`引数
  (省略時はこれまで通り`ignored_types`扱いとする後方互換)を追加し、この2イベント種別を
  振り分けるようにした。design 6節が予告していた「専用のInMemoryストアを新設するか」
  という論点は、deletion_candidate.pyのように別系統のdictを持つ専用ストアを新設すると
  実Firestore接続時に同一user_profileドキュメントのフィールドが2つのストアオブジェクトに
  分裂して見えてしまうため、専用ストアは新設せず`InMemoryUserProfileStore`が
  `PaymentFailureStoreProtocol`を構造的に(duck typing)満たす形にした。テスト15件追加
  (test_payment_failure.py 8件・test_stripe_dispatch.py 7件)、venture全体235件全件
  パス・schema/validate_test_cases.py 9件全件パスを確認した。承認不要な設計・実装・
  テスト追加のみで、外部サービスへの公開・アカウント作成・支払い等は今回発生していない
  ためpending-approval.mdへの追記なし。design 6節の残る項目(猶予期間終了後に制限モードへ
  自動移行させるスケジューラ、`_is_generation_paused()`の判定条件拡張・専用メッセージの
  `process_memo_event()`への配線、Stripe Customer Portalの要否検討、猶予期間中の決済成功
  時の復旧通知3分岐の文言出し分け)はいずれも未着手のまま次回以降の課題として残る。次回は
  この中で最も既存パターン(GENERATION_PAUSED_MESSAGE・quick_replyの流用)に近い
  `_is_generation_paused()`の判定条件拡張・専用メッセージ配線を優先候補とする。
- フェーズ139(2026-08-28 08:00 UTC): line-reservation-aiにのみ存在し本venture・
  course-set-pashaには無かった「決済失敗(カード継続課金エラー)時の案内」設計の欠落に
  気づき、payment-failure-dunning-design.mdを新規作成した。line-reservation-aiの
  payment-failure-dunning-design.md(猶予期間7日・Stripeスマートリトライ活用・3段階
  状態遷移)を土台に、本venture固有の前提(「新規予約受付」ではなく既存の`_is_generation_
  paused`/`GENERATION_PAUSED_MESSAGE`(フェーズ138)と同じ「生成一時停止」機構の対象に
  決済失敗由来の理由を追加する設計)へ翻案した。猶予期間中は生成を止めない、猶予期間
  終了後に制限モードへ移行して初めて生成を止める、という3段階構成と、業者向け通知文言
  4種(検知時・終了直前リマインド・制限モード移行時・復旧時、tone-and-manner-guideline.md
  準拠でですます調・絵文字不使用・見出しなし)の初版を作成した。CTA方式は本venture既存の
  postback方式quick_replyを踏襲する一方、支払い方法更新にはcheckout-initiation-flow-
  design.mdの新規Checkout Session発行とは別にStripe Customer Portalが必要になる見込みを
  次回以降の検討課題として明記した。設計のみで、`UserProfile`へのフィールド追加・
  `stripe_dispatch.py`への`invoice.payment_failed`等のイベント種別追加・実装・
  Webhook配線はいずれも未着手のまま次回以降の課題として残した。承認不要な設計作業のみで、
  外部サービスへの公開・アカウント作成・支払い等は今回発生していないためpending-approval.md
  への追記なし。
- フェーズ138(2026-08-28 05:00 UTC): フェーズ137の申し送り通り、トライアル終了後(未
  アップグレード)の「生成一時停止」(trial-end-notification-design.md 4節、
  course-set-pashaのフェーズ114相当)を実装した。`_is_generation_paused(profile)`
  (`profile.trial_end_notified_at`設定済みかつ`profile.upgraded_at`未設定の場合のみTrue)
  と`GENERATION_PAUSED_MESSAGE`を新設し、`process_memo_event()`冒頭(LLM呼び出しより前)で
  該当する場合はLLM呼び出し・月間カウント・トライアル生成回数カウントのいずれも行わず
  一時停止案内を即座に返信する分岐を追加した。本venture固有の対応として、CTA(有料プランへ
  進む)はcourse-set-pashaのLIFF URLプレースホルダ埋め込み方式ではなく、フェーズ137で
  確立したpostback方式のquick_reply(`QuickReplyButton(label=TRIAL_END_BUTTON_LABEL,
  postback_data=START_CHECKOUT_POSTBACK_DATA)`)を一時停止応答にも同じ形で添付する設計とした。
  従来`process_memo_event()`後半でLLM呼び出し結果と共に取得していた`user_id`・`profile`を
  関数冒頭へ前倒しし、一時停止判定と後半の初回セルフチェック・条件A判定の両方で1回の
  `profile_store.get()`を再利用する形にリファクタした(プロフィール状態はLLM呼び出しの
  前後で変化しないため、取得タイミングを早めても既存の挙動に影響しない)。既存テスト
  `test_no_double_send_when_already_notified_by_condition_b`(フェーズ137)は、
  `trial_end_notified_at`設定済み・`upgraded_at`未設定という同条件がそのまま一時停止対象と
  一致するため、期待するふるまいを一時停止応答の内容に合わせて更新した(「二重送信しない」
  という結論自体は変わらない)。テスト6件新規追加(`ProcessMemoEventGenerationPausedTest`、
  LLM呼び出しが一切行われないことを検証する`_MustNotBeCalledLlmClient`を使用)、venture全体
  221件全件パス、schema/validate_test_cases.pyも9件全件パスを確認した。
  trial-end-notification-design.md 4節に実装済みの旨を追記した。承認不要な設計・実装・
  テスト追加のみで、外部サービスへの公開・アカウント作成・支払い等は今回発生していないため
  pending-approval.mdへの追記なし。なお4節2点目に挙げられていた一時停止解除後の
  `upgraded_at`書き込み配線は、`stripe_webhook.py`の`handle_checkout_session_completed()`に
  既にフェーズ135で実装済み(`profile.upgraded_at is None`のときのみ`set_upgraded_at()`を
  呼ぶ「1回だけ書き込む」不変条件を維持)であることを確認し、4節の記述は本フェーズの
  一時停止実装分のみを更新した。次回は他venture・アイデア領域の前進、または本venture内で
  未着手のまま残っている実LLM・実Stripe接続待ちの残課題(オーナー承認待ち)以外の棚卸しを
  優先候補とする。
- フェーズ137(2026-08-28 04:00 UTC): フェーズ136の申し送り「`trial_generation_count`の
  実集計配線」に対応した(trial-end-condition-a-cta-design.md新規作成)。`user_id_linking.py`の
  `UserProfile`に`trial_generation_count`フィールド(既定値0)、
  `UserProfileStoreProtocol.increment_trial_generation_count()`を追加し、
  `process_memo_event()`のstatus=="generated"かつ`upgraded_at`未設定(有料転換前)の経路で
  毎回インクリメントするよう配線した。インクリメント後の値がTRIAL_GENERATION_LIMIT(10、
  pricing-plan.mdの「生成10回到達」と一致)ちょうど、かつ`trial_end_notified_at`未設定
  (=(B)期間到達側の日次スケジューラでまだ未通知)の場合のみ、トライアル終了通知文
  (format_trial_end_condition_a_notice())を返信本文に追記し`set_trial_end_notified_at()`を
  書き込む(course-set-pashaのフェーズ113相当)。本venture固有の課題として、CTA(有料プラン
  へ進む)がLIFF URLではなくpostbackボタンのため、Reply APIへの返信本文への便乗だけでは
  ボタンを表現できない点への対応が必要だった。検討の結果、LINE Messaging APIのquickReply
  機能(テキストメッセージにも添付できるボタン領域)を採用し、`ReplyClient.reply()`に
  `quick_reply: Optional[QuickReplyButton] = None`(キーワード専用引数、既定None)を追加、
  `_reply_with_retry()`はquick_replyがNoneのときはキーワード引数自体を渡さないことで、
  既存の2引数シグネチャのみのテスト用スタブ・呼び出し元を一切変更せずに済ませた。
  `InMemoryReplyClient.sent`の既存タプル形式も変更せず、quick_replyは別属性
  `quick_replies_sent`に記録する形にした。テスト4件追加
  (`ProcessMemoEventTrialEndConditionATest`)、venture全体215件全件パス、
  schema/validate_test_cases.pyも9件全件パスを確認した。設計・実装・テスト追加のみで、
  外部サービスへの公開・アカウント作成・支払い等は発生していないためpending-approval.mdへの
  追記なし。次回は引き続き対象外としたトライアル終了後(未アップグレード)の「生成一時停止」
  (trial-end-notification-design.md 4節、course-set-pashaのフェーズ114相当)の実装を
  優先候補とする。
- フェーズ136(2026-08-28 03:00 UTC): first-generation-self-check-design.md「残課題」
  1点目(初回生成時セルフチェック案内の実配線)に対応した。`cloud_function_webhook.py`の
  `process_memo_event()`に`profile_store`・`now`引数を追加し、status=="generated"かつ
  `user_profile.trial_start_at`が未設定(=生涯最初の生成成功)の場合のみ、
  SELF_CHECK_NOTICE_TEXT(業者向け・依頼者への転送不要の旨を明記した確認案内)を
  返信本文末尾に付記し(completion_report・care_guideのbody自体は不変)、
  `profile_store.set_trial_start_at()`で書き込む設計とした。course-set-pashaの原設計
  (`usage_counter`側に別立ての`first_generation_notice_sent`フラグを新設する案)とは
  異なり、本ventureは`trial_start_at`自体が既に「生涯1回だけ書き込む」不変フィールドと
  して`user_profile`に実装済み(フェーズ134)のため、新規フラグを追加せずそれをそのまま
  要否判定に兼用する設計に変更した(trial-start-anchor-decision.md 3節「実装時の変更点」・
  first-generation-self-check-design.md「残課題」に理由を追記)。`process_message_event()`
  から`process_memo_event()`への委譲呼び出しに`profile_store`・`now`を明示的に渡すよう
  配線した。テスト5件追加(`ProcessMemoEventFirstGenerationSelfCheckTest`)、venture全体
  211件のテストがすべて成功、schema/validate_test_cases.pyも9件全件パスを確認した。
  コード実装・テスト追加のみで外部サービスへの公開・アカウント作成・支払い等は発生して
  いないためpending-approval.mdへの追記なし。次回は`trial_generation_count`の実集計配線
  (trial-end-scheduler-design.md・trial-end-notification-design.md 5節で予告されていた、
  トライアル専用生成回数カウンタ。現状`TrialUserState.trial_generation_count`は既定値0の
  まま呼び出し元集計待ちとして残っている)を優先候補とする。
- フェーズ135(2026-08-28 02:00 UTC・前回実行時にREADME記載漏れ、本フェーズで遡って追記):
  trial-end-scheduler-design.md 2節「今後の課題」に残っていた`upgraded_at`書き込み配線を
  `stripe_webhook.py`の`handle_checkout_session_completed()`に実装した。
  `store.get(user_id).upgraded_at`が未設定の場合のみ`store.set_upgraded_at()`を呼ぶ形で
  「有料転換時に1回だけ書き込む」不変条件(UserProfile docstring)を維持した。テスト3件
  追加、venture全体206件のテストがすべて成功、schema/validate_test_cases.pyも9件全件パス
  を確認した。承認不要な実装・テスト追加のみで、外部サービスへの公開・アカウント作成・
  支払い等は発生していないためpending-approval.mdへの追記なし。
- フェーズ134(2026-08-28 01:57 UTC): フェーズ133の申し送り1点目・2点目に対応し、
  trial-end-scheduler-design.mdの選定ロジック・メッセージ設計を`prototype/`へ実装した。
  `user_id_linking.py`の`UserProfile`/`UserProfileStoreProtocol`/
  `InMemoryUserProfileStore`に`trial_start_at`・`trial_end_notified_at`・`upgraded_at`
  の3フィールドと専用setter(`set_trial_start_at`等、未知の`user_id`にはno-op)を追加した。
  新規`prototype/trial_end_scheduler.py`として、`select_due_trial_end_notifications()`
  (design 3節の抽出条件をそのままコード化)、`build_trial_end_notification_flex_message()`
  (本venture固有のpostbackボタン付きFlex Message組み立て。ボタンのpostbackデータは
  `checkout_session.START_CHECKOUT_POSTBACK_DATA`を再利用し、Checkout Session作成は
  引き続き`process_postback_event()`側の役割とする分離を維持)、`send_trial_end_notifications()`
  (送信成功時のみ`trial_end_notified_at`書き込み、失敗時は次回再試行に委ねる冪等性設計)を
  実装した。テスト29件(test_trial_end_scheduler.py 12件、test_user_id_linking.py新規5件)を
  追加し、venture全体204件のテストがすべて成功することを確認した。トライアル専用生成回数
  カウンタ(`trial_generation_count`の実集計配線)・`handle_checkout_session_completed()`への
  `upgraded_at`書き込み配線・実Cloud Scheduler環境の構築はいずれも次回以降の課題として残る
  (実クラウド接続はオーナー承認待ちの範囲、pending-approval.md参照)。コード実装・テストの
  みで外部サービスへの公開・アカウント作成・支払い等は発生していないためpending-approval.md
  への追記なし。次回は`trial_generation_count`の実集計配線、または`upgraded_at`書き込み配線
  (`handle_checkout_session_completed()`側)を優先候補とする。
- フェーズ133(2026-08-28 00:00 UTC): フェーズ132の申し送り2点目「(B)期間到達判定用の
  日次スケジューラ設計」に着手し、trial-end-scheduler-design.mdを新規作成した。
  course-set-pashaのtrial-end-scheduler-design.md(フェーズ102〜104)を参考にしつつ、
  本venture固有の差分(CTAがLIFF不要のpostbackアクションボタン方式であること、
  通知メッセージ自体もFlex Message組み立てが必要なこと)を整理した。選定ロジック
  `select_due_trial_end_notifications()`の抽出条件(`trial_start_at`設定済み・
  `trial_end_notified_at`未設定・`upgraded_at`未設定・14日経過)を確定し、
  course-set-pashaと同じ安全策(`upgraded_at`書き込み配線が未接続でも二重送信が
  起きない設計)を踏襲した。本フェーズは設計のみで`prototype/`への実装は次回以降の
  課題として残した(UserProfileへの`trial_start_at`等3フィールド追加が実装の前提と
  なるため)。実Cloud Scheduler環境の構築はオーナー承認待ちの範囲(pending-approval.md
  参照)。設計作業のみで、外部サービスへの公開・アカウント作成・支払い等は今回発生
  していないためpending-approval.mdへの追記なし。次回は`UserProfile`への3フィールド
  追加とtrial_end_scheduler.py本体の実装、または`CheckoutSessionClient`実クライアント
  接続に向けた準備を優先候補とする。
- フェーズ132(2026-08-27 23:00 UTC): フェーズ131の残課題1点目に対応し、
  `dispatch_webhook_events()`への`postback`イベント種別の振り分け配線と
  `process_postback_event()`本体(checkout-initiation-flow-design.md 2〜3節)を実装した。
  実Stripe Checkout Session作成API呼び出し自体は実アカウント接続後(オーナー承認待ち)の
  ままだが、`llm_call`/`reply_client`と同じ位置づけの`CheckoutSessionClient`Protocol
  (`create(params) -> str`)を新設し`InMemoryCheckoutSessionClient`スタブで固定URLを返す
  ことで、data判定→user_id取得→user_profile確認→パラメータ組み立て
  (`build_checkout_session_params()`)→URL取得→LINE返信、という一連の処理ロジック自体は
  実接続なしで検証可能にした(course-set-pashaのHTTPレスポンス返却方式と異なり、本venture
  はLINEトーク内完結のため返信文組み立てまでを`process_postback_event()`が担う)。未連携
  user_id(異常系)は既存の`LINKING_REQUIRED_MESSAGE`をそのまま流用し新規メッセージを増やさない
  設計とした。`dispatch_webhook_events()`のignored_types判定から`postback`を除外し(既存の
  follow/message/unfollowと同じ「未接続時は素通り・ignoredには載せない」方針に統一)、
  `receive_webhook()`にも`checkout_session_client`引数を追加した。テスト13件追加
  (`ProcessPostbackEventTest`7件・dispatch経由の新規ルーティング確認2件・既存の
  `ignored_types`関連テスト2件を`postback`が既知種別になったことに合わせて更新)、
  prototype配下全テスト`unittest discover`実行で186件全件パス(既存173件+新規13件)、
  schema/validate_test_cases.pyも9件全件パス。checkout-initiation-flow-design.mdの
  「残課題」を実装済みの記述に更新した。承認不要な設計・実装・テスト追加のみで、外部
  サービスへの公開・アカウント作成・支払い等は今回発生していないためpending-approval.mdへの
  追記なし。次回は`CheckoutSessionClient`実クライアント接続に向けた準備(実Stripeアカウント
  接続後の差し替え手順の明文化等、承認不要な範囲)、または(B)期間到達判定用の日次
  スケジューラ設計を優先候補とする。
- フェーズ131(2026-08-27 22:00 UTC): フェーズ130の申し送り(次回優先候補1点目)の
  決済導線設計に着手し、checkout-initiation-flow-design.mdを新規作成した。
  trial-end-notification-design.md 3節・6節で繰り返し「未確定」と記録されていた
  CTA「▼有料プランへ進む」リンクの実現方式を、course-set-pashaのLIFF IDトークン検証方式
  ではなく**LINEのpostbackアクションボタン方式**に確定した。本ventureはuser-account-
  linking-design.md 4節の前提(Checkout Session作成時点でuser_idは`user_profile`上で
  判明済み)が成立するため、決済ボタンをLINEトーク内のpostbackアクション
  (`data="action=start_checkout"`)として提供すれば、webhook-http-entry-point-design.md
  の署名検証を経た`event["source"]["userId"]`をそのまま認証済みuser_idとして使え、
  LIFFアプリの追加登録・IDトークン検証実装を本ventureでは省略できるという設計判断を行った。
  course-set-pashaのcheckout_session.py(`build_checkout_session_params()`)を参考に
  `prototype/checkout_session.py`を新規実装し(LIFF依存の`create_checkout_session()`相当は
  本venture不要のため実装せず、パラメータ組み立て純粋関数のみ)、テスト6件を追加した。
  あわせて、CI設定(`.github/workflows/aircon-pasha-tests.yml`)がフェーズ26でテスト
  モジュール名を`test_cloud_function_webhook`・`test_post_generation_checks`の2本に
  ハードコードしたまま、フェーズ102前後で追加された`test_deletion_candidate`・
  `test_stripe_dispatch`・`test_stripe_webhook`・`test_user_id_linking`がCI上で
  実行されないまま放置されていたことに気づき、`unittest discover`方式に変更して解消した
  (ci-setup.md追記)。prototype配下全テストを`python3 -m unittest discover -p
  "test_*.py" -v`で実行し178件全件パス(既存171件+新規7件)、schema/validate_test_cases.py
  も9件全件パスを確認した。`dispatch_webhook_events()`への`postback`種別振り分け・
  `process_postback_event()`本体の実装、実Stripe Checkout Session作成API呼び出しは
  次回以降の課題として残した(承認不要)。次回は上記残課題への着手、または(B)期間到達
  判定用の日次スケジューラ設計を優先候補とする。
- フェーズ130(2026-08-27 21:00 UTC): フェーズ129の申し送り(次回優先候補1点目)に対応し、
  trial-end-notification-design.mdで仮置きしていたトライアル開始起点(初回生成成功時)を
  本venture専用ドキュメントとして正式に確定した(trial-start-anchor-decision.md新規作成)。
  course-set-pashaのtrial-start-anchor-decision.md(フェーズ100)と同じ「初回生成成功時」
  という結論を、本venture固有のユーザー動線(フォーム提出→LINE連携→初回生成)に照らして
  個別に再確認し、動線の順序差(本ventureはフォーム提出が先、course-set-pashaはfollowが先)
  が結論に影響しないことを確認した上で確定した。pricing-plan.mdの「導入から14日間」を
  「初回の作業完了報告生成成功から14日間」に表現統一し、trial-end-notification-design.mdの
  「仮置き」表現・6節の未解決課題を解消済みとして反映した。ドキュメント整備のみで
  `prototype/`への実装・Firestoreフィールド追加・外部接続はいずれも次回以降の課題として
  残した(承認不要)。次回はフェーズ129の申し送り2点目だった決済導線設計の着手、または
  (B)期間到達判定用の日次スケジューラ設計を優先候補とする。
- フェーズ129(2026-08-27 20:00 UTC): フェーズ128「未検証・残課題」2点目
  (`usage_counter`側の`upgraded_at`書き込み配線は、本venture側にまだトライアル終了通知の
  実装自体が無いため対象外、という積み残し)に対応し、本venture未着手だったトライアル終了
  通知を設計した(trial-end-notification-design.md新規作成)。course-set-pashaの
  trial-end-notification-design.md(フェーズ99)を参考に、pricing-plan.mdの二重条件
  (期間14日・生成回数10回のいずれか早い方)に基づくトリガー条件・通知文言案・トライアル終了後の
  生成一時停止方針を整理した。本venture固有の差異として、(1)trial-start-anchor-decision.md
  相当の起点確定ドキュメントが本venture未作成のため、course-set-pashaフェーズ100の結論
  (初回生成成功時起点)を同じ理由でそのまま仮置きとして採用した、(2)「浮いた作業時間の目安」
  相当の試算(course-set-pashaのcontent-generation-time-estimate.md相当)が本venture未作成の
  ため通知文言からは今回除外した、(3)決済導線設計(course-set-pashaのcheckout-initiation-flow-
  design.md相当)も本venture未着手のためCTAリンクの具体的な実現方式は未確定のプレースホルダ
  とした、という3点を明記した。いずれもドキュメント設計のみで、`prototype/`への実装・
  Firestoreフィールド追加・外部接続は次回以降の課題として残した(ドキュメント整備のみのため
  承認不要)。次回はtrial-start-anchor-decision.md相当の本venture専用ドキュメント作成による
  (1)の解消、または決済導線設計の着手による(3)の解消のいずれかを優先候補とする。
- フェーズ128(2026-08-27 18:00 UTC): フェーズ127の残課題だった`checkout.session.completed`
  受信配線を設計・実装した(checkout-session-completed-handling-design.md新規作成)。
  user-account-linking-design.md 4節のとおり本ventureはCheckout Session作成時点で
  `client_reference_id`へ既知の`user_id`をそのまま設定できる前提のため、
  course-set-pashaの`handle_checkout_session_completed()`とほぼ同じ処理をそのまま
  踏襲しつつ、本venture固有の安全策として対応する`user_profile`が存在しない場合
  (想定外の順序でCheckout Sessionが作成された異常系)は書き込みを行わず
  `error="user_profile_not_found"`として区別する分岐を追加した。あわせて
  `stripe_customer_id → user_id`の逆引きを担う`make_resolve_user_id()`を新設し、
  `user_id_linking.py`の`UserProfileStoreProtocol`/`InMemoryUserProfileStore`に
  `set_stripe_customer_id()`・`get_user_id_by_stripe_customer_id()`を追加した。
  `receive_stripe_webhook()`に`user_profile_store`引数を追加し、
  `checkout.session.completed`は`dispatch_stripe_event()`ではなく
  `handle_checkout_session_completed()`へ振り分けるよう分岐した(course-set-pashaの
  `receive_stripe_webhook()`と同じ方針)。テスト12件追加(`checkout.session.completed`で
  紐付けた`user_id`を後続の`customer.subscription.deleted`が正しく逆引きできることを
  確認する一気通貫テストを含む)、`prototype/`配下全テスト実行で171件全件パス
  (既存159件+新規12件)、`schema/validate_test_cases.py`も9件全件パスを確認した。
  実Stripeアカウント接続時のCheckout Session作成(`client_reference_id`設定)自体・
  `stripe_customer_id → user_id`逆引きストアの実Firestore実装はいずれも実接続後の
  課題として残る。実接続・課金・外部公開を伴わないコード実装のみのため承認不要。
- フェーズ127(2026-08-27 17:00 UTC): フェーズ126の申し送り通り、Stripe WebhookのHTTP
  エントリポイント本体を設計・実装した。course-set-pashaのstripe-webhook-http-entry-point-
  design.md(フェーズ95)の初期版(`checkout.session.completed`受信配線を含まない範囲)を
  参照し、stripe-webhook-http-entry-point-design.mdとして本venture向けに新規作成した
  (本venture固有の留意点として、user-account-linking-design.mdの連携コード方式は
  course-set-pashaの`client_reference_id`方式と異なり`checkout.session.completed`受信配線が
  別途必要になる点を「残課題」に明記)。`prototype/stripe_webhook.py`に
  `StripeWebhookReceiverResult`・`receive_stripe_webhook()`を追加し、既存の
  `verify_stripe_signature()`(フェーズ125)と`stripe_dispatch.dispatch_stripe_event()`
  (フェーズ126)を薄く結線した(署名検証失敗時は401、JSONパース失敗・非dictは400、
  それ以外は`dispatch_stripe_event()`に委譲し200)。`prototype/test_stripe_webhook.py`に
  `ReceiveStripeWebhookTest`としてテスト5件を追加し(署名不正時401・dispatch未呼び出しの
  確認を含む)、`prototype/`配下の全テスト実行で159件全件パス(既存154件+新規5件)、
  `schema/validate_test_cases.py`も9件全件パスを確認した。`main(request)`相当の実配線・
  `checkout.session.completed`対応・`resolve_user_id`の実装はいずれも未着手のまま
  次回以降の課題として残る(design「残課題」参照)。実接続・課金・外部公開を伴わない
  コード実装のみのため承認不要。
- フェーズ126(2026-08-25 04:00 UTC): フェーズ125の申し送り通り、Stripe Webhookイベント種別
  ディスパッチ設計に着手した。course-set-pashaのstripe-webhook-event-dispatch-design.md
  (フェーズ94)と同一の方針(`customer` → `user_id`解決を`resolve_user_id`として外部注入、
  対応3種別`customer.subscription.deleted/created/updated`のみ処理し他は`ignored_types`に
  記録)を`stripe-webhook-event-dispatch-design.md`として本venture向けに新規作成した。
  course-set-pasha版は設計のみで留まっていたが、本ventureでは同一フェーズ内で
  `prototype/stripe_dispatch.py`に`dispatch_stripe_event()`・`StripeDispatchResult`を
  実装し(既存の`deletion_candidate.py`の3関数をそのまま呼び出す構成)、
  `prototype/test_stripe_dispatch.py`にテスト13件を追加した(3種別の正常系、対象外type、
  customer未解決、`created`欠落/非数値/bool混入、`updated`のstatus別分岐)。`prototype/`
  配下の全テスト実行で154件全件パス(既存141件+新規13件)を確認した。実Stripeアカウント
  接続・Webhookエンドポイント登録・`resolve_user_id`の実ストア実装(実Firestoreクエリ)は
  引き続きスコープ外(design 5節)。実接続・課金・外部公開を伴わないコード実装のみのため
  承認不要。次回はHTTPエントリポイント本体(`receive_stripe_webhook()`、
  `verify_stripe_signature()`と`dispatch_stripe_event()`を結ぶ薄い配線、course-set-pashaの
  stripe-webhook-http-entry-point-design.md フェーズ95相当)、またはllm-quality-
  verification-plan.mdに残る未確定事項(実測前提のため引き続き着手不可)以外で前進可能な
  領域を検討する。
- フェーズ125(2026-08-25 02:00 UTC): フェーズ124の申し送り通り、Stripe Webhook受信口自体の
  設計(署名検証方式)に着手した。course-set-pashaのstripe-webhook-signature-verification-
  design.md(フェーズ93)と同一のアルゴリズム(`Stripe-Signature`ヘッダのt/v1解析、
  HMAC-SHA256署名比較、300秒のタイムスタンプ許容範囲チェック、v1複数時のシークレット
  ローテーション対応、v0無視)を本venture向けに`stripe-webhook-signature-verification-
  design.md`として新規作成した。実Stripeアカウント接続・Webhookエンドポイント登録なしでも
  机上実装・テスト可能な部分のみを対象とし、`prototype/stripe_webhook.py`に
  `verify_stripe_signature()`を新規実装、`prototype/test_stripe_webhook.py`にテスト7件
  (正常系、ヘッダ欠落・不正形式、署名不一致、許容範囲外〈過去・未来〉、シークレット
  ローテーション、v0のみの旧方式)を追加した。`prototype/`配下の全テスト実行で141件全件
  パス(既存133件+新規8件)を確認した。実Stripe
  Webhookイベント種別ディスパッチ・HTTPエントリポイント本体(`receive_stripe_webhook()`
  相当)・`resolve_user_id`(`stripe_customer_id → user_id`解決)は本フェーズのスコープ外の
  まま残る(design「残課題」参照)。実接続・課金・外部公開を伴わないコード実装のみのため
  承認不要。次回はStripe Webhookイベント種別ディスパッチ設計(course-set-pashaの
  stripe-webhook-event-dispatch-design.md フェーズ94相当)、またはllm-quality-
  verification-plan.mdに残る未確定事項(実測前提のため引き続き着手不可)以外で前進可能な
  領域を検討する。
- フェーズ124(2026-08-25 01:00 UTC): stripe-cancellation-deletion-candidate-trigger-design.md
  (削除候補化トリガーの関数設計)「未解決事項・次の課題」に残っていた「本ドキュメント自体は
  プロトタイプ関数の設計のみで、prototype/配下への実コード化・テスト追加は次回以降の候補」
  に対応した。course-set-pasha/prototype/deletion_candidate.py(フェーズ91)と同一の判定
  ロジックを踏襲しつつ、本venture向けのドキュメント参照・コメントに調整した
  `prototype/deletion_candidate.py`(`mark_deletion_candidate_on_subscription_deleted()`・
  `clear_deletion_candidate_on_subscription_reactivated()`・`list_deletion_candidates()`の
  3関数、`InMemoryProfileDeletionCandidateStore`)を新規作成し、
  `prototype/test_deletion_candidate.py`にテスト12件を追加した(course-set-pasha版と同じ
  観点: 365日後への設定・最新解約日での上書き・他ユーザー非干渉・再契約時のクリアと冪等性・
  now以前/以降の境界値・複数候補のuser_id昇順ソート)。`prototype/`配下の全テスト実行で
  133件全件パス(既存121件+新規12件)を確認した。実Stripe Webhook受信エンドポイント自体
  (署名検証・イベント種別ディスパッチ)は引き続き未設計のまま、実Stripeアカウント接続後の
  課題として残る(design 5節)。実接続・課金・外部公開を伴わないコード実装のみのため承認不要。
  次回はStripe Webhook受信口自体の設計(署名検証方式・エンドポイントURL)、または
  llm-quality-verification-plan.mdに残る未確定事項(実測前提のため引き続き着手不可)以外で
  前進可能な領域を検討する。
- フェーズ123(2026-08-25 00:00 UTC): フェーズ122の申し送り通り、オーナーの初回コンタクト
  承認可否を待つ間に前進可能な領域として、決済手数料以外の周辺コスト項目の再確認に着手した。
  unit-economics-estimate.mdの粗利率試算がこれまで決済手数料・Firestore原価・LLM API原価の
  3要素のみで、tech-stack.mdが採用方針とするGCP Cloud Functions自体の実行課金(呼び出し回数・
  実行時間)が一度も試算に含まれていなかった点に気づいた。WebSearchでCloud Functions(第1世代)の
  公開料金情報(無料枠: 呼び出し200万回/月・400,000 GB秒・200,000 CPU秒、超過分は100万回
  あたり0.4米ドル)を確認し、想定規模(最大1,000業者、繁忙期対応プラン上限を全員が毎月
  使い切る極端な前提でも15万回/月程度)では無料枠内に収まる見込みが高いことを試算した
  (unit-economics-estimate.md「Cloud Functions実行課金の原価試算」新設)。実行メモリ・実測
  実行時間に基づく厳密な試算は実装・実測後の課題として残した。ドキュメント整備のみで
  実装・課金・外部接続は伴わない。次回はllm-quality-verification-plan.mdの残る未確定事項
  (不合格基準の緩め・厳しめ調整、temperatureパラメータ選定、いずれも実測が前提のため
  引き続き着手不可)以外で前進可能な領域を検討するか、オーナーの初回コンタクト承認可否を
  待つ間の他の未着手領域を探る。
- フェーズ122(2026-08-24 18:00 UTC): フェーズ121で申し送った次点候補のうち、
  llm-quality-verification-plan.mdの「残る未確定事項」3点目(検証結果の記録先が未確定)に
  対応した。フェーズ118で作成済みのllm-quality-verification-results-template.mdが既に
  記録先・記入方法・記録表様式を確定していたことを確認し、当該項目を「解消済み」として
  llm-quality-verification-plan.md側に取り消し線付きで反映した(参照先の追記のみで、
  新たな設計判断は伴わない整合作業)。これにより実LLM接続承認後にすぐ着手できる状態の
  ドキュメント整備は一通り出尽くした。残る未確定事項2点(不合格基準の緩め・厳しめ調整、
  temperatureパラメータ選定)はいずれも実測が前提のため、引き続きAPIキー取得・課金の
  オーナー承認待ち。次回はcandidate-readiness-summary.md(フェーズ106)に残る実ヒアリング待ち
  事項以外で、初回コンタクト承認可否を待つ間に前進可能な領域(例: subscription-billing-
  cost-estimate.mdの決済手数料以外の周辺コスト項目の再確認等)を検討する。
- フェーズ121(2026-08-24 11:00 UTC): フェーズ112でdata-retention-policy.mdの「今後の課題」に
  残していた「legal-notices-draft.md 2.4節への本方針の要旨反映(未着手)」に対応した。
  data-retention-policy.mdで確定済みの保存期間ポリシー(トライアル中・有料プラン中は保有継続、
  Stripe解約から1年保有後に削除候補化、LINEブロックのみでは削除起点にならない、削除候補化後は
  LINE pushまたはメールでの最終確認を経てから削除、連絡不能な場合は運営者が個別判断)の要旨を
  legal-notices-draft.md 2.4節に反映し、詳細はdata-retention-policy.mdを参照する形に更新した。
  あわせてdata-retention-policy.md側の「今後の課題」該当項目を解消済みとして記録した。
  (2026-08-23付フェーズ115〜120はgit logを参照。フェーズ120でsubscription-billing-cost-
  estimate.mdの決済手数料3.6%一次情報確認まで完了しており、本フェーズが着手可能な範囲での
  ドキュメント整合作業として残っていた最後の明示的な積み残しだった)。ドキュメント整備のみで
  実装・課金・外部接続は伴わない。次回はcandidate-readiness-summary.md(フェーズ106)に残る
  未確認事項(スタッフ数5名以下の直接確認等、実ヒアリング待ち)以外の未着手領域として、
  llm-quality-verification-plan.mdの「残る未確定事項」(検証結果の記録先は既にフェーズ118で
  テンプレート作成済みのため当該記述の更新)、またはオーナーの初回コンタクト承認可否を待つ間の
  他領域の前進を検討する。
- フェーズ114(2026-08-23 17:00 UTC): フェーズ111「design『残課題』に残っていたもう1点
  (`dispatch_webhook_events()`、3つのイベント種別への振り分け経路自体)は未着手のまま残る」に
  対応した。`prototype/cloud_function_webhook.py`に`DispatchResult`(dataclass)・
  `dispatch_webhook_events()`を新規実装し、course-set-pashaの
  webhook-event-dispatch-design.mdと同じ考え方(受信した`events`配列を`event["type"]`ごとに
  各処理関数へ振り分ける単一の入口)を踏襲した。本venture固有の差異として、(1)
  course-set-pashaのtext-image束ね(`merge_text_and_photo_events()`)は本ventureに存在しない
  ため対応する処理は行わない、(2)`process_follow_event()`の引数順序が本venture版
  (`event, reply_client, *, form_link_provider`)のためcourse-set-pasha版と異なる、(3)
  messageイベントの処理条件に`profile_store`・`linking_store`・`now`が必須である
  (連携済みか未連携かの判定自体にこれらが必要なため、course-set-pashaより必須依存が多い)、
  という3点を反映した。未知の種別(postback・join等)は`ignored_types`に記録するのみで
  処理しない。テスト8件を新規作成し(follow/unfollow/message個別振り分け、必須依存未接続時の
  素通り、未知種別の記録、複数種別混在時の独立処理)、既存101件と合わせて全109件パスを
  確認した(`prototype/test_cloud_function_webhook.py`)。これによりuser-account-linking-
  design.md 3節・follow-unfollow-event-handling-design.mdで挙げられていた「未実装のまま
  残る」項目は解消され、本venture全体の残る大きな課題は実LLM/実LINE API/実Cloud Functions
  デプロイ自体(オーナー承認待ち、pending-approval.md 2026-08-23 04:00 UTC参照)のみとなった。
- フェーズ113(2026-08-23 15:00 UTC): フェーズ111・112の申し送り(follow/unfollow実装後の
  残課題2点のうちの1つ)を受け、user-account-linking-design.md 3節で設計していた
  「follow後の1:1トークで受信したテキストが連携コードか施工メモかを判定する分岐」を実装した。
  course-set-pashaのprototype/user_id_linking.pyを踏襲しつつ、本venture固有の紐付けの向き
  (design 1節: フォーム送信時点でコード発行、LINE側で受信して初めてuser_idが判明)に合わせ、
  新規prototype/user_id_linking.pyに`PendingLink`/`LinkingCodeStoreProtocol`/
  `UserProfile`/`UserProfileStoreProtocol`/`issue_linking_code_on_form_submission()`/
  `resolve_linking_code()`/`purge_expired_links()`を実装した(course-set-pasha版と異なり、
  `resolve_linking_code()`は`code`だけでなく`user_id`も受け取り、解決成功時に`user_profile`を
  新規作成するところまで一体で行う)。あわせてcloud_function_webhook.pyに
  `process_message_event()`を新設し、design 3節の分岐(連携済みなら`process_memo_event()`へ
  委譲、未連携なら受信テキストが`pending_links`の辞書引きに一致するかのみで連携コードと判定し、
  一致すれば連携完了案内、一致しなければ「先に連携コードの送信が必要です」という案内を返す)を
  実装した。design 3節の「解決失敗時の案内文言は次回以降の課題」との記載通り、連携コード自体が
  見つからない場合と未連携のまま施工メモを送った場合とで文言を区別する根拠が無いため、
  現時点では両者に同一の案内文言(`LINKING_REQUIRED_MESSAGE`)を返す仕様とした。
  test_user_id_linking.py(11件)・test_cloud_function_webhook.pyへの
  `ProcessMessageEventLinkingTest`追加(6件)含め、prototype配下の全テスト実行(101件パス)を
  確認した。design「残課題」に残っていたもう1点(`dispatch_webhook_events()`、3つのイベント
  種別への振り分け経路自体)は未着手のまま残る。次回はこちらへの着手、または連携失敗時の
  確定文言のtone-and-manner-guideline.md整合確認を優先候補とする。
- フェーズ111(2026-08-23 10:00 UTC): フェーズ110の申し送り通り、follow-unfollow-event-
  handling-design.md(フェーズ109)で設計済みだった`process_follow_event()`・
  `process_unfollow_event()`をprototype/cloud_function_webhook.pyに実装した。
  followイベントは本venture固有の「フォーム送信 → LINE友だち追加」の順序(コード発行済み)
  を反映し、course-set-pashaと異なり連携コードを発行しない固定文言のウェルカムメッセージ
  (`format_welcome_message()`、`ApplicationFormLinkProvider`/`InMemoryApplicationFormLinkProvider`
  経由でフォームURLを差し込み、未接続時はプレースホルダのまま返す)を返信する構成とした。
  unfollowイベントはdesign 2節「決定のまとめ」通り、`pending_links`・`user_profile`・
  `usage_counter`のいずれにも一切アクセスせず`handled=True`を返すだけの薄い実装とし、
  course-set-pasha版のような`linking_store`引数自体を持たせないことで「削除処理が
  存在しないこと」を構造的に保証した。design「プロトタイプ実装方針」で挙げられていた
  最低3ケース(follow正常系、form_link_provider未接続/接続時のURL差し替え、unfollow時に
  データ変更が発生しないこと)に加え、userId欠落時・イベント種別不一致時の防御的分岐も
  含めテストを追加し(test_cloud_function_webhook.py、ProcessFollowEventTest・
  ProcessUnfollowEventTest新設)、全50件パスを確認した。_demo()にもfollow/unfollow
  イベントの実行例を追加した。design「残課題」に残っていた3項目のうち、本フェーズでは
  follow/unfollow処理本体のみに着手し、(1)`dispatch_webhook_events()`(3つのイベント種別
  への振り分け経路自体)、(2)`process_message_event()`相当(follow後の1:1トークで受信した
  テキストが連携コードか施工メモかを判定する分岐、user-account-linking-design.md 3節)は
  未実装のまま残る。次回はこのうちどちらかへの着手、または候補研究の残る未確認事項
  (スタッフ数5名以下の直接確認等)の整理を優先候補とする。
- フェーズ112(2026-08-23 14:00 UTC): フェーズ108でdata-retention-policy.md作成時点では
  未設計だったため「未決定」のまま切り出していた「LINEブロック(unfollow)時の`user_profile`・
  `usage_counter`の扱い」を、その後フェーズ109・111で確定したfollow-unfollow-event-handling-
  design.mdの内容(unfollow時は`pending_links`・`user_profile`・`usage_counter`のいずれにも
  一切アクセスしない)を踏まえて更新した。保存期間ポリシー表の該当行を「保有継続」で確定させ、
  削除候補化後の最終確認(LINE push経路)の記述もブロック中は送達不可であることが確定した旨に
  更新し、「今後の課題」の該当項目を解消済みとして記録した。data-retention-policy.mdの新規作成
  ではなく、フェーズ108時点で明示的に切り出されていた残課題1点を解消する更新のみで、
  legal-notices-draft.md 2.4節への反映は引き続き未着手のまま次回以降の課題として残る。
- フェーズ110(2026-08-23 07:00 UTC): interview-rehearsal-script.mdがフェーズ104
  (customer-interview-design.mdへのQ11〈SNS絵文字質問〉新設、全13問→全14問)の反映漏れで
  古い13問構成のまま放置されていた不整合を発見・解消した。フェーズ104のREADME記載では
  「実施方法の所要時間目安・未検証の仮説・次のステップ候補の各節にあった『13問』表記も
  整合するよう更新した」とあったが、実際にはcustomer-interview-design.md自体は更新されて
  いたものの、別ファイルのinterview-rehearsal-script.mdは対象に含まれておらず、旧Q11
  (フランチャイズ向け設問)以降の番号(旧Q11→Q12、旧Q12→Q13、旧Q13→Q14)がずれたまま
  だった。想定タイムテーブル(全14問・目標13分に更新、C区分に新Q11の3.5分を追加)、
  オープニング読み上げ台本の問数表記、質問ごとの補足ト書きへの新Q11(SNS発信状況の
  一言確認→非該当ならスキップする運用)の追加、確認ポイントチェックリスト、候補3・7・10・
  12・13・14向けの調整セクション全てで番号を整合させた。あわせて、候補14(FC名物45日研修
  講師)はブログでの継続的自己発信は確認済みだがInstagram等の絵文字を使うSNSでの発信は
  未確認である点を明記し、媒体の違い(ブログかInstagram等か)を区別せず該当有無を断定
  しないよう申し送った。ドキュメント整備のみで実装・課金・外部連絡は伴わない。次回は
  follow/unfollowイベント処理(フェーズ109の申し送り)のprototype/cloud_function_webhook.py
  への実装、または候補研究の残る未確認事項(スタッフ数5名以下の直接確認等)の整理を
  優先候補とする。
- フェーズ109(2026-08-23 05:00 UTC): フェーズ108の申し送り通り、follow/unfollowイベント
  受信時の扱いを設計した(follow-unfollow-event-handling-design.md新規作成)。(1)follow時の
  ウェルカムメッセージは、本ventureはフォーム送信完了時点で既にコード発行済み
  (user-account-linking-design.md 2節)のため、course-set-pashaと異なりコードを埋め込む
  必要がなく固定文言のみで足りることを確認した。(2)unfollow時の扱いはcourse-set-pashaの
  unfollow-event-handling-design.mdを参考にしつつ、本venture固有の差異を発見した:
  `pending_links`がフォーム送信時点(まだfollowしていない段階)で発行されるため`user_id`
  フィールドを持たず、unfollowイベントからは対応する`pending_links`エントリを特定できない。
  course-set-pashaのような`delete_pending_links_for_user()`は適用できないため、本venture版は
  「何もしない(24時間の自然失効に委ねる)」という結論とした。`user_profile`・`usage_counter`・
  Stripe課金の扱いはcourse-set-pashaと同じ(保持・自動解約しない)。ドキュメント整備のみで
  実装は未着手。次回はfollow・unfollow・コード判定分岐(施工メモとの区別)をまとめて
  prototype/cloud_function_webhook.pyへ実装する作業を優先候補とする。
- フェーズ108(2026-08-23 04:00 UTC): フェーズ107のuser-account-linking-design.mdが「残課題」
  として残していた2点に対応した。(1)legal-notices-draft.md 2.4節で保留していた「契約終了後の
  データ保存期間」を、確定済みの3コレクション(`pending_links`・`user_profile`・
  `usage_counter`)を前提に整理したdata-retention-policy.mdを新規作成(course-set-pashaの構成を
  踏襲、Stripe解約日起点で1年保有後に削除候補化する方針。ただし本ventureはunfollowイベント
  処理自体が未設計のため、course-set-pashaと異なり「ブロック時の扱い」は未決定のまま明示的に
  切り出した)。(2)pending-approval.mdに、フォーム送信完了時の連携コード発行を実現するための
  Googleフォーム作成・GAS Webhookデプロイの承認待ち事項を追記(course-set-pashaの同種案件と
  同じ範囲を想定)。ドキュメント整備のみで実装・課金・外部接続は伴わない。次回はunfollow
  イベント処理設計(follow時のウェルカムメッセージ分岐と合わせた検討)、またはコード判定ロジック
  (6文字・辞書引き一致)の境界値をprototype化して机上検証する作業を候補とする。
- フェーズ107(2026-08-23 03:00 UTC): subscription-cancellation-flow-design.mdで指摘されたまま
  未設計だった「Stripe Webhookで受信した最新のプランIDへの紐づけ」、およびtech-stack.mdコンポーネント5が
  前提としていた「usage_counterのみが唯一の永続データ」という整理の不正確さに対応し、
  申込フォーム・LINE・Stripeのアカウント紐付け設計を新規作成した(user-account-linking-design.md)。
  course-set-pashaの連携コード方式(line-user-id-linking-design.md)を参考にしつつ、本ventureは
  「1.申込フォーム→2.LINE友だち追加」という順序が既に確定しているため紐付けの向きを反転させ、
  フォーム送信完了時に発行した連携コードをLINE初回メッセージで送ってもらう方式とした。あわせて、
  Stripe決済(オンボーディングのステップ6)がLINE連携完了より後に発生する本venture固有の構造を
  活かし、Checkout Session作成時に`client_reference_id`へ既知のuser_idをそのまま設定することで
  course-set-pashaのような決済後の逆引き連携コードが不要になる点を整理した。新設が必要な
  `pending_links`・`user_profile`の2コレクション(`usage_counter`と合わせ計3コレクション)を
  表形式で確定し、tech-stack.mdコンポーネント5に追記した。ドキュメント整備のみで実装・課金・
  外部接続は伴わない。次回はuser-account-linking-design.mdを前提としたdata-retention-policy.md
  (legal-notices-draft.md 2.4節で保留していた課題)の新規作成、または候補12関連・
  llm-quality-verification-plan.mdの精緻化等、オーナーの初回コンタクト承認可否を待つ間の
  他領域の前進を検討する。
- フェーズ106(2026-08-22 22:00 UTC): フェーズ104・105の申し送りだった「候補12関連」の
  確認として、candidate-longlist-draft.md(第1〜58弾)・initial-contact-message-draft.mdを
  突き合わせたところ、独立系5候補(候補1・3・7・10・12)・フランチャイズ加盟3候補
  (候補2・13・14)いずれも屋号・所在地・連絡チャネルの一次情報確認が既に完了しており、
  新規のWebSearch調査は不要と判明した。オーナーが承認可否を判断しやすいよう
  candidate-readiness-summary.mdを新規作成し、8候補の連絡チャネル確定状況・残る未確認事項
  (スタッフ数5名以下の直接確認、候補1のドメイン選択、候補7のフォーム有無)を一覧化した。
  これらの未確認事項はWebSearchでの追加調査が繰り返し頭打ちになっている(候補11・12と同傾向)
  ため、ヒアリング実施時に自然に確認する運用とする方針を記録した。ドキュメント整理のみで
  実装・課金・外部連絡を伴わない範囲にとどめた。次回はcharacter-limit-fallback-design.mdの
  残る1点(実LLM接続待ちのため引き続き着手不可)、llm-quality-verification-plan.mdの精緻化、
  またはオーナーの初回コンタクト承認可否を待つ間の他領域の前進を検討する。
- フェーズ105(2026-08-22 21:00 UTC): character-limit-fallback-design.mdの残課題3点目
  だった、LINE文字数上限(5,000文字、UTF-16コード単位)超過時のフォールバック処理の実装に
  着手した。prototype/post_generation_checks.pyに`check_message_length_within_line_limit()`
  を新設し(`_utf16_code_unit_length()`でUTF-16コード単位を算出、completion_report.body・
  care_guide.bodyをそれぞれ判定)、`run_all_checks()`に組み込んだ。エラーメッセージには
  `LENGTH_LIMIT_ERROR_PREFIX`を付与し、cloud_function_webhook.py側で他の検証エラーと
  区別できるようにした。process_memo_event()の最終フォールバック分岐で、検証エラーに
  文字数上限超過が含まれる場合は汎用のVALIDATION_FAILURE_FALLBACK_MESSAGEではなく、
  設計ドキュメント記載の例文通りの`LENGTH_LIMIT_FALLBACK_MESSAGE`(業者向け・入力メモの
  短縮を促す固定文言)を返すよう分岐した。設計方針(切り詰めは行わない)通り、上限超過時は
  部分的な内容であっても依頼者へは一切送信しない。この実装自体は純粋なテキスト処理・
  分岐ロジックであり実LLM・実LINE API接続を必要としないため、これまで「オーナー承認待ちの
  ため未着手」としていた項目のうち着手可能な部分だと判断した(course-set-pashaのStripe
  署名検証実装等と同じ考え方、実際の課金・外部送信を伴う接続作業自体は引き続き承認待ちの
  まま変更なし)。post_generation_checks.py側にサロゲートペア文字(基本多言語面外)を使った
  UTF-16コード単位カウントの境界値テストを含むテスト13件、cloud_function_webhook.py側に
  上限超過時のフォールバック文言選択を確認するテスト1件を追加し、プロトタイプ全体75件・
  schema検証9件をいずれも実行して全件パスを確認した。次回はcharacter-limit-fallback-
  design.mdの残る1点(ソフトな閾値設定の要否、実LLM接続後の生成品質検証で実測データを見て
  検討)、候補12関連、またはオーナーの初回コンタクト承認可否を待つ間の他領域の前進を検討する。
- フェーズ104(2026-08-22 18:00 UTC): フェーズ103の申し送り(tone-and-manner-guideline.md
  「未検証の仮説」2点目、sns-blog-example-observation.mdフェーズ100で確認した「独立系業者
  自身のSNS発信は絵文字を積極的に使う傾向がある」という観察が、本サービスの出力(絵文字
  不使用)への評価にどう影響するかがcustomer-interview-design.mdのヒアリング項目に未反映、
  という積み残し)に対応した。customer-interview-design.mdの「C. 内容・体験の検証」に
  質問11(普段SNSで絵文字を使って発信している業者向けに、本サービスの絵文字不使用・事務的な
  文体を「実務連絡として適切」と感じるか「素っ気ない」と感じるかを問う設問)を新設し、
  全13問→全14問に変更した(course-set-pashaの14問と同水準)。既存のD区分(導入障壁・競合の
  確認)の質問番号を11〜13から12〜14に繰り下げ、実施方法の所要時間目安・未検証の仮説・
  次のステップ候補の各節にあった「13問」表記も整合するよう更新した。tone-and-manner-
  guideline.mdの「未検証の仮説」2点目にも本反映が完了した旨を追記し、実際の回答傾向の
  確認自体は実ヒアリング実施(オーナー承認待ち)まで引き続き未検証のまま残る旨を明記した。
  ドキュメント整備のみで実装・課金を伴わない範囲にとどめた。次回は候補12関連(フランチャイズ
  加盟候補2・13・14の連絡チャネル確認要否整理)、character-limit-fallback-design.md
  「残課題」3点目(`check_message_length_within_line_limit()`のprototype/post_generation_
  checks.pyへの実装・配線、実LLM・実LINE API接続待ちのため引き続き未着手)、またはオーナーの
  初回コンタクト承認可否を待つ間の他領域の前進を検討する。
- フェーズ103(2026-08-22 15:00 UTC): フェーズ102の残課題だった「フォールバック通知文言の
  最終確定(トーン&マナーガイドラインとの整合確認)」に対応し、本ventureにまだ無かった
  tone-and-manner-guideline.mdを新設した(line-reservation-ai/tone-and-manner-guideline.mdの
  構成を踏襲)。依頼者向け文面(completion_report.body・care_guide.body)と業者向け内部
  メッセージ(接続テスト確認案内・入力不足再送依頼・フォールバック通知・解約/プラン変更案内・
  意思確認応答)の2種類を明確に区別する基本方針を軸に、これまで個別に設計してきた業者向け
  文言を一覧化して確認したところ、いずれも絵文字不使用・ですます調で統一されていたことを
  確認した。character-limit-fallback-design.mdのフォールバック通知例文(「生成結果が長く
  なりすぎたため…」)はこのガイドラインと整合しており確定文言として扱ってよいと結論し、
  同ファイルの残課題1点目を解消済みとした。あわせて、フェーズ100で確認した「独立系業者
  自身のSNS発信は絵文字を積極的に使う傾向がある」という観察が本サービスの絵文字不使用方針の
  評価にどう影響するかは、customer-interview-design.mdのヒアリング項目に未反映のままである
  ことを新たな未検証事項として記録した(次回以降の反映候補)。ドキュメント整備のみで
  実装・課金を伴わない範囲にとどめた。
- フェーズ102(2026-08-22 12:00 UTC): フェーズ101の残課題「極端に長い入力メモによる
  文字数上限(5,000文字、UTF-16コード単位)超過時のフォールバック処理」を設計した
  (character-limit-fallback-design.md新規作成)。依頼者へ直接転送される
  `completion_report.body`・`care_guide.body`は誤送信事故リスクを避けるため切り詰めて
  送信する案を採用せず、上限超過時は生成全体を失敗として扱い、業者向けにのみ固定文言の
  フォールバック通知(入力メモを短くして再送を促す)を返す方針とした。あわせて、Python
  の`len()`がUnicodeコードポイント数を返しUTF-16コード単位数と一致しない場合がある点
  (補助文字面の文字はサロゲートペアで2カウント)を実装上の注意として明記し、
  `len(text.encode('utf-16-le')) // 2`でのカウント方式を推奨した。ドキュメント設計のみで
  承認不要な範囲にとどめた。`post_generation_checks.py`への実装・配線は実LLM・実LINE API
  接続がオーナー承認待ちのため未着手。次回はフォールバック通知文言のトーン&マナー整理
  (tone-and-manner-guideline.md相当のドキュメントが本ventureに未整備のため他venture参考に
  新設するか検討)、または候補12関連・他の未着手領域の前進を検討する。
- フェーズ101(2026-08-22 09:00 UTC): フェーズ100の申し送りのうち「実LINE接続後の複数
  メッセージ送信のAPI仕様先行調査」を実施した。LINE Developers公式ドキュメント
  (Send messages、Character counting in a text)をWebSearchで確認し、(1)1回の応答
  (reply token)で送信できるメッセージオブジェクトは最大5件までであり、本ventureの
  初回生成時の最大送信数(completion_report_message・care_guide_message・
  SELF_CHECK_NOTICE_TEXTの3件)は上限内に収まること、(2)テキストメッセージ1件あたりの
  文字数上限は5,000文字(UTF-16コード単位)であることを確認した。この結果を
  first-generation-self-check-design.mdの「残課題」に記載していた「別吹き出し必須制約が
  メッセージ数上限と衝突しないか」という懸念点に反映し解消した(新設の「LINE Messaging
  API のメッセージ数・文字数上限確認」節参照)。一方、極端に長い入力メモによる文字数上限
  超過時のフォールバック処理は新たな未設計事項として残した。ドキュメント整理と公開情報の
  確認のみで承認不要な範囲にとどめた。次回は候補12(東京住まいる)の連絡先確認を継続するか、
  新たに残った文字数上限超過時のフォールバック設計に着手するか、オーナーからの初回コンタクト
  承認可否を待つ間の他の未着手領域を検討する。
- フェーズ100(2026-08-22 05:00 UTC): フェーズ99の申し送り「aircon-pasha自体の未着手領域
  (オーナーからの初回コンタクト承認可否を待つ間の別の前進策)を検討する」に対応し、
  onboarding-guide.mdの「次のステップ候補」に残っていた「ステップ3(接続テスト)省略時の
  フォールバック設計(course-set-pashaのonboarding-settings-and-self-check-design.md・
  first-generation-notice-implementation-design.md相当)の要否・内容」を検討した。
  `first-generation-self-check-design.md`を新規作成し、(1)本ventureもcourse-set-pashaと同じ
  単方向バッチ処理のため同じ設計方針(初回生成成功時のみレスポンス末尾に確認案内を1回だけ
  付記)を採用できると結論、(2)一方で本ventureの出力1・出力2(作業完了報告・お手入れ案内)は
  業者がそのままコピー&ペーストで依頼者(エンドカスタマー)へ転送する運用が正規ルートである
  (course-set-pashaのSNS投稿文はオーナーが一手間置いてから投稿する)ため、確認案内を
  `completion_report.body`等の転送されうるフィールド内部に混入させることは「依頼者への
  誤送信事故」に直結する本venture固有のリスクである点を明記し、確認案内は必ず別メッセージ
  (別吹き出し)としてレスポンス組み立て時に付加する設計を必須要件とした、(3)本ventureは
  屋号・エリア設定項目自体が無いため、course-set-pashaにあった「未設定項目案内」の分岐は
  不要と整理した。`usage_counter`への`first_generation_notice_sent`フィールド追加案・
  疑似コードもcourse-set-pashaのパターンを踏襲する形で示したが、実装はFirestore・LINE API
  接続がオーナー承認待ちのため未着手のまま残す。ドキュメント整理のみで承認不要な範囲に
  とどめた。次回は候補12(東京住まいる)の連絡先確認を継続するか、実LINE接続後の複数メッセージ
  送信のAPI仕様(本ドキュメント「残課題」参照)を先行調査するか、オーナーからの初回コンタクト
  承認可否を待つ間の他の未着手領域を検討する。
- フェーズ99(2026-08-22 01:00 UTC): フェーズ98の申し送りのうち「屋号・ドメイン類似による
  誤結合」教訓の他venture横展開を進めた(もう一方の申し送りだったllm-quality-verification-
  plan.mdの他venture展開は、直前の定例更新でline-reservation-aiにも作成済みとなり両venture
  で完了している)。course-set-pasha・line-reservation-aiのinterview-candidate-selection-
  criteria.mdに、aircon-pashaの候補1・7・8・12で4件連続発生した「WebSearchのAI要約が類似の
  屋号・ドメインを持つ無関係な別会社の情報を候補の情報として誤って返す」事例と、その対策
  (公式ドメイン・掲載ページURLと情報源URLの一致確認を必須手順とする、一致しない情報は
  「未確認」のまま残す)を、それぞれの業種(クライミングジムのチェーン展開、美容室・整体院等の
  同名店舗)に合わせて追記した。ドキュメント整理のみで承認不要な範囲にとどめた。次回は
  course-set-pasha・line-reservation-aiの実際の候補探索で、追記した注意手順が実際に機能するか
  (今後の候補調査で同種の誤結合を未然に防げているか)を確認するか、aircon-pasha自体の
  未着手領域(オーナーからの初回コンタクト承認可否を待つ間の別の前進策)を検討する。
- フェーズ98(2026-08-21 20:00 UTC): フェーズ97の申し送りのうち「実LLM接続後の生成品質検証
  設計」を前進させた。output-samples-validation.mdの「残る未検証事項」節に積み残されていた
  論点(厳守事項1・2・7・6aの遵守率、厳守事項4のデフォルト目安粒度等)を、llm-system-prompt-
  draft.mdの厳守事項1〜8・6aと突き合わせて整理し、機械チェック可能な項目(post_generation_
  checks.py・schema/validate_test_cases.pyの既存ロジックで判定可能なもの)と人手判定が必要な
  項目(効果の推測付け足しの有無等、否定の証明を機械チェックできないもの)を区別した
  `llm-quality-verification-plan.md`を新規作成した。人手判定項目は同一入力で最低3回生成し
  3回中1回でも厳守事項抵触があれば要改善とする暫定基準も定めた。ドキュメント整理のみで
  APIキー取得・課金を伴わないため承認不要な範囲にとどめ、実際のLLM API呼び出しは引き続き
  オーナー承認待ち。次回は本プランをcourse-set-pasha・line-reservation-aiにも同様の形で
  展開するか、フェーズ97のもう一方の申し送り(「屋号・ドメイン類似による誤結合」教訓の
  他venture横展開)を優先するかを判断する。
- フェーズ97(2026-08-21 19:00 UTC): フェーズ96の申し送り通り、候補12(東京住まいる/
  tokyo-smile.jp)の連絡先確認をtokyo-smile.jpドメイン限定のWebSearchで再試行した
  (candidate-longlist-draft.md第五十八弾)。運営会社(株式会社アクシル、東京都千代田区
  麹町、代表・永澤史博氏、2015年3月設立)を一次情報で再確認した上で、tokyo-smile.jpの
  トップページ自体に申込フォームが組み込まれており、フォーム送信後にスタッフから折り返し
  連絡が来る方式であることを新たに確認した。専用の電話番号・メールアドレスは
  引き続き未特定(WebFetchのegress制約でtokyo-smile.jp本体を直接閲覧できないため)だが、
  初回コンタクト手段としては「トップページ申込フォーム」という具体的な経路が確定した。
  無関係な別会社(tokyo-smile.co.jp、株式会社東京スマイル)の電話番号・会社概要を候補12の
  ものと誤認しないよう改めて注意喚起した上で、initial-contact-message-draft.mdの候補12の
  記載を更新した。これにより独立系候補(候補1・3・7・10・12)は全件で何らかの連絡チャネルが
  判明した状態に達した。次回は「屋号・ドメイン類似による誤結合」の教訓の他venture(course-
  set-pasha・line-reservation-ai)への横展開要否の検討、またはオーナーからの初回コンタクト
  承認可否を待つ間の他の未着手領域(実LLM接続後の生成品質検証設計等)の前進を優先する。
- フェーズ89(2026-08-21 02:00 UTC): candidate-longlist-draft.md第五十五弾の申し送り通り、
  候補1(rhinohands.com/リノハンズ)の運営者名確認をWebSearchで再試行した。運営者名が
  「永岡裕隆」(店長・代表、32歳、ハウスクリーニング歴3年、作業実績3000件以上)、所在地が
  「熊本県熊本市中央区下通1-3-8」であることを複数の自社ページ(company-overview/、
  greeting/等)のスニペット要約の一致により確認した。従業員数の直接的な一次情報は
  得られなかったが、rhinohands.com/partner/「協力店募集中」ページの存在から、自社雇用の
  多数スタッフではなく外部協力店との提携モデルである可能性が示唆され、必須条件
  (スタッフ数5名以下)への該当を支持する間接傍証と評価した。候補1は独立系候補の中で
  最も情報が整った候補となったため、次回は候補10・12のスタッフ数確認、または独立系候補の
  情報充足を踏まえた初回コンタクト文面の下書き着手条件の再確認のいずれかを優先する。
  詳細はcandidate-longlist-draft.md第五十六弾参照。
- フェーズ88(2026-08-20 23:59 UTC): candidate-longlist-draft.md第五十四弾の申し送り通り、
  独立系候補のスタッフ数(5名以下)確認について「求人情報・口コミ等の間接的な手がかり」への
  探索軸切り替えを候補7(Clean Labo)・候補3(快線屋)で試行したが、いずれも自社の求人掲載は
  見つからず新情報の増分はなかった(第五十五弾参照)。一方で候補1(rhinohands.com)について
  検索したところ、屋号「リノハンズ」・対応エリア(熊本県・福岡県南部)という副産物的な新情報を
  確認できた(運営者名候補「永岡」・スタッフ数は依然未確認、いずれもスニペット経由で
  一次情報未確認)。求人情報の有無という間接軸自体は候補7・3で早々に頭打ちとなったため、
  次回は候補1の運営者名・スタッフ数確認を優先するか、候補研究以外の未着手領域(初回
  コンタクト文面の下書き着手条件の再確認)へ切り替えるかを判断する。詳細は
  candidate-longlist-draft.md第五十五弾参照。
- フェーズ87(2026-08-20 22:00 UTC): course-set-pasha・line-reservation-aiには既にある
  「申込からLINE公式アカウントでの生成開始まで」を整理したオンボーディングガイドが本ventureに
  未作成だったギャップに対応し、onboarding-guide.mdを新規作成した。course-set-pashaの構成を
  踏襲しつつ、本ventureの出力1・出力2は依頼者本人1名への直接報告・案内でありSNS投稿を含まない
  ため(llm-system-prompt-draft.md・schema/output.schema.jsonを確認し、屋号・エリアを反映する
  フィールドが存在しないことを本フェーズで確認)、course-set-pashaの「ジム名・地域名の初期登録
  (任意)」ステップに相当する項目が本ventureには存在しない点を明記し、他venture比でオンボー
  ディングが最も軽量である旨を整理した。
- フェーズ86(2026-08-20 20:00 UTC): 候補研究がegress制約で3課題(候補3・8・9)とも
  一次情報未到達で行き詰まっていたため、今回は研究を離れコード側を前進させた。
  prototype/post_generation_checks.pyに、厳守事項4関連の追加ヒューリスティックチェック
  check_next_recommended_date_history_care_guide_consistencyを実装した。既存の
  check_next_recommended_date_estimate_consistencyが本文(打消し文言)側との整合を
  見るのに対し、新チェックはcare_guide.next_recommended_date_is_estimate=false
  (メモ由来の具体的な次回目安)と主張しながらhistory_row.next_recommended_dateが
  空という構造化データ側の不整合を検出する。run_all_checksに組み込み、テスト4件を
  追加して全19件パス(webhook側30件も回帰なし)。
- フェーズ1(2026-08-09 13:00 UTC): venture新規作成。ideas.mdの原案(2026-08-09 06:00 UTC)を
  ベースに、市場調査の一次整理(market-research.md)とMVPの入出力フォーマット草案
  (mvp-flow-draft.md)を作成した。course-set-pasha(ボルダリングジム向け同種サービス)で
  確立した「メモ入力→複数下書き生成」のMVP設計パターンを踏襲しつつ、対象業種固有の
  差異(号数・機種系統・防カビコート・冷媒/電気系統への言及回避)を反映した。
- フェーズ2(2026-08-09 14:00 UTC): LLM生成エンジンのシステムプロンプト草案
  (llm-system-prompt-draft.md)を作成した。course-set-pashaの厳守事項リスト形式を踏襲し、
  「冷媒・電気系統への専門的助言を行わない」「メモに無い効果を推測で付け足さない」等を
  厳守事項として明文化した。構造化出力(JSON Schema)については方針のみ整理し、
  実ファイルの作成は次回以降の課題とした。
- フェーズ3(2026-08-09 15:00 UTC): 構造化出力スキーマ(schema/output.schema.json)を
  作成した。llm-system-prompt-draft.mdの方針通り、course-set-pashaのstatus分岐
  (generated/out_of_scope/insufficient_input)パターンを踏襲しつつ、history_rowは
  course-set-pashaのような配列化はせず単一オブジェクトのままとした(1メモ=1件の訪問施工が
  前提のため)。厳守事項1(冷媒・電気系統への言及回避)の検証用フィールドとして
  completion_report.mentions_refrigerant_or_electricalを、厳守事項4(次回推奨時期が
  一般的目安か入力メモ由来かの区別)の検証用フィールドとしてcare_guide.
  next_recommended_date_is_estimateを追加した。python3のjson.loadで構文検証済み
  (実LLM出力での適合性検証は未実施)。
- フェーズ4(2026-08-09 16:00 UTC): 期待JSON出力サンプル(status別5パターン、
  output-samples-validation.md)と机上バリデータ(schema/validate_test_cases.py)を作成した。
  course-set-pashaのvalidate_test_cases.pyと同じ簡易バリデータ方式を踏襲しつつ、本venture
  固有のクロスフィールドルールとして、care_guide.next_recommended_date_is_estimateが
  false(入力メモに次回推奨時期の記載あり)の場合はhistory_row.next_recommended_dateが
  null不可であることの検証を追加した。5件中5件パスを確認(python3実行済み、実LLM検証は未実施)。
- フェーズ5(2026-08-09 17:00 UTC): 料金プラン・無料トライアル条件の仮決め(pricing-plan.md)
  を作成した。course-set-pashaのプラン設計方針を踏襲しつつ、market-research.mdの利用量見積もり
  (個人事業主で月60〜100件程度)を踏まえ、course-set-pashaより一桁多い生成回数を前提とした
  3プラン(基本料+従量課金の併用)を設計した。繁忙期(梅雨〜夏)の季節性が強い業種のため、
  月固定枠の超過分は従量課金で吸収する設計とし、繰越の要否・従量単価の妥当性は未検証事項として
  整理した。
- フェーズ6(2026-08-09 18:00 UTC): 実在のエアコンクリーニング業者・関連情報サイトの
  公開情報をWebSearchで観察し(sns-blog-example-observation.md新規作成)、
  llm-system-prompt-draft.mdの厳守事項3(動作確認への言及)・厳守事項4(次回推奨時期の
  デフォルト目安の粒度、自己分解洗浄リスクの注意喚起の具体的方向性)に反映した。
  個人事業主・独立系業者に絞った実例は今回も直接は見当たらず、業界大手・情報サイトの
  解説記事が中心の観察に留まった(course-set-pashaのsns-tone-research.mdと同じ傾向)。
- フェーズ7(2026-08-09 20:00 UTC): 想定顧客ヒアリング設計(customer-interview-design.md)を
  新規作成した。course-set-pashaのヒアリング設計方針(目的→対象選定→質問項目→実施方法→
  留意点)を踏襲しつつ、本venture固有の論点(pricing-plan.mdの季節性・従量課金設計の妥当性、
  llm-system-prompt-draft.mdの厳守事項1(冷媒・電気系統への言及回避)の現場実務との整合性、
  独立系業者とフランチャイズ加盟業者の導入意欲の差)を反映した全13問の質問案を整理した。
  対象は独立系4〜5件・フランチャイズ加盟2〜3件・複合メニュー業者2件の計8〜10件を想定。
  実在業者への連絡はオーナー承認が必要な範囲のため、設計のみに留めた。
- フェーズ8(2026-08-09 21:00 UTC): ヒアリング対象候補の選定基準・情報源
  (interview-candidate-selection-criteria.md)を新規作成した。course-set-pasha・
  line-reservation-aiの同名ドキュメントの構成(必須条件→望ましい条件→除外条件→情報源→
  選定プロセス)を踏襲しつつ、本venture固有の除外条件(全国チェーン直営・コールセンター
  一括受注で現場作業員個人が報告文作成主体でない業者)と情報源(くらしのマーケット等の
  作業依頼マッチングサイトの公開プロフィール)を追加した。実在業者の特定・連絡は
  オーナー承認が必要な範囲のため、選定方法の設計のみに留めた。
- フェーズ9(2026-08-10 00:00 UTC): interview-candidate-selection-criteria.mdの選定基準に
  沿って、WebSearchで実在の独立系・フランチャイズ加盟エアコンクリーニング業者の公開情報を
  観察し、候補ロングリスト第一弾(candidate-longlist-draft.md)を作成した。独立系2件
  (rhinohands.com運営者、hello-osouji.com運営者)・フランチャイズ加盟1件(篠崎昌則オーナー、
  おそうじ本舗)を候補として記録し、除外条件に該当する可能性が高い大手展開アカウント
  (おそうじドットコム)は候補から除外、設置作業中心で必須条件(分解洗浄)への該当が未確認の
  アカウント(エア魂女子)は保留とした。候補1・3は屋号・所在エリア・スタッフ数(必須条件)が
  未確認、複数メニュー展開のハウスクリーニング業者区分は未着手のため、次回以降の探索課題として
  残った。
- フェーズ10(2026-08-10 02:00 UTC): candidate-longlist-draft.mdの「未確認・次回への申し
  送り」に沿って、候補1・3の会社概要確認、候補2と同区分のフランチャイズ加盟オーナー追加
  探索、複数メニュー展開のハウスクリーニング業者区分の探索をWebSearchで継続した(第二弾)。
  候補1(rhinohands.com)は所在地(熊本市中央区下通)を確認できた一方、協力会社募集ページの
  存在から必須条件(スタッフ数5名以下)への該当が「要精査」と判明、候補3(hello-osouji.com)
  は屋号がAC販売・取付・不用品回収も扱う「ワンストップダイレクト」であることが判明し、
  必須条件(訪問分解洗浄が主力)への該当が「確認中」となったため、いずれも正式な候補確定を
  保留とした。フランチャイズ加盟区分では、候補2と同じ情報源(フランチャイズWEBリポート・
  osoujihonpo-fc.com)に金沢示野店・心斎橋店・宗像中央店の3名のオーナーインタビュー記事を
  新たに発見し、次回候補4〜6として正式化する材料を得た。複数メニュー展開区分は今回も
  大手企業のメニューページが中心で個人事業主の実例は未発見に終わった。
- フェーズ11(2026-08-10 04:00 UTC): candidate-longlist-draft.mdの申し送りに沿って、
  候補4〜6(金沢示野店・心斎橋店・宗像中央店の各オーナー)の記事本文確認を試みた(第三弾)。
  line-reservation-ai・course-set-pashaで既知のパターン通り、osoujihonpo-fc.com・
  osoujihonpo.com・各店舗独自ドメインはいずれもWebFetchがネットワークegressプロキシに
  よりブロックされ直接閲覧はできず、WebSearchのスニペットのみから所在エリア・開業時期・
  経歴を記録した。候補5(心斎橋店・田中オーナー)は「経験豊富なスタッフが充実」「国家資格
  保有スタッフ在籍」、候補6(宗像中央店・前山オーナー)は「従業員も雇用している」との記述が
  あり、いずれも必須条件(スタッフ数5名以下)への該当が疑わしいことが判明した。候補4
  (金沢示野店・山元オーナー)は所在エリア(石川県)のみ判明し開業時期・スタッフ数は不明の
  ままとした。フランチャイズ本部主導のオーナーストーリー記事は成功事例として比較的
  規模の大きい店舗を紹介している可能性がある、という示唆を得た。
- フェーズ12(2026-08-10 05:00 UTC): 前フェーズからの持ち越しだった候補1・3の必須条件
  該当確認をWebSearchで進めた(第四弾)。候補3(hello-osouji.com/ワンストップダイレクト)は
  「取り外しなし壁掛け分解洗浄」〜「取り外し完全分解洗浄」まで4段階の分解洗浄プランを主力
  メニューとして展開していることが確認でき、必須条件(訪問分解洗浄が主力)への該当が明確に
  なったため正式な候補に昇格した(残る不確定要素はスタッフ数のみ)。候補1(rhinohands.com)は
  会社概要ページの存在・店主名・所在地(熊本市中央区下通、既存記録と一致)を再確認できたが、
  協力会社体制の規模感(スタッフ数5名以下への該当)は今回も新情報が得られず「要精査」の
  まま持ち越しとなった。会社概要ページ本文の詳細はline-reservation-ai・course-set-pashaと
  同様にWebFetchがネットワークegressプロキシによりブロックされ直接閲覧できなかった。
- フェーズ13(2026-08-10 06:00 UTC): 候補1・3の必須条件(スタッフ数5名以下)確認を
  WebSearchでさらに進めた(candidate-longlist-draft.md第五弾)。候補1(rhinohands.com)は
  運営法人「リノビー合同会社」(熊本県登記)の存在を新たに確認できたが、店長名の表記揺れ
  (永岡裕隆/永岡浩貴)や合同会社=必ずしも複数名体制を意味しないことから、スタッフ数の
  確定には至らず「要精査」を継続した。候補3(hello-osouji.com)は運営主体が新潟県長岡市の
  「快線屋」であることが判明したが、快線屋自体の会社概要・代表者・従業員数はWebSearchでは
  特定できず、こちらも持ち越しとなった。候補1・3ともcurama.jp等の詳細ページ本文は
  WebFetchがネットワークegressプロキシによりブロックされ直接閲覧できなかった。
- フェーズ14(2026-08-10 08:00 UTC): 候補1のエキテン掲載情報・候補3の運営主体「快線屋」の
  会社概要をWebSearchで確認した(candidate-longlist-draft.md第六弾)。候補1は「女性スタッフも
  在籍」との記述から店長以外に少なくとも1名以上のスタッフがいることが裏付けられた一方、
  エキテン掲載の所在地(熊本市東区上南部)が会社概要ページの所在地(熊本市中央区下通)と
  異なる点が新たに判明し、複数拠点運営の可能性(必須条件との関係で要確認)が浮上した。
  候補3(快線屋)は長岡商工会議所の会員データベース等を確認したが該当情報は見つからず、
  3回連続で会社概要の特定に至らなかった。
- フェーズ15(2026-08-10 09:00 UTC): 候補1の所在地表記の相違(熊本市東区上南部 vs
  熊本市中央区下通)を優先確認した(candidate-longlist-draft.md第七弾)。運営元が
  rhinohands.com・rhinohands.jpの2ドメインを使い分けており、外部掲載媒体(エキテン・
  くらしのマーケット・ミツモア等)は軒並みrhinohands.jp側の住所を採用していることが
  判明。複数拠点運営というより旧住所または用途違いの可能性が高いとみられるが、必須条件
  (スタッフ数5名以下)への該当は依然「要精査」。候補3(快線屋)は3回連続で会社概要が
  特定できなかったため、申し送り通り同じ検索の繰り返しをやめ、curama.jp等の
  マッチングプラットフォーム経由の代替候補探索に切り替えたが、今回は新規候補の特定には
  至らなかった。
- フェーズ16(2026-08-10 10:00 UTC): 「次にやること」2点目だった、候補3(快線屋)の代替
  探索をcurama.jp(くらしのマーケット)のエアコンクリーニングカテゴリ掲載事業者一覧から
  WebSearchで実施した(candidate-longlist-draft.md第八弾)。「【完全自社対応】業界歴15年の
  店長が訪問いたします」を掲げるClean Labo(クリーンラボ、代表 森下将也)を候補7(暫定)、
  ペット・子供向けの安全性を個人色強く訴求する店長プロフィールの事業者を候補8(暫定)として
  発見した。候補7は同名「クリーンラボ」を名乗る事業者が福井・埼玉・石川に複数存在し掲載店の
  拠点特定が未了、候補8は屋号がスニペットにより「ハウスクリーニング幸せの種」「猫の手」と
  表記が割れており真偽確認が必要なため、いずれも正式な候補への昇格は次回以降に持ち越した。
  curama.jp掲載ページ本文はcourse-set-pasha・line-reservation-aiと同様WebFetchが
  ネットワークegressプロキシによりブロックされ直接閲覧できず、WebSearchのスニペットの
  範囲内での記録にとどまった。
- フェーズ17(2026-08-10 12:00 UTC): 「次にやること」1点目だった、候補7(Clean Labo/
  森下将也)の掲載店舗IDの特定をWebSearchで進めた(candidate-longlist-draft.md第九弾)。
  第八弾で記録した店舗ID 630456198は同名別事業者(店長 鈴木健介、屋号「一人一魂」)の
  誤記載だったと判明し、森下将也の店舗IDは544318702が正しいと訂正した。あわせて拠点が
  熊本市であることも判明し、候補1(rhinohands.com/jp)と同一エリアであることが新たに
  分かった。候補8の確認は今回は着手せず持ち越し。curama.jp掲載ページ本文はこれまで通り
  WebFetchがネットワークegressプロキシによりブロックされ直接閲覧できず、WebSearchの
  スニペット範囲内での確認にとどまる。
- フェーズ18(2026-08-10 13:00 UTC): 「次にやること」2点目だった、候補8の屋号表記揺れ
  (「ハウスクリーニング幸せの種」 vs「猫の手」)をWebSearchで確認した
  (candidate-longlist-draft.md第十弾)。curama.jp/849994132/は屋号「猫の手」(店主
  本田二三惠)のページであり、「幸せの種」は前回記録時のAI要約由来の誤情報だったと判断し
  屋号を「猫の手」で確定した。ただし「猫の手」は石垣島・鹿児島・松山/西条・沖縄・千葉等
  全国に同一ブランド名の別事業者が複数存在することが判明し、候補8がどの地域拠点かは
  今回のスニペットのみでは特定できず、スタッフ数(5名以下)への該当も未確認のまま持ち越した。
- フェーズ19(2026-08-10 15:00 UTC): 「次にやること」5点目だった、複数メニュー展開の
  ハウスクリーニング業者区分の探索をキーワードを変えてWebSearchで継続した
  (candidate-longlist-draft.md第十一弾)。開業ノウハウ解説記事・記帳代行業者のブログが
  中心で個人名・屋号が特定できる新規事業者は見つからず、第一弾以降繰り返してきたキーワード
  検索方式の限界が明確になった。次回はキーワードを変えるのではなく、候補7・8を発見した
  curama.jp事業者プロフィール単位の絞り込み方式に探索方法を切り替える申し送りとした。
- フェーズ20(2026-08-10 16:00 UTC): 「次にやること」2点目だった、候補8(猫の手/
  本田二三惠、curama.jp/849994132/)の所在地域特定をWebSearchで継続した
  (candidate-longlist-draft.md第十二弾)。地域を特定できる情報は今回も得られなかった一方、
  以前候補8の掲載サービスと推定していたSER562451587(保護猫3匹の癒し系店長)が、検索結果上
  では屋号「ハウスクリーニング幸せの種」のサービスとして扱われていることが判明し、両者が
  同一事業者か別事業者かという新たな確認事項が生じた。全国の同一/類似ブランド名事業者も
  神戸市西区・愛知県一宮市・千葉市若葉区・相模原市中央区の事例が新たに見つかり、ブランド名
  乱立の広範さが改めて裏付けられた。WebSearchのスニペットのみでの特定は限界に達しつつあり、
  次回はブログ投稿経由の探索か、候補8を保留・除外に回す判断のいずれかに切り替える。
- フェーズ21(2026-08-13 17:00 UTC): 候補ロングリスト探索(WebSearch)がここ数フェーズ
  横ばい・空振りが続いていたため、今回は候補探索を一旦離れ、course-set-pasha/prototype/
  post_generation_checks.pyに相当する後処理チェックスクリプト(prototype/
  post_generation_checks.py)を新規作成した。schema/output.schema.json・
  llm-system-prompt-draft.mdで方針のみ記述していた厳守事項1(冷媒・電気系統への専門的
  助言回避)・厳守事項4(次回推奨時期が一般的目安か入力メモ由来かの区別)・厳守事項6
  (会員管理・予約受付・決済への不応答)・厳守事項3(機種系統・号数/追加施工の本文への
  明示)について、本文とcompletion_report/care_guide/history_rowの構造化フィールドとの
  突き合わせをヒューリスティックに検証する5つのチェック関数を実装した。
  prototype/test_post_generation_checks.pyで15件のユニットテストを作成し全件パス。
  テスト作成の過程でschema/validate_test_cases.mdのG2フィクスチャ
  (history_row.model_type_and_capacity="壁掛け型(お掃除機能付き)"がcompletion_report.body
  の実際の文言「壁掛け型のお掃除機能付き」と表記が一致していない不整合)を発見し、
  schema/validate_test_cases.pyのG2本文を修正した(机上バリデータ実行は5件中5件パス
  を再確認)。
- フェーズ22(2026-08-13 19:59 UTC): 「次にやること」3点目(複数メニュー展開のハウス
  クリーニング業者区分をcurama.jp事業者プロフィール単位の絞り込みに切り替える)をWebSearchで
  試みたが、curama.jpのカテゴリ一覧・大学記事(univ.curama.jp)のみが返り個人名・屋号が
  特定できる新規事業者は今回も得られず、フェーズ19以降指摘してきたWebSearchスニペット方式の
  頭打ちが再確認された。候補探索を追加で繰り返すより他venture(line-reservation-ai・
  course-set-pasha)との整備状況の差分を埋める方が生産的と判断し、本ventureにまだ無かった
  特定商取引法に基づく表記・プライバシーポリシー文面草案(legal-notices-draft.md)を新規
  作成した。course-set-pasha/legal-notices-draft.mdの構成(特商法表記の項目表→プライバシー
  ポリシー2.1〜2.5→次のステップ候補)を踏襲しつつ、本venture固有の論点として、依頼者
  (エンドユーザー)個人情報が業者のメモに誤って混入するケースへの対応方針を新規の未検証事項
  として追加し、course-set-pashaで独自論点だったステルスマーケティング規制は本ventureが
  SNS投稿文でなく一対一の完了報告文を扱うため該当性が薄いと整理した。
- フェーズ23(2026-08-13 20:59 UTC): 「次にやること」1点目だった、他venture同様の
  landing-page-copy-draft.md相当のLP文面草案作成に着手した(landing-page-copy-draft.md
  新規作成)。course-set-pasha/landing-page-copy-draft.mdの構成(ヒーロー→課題提起→
  機能紹介→差別化→料金→FAQ)を踏襲しつつ、本venture固有の差異(出力の宛先が依頼者本人
  1名であること、冷媒・電気系統には踏み込まない旨を安心材料として訴求すること)を反映した。
  market-research.md・pricing-plan.md・sns-blog-example-observation.md・
  legal-notices-draft.mdの既存内容をそのまま反映し、新規の調査・設計判断は発生していない。
  LPワイヤーフレームの作成は本venture未着手のまま次の課題として残した。
- フェーズ24(2026-08-13 21:59 UTC): フェーズ23の残課題だった、landing-page-copy-draft.md
  に対応するLPワイヤーフレーム(セクション配置・画像イメージ)を新規作成した
  (landing-page-wireframe.md)。line-reservation-ai/landing-page-wireframe.mdの構成
  (設計方針→画面構成→画像方針まとめ表→未確定事項)を踏襲しつつ、本venture固有の差異として、
  他ventureのLINEトーク画面・SNS投稿プレビューのモックアップに代えて「入力メモ→完了報告文」の
  ビフォーアフター画像を軸に据えた(1対1の完了報告文書という成果物の性質に合わせた変更)。
  実際の画像制作・HTML/CSS実装・公開はスコープ外のまま次の課題として残した。
- フェーズ25(2026-08-13 22:59 UTC): course-set-pasha・line-reservation-aiには存在するが
  本ventureにまだ無かった、Webhook受信〜LLM呼び出し〜返信のバックエンド処理フローの
  プロトタイプ(prototype/cloud_function_webhook.py)を新規作成した。course-set-pashaの
  同名モジュールの構成(LLM呼び出し・返信送信をProtocolで抽象化、検証失敗時は同一入力で
  1回だけ再生成、それでも失敗すれば定型フォールバック文言)を踏襲しつつ、本venture固有の
  差異として、history_rowが単一オブジェクト(1メモ=1件の訪問施工)であるためCSV変換
  (history_export.py相当)は不要とし表形式の項目名付きテキストへの整形関数
  (format_history_row_text)に単純化した。mvp-flow-draft.mdの出力スキーマに写真添付
  (hasPhoto)相当のフィールドが無いため、course-set-pashaのテキスト・画像束ねロジック
  (merge_text_and_photo_events)・LINE署名検証は移植を見送った。
  prototype/test_cloud_function_webhook.py(13件のユニットテスト、schema/
  validate_test_cases.pyの全フィクスチャ含む)を新規作成し全件パスを確認、
  python3 cloud_function_webhook.pyのデモ実行でも期待通りの返信文が組み立てられることを
  確認した(実LLM・実クラウド接続は未実施、オーナー承認待ち)。
- フェーズ26(2026-08-14 00:59 UTC): course-set-pasha・line-reservation-aiには存在するが
  本ventureにまだ無かった、GitHub Actionsによるテスト自動実行(ci-setup.md)を導入した。
  `.github/workflows/aircon-pasha-tests.yml`を新規作成し、prototype/のunittestスイート
  (test_cloud_function_webhook.py・test_post_generation_checks.py、計28件)と
  schema/validate_test_cases.py(5件)を`ventures/aircon-pasha/`配下への変更時に自動実行する
  構成とした。course-set-pasha/ci-setup.mdの構成(背景→実施内容→確認事項→今後の課題)を
  踏襲した。ローカルでの事前確認は28件・5件とも全件パス済み。実際のコミット後のCI実行結果
  確認(actions_list)は次回以降の課題として残した。
- フェーズ27(2026-08-14 03:00 UTC): フェーズ26の残課題だった、aircon-pasha-tests.ymlの
  初回CI実行結果をmcp__github__actions_list(list_workflow_runs)で確認した。
  フェーズ26のコミット(7940fc4、01:02 UTC)をトリガーに実行されたrun
  (id: 31759422249)はstatus: completed / conclusion: successで、ローカル確認結果
  (unittest計28件・schema検証5件、全件パス)と一致した。course-set-pasha・
  line-reservation-aiと同じ運用がaircon-pashaでも機能していることを確認できた。
  ワークフローはventures/aircon-pasha/配下への変更時のみ起動する構成のため、これ以降の
  02:00 UTC・03:00 UTCコミット(いずれもaircon-pasha配下を変更していない)では新規run
  は発生していない(total_count: 1)。次にaircon-pasha配下を変更するコミットで改めて
  run結果を確認する。
- フェーズ28(2026-08-14 05:00 UTC): 「次にやること」1点目だった、候補8(猫の手/本田二三惠、
  curama.jp/849994132/)の地域特定をブログ投稿・口コミページ経由でWebSearchしたが、いずれも
  所在エリアを示す情報は得られなかった。第十弾・第十二弾と合わせて4回目の試行となり、
  フェーズ20時点の申し送り基準(3回連続未特定なら保留・除外)に達したと判断し、候補8は
  正式に保留・除外とした。空いた独立系候補枠の代替探索も試みたが、個人事業主の経費処理を
  解説する一般記事が中心にヒットし新規候補は見つからなかった(candidate-longlist-draft.md
  第十三弾)。「curama.jp事業者プロフィール単位の絞り込み」への切り替えは複数フェーズにわたり
  申し送りが続いており、次回はキーワード検索ではなくこの方式を優先的に試す。
- フェーズ29(2026-08-14 08:00 UTC): 「次にやること」の候補7(Clean Labo/森下将也)の
  熊本市内詳細所在地確認をWebSearchで進めた(candidate-longlist-draft.md第十四弾)。
  事業者ページの記載から「熊本県熊本市南区大迫4-3-57」まで丁目レベルで特定でき、候補1
  (熊本市中央区下通)とは異なる区であることも判明した。スタッフ数(必須条件5名以下)は
  「完全自社対応」「店長本人が訪問」という間接的な記述に留まり、一次情報での直接確認には
  至らなかった(curama.jpの事業者プロフィール本文はWebFetchがネットワークegressプロキシに
  よりブロックされ引き続き直接閲覧不可のため)。候補7は所在地確認済み・スタッフ数は間接
  推定の状態のまま候補として維持することとした。
- フェーズ30(2026-08-14 12:00 UTC): 「次にやること」だった、候補1の関連法人名
  (「ニシムラ・プロバイズ株式会社」)の裏付け確認をWebSearchで進めた
  (candidate-longlist-draft.md第十五弾)。「ニシムラ・プロバイズ株式会社」自体は今回も
  裏付けが得られず過去のWebSearch要約由来の誤情報と判断し追跡を打ち切った一方、複数の
  法人データベース(企業INDEXナビ・SalesNow DB・全国法人リスト・IRBANK)で運営法人が
  「リノビー合同会社」(法人番号9330003009063、2021年設立)であることを確度高く確認できた。
  あわせて2024年11月20日に本店所在地を熊本市中央区下通から熊本市南区護藤町へ移転した
  記録も見つかり、候補1で懸案だった複数住所表記の一部(中央区下通が移転前の旧本店所在地)を
  整理できた。スタッフ数(必須条件5名以下)の直接的な一次情報での裏付けは今回も得られず、
  合同会社という小規模向けの法人格・設立年の若さを間接的な傍証として記録するに留めた。
- フェーズ31(2026-08-14 16:00 UTC): 「次にやること」だった、候補4(山元オーナー)の
  開業時期・スタッフ数確認を、店舗独自ドメイン・SNS等の追加情報源も含めてWebSearchで
  再試行した(candidate-longlist-draft.md第十六弾)。開業時期は今回も特定できなかったが、
  「全スタッフに心を込めて丁寧に作業を進めるよう徹底させています」という記述が見つかり、
  候補5・6と同様に複数名スタッフ在籍を示唆する結果となった。候補4は第三弾から5回目の
  確認試行で新情報がほぼ増えていないと判断し、候補4〜6(フランチャイズ本部公式の
  オーナーストーリー経由で発見した候補)の個別深掘りをここで打ち切る方針転換を行った。
  今後フランチャイズ加盟区分の代替候補探索は、本部公式ストーリー経由ではなく候補2
  (篠崎オーナー)のような個人のSNS発信・ブログ経由の探索に切り替える。
- フェーズ32(2026-08-14 18:00 UTC): 「次にやること」だった、フランチャイズ加盟区分の
  代替候補探索を新方針(個人のオーナー体験談・レポート経由)でWebSearchした
  (candidate-longlist-draft.md第十七弾)。独立開業情報サイト「アントレ」が
  「おそうじ革命」加盟オーナーの個別レポート(横田有輝さん・柳川敬士さん・細川宗晧さん・
  小浦さゆりさん・高野恭平さん)を氏名付きで公開していることを発見し、新しい探索経路と
  して有望と判断。加盟店実績データからは神奈川県・2019年7月開業・ワンオペ体制・
  年間所得1,300万円という、必須条件(スタッフ5名以下)に明確に合致する実績を発見した
  (候補9・仮)が、氏名までは特定できなかった。横田有輝さんの個別レポートは確認できた
  ものの「東京・2023年3月開業・年商2,900万円」とプロフィールが一致せず除外。氏名の
  特定は次回の課題として持ち越し。
- フェーズ33(2026-08-14 20:00 UTC): フェーズ32で「候補9・仮」(神奈川県・2019年7月開業・
  ワンオペ・年商1,300万円)の氏名特定候補として残った柳川敬士さん・細川宗晧さん・
  小浦さゆりさん・高野恭平さんの各オーナーレポートをWebSearchで個別に確認した
  (candidate-longlist-draft.md第十八弾)。細川さん(2024年8月開業)・高野さん(2024年12月
  開業・夫婦運営)・小浦さん(2023年5月開業・愛知県豊川市)の3名は開業時期または地域・
  体制のいずれかで候補9の実績と矛盾することを確認し除外。消去法で柳川敬士さんが最有力
  候補となったが、本人プロフィールでの開業時期・地域・体制人数の直接確認はWebFetchの
  egress制約(entrenet.jp個別レポートページ本文にアクセス不可)により取れず、氏名確定には
  至らなかった。これ以上スニペット経由の絞り込みを繰り返しても新情報の増分が乏しいと
  判断し、候補9の氏名特定はここで一旦保留、他の未着手課題(候補7のスタッフ数裏付け、
  複数メニュー展開区分の探索)を先行させる方針に転換した。
- フェーズ34(2026-08-14 21:00 UTC): line-reservation-ai・course-set-pashaには存在するが
  本ventureにまだ無かった、月額サブスク決済手数料試算(subscription-billing-cost-estimate.md)を
  新規作成した。course-set-pasha/subscription-billing-cost-estimate.mdの構成・観点を踏襲し、
  本venture固有の料金水準(2,980円/5,980円/8,980円の3プラン)でクレジットカード継続課金
  (3.6%と仮定)の手数料を試算(固定分107〜323円/月、超過分1回あたり1.4〜2.2円)。あわせて、
  market-research.mdの季節性(繁忙期は施工件数が閑散期の2〜3倍)を踏まえると本venture固有の
  課題として、月間生成回数を積算する軽量データストア(Firestore等)の導入方針が
  course-set-pashaと異なりまだ未着手(対応するtech-stack.md自体が未作成)であることを新たに
  整理し、優先度の高い次の課題として記録した。
- フェーズ35(2026-08-14 22:00 UTC): フェーズ34で判明した設計ギャップ(月間生成回数を
  積算する軽量データストアの導入方針が未着手)に対応し、tech-stack.mdを新規作成した。
  course-set-pasha/tech-stack.mdの構成(全体構成イメージ・想定コンポーネント5点・MVP
  スコープ・初期投資/ランニングコスト目安)を踏襲しつつ、本venture固有の季節性(繁忙期は
  施工件数が閑散期の2〜3倍)を踏まえ、上限接近時の事前通知の閾値・タイミング設計は
  course-set-pashaの設計をそのまま流用せず再検討が必要な次の課題として明記した。あわせて、
  月間カウント用データストアの読み書き課金がsubscription-billing-cost-estimate.mdの試算に
  含まれていない点も次の課題として記録した。
- フェーズ36(2026-08-14 23:00 UTC): 「次にやること」1点目だった、本venture固有の季節性
  (繁忙期は施工件数が閑散期の2〜3倍)を踏まえた上限接近時の事前通知設計
  (limit-approaching-notification-design.md)を新規作成した。course-set-pashaの「残り2回」
  閾値は、本ventureの利用ペース(1日3〜5件、course-set-pasha比で一桁多い)ではそのまま
  流用すると通知の実効猶予が不足すると判断し、3プラン共通で「残り5回」(35回目/85回目/
  145回目の生成完了時)に変更した。繁忙期のみ閾値を分ける案は実データが無く妥当性検証
  できないため見送り、実運用データが得られた段階での見直しを次の課題として残した。
- フェーズ37(2026-08-15 01:00 UTC): 「次にやること」だった、月間生成回数カウント用
  データストア(Firestore等)の読み書き課金の原価試算を、subscription-billing-cost-estimate.md
  に追記した。course-set-pasha/subscription-billing-cost-estimate.mdの試算方法(1回の生成
  あたり読み取り1回・書き込み1回の計2回)を踏襲しつつ、本venture固有の季節性(繁忙期は
  施工件数が閑散期の2〜3倍)を踏まえ、最繁忙日の1業者あたり操作数を仮に20回/日と置いて
  試算した結果、書き込み無料枠(20,000回/日)内で約1,000業者分まで収まる計算となった
  (course-set-pashaと同水準)。ただしこの日次操作数の仮定自体が、フェーズ36で「残り5回」
  閾値に変更した根拠(本venture利用ペースがcourse-set-pasha比で一桁多い)からみてやや
  保守的すぎる可能性があり、実運用データでの日次ピーク再検証を新たな未検証事項として残した。
- フェーズ38(2026-08-15 06:00 UTC): candidate-longlist-draft.mdの申し送り(第十八弾)を
  受け、(1)複数メニュー展開のハウスクリーニング業者区分の代替候補探索(個人事業主に
  絞ったキーワード)、(2)候補7(Clean Labo/森下将也)のスタッフ数一次情報での裏付け、の
  2点をWebSearchで試みた(第十九弾)。(1)は3パターンのキーワードを試したがいずれも
  開業ガイド記事止まりで新規候補には到達できず、頭打ちと判断し次回は既発見の独立系候補
  (候補1・3・7)のメニュー内容を個別確認する方針転換を検討することにした。(2)は
  くらしのマーケットの候補7個別ページのスニペットに「【完全自社対応】業界歴15年の
  店長が訪問いたします」という記述を確認し、必須条件(スタッフ5名以下)への間接的な
  裏付けがやや強まったが確定には至らない。あわせて候補7とは別の店舗ID(054122114)が
  くらしのマーケットに存在することを新たに確認し、同一事業者か別事業者かの確認が
  新課題として加わった。詳細はcandidate-longlist-draft.md「第十九弾」参照。
- フェーズ39(2026-08-15 07:00 UTC): フェーズ38・第十九弾の申し送りに沿って、候補1・3・7の
  サービスメニュー内容(訪問分解洗浄が主力メニューの一つに該当するか)をWebSearchで個別
  確認した(candidate-longlist-draft.md「第二十弾」)。候補1(リノハンズ)は「熊本で唯一の
  エアコン完全分解クリーニング」を看板メニューとする自社ページを確認し必須条件への該当を
  明確化。候補7(Clean Labo)も機種別の分解洗浄所要時間・追加料金の詳細な体系を確認し
  同様に該当を明確化。候補3(hello-osouji.com)はクリーニング専門サイトと取付・販売主体の
  姉妹サイト(onestop-direct.com)を分けて運営していることが判明したが、事業全体に占める
  クリーニングの比重は依然不明瞭のため「必須条件の該当確認中」の位置づけを維持した。
  なお候補ドメインへのWebFetchは今回もegress制約でブロックされ、WebSearchのスニペットの
  みでの確認となった。
- フェーズ40(2026-08-15 07:58 UTC): 「次にやること」だった、店舗ID(054122114、屋号
  「クリーンラボ-clean labo-」)が候補7(店舗ID 544318702、森下将也、熊本市拠点)と同一
  事業者か別事業者かをWebSearchで確認した(candidate-longlist-draft.md「第二十一弾」)。
  054122114の所在地が「埼玉県さいたま市緑区」であることが判明し、熊本市拠点の候補7とは
  明確に異なる無関係の別事業者と結論づけて店舗ID重複疑惑を解消した。あわせて「クリーンラボ」
  を屋号・社名に含む事業者(春日部市の株式会社クリーンラボFD、cleanlabo.co.jp、
  株式会社CLEAN Lab JAPAN、株式会社MR.クリーンラボ等)が全国に多数存在することも確認でき、
  候補8(猫の手)で判明したブランド名乱立と同様の教訓(屋号一致だけで同一事業者と即断せず
  所在地・代表者名での個別照合が必須)として記録した。
- フェーズ41(2026-08-15 10:00 UTC): 「次にやること」だった、候補3(hello-osouji.com/
  ワンストップダイレクト)の事業全体における取付・販売とクリーニングの比重確認をWebSearchで
  行った(candidate-longlist-draft.md「第二十二弾」)。hello-osouji.com(クリーニング専用
  サイト)とonestop-direct.com(取付・販売専用サイト)を意図的に別ドメインで運用し、
  それぞれ独立した専門店として打ち出している実態が判明し、クリーニングが取付・販売の
  ついでではなく独立した主力メニューであると判断できたため、必須条件(訪問分解洗浄が主力)
  への該当を確認し候補3を正式候補に昇格させた。これにより独立系候補が候補1・3・7の3件
  そろい、目標件数(6〜7件)の半数に達した。
- フェーズ42(2026-08-15 14:00 UTC): 「次にやること」だった、独立系候補(候補1・3・7)への
  初回コンタクト文面の草案作成に着手した(initial-contact-message-draft.md新規作成)。
  course-set-pashaのinitial-contact-message-draft.mdの構成(想定チャネル→文面草案A・B→
  候補ごとの留意点→未確定事項)を踏襲しつつ、選定基準(interview-candidate-selection-
  criteria.md)の「マッチングサイト経由の直接勧誘は行わない」方針に沿い、curama.jpの
  メッセージ機能を連絡チャネルから除外し公式サイト問い合わせフォーム・電話のみとした。
  候補3は姉妹サイト(onestop-direct.com、取付・販売主体)への誤送信を避ける注意点として
  明記、候補1・7は同一エリア(熊本市)のため連絡時期をずらす等の配慮を検討事項とした。
  実際の送信は行っていない(オーナー承認待ち)。
- フェーズ43(2026-08-15 15:00 UTC): 「次にやること」だった、customer-interview-design.mdの
  未検証仮説(質問13問が10〜15分に収まるか)を検証するリハーサル台本
  (interview-rehearsal-script.md)を新規作成した。course-set-pasha/interview-rehearsal-
  script.mdの構成(想定タイムテーブル→オープニング台本→質問ごとの補足ト書き→クロージング
  台本→確認ポイント)を踏襲し、独立系正式候補である候補1(リノハンズ)を想定回答者とした。
  全13問・目標12.5分で想定時間内に収まる見込みとし、候補1が独立系のためフランチャイズ向け
  Q11は代替質問に置き換える設計とした。実際のリハーサル実施・候補への連絡は行っていない。
- フェーズ44(2026-08-15 16:00 UTC): 「次にやること」だった、リハーサル台本
  (interview-rehearsal-script.md)の候補3(hello-osouji.com)・候補7(Clean Labo)向け展開に
  着手した。候補ごとに台本を作り直すのではなく、候補1版を土台に差分のみを申し送る方式を
  採用(候補7: 個人〈店長本人〉対応前提の一言追加+他候補〈候補1〉への非言及の注意書き、
  候補3: オープニングでのサイト名〈hello-osouji.com〉明示+姉妹サイト〈onestop-direct.com、
  取付・販売主体〉との切り分けの一言追加)。両候補ともQ11(独立系のため代替質問への
  置き換え)・想定時間12.5分は候補1と同じで、候補3のみQ8(冷媒ガス等除外)のト書きに
  取付工事への脱線防止の注意を追加した。
- フェーズ45(2026-08-15 17:00 UTC): 「次にやること」の優先度検討に沿い、独立系候補の
  追加確保(現状3件/目標6〜7件)を先行する方針でWebSearchによる新規候補探索に着手した
  (candidate-longlist-draft.md 第二十三弾)。新規候補として候補10(暫定)「キキのおそうじ屋」
  (クローバーズシステム合同会社、名古屋市中川区)を発見し要精査で追加した。あわせて
  ヒットした「ありがとうエアコンお掃除専門店」は多府県展開・登録スタッフ多数のネットワーク
  型運営と判明し、除外条件(スタッフ数5名以下の想定から外れる)に該当するためロングリスト
  への追加を見送った。
- フェーズ46(2026-08-15 18:00 UTC): 「次にやること」だった、候補10(キキのおそうじ屋)の
  スタッフ数(5名以下)該当・訪問分解洗浄が主力メニューかをWebSearchで確認した
  (candidate-longlist-draft.md「第二十四弾」)。運営法人クローバーズシステム合同会社の
  再確認、電話受付窓口に2名の氏名(小清水・服部)が明記されている点を新たに確認したが、
  サービスメニューがエアコンクリーニングに加え浴室・トイレ・キッチン等幅広いハウス
  クリーニングを展開していることが判明し、候補1・3・7(エアコン分解洗浄を看板メニューと
  する専門店)とは性格が異なる可能性が浮上した。候補3で用いた「専用サイト・専用訴求の
  有無」による判定基準を候補10にも適用する必要があると判断し、正式候補への昇格は見送り
  「必須条件の該当確認中」のまま次回に持ち越した。
- フェーズ47(2026-08-15 19:00 UTC): 「次にやること」だった、候補10(キキのおそうじ屋)の
  専用サイト・専用訴求の有無をWebSearchで確認した(candidate-longlist-draft.md
  「第二十五弾」)。メインドメイン(kikinoosoujiya.com)のトップページ自体が「名古屋の
  低価格エアコンクリーニング業者」を掲げ、業務用エアコンクリーニング専用ページも別途
  用意されている一方、一般的なハウスクリーニングメニューは下層ページ(/house)にまとめ
  られていることを確認した。候補3のような別ドメイン分離ではなく同一ドメイン内のページ
  階層による分離だが、「事業の顔(トップページ)としての訴求対象がエアコンクリーニング」
  という点で必須条件への該当を確認できたと判断し、候補10を正式な候補に昇格させた
  (スタッフ数5名以下は候補1・3・7と同様、間接傍証止まりで未確定)。独立系候補は
  候補1・3・7・10の4件となり、目標(6〜7件)まで残り2〜3件。
- フェーズ48(2026-08-15 21:00 UTC): 「次にやること」だった、独立系候補の追加確保
  (現状4件/目標6〜7件)をキーワードを変えてWebSearchで継続した(candidate-longlist-draft.md
  「第二十六弾」)。新規候補として候補11(暫定)「エアクリ」(aircle.wwww.jp)を発見した。
  分解洗浄・脱着を専門店として前面に掲げ、口コミに「一人での作業」との言及があり個人事業主
  が有力だが、同サイトが「完全分解クリーニング技術セミナー」を実施しており他者への技術
  指導・展開を行っている可能性がある点、所在エリアが未確定な点、類似ドメイン(aircle.net、
  大分県中津市・福岡県豊前市)との異同確認が必要な点を次回への申し送りとした。
- フェーズ49(2026-08-16 00:00 UTC): フェーズ48の申し送りだった候補11(エアクリ)の
  類似ドメイン異同確認をWebSearchで実施した(candidate-longlist-draft.md「第二十七弾」)。
  aircle.net(大分県中津市・福岡県豊前市)、エアクリ株式会社(air-cle.com、埼玉県)、
  エアクリ株式会社(airkuri.com、建築設備管理業)、AIRCLE/エアクル(シェアリング
  エコノミー協会掲載、運転代行配車)の4件はいずれも候補11とは無関係の別事業者と確認でき、
  屋号の混同は解消した。一方で候補11自身の所在エリア・代表者名・スタッフ数は
  aircle.wwww.jp本体へのWebFetchがegress制約でブロックされ続けているため未特定のまま
  残った。新たな論点として、候補11が展開する「完全分解クリーニング技術セミナー」
  (他業者向けの現場同行研修)が本サービスの前提(個人が自分で報告文を作成)とどこまで
  整合するかを次回検討課題とした。
- フェーズ50(2026-08-16 01:00 UTC): 「次にやること」の2点をWebSearch・WebFetchで進めた
  (candidate-longlist-draft.md「第二十八弾」)。(1)候補11(エアクリ)の所在エリア・
  代表者名・スタッフ数は、予約サイト(reserva.be/aircle)の存在を新たに確認したものの
  WebFetchがegress制約で本文に到達できず、WebSearchのスニペットからも特定できなかった。
  類似屋号(aircle.net)の住所が検索結果に混入する誤結合リスクも再確認し、採用は見送った。
  第二十六弾以降3回連続で新情報がほぼ増えていないため、候補11は保留とし独立系の新規候補
  探索(残り2〜3件)を優先する方針に転換した。(2)「技術指導・研修事業を兼業する候補」の
  扱いをinterview-candidate-selection-criteria.mdに新規節として追記し、除外条件には
  追加せず「望ましい条件」の判定材料として扱う方針(スタッフ数確認は研修運営人員も含め
  他候補より一段階厳しく確認、ヒアリング時は候補者自身の施工報告実務に質問を絞る)を整理した。
- フェーズ51(2026-08-16 02:00 UTC): 「次にやること」の方針に沿って、候補11を保留に回し
  独立系の新規候補探索をキーワードを変えてWebSearchで継続した(candidate-longlist-draft.md
  「第二十九弾」)。新たに候補12(暫定、東京住まいる/株式会社アクシル、東京都千代田区、
  代表・永澤史博氏、2015年3月設立)を発見し、会社概要ページから代表者名・所在地・設立年・
  資本金まで一次情報で確認できた。併せて発見した「エアタクミ」(株式会社ウガホームサービス)は
  7都府県展開・研修センター常設・加盟店募集中のフランチャイズ本部と判明したため、除外条件
  (全国チェーン・大手フランチャイズの直営店)に該当すると判断し候補には加えなかった。
  これにより独立系候補は5件(候補1・3・7・10・12暫定)となり目標(6〜7件)まで残り1〜2件。
- フェーズ52(2026-08-16 03:00 UTC): 「次にやること」だった、候補12(東京住まいる)の
  スタッフ数・「住宅メンテナンス事業」表記の事業比重をWebSearchで確認した
  (candidate-longlist-draft.md「第三十弾」)。トップページのタイトルタグが「エアコン
  完全分解クリーニング」であることから候補10と同じ「事業の顔としての訴求対象」基準で
  必須条件(訪問分解洗浄が主力)への該当を支持する材料を得た一方、「電気工事業の登録を
  受けた電気登録事業者」との記述も見つかり、候補3のような明確なドメイン分離のない同一
  サイト内での設置・電気工事関連の言及があることが判明した。スタッフ数は「経験豊富な
  専門スタッフが」という複数名を示唆する表現以外、具体的人数の一次情報は得られず間接
  傍証止まりのまま。tokyo-smile.jp本体へのWebFetchは他候補と同様egress制約でブロック
  され、正式候補への昇格判断は次回に持ち越した。
- フェーズ53(2026-08-16 06:00 UTC): 候補探索が直近複数フェーズで新情報の増分が乏しく
  優先度を下げていたため、別軸の未着手課題に着手した。course-set-pashaには存在するが
  本ventureには無かった「解約・プラン変更時の案内文言・処理フロー設計」
  (subscription-cancellation-flow-design.md)を新規作成した。course-set-pashaの同名
  ファイルの構成(解約フロー→案内文言→ダウングレード時の当月生成回数上限の適用方法)を
  踏襲しつつ、本venture固有の季節性(繁忙期対応プランへの需要が梅雨〜夏に偏る)を反映し、
  「季節に応じたダウングレードの偏り」を本venture固有の論点として追加した。当月上限の
  適用方式(`usage_counter`のcountは維持し上限値のみ差し替え)は決済方式(Stripe Billing)が
  course-set-pashaと共通であることを根拠に流用したが、本venture独自の一次情報確認は
  行っておらず、実際のStripe接続後の検証が残課題として残る。
- フェーズ54(2026-08-16 07:00 UTC): フェーズ53の残課題だった「解約」インテントの誤検知
  境界設計に着手した。llm-system-prompt-draft.mdの厳守事項6に、course-set-pashaの
  厳守事項7a(解約意図検知の境界、フェーズ53・2026-08-15 13:00 UTC)を参考に厳守事項6aを
  新設し、(i)解約意思が明確/(ii)プラン変更(ダウングレード等)の意思表示/(iii)雑談・愚痴の
  域を出ない表現/(iv)判断がつかない場合、の4分岐で判定する境界を整理した。本venture固有の
  留意点として、繁忙期(梅雨〜夏)の施工件数の多さを愚痴る発言をダウングレード意思表示
  ((ii))と混同しないことを明記した。構造化出力の方針(`status`拡張案)・次の課題も
  course-set-pashaのschema/output.schema.json改訂(フェーズ54)を参考に更新したが、
  実際のJSON Schemaファイルへの反映・post_generation_checks.py相当の機械チェック実装は
  次回以降の課題として残す。
- フェーズ55(2026-08-16 09:00 UTC): 第三十弾の申し送りだった候補12(東京住まいる)の
  「クリーニングと設置工事の事業比重」をWebSearchで追加確認した(候補longlist第三十一弾)。
  価格訴求面ではエアコンクリーニングの工賃のみで構成された料金体系が確認でき、電気工事側の
  独立した価格メニューは見当たらなかったため、クリーニング一本化を支持する傍証が上積み
  された。スタッフ数は依然未確定で、次回はスタッフ数確認を優先する。詳細は
  candidate-longlist-draft.md「第三十一弾」参照。
- フェーズ56(2026-08-16 12:00 UTC): 候補12(東京住まいる)のスタッフ数確認をWebSearchで
  再試行したが、第三十弾・第三十一弾に続き3回目も新情報は得られなかった。候補1・7・3の
  スタッフ数確認が「間接傍証止まりで未解決のまま残る」扱いで正式候補入りした前例に照らし、
  候補12(暫定)を正式候補に昇格させた。これにより独立系候補は6件(候補1・3・7・10・12)と
  なり、目標件数(6〜7件)の下限に到達した。詳細はcandidate-longlist-draft.md
  「第三十二弾」参照。
- フェーズ57(2026-08-16 15:00 UTC): 独立系の新規探索が頭打ちになっていたため、候補選定の
  軸足をフランチャイズ加盟系に転換した。web-repo.jp「フランチャイズWEBリポート」で新規
  インタビュー記事(専門学校職員から独立した女性オーナーの4年間の歩み)を発見し、候補13
  〈仮、氏名未確認〉としてロングリストに仮登録した。詳細はcandidate-longlist-draft.md
  「第三十三弾」参照。
- フェーズ58(2026-08-16 17:00 UTC): 候補13〈仮〉の氏名・所在エリアをWebSearchで確認した。
  「金井美樹オーナー(おそうじ本舗 杉並高井戸店、東京都杉並区)」と判明し、正式候補に
  昇格させた。スタッフ数は開業当初(2020年時点)の推測にとどまり、2026年時点の現体制・
  店舗の稼働継続は次回の確認課題として残る。詳細はcandidate-longlist-draft.md
  「第三十四弾」参照。
- フェーズ59(2026-08-16 18:00 UTC): 「次にやること」だった、候補13(金井美樹オーナー、
  おそうじ本舗 杉並高井戸店)が2026年時点でも稼働中かの確認をWebSearchで行った。おそうじ本舗
  公式サイトの現行店舗一覧への掲載、自社サイト・LINE公式・Facebook・エキテンの現存を確認し、
  廃業・屋号変更の兆候は見当たらなかったため稼働継続と判断した。ただしWebFetchはegress制約で
  osoujihonpo.com・osoujihonpo-fc.comに接続できず、店舗詳細ページ本文での一次情報直接確認は
  持ち越しとなった。詳細はcandidate-longlist-draft.md「第三十五弾」参照。
- フェーズ60(2026-08-16 19:00 UTC): 「次にやること」だった、フランチャイズ加盟系候補4〜6
  (「要精査・除外候補寄り」のまま)について、精査継続か除外確定かの判断を行った。3件とも
  「複数名スタッフ在籍」を示唆する記述が一次情報に近い形で確認されており、これ以上の追加調査で
  結論が覆る見込みが薄いため、候補4〜6を正式に除外確定とした。これによりフランチャイズ加盟系の
  正式候補は候補2・13の2件のみとなり、目標件数(3〜4件)の下限を割り込んだため、次回は
  第十六弾で方針転換した「個人のSNS発信・ブログ経由」の探索を再開し新規候補を探す。詳細は
  candidate-longlist-draft.md「第三十六弾」参照。
- フェーズ61(2026-08-16 23:01 UTC): 「次にやること」だった、「個人のSNS発信・ブログ経由」の
  探索方針を再開し、フランチャイズ加盟系の新規候補をWebSearch3クエリで探索した。ameblo.jpの
  記事は複数ヒットしたが加盟店オーナー本人ではなく利用者(顧客)側の体験ブログにとどまり、
  「プロコート株式会社」(大阪府堺市)の1人年商1,000万円という実績も発見したが加盟店オーナーの
  体験談ではなく開業支援事業者自身の創業ストーリーであり候補として不採用と判断した。3クエリとも
  新規候補の発見には至らず、フランチャイズ加盟系の正式候補は候補2・13の2件のまま。次回は
  Instagram・X等のハッシュタグ検索や、ミツモア・くらしのマーケット等の個人事業主向けポータルの
  事業者プロフィール個別ページ経由での探索に切り替える。詳細は上記candidate-longlist-draft.md
  「第三十七弾」参照。
- フェーズ62(2026-08-17 00:59 UTC): 「次にやること」だった、おそうじ本舗以外のブランドからの
  探索をWebSearchで行った。「おそうじ革命」加盟店の店舗公式ブログに、オーナー本人が独立開業の
  経緯を語る記事(世田谷桜新町店「脱サラして独立開業するならおそうじ革命をご検討しませんか?」等)
  を発見し、店舗責任者「濱暁洋オーナー」を氏名確認した。これを候補14(仮)としてロングリストに
  仮登録し、フランチャイズ加盟系の正式候補は候補2・13・14(仮)の3件となり、目標件数(3〜4件)の
  下限に到達した。スタッフ数(5名以下該当)の一次情報確認は次回以降の課題として残る。詳細は
  上記candidate-longlist-draft.md「第三十八弾」参照。
- フェーズ63(2026-08-17 02:00 UTC): 「次にやること」だった、候補14(仮、濱暁洋オーナー)の
  スタッフ数一次情報確認・2026年時点の稼働継続確認をWebSearchで行った。開業時期(2020年4月)と
  ブランド全体の2026年時点での活発な展開(2026年7月に20店舗新規オープン等)から稼働継続中の
  可能性は高いと判断できたが、スタッフ数の一次情報はcurama.jp・osoujikakumei.jpともWebFetchの
  egress制約により今回も直接確認できず、候補2・13と同水準の間接傍証にとどまった。候補2・13の
  昇格時と同基準により候補14を正式候補に昇格させ、フランチャイズ加盟系候補を候補2・13・14の
  3件で確定。新規候補探索(第十六弾開始、3回の試行で増分縮小)はここで打ち切り、次のステップ
  (初回コンタクト文面の草案作成)に進む方針とした。詳細は上記candidate-longlist-draft.md
  「第三十九弾」参照。
- フェーズ64(2026-08-17 03:00 UTC): 「次にやること」だった、フランチャイズ加盟系候補
  (候補2・13・14)確定を受けた初回コンタクト文面の草案作成に着手した。既存の
  initial-contact-message-draft.md(独立系候補1・3・7向け)に、フランチャイズ加盟系候補向けの
  追加節を新設した。独立系との違い(本部の代表窓口ではなく店舗個別の窓口を用いる、本部
  ブランド名ではなく店舗・オーナー個人宛の依頼として文面を調整する)を整理し、候補2は所在
  エリア未特定のため実送信対象に含めないこと、候補13・14は店舗ページの問い合わせフォーム・
  ブログコメント欄の有無確認が次回以降の課題として残ることを明記した。詳細は
  initial-contact-message-draft.md「フランチャイズ加盟系候補(候補2・13・14)への追加留意点」
  参照。
- フェーズ65(2026-08-17 04:00 UTC): 「次にやること」1点目だった、候補2(篠崎昌則オーナー)の
  所在エリア特定をWebSearchで再試行した。これまで混同していた可能性がある東京都江戸川区の
  同名店舗(店長は村上氏で無関係)を除外し、検索語を「阿倍野駅前店 篠崎昌則」に変えたところ、
  本部公式オーナーストーリー(osoujihonpo-fc.com/story/story-7089/)から「大阪府 阿倍野駅前店
  篠崎オーナー」を発見した。脱サラ後にエアコンクリーニング依頼をきっかけに応募したという
  経歴が従前把握していた人物像と整合しており、所在エリアを「大阪府(阿倍野駅前店、登録住所は
  Yahoo!マップ上で大阪市生野区中川)」と暫定特定した。氏名「篠崎昌則」と「阿倍野駅前店
  篠崎オーナー」の同一人物確認は経歴の一致による傍証止まりで、記事本文への直接アクセスは
  WebFetchのegress制約により未確認のまま残る。詳細はcandidate-longlist-draft.md
  「第四十弾」参照。
- フェーズ66(2026-08-17 05:00 UTC): 「次にやること」だった、候補13・14の店舗ページ
  問い合わせフォーム・ブログコメント欄の有無確認をWebSearchで行った。候補13(金井美樹
  オーナー、おそうじ本舗 杉並高井戸店)は本部公式サイト内の店舗別問い合わせフォーム・店舗
  専用ホームページ・LINE公式アカウントを保有していることを確認し、あわせて本部公式サイト内の
  別のオーナーストーリーページ(story-765961305-2)も新たに見つかり氏名・店舗の裏付けが
  一段強化された。候補14(濱暁洋オーナー、おそうじ革命 世田谷桜新町店)は専用ブログに多数の
  記事があり、「開業4年目」「FC名物45日研修の講師を担当」等の記述から独立開業から一定年数が
  経過し本部研修講師を務めるベテランオーナーであることが判明、稼働継続の裏付けが強化された
  (専用問い合わせフォームは未確認、フリーダイヤルでの電話受付は案内あり)。詳細は
  candidate-longlist-draft.md「第四十一弾」参照。
- フェーズ67(2026-08-17 06:00 UTC): interview-rehearsal-script.mdが独立系候補
  (候補1・3・7)のみを対象としており、フランチャイズ加盟系候補(候補13・14)向けの調整が
  未着手だった課題に対応した。候補13・14ではQ11(フランチャイズ向け設問)が独立系のような
  「非該当・代替質問への置き換え」ではなく本題としてそのまま使える点が最大の差分であることを
  整理し、「候補13・候補14向けの調整(フランチャイズ加盟系)」節を新設した。候補13は
  フォーム・LINE経由の日程調整を第一候補、候補14は電話を第一候補とする連絡チャネルの差分、
  候補14固有の研修講師経験を活かした深掘り質問の追加案も記載した。候補2は正式候補への
  昇格が未確定のため本調整の対象外とし、昇格確定後に追加する方針とした。実際のリハーサル
  実施・候補への連絡は行っていない。
- フェーズ68(2026-08-17 09:00 UTC): これまで決済手数料・Firestore課金は
  subscription-billing-cost-estimate.mdで試算済みだったが、原価構造の残る空白だった
  LLM API呼び出し自体のコストが未試算だった点に対応した。llm-system-prompt-draft.md・
  schema/output.schema.jsonの現行ドラフト文字数から入出力トークン数を2シナリオ
  (圧縮後想定/現行ドラフト文字数ベースの上限)で概算し、Claude Haiku 4.5・Sonnet 5・
  Opus 5の生成1回あたりコストを試算した(llm-api-cost-estimate.md新規作成)。
  最も保守的な組み合わせ(Opus 5・上限シナリオ・キャッシュなし)でも従量単価(40〜60円/回)
  の3割程度にとどまり、Sonnet 5+プロンプトキャッシュ利用時は5〜7%程度まで下がる計算となり、
  LLM API原価も決済手数料と同様に事業性を圧迫する主要因にはならないと結論づけた。
- フェーズ69(2026-08-17 12:00 UTC): 「次にやること」だった、候補13・14の店舗ページ
  問い合わせフォーム・ブログコメント欄の有無確認をWebSearch/WebFetchで再試行した。
  WebFetchは本部公式サイト(osoujihonpo.com)・おそうじ革命店舗サイト(osoujikakumei.jp)・
  くらしのマーケット(curama.jp)・本部オーナーストーリーページ(osoujihonpo-fc.com)の
  いずれもEGRESS_BLOCKEDで直接閲覧できず、ドメインを問わず外部サイトへのWebFetchが
  引き続き遮断されていることを改めて確認した。方針を転換し、WebSearchで既に得られていた
  第四十一弾時点の情報(候補13はLINE公式・店舗別問い合わせフォーム・店舗専用HP、候補14は
  専用問い合わせフォームなし・フリーダイヤル0120-849-252)を初回コンタクト連絡チャネルの
  確定情報としてinitial-contact-message-draft.mdに反映した(候補13は第一候補をLINE公式、
  候補14は第一候補を電話に確定)。スタッフ数(5名以下該当)の一次情報での直接確認は
  WebFetch制約により引き続き未達のまま残る。
- フェーズ70(2026-08-17 13:00 UTC): 「次にやること」だった、候補2(篠崎昌則オーナー)の
  所在エリア特定・氏名確認を、これまでのweb-repo.jp系記事に加え本部公式サイトの店舗ページを
  検索対象に加えて再試行した。「おそうじ本舗 店舗検索 阿倍野駅前店 篠崎」のWebSearchにより
  本部公式サイト内の店舗ページ(osoujihonpo.com/shop/detail/15773/)と店舗独自サイト
  (osouji-abenoekimae.com)を新規発見し、フランチャイズ全国大会での優秀賞受賞歴
  (2019・2021・2022・2023年)という稼働継続性の一次情報も確認できた。一方、氏名表記に
  「篠崎」/「篠﨑」の異体字差異が残り、店舗独自サイト経由の問い合わせ窓口有無もWebFetchの
  egress制約により確認できなかったため、候補2は依然初回コンタクトの実送信対象に含めない
  (詳細はcandidate-longlist-draft.md「第四十二弾」参照)。
- フェーズ71(2026-08-17 15:00 UTC): 「次にやること」だった、候補2の氏名表記の異体字差異
  (篠崎/篠﨑)の解消と店舗独自サイト(osouji-abenoekimae.com)の連絡先確認をWebSearchで
  再試行した。本部公式サイトのオーナーインタビューページ(story-7089)・第三者媒体
  (web-repo.jp)双方で氏名表記が「篠崎」に統一されていることを確認し異体字差異を解消。
  また店舗独自サイトの連絡先として電話番号(0120-922-589)・住所(大阪市阿倍野区松虫通)・
  店舗独自LINE公式アカウントを新たに確認し、初回コンタクトチャネルの選択肢を確定した。
  候補2は正式候補への昇格に足る一次情報が揃った状態になったが、最終的な昇格判断・初回
  コンタクト文面への反映は次回に持ち越す(詳細はcandidate-longlist-draft.md
  「第四十三弾」参照)。
- フェーズ72(2026-08-17 17:00 UTC): フェーズ71の残課題だった、候補2を正式候補へ昇格させる
  かの最終判断と、初回コンタクト文面(initial-contact-message-draft.md)への電話・LINE公式
  チャネルの反映を行った(candidate-longlist-draft.md「第四十四弾」参照)。所在エリア・
  実在性・氏名表記・連絡チャネルの4点が揃ったことを踏まえ候補2を正式候補に確定し、
  候補13と同様の理由付け(本人の目に留まりやすく返信のハードルが低い)でLINE公式アカウントを
  第一候補チャネル、フリーダイヤル電話を代替チャネルとした。これによりフランチャイズ加盟系
  候補2・13・14の3件はいずれも正式候補化・連絡チャネル確定が完了した。
- フェーズ73(2026-08-17 18:00 UTC): 「次にやること」だった、候補13・14のスタッフ数
  (5名以下該当)の一次情報確認をWebSearchで再試行した。候補13(金井美樹オーナー、おそうじ
  本舗 杉並高井戸店)は店舗紹介記事に「一人暮らしの女性のお客様にも安心していただけるよう
  女性スタッフが対応しています」との記述を新たに確認し、オーナー本人とは別にスタッフが
  存在する間接傍証を得た(正確な人数は依然不明)。候補14(濱暁洋オーナー、おそうじ革命
  世田谷桜新町店)はスタッフ人数に触れた記述が今回も見つからず、第四十一弾以降2回連続で
  新情報なしとなったため、次回は求人記事経由の探索への切り替えを検討する。詳細は
  candidate-longlist-draft.md「第四十五弾」参照。
- フェーズ74(2026-08-17 19:00 UTC): 「次にやること」だった、候補14のスタッフ数の求人記事
  経由再探索と、候補9(仮)の氏名特定(第十八弾で消去法の最有力候補とした柳川敬士さんの
  本人確認)をWebSearchで試みた。候補14は求人情報が見つからず3回連続で新情報なし。候補9は
  柳川敬士さんの具体的な開業時期・所在地(2018年6月・東京都足立区足立西新井店、おそうじ革命
  KIREI produce)が新たに確認できたが、これは候補9の実績仮説(神奈川県・2019年7月開業)と
  地域・時期の両方で矛盾しており、柳川さんも除外と判断した。第十八弾の消去法候補4名
  (細川さん・高野さん・小浦さん・柳川さん)は全員除外となり、候補9の氏名特定は現アプローチ
  では行き詰まった。詳細はcandidate-longlist-draft.md「第四十六弾」参照。
- フェーズ75(2026-08-17 23:00 UTC): 「未確認・次回への申し送り(第四十六弾時点)」だった、
  候補3(hello-osouji.com/onestop-direct.com)の事業比重再確認をWebSearchで再試行した。
  快線屋(ワンストップダイレクト)の事業の出自が「製品販売から取付工事まで」のワンストップ
  提供にあり、分解洗浄クリーニングは対応業者が0.1%程度という差別化された付加サービスと
  位置付けられていること、メインサイトonestop-direct.comのSEOタイトルが「エアコン取り付け」を
  前面に出していることを新たに確認した。売上比率そのものの一次情報や快線屋の会社概要
  (代表者・従業員数)はWebFetchのegress制約により今回も確認できず、候補3は正式候補の
  ステータスを維持したまま次回に持ち越す(詳細はcandidate-longlist-draft.md「第四十七弾」参照)。
- フェーズ76(2026-08-18 03:00 UTC): limit-approaching-notification-design.mdで設計済み
  だった月間生成回数カウント・上限接近通知を、course-set-pashaのUsageCounterProtocol/
  InMemoryUsageCounter/build_usage_noticeと同じ構成でprototype/cloud_function_webhook.pyに
  実装した。本venture固有の差異として、course-set-pashaのプラン別閾値マッピング
  (PLAN_NOTICE_THRESHOLDS)は持たず、設計2節の方針通り3プラン共通の固定閾値
  (NOTICE_THRESHOLD=5)のみとした。process_memo_event()にusage_counter/plan/month引数を
  追加し、status=="generated"かつevent.source.userIdがある場合のみカウント・通知を行う
  (未接続時は従来通りスキップ)。3プランの境界値(35/85/145回目到達・上限超過)を含む
  テスト13件を新規追加し、test_cloud_function_webhook.py全26件・test_post_generation_
  checks.py全41件がパスすることを確認した。実Firestore接続はオーナー承認待ちのため、
  引き続きInMemoryスタブでの検証にとどまる。
- フェーズ77(2026-08-18 04:00 UTC): 「未確認・次回への申し送り(第四十五弾時点)」以来
  持ち越されていた、候補13(金井美樹オーナー、おそうじ本舗 杉並高井戸店)のスタッフ数
  (5名以下該当)の一次情報確認を、キーワードを変えてWebSearchで再試行した
  (candidate-longlist-draft.md第四十八弾)。求人媒体一般へのリンクと既知の店舗紹介記事が
  再ヒットしたのみで、第四十五弾で確認済みの「女性スタッフが対応」以上の新規情報(実人数)は
  得られず、2回連続で新情報なしとなった。候補14が第四十六弾で辿った経過(3回連続新情報なし→
  優先度低下)と同様の兆候であり、次回は求人記事経由の探索を1回試すか他の未着手課題を
  先行させるかの判断が必要と申し送った。
- フェーズ78(2026-08-18 06:00 UTC): フェーズ77の申し送り通り、候補13のスタッフ数確認を
  求人記事経由の検索式(「おそうじ本舗 杉並高井戸店 求人」「同 スタッフ募集」)に切り替えて
  再試行した(candidate-longlist-draft.md第四十九弾)。本部一括採用ページ・求人媒体一般への
  リンクのみがヒットし、店舗単独の求人票・スタッフ人数を示す記述は得られず3回連続で新情報
  なしとなった。候補14が第四十六弾で辿った経過(3回連続新情報なし→優先度低下)と同一
  パターンに達したため、候補13についてもスタッフ数の個別深掘りを一旦打ち切り「要精査」の
  まま維持する方針に転換した。次回は独立系候補6件の深掘り・候補8の地域特定・候補9の氏名
  特定アプローチ再設計等、他の未着手課題を優先する。
- フェーズ79(2026-08-18 07:00 UTC): course-set-pasha・line-reservation-aiには既にある
  unit-economics-estimate.md(決済手数料・Firestore原価・LLM API原価を統合した1業者
  あたり月次粗利試算)が本ventureには未作成だったため新規作成した。既存の
  pricing-plan.md・subscription-billing-cost-estimate.md・llm-api-cost-estimate.mdの
  試算値を統合し、3プランいずれも粗利率84.8〜87.1%(キャッシュなし)・91.6〜92.5%
  (プロンプトキャッシュ利用時)を確保できる見込みと確認した。course-set-pashaとの比較で、
  本ventureは月間利用回数がひとケタ多いためLLM API原価の絶対額が大きく粗利率が3〜6ポイント
  低いこと、プランが上がるほど粗利率がわずかに下がる本venture固有の傾向があることを新たに
  明らかにした。次回は、市場調査が指摘する強い季節性(繁忙期は閑散期の2〜3倍)を踏まえた
  月別(繁忙期/閑散期)の粗利シミュレーションを残課題として整理する。
- フェーズ80(2026-08-18 08:00 UTC): candidate-longlist-draft.md「第四十九弾」の申し送り
  通り、複数メニュー展開のハウスクリーニング業者区分の新規探索を新キーワード(「個人事業主
  一人で 開業」「くらしのマーケット セット 出張」)で再試行した(candidate-longlist-draft.md
  第五十弾)。いずれも開業ガイド記事・ポータルのカテゴリページ・口コミまとめサイトが上位を
  占め、独立系候補6件探索時と同様に個別事業者名への到達率が低い傾向を確認した。この区分は
  汎用の開業ガイド系キーワードでは頭打ちであり、候補13・14をおそうじ本舗ブランド内で発見
  できた時と同じ「ポータル内の個別プロフィール・口コミ本文を直接手がかりにする」方式への
  切り替えが必要と結論した。次回は独立系候補6件(候補1・3・7・10・12)の深掘り・候補8の
  地域特定・候補9の氏名特定アプローチ再設計を優先する。
- フェーズ81(2026-08-18 11:00 UTC): フェーズ80の申し送り通り、複数メニュー展開の
  ハウスクリーニング業者区分の新規探索を、候補13・14を発見した時と同じ「ポータル内の個別
  プロフィール・口コミ本文を直接手がかりにする」検索式に切り替えて再々試行した
  (candidate-longlist-draft.md第五十一弾)。「くらしのマーケット エアコンクリーニング
  ハウスクリーニング セット 出張 個人事業主 口コミ」「site:curama.jp エアコンクリーニング
  ハウスクリーニング 両方 対応 一人で」のいずれも、カテゴリ一覧ページ・比較記事・マガジン
  記事のみがヒットし個別事業者プロフィールには到達せず、2回連続で候補ゼロのまま変化が
  なかった。次回は地域名を先に絞り込む検索式、またはくらしのマーケット以外のポータル
  (ホットペッパー等)への切り替えを試すか、独立系候補6件の深掘り・候補9の氏名特定
  アプローチ再設計を先行させるかを次回判断する。
- フェーズ82(2026-08-18 12:00 UTC): 候補探索がWebSearchの手詰まりで足踏み中のため、
  技術面の未着手課題に切り替えた。line-reservation-ai・course-set-pashaには既にある
  deployment-runbook.mdが本ventureには未作成だった点を解消し、GCPプロジェクト作成承認後の
  実行手順(GCPプロジェクト作成→Firestore有効化→シークレット管理→Cloud Functionsデプロイ→
  LINE公式アカウント開設→結合テスト→本番投入前チェックリスト)を新規整理した
  (deployment-runbook.md)。course-set-pashaの手順書をベースにしつつ、本venture固有の
  想定利用ペース(月60〜100件、繁忙期はさらに増加)を踏まえ、Cloud Functionsの同時実行数に
  余裕を持たせる必要がある点、LINEメッセージ通数消費がフリープラン上限に収まるか結合テストで
  確認する必要がある点を追記した。本ドキュメント作成自体はアカウント作成・課金を伴わない
  机上整理であり、承認前に着手してよい範囲内の作業として実施(手順の実行自体は引き続き
  pending-approval.md記載のオーナー承認待ち)。
- フェーズ83(2026-08-18 15:00 UTC): course-set-pashaのapi-call-failure-handling.md
  相当のドキュメントが本ventureには未作成だった点を解消した。course-set-pashaと同様
  「単方向バッチ処理・Reply APIのみ・Cloud Tasksなし」という前提が一致するため、方針を
  そのまま踏襲しつつ本venture固有の差異(`generate()`に`has_photo`引数を持たない簡略版)を
  反映した設計ドキュメント(api-call-failure-handling.md)を作成し、
  `LlmApiError`/`ReplyApiError`例外・`_generate_with_api_retry()`/`_reply_with_retry()`
  (即時1回のみリトライ)・`API_FAILURE_FALLBACK_MESSAGE`・`MemoProcessResult.api_failure`を
  `prototype/cloud_function_webhook.py`に実装した。`FlakyOnceLlmClient`/
  `AlwaysFailingLlmClient`/`FlakyOnceReplyClient`/`AlwaysFailingReplyClient`スタブを
  `prototype/test_cloud_function_webhook.py`に追加し、LLM API/Reply API呼び出し失敗時の
  リトライ成功・2回とも失敗時のフォールバックの4パターンをテストで確認した(テスト4件追加、
  全45件パス)。実LLM/実LINE API接続後の一次情報確認・レイテンシ実測は引き続き未検証事項
  (詳細は同ドキュメント「未検証・要検討事項」参照)。
- 最終更新: 2026-08-18 15:00 UTC

## 次にやること(候補)

- (解消(効果薄と確認) 2026-08-18 08:00 UTC: フェーズ80で複数メニュー展開のハウスクリー
  ニング業者区分の新規探索を「個人事業主 一人で 開業」「くらしのマーケット セット 出張」の
  新キーワードで再試行したが、開業ガイド記事・ポータルのカテゴリページばかりがヒットし
  個別事業者名には到達しなかった。汎用の開業ガイド系キーワードではなくポータル内の個別
  プロフィール・口コミ本文を直接手がかりにする方式への切り替えが必要と結論し、次回以降は
  独立系候補6件の深掘り・候補8の地域特定・候補9の氏名特定アプローチ再設計を先行させる方針に
  転換した。詳細は上記フェーズ80・candidate-longlist-draft.md「第五十弾」参照)
- (解消・打ち切り 2026-08-18 06:00 UTC: 候補13のスタッフ数確認はフェーズ78・第四十九弾で
  3回連続新情報なしとなり、候補14と同様に個別深掘りを打ち切り「要精査」のまま維持する方針に
  転換した。次回は独立系候補6件〈候補1・3・7・10・12〉の深掘り・候補8の地域特定・候補9の
  氏名特定アプローチ再設計等、他の未着手課題を優先する。詳細は上記フェーズ78・
  candidate-longlist-draft.md「第四十九弾」参照)
- 実LLM接続の承認が得られ次第、`count_tokens`エンドポイント(無料)でllm-api-cost-
  estimate.mdのシナリオA/Bどちらに近いか正確なトークン数を確認し、モデル選定
  (Sonnet 5想定)とプロンプトキャッシュ導入(cache_control付与)を実装する
  (詳細は上記フェーズ68・llm-api-cost-estimate.md参照)。
- (継続 2026-08-17 23:00 UTC: 候補3の事業比重再確認をフェーズ75で再試行した。快線屋の
  事業の出自が販売・取付側にあることを示す間接傍証は得られたが、売上比率そのものの一次
  情報・会社概要(代表者・従業員数)はWebFetchのegress制約により今回も未確認のまま。
  正式候補ステータスは維持。詳細は上記フェーズ75・candidate-longlist-draft.md
  「第四十七弾」参照)
- (一部解消 2026-08-17 18:00 UTC: 候補13・14のスタッフ数確認をフェーズ73で再試行した。
  候補13は「女性スタッフが対応」という間接傍証を新たに得た。候補14は2回連続で新情報が
  得られず、次回は求人記事経由の探索への切り替えを検討する。詳細は上記フェーズ73・
  candidate-longlist-draft.md「第四十五弾」参照)
- (保留へ転換 2026-08-17 19:00 UTC: 候補14のスタッフ数を求人記事経由でフェーズ74で
  再試行したが求人情報自体が見つからず3回連続で新情報なしとなったため、優先度を下げ
  他の未着手課題を先行させる方針に転換した。詳細は上記フェーズ74・
  candidate-longlist-draft.md「第四十六弾」参照)
- (解消済み 2026-08-17 17:00 UTC: 候補2を正式候補へ昇格させるかの最終判断と、初回コンタクト
  文面〈initial-contact-message-draft.md〉への電話・LINE公式チャネルの反映をフェーズ72で
  行った。詳細は上記フェーズ72・candidate-longlist-draft.md「第四十四弾」参照。フランチャイズ
  加盟系候補2・13・14の3件はいずれも正式候補化・連絡チャネル確定が完了し、残るは候補13・14の
  スタッフ数〈5名以下該当〉の一次情報確認)
- (解消済み 2026-08-17 06:00 UTC: フランチャイズ加盟系候補〈候補13・14〉向けの
  ヒアリングリハーサル台本調整をフェーズ67で行った。Q11を本題としてそのまま使う点を
  中心に、連絡チャネル・深掘り質問の差分を整理した。詳細は上記フェーズ67・
  interview-rehearsal-script.md「候補13・候補14向けの調整(フランチャイズ加盟系)」参照。
  候補2は正式候補への昇格が未確定のため対象外とした)
- (解消済み 2026-08-17 05:00 UTC: 候補13・14の店舗ページ問い合わせフォーム・ブログコメント欄の
  有無確認をフェーズ66で行った。候補13は本部公式問い合わせフォーム・専用HP・LINE公式を保有、
  候補14は専用ブログで稼働継続〈開業4年目・研修講師〉を裏付け。詳細は上記フェーズ66・
  candidate-longlist-draft.md「第四十一弾」参照。残るはいずれもスタッフ数の一次情報での
  直接確認〈WebFetch egress制約により持ち越し〉)
- (一部解消 2026-08-17 13:00 UTC: 候補2の所在エリア・店舗の実在性をフェーズ70で本部公式
  サイトの店舗ページ・店舗独自サイトという一次情報で確認した。ただし氏名表記の異体字差異
  〈篠崎/篠﨑〉が残り、店舗独自サイト(osouji-abenoekimae.com)経由の問い合わせ窓口有無も
  WebFetch制約により未確認のため、初回コンタクトの実送信対象には引き続き含めない。詳細は
  上記フェーズ70・candidate-longlist-draft.md「第四十二弾」参照)
- (解消済み 2026-08-17 04:00 UTC: 候補2の所在エリア特定をフェーズ65で行い、「大阪府
  阿倍野駅前店(登録住所は大阪市生野区中川)」と暫定特定した。詳細は上記フェーズ65・
  candidate-longlist-draft.md「第四十弾」参照)
- 候補13・14の店舗ページ問い合わせフォーム・ブログコメント欄の有無確認(WebFetchのegress
  制約により未確認)。
- 候補13・14のスタッフ数(5名以下該当)の一次情報での直接確認は、WebFetchのegress制約により
  引き続き未解決(間接傍証止まり)。実接続(オーナー承認後)の際に優先確認する課題として残す。
- (解消済み 2026-08-17 03:00 UTC: フランチャイズ加盟系候補向けの初回コンタクト文面の草案作成に
  フェーズ64で着手した。詳細は上記フェーズ64・initial-contact-message-draft.md参照)
- (解消済み 2026-08-17 02:00 UTC: 候補14(仮)のスタッフ数・稼働継続確認をフェーズ63で行い、
  候補2・13と同基準で正式候補に昇格、フランチャイズ加盟系候補を候補2・13・14の3件で確定した。
  詳細は上記フェーズ63・candidate-longlist-draft.md「第三十九弾」参照)
- (解消済み 2026-08-17 00:59 UTC: おそうじ本舗以外のブランドからの探索をフェーズ62で行い、
  「おそうじ革命」世田谷桜新町店の濱暁洋オーナーを候補14(仮)として発見・仮登録した。詳細は
  上記フェーズ62・candidate-longlist-draft.md「第三十八弾」参照)
- 候補13の店舗詳細ページ本文・現在のスタッフ数の一次情報での直接確認(WebFetchのegress制約に
  より持ち越し)。次回はWebSearchでの追加スニペット取得や別角度からの確認を試みる。
- (解消済み 2026-08-16 19:00 UTC: フランチャイズ加盟系候補4〜6の精査継続か除外確定かの判断を
  フェーズ60で行った。3件とも複数名スタッフ体制を示唆する記述が確認されたため正式に除外確定と
  した。詳細は上記フェーズ60・candidate-longlist-draft.md「第三十六弾」参照)
- (解消済み 2026-08-16 17:00 UTC: 候補13〈仮〉の氏名・所在エリア確認をフェーズ58で行った。
  「金井美樹オーナー(おそうじ本舗 杉並高井戸店、東京都杉並区)」と判明し正式候補に昇格。
  詳細は上記フェーズ58・candidate-longlist-draft.md「第三十四弾」参照)
- (解消済み 2026-08-16 15:00 UTC: 独立系候補6件〈候補1・3・7・10・12〉で目標下限に到達し
  新規探索が頭打ちだったため、フェーズ57でフランチャイズ加盟系への軸足転換を判断した。詳細は
  上記フェーズ57・candidate-longlist-draft.md「第三十三弾」参照)
- (解消済み 2026-08-16 12:00 UTC: 候補12(東京住まいる)のスタッフ数確認をフェーズ56で
  3回目試行したが新情報なし。候補1・7・3と同様に間接傍証のみで正式候補に昇格させた。詳細は
  上記フェーズ56・candidate-longlist-draft.md「第三十二弾」参照)
- (解消済み 2026-08-16 07:00 UTC: 「解約」インテントの誤検知境界設計をフェーズ54・
  llm-system-prompt-draft.md厳守事項6aで行った。schema/output.schema.json相当への反映
  〈status enum拡張案〉、実LLM接続後の判定精度検証、機械チェック実装は次の課題として残る。
  詳細は上記フェーズ54参照)
- 季節に応じたプラン変更のしやすさへのニーズ確認は、customer-interview-design.mdの質問項目
  追加として今後反映する。(詳細は上記フェーズ53参照)
- 候補12(東京住まいる)のクリーニングと設置工事(電気工事業登録)の事業比重を候補3と
  同様の観点で次回さらに確認し、正式候補への昇格を判断する。スタッフ数(5名以下)の
  確認も引き続き課題。(詳細はcandidate-longlist-draft.md「第三十弾」参照)
- (解消済み 2026-08-16 03:00 UTC: 候補12のスタッフ数・「住宅メンテナンス事業」の事業比重
  確認にフェーズ52で着手した。分解洗浄主力の訴求は確認できたが電気工事関連の言及もあり、
  正式候補への昇格判断は次回に持ち越し。詳細は上記フェーズ52・candidate-longlist-draft.md
  「第三十弾」参照)
- 独立系候補は5件(候補1・3・7・10・12暫定)、目標(6〜7件)まで残り1〜2件のため、
  次回も新規候補探索を継続する。
- (解消済み 2026-08-16 02:00 UTC: 独立系の新規候補探索をフェーズ51で継続し、候補12(暫定・
  東京住まいる)を新規発見した。あわせて発見した「エアタクミ」はフランチャイズ本部と判明し
  除外条件に該当するため候補に加えなかった。詳細は上記フェーズ51・candidate-longlist-draft.md
  「第二十九弾」参照)
- (解消済み 2026-08-16 01:00 UTC: 候補11(エアクリ)は保留とし、独立系の新規候補探索
  (残り2〜3件、目標6〜7件)を優先する方針とした。(詳細はcandidate-longlist-draft.md
  「第二十八弾」参照)
- interview-rehearsal-script.mdへの「技術指導・研修事業を兼業する候補」向け留意点の反映は、
  該当候補が正式候補に確定した段階で行う。(詳細は上記フェーズ50・
  interview-candidate-selection-criteria.md参照)
- (解消済み 2026-08-16 01:00 UTC: 候補11自身の所在エリア・代表者名・スタッフ数の特定を
  フェーズ50で試みたが3回連続で未特定のまま。詳細は上記フェーズ50・candidate-longlist-draft.md
  「第二十八弾」参照)
- (解消済み 2026-08-16 00:00 UTC: 候補11の類似ドメイン異同確認をフェーズ49で行い、
  aircle.net等4件が無関係の別事業者であることを確認した。詳細は上記フェーズ49・
  candidate-longlist-draft.md「第二十七弾」参照)
- (解消済み 2026-08-15 21:00 UTC: 独立系候補の追加確保をフェーズ48で継続し、候補11
  〈エアクリ〉を新規発見した。詳細は上記フェーズ48・candidate-longlist-draft.md
  「第二十六弾」参照)
- 独立系候補は4件(候補1・3・7・10)となり目標(6〜7件)まで残り2〜3件のため、
  次回も新規候補探索を継続する。(詳細はcandidate-longlist-draft.md「第二十五弾」参照)
- (解消済み 2026-08-15 19:00 UTC: 候補10の専用サイト・専用訴求の有無をフェーズ47で
  確認し、必須条件該当を確認して正式候補に昇格させた。詳細は上記フェーズ47・
  candidate-longlist-draft.md第二十五弾参照)
- (解消済み 2026-08-15 18:00 UTC: 候補10のスタッフ数・主力メニュー該当確認にフェーズ46で
  着手した。幅広いメニュー構成が判明し「必須条件の該当確認中」のまま持ち越しとなった。
  詳細は上記フェーズ46・candidate-longlist-draft.md第二十四弾参照)
- (解消済み 2026-08-15 17:00 UTC: 独立系候補の追加確保を先行する方針を採り、候補10
  〈キキのおそうじ屋〉を新規発見した。詳細は上記フェーズ45・candidate-longlist-draft.md
  第二十三弾参照)
- (解消済み 2026-08-15 16:00 UTC: リハーサル台本を候補3〈hello-osouji.com〉・候補7
  〈Clean Labo〉向けにも展開した。詳細は上記フェーズ44・interview-rehearsal-script.md
  「候補3・候補7向けの調整」参照)

- (解消済み 2026-08-15 07:00 UTC: 複数メニュー展開のハウスクリーニング業者区分の新規探索が
  頭打ちのため方針転換し、既発見の独立系候補〈候補1・3・7〉のメニュー内容をフェーズ39で
  個別確認した。候補1・7は必須条件への該当を明確化できたが、候補3は取付・販売主体の
  姉妹サイトとクリーニング専門サイトを分けて運営している実態が判明し、クリーニングの
  事業比重は依然不明瞭なまま残る)
- (解消済み 2026-08-15 07:58 UTC: 候補7と店舗ID〈054122114〉の同一/別事業者確認を
  フェーズ40で行った。054122114は埼玉県さいたま市緑区の無関係の別事業者と判明し、
  店舗ID重複疑惑は解消。候補7のスタッフ数〈5名以下〉一次情報での直接確認は
  「店長本人が訪問」という間接傍証止まりで未解決のまま残る)
- (解消済み 2026-08-15 10:00 UTC: 候補3〈hello-osouji.com/ワンストップダイレクト〉の
  事業全体における取付・販売とクリーニングの比重確認をフェーズ41で行った。取付・販売
  〈onestop-direct.com〉とクリーニング〈hello-osouji.com〉を別ドメインで独立運用している
  実態から必須条件〈訪問分解洗浄が主力〉への該当を確認し正式候補に昇格。スタッフ数
  〈5名以下〉の一次情報での直接確認は候補1・7と同様間接傍証止まりで未解決のまま残る)
- (解消済み 2026-08-15 01:00 UTC: 月間生成回数カウント用データストア〈Firestore等〉の
  読み書き課金の原価試算をフェーズ37・subscription-billing-cost-estimate.mdで行った。
  数百業者規模までは無料枠内に収まる見込みだが、最繁忙日の日次操作数の仮定〈20回/日〉は
  実運用データでの再検証が必要な課題として残る)
- (解消済み 2026-08-14 23:00 UTC: 本venture固有の季節性を踏まえた上限接近時の事前通知設計を
  フェーズ36・limit-approaching-notification-design.mdで行った。「残り5回」固定閾値の
  妥当性検証・繁忙期固有閾値の要否は実運用データ待ちの課題として残る)
- (解消済み 2026-08-14 22:00 UTC: 月間生成回数を積算する軽量データストア〈Firestore等〉の
  導入方針・技術構成をtech-stack.mdとして新規作成した。course-set-pashaの最小構成
  〈ユーザー1人=1ドキュメント、month・countのみ〉を踏襲する方針とした)
- (解消済み 2026-08-14 03:00 UTC: aircon-pasha-tests.ymlの初回CI実行結果をフェーズ27で
  確認した。status: completed / conclusion: success、ローカル確認結果と一致。次に
  aircon-pasha配下を変更するコミットで改めてrun結果を確認する)
- prototype/cloud_function_webhook.pyのLLM呼び出し・返信送信は実クライアント未接続の
  スタブのままのため、実LLM API接続後は実際の生成結果に対してvalidate_llm_outputが
  想定通り機能するかの再検証が必要(オーナー承認待ち)。
- prototype/post_generation_checks.pyのヒューリスティックは、course-set-pashaと同様
  キーワード近傍探索に依存しており、実LLM接続後は拾いきれない違反パターンの収集・
  ルール改善が必要になる見込み(実LLM呼び出しはオーナー承認待ち)。
- 候補8(猫の手/本田二三惠、curama.jp/849994132/)は3回連続で地域特定に至らなかったため、
  次回はブログ投稿経由の探索を試すか、それでも不明なら保留・除外に回して他の代替候補探索に
  切り替えるかを判断する。あわせてSER562451587(保護猫3匹の癒し系店長/屋号「幸せの種」)との
  関係(同一事業者か別事業者か)も整理する。
- 複数メニュー展開のハウスクリーニング業者区分は、curama.jp事業者プロフィール単位の
  絞り込み方式が今回も新規候補につながらなかったため、優先度を下げ他の未着手課題を先行させる。
- (解消済み 2026-08-14 12:00 UTC: 候補1の運営法人をフェーズ30で「リノビー合同会社」
  〈法人番号9330003009063、2021年設立〉と確度高く確認した。「ニシムラ・プロバイズ
  株式会社」は誤情報と判断し追跡打ち切り。2024年11月の本店移転〈中央区下通→南区護藤町〉
  も判明し、複数住所表記の一部を整理できた。残るのは東区上南部〈店舗所在地〉と南区護藤町
  〈法人登記上の本店〉の関係整理のみで、優先度は下げる)
- (解消済み 2026-08-14 16:00 UTC: 候補4〈山元オーナー〉の開業時期・スタッフ数確認を
  フェーズ31で再試行したが、開業時期は依然不明、スタッフ体制は候補5・6と同様「複数名
  在籍」を示唆する間接情報にとどまった。5回目の試行で新情報の増分がほぼ止まったため、
  候補4〜6の個別深掘りは打ち切り、要精査〈除外候補寄り〉のまま維持する方針に転換した)
- (解消済み 2026-08-14 18:00 UTC: フランチャイズ加盟区分の代替候補探索をフェーズ32で
  新方針(アントレの個別オーナーレポート経由)で実施した。神奈川県・2019年7月開業・
  ワンオペ・年商1,300万円という有望な実績〈候補9・仮〉を発見したが氏名は未特定。
  次回は柳川敬士さん・細川宗晧さん・小浦さゆりさん・高野恭平さんの各レポートを
  個別に確認し氏名を特定する)
- (一部解消・保留 2026-08-14 20:00 UTC: フェーズ33で柳川敬士さん・細川宗晧さん・
  小浦さゆりさん・高野恭平さんの各オーナーレポートを個別にWebSearchした。細川さん・
  高野さん・小浦さんの3名は候補9〈神奈川県・2019年7月開業・ワンオペ・年商1,300万円〉の
  実績と矛盾し除外、消去法で柳川さんが最有力だがWebFetchのegress制約により本人確認が
  取れず氏名確定には至らなかった。これ以上の絞り込みは新情報の増分が乏しいと判断し保留、
  他の未着手課題を先行させる方針に転換した)
- (解消(除外確定) 2026-08-17 19:00 UTC: フェーズ74で柳川敬士さんの本人確認を再試行した
  ところ、実際の開業時期・所在地は2018年6月・東京都足立区足立西新井店(おそうじ革命
  KIREI produce)であることが判明し、候補9の実績仮説〈神奈川県・2019年7月開業〉と地域・
  時期の両方で矛盾するため柳川さんも除外と判断した。第十八弾の消去法候補4名は全員除外と
  なり、候補9の氏名特定は現アプローチ〈アントレ個別オーナーレポート経由の消去法〉では
  行き詰まった。次回再開する場合は探索アプローチの再設計〈新キーワード・別媒体〉が必要
  〈詳細はcandidate-longlist-draft.md「第四十六弾」参照〉)
- (解消(打ち切り) 2026-08-18 14:00 UTC: 複数メニュー展開のハウスクリーニング業者区分の
  探索を、くらしのマーケット以外のポータル(ユアマイスター/yourmystar.jp)への切り替えと
  地域先絞り込みの検索式でフェーズ続き(candidate-longlist-draft.md第五十二弾)として再試行
  したが、個別事業者のプロフィールページには到達できず新規候補ゼロだった。第五十弾・
  第五十一弾と合わせ3回連続で新規候補ゼロとなったため、候補13・14と同様の基準で本区分の
  探索を一旦打ち切り、独立系候補6件の深掘り・候補8の地域特定・候補9の氏名特定アプローチ
  再設計・候補3の売上比率確認を優先する方針に転換した)
- ロングリストが選定基準の目標件数(独立系6〜7件・フランチャイズ加盟3〜4件・複合メニュー
  業者3件程度)に近づいた段階で、course-set-pashaのinitial-contact-message-draft.mdに
  相当する初回コンタクト文面の草案を作成する。
- 上記が揃った段階で、line-reservation-aiのinterview-rehearsal-script.mdに
  相当するリハーサル台本を作成し、質問数13問が想定時間(10〜15分)に収まるか机上で検証する。
- 実LLM呼び出し・SNS API連携等、外部サービスとの実接続はオーナー承認が必要なため、
  設計・下書き作成の範囲に留める。
- (解消済み 2026-08-16 15:00 UTC: 独立系候補が6件で目標下限に到達し新規探索が頭打ちに
  なっていたことを受け、フェーズ57で候補選定の軸足を独立系からフランチャイズ加盟系に
  転換した。web-repo.jp「フランチャイズWEBリポート」で候補2〈篠崎昌則オーナー〉と同種の
  新規インタビュー記事(専門学校職員から独立した女性オーナーの4年間の歩み)を発見し、
  候補13〈仮、氏名未確認〉としてcandidate-longlist-draft.md 第三十三弾にロングリスト
  仮登録した。次回は氏名・所在エリア・スタッフ数〈5名以下該当〉の確認を優先する)
- フェーズ84(2026-08-18 18:00 UTC): 候補9(仮、神奈川県・2019年7月開業・ワンオペ・
  年商1,300万円)の氏名特定について、第十七・十八弾で行き詰まった「アントレの個別
  オーナーレポート経由の消去法」とは別の新アプローチ(フランチャイズ本部公式サイトの
  地域別店舗一覧・月次開店告知記事アーカイブ経由)を設計・試行した
  (candidate-longlist-draft.md第五十三弾)。神奈川大和店の開店告知記事等を辿ったが
  開店年が2023年で候補9の実績(2019年)と不一致、月次開店告知アーカイブも2019年7月分の
  番号特定には至らず、WebFetchのegress制約下では新アプローチも手詰まりと判明した。
  候補9の氏名特定は一旦凍結し、次回以降は独立系候補6件の深掘り・候補8の地域特定・
  候補3の売上比率確認を優先する方針とした。
- フェーズ85(2026-08-18 21:00 UTC): 候補3(hello-osouji.com/onestop-direct.com、
  運営主体「快線屋」)の売上比率(%)・会社概要確認をcandidate-longlist-draft.md第五十四弾で
  再試行した。快線屋の公式サイトが従来把握のhello-osouji.com/onestop-direct.comとは別の
  kaisen-niigata.comであることを新たに確認したが、同サイトへのWebFetchはEGRESS_BLOCKED、
  WebSearchのスニペット経由でも会社概要・売上比率につながる情報は得られず、候補8・9と
  同じ構造的制約(egress制約下での一次情報未到達)で行き詰まった。候補3・8・9の3課題は
  いずれも同一制約によるものと判断し、同種アプローチの反復は次回以降停止する方針とした。
  次回は独立系候補のスタッフ数確認について間接的な手がかり(求人情報・口コミ等)への
  探索軸切り替えを試すか、候補研究以外の未着手領域を優先するかを判断する。
- フェーズ91(2026-08-21 08:00 UTC): llm-system-prompt-draft.md「次の課題」の最後の残項目
  だった、post_generation_checks.py相当の機械チェック(course-set-pashaのcheck_subscription_
  notice_consistency()相当)を実装した。厳守事項6aのkind別制約(cancellation_unclearでは
  カスタマーポータル・手続き完了文言の混入禁止、cancellation_intent/downgrade_intentでは
  includes_portal_link=trueと本文中のポータル言及〈PORTAL_KEYWORDS・URLプレースホルダ・
  短縮URLパターン〉との整合)をヒューリスティックに検証するcheck_subscription_notice_
  consistency()を新設し、run_all_checksに組み込んだ。test_post_generation_checks.pyに
  テスト6件を追加(全25件パス)、schema/validate_test_cases.pyのCI1〜CI3フィクスチャが
  新チェックにも違反しないことを確認した(FixtureCasesTest経由、8件パス)。これで
  llm-system-prompt-draft.md「次の課題」欄の項目はすべて解消済みとなった。
- フェーズ90(2026-08-21 05:00 UTC): 候補研究がWebFetchのegress制約で頭打ちのため、
  技術設計側の未着手課題(llm-system-prompt-draft.md「次の課題」1点目)を前進させた。
  厳守事項6a(解約意図検知)の`status`分岐(cancellation_intent/downgrade_intent/
  cancellation_unclear)に対応するschema/output.schema.jsonの改訂(`subscription_procedure_notice`
  フィールド新設)、course-set-pashaのフェーズ54と同じ構成のPortalLinkProvider Protocol・
  render_subscription_procedure_notice()のprototype/cloud_function_webhook.pyへの実装、
  schema/validate_test_cases.pyへのCI1〜CI3フィクスチャ追加(全8件パス)を行った
  (テスト9件追加、全58件パス)。あわせてsubscription-cancellation-flow-design.mdの
  「未検証の仮説・次の課題」欄にあった解約意図検知境界の未着手記述が、実際には
  llm-system-prompt-draft.md厳守事項6aとして既に整理済みだったことを確認し、記述を
  解消済みへ更新した(ドキュメント間の同期漏れの解消)。
- フェーズ92(2026-08-21 10:00 UTC): 候補10・12がcandidate-longlist-draft.md第三十二弾
  (2026-08-16 12:00 UTC)時点で既に正式候補(独立系5件目・6件目相当)に昇格していたにも
  かかわらず、initial-contact-message-draft.mdとinterview-rehearsal-script.mdへの反映が
  漏れたまま5日間放置されていたことを発見し、両ドキュメントに候補10(キキのおそうじ屋/
  kikinoosoujiya.com)・候補12(東京住まいる/tokyo-smile.jp)の記載を追加した。
  initial-contact-message-draft.mdは「候補ごとの留意点」に2候補分の項目を追加し、
  「独立系の目標件数(6〜7件)に対し現状3件」等の古い件数記述を現状(5件)に更新。
  interview-rehearsal-script.mdは既存の「候補3・候補7向けの調整」と同じ構成で
  「候補10・候補12向けの調整」を新設し、両候補とも既存の差分パターン(候補7型の電話冒頭の
  一言・候補3型の話題限定の一言)の組み合わせで対応できることを確認した。両候補とも
  問い合わせフォーム・電話番号等の連絡チャネル自体は一次情報未確認のまま残っており、
  次回はkikinoosoujiya.com・tokyo-smile.jpの連絡窓口確認を優先課題とする。
- フェーズ93(2026-08-21 11:00 UTC): フェーズ92の申し送り通り、候補10(キキのおそうじ屋/
  kikinoosoujiya.com)・候補12(東京住まいる/tokyo-smile.jp)の連絡チャネルをWebSearchで
  確認した(candidate-longlist-draft.md第五十七弾)。候補10は公式サイトの問い合わせ
  フォーム(kikinoosoujiya.com/contact)とメールアドレス(kikinoosoujiya@gmail.com)を確認でき、
  initial-contact-message-draft.mdの連絡チャネル記載を更新した。候補12は連絡先が未確認の
  まま残ったが、その過程でWebSearchのAI要約が無関係な別会社(tokyo-smile.co.jp/株式会社
  東京スマイル、不動産・住宅支援業)の電話番号・会社概要を候補12の情報として誤って返す
  事例を発見した。これは候補1・候補7・候補8で既出の「屋号・ドメイン類似による誤結合」と
  同種のリスクが4件目として現れたものであり、interview-candidate-selection-criteria.mdに
  「屋号・ドメイン類似による誤結合への注意」節を新設し、候補の公式ドメインと情報源URLの
  一致確認を必須手順として明文化した。次回は候補12の連絡先確認(tokyo-smile.jp限定での
  再探索)、または独立系候補が概ね揃ったことを踏まえた初回コンタクト実施の是非をオーナーに
  確認する準備を優先する。
- フェーズ94(2026-08-21 12:00 UTC): フェーズ93の申し送り通り、初回コンタクト実施の是非を
  オーナーに確認する準備を進めた。initial-contact-message-draft.mdを確認したところ、独立系
  候補5件(候補1・3・7・10・12)・フランチャイズ加盟候補3件(候補2・13・14)の計8件について
  連絡チャネル・文面草案・候補ごとの留意点が出揃っており、line-reservation-ai(2026-07-30
  01:58 UTC承認済み)・course-set-pasha(2026-08-09 01:00 UTC)と同じ「顧客ヒアリング実施の
  承認確認」を行える状態に達したと判断した。候補12(東京住まいる)のみ連絡先が一次情報未確認
  のまま残るが、他7件は連絡チャネル確認済みのため、候補12を除く7件から着手できる旨を含めて
  pending-approval.mdに承認確認事項を追記した。本人への電話・メール等の実連絡はオーナーの
  直接指示があるまで一切行わない。次回は候補12の連絡先確認(tokyo-smile.jp限定)を継続するか、
  オーナーからの承認可否を待つ間に他の未着手領域(実LLM接続後の生成品質検証設計等)を
  前進させるかを判断する。
- フェーズ95(2026-08-21 14:00 UTC): フェーズ94の申し送り通り、承認待ちの間に前進できる
  未着手領域として、llm-system-prompt-draft.mdの未検証事項に残っていた「1メモで複数台の
  エアコンを同時に扱うケースの頻度」をWebSearchで調査した(market-research.md追記)。
  「エアコンクリーニング 1回の訪問 複数台 依頼 料金 セット割引」で検索した結果、2台目以降
  1台あたり1,000〜3,300円程度の割引が業界標準として存在すると確認でき、同一訪問先で複数台を
  同時に分解洗浄する依頼は一般的なパターンと判断した。これを受け、course-set-pashaのフェーズ11
  改訂(history_row→history_rows配列化)と同じ設計判断で、出力3を単一オブジェクトから配列に
  変更した。schema/output.schema.json・schema/validate_test_cases.py(複数台ケース
  G4_multiple_units_same_visit新規追加、items対応のバリデータ拡張)・llm-system-prompt-draft.md・
  output-samples-validation.mdに反映し、schema/validate_test_cases.pyを実行して9件全件パスを
  確認した。一方で、prototype/cloud_function_webhook.py・prototype/post_generation_checks.py
  (および対応するtest_*.py)は旧仕様の単一オブジェクト`history_row`のままで未更新のため、
  現時点ではスキーマ・設計ドキュメントとprototypeコードの間に不整合が生じている。次回は
  この2ファイル(+テスト)を`history_rows`配列対応に更新することを最優先とする。
- フェーズ96(2026-08-21 17:00 UTC): フェーズ95の申し送り通り、prototype/cloud_function_webhook.py・
  prototype/post_generation_checks.py(+対応するtest_*.py)を`history_rows`配列対応に更新した。
  cloud_function_webhook.pyはformat_history_row_text()を1台分の整形に据え置きつつ、新設の
  format_history_rows_text()で複数台の場合に「[1台目]」「[2台目]」の見出しを付けて連結する形とした
  (1件のみの場合は従来通り見出し無し、既存の返信文言との後方互換を維持)。post_generation_checks.py
  側はcheck_model_type_mentioned_in_text()・check_additional_treatment_mentioned_in_text()・
  check_next_recommended_date_history_care_guide_consistency()の3チェックをhistory_rows配列を
  要素ごとにループする形に変更した(course-set-pashaのエリア別チェックと同じ設計)。
  この過程で、schema/validate_test_cases.pyのG4_multiple_units_same_visitフィクスチャに
  実データ不整合(history_rows[*].model_type_and_capacityが「壁掛け型2.8kW(リビング)」のような
  表記だったのに対し、completion_report.bodyは「リビングの壁掛け型2.8kW」という語順で記述して
  おり、両者が文字列として一致しない)を発見した。これはcheck_model_type_mentioned_in_text()が
  history_row単数版のままだったフェーズ95時点では検出できなかった潜在バグで、今回の配列化に
  伴い初めて機械チェックの対象になったことで顕在化した。schema/output.schema.jsonのdescription
  記載例(「リビング2.8kW・寝室2.2kW」の語順)に合わせ、history_rows側の値を「リビングの
  壁掛け型2.8kW」「寝室の壁掛け型2.2kW」に修正して解消した(body側は変更不要)。
  prototype配下のtest_cloud_function_webhook.py・test_post_generation_checks.pyにG4フィクスチャ・
  複数台ケースを使った新規テストを追加し、schema/validate_test_cases.py実行(9件パス)・
  prototype配下の全テスト実行(67件パス)をいずれも確認した。次回は候補12(東京住まいる、
  tokyo-smile.jp限定)の連絡先確認、またはオーナーからの初回コンタクト承認可否を待つ間の
  他の未着手領域(実LLM接続後の生成品質検証設計等)の前進を優先する。
- フェーズ97(2026-08-21 19:00 UTC): フェーズ96の申し送り通り、候補12(東京住まいる/
  tokyo-smile.jp)の連絡チャネルをtokyo-smile.jpドメイン限定で再調査し(candidate-longlist-draft.md
  第五十八弾)、トップページ内蔵の申込フォーム(送信後スタッフ折り返し方式)を確認、
  initial-contact-message-draft.mdの候補12欄に反映した。これで独立系候補(候補1・3・7・10・12)
  全件で何らかの連絡チャネルが判明した状態に達した。あわせて、候補1(rhinohands)・候補7
  (「クリーンラボ」)・候補8(「猫の手」)に続き候補12でも発生した「屋号・ドメイン類似による
  AI要約の誤結合」(tokyo-smile.co.jpという無関係な別会社情報が混入)を、通算4件目の再発事例として
  interview-candidate-selection-criteria.mdに探索手順(ドメイン一致確認の徹底、未確認情報は
  確定させない)として明文化した。
- フェーズ98(2026-08-21 20:00 UTC): フェーズ96・97の申し送り通り、承認待ちの間に前進できる
  未着手領域として「実LLM接続後の生成品質検証設計」に着手し、llm-quality-verification-plan.mdを
  新規作成した。output-samples-validation.mdの9ケース(G1〜G4・OOS1・II1・CI1〜CI3)について、
  厳守事項1〜8ごとに検証観点・機械チェック可否・人手判定要否を整理し、人手判定項目は同一入力で
  3回生成し1回でも抵触があれば不合格とする基準を仮設定した。本ドキュメントの作成自体はAPIキー
  取得・課金を伴わない机上作業であり、実際のLLM API呼び出しは引き続きオーナー承認待ちのまま
  未実施。
- フェーズ99(2026-08-22 07:00 UTC): llm-quality-verification-plan.mdの検証手順1が
  「llm_callスタブ相当の関数に注入する」という抽象的な記述だったため、実際に
  prototype/cloud_function_webhook.pyを確認し、既存の`LlmCallClient`Protocol
  (`generate(memo_text, retry_context)`)への差し替えのみで着手可能であることを具体的に
  確認・記述した(呼び出し元の`_generate_with_api_retry()`等の変更は不要)。承認が下り次第
  迷わず着手できる状態を維持する目的の小規模な整備。次回は候補研究の残課題(独立系全件の
  連絡チャネル判明を受け、フランチャイズ加盟候補2・13・14側の連絡チャネル確認の要否整理)、
  またはオーナーの初回コンタクト承認可否を待つ間の他領域の前進を検討する。
- フェーズ100(2026-08-22 08:00 UTC): sns-blog-example-observation.mdの「未検証事項」1点目
  だった、個人事業主・独立系業者に特化したSNS投稿実例の再調査にWebSearchで着手した。
  候補2・13・14の連絡チャネル確認は初回コンタクト文面草案時点(initial-contact-message-
  draft.md)で既に確定済み(2026-08-17)と判明したため優先度を見送った。個別事業者ブログ
  本文への直接アクセスは実行環境のegressプロキシによりブロックされる制約
  (`EGRESS_BLOCKED`)を確認した一方、Instagramの検索結果からは「#エアコンクリーニング」
  「#ビフォーアフター」を付けた独立系・小規模事業者と見られるアカウントが絵文字(🫧・📸等)を
  積極的に使う傾向を確認した。本サービスのですます調・絵文字不使用という出力方針(厳守事項8)
  を変更する根拠にはならないと判断したが、実在業者の「素の」発信スタイルとの差異は今後の
  ヒアリング確認項目候補として記録した。詳細はsns-blog-example-observation.md「追記
  (2026-08-22 08:00 UTC・フェーズ100)」参照。次回はcustomer-interview-design.md相当の
  ヒアリング設計への同項目の反映、またはオーナーの初回コンタクト承認可否を待つ間の
  他領域の前進を検討する。
- (注記: フェーズ101〜114は個別ドキュメント側(follow-unfollow-event-handling-design.md・
  user-account-linking-design.md・data-retention-policy.md等)とgit commitログには記録されて
  いるが、本READMEのフェーズログへの追記がフェーズ100で止まっていた。詳細はgit log
  (b64f15f・b5f9ef9・a7fd472・13488f6等のcommitメッセージ)参照。フェーズ115から本READMEへの
  記録を再開する。)
- フェーズ115(2026-08-23 20:00 UTC): follow-unfollow-event-handling-design.md「残課題」・
  フェーズ114で実装した`dispatch_webhook_events()`の先に残っていた「実HTTPリクエスト
  (署名ヘッダ付きJSONボディ)を受け取り、署名検証を通してからdispatch_webhook_events()へ
  渡す入口」を、webhook-http-entry-point-design.mdとして新規設計した。本ventureには
  course-set-pasha・line-reservation-aiには既にあった`verify_line_signature()`
  (HMAC-SHA256 + Base64、標準ライブラリのみ)自体が未実装だったため、設計・実装ともに
  新設した。あわせて`WebhookReceiverResult`・`receive_webhook()`
  (署名検証→JSONパース→`events`キー確認→`dispatch_webhook_events()`委譲、の4段階、
  course-set-pashaのreceive_webhook()と同じ設計)をprototype/cloud_function_webhook.pyに
  実装し、test_cloud_function_webhook.pyに`VerifyLineSignatureTest`・`ReceiveWebhookTest`
  (計7件)を追加、prototype配下の全テスト実行で116件全件パスを確認した。次回は実際の
  Cloud Functions(`functions_framework`)のリクエストオブジェクトから`body`・署名ヘッダを
  取り出して`receive_webhook()`に渡す`main(request)`薄い配線(course-set-pashaフェーズ83
  相当)を優先する。
- フェーズ116(2026-08-23 21:00 UTC): フェーズ115の申し送り・webhook-http-entry-point-design.md
  「残課題」だった`main(request)`薄い配線に着手した。course-set-pashaのcloud_function_webhook.py
  (`get_runtime_dependencies()`・`main()`)と同じ設計で、`get_runtime_dependencies()`
  (実クレデンシャル未接続のため現時点は空辞書を返すファクトリ)・`main(request)`
  (`functions_framework`のRequestインターフェース`get_data()`・`headers.get(...)`のみに依存し、
  環境変数`LINE_CHANNEL_SECRET`からchannel_secretを取得、`receive_webhook()`へ委譲)を
  prototype/cloud_function_webhook.pyに実装した。テストはcourse-set-pashaの
  `_StubFlaskRequest`・`MainEntryPointTest`をそのまま踏襲し5件追加、prototype配下の全テスト
  実行で121件全件パス・schema/validate_test_cases.py実行(9件パス)をいずれも確認した。これで
  webhook-http-entry-point-design.mdの残課題のうち、実デプロイ・アカウント作成に該当しない
  範囲(署名検証〜HTTPエントリポイントまでの処理ロジック自体)は完了した。次回は本venture未着手の
  llm-quality-verification-plan.md相当(実LLM接続後の生成品質検証設計、course-set-pasha・
  line-reservation-aiには既存)の新規作成、または候補研究の残課題の前進を優先する。
- フェーズ117(2026-08-24 00:00 UTC): フェーズ116の申し送りを確認したところ、
  llm-quality-verification-plan.mdは既にフェーズ98(2026-08-21 20:00 UTC)で新規作成済み
  であり、申し送り自体が古い状態を参照した誤りだったと判明した。改めて各ドキュメントの
  「残課題」を棚卸しした結果、subscription-cancellation-flow-design.md「本venture固有の
  論点: 季節性に伴うダウングレードの偏り」に残っていた「想定顧客ヒアリングで『季節に応じた
  プラン変更のしやすさ』自体へのニーズを確認する必要がある(customer-interview-design.md
  作成時の追加論点候補)」に対応した。customer-interview-design.mdの質問Bセクションに
  質問7a(繁忙期対応プランと通常プランを季節に応じて切り替える運用の手続き・請求の分かり
  やすさ、および「解約せず一時的に生成を止める」選択肢へのニーズを問う質問)を新設し、
  全14問から全15問に更新、所要時間見積もり・未検証の仮説節の記述もあわせて更新した。
  subscription-cancellation-flow-design.md側にも解消済みの旨を追記した。実在の業者への
  ヒアリング実施自体は引き続きオーナー承認待ち(customer-interview-design.md「実施に
  あたっての留意点」参照)。次回はinterview-candidate-selection-criteria.md相当の
  選定基準を踏まえた候補研究の残課題、またはllm-quality-verification-plan.mdに残る
  実LLM接続後の検証(承認待ちのため机上準備のみ可能な範囲)の前進を優先する。
- フェーズ118(2026-08-24 03:00 UTC): candidate-readiness-summary.mdが「次回以降の候補研究は
  優先度が低く、llm-quality-verification-plan.mdの精緻化等を優先する方が生産的」と提案していた
  点、およびフェーズ117の申し送りを踏まえ、llm-quality-verification-plan.md「残る未確定事項」
  3点目(検証結果の記録先を検証着手段階で判断する)への準備として、
  llm-quality-verification-results-template.mdを新規作成した。output-samples-validation.mdの
  9ケース(G1〜G4・OOS1・II1・CI1〜CI3)×各3試行分の記録表(検証観点表#1〜#8に対応する列、
  機械/人手の別を明記)、トークン数・コスト実測記録欄、総合結果サマリ欄を先に用意し、実LLM接続の
  承認が下りた際にその場で記入するだけで着手できる状態にした。本ドキュメント自体は空欄の
  テンプレートでありAPIキー取得・課金を伴わないため承認不要。次回はテンプレートの空欄を実際に
  埋める作業(オーナー承認待ち)以外の残課題として、character-limit-fallback-design.mdの
  ソフト閾値検討(これも実LLM接続待ちで着手不可と記録されている)以外に着手可能な領域が
  無いか棚卸しし、無ければ候補研究の残課題(スタッフ数5名以下の直接確認等)に優先度を戻すことを
  検討する。
- フェーズ119(2026-08-24 06:00 UTC): フェーズ118の申し送りを踏まえ棚卸しした結果、
  unit-economics-estimate.md「残課題(新規)」1点目(季節性を踏まえた月別シミュレーションが
  未着手)が残っていたことに対応した。market-research.mdの季節性言及(繁忙期は施工件数が
  閑散期の2〜3倍)を踏まえ、繁忙期(6〜9月の4ヶ月・倍率2.5倍)/閑散期(8ヶ月)で利用回数が
  変動する前提の年間シミュレーションを追加した。3プランいずれも季節変動を織り込んだ年間
  平均粗利率(86.3〜88.5%)が、既存の「毎月ちょうど使い切る」単純化試算の粗利率
  (84.8〜87.1%)を上回るという結果になり、閑散期の原価減少効果が繁忙期の超過課金コストを
  上回るためと分析した。実LLM・実決済接続やヒアリング実施を要さない机上試算のため承認不要。
  次回はcharacter-limit-fallback-design.mdのソフト閾値検討(実LLM接続待ちで着手不可のまま)
  以外に着手可能な残課題の棚卸しを継続するか、候補研究の残課題(スタッフ数5名以下の直接
  確認等)に優先度を戻すことを検討する。
- フェーズ120(2026-08-24 08:00 UTC): subscription-billing-cost-estimate.md「残課題(新規)」
  2点目、決済手数料3.6%が「一次情報未確認の仮定値」だった点にWebSearchで対応した。Stripe
  Japanの公開情報を確認し、国内カード決済の基本料率3.6%自体は裏付けが取れた一方、本venture
  が想定するStripe Billing(月額サブスクの継続課金)利用時は0.5%が上乗せされ合計4.1%程度に
  なる可能性、JCBブランドでは消費税加算で実質約3.96%になる可能性の2点を新たに確認した。
  「決済手数料3.6%の一次情報確認(2026-08-24追記)」節を新設し、4.1%採用時の固定月額分・
  超過課金分の手数料額を再計算した参考値を記載。いずれもcourse-set-pashaの結論(決済手数料が
  粗利率を左右する優先コスト項目)を変えるほどの差ではないと確認した。正式な料率確定は
  実際の契約時(オーナー承認待ち)の一次情報再確認に委ねる。実LLM・実決済接続を伴わない
  WebSearchでの公開情報確認のみのため承認不要。次回はキャッシュ有効期限1時間TTL側の
  一次情報確認(llm-api-cost-estimate.md記載の残課題)、またはcharacter-limit-fallback-design.md
  以外の棚卸し残課題への着手を検討する。
- フェーズ121(2026-08-24 14:00 UTC): フェーズ120の申し送り通り、キャッシュ有効期限1時間TTLの
  料金条件をWebSearchで確認した(Claude Platform Docs「Prompt caching」等の一次情報系ソースが
  一致)。デフォルト5分TTLの書き込み単価(通常入力の約1.25倍)は既存の前提通りである一方、
  `cache_control`に`"ttl": "1h"`を明示指定する1時間TTLは書き込み単価が通常入力の約2倍になる
  (読み取り単価0.1倍は共通)ことを新たに確認した。1時間TTLは呼び出し間隔が10分を超えて
  空く場合に有効で、概ね3回目以降の生成で書き込みコスト増分を回収できる計算になる。本venture
  は業者ごとの生成間隔にばらつきがあるため、5分TTL固定・1時間TTL固定・間隔に応じた動的切替の
  いずれを採用するかは実LLM接続後の利用間隔実測データを見て判断する方針とし、
  llm-api-cost-estimate.mdに「1時間TTLの一次情報確認(2026-08-24追記)」節として反映した
  (結論・次のステップ候補にも反映)。WebSearchでの公開情報確認のみのため承認不要。これで
  フェーズ118で棚卸しした「character-limit-fallback-design.md以外に着手可能な残課題」は
  一通り解消したため、次回は候補研究の残課題(候補13・14のスタッフ数5名以下の直接確認等、
  WebFetchのegress制約により持ち越し中)に優先度を戻すか、他venture・アイデア領域の前進を
  検討する。
- フェーズ122(2026-08-24 17:00 UTC): フェーズ121の申し送り通り候補研究の残課題(候補13・14の
  スタッフ数5名以下の直接確認)にもう一度取り組み、candidate-longlist-draft.mdの第五十九弾
  としてWebSearchを再試行したが、第四十四弾以降と同じ頭打ちパターンが再現され新規情報は
  得られなかった。8候補全件で屋号・所在地・連絡チャネルの一次情報確認は既に完了しており、
  候補選定プロセスの材料としては揃っている一方、スタッフ数のみWebSearchでの継続調査では
  これ以上の進展が見込めないと判断し、本弾をもってスタッフ数確認のための毎時WebSearch
  再試行を打ち切ることにした(以後は初回コンタクト承認後のヒアリング過程で自然に確認する
  運用に切替え)。candidate-longlist-draft.md・candidate-readiness-summary.mdに打ち切りの
  経緯と方針転換を追記した。WebSearchでの公開情報確認のみで承認不要。次回は候補研究以外の
  他venture・アイデア領域の前進(course-set-pasha・line-reservation-aiの残課題、または
  新規アイデアの検討)を優先する。
- フェーズ123(2026-08-24 22:00 UTC): フェーズ122の申し送り通り候補研究以外の領域に前進先を
  切替え、data-retention-policy.md「今後の課題」に残っていた削除候補化トリガー
  (Stripe解約Webhook受信時の`deletion_candidate_at`マーク付け、course-set-pashaの
  stripe-cancellation-deletion-candidate-trigger-design.md相当)を新規設計した
  (stripe-cancellation-deletion-candidate-trigger-design.md新規作成)。
  `user_profile/{user_id}`への`deletion_candidate_at`フィールド追加、
  `customer.subscription.deleted`受信時に365日後を削除候補時刻として記録する
  `mark_deletion_candidate_on_subscription_deleted()`、再契約時に取り消す
  `clear_deletion_candidate_on_subscription_reactivated()`、月次バッチから呼ぶ想定の
  `list_deletion_candidates()`の3関数を設計した。本venture固有の留意点として、
  Checkout Session作成時に`client_reference_id`へ既知の`user_id`を設定できる
  (user-account-linking-design.md 4節)ため`checkout.session.completed`の処理は
  course-set-pashaより単純化されている一方、`customer.subscription.*`系イベントは
  引き続き`stripe_customer_id → user_id`の逆引きが必要である点を整理した。
  data-retention-policy.md「今後の課題」にも解消済みの旨を追記した。実Stripe Webhook
  受信口の設計・`prototype/`への実装はいずれも未着手のまま次回以降の課題として残る。
- フェーズ141(2026-08-28 12:00 UTC): payment-failure-dunning-design.md「残課題」に
  残っていた「`_is_generation_paused`の判定条件拡張(制限モード状態を含める)」に対応した。
  course-set-pashaフェーズ140の`_is_payment_suspended()`と同じ考え方で、既存関数を拡張
  するのではなく別関数`_is_payment_suspended(profile)`として新設し(判定条件が
  `upgraded_at`の有無で排他的なため責務を分離)、`process_memo_event()`に
  `PAYMENT_SUSPENDED_MESSAGE`を返す分岐(`MemoProcessResult.payment_suspended`)として
  配線した。本ventureはcourse-set-pasha(検知時刻+猶予日数から都度算出)と異なり、
  フェーズ140で追加済みの`payment_suspended_at`フィールドの設定有無で判定する設計を
  踏襲したため、猶予期間経過を検知するスケジューラが未実装の現時点ではこの分岐はまだ
  実際には発火しない(判定ロジック・応答文言・テストのみ先行整備、スケジューラ実装時に
  書き込み配線を追加するだけで機能する)。CTAボタンはpostback方式のquick_replyとし、
  `UPDATE_PAYMENT_METHOD_POSTBACK_DATA`を仮に用意したが、遷移先のStripe Customer Portal
  実装・`process_postback_event()`への配線は未着手のまま次回以降の課題として残す。
  テスト4件追加、venture全体239件全件パス・schema検証9件パスを確認した。承認不要な
  設計・実装・テスト追加のみで、外部サービスへの公開・アカウント作成・支払い等は
  発生していないためpending-approval.mdへの追記なし。
- フェーズ142(2026-08-28 15:00 UTC): payment-failure-dunning-design.md「残課題」に
  残っていたStripe Customer Portal(支払い方法更新用URL発行)の要否・実装方式の検討に
  対応した。コード調査の結果、本ventureには既に`render_subscription_procedure_notice()`
  (解約・プラン変更案内向け、フェーズ131以前から存在)が使う`PortalLinkProvider`
  Protocol(`get_portal_url(user_id) -> Optional[str]`でStripe Billing Portalの
  一時URLを取得する差し替え可能な口)があり、新規クライアント種別を追加せずそのまま
  再利用できると判明した。`process_postback_event()`に`portal_link_provider`引数を
  追加し、`UPDATE_PAYMENT_METHOD_POSTBACK_DATA`受信時はこれまでの
  `build_checkout_session_params()`/`checkout_session_client.create()`経路とは別に
  `portal_link_provider.get_portal_url(user_id)`を呼んでURLを案内する分岐
  (`format_payment_portal_reply_message()`新設)を実装した。未接続・取得失敗時は
  `render_subscription_procedure_notice()`と同じ`PORTAL_LINK_UNAVAILABLE_FALLBACK`へ
  差し替える(ボタンタップに無反応で応じることを避けるため)。`dispatch_webhook_events()`
  にも`portal_link_provider`を配線した。テスト5件追加(process_postback_event向け4件・
  dispatch_webhook_events向け1件)、venture全体244件全件パス・schema検証9件パスを
  確認した。承認不要な設計・実装・テスト追加のみで、外部サービスへの公開・アカウント
  作成・支払い等は発生していないためpending-approval.mdへの追記なし。次回は
  猶予期間終了直前リマインドを送信するスケジューラ(trial-end-scheduler-design.mdの
  日次バッチと同種の仕組みを流用できる見込み、payment-failure-dunning-design.md
  「残課題」参照)への着手を検討する。
- フェーズ143(2026-08-28 16:00 UTC): payment-failure-dunning-design.md「残課題」に
  残っていた猶予期間終了直前リマインドを送信するスケジューラを設計・実装した
  (payment-failure-reminder-scheduler-design.md新規作成)。trial-end-scheduler-design.md
  (フェーズ133)と同じ全体構成(Cloud Scheduler日次バッチ→対象抽出→Flex Message送信→
  フラグ書き込み)を踏襲し、猶予期間7日のうち3日前(検知から4日経過時点)に1回のみ
  リマインドを送る設計とした。既存の`payment_failure_detected_at`・`payment_suspended_at`
  だけでは「リマインド送信済みか」を区別できなかったため、`trial_end_notified_at`と
  同じ役割の`payment_failure_reminder_sent_at`フィールドを新設し(user_id_linking.py)、
  `prototype/payment_failure_reminder_scheduler.py`に`select_due_payment_failure_
  reminders()`・`build_payment_failure_reminder_flex_message()`(ボタンは既存の
  `UPDATE_PAYMENT_METHOD_BUTTON_LABEL`/`UPDATE_PAYMENT_METHOD_POSTBACK_DATA`を再利用、
  新規クライアント種別は不要)・`send_payment_failure_reminders()`を実装した。あわせて
  `payment_failure.py`の`clear_payment_failure_on_success()`が新フィールドもクリアする
  よう拡張し(決済成功後に再度失敗した際もリマインドが送れるようにするための対応)、
  テスト19件追加、venture全体263件全件パス・schema検証9件パスを確認した。承認不要な
  設計・実装・テスト追加のみで、外部サービスへの公開・アカウント作成・支払い等は
  発生していないためpending-approval.mdへの追記なし。次回は猶予期間(7日)経過後に
  制限モードへ自動移行させるスケジューラ本体(`payment_suspended_at`への書き込み配線、
  payment-failure-reminder-scheduler-design.md「今後の課題」参照)への着手を検討する。
- フェーズ145(2026-08-28 18:00 UTC): payment-failure-reminder-scheduler-design.md
  「今後の課題」に残っていた、猶予期間(7日)経過後に制限モードへ自動移行させる
  スケジューラ本体を実装した。trial_end_scheduler.py・payment_failure_reminder_
  scheduler.pyと同じ全体構成(対象抽出→Flex Message送信→フラグ書き込み)を踏襲し、
  新規モジュール`prototype/payment_suspension_scheduler.py`に
  `select_due_payment_suspensions()`(`payment_failure_detected_at`から7日以上経過かつ
  `payment_suspended_at`未設定のユーザーを抽出、「以上」の範囲条件で日次実行の遅延・
  欠落に耐える設計は他スケジューラと同一)・`build_payment_suspension_flex_message()`・
  `send_payment_suspensions()`を実装した。Push通知の本文はcloud_function_webhook.pyの
  `PAYMENT_SUSPENDED_MESSAGE`(リプライ時に返す文言)をそのまま再利用し、プロアクティブな
  制限モード移行通知とその後のリプライ案内とで文言が食い違わないようにした。書き込みは
  Push送信成功後にのみ行う設計(失敗時は次回バッチで再試行、他スケジューラと同じ
  「書き込み一発+自然な再試行」方式)とした。テスト12件追加、venture全体275件全件パス・
  schema検証9件パスを確認した。承認不要な設計・実装・テスト追加のみで、外部サービスへの
  公開・アカウント作成・支払い等は発生していないためpending-approval.mdへの追記なし。
  これでpayment-failure-dunning-design.md「残課題」に残っていたコード実装系のタスクは
  一通り実装済みとなった(残るのは実Cloud Scheduler・LINE Push Message API接続等、
  オーナー承認待ちのインフラ構築のみ)。次回は他venture(line-reservation-ai・
  course-set-pasha)の状況も踏まえ、本ventureで未着手の領域への着手を検討する。
- フェーズ146(2026-08-28 21:00 UTC): payment-failure-dunning-design.md 4節末尾に先行して
  書き残していた「猶予期間中に決済が成功した場合の復旧通知の3分岐(制限モードからの復旧/
  猶予期間中の完了通知/状態リセットのみ)」を、line-reservation-aiのフェーズ続き115
  (`classify_payment_succeeded()`)と同じ考え方で移植し、新規`prototype/payment_
  recovery_notification.py`に`classify_payment_recovery()`・`handle_payment_succeeded()`
  として実装した。本ventureはline-reservation-aiと異なり決済失敗検知時(段階1)の通知を
  実際に送信する配線がまだ存在しないため、「猶予期間中に一度でも通知済みか」の判定は
  本venture唯一の送信済みフラグである`payment_failure_reminder_sent_at`のみで行う設計
  とした(制限モードからの復旧は既存文言をそのまま使用、猶予期間中の完了通知は新設した
  `PAYMENT_CONFIRMED_IN_GRACE_MESSAGE`(「再開」ではなく「解消」と表現)を使用)。状態の
  クリアは既存の`clear_payment_failure_on_success()`をそのまま再利用した。テスト13件
  追加、venture全体288件全件パス・schema検証9件パスを確認した。承認不要な設計・実装・
  テスト追加のみで、外部サービスへの公開・アカウント作成・支払い等は発生していないため
  pending-approval.mdへの追記なし。実際のStripe Webhook受信エンドポイントからの呼び出し
  配線、および決済失敗検知時(段階1)通知の実送信配線自体は次回以降の課題として残る
  (payment-failure-dunning-design.md該当箇所に追記済み)。
- フェーズ147(2026-08-29 02:00 UTC): payment-failure-dunning-design.md「残課題」に
  残っていた「決済失敗検知時(段階1)通知の実送信配線」に対応した。
  `prototype/payment_failure.py`に`handle_payment_failure_detected()`を新設し、design
  4節「決済失敗検知時(猶予期間開始)」の文言を`build_payment_failure_detected_flex_
  message()`でFlex Message化(既存の`UPDATE_PAYMENT_METHOD_BUTTON_LABEL`/`_POSTBACK_DATA`
  ボタンを再利用、payment_failure_reminder_scheduler.pyと同じ構成)し、送信成功時のみ
  `mark_payment_failure_detected()`で状態を書き込む設計とした(フェーズ146の
  `handle_payment_succeeded()`と対称に、送信失敗時は状態を一切変更せずWebhookリトライに
  委ねる)。`stripe_dispatch.py`の`dispatch_stripe_event()`に`push_client`引数
  (省略時はこれまで通り`mark_payment_failure_detected()`を直接呼び通知は送信しない、
  後方互換)を追加し、`invoice.payment_failed`受信時に配線した
  (`payment_failure_notification_failed_user_ids`を結果へ新設し、送信失敗を区別できる
  ようにした)。テスト6件追加(test_payment_failure.py 4件・test_stripe_dispatch.py 2件)、
  venture全体294件全件パス・schema検証9件パスを確認した。承認不要な設計・実装・テスト
  追加のみで、外部サービスへの公開・アカウント作成・支払い等は今回発生していないため
  pending-approval.mdへの追記なし。なお`invoice.payment_succeeded`側の復旧通知
  (`handle_payment_succeeded()`、フェーズ146で実装済みだが`dispatch_stripe_event()`への
  配線は未着手のまま)は、モジュールごとに`LinePushDeliveryError`を別クラスとして定義
  している既存の慣習上、本フェーズの`push_client`とは別の配線検討(例外クラスの共通化、
  または`invoice.payment_succeeded`専用の別引数を設けるか)が必要と判断し、次回以降の
  課題として残した。次回はこの`invoice.payment_succeeded`側の復旧通知配線への着手、
  または他venture・アイデア領域の前進を優先候補とする。
- フェーズ148(2026-08-29 04:00 UTC): フェーズ147の申し送り通り、`invoice.payment_
  succeeded`側の復旧通知配線に着手した。フェーズ147時点で挙がっていた2案(例外クラスの
  共通化/専用の別引数を設ける)のうち、他の各スケジューラ(trial_end_scheduler・
  payment_failure_reminder_scheduler・payment_suspension_scheduler等)がいずれも自分
  専用の`push_client`・`LinePushDeliveryError`を持つ既存パターンとの一貫性を優先し、
  後者(別引数)を採用した。`stripe_dispatch.py`の`dispatch_stripe_event()`に
  `recovery_push_client`引数(省略時はこれまで通り`clear_payment_failure_on_success()`を
  直接呼び通知は送信しない、後方互換)を追加し、`invoice.payment_succeeded`受信時に
  `payment_store`の現在状態を`PaymentFailureReminderUserState`へ詰め替えて
  `handle_payment_succeeded()`(payment_recovery_notification.py、フェーズ146)を呼ぶ
  よう配線した(`payment_recovery_notification_failed_user_ids`を結果へ新設し、送信失敗を
  区別できるようにした。送信失敗時は状態を変更せずWebhookリトライに委ねる設計はフェーズ147の
  `handle_payment_failure_detected()`と対称)。テスト4件追加(制限モードからの復旧通知/
  猶予期間中の無通知リセット/通常課金での無処理/送信失敗時の状態未変更、いずれも
  test_stripe_dispatch.py)、venture全体298件全件パス・schema検証9件パスを確認した。
  承認不要な設計・実装・テスト追加のみで、外部サービスへの公開・アカウント作成・支払い等は
  今回発生していないためpending-approval.mdへの追記なし。これでpayment-failure-dunning-
  design.md 4・6節に残っていた2つの通知実送信配線(段階1検知・決済成功復旧)はいずれも
  `dispatch_stripe_event()`から呼び出し可能な状態になった。実際のStripe Webhook HTTP
  エントリポイント自体・実LINE Push API接続・実Stripeアカウント接続はいずれも引き続き
  オーナー承認待ちのまま残る(pending-approval.md参照)。次回は他venture・アイデア領域の
  前進、または猶予期間(7日)終了後に制限モードへ自動移行させるスケジューラ配線(design 6節
  「残課題」)を検討する。
- フェーズ149(2026-08-29 07:00 UTC): 各設計docの「残課題」を棚卸しした結果、
  stripe-webhook-http-entry-point-design.mdに残る`resolve_user_id`実装(既に
  フェーズ140以降で対応済みだが本節の更新が漏れていた)以外に、コード側の実際の配線漏れを
  発見した。`stripe_dispatch.py`の`dispatch_stripe_event()`は`payment_store`・
  `push_client`・`recovery_push_client`の3引数(フェーズ140・147・148で追加)により
  `invoice.payment_failed`/`invoice.payment_succeeded`(決済失敗検知・復旧通知)を
  処理できる設計になっていたが、`prototype/stripe_webhook.py`の`receive_stripe_webhook()`
  (実HTTPエントリポイントに最も近い層)はこの3引数を一切受け取らず、常に`None`のまま
  `dispatch_stripe_event()`へ委譲していたため、HTTPエントリポイント経由の実際の経路では
  両イベントが`ignored_types`に落ちてしまう配線漏れがあった(`dispatch_stripe_event()`
  単体のテストは既存だったが、`receive_stripe_webhook()`を通した一気通貫のテストが
  無かったため気付かれていなかった)。`receive_stripe_webhook()`に同名の3引数
  (`payment_store`/`push_client`/`recovery_push_client`、いずれも省略時`None`で
  従来通りの後方互換)を追加し、`dispatch_stripe_event()`へそのまま委譲する薄い配線を
  追加して解消した。テスト7件追加(`payment_store`省略時のignored_types確認・
  `payment_store`指定時の状態書き込み・`push_client`指定時の通知送信と送信失敗時の
  状態未変更・`recovery_push_client`指定時の復旧通知送信と送信失敗時の状態未変更、
  いずれも`prototype/test_stripe_webhook.py`
  `ReceiveStripeWebhookPaymentFailureWiringTest`)、venture全体305件全件パス・
  schema検証9件パスを確認した。あわせてstripe-webhook-http-entry-point-design.md
  「残課題」に本フェーズの対応内容と、フェーズ140以降で既に解消済みだった
  `resolve_user_id`項目の更新漏れをまとめて反映した。承認不要な設計・実装・テスト
  追加のみで、外部サービスへの公開・アカウント作成・支払い等は今回発生していないため
  pending-approval.mdへの追記なし。なお`main(request)`相当(実Cloud Functionsの
  `functions_framework`リクエストからのbody・`Stripe-Signature`ヘッダ取り出し配線)は
  Stripe側にはまだ存在せず(LINE側`cloud_function_webhook.main()`のみ実装済み)、
  次回以降の課題として残る。
- フェーズ150(2026-08-29 09:00 UTC): フェーズ149末尾で次回課題として残った、Stripe版
  `main(request)`(実Cloud Functionsの`functions_framework`リクエストからの`body`・
  `Stripe-Signature`ヘッダ取り出し配線)をstripe-webhook-http-entry-point-design.md
  「残課題」2点目に沿って実装した。course-set-pashaの`prototype/stripe_webhook.py`の
  `main(request)`・`get_stripe_runtime_dependencies()`を土台としつつ、本venture固有の
  差異(専用の`PaymentFailureStoreProtocol`スタブを持たず`UserProfileStoreProtocol`が
  duck typingで満たす設計)を反映し、`get_stripe_runtime_dependencies()`は
  `InMemoryUserProfileStore()`を1つ生成して`user_profile_store`・`payment_store`の
  両方として渡す形にした。`push_client`・`recovery_push_client`は実LINE Push API接続
  (チャネルアクセストークン)がオーナー承認待ちのため意図的に渡さず、状態の読み書きは
  できるが実通知送信はまだ行われない状態にとどめた(payment-failure-dunning-design.md
  6節と同じ区別)。環境変数名は設計どおり`STRIPE_WEBHOOK_SECRET`とした。テスト13件追加
  (`_StubFlaskRequest`を使った`main()`本体の署名検証・環境変数未設定時401・
  `get_stripe_runtime_dependencies()`の出力が`receive_stripe_webhook()`に受理される
  ことの確認、course-set-pashaと同じ紐付け解決の回帰防止テスト2件を含む、いずれも
  `prototype/test_stripe_webhook.py`)、venture全体312件全件パス・schema検証9件パスを
  確認した。承認不要な設計・実装・テスト追加のみで、外部サービスへの公開・アカウント作成・
  支払い等は今回発生していないためpending-approval.mdへの追記なし。あわせて
  stripe-webhook-http-entry-point-design.md「残課題」2点目を解消済みに更新した。
  実際のStripeアカウント接続・Webhookエンドポイント登録・`STRIPE_WEBHOOK_SECRET`の
  実際の値の取得はいずれも引き続きオーナー承認待ちのまま残る(pending-approval.md参照)。
- フェーズ151(2026-08-29 14:00 UTC): 各設計docの残課題を棚卸しした結果、既に実装済み
  (フェーズ111・112・113・132等)にもかかわらずドキュメント側の更新が漏れていた残課題を
  複数発見・整理した。follow-unfollow-event-handling-design.mdが「未実装」としていた
  `process_follow_event()`・`process_unfollow_event()`・`dispatch_webhook_events()`は
  実際には既に実装済み(prototype/cloud_function_webhook.py)、user-account-linking-design.md
  が「pending-approval.md未記録」としていた申込フォーム作成案件は実際には2026-08-23
  04:00 UTC付けで記録済み、「data-retention-policy.md相当が未作成」としていた点も
  フェーズ108で既に新規作成済みであることを確認し、いずれも解消済みとして更新した。
  その上で、真に未対応だった2点に着手した。(1)user-account-linking-design.md
  「未検証・残課題」の`LINKING_SUCCESS_MESSAGE`・`LINKING_REQUIRED_MESSAGE`
  (連携コード解決成功・連携コード送信依頼の案内文言)の確定文言化を、
  tone-and-manner-guideline.mdに新設した「連携コード関連文言の最終確定」節で行った
  (宛先・見出し要否・謝罪表現のいずれもガイドラインの既存方針と整合することを確認し、
  現行の実装文言のまま確定文言として採用)。(2)同ドキュメントが未実施としていた
  「6文字・辞書引き一致」ロジックの境界値確認(施工メモの書き出し文言との偶然一致
  可能性)について、prototype/test_user_id_linking.pyにテスト2件を追加した
  (コード生成用アルファベットが号数・電圧表記に頻出する`0`・`1`・`O`・`I`・`L`を
  含まないことの確認、および実際にコードが1件発行された状態で「壁掛型2.2」「100V電源」
  等の実際的なメモ書き出し文言や実在コードに酷似する1文字違いの文字列がいずれも
  誤判定されないことの確認)。テスト2件追加、venture全体314件全件パス・schema検証9件
  パスを確認した。承認不要なドキュメント整理・テスト追加のみで、外部サービスへの公開・
  アカウント作成・支払い等は今回発生していないためpending-approval.mdへの追記なし。
- フェーズ152(2026-08-29 17:00 UTC): フェーズ151の棚卸しの続きとして、
  stripe-webhook-http-entry-point-design.md「残課題」に取り残されていたドキュメント記載
  漏れをもう1件発見・解消した。`checkout.session.completed`の受信配線について「本設計の
  範囲外のまま残る」と記載され続けていたが、実際にはcheckout-session-completed-handling-
  design.md(フェーズ140台)で`handle_checkout_session_completed()`として既に実装・
  `receive_stripe_webhook()`へ配線済みであることを確認し、解消済みとして反映した。
  コード変更は無し、設計docの現状反映のみ。venture全体314件全件パスを確認した(変更前と
  同数、テスト自体は変更していないため差分なしを確認する目的での再実行)。承認不要な
  ドキュメント整理のみで、外部サービスへの公開・アカウント作成・支払い等は今回発生して
  いないためpending-approval.mdへの追記なし。
- フェーズ153(2026-08-29 23:00 UTC): trial-end-scheduler-design.md 5節に残っていた
  「トライアル終了後の『生成一時停止』判定の実コード実装は本venture側でまだ未着手」という
  記載が、実際にはフェーズ138で`_is_generation_paused()`として実装済みであるにも
  かかわらず更新されていなかった(同ドキュメントが作成されたフェーズ133時点ではまだ
  未実装だったための書き漏れ)ことに気づき、解消済みとして反映した。あわせて、この
  棚卸しの過程で、`send_trial_end_notifications()`(trial_end_scheduler.py)が書き込む
  `trial_end_notified_at`と`_is_generation_paused()`(cloud_function_webhook.py)が読む
  `trial_end_notified_at`が、実際に同一の`InMemoryUserProfileStore`(user_id_linking.py)を
  介して正しくつながることを確認する一気通貫テストがどちらのテストファイルにも存在
  しなかった(`test_trial_end_scheduler.py`のテストはローカル定義のスタブストア、
  `test_cloud_function_webhook.py`のテストは`trial_end_notified_at`を直接設定した
  ストアを使っており、両モジュールを実際に接続するテストが抜けていた)ことを発見し、
  `test_cloud_function_webhook.py`に`TrialEndSchedulerToGenerationPausedWiringTest`を
  新設した(スケジューラの通知送信→書き込まれた`trial_end_notified_at`により次回メモが
  一時停止応答になることの確認、および14日未満でスケジューラ対象外だったユーザーは
  一時停止しないことの確認、テスト2件)。フェーズ149で発見した`stripe_webhook.py`の
  配線漏れと同種の「単体テストはあるが結線テストが無い」観点の点検。テスト2件追加、
  venture全体316件全件パス・schema検証9件パスを確認した。承認不要なドキュメント整理・
  テスト追加のみで、外部サービスへの公開・アカウント作成・支払い等は今回発生していない
  ためpending-approval.mdへの追記なし。
- フェーズ154(2026-08-30 01:00 UTC): payment-failure-dunning-design.md 6節「残課題」に
  残っていたドキュメント記載漏れを解消した。「`invoice.payment_succeeded`側の復旧通知の
  `dispatch_stripe_event()`への配線は次回以降の課題」という記載が、実際にはフェーズ148で
  `recovery_push_client`引数として既に配線済み、フェーズ149で実HTTPエントリポイント
  (`stripe_webhook.py`の`receive_stripe_webhook()`)側の委譲漏れも解消済みであるにも
  かかわらず未対応のまま残っていた(該当記載がフェーズ147時点で書かれたための書き漏れ)。
  コード変更は無し(ドキュメント整理のみ)、venture全体316件全件パスを再確認した。
  承認不要なドキュメント整理のみで、外部サービスへの公開・アカウント作成・支払い等は
  今回発生していないためpending-approval.mdへの追記なし。
- フェーズ155(2026-08-30 04:00 UTC): 各設計docの残課題を棚卸しした結果、
  `cloud_function_webhook.py`の`_is_payment_suspended()`直前のコメントに、フェーズ145で
  `payment_suspension_scheduler.py`の`send_payment_suspensions()`として既に実装済みの
  スケジューラを「次回以降の課題として未実装」と記載したままの更新漏れを発見した
  (`user_id_linking.py`側の`UserProfile`docstringは既にフェーズ145実装済みと正しく
  記載していたが、`cloud_function_webhook.py`側のコメントのみ古いままだった)。この
  棚卸しの過程で、`test_payment_suspension_scheduler.py`の各テストがローカル定義の
  スタブストアのみを使っており、`send_payment_suspensions()`が書き込む
  `payment_suspended_at`と`_is_payment_suspended()`が読む`payment_suspended_at`が
  実際に同一の`InMemoryUserProfileStore`を介して正しくつながることを確認する一気通貫
  テストがどちらのテストファイルにも存在しなかった(フェーズ149の`stripe_webhook.py`・
  フェーズ153の`trial_end_scheduler.py`と同種の「単体テストはあるが結線テストが無い」
  観点の抜け)ことを発見し、`test_cloud_function_webhook.py`に
  `PaymentSuspensionSchedulerToPaymentSuspendedWiringTest`を新設した(スケジューラの
  送信→書き込まれた`payment_suspended_at`により次回メモが制限モード応答になることの
  確認、および猶予期間7日未経過のユーザーはスケジューラ対象外で制限モードにならない
  ことの確認、テスト2件)。あわせてコメントをフェーズ145実装済みの旨に更新し、
  payment-failure-dunning-design.md 6節「残課題」にも反映した。テスト2件追加、venture
  全体318件全件パス・schema検証9件パスを確認した。承認不要なドキュメント整理・テスト
  追加のみで、外部サービスへの公開・アカウント作成・支払い等は今回発生していないため
  pending-approval.mdへの追記なし。
- フェーズ156(2026-08-30 07:00 UTC): trial-end-scheduler-design.md 5節に記載の
  「`user_profile`ストアから対象ユーザーを抽出」部分について、実際に
  `InMemoryUserProfileStore`(`user_id_linking.py`)から`trial_end_scheduler.
  TrialUserState`を組み立てる関数が存在しない配線漏れ(course-set-pashaが
  フェーズ158で解消したのと同種の観点)を発見し、`build_trial_user_states()`を
  新設した。あわせて、`stripe_webhook.handle_checkout_session_completed()`が
  書き込む`upgraded_at`と`trial_end_scheduler.select_due_trial_end_notifications()`
  が読む`upgraded_at`が、`build_trial_user_states()`を介して実際に同一の
  `InMemoryUserProfileStore`経由でつながることを確認する結線テスト
  (`StripeWebhookUpgradedAtToTrialEndSchedulerWiringTest`、
  `test_trial_end_scheduler.py`)を追加した。テスト4件追加、venture全体322件全件
  パス・schema検証9件パスを確認した。承認不要な設計・実装・テスト追加のみで、
  外部サービスへの公開・アカウント作成・支払い等は今回発生していないため
  pending-approval.mdへの追記なし。
- フェーズ157(2026-08-30 11:00 UTC): trial-end-scheduler-design.md 2節に残っていた
  「条件(A)(生成回数10回到達)側の実装(`process_memo_event()`相当)は本venture未着手」
  という記載が、実際にはフェーズ137(trial-end-condition-a-cta-design.md)で既に実装
  済み(その後フェーズ138で「生成一時停止」判定にも統合済み)だったにもかかわらず、
  本ドキュメント(フェーズ133作成)側の更新が漏れていた記載漏れを解消した。あわせて、
  `process_memo_event()`が条件A到達時に書き込む`trial_end_notified_at`と、本モジュールの
  `select_due_trial_end_notifications()`(条件B側)が読む`trial_end_notified_at`が、
  `build_trial_user_states()`を介して実際に同一の`InMemoryUserProfileStore`経由で
  つながり、条件A到達後は条件B側の日次送信対象から自動的に除外される(二重送信しない)
  ことを確認する結線テスト(`ConditionAWriteExcludesFromTrialEndSchedulerWiringTest`、
  `test_trial_end_scheduler.py`、条件A未到達〈9回目〉では引き続き条件B側の対象に
  残ることを確認するケースも含め2件)を追加した。テスト2件追加、venture全体324件全件
  パス・schema検証9件パスを確認した。承認不要な設計・テスト追加のみで、外部サービスへの
  公開・アカウント作成・支払い等は今回発生していないためpending-approval.mdへの追記なし。
- フェーズ158(2026-08-30 14:00 UTC): checkout-initiation-flow-design.md(フェーズ131)
  3節「処理フロー(設計)」手順1・2に残っていた「`dispatch_webhook_events()`へのpostback
  振り分け配線」「`process_postback_event()`は新設予定・次回以降の課題」という記載が、
  実際にはフェーズ132で両方とも実装済み(`prototype/cloud_function_webhook.py`)だった
  にもかかわらず、同ドキュメント下部の「残課題」節は更新済みなのに本文3節側の更新が
  漏れていた記載漏れを解消した。あわせてこの棚卸しの過程で、
  `stripe_webhook.handle_checkout_session_completed()`が書き込む`stripe_customer_id`
  (`store.set_stripe_customer_id()`経由)と、`process_postback_event()`
  (`build_checkout_session_params()`経由)が読む`stripe_customer_id`が、実際に同一の
  `InMemoryUserProfileStore`を介してつながることを確認する結線テストが存在しなかった
  (既存の`test_existing_stripe_customer_id_is_forwarded_to_params`はプロフィール作成時
  に`stripe_customer_id`を直接指定するのみで、書き込み側モジュール`stripe_webhook.py`
  を経由していなかった)ことを発見し、`test_cloud_function_webhook.py`に
  `CheckoutSessionCompletedToPostbackCheckoutWiringTest`を新設した(解約後の再契約等で
  既存Stripe顧客IDが次回のCheckout Session作成パラメータに正しく引き継がれることの
  確認、および書き込み前は`customer`キー自体が付与されないことを対照確認するケースの
  計2件)。フェーズ149・153・155・156・157と同種の「単体テストはあるが結線テストが無い」
  観点の点検。テスト2件追加、venture全体326件全件パス・schema検証9件パスを確認した。
  承認不要なドキュメント整理・テスト追加のみで、外部サービスへの公開・アカウント作成・
  支払い等は今回発生していないためpending-approval.mdへの追記なし。
- フェーズ159(2026-08-30 18:00 UTC): follow-unfollow-event-handling-design.md(フェーズ109)
  「残課題」節に残っていた「本ventureには`follow`/`unfollow`のディスパッチ経路自体が
  まだ存在しない」「`process_message_event()`相当のコード判定分岐も未実装」という記載が、
  実際にはフェーズ111〜113で`process_follow_event()`・`process_unfollow_event()`・
  `process_message_event()`(連携済みユーザーは`process_memo_event()`へ委譲、未連携ユーザーは
  `resolve_linking_code()`でコード一致のみを判定根拠とする分岐)・`dispatch_webhook_events()`
  (follow/unfollow/message/postbackの4種別振り分け)がいずれも実装済み(それぞれ
  `test_cloud_function_webhook.py`の`ProcessMessageEventLinkingTest`・
  `DispatchWebhookEventsTest`でカバー済み、連携済みユーザーのmessageイベントが実際に
  `process_memo_event()`側の生成フローまで到達することを確認する結線テストも含む)だった
  にもかかわらず、本ドキュメント側の更新が漏れていた記載漏れを解消した。フェーズ150台の
  一連の「単体テストはあるが結線テストが無い」棚卸しとは異なり、本件は結線テスト自体は
  既に存在しドキュメントの記載のみが古かったケース。コード変更は無し(ドキュメント整理
  のみ)、venture全体326件全件パス・schema検証9件パスを確認した。承認不要なドキュメント
  整理のみで、外部サービスへの公開・アカウント作成・支払い等は今回発生していないため
  pending-approval.mdへの追記なし。
- フェーズ160(2026-08-30 21:00 UTC): first-generation-self-check-design.mdの
  「LINE Messaging API のメッセージ数・文字数上限確認」節に残っていた「極端に長い
  入力メモが送られた場合の文字数超過時のフォールバック処理(切り詰め・エラー応答等)は
  未設計のまま残課題とする」という記載が、実際にはフェーズ102で
  character-limit-fallback-design.mdとして設計済み、フェーズ105で
  `check_message_length_within_line_limit()`(`prototype/post_generation_checks.py`)・
  `cloud_function_webhook.py`側のフォールバック分岐として実装・テスト済み(テスト13件)
  だったにもかかわらず、本ドキュメント側の更新が漏れていた記載漏れを解消した。
  フェーズ158・159と同種の「本文中の古い記載がその後の実装で追い越されたまま残る」
  棚卸し。コード変更は無し(ドキュメント整理のみ)、venture全体326件全件パス・
  schema検証9件パスを再確認した。承認不要なドキュメント整理のみで、外部サービスへの
  公開・アカウント作成・支払い等は今回発生していないためpending-approval.mdへの
  追記なし。
- フェーズ161(2026-08-31 00:00 UTC): 直近8フェーズ(149・151・153〜160)が「既に実装済み
  だが更新漏れのドキュメント記載を解消する」棚卸しに偏っていたため、各設計docの
  「残課題」を実装コード側から再点検し、本当に未実装のまま残っている配線漏れを探した。
  user-account-linking-design.md 4節・subscription-cancellation-flow-design.md
  「当月生成回数上限の適用方法」がそれぞれ「`user_profile/{user_id}.current_plan_id`
  フィールドを`customer.subscription.*`受信のたびに更新する」と確定済み(いずれもフェーズ
  107)だったにもかかわらず、`UserProfile.current_plan_id`フィールド自体はフェーズ134で
  追加された既定値`None`のまま、実際に書き込む処理が一度も実装されていなかった(直近の
  棚卸し8件はいずれも「ドキュメント記載の更新漏れ」だったのに対し、これは「コード側の
  実装自体の抜け」という異なる種類のギャップ)。新規`prototype/subscription_plan_sync.py`
  (deletion_candidate.py・payment_failure.pyと同じ位置づけの薄いProtocol・純粋関数)を
  新設し、`resolve_plan_id_from_subscription()`(Stripeの`items.data[0].price.
  lookup_key`から`LOOKUP_KEY_TO_PLAN_ID`経由でpricing-plan.mdの3プラン名へ解決、
  未知のlookup_key・欠落時はNoneで現状維持)・`sync_current_plan_on_subscription_event()`・
  `clear_current_plan_on_subscription_deleted()`の3関数を実装した。`user_id_linking.py`の
  `UserProfileStoreProtocol`/`InMemoryUserProfileStore`に`get_current_plan_id`/
  `set_current_plan_id`を追加し(フェーズ140の`PaymentFailureStoreProtocol`と同じ考え方で、
  専用のInMemoryストアは新設せず`InMemoryUserProfileStore`が`CurrentPlanStoreProtocol`を
  構造的にduck typingで満たす形にした)、`stripe_dispatch.py`の`dispatch_stripe_event()`に
  `plan_store`引数(省略時はこれまで通り同期を行わない後方互換)を追加して
  `customer.subscription.created/updated`受信時の同期・`deleted`受信時のクリアを配線した
  (結果集約用に`plan_synced_user_ids`・`plan_cleared_user_ids`をStripeDispatchResultへ
  新設)。フェーズ149・153・155・156・157・158と同種の「HTTPエントリポイントへの委譲漏れ」
  を防ぐため、`stripe_webhook.py`の`receive_stripe_webhook()`・
  `get_stripe_runtime_dependencies()`にも同じ`plan_store`(`payment_store`と同じ
  `InMemoryUserProfileStore`インスタンスを共用)を配線した。テスト28件追加
  (test_subscription_plan_sync.py新規作成13件、test_stripe_dispatch.py 6件、
  test_stripe_webhook.py 5件、test_user_id_linking.py 4件)、venture全体354件全件パス・
  schema/validate_test_cases.py 9件全件パスを確認した。承認不要な設計・実装・テスト追加のみで、外部サービスへの公開・
  アカウント作成・支払い等は今回発生していないためpending-approval.mdへの追記なし。
  `current_plan_id`の書き込み配線は完成したが、`cloud_function_webhook.py`の
  `process_memo_event()`側が`current_plan_id`を読んで月間生成回数の上限判定・上限接近
  通知に使う`plan`引数へ実際に反映する配線(limit-approaching-notification-design.md・
  subscription-cancellation-flow-design.mdが前提とする「Stripeで受信した最新プランIDを
  上限判定に使う」の後段部分)はまだ未着手のまま次回以降の課題として残る(該当箇所に
  追記済み)。次回はこちらへの着手を優先候補とする。
- フェーズ162(2026-08-31 02:00 UTC): フェーズ161の申し送り通り、
  `process_memo_event()`側が`current_plan_id`を読んで月間生成回数の上限判定・上限接近
  通知に使う`plan`引数へ反映する配線(subscription-cancellation-flow-design.md「当月生成
  回数上限の適用方法」節の後段部分、limit-approaching-notification-design.md)を実装した。
  `prototype/cloud_function_webhook.py`に`_resolve_plan_for_limit_check(profile, plan)`を
  新設し、月間カウント処理の直前でこの関数の返り値を実際に使うプランとして
  `build_usage_notice()`へ渡すよう変更した(従来はイベント処理関数の外側から渡される
  静的な`plan`引数のみを使用し、常に`None`のままだった`current_plan_id`との接続が
  存在しなかった)。優先順位は(1)`profile.current_plan_id`が設定済みならそれを最優先
  (値自体は`profile_store.get_current_plan_id(user_id)`と同一だが、
  `process_memo_event()`冒頭で既に取得済みの`profile`をそのまま再利用し、同一ストアへの
  重複呼び出しを避けた、フェーズ138と同じ考え方)、(2)`current_plan_id`が未設定でも
  `profile.upgraded_at`が設定済み(一度は有料転換済みだがStripe Webhookの受信順序次第の
  一時的な同期漏れ)の場合は上限判定自体を省略せず新設の
  `DEFAULT_PLAN_FOR_UNSYNCED_UPGRADED_USER`(スモール、既存の3プラン中で最も低い上限・
  最も高い従量単価という安全側の初期値)を採用、(3)それ以外(トライアル中で
  `upgraded_at`未設定、または`profile_store`未接続・未連携user_id)は既存の呼び出し元
  引数`plan`をそのまま使う、という3段構成にした。(3)を残したのは、pricing-plan.mdの
  月間プラン上限がトライアル終了後にのみ適用対象であり、トライアル中の回数制限は
  既存の`TRIAL_GENERATION_LIMIT`側が別途担うため、ここでプランを補うと本来無制限のはずの
  トライアル生成に誤って月間上限を適用してしまう(既存の`plan is None`時はカウント処理
  自体をスキップするという既存呼び出し元との後方互換も兼ねる)。
  `dispatch_webhook_events()`・`receive_webhook()`は`profile_store`・`plan`のいずれも
  フェーズ113・136で既に`process_message_event()`/`process_memo_event()`まで配線済み
  だったため、Webhookエントリポイント側の追加配線は不要だった(フェーズ161の
  `stripe_webhook.py`側`plan_store`配線とは異なり、本フェーズはStripe側ではなくLINE側の
  受信経路のため対象外)。テスト4件追加
  (`ProcessMemoEventPlanFromProfileTest`3件: 同期済みプランが明示的な`plan`引数より
  優先されること・有料転換済みだが未同期の場合にデフォルトプランへ落ちること・トライアル中
  未同期の場合は月間上限を補わずカウント処理自体をスキップすること、
  `DispatchWebhookEventsPlanFromProfileWiringTest`1件: `dispatch_webhook_events()`
  経由のmessageイベント処理でも`current_plan_id`が実際に反映されることを確認する
  フェーズ158〜160と同種の結線テスト)、venture全体358件全件パス
  (`python3 -m unittest discover -s prototype -p "test_*.py"`)・
  `schema/validate_test_cases.py`9件全件パスを確認した。あわせて
  subscription-cancellation-flow-design.md「当月生成回数上限の適用方法」節の該当箇所に
  本フェーズで解消済みの旨を追記した。承認不要な設計・実装・テスト追加のみで、外部
  サービスへの公開・アカウント作成・支払い等は今回発生していないためpending-approval.md
  への追記なし。これによりフェーズ107・134・161から続いていた
  「`current_plan_id`フィールド追加→書き込み配線→読み取り配線」の一連の配線漏れは
  解消済みとなった。次回は他venture・アイデア領域の前進、または本venture内で
  未着手のまま残っている実LLM・実LINE API・実Stripe接続待ちの残課題(オーナー承認待ち)
  以外の棚卸しを優先候補とする。
- フェーズ163(2026-08-31 07:00 UTC): 各設計docの残課題を棚卸しした結果、
  payment-failure-reminder-scheduler-design.md 6節に残っていた「design 4節末尾で
  触れた『猶予期間中に決済が成功した場合の復旧通知の3分岐』の文言出し分けは引き続き
  次回以降の課題として残る」という記載が、実際にはフェーズ146(`prototype/
  payment_recovery_notification.py`の`classify_payment_recovery()`、制限モードからの
  復旧/猶予期間中の完了通知/dunning対象外/状態リセットのみの4分類)・フェーズ148
  (`stripe_dispatch.py`の`dispatch_stripe_event()`への`recovery_push_client`引数配線)で
  既に対応済みだった記載漏れ(payment-failure-dunning-design.md 6節側は同日中に追記・
  修正済みだったが、本ドキュメント側の「今後の課題」節が未更新のまま取り残されていた)を
  解消した。コード変更は無し(ドキュメント整理のみ)、venture全体358件全件パス
  (`python3 -m unittest discover -s prototype -p "test_*.py"`)・
  `schema/validate_test_cases.py`9件全件パスを再確認した。承認不要なドキュメント整理・
  アイデア追加のみで、外部サービスへの公開・アカウント作成・支払い等は今回発生していない
  ためpending-approval.mdへの追記なし。次回は他venture・アイデア領域の前進、または
  本venture内で未着手のまま残っている実LLM・実LINE API・実Stripe接続待ちの残課題
  (オーナー承認待ち)以外の棚卸しを優先候補とする。
- フェーズ164(2026-08-31 12:00 UTC): 各設計docの残課題を棚卸しした結果、
  trial-start-anchor-decision.md 5節に残っていた「(B)期間到達判定用の日次スケジューラ
  本体は...別途設計する必要があり、引き続き未着手」という記載が、実際には本ドキュメント
  作成(フェーズ134)より後のフェーズ133〜138でtrial-end-scheduler-design.mdとして
  設計され`prototype/trial_end_scheduler.py`に実装済み(`select_due_trial_end_
  notifications()`・`send_trial_end_notifications()`・
  `build_trial_end_notification_flex_message()`、フェーズ156の`build_trial_user_states()`
  結線まで完了)だった記載漏れ(フェーズ155・157・159・160・163と同種の「本文中の古い
  記載がその後の実装で追い越されたまま残る」棚卸し)を解消した。コード変更は無し
  (ドキュメント整理のみ)、venture全体358件全件パス
  (`python3 -m unittest discover -s prototype -p "test_*.py"`)・
  `schema/validate_test_cases.py`9件全件パスを再確認した。承認不要なドキュメント整理・
  アイデア追加のみで、外部サービスへの公開・アカウント作成・支払い等は今回発生していない
  ためpending-approval.mdへの追記なし。次回は他venture・アイデア領域の前進、または
  本venture内で未着手のまま残っている実LLM・実LINE API・実Stripe接続待ちの残課題
  (オーナー承認待ち)以外の棚卸しを優先候補とする。
- フェーズ165(2026-08-31 15:00 UTC): フェーズ164の申し送り通り他venture・アイデア領域の
  前進を優先し、follow-unfollow-event-handling-design.md「残課題」に残っていた「『ブロック
  したのに課金だけ続く』場合のオーナー向け運用課題は本venture側でもスコープ外として残る」
  という未着手事項に対応した。course-set-pashaのunfollow-billing-faq.md(フェーズ86)を
  土台に、本venture固有のサービス名・解約フロー(subscription-cancellation-flow-design.md、
  `PortalLinkProvider`)へ翻案したunfollow-billing-faq.mdを新規作成し、(1)LP掲載用FAQ文面
  (「ブロック=解約ではない」の事前周知)、(2)オーナー自身がメール等の問い合わせに使える
  返信テンプレート(事後対応)の2点を整理した。1.のFAQ文面はlanding-page-copy-draft.mdの
  既存FAQセクションに4問目として反映し、follow-unfollow-event-handling-design.md側の
  該当記載にも解消済みの旨を追記した。文面整理のみでコード変更は無し、venture全体358件
  全件パス・schema検証9件パスを再確認した。プロアクティブな検知・通知バッチの要否は
  unfollow-billing-faq.md「今後の課題」として引き続き未着手のまま残る。line-reservation-ai
  にも同種の未着手課題(user-account-linking-design.md周辺)が残っているため次回以降の
  候補とする。承認不要な文書作成・整理のみで、外部サービスへの公開・アカウント作成・
  メール送信等は今回発生していないためpending-approval.mdへの追記なし。
- フェーズ166(2026-08-31 17:00 UTC): unfollow-billing-faq.md「今後の課題」節を棚卸しした
  結果、「FAQ文面をlanding-page-copy-draft.mdへ反映する作業(本ドキュメント作成後の別作業
  として実施予定)」という記載が、実際には同一フェーズ165内で既にlanding-page-copy-draft.md
  4問目への反映まで完了していた(landing-page-copy-draft.md該当箇所で確認)にもかかわらず
  未着手のまま記載され続けていた記載漏れ(course-set-pashaの一連のドキュメント整合性
  メンテナンスと同種)であることを発見・解消した。該当項目を解消済みに更新した。コード変更は
  無し(ドキュメント整理のみ)、venture全体358件全件パス・schema検証9件パスを再確認した。
  承認不要なドキュメント整理のみで、外部サービスへの公開・アカウント作成・メール送信等は
  今回発生していないためpending-approval.mdへの追記なし。
- フェーズ167(2026-08-31 21:00 UTC): unfollow-billing-faq.md「今後の課題」に残っていた
  「本サービス側から能動的に『ブロック中かつ契約継続中』の業者を検知するプロアクティブな
  通知バッチの要否・設計は未着手」に対応した。設計に着手する前段階で、そもそも本venture側に
  「誰がLINEをブロックしたか」を記録する手段自体が無かった(process_unfollow_event()が
  design 2節の通り「何もしない」実装だったため)ことを発見し、blocked-but-billing-
  detection-design.mdとして新規設計した。`UserProfile`に`is_following: bool = True`
  フィールドを追加し、`process_follow_event()`/`process_unfollow_event()`が
  follow/unfollowイベント受信のたびに更新するよう配線(`dispatch_webhook_events()`からの
  `profile_store`結線含む)、`prototype/blocked_but_billing_candidates.py`に
  `list_blocked_but_billing_candidates()`(`is_following=False`かつ`current_plan_id`が
  設定されているuser_idを洗い出す読み出し専用関数、deletion_candidate.pyと同じ位置づけ)を
  新規実装した。契約情報(`current_plan_id`等)は従来通り一切変更せず、`is_following`は
  別軸の追加フラグという整理としたためfollow-unfollow-event-handling-design.md 2節の
  既存決定とは矛盾しない。テスト12件追加(follow/unfollowイベント処理4件・dispatch結線
  1件・候補洗い出しロジック6件・postback系の既存動作に影響がないことの確認含む)、
  venture全体370件全件パス・schema検証9件パスを確認した。候補一覧を実際にオーナーへ届ける
  手段(バッチ実行主体・通知チャネル)は未設計のまま残る(blocked-but-billing-detection-
  design.md 4節)。承認不要な設計・実装・テスト追加・アイデア追加のみで、外部サービスへの
  公開・アカウント作成・メール送信等は今回発生していないためpending-approval.mdへの
  追記なし。
- フェーズ168(2026-09-01 21:00 UTC): user-account-linking-design.mdの「未検証・残課題」節に
  残っていた2点の記載漏れを発見・解消した。(1)「tech-stack.mdコンポーネント5の記述の更新が
  必要な残課題」という記載は、実際には同一フェーズ107内でtech-stack.md側に既に追記済み
  (「usage_counterのみが唯一の永続データ」という整理が不正確だった旨、`pending_links`・
  `user_profile`の2コレクションが別途必要である旨)だったことを確認し、解消済みとして訂正
  した。(2)「連携失敗時の確定文言〈`LINKING_SUCCESS_MESSAGE`・`LINKING_REQUIRED_MESSAGE`〉は
  未確定」という記載も、その後tone-and-manner-guideline.md「連携コード関連文言の最終確定」節
  で既にトーン&マナーガイドラインとの整合確認が完了し確定文言として結論済みだったことを
  確認し、同じく解消済みとして訂正した。いずれもドキュメント間の整合確認・記載修正のみで
  コード変更は無し、venture全体370件全件パス・schema検証9件パスを再確認した。なお
  blocked-but-billing-detection-design.md 4節に残る「候補一覧をオーナーへ届ける手段の設計」
  は、実LINE・実Stripe接続後にunfollow発生率が実測できてから設計する方が精度が高いという
  既存の判断(フェーズ167)を踏襲し、本フェーズでは対象外のまま据え置いた。承認不要な
  ドキュメント整理のみで、外部サービスへの公開・アカウント作成・メール送信等は今回発生して
  いないためpending-approval.mdへの追記なし。
- フェーズ169(2026-09-02 00:00 UTC): limit-approaching-notification-design.md「5. 実装への
  影響メモ」に残っていた「設計のみ、実装は次回以降」という記載が、実際にはフェーズ76
  (2026-08-18 03:00 UTC)で`UsageCounterProtocol`/`InMemoryUsageCounter`/固定閾値
  `NOTICE_THRESHOLD = 5`としてprototype/cloud_function_webhook.pyに実装済み(境界値
  35/85/145回目到達・上限超過を含むテスト13件も追加済み)だった記載漏れを発見した。
  あわせて、本節が実装前のイベント処理関数の仮称として書いていた
  `process_visit_memo_event()`も、実装時に実際の関数名`process_memo_event()`へ
  命名変更されていた点も併せて訂正した。ドキュメント間の整合確認・記載修正のみで
  コード変更は無し、venture全体370件全件(`python3 -m unittest discover -s prototype
  -p "test_*.py"`)パスを再確認した。承認不要なドキュメント整理・アイデア追加のみで、
  外部サービスへの公開・アカウント作成・メール送信等は今回発生していないため
  pending-approval.mdへの追記なし。
- フェーズ170(2026-09-02 07:00 UTC): trial-end-scheduler-design.md 2節・
  trial-end-notification-design.md 4節の両方に残っていた「`handle_checkout_session_
  completed()`は`stripe_customer_id`の書き込みのみで`upgraded_at`(有料転換日時)は
  未書き込み、書き込み配線は次回以降の課題」という記載が、実際には`prototype/
  stripe_webhook.py`のdocstring・`test_stripe_webhook.py`の`test_upgraded_at_
  defaults_to_current_time_when_now_omitted`等のテストが示す通りフェーズ135で
  既に実装済み(`profile.upgraded_at is None`の場合のみ`store.set_upgraded_at()`を
  呼ぶ「1回だけ書き込む」不変条件付き)だった記載漏れを、両ドキュメント作成
  (それぞれフェーズ133・129)以降フェーズ135の実装内容が反映されないまま残っていたと
  発見・解消した。ドキュメント間の整合確認・記載修正のみでコード変更は無し、venture
  全体370件全件(`python3 -m unittest discover -s prototype -p "test_*.py"`)パス・
  schema検証9件パスを再確認した。承認不要なドキュメント整理・アイデア追加のみで、
  外部サービスへの公開・アカウント作成・メール送信等は今回発生していないため
  pending-approval.mdへの追記なし。
- フェーズ171(2026-09-02 09:58 UTC): trial-end-condition-a-cta-design.md「4. 対象外に
  した範囲」に残っていた「trial-end-notification-design.md 4節の『生成一時停止』実装は
  本フェーズでも引き続き対象外・本venture未着手のまま次回以降の課題」という記載が、
  実際には同ドキュメント作成(フェーズ137)の直後のフェーズ138で
  `prototype/cloud_function_webhook.py`に`_is_generation_paused(profile)`・
  `GENERATION_PAUSED_MESSAGE`・`process_memo_event()`冒頭の短絡分岐として実装済み
  (trial-end-notification-design.md 4節側には解消済みの旨が既に記載されていた)だった
  記載漏れ(フェーズ155・157・159・160・163・164・168・169・170と同種のドキュメント
  棚卸し)を発見・解消した。コード変更は無し(ドキュメント整理のみ)、venture全体370件
  全件(`python3 -m unittest discover -s prototype -p "test_*.py"`)パス・schema検証9件
  パスを再確認した。承認不要なドキュメント整理・アイデア追加のみで、外部サービスへの
  公開・アカウント作成・メール送信等は今回発生していないためpending-approval.mdへの
  追記なし。次回は他venture・アイデア領域の前進、またはpayment-failure-dunning-design.md
  6節・blocked-but-billing-detection-design.md 4節等に残る実LINE・実Stripe接続待ちの
  残課題(オーナー承認待ち)以外の棚卸しを優先候補とする。
- フェーズ172(2026-09-02 10:58 UTC): 各設計docの残課題を棚卸しした結果、
  character-limit-fallback-design.md冒頭(フェーズ102作成時点)に残っていた
  「実装未着手・動作未検証(実LLM・実LINE API接続はオーナー承認待ちのため)」という記載が、
  実際には同ドキュメント末尾の「残課題」節が示す通りフェーズ103(トーン&マナー整合確認)・
  フェーズ105(`check_message_length_within_line_limit()`の`prototype/post_generation_
  checks.py`への実装、`cloud_function_webhook.py`側の`LENGTH_LIMIT_FALLBACK_MESSAGE`
  分岐配線、テスト13件追加)で実装・検証まで完了済みだった記載漏れ(フェーズ155・157・
  159・160・163・164・168・169・170・171と同種のドキュメント棚卸し。冒頭の課題提起文と
  末尾の解決記録が矛盾したまま長期間放置されていたケース)を発見・解消した。
  `check_message_length_within_line_limit`・`LENGTH_LIMIT_FALLBACK_MESSAGE`・
  `LENGTH_LIMIT_ERROR_PREFIX`が`prototype/post_generation_checks.py`・
  `prototype/cloud_function_webhook.py`に現存し、`test_post_generation_checks.py`・
  `test_cloud_function_webhook.py`双方にテストが存在することをコード上で確認した上で
  冒頭の記載を訂正した。コード変更は無し(ドキュメント整理のみ)、venture全体370件全件
  (`python3 -m unittest discover -s prototype -p "test_*.py"`)パス・schema検証9件パスを
  再確認した。承認不要なドキュメント整理・アイデア追加のみで、外部サービスへの公開・
  アカウント作成・メール送信等は今回発生していないためpending-approval.mdへの追記なし。
  次回は他venture・アイデア領域の前進、またはpayment-failure-dunning-design.md 6節・
  blocked-but-billing-detection-design.md 4節等に残る実LINE・実Stripe接続待ちの残課題
  (オーナー承認待ち)以外の棚卸しを優先候補とする。
- フェーズ173(2026-09-02 14:02 UTC): 各設計docの残課題を棚卸しした結果、
  stripe-webhook-signature-verification-design.md「残課題」・stripe-webhook-event-
  dispatch-design.md 3節・5節に残っていた「HTTPエントリポイント本体
  (`receive_stripe_webhook()`)・`resolve_user_id`(`stripe_customer_id → user_id`解決)は
  未実装・次の課題」という記載が、実際にはフェーズ127(stripe-webhook-http-entry-point-
  design.md)で`prototype/stripe_webhook.py`の`receive_stripe_webhook()`・
  `make_resolve_user_id()`として、フェーズ107で`prototype/user_id_linking.py`の
  `get_user_id_by_stripe_customer_id()`として、いずれも実装済みだった記載漏れ(フェーズ155・
  157・159・160・163・164・168・169・170・171・172と同種のドキュメント棚卸し)を発見・
  解消した。あわせて`prototype/stripe_dispatch.py`冒頭のモジュールdocstringに残っていた
  同種の古い記載(「HTTPエントリポイントは本ventureにまだ存在せず」)も訂正した。コード変更は
  無し(ドキュメント・docstring整理のみ)、venture全体370件全件(`python3 -m unittest
  discover -s prototype -p "test_*.py"`)パスを再確認した。承認不要なドキュメント整理・
  アイデア追加のみで、外部サービスへの公開・アカウント作成・メール送信等は今回発生していない
  ためpending-approval.mdへの追記なし。次回は他venture・アイデア領域の前進、または
  payment-failure-dunning-design.md 6節・blocked-but-billing-detection-design.md 4節等に
  残る実LINE・実Stripe接続待ちの残課題(オーナー承認待ち)以外の棚卸しを優先候補とする。
- フェーズ174(2026-09-02 19:59 UTC): blocked-but-billing-detection-design.md(フェーズ167)
  4節「未着手のまま残る課題」に残っていた「候補一覧をオーナーへ実際に届ける手段は未設計・
  未接続」に対応した。フェーズ167時点では実LINE・実Stripe接続後の実測データ待ちとして
  あえて先送りしていたが、course-set-pashaが同種の課題をフェーズ143で「固定のオーナー1件へ
  LINE Push」という既存パターンの転用のみ(実測データ不要)で解決していた前例
  (blocked-but-billing-owner-notification-design.md 6節「同様の設計はaircon-pasha側でも
  横展開可能」の記載)に基づき、本venture向けにも横展開した。本venture一貫の
  `LinePushClient`がプレーンテキストではなくFlex Messageのみ(`send_flex_message`)を
  提供する点がcourse-set-pasha版との差分であるため、ボタンを持たないシンプルなbubble形式の
  Flex Messageとして通知文面を組み立てる設計・実装とした
  (blocked-but-billing-owner-notification-design.md新規作成)。
  `prototype/blocked_but_billing_owner_notification.py`に
  `select_new_blocked_but_billing_candidates_for_notification()`・
  `build_blocked_but_billing_owner_notification_flex_message()`・
  `send_blocked_but_billing_owner_notifications()`(Cloud Function G相当)を実装、
  `user_id_linking.py`の`UserProfile`に`blocked_but_billing_owner_notified_at`
  フィールド(1候補=1回のみ通知の冪等性フラグ)を追加し`UserProfileStoreProtocol`/
  `InMemoryUserProfileStore`にget/setメソッドを追加した。フォロー再開・解約確定時の
  クリア配線は次回以降の実装課題として残す(course-set-pashaもフェーズ142→143→144の
  3段階で同じ順序を踏んだ、詳細はdesign 6節参照)。テスト11件追加、venture全体381件全件
  パス・schema検証9件パスを確認した。承認不要な設計・実装・テスト追加のみで、外部サービスへの
  公開・アカウント作成・支払い等は今回発生していないためpending-approval.mdへの追記なし。
- フェーズ175(2026-09-02 21:59 UTC): フェーズ174「次回以降の実装課題」に残っていた、
  「フォロー再開」・「解約確定」時の`blocked_but_billing_owner_notified_at`クリア配線を
  実装した。course-set-pashaが同種の課題をフェーズ142→143→144の3段階で解決した前例の
  最終段階(フェーズ144相当)に当たる。`blocked_but_billing_owner_notification.py`に
  `clear_blocked_but_billing_owner_notified_at()`(`payment_failure.py`の
  `clear_payment_failure_on_success()`と同じ「設定済みの場合のみクリアしTrue/Falseを
  返す」純粋関数、および読み書き両方を要求する合成Protocol
  `BlockedButBillingOwnerNotifiedAtStoreProtocol`)を新設し、
  `cloud_function_webhook.process_follow_event()`(フォロー再開)・
  `stripe_dispatch.dispatch_stripe_event()`の`customer.subscription.deleted`分岐
  (解約確定)の両方から呼び出す配線を追加した。`dispatch_stripe_event()`・
  `receive_stripe_webhook()`・`get_stripe_runtime_dependencies()`に新規引数
  `blocked_but_billing_store`(省略時は従来通りクリアを行わない後方互換)を追加し、
  `plan_store`等と同じく`InMemoryUserProfileStore`が構造的に満たす設計とした。
  `set_blocked_but_billing_owner_notified_at`の型を`Optional[datetime]`へ拡張し
  `None`渡しでクリアを表現する、本venture一貫の方針を踏襲した。テスト7件追加、
  venture全体388件全件(`python3 -m unittest discover -s prototype -p "test_*.py"`
  相当、pytest実行)パス・schema検証9件パスを確認した。承認不要な設計・実装・テスト
  追加のみで、外部サービスへの公開・アカウント作成・支払い等は今回発生していないため
  pending-approval.mdへの追記なし。
- フェーズ176(2026-09-03 00:58 UTC): 各設計docの残課題を棚卸しした結果、
  trial-end-notification-design.md 6節に残っていた「`process_postback_event()`本体の実装・
  実Stripe接続はなお次回以降の課題」「4節の『生成一時停止』判定の実コード実装はなお次回以降の
  課題として残る」という2件の記載が、実際にはそれぞれフェーズ132(`prototype/
  cloud_function_webhook.py`の`process_postback_event()`・`dispatch_webhook_events()`への
  `postback`種別振り分け)・フェーズ138(`_is_generation_paused()`・
  `GENERATION_PAUSED_MESSAGE`)で実装済みだった記載漏れ(フェーズ155・157・159・160・163・
  164・168・169・170・171・172・173と同種のドキュメント棚卸し)を発見・解消した。コード上で
  `process_postback_event`・`dispatch_webhook_events`・`_is_generation_paused`がいずれも
  `prototype/cloud_function_webhook.py`に現存することを確認した上で該当箇所を訂正した。
  コード変更は無し(ドキュメント整理のみ)、venture全体388件全件
  (`python3 -m unittest discover -s prototype -p "test_*.py"`)パス・schema検証9件パスを
  再確認した。承認不要なドキュメント整理・アイデア追加のみで、外部サービスへの公開・
  アカウント作成・支払い等は今回発生していないためpending-approval.mdへの追記なし。次回は
  他venture・アイデア領域の前進、または実Cloud Scheduler・実Stripe接続待ち(オーナー承認待ち)
  以外の残課題棚卸しを優先候補とする。
- フェーズ177(2026-09-03 04:01 UTC): 各設計docの残課題を棚卸しした結果、
  `prototype/payment_failure.py`のモジュールdocstring(フェーズ139作成時点のまま)に、
  「猶予期間終了後に制限モードへ移行させるスケジューラ」「`_is_generation_paused()`の
  判定条件拡張・制限モード専用メッセージの配線」「決済成功時の復旧通知3分岐の文言出し分け」
  の3件が「次回以降の課題」として残ったままの記載漏れを発見した。payment-failure-dunning-
  design.md 6節では既にフェーズ143・141・148でそれぞれ対応済みと正しく記録されており
  (前者2件はフェーズ155・176の棚卸しでも`cloud_function_webhook.py`側のコメントは訂正済み
  だったが、`payment_failure.py`自身のdocstringは今回まで未訂正のまま残っていた)、実際に
  `payment_suspension_scheduler.py`(フェーズ145)・`_is_payment_suspended()`
  (フェーズ141)・`payment_recovery_notification.py`+`recovery_push_client`配線
  (フェーズ146・148・149)がいずれも現存することをコード上で確認した上で、docstringを
  解消済みの旨に訂正した。コード変更は無し(docstring整理のみ)、venture全体388件全件
  (`python3 -m unittest discover -s prototype -p "test_*.py"`)パス・schema検証9件パスを
  再確認した。承認不要なドキュメント整理のみで、外部サービスへの公開・アカウント作成・
  支払い等は今回発生していないためpending-approval.mdへの追記なし。
- フェーズ178(2026-09-03 11:01 UTC): `cloud_function_webhook.py`の`PortalLinkProvider`
  Protocol(`get_portal_url(user_id) -> Optional[str]`)は既存だが、その実装本体
  (実`stripe.billing_portal.Session.create()`呼び出し)が未設計のまま`InMemoryPortalLinkProvider`
  (検証用の固定URLスタブ)のみが存在していたギャップに対応した。course-set-pashaがフェーズ
  148・149で実装した`customer-portal-session-endpoint-design.md`/`StripePortalLinkProvider`
  を横展開したが、本ventureのCheckout Session作成がLIFF IDトークン検証を経由せずLINEの
  postbackイベント(`source.userId`がプラットフォーム自身に認証済み)を前提とする設計
  (checkout_session.py)であるため、対称となるLIFF検証を伴うHTTPエンドポイント
  (`create_portal_session()`)は不要と判断し、`PortalLinkProvider`実装本体
  (`StripePortalLinkProvider`)のみを設計・実装する`portal-session-provider-design.md`を
  新規作成した。前提として、`StripePortalLinkProvider`が必要とする順引きgetter
  `user_id_linking.UserProfileStoreProtocol.get_stripe_customer_id(user_id)`が、
  「現時点でどこからも呼ばれないため未追加」と明記されたまま存在していなかったため、
  `UserProfileStoreProtocol`/`InMemoryUserProfileStore`に追加した。`prototype/portal_session.py`
  (新規)に`build_portal_session_params()`・`StripePortalLinkProvider`・
  `_create_billing_portal_session_not_implemented()`を実装した。テスト11件追加
  (`user_id_linking`側3件・`portal_session`側8件)、venture全体406件全件
  (`python3 -m unittest discover -p "test_*.py"`)パス・schema検証9件パスを確認した。
  実`session_creator`差し替え・呼び出し元(`get_runtime_dependencies()`等)を実際に
  `InMemoryPortalLinkProvider`から`StripePortalLinkProvider`へ差し替える配線は、実Stripe
  アカウント接続(オーナー承認待ち)後の課題として引き続き残す。承認不要な設計・実装・テスト
  追加のみで、外部サービスへの公開・アカウント作成・支払い等は今回発生していないため
  pending-approval.mdへの追記なし。
- フェーズ179(2026-09-03 17:00 UTC): course-set-pasha・line-reservation-aiの
  「Checkout Sessionが購入プランを記録していない」ギャップの横展開検討中に、本ventureは
  それ以上に根本的なギャップ(`build_checkout_session_params()`が`line_items`を一切
  含めておらず、`mode="subscription"`のCheckout Sessionは実Stripe接続後にAPI呼び出し
  自体が失敗する状態のまま放置されていた)を発見した。
  checkout-session-plan-selection-design.mdを新規作成し、`PLAN_TO_STRIPE_PRICE_ID_
  PLACEHOLDER`(pricing-plan.mdの3プラン名→Price IDプレースホルダ)・
  `DEFAULT_CHECKOUT_PLAN`(`"スタンダード"`)を新設、`build_checkout_session_params()`に
  `plan`引数(既定値`DEFAULT_CHECKOUT_PLAN`、未知の値は`ValueError`)を追加し常に1件の
  `line_items`を含めるようにした。本venture固有の事情(決済導線が単一postbackボタンで
  LIFFプラン選択UIを持たない)を踏まえ、全ユーザーをスタンダードプランで開始させ、開始後の
  プラン変更は既存のStripe Customer Portal導線(フェーズ178)に委ねる設計とした
  (`subscription_plan_sync.py`が`customer.subscription.updated`から`current_plan_id`を
  自動追従するため、追加のアプリ側実装は不要)。`cloud_function_webhook.py`が既に
  `checkout_session.py`をインポートしているため循環インポートを避け、プラン名リテラルは
  本venture既存の重複パターンを踏襲し独立して保持した(course-set-pashaとインポート方向が
  逆のため同じ横展開手法は使えなかった)。テスト5件追加、venture全体411件全件パス・
  schema検証9件パスを確認した。プラン選択UI(postbackボタンの複数分割)・実Price ID確定は
  次回以降の課題として残る。承認不要な設計・実装・テスト追加のみで、外部サービスへの公開・
  アカウント作成・支払い等は今回発生していないためpending-approval.mdへの追記なし。
- フェーズ180(2026-09-03 21:00 UTC): フェーズ179「次回以降の課題」に残っていた
  postbackボタンの複数プラン分割に着手した。`checkout_session.py`に
  `build_start_checkout_postback_data(plan)`(`"action=start_checkout&plan=<プラン名>"`を
  組み立て)・`parse_start_checkout_postback_data(data)`(逆にプラン名を解決、プラン未指定の
  `START_CHECKOUT_POSTBACK_DATA`は`DEFAULT_CHECKOUT_PLAN`へ後方互換、未知のプラン名は`None`)
  を新設した。`trial_end_scheduler.build_trial_end_notification_flex_message()`
  (業者が最初にプランを選ぶ主要な入口であるトライアル終了通知Push Message)のFlex
  Messageフッターを、単一ボタンから3プラン分のボタン(スモール/スタンダード/繁忙期対応、
  既定プランのみ`style: primary`)へ変更した。`cloud_function_webhook.process_postback_event()`
  は`parse_start_checkout_postback_data()`でpostbackデータからプラン名を解決し
  `build_checkout_session_params(..., plan=...)`へ渡すよう変更、未知のプラン名は他の
  未対応アクションと同様`handled=False`で素通りする(安全側)。条件A(生成回数到達)・
  一時停止/制限モード通知等、`QuickReplyButton`(現状`Optional`単数)経由の他CTAは
  対象外とし、既定プラン据え置きのまま次回以降の課題として残した(`QuickReplyButton`の
  複数ボタン対応は`ReplyClient.reply()`・`InMemoryReplyClient`・呼び出し元3箇所の変更を
  伴うため)。テスト9件追加(`test_checkout_session.py`7件・`test_cloud_function_webhook.py`
  2件、`test_trial_end_scheduler.py`の既存テスト1件を3ボタン確認に更新)、venture全体
  420件全件(`python3 -m unittest discover -s prototype -p "test_*.py"`)パス・schema検証
  9件(`python3 schema/validate_test_cases.py`)パスを確認した。詳細は
  checkout-session-plan-selection-design.md「残課題」節参照。実Price ID確定・Stripe
  Customer Portalでのプラン変更許可設定は引き続き実Stripeアカウント接続(オーナー承認待ち)
  後の課題として残る。承認不要な設計・実装・テスト追加のみで、外部サービスへの公開・
  アカウント作成・支払い等は今回発生していないためpending-approval.mdへの追記なし。
- フェーズ181(2026-09-03 23:00 UTC): フェーズ180「次回以降の課題」に残っていた、
  条件A(生成回数到達)・生成一時停止通知の`QuickReplyButton`複数ボタン対応に着手した。
  `ReplyClient.reply()`・`InMemoryReplyClient.reply()`・`_reply_with_retry()`の
  `quick_reply`引数を`Optional[QuickReplyButton]`単数から`Optional[list[QuickReplyButton]]`へ
  変更し、新設の`_build_plan_selection_quick_reply()`(`checkout_session.
  PLAN_TO_STRIPE_PRICE_ID_PLACEHOLDER`の3プラン分、`build_start_checkout_postback_data(plan)`で
  postback_dataを組み立て、ラベルは`trial_end_scheduler.build_trial_end_notification_
  flex_message()`のfooterボタンと表記を揃えた`"{plan}プランで始める"`)を`process_memo_event()`の
  条件A・生成一時停止の2経路に適用した。`process_postback_event()`側は
  `parse_start_checkout_postback_data()`で従来通り解釈できるため変更不要。決済失敗時の
  制限モード通知(`UPDATE_PAYMENT_METHOD_POSTBACK_DATA`)はプラン選択ではなく支払い方法の
  更新のCTAのため対象外とし、単一ボタンを要素数1のリストとして渡す形のみ変更した。
  本venture内で`TRIAL_END_BUTTON_LABEL`・`START_CHECKOUT_POSTBACK_DATA`(いずれも旧単一ボタン
  用)がcloud_function_webhook.py側で不要になったためimportを削除した(テスト側は
  払込方法CTAの単一ボタンケース・postbackイベントテストで引き続き使用するため残した)。
  テスト更新のみ(新規テスト追加なし、既存3テストの期待値を単一`QuickReplyButton`から
  3ボタンのリストへ更新)、venture全体420件全件(`python3 -m unittest discover -s prototype
  -p "test_*.py"`)パス・schema検証9件(`python3 schema/validate_test_cases.py`)パスを
  確認した。詳細はcheckout-session-plan-selection-design.md「残課題」節参照。実Price ID確定・
  Stripe Customer Portalでのプラン変更許可設定は引き続き実Stripeアカウント接続
  (オーナー承認待ち)後の課題として残る。承認不要な設計・実装・テスト更新のみで、
  外部サービスへの公開・アカウント作成・支払い等は今回発生していないため
  pending-approval.mdへの追記なし。
- フェーズ182(2026-09-04 02:00 UTC): 各設計docの残課題を棚卸しした結果、
  blocked-but-billing-detection-design.md 4節「未着手のまま残る課題」の記載
  (フェーズ174時点で追記した「フォロー再開・解約確定時の
  `blocked_but_billing_owner_notified_at`クリア配線は引き続き次回以降の実装課題として
  残る」という一文)が、実際にはフェーズ175で解消済みであるにもかかわらず訂正されずに
  残っていた記載漏れを発見した(フェーズ155・157・159・160・163・164・168・169・170・171・
  172・173・176・177と同種のドキュメント棚卸し)。コード上で
  `blocked_but_billing_owner_notification.clear_blocked_but_billing_owner_notified_at()`が
  `prototype/blocked_but_billing_owner_notification.py`に実装済みであり、
  `prototype/cloud_function_webhook.py`の`process_follow_event()`(フォロー再開)・
  `prototype/stripe_dispatch.py`の`dispatch_stripe_event()`の
  `customer.subscription.deleted`分岐(解約確定)の両方から実際に呼び出されていることを
  確認した上で、4節の該当箇所をフェーズ175での解消内容(新設関数名・呼び出し元2箇所)を
  明記する記載へ訂正した(blocked-but-billing-owner-notification-design.md 6節の記載とも
  整合させた)。コード変更は無し(ドキュメント整理のみ)、venture全体420件全件
  (`python3 -m unittest discover -s prototype -p "test_*.py"`)パス・schema検証9件
  (`python3 schema/validate_test_cases.py`)パスを再確認した(いずれも変更前と同じ件数、
  ドキュメントのみの変更であるため差分なし)。承認不要なドキュメント整理のみで、
  外部サービスへの公開・アカウント作成・支払い等は今回発生していないため
  pending-approval.mdへの追記なし。次回はcheckout-session-plan-selection-design.md
  「残課題」に残る実Price ID確定(オーナー承認待ち)以外の、他venture・アイデア領域の
  前進、または未走査の設計docの残課題棚卸しを優先候補とする。
- フェーズ183(2026-09-04 09:00 UTC): フェーズ182「次回候補」の「未走査の設計docの残課題
  棚卸し」に沿って各設計docを棚卸しした結果、stripe-webhook-signature-verification-design.md
  「残課題」に残っていた「Stripeイベントの重複配信対策(`event.id`によるべき等性チェック)は、
  エンドポイント本体側の設計課題として次回以降に持ち越す」という記載が、実際には
  stripe-event-idempotency-design.mdとして設計され`prototype/stripe_webhook.py`に
  `StripeEventIdStoreProtocol`・`InMemoryStripeEventIdStore`・`receive_stripe_webhook()`の
  `event_id_store`引数(同一`event.id`の2回目以降の配信ではハンドラを呼び出さず200を返す、
  省略時は従来通り無効という後方互換設計)として実装済み(`test_stripe_webhook.py`の
  `InMemoryStripeEventIdStoreTest`他で検証済み)だった記載漏れを発見・解消した。加えて、
  この実装作業自体はコミット履歴上「フェーズ177」として行われていたにもかかわらず、
  README.md側の現行フェーズ177エントリは別内容(`payment_failure.py`docstring整理、
  当時の並行セッションによるフェーズ番号の重複)であり、本実装のフェーズログ記載自体が
  README.mdから欠落していたことも判明した(コードは既存、ログ記載のみの欠落であるため
  過去フェーズ番号を付け直すことはせず、本フェーズの記載として補記する形で整理した)。
  コード変更は無し(ドキュメント整理のみ)、venture全体420件全件(`python3 -m unittest
  discover -s prototype -p "test_*.py"`)パス・schema検証9件(`python3 schema/
  validate_test_cases.py`)パスを再確認した(いずれも変更前と同じ件数、ドキュメントのみの
  変更であるため差分なし)。承認不要なドキュメント整理のみで、外部サービスへの公開・
  アカウント作成・支払い等は今回発生していないためpending-approval.mdへの追記なし。次回は
  他venture・アイデア領域の前進、またはcheckout-session-plan-selection-design.md「残課題」
  に残る実Price ID確定(オーナー承認待ち)以外の、未走査の設計docの残課題棚卸しを
  優先候補とする。
- 最終更新: 2026-09-04 09:00 UTC
