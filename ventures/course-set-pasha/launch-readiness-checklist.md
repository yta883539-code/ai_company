# course-set-pasha 公開までのチェックリスト(フェーズ268時点、2026-09-29 11:00 UTC更新)

目的: 設計・実装・テストは完了しているが、実際の稼働にはオーナー承認が必要な外部サービス
設定が複数残っている。pending-approval.md中に本venture関連の記載が複数回・複数日に
分散しているため、オーナーが一つずつ確認する際に迷わないよう、依存順に並べ1箇所に
まとめる(kura-pasha・aircon-pasha・line-reservation-aiの同種チェックリストと同形式)。

## 現状(実装・検証済み、追加作業不要)

- Checkout Session発行ロジック・Stripe Webhook受信/署名検証/イベントディスパッチ・
  トライアル管理・決済失敗猶予・解約確定判定: InMemoryStubによるテスト682件・
  schema検証21件いずれもパス(2026-09-28時点)。
- Stripe Webhook配信順序入れ替わりガード(`subscription_status`・`plan`・決済失敗・
  `customer.subscription.updated`〈プラン更新/解約予約通知/reactivated状態クリア〉
  関連の各分岐): フェーズ263〜265、および`customer.subscription.updated`分岐を
  追加対応したフェーズ267まで完了。他venture(aircon-pasha・kura-pasha・
  line-reservation-ai)との横断確認も済み(2026-09-29時点で4venture全てに横展開完了)。
- LINEユーザー連携コード発行・解決ロジック(`prototype/user_id_linking.py`、
  友だち追加時にトークで届く6文字コード方式): 実装・テスト(11件)済み。
- 申込フォーム提出フローの正規化・書き込みロジック
  (`prototype/application_form_submission_flow.py`): テスト16件済み。
- LP実装ドラフト(`landing-page/index.html`、2026-10-02 01:00 UTC作成): aircon-pasha・
  line-reservation-aiと同じ位置づけで、landing-page-wireframe.md・landing-page-copy-draft.md
  の内容をHTML/CSSに落とし込んだローカル静的ファイル。ドメイン取得・ホスティング・公開は
  未着手(CTAは非活性プレースホルダー)。

## 承認待ち事項(依存順、pending-approval.md記載の要約)

1. **LINE公式アカウント開設**(2026-09-28 20:00 UTC記載、フェーズ266で独立エントリ
   として記録。従来は2026-08-18 20:00 UTC記載の申込フォーム案件内で前提として言及
   されるのみで、独立した承認依頼としての記録漏れがあった)
   Messaging APIチャネルアクセストークン取得。本venture稼働・LIFFアプリ登録双方の
   前提。
   → 承認後: チャネルアクセストークン設定から着手。

2. **Googleフォーム作成 + GAS Webhook設定**(2026-08-18 20:00 UTC記載、
   2026-08-20 21:00 UTCで仕様変更を申し送り済み)
   申込フォーム項目(ジム名・地域名・LINE友だち追加時の連携コード欄〈6文字、
   user_id手入力方式から変更済み〉)の作成、GAS Webhookスクリプトの実装・デプロイ、
   Cloud FunctionsエンドポイントへのPOST接続確認。
   → 承認後: フォーム項目作成・GAS Webhookデプロイ・接続確認から着手。

3. **LIFFアプリ登録 + Cloud Scheduler作成**(2026-08-23 09:00 UTC記載、
   2026-09-27 07:00 UTCで記載漏れ点検の結果として再確認)
   LINE DevelopersコンソールでのLIFFアプリ登録(本venture用LINE公式アカウントの
   チャネルに紐づけ)、無料トライアル終了判定用Cloud Scheduler(GCPプロジェクトの
   課金設定を伴う)の作成。
   → 承認後: stripe-liff-integration-sequence-design.md 5節の順序(LINE公式
   アカウント開設→LIFFアプリ登録→IDトークン検証実装)に沿って着手。

4. **Stripeアカウント開設**(2026-09-27 03:00 UTC記載)
   本人確認・銀行口座登録、本番APIキー・Webhook署名シークレット取得、実キー設定、
   Stripe側Webhookエンドポイント登録。
   → 承認後: 実APIキー・Webhookシークレット設定・Webhookエンドポイント登録から
   着手(LIFF経由IDトークン検証の実装と合わせた結合確認が必要)。

5. **顧客ヒアリングの実施**(2026-08-09 01:00 UTC記載)
   candidate-longlist-draft.mdで有力候補と確定した候補(FRICTION FREAKS等)への
   Instagram DM・メール・電話等での初回コンタクト。
   → 承認後: initial-contact-message-draft.mdの文面案を使い、Instagram DM・電話
   での実連絡はオーナー自身が行う、メール送信はGmail連携接続後に送信直前の毎回
   確認を経てのみ行う。

6. **GCPプロジェクト作成 + Firestoreデータベース新規作成**(2026-10-24 09:00 UTC記載。
   firestore-provider-adapter-design.mdが設計済みの`LinkingCodeStoreProtocol`・
   `UserProfileStoreProtocol`等の実デプロイ先)
   実GCPプロジェクトの作成(課金設定を含む)、Firestoreデータベースの新規作成。
   → 承認後: 実GCPプロジェクトの作成、Firestoreデータベースの新規作成、各Protocol
   アダプタの実コード化・結合実装から着手。

## 運用手順(オーナー数に応じたBilling Budget予算見直し、フェーズ380時点)

billing-budget-cap-safeguard-design.mdは、本venture想定のオーナー数(構造的に少数)を
踏まえ暫定予算額500円/月(50%・90%・100%到達時にオーナー宛メール通知)を採用した上で、
「セッター複数プランの上限(267.3円/オーナー)を使い切るオーナーが2件を超える規模に
なった場合は、オーナー確認の上で引き上げる」という申し送りを残していた。aircon-pasha
フェーズ387・388が同種の予算見直しプロセスを自venture側のlaunch-readiness-checklist.md
へ運用手順として明文化・反映済みであることを踏まえ、本venture側でも同様に運用手順として
明記する。

- セッター複数プラン利用オーナーのうち、月間生成回数が上限(月30回)に達した
  オーナー数が2件を超えた時点で、billing-budget-cap-safeguard-design.mdの想定に
  基づき予算額の見直し案(現行500円/月・新規提案額・増加理由)を算出し、オーナーへ
  見直し提案を提示する。
- 見直し提案自体は承認待ち事項1〜6と同様、実際のCloud Billing Budgets & alertsの
  設定変更を伴うためオーナー承認が必要なアクションであり、本エージェントが単独で
  予算額を変更することはない。
- 本運用手順は承認待ち事項1〜6(実LINE公式アカウント・Stripeアカウント・実GCP
  プロジェクト等の作成)が承認され、実際にBilling Budgetが作成された後にのみ適用
  される(セッター複数プラン利用オーナー数の実測自体が実Stripeアカウント接続を
  前提とするため)。

## 次回候補

上記1〜6のいずれかがオーナーから承認された場合、その着手を最優先とする。承認が
得られるまでの間は、他venture・アイデア領域の前進、または本チェックリストと
pending-approval.mdの記載に齟齬がないかの定期的な棚卸しを行う。

## 定期棚卸し記録

2026-09-29 11:00 UTC(フェーズ268): 上記1〜5の日時をpending-approval.mdの「日時」欄と
突き合わせたところ、5件とも1対1で対応しており記載漏れ・日時不一致は見つからなかった
(kura-pashaのlaunch-readiness-checklist.mdに記録済みの2026-09-29 01:00 UTC・4venture
横断棚卸しでも同様に確認済み)。あわせて「現状」節のStripe Webhookガード説明が
フェーズ267(`customer.subscription.updated`分岐へのガード追加)を反映していなかった
記載漏れを発見・是正した(コード変更は不要、説明文のみの更新)。回帰確認として
`python3 -m unittest discover -s prototype -p "test_*.py"`(690件)・`python3
schema/validate_test_cases.py`(21件)を再実行し、いずれもパスすることを確認した
(テスト件数はフェーズ267時点の685件から690件に増えているが、これは本フェーズ以前の
他作業によるものでありドキュメント記載漏れの是正自体にコード変更は伴わない)。承認が
必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していないため
pending-approval.mdへの追記なし。

2026-10-02 01:00 UTC: aircon-pasha・line-reservation-aiが直近2時間でLP実装ドラフト
(`landing-page/index.html`)を作成済みである一方、本ventureは未着手のまま残っていたことを
確認したため、本venture分のLP実装ドラフトを新規作成した(「現状」節参照)。ドメイン取得・
ホスティング・公開は未着手のままで、承認待ち事項1〜5の内容・件数に変更はない。回帰確認として
`python3 -m unittest discover -s prototype -p "test_*.py"`(690件)・`python3
schema/validate_test_cases.py`(21件)を再実行し、いずれもパスすることを確認した(コード変更
なし)。承認が必要なアクションは今回発生していないためpending-approval.mdへの追記なし。

2026-10-02 19:00 UTC(フェーズ272): 承認待ち事項1〜5をpending-approval.mdの該当エントリと
再度突き合わせ、記載漏れ・日時不一致なしを確認した。承認待ち事項1〜5の内容・件数に変更はない。
あわせてlanding-page-wireframe.mdの「最終更新」表記の記載漏れ(フェーズ270の内容追記が
未反映のまま)を発見・是正した(詳細は本venture README参照)。回帰確認として`python3
-m unittest discover -s prototype -p "test_*.py"`(690件)・`python3
schema/validate_test_cases.py`(21件)を再実行し、いずれもパスすることを確認した(コード変更
なし)。承認が必要なアクションは今回発生していないためpending-approval.mdへの追記なし。

2026-10-11 16:00 UTC(フェーズ288): 承認待ち事項1〜5をpending-approval.mdの該当エントリ
(LINE公式アカウント開設=2026-09-28 20:00 UTC記載、Googleフォーム+GAS Webhook=2026-08-18
20:00 UTC記載、LIFFアプリ登録+Cloud Scheduler=2026-08-23 09:00 UTC記載〈2026-09-27 07:00
UTCで記載漏れ点検済み〉、Stripeアカウント開設=2026-09-27 03:00 UTC記載、顧客ヒアリング=
2026-08-09 01:00 UTC記載)と再度1対1で突き合わせ、5件とも記載漏れ・日時不一致なしを確認した。
承認待ち事項1〜5の内容・件数に変更はない。回帰確認として`python3 -m unittest discover -s
prototype -p "test_*.py"`(692件)・`python3 schema/validate_test_cases.py`(21件)を再実行し、
いずれもパスすることを確認した(コード変更なし)。承認が必要なアクション(支払い・アカウント
作成・外部公開・送信等)は今回発生していないためpending-approval.mdへの追記なし。次回候補:
(1)承認待ち事項1〜5がオーナーから承認された場合はその着手を最優先、(2)他venture・アイデア
領域の前進。

2026-10-13 23:00 UTC(フェーズ295): 本棚卸しの一環でapplication-form-submission-flow-
design.mdを再読した結果、承認待ち事項2(Googleフォーム作成+GAS Webhook設定)の対象である
GAS Webhookから実際に呼び出すCloud Functions側のHTTPエントリポイント自体が未設計のまま
放置されていたことを発見し、application-form-submission-http-entry-point-design.mdとして
新規設計・実装した(詳細は本venture README参照)。承認待ち事項1〜5の内容・件数に変更は
ない(本件は承認待ち事項2の範囲内の設計・コード草案であり、新たな承認待ち事項を追加する
ものではない)。回帰確認として`python3 -m unittest discover -s prototype -p "test_*.py"`
(756件)・`python3 schema/validate_test_cases.py`(21件)を再実行し、いずれもパスすることを
確認した。承認が必要なアクションは今回発生していないためpending-approval.mdへの追記なし。

2026-11-03 01:00 UTC(フェーズ348): 本棚卸しの一環でpending-approval.md全体を本venture名
(course-set-pasha)で再検索した結果、2026-10-24 09:00 UTC記載の「GCPプロジェクト作成+
Firestoreデータベース新規作成」(line-reservation-ai・kura-pasha・aircon-pasha・
forklift-pashaで発見された同種の記載漏れの棚卸しを受けて同日中に本venture側で記録済み)が、
承認待ち事項1〜5のリストに反映されないまま本チェックリストから漏れていたことを発見した。
承認待ち事項6として追加し是正した(内容は「現状」節参照、firestore-provider-adapter-design.md
が設計済みの各Protocolアダプタの実デプロイ先)。コード変更なし、回帰確認として`python3 -m
unittest discover -s prototype -p "test_*.py"`(863件、変更なし)・`python3
schema/validate_test_cases.py`(21件、変更なし)を実行しいずれもパスすることを確認した
(回帰なし)。承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生
していないためpending-approval.mdへの追記なし(既存エントリの反映漏れの是正のみ)。
次回候補: (1)承認待ち事項1〜6がオーナーから承認された場合はその着手を最優先、(2)他venture・
アイデア領域の前進。

2026-11-17 08:00 UTC(フェーズ385): subscription-updated-event-order-guard-design.mdが
次回候補として残していた「launch-readiness-checklist.mdとpending-approval.mdの記載齟齬の
定期棚卸し」に対応。フェーズ348(2026-11-03 01:00 UTC)以来初めての再棚卸しとして、
承認待ち事項1〜6をpending-approval.mdの該当エントリ(LINE公式アカウント開設=2026-09-28
20:00 UTC、Googleフォーム+GAS Webhook=2026-08-18 20:00 UTC、LIFFアプリ登録+Cloud
Scheduler作成=2026-08-23 09:00 UTC、Stripeアカウント開設=2026-09-27 03:00 UTC、顧客
ヒアリング=2026-08-09 01:00 UTC、GCPプロジェクト作成+Firestoreデータベース新規作成=
2026-10-24 09:00 UTC)と1対1で再度突き合わせ、6件とも記載漏れ・日時不一致なしを確認した。
pending-approval.md全体を「course-set-pasha」で再検索した結果も該当8エントリ(上記6件+
仕様変更申し送り〈2026-08-20 21:00 UTC〉・LIFF記載漏れ点検〈2026-09-27 07:00 UTC〉の2件の
補足エントリ)のみで、フェーズ348以降に新規追加されたcourse-set-pasha個別の承認待ち事項は
無いことを確認した。承認待ち事項1〜6の内容・件数に変更はない。コード変更なし、回帰確認として
`python3 -m unittest discover -s prototype -p "test_*.py"`(910件、変更なし)・`python3
schema/validate_test_cases.py`(22件、変更なし)を実行しいずれも変更なしでパスすることを
確認した(回帰なし)。実LINE/Stripe/GCP API接続・支払い・アカウント作成・外部公開・送信は
一切行っていない。承認が必要なアクションは今回発生していないためpending-approval.mdへの
追記なし。
次回候補: (1)承認待ち事項1〜6がオーナーから承認された場合はその着手を最優先、(2)他venture・
アイデア領域の前進、(3)本棚卸しは今回齟齬なしだったため、次回以降は概ね1〜2週間間隔での
実施で十分と考えられる。

2026-11-27 20:00 UTC(フェーズ411): フェーズ385の申し送り(1〜2週間間隔での再棚卸し)に
従い、フェーズ385(2026-11-17 08:00 UTC)から約10日経過した時点で再棚卸しを実施した。
承認待ち事項1〜6の日時アンカー(2026-08-09 01:00 UTC・2026-08-18 20:00 UTC・2026-08-23
09:00 UTC・2026-09-27 03:00 UTC・2026-09-28 20:00 UTC・2026-10-24 09:00 UTC)をそれぞれ
pending-approval.md内で検索し、6件全てが`venture: ventures/course-set-pasha/`として
現存し、内容・件数に変更がないことを確認した(削除・改変なし)。承認待ち事項1〜6の内容・
件数に変更はない。コード変更なし、回帰確認として`python3 -I -m unittest discover -s
prototype -p "test_*.py"`(933件、変更なし)・`python3 -I schema/validate_test_cases.py`
(22件、変更なし)を実行しいずれもパスすることを確認した(回帰なし)。実LLM/LINE/Stripe/GCP
API接続・支払い・アカウント作成・外部公開・送信は一切行っていない。承認が必要なアクション
は今回発生していないためpending-approval.mdへの追記なし。
次回候補: (1)承認待ち事項1〜6がオーナーから承認された場合はその着手を最優先、(2)他venture・
アイデア領域の前進、(3)次回の本棚卸しは概ね1〜2週間後(2026年12月上旬目安)を目安とする。
