# kura-pasha 公開までのチェックリスト(フェーズ196時点)

目的: 設計・実装・テストは完了しているが、実際の稼働にはオーナー承認が必要な外部サービス
設定が複数残っている。オーナーがpending-approval.mdを一つずつ確認する際に迷わないよう、
本ventureに関わる承認待ち事項を依存順に並べ、承認後すぐ着手できる作業内容を1箇所にまとめる。

## 現状(実装・検証済み、追加作業不要)

- Checkout Session発行ロジック・Stripe Webhook受信/署名検証/イベントディスパッチ:
  InMemoryStubによるテスト171件・schema検証32件いずれもパス(2026-09-28時点)。
- Stripe Webhook配信順序入れ替わりガード(`subscription_status`等の各分岐):
  フェーズ192〜195で対応完了。他venture(aircon-pasha・course-set-pasha・
  line-reservation-ai)との横断確認も済み。
- 日次バッチ(`run_daily_workshop_checks()`、トライアル30日到達報告・決済失敗3日前
  リマインド・制限モード移行時のオーナー通知): ロジック・送信判定・通知文言はProtocol
  経由の依存注入・InMemoryStubテスト(フェーズ120、8件)まで完了。
- 顧客ヒアリング候補選定・優先順位付け(候補1 ライディングショップ池上・候補2
  エクウスワールド)・連絡文面ドラフト(文面案A/B)・リハーサル台本: フェーズ7〜16で
  作成済み。

## 承認待ち事項(依存順、pending-approval.md記載の要約)

1. **Stripeアカウント開設**(2026-09-27 08:00 UTC記載)
   本人確認・銀行口座登録、本番APIキー・Webhook署名シークレット取得、
   `plan_id`→Stripe Price ID対応表・`success_url`/`cancel_url`の確定、
   Stripe側Webhookエンドポイント登録。
   → 承認後: 実キー設定・Webhookエンドポイント登録・Price ID対応表確定から着手。
   (本ventureはLINE Platform Webhook受信時点で検証済みの`event.source.userId`を
   使う設計のため、LIFFアプリ登録は不要。)

2. **LINE公式アカウント開設 + Cloud Scheduler作成**(2026-09-15 03:00 UTC記載)
   Messaging APIチャネルアクセストークン取得、日次1回(暫定JST 04:00)起動の
   Cloud Scheduler(GCPプロジェクトの課金設定を伴う)作成、オーナー向け通知送信先
   LINEユーザーID(`OWNER_LINE_USER_ID_PLACEHOLDER`)の設定。
   → 承認後: チャネルアクセストークン設定・Cloud Schedulerデプロイ・
   オーナーLINEユーザーID設定から着手。

3. **顧客ヒアリングの実施**(2026-09-11 04:00 UTC記載)
   候補1(ライディングショップ池上)・候補2(エクウスワールド)への初回コンタクト。
   → 承認後: 文面案A(メール・問い合わせフォーム用)・文面案B(電話トーク要点)を
   使い、電話での実連絡・メールフォーム送信文面の最終確定はオーナー自身が行うか、
   Gmail連携接続後に送信直前の毎回確認を経てのみ行う。

## 次回候補

上記1〜3のいずれかがオーナーから承認された場合、その着手を最優先とする。承認が
得られるまでの間は、他venture・アイデア領域の前進、または本チェックリストと
pending-approval.mdの記載に齟齬がないかの定期的な棚卸しを行う。

## 定期棚卸し記録

2026-09-29 01:00 UTC: 4venture(kura-pasha・aircon-pasha・course-set-pasha・
line-reservation-ai)すべてのlaunch-readiness-checklist.md記載の承認待ち事項の日時
(計19件)をpending-approval.mdの「日時」「venture」欄と突き合わせたところ、全件が
1対1で対応しており記載漏れ・日時不一致は見つからなかった(aircon-pashaフェーズ278・
course-set-pasha 2026-09-28 20:00 UTC記載で過去に発見された記載漏れはいずれも是正済み
であることを確認)。またkura-pasha自身のStripe Webhook配信順序入れ替わりガード
(subscription-status-event-order-guard-design.md、フェーズ194)・line-reservation-ai
の同種ガード(subscription-event-order-guard-design.md・payment-failure-detected-at-
event-order-guard-design.md)・deployment-runbook.mdについても4venture間の横展開状況を
確認し、いずれも横展開済み・記載済みで新たな欠落は見つからなかった。

2026-10-01 19:00 UTC: 本チェックリスト「承認待ち事項」節に記載のkura-pasha自身の3件
(1. Stripeアカウント開設〈2026-09-27 08:00 UTC記載〉、2. LINE公式アカウント開設+
Cloud Scheduler作成〈2026-09-15 03:00 UTC記載〉、3. 顧客ヒアリングの実施〈2026-09-11
04:00 UTC記載〉)について、pending-approval.md本文と日時・内容を再度突き合わせたところ、
3件とも1対1で対応し記載漏れ・内容の齟齬は見つからなかった。いずれもオーナー承認が
得られておらず着手可能な新規作業がないため、本サイクルはkura-pasha側のコード変更・
設計追加は行わず、棚卸し記録の更新のみとした。回帰確認として`python3
prototype/run_all_tests.py`(16ファイルOK)・`python3 schema/validate_test_cases.py`
(32件)を再実行し、いずれもパスすることを確認した。承認が必要なアクション(支払い・
アカウント作成・外部公開・送信等)は今回発生していないためpending-approval.mdへの
追記なし。次回候補: 他venture・アイデア領域の前進、またはオーナーからの承認・回答を
待つ。
