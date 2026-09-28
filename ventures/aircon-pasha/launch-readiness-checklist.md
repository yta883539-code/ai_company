# aircon-pasha 公開までのチェックリスト(フェーズ284時点)

目的: 設計・実装・テストは完了しているが、実際の稼働にはオーナー承認が必要な外部サービス
設定が複数残っている。オーナーがpending-approval.mdを一つずつ確認する際に迷わないよう、
本ventureに関わる承認待ち事項を依存順に並べ、承認後すぐ着手できる作業内容を1箇所にまとめる。
kura-pasha(フェーズ196)・line-reservation-ai(フェーズ続き286)と同型の整理を行う。

## 現状(実装・検証済み、追加作業不要)

- Checkout Sessionパラメータ組み立て(`build_checkout_session_params()`)・
  決済完了後のStripe側処理(checkout-session-completed-handling-design.md):
  プロトタイプ全体186件、いずれもパス。
- Stripe Webhook配信順序入れ替わりガード(`customer.subscription.deleted`分岐の
  5箇所の副作用: deletion_candidate・plan・blocked_but_billing・payment_failure・
  cancellation通知): フェーズ280〜283で対応完了。他venture(kura-pasha・
  course-set-pasha・line-reservation-ai)との横断確認も済み。
- user-account-linking-design.md(フェーズ107): 申込フォーム送信完了時の連携コード
  発行→LINE初回メッセージでのコード送信方式、連携コードの判定・解決ロジックは机上設計
  まで完了。
- 顧客ヒアリング候補研究: 独立系候補5件(候補1リノハンズ・候補3hello-osouji.com・
  候補7Clean Labo・候補10キキのおそうじ屋・候補12東京住まいる〈連絡先一次情報未確認〉)、
  フランチャイズ加盟候補3件(候補2篠崎昌則オーナー・候補13金井美樹オーナー・
  候補14濱暁洋オーナー)、initial-contact-message-draft.mdでの文面・台本作成まで完了。

## 承認待ち事項(依存順、pending-approval.md記載の要約)

1. **LINE公式アカウント開設 + Cloud Scheduler作成**(2026-09-27 10:00 UTC記載)
   Messaging APIチャネルアクセストークン・チャネルシークレット取得、
   trial_end_scheduler.py・payment_suspension_scheduler.py・
   payment_failure_reminder_scheduler.py等の日次バッチ用Cloud Scheduler
   (GCPプロジェクトの課金設定を伴う)作成。本venture自体の稼働に必須の前提。
   → 承認後: 実チャネルアクセストークン・チャネルシークレットの設定、
   Cloud Schedulerのデプロイ(各日次バッチのcron設定含む)から着手。

2. **Googleフォーム作成 + GAS Webhook実装・デプロイ**(2026-08-23 04:00 UTC記載)
   user-account-linking-design.md(フェーズ107)で設計した「申込フォーム送信完了時の
   連携コード発行→LINE初回メッセージでのコード送信」方式について、実際のGoogleフォーム
   作成・フォーム送信をトリガーとするGAS Webhookの実装・デプロイ。
   → 承認後: フォーム項目(屋号・事業形態・メールアドレス)作成、GAS Webhook
   スクリプト実装・デプロイ、連携コード発行処理の接続確認から着手。

3. **Stripeアカウント開設 + LP公開**(2026-09-27 09:00 UTC記載)
   本人確認・銀行口座登録、本番APIキー・Webhook署名シークレット取得、
   `success_url`/`cancel_url`が指すLP(ランディングページ)の実装・公開、
   Stripe側Webhookエンドポイント登録。本ventureは決済ボタンをLINE Flex Message内の
   postbackアクションとして提供する構成のため、course-set-pasha・kura-pashaと異なり
   LIFFアプリ登録は不要。
   → 承認後: 実キー・Webhookシークレット設定、Webhookエンドポイント登録、
   LPドメイン確定・LP実装・公開から着手。

4. **顧客ヒアリングの実施**(2026-08-21 12:00 UTC記載)
   独立系候補5件・フランチャイズ加盟候補3件への初回コンタクト・ヒアリング協力依頼
   (候補12は連絡先一次情報未確認のため承認後もまず残り7件から着手)。
   → 承認後: 電話・LINE等の実連絡はオーナー自身が行い、メール送信はGmail連携接続後に
   送信直前の毎回確認を経てのみ行う。

## 次回候補

上記1〜4のいずれかがオーナーから承認された場合、その着手を最優先とする。承認が
得られるまでの間は、他venture・アイデア領域の前進、または本チェックリストと
pending-approval.mdの記載に齟齬がないかの定期的な棚卸しを行う。
