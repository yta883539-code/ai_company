# oshien-pasha 公開までのチェックリスト(フェーズ118時点)

目的: 設計・プロトタイプ・テストは積み上げてきたが、実際の稼働にはオーナー承認が必要な
外部サービス設定が残っている。オーナーがpending-approval.mdを確認する際に迷わないよう、
本ventureに関わる承認待ち事項・未決定の運営判断を1箇所にまとめる。
aircon-pasha(フェーズ289)・kura-pasha(フェーズ196)・line-reservation-ai(フェーズ続き286)
と同型の整理を行う。

## 現状(設計・プロトタイプ・検証済み、追加作業不要)

- README.md: B2C個人向け(アイドル・声優・2.5次元舞台・eスポーツ遠征参加者)という
  他6venture(B2B)とは異なる顧客層・利用シーンの整理完了。
- venue-master-draft.md: 東京圏・大阪圏・名古屋圏の主要ドーム・アリーナ・ライブハウスの
  最寄り駅・アクセス情報を一次整理。
- fan-pass-store-protocol-design.md・usage-counter-store-protocol-design.md:
  月額フリーパス(fan_pass)・都度プラン(one_time_pass)のProtocol設計。
- firestore-data-model.md・firestore-security-rules-draft.md: 本番用`fan_pass`コレクション等
  のデータモデル・セキュリティルール設計。
- stripe-webhook-entry-point-design.md・monthly-pass-identity-design.md・
  payment-method-design.md: 月額フリーパス(mode=subscription)・都度プラン(mode=payment)
  のCheckout Session発行・Webhook処理設計。
- llm-generation-failure-handling-design.md・generation_request_handler.py:
  LLM呼び出し失敗時(タイムアウト・Structured Outputs不整合等)のstatus_code=502分岐、
  失敗時に消費させない設計・実装済み。
- prototype/: fan_pass_store.py・usage_counter.py・venue_matcher.py等、prototype配下の
  素朴テストスクリプト全7本で計約113アサーション、いずれもパス(フェーズ117時点)。
- customer-interview-design.md(フェーズ116)・interview-rehearsal-script.md(フェーズ117):
  B2C個人向け匿名性配慮を反映した全12問・目標10分のヒアリング設計・リハーサル台本完成。

## 承認待ち事項(pending-approval.md記載の要約)

1. **実GCPプロジェクト作成 + Firestoreデータベース新規作成 + 実Stripeアカウント開設**
   (2026-11-08 04:00 UTC記載)
   firestore-data-model.md・firestore-security-rules-draft.mdで設計済みの`fan_pass`
   コレクション等の実デプロイ先、stripe-webhook-entry-point-design.md・
   monthly-pass-identity-design.md・payment-method-design.mdで設計済みの月額フリーパス
   (mode=subscription)・都度プラン(mode=payment)のCheckout Session発行先。
   → 承認後: 実GCPプロジェクト作成、Firestoreデータベース新規作成、実Stripeアカウント・
   Webhookエンドポイント登録、`fan_pass`コレクション構造の実デプロイ・結合実装から着手。
   これが整わない限り、本ventureは「設計の蓄積」から「実サービスの起動」へ進めない唯一
   にして最大の前提(pending-approval.md 2026-11-08 04:00 UTC記載の理由欄より)。
2. **全7venture共通の運営方針判断**(2026-11-08 08:00 UTC記載、全venture共通)
   7venture全てが同種の外部サービス接続承認待ちで最長約3ヶ月以上停止している状態について、
   いずれかのventureだけでも承認するか、当面すべて保留するかのオーナー判断を仰いでいる。
   本時刻(2026-11-13 19:00 UTC)時点で5日以上未回答。

## 承認は不要だが未解決の運営判断(次回ヒアリング実施前に必要)

- 顧客ヒアリング(customer-interview-design.md・interview-rehearsal-script.md対象)の
  謝礼の有無・対象選定方法: 他venture(実在事業者の屋号ベースのロングリスト)とは異なり、
  本ventureはB2C個人(ファン)向けのため対象選定方法自体が未確定。社内リハーサルの実施も
  本エージェントの作業範囲外(オーナー内部で完結可能)。

## 運用手順(月額フリーパス会員数に応じたBilling Budget予算見直し、フェーズ133時点)

aircon-pasha(フェーズ387・388)・course-set-pasha・kura-pasha(フェーズ続き309)・
forklift-pasha(フェーズ241)が横展開してきた「契約数に応じたBilling Budget予算見直し
運用手順」を、forklift-pashaフェーズ241の「残る横展開先はoshien-pashaのみ」を受けて
本venture側に反映する。billing-budget-cap-safeguard-design.mdの暫定予算額(月間500円)は
line-reservation-ai同様の暫定値を踏襲したものだったが、フェーズ119で作成したunit-economics-
estimate.mdにより、月額フリーパス会員1人あたりの月間LLM原価(月6回利用想定・キャッシュなし・
シナリオB)が約42.72円と試算されたため、この値を根拠に数値閾値を以下の通り確定する。

- 500円 ÷ 42.72円 ≒ 11.7人のため、月額フリーパス会員数の想定上限を保守的に10人と置く
  (10人×42.72円=427.2円で500円以内に収まる)。
- 月額フリーパス(fan_pass)の有効会員数(Stripeの有効サブスクリプション件数)が8人
  (想定上限10人の8割)に達した時点で、billing-budget-cap-safeguard-design.mdの算出式
  (会員数×会員1人あたり原価約42.72円×安全マージン相当)に基づき予算額の見直し案を算出し、
  オーナーへ見直し提案(現行予算額・新規提案額・増加理由)を提示する。
- 都度プラン(one_time_pass)は継続課金ではなく単発利用のため、月額フリーパスのような
  会員数の累積リスクとは性質が異なり、本運用手順の対象外とする(都度プランの利用集中時の
  原価は、unit-economics-estimate.mdが留保したピーク集中時の再検証課題として別途扱う)。
- 見直し提案自体は承認待ち事項1と同様、実際のCloud Billing Budgets & alertsの設定変更を
  伴うためオーナー承認が必要なアクションであり、本エージェントが単独で予算額を変更することは
  ない。
- 本運用手順は承認待ち事項1(実GCPプロジェクト・実Stripeアカウント等の作成)が承認され、
  実際にBilling Budgetが作成された後にのみ適用される(会員数の実測自体が実Stripeアカウント
  接続を前提とするため)。

これにより、aircon-pashaフェーズ388が確認した「契約数に応じたBilling Budget予算見直し
運用手順」の7venture横展開が全て完了した(aircon-pasha・course-set-pasha・kura-pasha・
forklift-pasha・event-komiguai-pasha・oshien-pasha・line-reservation-ai)。

## 次回候補

上記1・2のいずれかが承認された場合、その着手を最優先とする。承認が得られるまでの間は、
(1)社内リハーサル実施後の台本修正(オーナー判断・実施待ち)、(2)venue-master-draft.mdの
各会場アクセス情報の精査、(3)他venture・アイデア領域の前進、を優先する。

## 重複作業の抑制方針

aircon-pasha(フェーズ293)が確認した状態と同様、設計・プロトタイプ・テストの観点で
本venture側が自律的に前進できる余地はおおむね使い切っている。コード(prototype/)または
設計docの実質的な変更が発生していない限り、本チェックリストの棚卸しのみを目的とした
フェーズは追加しない。
