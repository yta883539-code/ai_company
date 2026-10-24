# 外部ベンダー侵害発覚時の自社キー緊急ローテーション手順(設計)

## 1. 背景

ノーコードWeb制作サービス「Studio」(Studio株式会社)の2026年10月不正アクセス事案(対象に
個人情報だけでなく外部サービス連携用の**APIキー・復号鍵**が含まれた)を踏まえ、kura-pasha
フェーズ262(2026-10-24 10:00 UTC)が、本venture群が共通して依存する外部サービスのキー・
シークレットが侵害対象に含まれた場合の緊急ローテーション手順を先行して設計する
vendor-breach-key-rotation-runbook.mdをkura-pasha自身について新規作成し、「他venture
(aircon-pasha・course-set-pasha・forklift-pasha・line-reservation-ai・
event-komiguai-pasha)も同種の外部キー依存構造を持つため、本設計の横展開は次回候補として
残す」と申し送っていた。本フェーズはこれを受け、aircon-pasha側に同種のランブックを作成する
(course-set-pashaフェーズ329〈2026-10-24 19:00 UTC〉・line-reservation-aiフェーズ続き341
〈2026-10-24 17:00 UTC〉に続く3件目の横展開)。

本venture自体が不正アクセス・キー漏えいを受けた事実はない。

## 2. aircon-pashaが保有する外部連携キー・シークレットの一覧

tech-stack.md(コンポーネント1〜5)の構成を前提に、本venture固有の依存先を整理する。

| 依存先 | 保有するシークレット | 用途 |
| --- | --- | --- |
| LINE Messaging API | チャネルアクセストークン・チャネルシークレット | Webhook署名検証・返信送信(コンポーネント1) |
| Stripe | シークレットキー(`sk_live_...`)・Webhook署名シークレット(`whsec_...`) | Checkout Session発行・Webhook受信(stripe-webhook-http-entry-point-design.md・stripe-webhook-signature-verification-design.md) |
| LLM APIプロバイダ | APIキー | 3出力生成(コンポーネント3) |
| GCP(Cloud Run functions・Firestore) | サービスアカウント鍵・Secret Managerアクセス権 | Webhook実行環境・月間生成回数カウント用usage_counter・user_profile等のデータストア接続(コンポーネント2・5) |

kura-pashaの一覧と同じ4種だが、本venture固有の違いとして、決済ボタンをLINE Flex Message内の
postbackアクションとして提供する構成(checkout-initiation-flow-design.md 1節)のため
LIFFアプリ自体は使用せず、LIFFアプリIDに紐づくシークレットは本venture固有の論点としては
存在しない(course-set-pasha・kura-pashaはLIFF経由IDトークン検証を採用するため対象となるが、
aircon-pashaは対象外)。

いずれも実アカウント開設自体がオーナー承認待ち(pending-approval.md参照、aircon-pasha関連の
LINE公式アカウント開設+Cloud Scheduler作成〈2026-09-27 10:00 UTC記載〉・Stripeアカウント
開設〈2026-09-27 09:00 UTC記載〉・Firestoreデータベース作成〈2026-10-24 02:00 UTC記載分の
是正により記録済み〉)のため、現時点では上記は「開設後に保有することになる」想定の一覧である。

## 3. 緊急ローテーション手順(ドラフト)

kura-pashaフェーズ262の5段階手順を踏襲する(ベンダー構成が同一のため、手順自体の変更は不要)。

1. **検知**: 上記いずれかのベンダー(またはそのベンダーがさらに利用する委託先)が不正
   アクセス・情報漏えいを公表し、自社が保有するAPIキー・シークレットが対象に含まれる
   可能性があるとの連絡・報道を確認した時点を起点とする。
2. **一次切断**: 対象ベンダーの管理画面から影響範囲が確定する前に、該当するキー・
   シークレットを予防的に失効させ、新しいキーを再発行する(「疑わしきは即時失効」を
   原則とし、公式な影響範囲の確定を待たない)。
3. **再配線**: 新しいキーをCloud Run functionsの環境変数・Secret Managerへ反映し、旧キー
   での呼び出しが拒否されることを確認する(例: Stripe Webhook署名検証で旧`whsec_...`が
   失敗することを確認)。
4. **不正利用の痕跡確認**: 各ベンダーの管理画面・Cloud Loggingで、キー失効までの間に想定外
   の呼び出し(決済・メッセージ送信等)が発生していないかを確認する。
5. **個人情報保護法上の対応との併走**: キー漏えい自体とは別に、当該ベンダーが保持していた
   顧客データ(本venture経由の個人情報)が対象に含まれる場合は、既存の漏えい対応系
   「パシャっと」群と同じ一次整理(報告・本人通知の要否判定)を並行して行う。

## 4. 未検証・残課題

- 上記は未着手(実アカウント未開設)の時点での設計ドラフトであり、実際のベンダー管理画面の
  UI・キー失効手順の詳細は各ベンダーの実アカウント開設後に確認・更新する。
- 残る横展開先はforklift-pasha・event-komiguai-pashaの2件(次回候補として残す)。
- 実際のキーローテーション実行・ベンダーへの問い合わせ自体は、各ベンダーの実アカウント
  開設(オーナー承認待ち)後でなければ発生しない。本フェーズはコード変更を行わない。

最終更新: 2026-10-24 20:00 UTC(新規作成。kura-pashaフェーズ262の横展開として外部ベンダー
侵害時キー緊急ローテーション手順runbookを作成。本venture固有の論点としてLIFFアプリID非依存
〈postback方式〉を明記。コード変更なし)
