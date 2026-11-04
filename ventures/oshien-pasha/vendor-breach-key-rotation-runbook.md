# 外部ベンダー侵害発覚時の自社キー緊急ローテーション手順(設計)

## 1. 背景

ノーコードWeb制作サービス「Studio」(Studio株式会社)の2026年10月不正アクセス事案(対象に
個人情報だけでなく外部サービス連携用の**APIキー・復号鍵**が含まれた)を踏まえ、kura-pasha
フェーズ262(2026-10-24 10:00 UTC)が本venture群共通の緊急ローテーション手順
`vendor-breach-key-rotation-runbook.md`を設計し、aircon-pasha・course-set-pasha・
forklift-pasha・line-reservation-ai・event-komiguai-pashaの5venture(当時の既存全venture)へ
横展開済みであることをaircon-pashaフェーズ342(firestore-provider-adapter-design.md 26節)が
確認している。本ventureはこの横展開完了後に新設された7番目のventureであるため、横展開対象に
含まれず同ファイルが存在していなかった。本フェーズはこの未整備(横展開漏れではなく、横展開
完了後の新規venture追加によるギャップ)を解消し、本venture向けに新規作成する。

本venture自体が不正アクセス・キー漏えいを受けた事実はない。

## 2. 本ventureが保有する外部連携キー・シークレットの一覧

tech-stack.mdの構成を前提に、本venture固有の依存先を整理する。

| 依存先 | 保有するシークレット | 用途 |
| --- | --- | --- |
| Stripe | シークレットキー(`sk_live_...`)・Webhook署名シークレット(`whsec_...`) | 都度プラン(`mode=payment`)・月額フリーパス(`mode=subscription`)の両方のCheckout Session発行・Webhook受信(payment-method-design.md) |
| LLM APIプロバイダ | APIキー | 4出力(itinerary_draft・day_timetable・cost_estimate・hashigo_check)生成 |
| GCP(Cloud Run・Firestore・Secret Manager) | サービスアカウント鍵・Secret Managerアクセス権 | Webフォーム配信・処理の実行環境(tech-stack.md コンポーネント1)、`fan_pass`コレクション(firestore-data-model.md)の読み書き |

他6venture(aircon-pasha・course-set-pasha・kura-pasha・forklift-pasha・
line-reservation-ai・event-komiguai-pasha)はいずれもLINE公式アカウント(LIFF)を入力・出力
チャネルとするため「LINE Messaging API(チャネルアクセストークン・チャネルシークレット)」が
依存先に含まれるが、本ventureはpayment-method-design.md(フェーズ5)で確定した
「Web単体(LINE非依存)」方針のため、LINE Messaging API関連のシークレットは対象外である点が
本venture固有の違いとなる。

実アカウント開設自体がオーナー承認待ち(本ventureについてはpending-approval.mdに個別の記載が
まだない。tech-stack.md・payment-method-design.mdいずれも「実際のGCPプロジェクト作成・
Cloud Runデプロイ・Stripeアカウント接続自体はオーナー承認待ち」と明記するに留まり、本venture
はまだ実アカウント開設の申請段階にも至っていない開発フェーズのため)のため、現時点では上記は
「開設後に保有することになる」想定の一覧である。

## 3. 緊急ローテーション手順(ドラフト)

kura-pashaフェーズ262の5段階手順を踏襲する(ベンダー構成がLINE非依存である点を除き同一の
ため、手順自体の変更は不要)。

1. **検知**: 上記いずれかのベンダー(またはそのベンダーがさらに利用する委託先)が不正
   アクセス・情報漏えいを公表し、自社が保有するAPIキー・シークレットが対象に含まれる
   可能性があるとの連絡・報道を確認した時点を起点とする。
2. **一次切断**: 対象ベンダーの管理画面から影響範囲が確定する前に、該当するキー・
   シークレットを予防的に失効させ、新しいキーを再発行する(「疑わしきは即時失効」を
   原則とし、公式な影響範囲の確定を待たない)。
3. **再配線**: 新しいキーをCloud Runの環境変数・Secret Managerへ反映し、旧キーでの呼び出し
   が拒否されることを確認する(例: Stripe Webhook署名検証で旧`whsec_...`が失敗することを
   確認)。
4. **不正利用の痕跡確認**: 各ベンダーの管理画面・Cloud Loggingで、キー失効までの間に想定外
   の呼び出し(決済・生成処理等)が発生していないかを確認する。
5. **個人情報保護法上の対応との併走**: キー漏えい自体とは別に、当該ベンダーが保持していた
   利用者データ(`fan_pass`コレクションの内容等)が対象に含まれる場合は、既存の漏えい対応系
   「パシャっと」群と同じ一次整理(報告・本人通知の要否判定)を並行して行う。

## 4. 未検証・残課題

- 上記は未着手(実アカウント未開設)の時点での設計ドラフトであり、実際のベンダー管理画面の
  UI・キー失効手順の詳細は各ベンダーの実アカウント開設後に確認・更新する。
- 本venture固有の論点として、都度プラン(`mode=payment`)・月額フリーパス(`mode=subscription`)
  の2種類のCheckout Session生成ロジックを持つ(payment-method-design.md)が、いずれも同一の
  Stripeシークレットキー・Webhook署名シークレットを共有するため、ローテーション手順自体に
  分岐は生じないことを確認した。
- 実際のキーローテーション実行・ベンダーへの問い合わせ自体は、各ベンダーの実アカウント
  開設(オーナー承認待ち)後でなければ発生しない。本フェーズはコード変更を行わない。
- 本ファイルの新規作成により、全7venture(aircon-pasha・course-set-pasha・
  event-komiguai-pasha・forklift-pasha・kura-pasha・line-reservation-ai・oshien-pasha)で
  横展開が完了した。

最終更新: 2026-11-04 02:00 UTC(新規作成。aircon-pashaフェーズ342が記録した「横展開完了後に
新設されたventureには同ファイルが存在しない」というギャップを解消。本venture固有の論点として
LINE Messaging API非依存〈Web単体〉・都度プラン/月額フリーパス2モードでのシークレット共有を
明記。コード変更なし)
