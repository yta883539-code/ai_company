# 外部ベンダー侵害発覚時の自社キー緊急ローテーション手順(設計)

## 1. 背景

本ドキュメントは、kura-pashaフェーズ262(2026-10-24 10:00 UTC)で新規設計された
`vendor-breach-key-rotation-runbook.md`の横展開(同フェーズ「次回候補(1)」記載)として、
line-reservation-ai固有の依存先キー群を洗い出し、外部ベンダー自身が不正アクセスを受け
APIキー・復号鍵が漏えい対象に含まれた場合の緊急ローテーション手順を設計のみ先行して
整理するもの。根拠事案(ノーコードWeb制作サービス「Studio」の2026年10月不正アクセス、
個人情報に加え外部連携用APIキーまで漏えい対象に含まれた)はkura-pasha側の記載を参照。
本venture自体がこの種の被害を受けた事実、実際の不正アクセス発生・キー漏えいはいずれも
生じていない。

## 2. line-reservation-aiが保有する外部連携キー・シークレットの一覧

tech-stack.md(想定コンポーネント1〜4)の構成を前提に、本venture固有の依存先を整理する。

| 依存先 | 保有するシークレット | 用途 |
| --- | --- | --- |
| LINE Messaging API | チャネルアクセストークン・チャネルシークレット | Webhook署名検証・返信送信・LIFFアプリIDトークン検証(line-account-connection-stepguide.md) |
| Stripe | シークレットキー(`sk_live_...`)・Webhook署名シークレット(`whsec_...`) | Checkout Session発行(checkout-initiation-flow-design.md)・Webhook受信/署名検証(stripe-webhook-signature-verification-design.md) |
| LLM APIプロバイダ | APIキー | 会話意図解釈・構造化出力生成(llm-system-prompt-draft.md) |
| GCP(Cloud Run functions・Firestore) | サービスアカウント鍵・Secret Managerアクセス権 | Webhook実行環境・会話状態/予約枠/通知ログのデータストア接続(firestore-data-model.md) |

いずれも実アカウント開設自体がオーナー承認待ち(pending-approval.md記載、LIFFアプリ登録+
LINE公式アカウント開設は2026-08-28 17:00 UTC記載分、実Firestoreプロジェクト・GCPアカウント
開設は2026-10-23 12:00 UTC記載分)のため、現時点では上記は「開設後に保有することになる」
想定の一覧である。

## 3. 緊急ローテーション手順(ドラフト)

kura-pasha版と同一の5段階手順を、本venture固有の構成要素に当てはめる。

1. **検知**: 上記いずれかのベンダー(またはそのベンダーがさらに利用する委託先)が
   不正アクセス・情報漏えいを公表し、自社が保有するAPIキー・シークレットが対象に
   含まれる可能性があるとの連絡・報道を確認した時点を起点とする。
2. **一次切断**: 対象ベンダーの管理画面から影響範囲が確定する前に、該当するキー・
   シークレットを予防的に失効させ、新しいキーを再発行する(「疑わしきは即時失効」を
   原則とし、公式な影響範囲の確定を待たない)。LINEチャネルについては、LIFFアプリの
   IDトークン検証に使う公開鍵もチャネルシークレットと紐づくため、再発行後は
   `build_line_return_link()`含むユニバーサルリンク組み立て処理への反映も対象に含める。
3. **再配線**: 新しいキーをCloud Run functionsの環境変数・Secret Managerへ反映し、
   旧キーでの呼び出しが拒否されることを確認する(例: Stripe Webhook署名検証で旧
   `whsec_...`が失敗することを確認、stripe-webhook-signature-verification-design.md参照)。
4. **不正利用の痕跡確認**: 各ベンダーの管理画面・Cloud Loggingで、キー失効までの間に
   想定外の呼び出し(予約確定・決済・LINE返信送信等)が発生していないかを確認する。
5. **個人情報保護法上の対応との併走**: キー漏えい自体とは別に、当該ベンダーが保持して
   いた顧客データ(本venture経由の氏名・予約内容等)が対象に含まれる場合は、既存の漏えい
   対応系「パシャっと」群と同じ一次整理(報告・本人通知の要否判定)を並行して行う。

## 4. 未検証・残課題

- 上記は未着手(実アカウント未開設)の時点での設計ドラフトであり、実際のベンダー管理画面
  のUI・キー失効手順の詳細は各ベンダーの実アカウント開設後に確認・更新する。
- 残る横展開先(aircon-pasha・course-set-pasha・forklift-pasha・event-komiguai-pasha)は
  他venture側の次回候補として残す。
- 実際のキーローテーション実行・ベンダーへの問い合わせ自体は、各ベンダーの実アカウント
  開設(オーナー承認待ち)後でなければ発生しない。本フェーズはコード変更を行わない。

最終更新: 2026-10-24 17:00 UTC(新規作成。kura-pashaフェーズ262の横展開として、本venture
固有の依存先キー一覧〈LINE Messaging API・Stripe・LLM API・GCP/Firestore〉と緊急
ローテーション手順のドラフトを整理した。コード変更なし)
