# 承認待ちアクション

支払い・アカウント作成・公開・送信など、オーナーの許可が必要なアクションをここに記録します。
記録するだけで実行はしません。オーナーがチャットで直接指示した時にのみ実行されます。

エントリの形式:

日時: YYYY-MM-DD HH:MM UTC
venture: ventures/<slug>/
内容: 具体的に何をしたいか
理由: なぜ必要か

---

日時: 2026-07-30 01:58 UTC
venture: ventures/line-reservation-ai/
内容: customer-interview-design.md で設計した想定顧客ヒアリング(美容室・整体院・パーソナルジム・個人講師業10件前後)について、実在の店舗・個人事業主への電話・LINE・メール等での連絡・依頼を実施したい。
理由: 料金プラン(pricing-plan.md)や会話フロー(conversation-flow.md)の妥当性を実顧客の声で検証するために必要だが、外部への連絡・送信はオーナー許可が必要なアクションのため、対象候補の選定・連絡文面の確定を含めオーナーの直接指示を待つ。
日時: 2026-07-30 13:40 JST
オーナー判断: 承認。オーナーがチャットで「いいよ」と回答し、上記ventureの顧客ヒアリング連絡を進めてよいとの意思表示を得た。
実行可能範囲: 本エージェントには電話発信・LINE送信機能はない。進めてよいのは次のとおりのみ。
(1)WebSearchで対象セグメント(美容室・整体院等)に合致する実在の候補店舗をリストアップしventureフォルダに記録。
(2)customer-interview-design.mdの16問を基に、メール/LINE送信用の連絡文面ドラフトを作成。
(3)電話・LINEでの実連絡はオーナー自身が行う。メール送信はGmail連携接続後、送信直前に毎回オーナーの確認を得てからのみ行う。

日時: 2026-07-31 13:58 UTC
venture: ventures/line-reservation-ai/
内容: schema/validate_test_cases.pyで机上検証したllm-system-prompt-draft.mdのシステムプロンプト・構造化出力スキーマを、実際のLLM API(Claude API等)に投入してconversation-samples-test-cases.mdの各ケース(N1〜N4、E1〜E16)の出力を自動テストしたい。
理由: これまでの設計・検証は全て机上(文章記述の突き合わせ)にとどまっており、実LLMが指示通りに安定した自然文・構造化出力を生成できるかは未確認。ただし実行にはAPIキーの取得(アカウント作成)と従量課金(支払い)が発生するため、オーナーの許可が必要なアクションに該当する。承認が得られれば、APIキー取得方法の提示・テストスクリプトの実装から着手する。

日時: 2026-08-09 01:00 UTC
venture: ventures/course-set-pasha/
内容: customer-interview-design.md で設計した想定顧客ヒアリング(個人経営ボルダリングジムオーナー・複合ジムオーナー・複数ジム掛け持ちセッター、candidate-longlist-draft.mdで有力候補と確定した候補1 FRICTION FREAKS等)について、initial-contact-message-draft.mdで草案した文面を使い、実在のジム・セッターへのInstagram DM・メール・電話等での連絡・依頼を実施したい。
理由: 料金プラン(pricing-plan.md)や告知文生成ルール(llm-system-prompt-draft.md)の妥当性を実顧客の声で検証するために必要だが、外部への連絡・送信はオーナー許可が必要なアクションのため、対象候補リスト・連絡文面(初回コンタクト依頼文面草案)の確定を含めオーナーの直接指示を待つ。line-reservation-aiの同種案件(2026-07-30 01:58 UTC、承認済み)と同じ実行可能範囲の想定: (1)WebSearchでの候補リストアップ・記録は実施済み、(2)連絡文面ドラフトの作成も本日実施済み、(3)Instagram DM・電話での実連絡はオーナー自身が行う、メール送信はGmail連携接続後に送信直前の毎回確認を経てのみ行う、という運用を承認いただけるかの確認。

日時: 2026-08-18 20:00 UTC
venture: ventures/course-set-pasha/
内容: application-form-submission-flow-design.md(フェーズ76)で設計した申込フォーム提出フローについて、実際のGoogleフォームの作成・Google Apps Script(GAS)Webhookの設定・デプロイを行いたい。
理由: 設計・prototype/application_form_submission_flow.pyでのロジック検証(正規化・書き込み処理、テスト16件)までは机上・コード上で完結できたが、Googleフォームの作成自体はGoogleアカウントでの外部サービス設定操作(「外部サービスへの公開」に類する行為)であり、オーナーの許可が必要なアクションに該当する。承認が得られれば、フォーム項目(ジム名・地域名欄)の作成、GAS Webhookスクリプトの実装・デプロイ、Cloud FunctionsエンドポイントへのPOST接続確認から着手する。

日時: 2026-08-20 21:00 UTC
venture: ventures/course-set-pasha/
内容: 上記(2026-08-18 20:00 UTC)の申込フォーム作成案件について、フォーム項目の仕様変更を申し送る。当初「LINE user_idを本人に手入力してもらう」前提だったが、line-user-id-linking-design.md(フェーズ77)での検討の結果、一般のLINEユーザーはアプリUI上から自分のuser_idを確認できず運用として成立しないことが判明したため、入力項目を「LINE友だち追加時にトークで届く連携コード(6文字)」に変更したい。あわせて、LINE公式アカウントのfollowイベント受信時に連携コードを発行してウェルカムメッセージで送る処理のデプロイも必要になる。
理由: フォーム作成・GAS配置は既に承認待ち事項として記録済みだが、その仕様が変わったため実施前にオーナーへ伝える必要がある。連携コードの発行・解決ロジック自体はprototype/user_id_linking.pyとして実装・テスト済み(11件)で、実行に必要なのはLINE公式アカウント開設・Messaging API接続・Googleフォーム作成という外部サービス側の設定のみであり、いずれもオーナーの許可が必要なアクションに該当するため着手していない。

日時: 2026-08-23 04:00 UTC
venture: ventures/aircon-pasha/
内容: user-account-linking-design.md(フェーズ107)で設計した「申込フォーム送信完了時の連携コード発行→LINE初回メッセージでのコード送信」方式について、実際のGoogleフォームの作成・フォーム送信をトリガーとするGoogle Apps Script(GAS)Webhookの実装・デプロイを行いたい。
理由: 連携コードの判定・解決ロジック自体は机上設計(user-account-linking-design.md 3節)まで完了しているが、Googleフォームの作成自体は外部サービス側の設定操作(「外部サービスへの公開」に類する行為)であり、オーナーの許可が必要なアクションに該当する。course-set-pashaの同種案件(2026-08-18 20:00 UTC記載)と同じ範囲の承認を想定している。承認が得られれば、フォーム項目(屋号・事業形態・メールアドレス)の作成、GAS Webhookスクリプトの実装・デプロイ、連携コード発行処理の接続確認から着手する。

日時: 2026-08-21 12:00 UTC
venture: ventures/aircon-pasha/
内容: customer-interview-design.md相当の想定で候補研究を進めてきた独立系候補5件(候補1リノハンズ・候補3hello-osouji.com・候補7Clean Labo・候補10キキのおそうじ屋・候補12東京住まいる)、フランチャイズ加盟候補3件(候補2篠崎昌則オーナー・候補13金井美樹オーナー・候補14濱暁洋オーナー)について、initial-contact-message-draft.mdで草案した文面・台本を使い、実在の事業者への公式サイト問い合わせフォーム・電話・LINE公式アカウント等での初回コンタクト・ヒアリング協力依頼を実施したい(候補12のみ連絡先が一次情報未確認のため、承認が得られてもまずは残り7件から着手する想定)。
理由: 料金プランやllm-system-prompt-draft.mdの厳守事項の妥当性を実顧客の声で検証するために必要だが、外部の実在事業者への連絡・送信はオーナー許可が必要なアクションのため、対象候補リスト・連絡文面の確定を含めオーナーの直接指示を待つ。line-reservation-ai(2026-07-30 01:58 UTC承認済み)・course-set-pasha(2026-08-09 01:00 UTC)と同種の案件であり、承認が得られた場合の実行可能範囲も同様(本エージェントに電話発信・LINE送信機能はないため、電話・LINE等の実連絡はオーナー自身が行い、メール送信はGmail連携接続後に送信直前の毎回確認を経てのみ行う)を想定している。

日時: 2026-08-23 09:00 UTC
venture: ventures/course-set-pasha/
内容: checkout-initiation-flow-design.md(フェーズ98)・trial-end-notification-design.md(フェーズ99)で設計した決済導線について、実際のLINE DevelopersコンソールでのLIFFアプリ登録、および無料トライアル終了(期間到達)判定用のCloud Scheduler(GCPプロジェクトの課金設定を伴う)の作成を行いたい。
理由: Checkout Session作成時になりすましを防ぐためのuser_id取得方式としてLIFF経由のIDトークン検証を採用する設計(checkout-initiation-flow-design.md 2節)まで完了しているが、LIFFアプリ自体の登録は外部サービス側でのアカウント作成・設定操作に該当し、Cloud Schedulerの新規作成もGCPプロジェクトの課金設定を伴うため、いずれもオーナーの許可が必要なアクションに該当する。承認が得られれば、LIFFアプリのURL・スコープ設定、IDトークン検証処理(`/oauth2/v2.1/verify`相当)の実装、日次スケジューラのデプロイから着手する。

日時: 2026-08-28 17:00 UTC
venture: ventures/line-reservation-ai/
内容: checkout-initiation-flow-design.md(フェーズ続き139)で新規設計した決済導線について、実際のLINE Developersコンソールでの本venture用LIFFアプリ登録、およびLINE公式アカウントの開設(Basic ID確定、決済完了後にLINEへ戻るユニバーサルリンクの組み立てに必要)を行いたい。
理由: Checkout Session作成時になりすましを防ぐためのuser_id取得方式としてLIFF経由のIDトークン検証を採用する設計(checkout-initiation-flow-design.md 2節)、決済完了後にLINEへ戻るリンクの組み立てロジック(`prototype/checkout_session.py`の`build_line_return_link()`)までは完了しているが、LIFFアプリ自体の登録・LINE公式アカウントの開設(本venture自体の稼働に必須の前提でもある)はいずれも外部サービス側でのアカウント作成・設定操作に該当し、オーナーの許可が必要なアクションに該当する。course-set-pasha・aircon-pashaの同種案件(それぞれ2026-08-23 09:00 UTC・2026-08-23 04:00 UTC記載)と同じ範囲の承認を想定している。承認が得られれば、LIFFアプリのURL・スコープ設定、IDトークン検証処理の実装、LINE公式アカウントのBasic ID確定・`build_line_return_link()`への反映から着手する。

日時: 2026-09-11 04:00 UTC
venture: ventures/kura-pasha/
内容: customer-interview-design.md・interview-candidate-selection-criteria.md・interview-rehearsal-script.mdで設計した想定顧客ヒアリング(鞍職人・馬具師)について、candidate-longlist-draft.md第五弾で優先順位付けした候補のうち優先順位1(ライディングショップ池上、代表・池上豊氏、千葉県富里市、公式サイトの問い合わせフォーム経由)・優先順位2(エクウスワールド、運営:トライ企画・代表 伊藤政男氏、代表個人への直通電話経由)への、initial-contact-message-draft.mdで草案済みの文面・台本(文面案A: メール・問い合わせフォーム用、文面案B: 電話トーク要点)を使った初回コンタクト・ヒアリング協力依頼の実施を行いたい(保留中のジャパンギャロップスインポーターは今回の対象外とし、優先順位1・2の結果を踏まえて改めて判断する)。
理由: pricing-plan.md(低頻度・高単価前提の3プラン設計)やllm-system-prompt-draft.mdの厳守事項(修理可否判断への不介入等)の妥当性を実顧客の声で検証するために必要だが、外部の実在事業者への連絡・送信はオーナー許可が必要なアクションのため、これまで候補選定・選定基準・文面草案・リハーサル台本の作成(2026-09-06 10:00〜23:00 UTC、フェーズ7〜16)は完了させつつも実際の連絡は一切行っていなかった。line-reservation-ai(2026-07-30 01:58 UTC承認済み)・course-set-pasha(2026-08-09 01:00 UTC)・aircon-pasha(2026-08-21 12:00 UTC)と同種の案件であり、承認が得られた場合の実行可能範囲も同様(本エージェントには電話発信・LINE送信機能はないため、電話での実連絡・メールフォーム送信文面の最終確定はオーナー自身が行うか、Gmail連携接続後に送信直前の毎回確認を経てのみ行う)を想定している。本フェーズまで本venture固有のこの承認依頼自体がpending-approval.mdに記録されていなかった記載漏れであったため、今回新規に記録した。

日時: 2026-09-15 03:00 UTC
venture: ventures/kura-pasha/
内容: daily-scheduler-design.md(フェーズ112・120)で設計・実装した日次バッチ(Cloud Function G: `run_daily_workshop_checks()`、(B)トライアル30日到達報告・決済失敗3日前リマインド・制限モード移行時のオーナー通知を送信)について、実際のLINE公式アカウントの開設(Messaging APIのチャネルアクセストークン取得)、および日次1回(暫定JST 04:00)起動するCloud Scheduler(GCPプロジェクトの課金設定を伴う)の作成を行いたい。あわせて、オーナー向け通知の送信先となる実際のオーナーLINEユーザーID(`payment_suspension_owner_notification.py`の`OWNER_LINE_USER_ID_PLACEHOLDER`に差し込む値)の設定も必要になる。
理由: `run_daily_workshop_checks()`本体・送信判定ロジック(`select_due_trial_end_reports()`等)・通知文言の組み立てはいずれもProtocol経由の依存注入・InMemoryStubによるテスト(フェーズ120、8件追加)まで完了しているが、実際のLINE公式アカウント開設・Cloud Schedulerの新規作成はいずれも外部サービス側でのアカウント作成・課金設定を伴う操作に該当し、オーナーの許可が必要なアクションに該当する。course-set-pasha(2026-08-23 09:00 UTC)・line-reservation-ai(2026-08-28 17:00 UTC)の同種案件と同じ範囲の承認を想定している(本venture自体の稼働に必須の前提でもあるLINE公式アカウント開設は、他の設計doc〈message-context-selection-design.md等〉でも繰り返し「実LINE公式アカウント接続待ち」として参照されていたが、この承認依頼自体がpending-approval.mdに記録されていなかった記載漏れであったため、今回新規に記録した)。承認が得られれば、実チャネルアクセストークンの設定、Cloud Schedulerのデプロイ、オーナーLINEユーザーIDの設定から着手する。

日時: 2026-09-27 03:00 UTC
venture: ventures/course-set-pasha/
内容: checkout-session-endpoint-design.md(フェーズ112)・checkout-session-cloud-function-entry-point-design.md(フェーズ115)で設計した決済フローについて、実際のStripeアカウントの開設(本人確認・銀行口座登録を含む)、本番用APIキー・Webhook署名シークレットの取得、`stripe_webhook.py`/`checkout_session.py`への実キー設定、およびStripe側Webhookエンドポイントの登録を行いたい。
理由: `create_checkout_session()`・`dispatch_stripe_event()`本体のロジック・状態遷移(トライアル管理・決済失敗猶予・解約確定判定等、直近ではフェーズ258の`subscription_canceled_at`判定追加を含む)はInMemoryStubによるテスト(venture全体663件・schema検証21件、いずれもパス)まで完了しているが、実Stripeアカウントの開設・本番APIキー取得はいずれも外部サービス側でのアカウント作成・決済手段登録を伴う操作であり、オーナーの許可が必要なアクションに該当する。本件はcheckout-session-cloud-function-entry-point-design.md 2節の`_verify_id_token_not_implemented`(LIFF実登録待ち、下記LIFF/LINE公式アカウント案件と対を成す)や、フェーズ256以降の複数回の「次回候補」記載で繰り返し「実Stripeアカウント接続待ち」として言及されてきたが、この承認依頼自体がpending-approval.mdに記録されていなかった記載漏れであったため、今回新規に記録した(aircon-pasha・kura-pashaも同型のStripe連携設計を持つが、本エントリはcourse-set-pashaの記載漏れの是正に限定する)。承認が得られれば、実APIキー・Webhookシークレットの設定、Stripe Webhookエンドポイント登録、`checkout-initiation-flow-design.md`で設計したLIFF経由IDトークン検証の実装(こちらは別途LIFFアプリ登録の承認が必要、2026-09-26頃の該当案件参照)と合わせた結合確認から着手する。

日時: 2026-09-27 07:00 UTC
venture: ventures/course-set-pasha/
内容: checkout-initiation-flow-design.md(フェーズ98)で設計した決済導線について、実際のLINE DevelopersコンソールでのLIFFアプリ登録(本venture用LINE公式アカウントのチャネルに紐づけて作成)を行いたい。
理由: stripe-liff-integration-sequence-design.md(フェーズ260)でStripe/LINE LIFF結合構成の依存関係を棚卸しした結果、LIFFアプリ登録自体がcheckout-initiation-flow-design.md「残課題」1点目でフェーズ98の時点から一貫して「オーナー承認待ち」と記述されていたにもかかわらず、実際にはpending-approval.mdへの記録が一度も行われていなかった記載漏れであることが判明したため、今回新規に記録した(直近のフェーズ259で発見・是正した実Stripeアカウント接続の記載漏れと同種の是正)。course-set-pashaのLINE公式アカウント自体の開設(2026-08-18 20:00 UTC記載の申込フォーム案件内で言及)もLIFF登録の前提として未承認のまま残っている。承認が得られれば、stripe-liff-integration-sequence-design.md 5節の順序(LINE公式アカウント開設→LIFFアプリ登録→IDトークン検証実装)に沿って着手する。

日時: 2026-09-27 08:00 UTC
venture: ventures/kura-pasha/
内容: checkout-initiation-flow-design.md(フェーズ50)・stripe-webhook-checkout-completed-design.md(フェーズ51)で設計した決済導線について、実際のStripeアカウントの開設(本人確認・銀行口座登録を含む)、本番用APIキー・Webhook署名シークレットの取得、`plan_id`→Stripe Price IDの対応表・`success_url`/`cancel_url`の実際の値確定、およびStripe側Webhookエンドポイントの登録を行いたい。
理由: Checkout Session発行ロジック・Webhook受信/署名検証/イベントディスパッチはいずれもInMemoryStub等によるテスト(venture全体171件・schema検証32件、いずれもパス)まで完了しているが、実Stripeアカウントの開設・本番APIキー取得はいずれも外部サービス側でのアカウント作成・決済手段登録を伴う操作であり、オーナーの許可が必要なアクションに該当する。本件はフェーズ50〜51の時点から両ドキュメント内で一貫して「オーナー承認待ち」と記述され、course-set-pashaフェーズ259・260で同種の記載漏れ(実Stripeアカウント接続・LIFFアプリ登録)が発見された際にも「kura-pashaも同型のStripe連携設計を持つが、本エントリはcourse-set-pashaの記載漏れの是正に限定する」と申し送られていたが、この承認依頼自体がpending-approval.mdに一度も記録されていなかった記載漏れであったため、今回kura-pasha側の監査(フェーズ191)で新規に記録した。なお本ventureはcheckout-initiation-flow-design.md 2節の設計判断によりLINE Platform Webhook受信時点で検証済みの`event.source.userId`をそのまま使う構成のため、LIFFアプリ登録自体は不要でありLIFF関連の記載漏れは該当しない。承認が得られれば、実APIキー・Webhookシークレットの設定、Stripe Webhookエンドポイント登録、plan_id→Price ID対応表の確定から着手する。

日時: 2026-09-27 09:00 UTC
venture: ventures/aircon-pasha/
内容: checkout-initiation-flow-design.md(フェーズ131)「残課題」で設計した決済導線について、実際のStripeアカウントの開設(本人確認・銀行口座登録を含む)、本番用APIキー・Webhook署名シークレットの取得、`success_url`/`cancel_url`の実際のLPドメイン確定、およびStripe側Webhookエンドポイントの登録を行いたい。あわせて、`success_url`/`cancel_url`が指す申込・案内用LP(ランディングページ)自体の実装・公開も必要になる。
理由: postbackイベント経由でのCheckout Sessionパラメータ組み立て(`build_checkout_session_params()`)・決済完了後のStripe側処理(checkout-session-completed-handling-design.md、フェーズ128)はいずれもInMemoryStub等によるテスト(プロトタイプ全体186件、いずれもパス)まで完了しているが、実Stripeアカウントの開設・本番APIキー取得・LPの公開はいずれも外部サービス側でのアカウント作成・決済手段登録・公開を伴う操作であり、オーナーの許可が必要なアクションに該当する。本件はcheckout-initiation-flow-design.md「残課題」で一貫して「オーナー承認待ち」と記述され、同ドキュメント3節手順5でも「pending-approval.md参照」と明記されていたにもかかわらず、course-set-pashaフェーズ259・260・kura-pashaフェーズ191で発見された記載漏れ(実Stripeアカウント接続・LIFFアプリ登録)と同種の是正がaircon-pasha自身には行われておらず、この承認依頼自体がpending-approval.mdに一度も記録されていなかった記載漏れであったため、今回aircon-pasha側の監査(フェーズ277)で新規に記録した。なお本ventureはcheckout-initiation-flow-design.md 1節の設計判断により決済ボタンをLINE Flex Message内のpostbackアクションとして提供する構成のため、course-set-pasha・kura-pashaと異なりLIFFアプリ登録自体は不要でありLIFF関連の記載漏れは該当しない。承認が得られれば、実APIキー・Webhookシークレットの設定、Stripe Webhookエンドポイント登録、LPドメイン確定・LP実装・公開から着手する。

日時: 2026-09-27 10:00 UTC
venture: ventures/aircon-pasha/
内容: 本venture自体の稼働に必須の前提である、LINE公式アカウントの開設(Messaging APIのチャネルアクセストークン・チャネルシークレット取得)、およびtrial_end_scheduler.py・payment_suspension_scheduler.py・payment_failure_reminder_scheduler.py等の日次バッチ用Cloud Scheduler(GCPプロジェクトの課金設定を伴う)の作成を行いたい。
理由: webhook-http-entry-point-design.mdは「実際のchannel_secretの値はLINE公式アカウント開設(アカウント作成、オーナー承認待ち)」、tech-stack.mdは「実際のCloud Scheduler実行環境の構築...もオーナー承認待ちとして残る」と、いずれも一貫してオーナー承認待ちの前提として記述してきたが、フェーズ278(2026-09-27 10:00 UTC定例更新)の棚卸しにより、course-set-pasha(2026-09-11 04:00 UTC記載)・kura-pasha(2026-09-15 03:00 UTC記載)が既に同種の承認依頼を個別に記録済みである一方、aircon-pasha自身についてはこの承認依頼自体がpending-approval.mdに一度も記録されていなかった記載漏れであることが判明したため、今回新規に記録した。既存のaircon-pasha関連3件(2026-08-21 12:00 UTC・2026-08-23 04:00 UTC・2026-09-27 09:00 UTC)はいずれも顧客ヒアリング連絡・Googleフォーム連携・Stripe/LP関連であり、本件(LINE公式アカウント開設・Cloud Scheduler作成)を対象としていない。承認が得られれば、実チャネルアクセストークン・チャネルシークレットの設定、Cloud Schedulerのデプロイ(各日次バッチのcron設定含む)から着手する。
