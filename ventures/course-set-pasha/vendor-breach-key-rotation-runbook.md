# 外部ベンダー侵害発覚時の自社キー緊急ローテーション手順(設計)

## 1. 背景

kura-pashaフェーズ262(2026-10-24 10:00 UTC)は、ノーコードWeb制作サービス「Studio」
(Studio株式会社)が2026年10月16日に公表した不正アクセス事案(対象は顧客アカウント情報・
フォーム送信内容に加え、**外部サービス連携用のAPIキーそのもの**。デジタル庁・LUUP・
Link-U・ラクスル等、業種を問わず多数の組織に波及)を踏まえ、同venture自身がこの種の
被害を受けた場合に備えた緊急キーローテーション手順を先行設計し、「他venture(course-set-
pasha・aircon-pasha・forklift-pasha・event-komiguai-pasha)への同種ランブックの横展開」を
次回候補として申し送った(line-reservation-aiは同日17:00 UTCに横展開済み)。

本ドキュメントは、その横展開として本venture(course-set-pasha)固有の依存先キー群を
洗い出し、緊急ローテーションの手順を設計のみ先行して整理するもの。実際の不正アクセス
発生・キー漏えいは本ventureには生じていない。

## 2. course-set-pashaが保有する外部連携キー・シークレットの一覧

tech-stack.mdの想定コンポーネント構成、およびcheckout-initiation-flow-design.md
(LIFF経由IDトークン検証、フェーズ98)・checkout-session-endpoint-design.md(フェーズ112)
を前提に、本venture固有の依存先を整理する。

| 依存先 | 保有するシークレット | 用途 |
| --- | --- | --- |
| LINE Messaging API | チャネルアクセストークン・チャネルシークレット | Webhook署名検証・返信送信(2026-09-28 20:00 UTC記載分、承認待ち) |
| LINE Developers(LIFF) | LIFFアプリID・LIFF URL | Checkout Session発行時のなりすまし防止IDトークン検証(2026-08-23 09:00 UTC記載分、承認待ち) |
| Stripe | シークレットキー(`sk_live_...`)・Webhook署名シークレット(`whsec_...`) | Checkout Session発行・Webhook受信(checkout-session-endpoint-design.md、2026-09-27 03:00 UTC記載分、承認待ち) |
| LLM APIプロバイダ | APIキー | 3出力生成(llm-system-prompt-draft.md) |
| GCP(Cloud Run functions・Firestore) | サービスアカウント鍵・Secret Managerアクセス権 | Webhook実行環境・`UserProfileStoreProtocol`等のデータストア接続(2026-10-24 09:00 UTC記載分、承認待ち) |

いずれも実アカウント開設自体がオーナー承認待ち(pending-approval.md参照、上表の各行に
記載の日時分)のため、現時点では上記は「開設後に保有することになる」想定の一覧である。
kura-pashaの横展開元ドキュメントと異なり、本ventureはLIFF経由IDトークン検証を採用する
構成(aircon-pasha・forklift-pashaはpostback/Webフォーム方式でLIFF非依存)のため、
LINE Developers側のLIFFアプリIDも独立した漏えい対象として表に追加した。

## 3. 緊急ローテーション手順(ドラフト、kura-pashaフェーズ262と同型)

1. **検知**: 上記いずれかのベンダー(またはそのベンダーがさらに利用する委託先)が
   不正アクセス・情報漏えいを公表し、自社が保有するAPIキー・シークレット・LIFFアプリID
   が対象に含まれる可能性があるとの連絡・報道を確認した時点を起点とする。
2. **一次切断**: 対象ベンダーの管理画面から影響範囲が確定する前に、該当するキー・
   シークレット・LIFFアプリを予防的に失効(LIFFはアプリ削除または紐づくチャネルの
   再発行)させ、新しいキー・LIFFアプリを再発行する(「疑わしきは即時失効」を原則とし、
   公式な影響範囲の確定を待たない)。
3. **再配線**: 新しいキーをCloud Run functionsの環境変数・Secret Managerへ反映し、
   旧キーでの呼び出しが拒否されることを確認する(例: Stripe Webhook署名検証で旧
   `whsec_...`が失敗すること、旧LIFF URLでのIDトークン検証が失敗すること)。
4. **不正利用の痕跡確認**: 各ベンダーの管理画面・Cloud Loggingで、キー失効までの間に
   想定外の呼び出し(Checkout Session発行・メッセージ送信等)が発生していないかを確認する。
5. **個人情報保護法上の対応との併走**: キー漏えい自体とは別に、当該ベンダーが保持して
   いた顧客データ(本venture経由の個人情報)が対象に含まれる場合は、既存の漏えい対応系
   「パシャっと」群と同じ一次整理(報告・本人通知の要否判定)を並行して行う。

## 4. 未検証・残課題

- 上記は未着手(実アカウント未開設)の時点での設計ドラフトであり、実際のベンダー管理画面
  のUI・キー失効手順・LIFFアプリ再発行手順の詳細は各ベンダーの実アカウント開設後に
  確認・更新する。
- 残る横展開対象(aircon-pasha・forklift-pasha・event-komiguai-pasha)への同種ランブック
  整理は引き続き次回候補として残る。
- 実際のキーローテーション実行・ベンダーへの問い合わせ自体は、各ベンダーの実アカウント
  開設(オーナー承認待ち)後でなければ発生しない。本フェーズはコード変更を行わない。

最終更新: 2026-10-24 19:00 UTC(新規作成。kura-pashaフェーズ262〈2026-10-24 10:00 UTC〉の
横展開申し送りを受け、本venture固有の依存先キー一覧〈LIFFアプリIDを含む〉と緊急
ローテーション手順のドラフトを整理した。コード変更なし)
