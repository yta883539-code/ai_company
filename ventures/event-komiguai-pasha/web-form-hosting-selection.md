# Webフォームホスティングサービスの具体的な選定(フェーズ49)

tech-stack.md(フェーズ7)「未検証・残課題」、およびフェーズ48の次回候補(3)で持ち越されていた
「Webフォームホスティングサービスの具体的な選定」に対応する。

## 1. 前提の整理

tech-stack.mdフェーズ7時点で既に確定している事項は以下の通り。

- バックエンドはline-reservation-ai・course-set-pashaが選定済みのGCP Cloud Run functions
  (2nd gen)を第一候補として流用する。
- 入力チャネルはLINE公式アカウントを採用せず、シンプルなWebフォーム(URLアクセスのみ、
  LINEアカウント登録不要)とする。
- 利用頻度は1主催者あたり月数件程度と低頻度で、双方向の会話状態管理は不要。
- フォーム送信(HTTPSトリガー)→構造化出力生成→レスポンスとして4出力を返す単方向バッチ
  処理で完結する。

未確定だったのは、フォーム自体(入力ページ・結果表示ページのHTML/UI)をどこでホスティング
するかという点。

## 2. 検討した選択肢

| 選択肢 | 概要 | 本venture適性 |
|---|---|---|
| A. Cloud Run(2nd gen)の同一サービス内でフォーム配信と処理を統合 | バックエンドと同じCloud RunサービスがHTMLフォーム(GET)とフォーム送信処理(POST)の両方を返す | ◎ |
| B. Firebase Hosting(静的ホスティング)+ Cloud Run functions(API) | フォームの静的ファイルをFirebase Hostingに配置し、送信先のみCloud Run functionsを呼ぶ | △ |
| C. Cloud Storage静的ウェブサイトホスティング + Cloud CDN | HTMLをバケットに置き、CDN経由で配信 | △ |

### 2-1. 選択肢Bの課題

Firebase Hostingを採用すると、本venture用に新たなGCPプロダクト(Firebase)の有効化・
プロジェクト紐付けが追加で必要になる。vendor-breach-key-rotation-runbook.md(フェーズ48)
が明記した本venture保有キー3種(Stripe・LLM API・GCPサービスアカウント鍵)に加えて
Firebase Hosting用の管理者権限・デプロイキーが新たな依存先として増える。低頻度利用に対して
運用対象のサービス数を増やさないという設計方針(tech-stack.mdフェーズ7「ランニング」節)に
反する。

### 2-2. 選択肢Cの課題

Cloud Storage静的ホスティング+Cloud CDNは、独自ドメイン運用時にCDN・ロードバランサ構成
(HTTPS証明書の紐付け含む)が別途必要になり、月数件程度の低頻度利用に対して構成要素が
過剰である。

### 2-3. 選択肢Aの優位性

Cloud Run(2nd gen)は静的レスポンス(HTMLテンプレート文字列)を返すエンドポイントと
JSON APIエンドポイントを同一サービス内の別ルートとして実装できるため、追加のGCPプロダクト
有効化が不要。依存先・課金対象・キー管理対象が「Cloud Runが動くGCPプロジェクト1つ」に
収まり、vendor-breach-key-rotation-runbook.mdの保有キー一覧(Stripe・LLM API・GCPサービス
アカウント鍵)を変更する必要がない。

## 3. 選定結果

本venture第一候補として**選択肢A(Cloud Run 2nd genの同一サービス内でフォーム配信と
処理を統合)**を採用する。GET `/`でフォームHTML(mvp-flow-draft.mdの5入力要素フォーム)を
返し、POST `/submit`でフォーム送信を受け付けてLLM生成・4出力表示ページを返す構成とする。
静的アセット(CSS等)が増えてページ配信負荷が高まった場合は、その段階でCloud CDNの前段
配置を再検討する(現時点では低頻度利用のため不要と判断)。

## 4. 未検証・残課題

- 実際のGCPプロジェクト作成・Cloud Runサービスのデプロイ自体は、他ventureと同様にアカウント
  作成・課金設定を伴うためオーナー承認待ちの範囲(pending-approval.md参照)。今回はホスティング
  方式の選定・cross-venture設計整理のみに留める。
- 独自ドメイン(URLアクセスのみを前提とするtech-stack.mdフェーズ7の方針)を使うか、Cloud Run
  のデフォルトURL(`*.run.app`)のままとするかは、実際のサービス公開時に再検討する。

最終更新: 2026-10-24 23:00 UTC(フェーズ49: tech-stack.mdフェーズ7の残課題だったWebフォーム
ホスティングサービスを検討し、Cloud Run 2nd gen同一サービスでのフォーム配信・処理統合を
選定。追加のGCPプロダクト依存を増やさない方針とし、vendor-breach-key-rotation-runbook.mdの
保有キー一覧に変更がないことを確認した)
