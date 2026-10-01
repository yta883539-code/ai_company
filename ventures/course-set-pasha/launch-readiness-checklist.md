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

## 次回候補

上記1〜5のいずれかがオーナーから承認された場合、その着手を最優先とする。承認が
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
