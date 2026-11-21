# forklift-pasha 公開までのチェックリスト(フェーズ94時点)

目的: aircon-pasha・course-set-pasha・kura-pasha・line-reservation-aiの4ventureは
launch-readiness-checklist.mdで承認待ち事項を依存順に一覧化済みだが、本venture
(forklift-pasha)は候補発見・リハーサル設計が中心でまだ同種のチェックリストを
持っていなかった。フェーズ33〜69で間接チャネル(建荷協・都道府県労働局)への
提案文面・送付先候補の準備がほぼ尽くされ、フェーズ88〜91でヒアリングリハーサル
台本の整備も一区切りついた現時点で、承認待ち事項と現状の棚卸しを1箇所にまとめる。

## 現状(設計・検証済み、追加作業不要)

- 市場調査・料金プラン・技術構成(market-research.md・pricing-plan.md・
  tech-stack.md): 作成済み。
- プロトタイプ・テスト: `python3 prototype/run_all_tests.py`(4ファイルOK)・
  `python3 schema/validate_test_cases.py`(11件)・
  `node prototype/browser_mockup_checks.js`(17件)いずれもパス(2026-10-06時点で
  再確認済み)。
- Webフォームモックアップ(web-form-mockup/、daily.html・monthly.html、
  CSS:has()による出し分け方式): 実装済み。
- 間接チャネル探索・提案文面(channel-partner-exploration.md・
  kenkakyo-proposal-draft.md・branch-outreach-priority-ranking.md・
  branch-outreach-individual-drafts.md): 建荷協本部・地方支部(Aランク7支部:
  群馬・山梨・広島・栃木・兵庫・茨城・福岡)・都道府県労働局(千葉・岐阜で
  部署名確認済み)向けの個別提案文面下書きがフェーズ65・67までに揃い、
  フェーズ69で「WebSearchで到達可能な範囲ではほぼ尽くした」と結論済み。
- ヒアリング設計・リハーサル(customer-interview-design.md・
  interview-candidate-selection-criteria.md・interview-rehearsal-script.md・
  rehearsal-timing-desk-estimate.md・mock-interview-responses-draft.md):
  仮想の想定回答者に基づく机上リハーサル・ストレステストまで完了(フェーズ88〜91)。
  実在候補が未確定のため、実際の社内リハーサル(実時間計測)・実在候補への実施は
  いずれも次段階。
- 特商法表記・プライバシーポリシー草案(legal-notices-draft.md): 他venture対比で
  未着手だったcross-venture parityギャップを解消し、フェーズ94で新規作成(【要記入】
  箇所あり、実際のLP公開は別途オーナー承認が必要)。フェーズ100でannual区分(特定自主
  検査)の法定保存義務(安衛則上3年)との整合を整理し、data-retention-policy.mdを
  新規作成した(下記参照)。
- 個人情報・記録の保存期間・削除方針(data-retention-policy.md): フェーズ100で新規作成。
  点検記録原本はサーバー側に保存しない設計を維持し、annual区分の3年法定保存義務は
  利用事業者自身が負う旨を利用規約・画面表示上で明示する方針とした。`fleet_operator`等の
  契約情報はStripe解約日から1年保有後に削除候補化する(他venture共通の方針)。
- 決済時の本人確認方式(payment-identity-verification-design.md): LINE非依存のため
  LIFF経由IDトークン検証が使えない本venture固有の課題として、フェーズ95でアクセス
  トークン方式を設計(operator_idをランダム発行方式に確定、firestore-data-model.md
  も合わせて更新)。フェーズ96でドキュメントID(internal_id)とアクセストークンを分離し
  (access-token-reissue-design.md)、フェーズ97で実ファイルに反映、フェーズ98で
  `accessToken`の有効期限方針を無期限に確定した。

## 承認待ち事項(pending-approval.md記載の要約)

1. **建荷協(本部・Aランク7支部)・都道府県労働局(千葉・岐阜)への電話・メール連絡**
   (2026-10-05 21:00 UTC記載)
   kenkakyo-proposal-draft.md・branch-outreach-individual-drafts.mdで下書き済みの
   提案文面(提案パスA: 会員向け付加サービス提案/パスB: 広報チャネル活用提案/
   パスC: 都道府県労働局向け)を用いた実際の対外連絡。
   → 承認後: 電話連絡はオーナー自身が行い、メール送信はメール連携接続後に
   送信直前の毎回確認を経てのみ行う(line-reservation-ai等の既承認案件と
   同じ運用)。
   **時期的な緊急性**: kenkakyo-proposal-draft.mdフェーズ47・53(2026-10-04〜05)の
   調査により、提案パスB・Cが紹介機会として想定する「特定自主検査強調月間」
   (毎年11月、2026年版スローガン「災害の 危険の芽を摘む 特自検」制定済み)の
   開始まで、本日(2026-10-06)時点で残り約25日。フェーズ53では「月間開始前
   (10月頃)の接触が望ましい」との仮説も記録済みであり、承認・電話連絡・
   建荷協側の月間準備(例年10月下旬〜11月上旬に労働局通達)のリードタイムを
   踏まえると、10月中の承認が得られないと今年度の月間に合わせた紹介機会を
   逃す可能性がある。
   **フェーズ253時点の追記(2026-11-21 15:00 UTC)**: 本日時点で「特定自主検査強調月間」
   (2026年11月)はほぼ終了しており、承認が未回答のまま経過したため、上記で想定していた
   2026年版月間への紹介機会は実質的に逃したと判断する。承認待ち自体は取り下げず、次の
   機会は2027年11月の月間(例年10月下旬〜11月上旬に労働局通達される見込み)となる。
   承認が2027年9月〜10月頃までに得られれば、建荷協側の月間準備リードタイムに間に合う
   見込みである。

2. **Stripeアカウントの開設**(2026-10-06 22:00 UTC記載)
   本venture稼働に必須の実際のStripeアカウント開設(本人確認・銀行口座登録を含む)・
   本番用APIキー・Webhook署名シークレットの取得・`plan_id`→Price ID対応表確定・
   Webhookエンドポイント登録。他venture(course-set-pasha・kura-pasha・aircon-pasha)で
   発見された同種の記載漏れ(フェーズ94でlegal-notices-draft.md作成時に本venture側の
   記載漏れも発見・是正)。
   → 承認後: 実APIキー・Webhookシークレットの設定、plan_id→Price ID対応表の確定から
   着手する。なお本ventureはLINE非依存のWebフォームであり、LIFF経由IDトークン検証は
   前提としないため、決済時の本人確認方式は別途検討が必要だったが、フェーズ95で
   payment-identity-verification-design.md(アクセストークン方式)として設計済み。

3. **トライアル終了通知用Cloud Schedulerの作成・メール送信**(2026-10-10 18:00 UTC記載)
   trial-end-notification-design.md(フェーズ119)で設計したトライアル終了通知
   (無料トライアルの生成回数5回到達、または初回生成から30日経過のいずれか早い方で
   1回送信)の(B)期間到達経路に必要な日次バッチ用Cloud Scheduler(GCPプロジェクトの
   課金設定を伴う)の作成、および対象事業者のメールアドレス宛への実際のメール送信
   (送信手段・送信元ドメインの確定を含む)。
   → 承認後: Cloud Schedulerのデプロイ(日次1回の対象者抽出バッチ)、メール送信手段
   (SMTP/メールAPI)の選定から着手する。メール送信はGmail等の連携接続後、送信直前に
   毎回オーナーの確認を得てからのみ行う(line-reservation-ai等の既承認案件と同じ運用)。

4. **実GCPプロジェクトの作成・Firestoreデータベースの新規作成**(2026-10-24 07:00 UTC記載)
   本venture稼働に必須の実際のGCPプロジェクトの作成(課金設定を含む)、および
   Firestoreデータベースの新規作成(本番用の`FleetOperatorStoreProtocol`
   〈全15メソッド、フェーズ184時点で実コード化完了〉・`AccessTokenStoreProtocol`等、
   firestore-composite-index-plan.md・fleet-operator-store-upgraded-canceled-
   firestore-adapter-design.md等で設計済みの各Firestoreアダプタの実コレクション・
   ドキュメント構造のデプロイ先)。本venture側の実コード化自体はフェーズ184までに
   完了済みで、残るのは外部サービス側の作成・課金設定のみ。
   → 承認後: 実GCPプロジェクトの作成、Firestoreデータベースの新規作成、
   `google-cloud-firestore`ライブラリへの切り替え・`FORKLIFT_PASHA_FIRESTORE_ENABLED`
   フラグの結線、`firestore.indexes.json`の実デプロイから着手する。

本ventureは他4ventureと異なり、LINE公式アカウントの開設は入力チャネルがLINE非依存の
汎用Webフォーム(tech-stack.mdフェーズ70暫定決定)であるため不要と見込まれる。
pending-approval.md記載の本venture宛エントリは上記4件で、他venture側の棚卸しで
度々発見されてきた「記載漏れ」は本チェックリスト自体の反映漏れ(上記3・4が未反映)
として存在していたが、本フェーズでこれを是正した。

## 運用手順(契約台数事業者数に応じたBilling Budget予算見直し、フェーズ241時点)

aircon-pasha(フェーズ387・388)・course-set-pasha・kura-pasha(フェーズ続き309)が
横展開してきた「契約数に応じたBilling Budget予算見直し運用手順」を、kura-pashaフェーズ
続き309の次回候補(1)「残る横展開先(forklift-pasha・oshien-pasha)は複数職人/契約業者数の
数値閾値が未確定のため、閾値確定後に同種の運用手順反映が必要」を受けて本venture側に反映する。
billing-budget-cap-safeguard-design.md(1節)の算出式は、複数台プラン(10台まで・月220回まで)
契約事業者1件あたりの月間LLM原価上限を約598.4円(キャッシュなし)とし、この契約事業者数が
5件程度稼働しても閾値(月間3,000円)に達しない水準として暫定予算額を設定したことを踏まえ、
数値閾値を以下の通り確定する。

- 契約事業者数(Stripeの有効サブスクリプション件数のうち複数台プラン契約分)が4件
  (想定上限5件の8割)に達した時点で、billing-budget-cap-safeguard-design.md 1節の算出式
  (契約事業者数×複数台プラン原価約598.4円×安全マージン相当)に基づき予算額の見直し案を
  算出し、オーナーへ見直し提案(現行予算額・新規提案額・増加理由)を提示する。
- 見直し提案自体は承認待ち事項1〜4と同様、実際のCloud Billing Budgets & alertsの設定変更を
  伴うためオーナー承認が必要なアクションであり、本エージェントが単独で予算額を変更することは
  ない。
- 本運用手順は承認待ち事項2・4(Stripeアカウント・実GCPプロジェクト等の作成)が承認され、
  実際にBilling Budgetが作成された後にのみ適用される(契約事業者数の実測自体が実Stripe
  アカウント接続を前提とするため)。

残る横展開先はoshien-pashaのみ(oshien-pasha側で契約数の数値閾値が確定した時点で反映)。
[解消済み(フェーズ244、2026-11-17 03:00 UTC)] oshien-pasha側はフェーズ133
(2026-11-16 08:00 UTC、本記載の確定〈フェーズ241、同日07:00 UTC〉の約1時間後)で
月額フリーパス会員数を根拠に数値閾値(会員数8人、想定上限10人の8割)を確定し運用手順を
反映済みであることを確認した。これにより7venture全ての横展開が完了している
(oshien-pasha/README.mdフェーズ133参照)。

## 次回候補

上記1〜4のいずれかがオーナーから承認された場合、その着手を最優先とする。上記1は
時期的な緊急性があったが、フェーズ188時点で今年度(2026年)の「特定自主検査強調月間」
(11月)に合わせた紹介機会での活用は実質的に困難と判断済み(campaign-window-approval-
contingency.md参照、承認待ち事項自体は取り下げない)。承認が得られるまでの間は、
他venture・アイデア領域の前進を行う。
(access-token-reissue-design.mdフェーズ98が次回候補とした`lastAccessedAt`表示の実装
検討は、フェーズ99でfirestore-data-model.mdへのフィールド追加・更新タイミング・表示方法
の確定まで完了した。)

最終更新: 2026-10-06 22:00 UTC(フェーズ94: 他venture対比で未着手だった
legal-notices-draft.mdを新規作成し、その過程で発見したStripeアカウント開設の
記載漏れを承認待ち事項2として追加した。コード変更なし、テスト4ファイル・
schema検証11件・ブラウザ検証17件いずれもパス)
最終更新: 2026-10-06 23:00 UTC(フェーズ95: 次回候補(3)だった決済時の本人確認方式
〈LIFF非依存〉をpayment-identity-verification-design.mdとして設計し、アクセス
トークン方式に確定。firestore-data-model.mdのoperator_id割り振り方針も合わせて
更新した。コード変更なし、テスト4ファイル・schema検証11件・ブラウザ検証17件
いずれもパス)
最終更新: 2026-10-07 03:00 UTC(フェーズ98: payment-identity-verification-design.md
〈フェーズ95〉の残課題だった`accessToken`有効期限方針を無期限に確定し、
access-token-reissue-design.md「5.」に決定理由を記録。副作用として
`lastAccessedAt`表示案を次回候補に追加した。コード変更なし、テスト4ファイル・
schema検証11件・ブラウザ検証17件いずれもパス)
最終更新: 2026-10-07 04:00 UTC(フェーズ99: フェーズ98次回候補だった`lastAccessedAt`
〈最終アクセス日時〉を、firestore-data-model.mdの`fleet_operator`にフィールド追加し、
access-token-reissue-design.md「6.」に更新タイミング〈設定ページアクセス時のみ〉・
表示方法〈前回アクセス時点の値を表示〉を設計した。コード変更なし、テスト4ファイル・
schema検証11件・ブラウザ検証17件いずれもパス)
最終更新: 2026-10-07 05:00 UTC(フェーズ100: legal-notices-draft.md次回候補(1)(2)だった
annual区分の法定保存義務との整合確認・data-retention-policy.mdの切り出しに対応した。
WebSearchで安衛則第151条の23・第169条等によるフォークリフト特定自主検査記録の3年保存
義務を確認し、本サービスは記録原本を保存しない設計を維持したまま利用事業者自身に3年
保存義務がある旨を利用規約・画面表示上で明示する方針とした。コード変更なし、テスト
4ファイル・schema検証11件・ブラウザ検証17件いずれもパス。なお本フェーズの内容はREADME.md
への反映が漏れていたことをフェーズ101で発見し、遡って追記した)
最終更新: 2026-10-07 06:00 UTC(フェーズ101: access-token-reissue-design.md 2節・6節
〈アクセスURL再発行・前回のアクセス日時表示〉を、web-form-mockup/settings.htmlとして
新規に画面モックアップ化した。index.htmlへのリンク追加、browser_mockup_checks.jsへの
checkSettings()4件追加を行った。あわせてREADME.mdのフェーズ100記載漏れを是正した。
コード変更あり(新規モックアップ・テスト追加)、テスト4ファイル・schema検証11件・
ブラウザ検証21件(+4)いずれもパス。承認が必要なアクションは今回発生していないため
pending-approval.mdへの追記なし)
最終更新: 2026-10-07 23:00 UTC(フェーズ105: 上記承認待ち事項1の提案文面一式(提案パス
A・B・C〈千葉・岐阜分〉・Aランク7支部個別提案文面)について、送信承認が得られた場合に
追加作業なしで即着手できる状態にあるかを棚卸しし、いずれも送信可能な状態にあることを
確認した(branch-outreach-priority-ranking.mdフェーズ105参照)。**時期的な緊急性の更新**:
フェーズ94時点(2026-10-06)で「月間開始まで残り約25日」としていたが、本日(2026-10-07)
時点では残り約24日であり、承認待ちのまま時間が経過している。10月中の承認が得られないと
今年度の「特定自主検査強調月間」(11月)に合わせた紹介機会を逃す可能性がある点は変わらず、
むしろ送信物が完全に準備済みであるだけに承認待ちであること自体がボトルネックになっている
状態である。コード変更なし、テスト4ファイル・schema検証11件いずれもパス)
最終更新: 2026-10-13 01:00 UTC(フェーズ148: 月間開始〈11/1想定〉まで残り約19日に
迫ったことを受け、WebSearchで11月以外の代替月間の有無を確認(見つからず)、月間を
逃した場合の通年提案への転用・2027年向け再提案のコンティンジェンシープランを
campaign-window-approval-contingency.mdとして新規文書化した。10/25前後になっても
承認が得られない場合は「今年度は困難」の判断切り替え期限を本ファイルに追記する
想定とした)
最終更新: 2026-10-25 04:00 UTC(フェーズ188: フェーズ148で定めた「今年度は困難」判断
切り替え期限の目安(10/25前後)が本日到来したことを受け棚卸しした結果、承認待ち事項1
(2026-10-05 21:00 UTC記載、建荷協・都道府県労働局への対外連絡)はpending-approval.md
上も依然未承認のまま。「特定自主検査強調月間」(11月)開始まで残り約7日であり、承認・
対外連絡・建荷協側の月間準備(例年10月下旬〜11月上旬に労働局通達)のリードタイムを
踏まえると、今年度(2026年)の月間に合わせた紹介機会での活用は実質的に困難と判断し、
ここに記録する。ただし承認待ち事項1自体は取り下げない。承認が得られ次第、
campaign-window-approval-contingency.md 1.が示す通年提案(「強調月間に合わせて」の
導入部分を「特定自主検査の実施率向上は通年の課題」に差し替え)への切り替えを経て
随時着手できる状態を維持する。次の月間機会は2027年11月であり、同2.が示す2027年
8月下旬〜9月頃のリードタイム確保に向けた再提案準備を次回候補とする。承認待ち事項2
(Stripeアカウント開設)は本判断の対象外で引き続き未承認のまま。コード変更なし、
確認・文書記録のみ。承認が必要なアクションは今回発生していないためpending-
approval.mdへの追記なし)
最終更新: 2026-10-30 08:00 UTC(フェーズ198: kura-pashaフェーズ271が自venture側で発見
した「launch-readiness-checklist.mdの承認待ち事項節とpending-approval.md本文の
突き合わせ漏れ」と同種の棚卸しを本venture側でも実施した結果、本チェックリストが
pending-approval.md記載の本venture宛4件のうち2件(2026-10-10 18:00 UTC記載のトライアル
終了通知用Cloud Scheduler作成・メール送信、2026-10-24 07:00 UTC記載の実GCPプロジェクト・
Firestoreデータベース新規作成)を反映していなかったことを発見した。pending-approval.md
側は正しく記録済みであり、実行済みアクションは一切ない。上記承認待ち事項節に項目3・4として
新規追記し是正した。コード変更なし、回帰確認として`python3 -m unittest discover -s
prototype -p "test_*.py"`(93件、変更なし)・`python3 schema/validate_test_cases.py`
(11件、変更なし)を実行しいずれもパスすることを確認した(回帰なし)。承認が必要な
アクション(支払い・アカウント作成・外部公開・送信等)は今回発生していないため
pending-approval.mdへの追記なし)
最終更新: 2026-11-16 07:00 UTC(フェーズ241: kura-pashaフェーズ続き309の次回候補(1)を
受け、本venture〈forklift-pasha〉に契約事業者数に応じたBilling Budget予算見直し運用手順を
反映した(数値閾値: 複数台プラン契約事業者数4件〈想定上限5件の8割〉)。残る横展開先は
oshien-pashaのみ。コード変更なし(運用手順docのみ)、既存テスト117件(`python3 -m unittest
discover -s prototype -p "test_*.py"`)・schema検証11件(`python3
schema/validate_test_cases.py`)いずれも変更なしでパス(回帰なし)。実LINE/Stripe/GCP API
接続・支払い・アカウント作成・外部公開・送信は一切行っていない。承認が必要なアクションは
今回発生していないためpending-approval.mdへの追記なし)
