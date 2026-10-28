# 技術構成案(初回メモ)

payment-method-design.md(フェーズ5)の次回候補(1)「tech-stack.mdの新規作成(Web単体構成を
前提とした技術スタック選定)」に対応する初回メモ。他6venture(aircon-pasha・course-set-pasha・
kura-pasha・forklift-pasha・line-reservation-ai・event-komiguai-pasha)がいずれもLINE公式
アカウント(LIFF)経由のB2B構成であるのに対し、本ventureはpayment-method-design.mdで確定した
「Web単体(LINE非依存)」方針を前提に、B2C・都度利用中心の技術構成を検討する。

## 全体構成イメージ

利用者(ファン、Webブラウザ) ⇄ Webフォーム+バックエンド(単一サービス) ⇄ LLM(4出力生成) ⇄
結果表示ページ(下書きをそのまま表示)

event-komiguai-pasha(B2C・Web単体・一度限りの利用という点で本ventureに最も近い既存構成)の
tech-stack.md・web-form-hosting-selection.mdの選定結果を第一候補として流用する。

## 想定コンポーネント

1. **Webフォーム+バックエンド(統合)**
   - event-komiguai-pashaのweb-form-hosting-selection.mdが選定した「Cloud Run (2nd gen)
     同一サービス内でフォーム配信(GET `/`)と処理(POST `/submit`)を統合する」構成を本venture
     でも流用する。line-reservation-ai・course-set-pashaが選定済みのGCP Cloud Run functions
     (2nd gen)を第一候補とする点は全venture共通。
   - 追加のGCPプロダクト(Firebase Hosting等)を有効化しない方針も流用し、依存先・キー管理
     対象を「Cloud Runが動くGCPプロジェクト1つ」に収める。
2. **入力フォーム**
   - README.mdの入力項目(会場・日時・枚数、予算感、グッズ購入希望、前後の予定、複数公演
     「ハシゴ」の有無)を1ページのWebフォームで受け付ける。LINEアカウント登録・会員登録は
     不要(README.md「会員管理・予約受付・決済は当面扱わない」方針どおり)。
3. **会場マスタ参照**
   - venue-master-draft.mdの会場マスタは、現段階ではコード化・データベース投入を行わない
     静的なMarkdownメモの段階にある。実装時はJSON化してバックエンド(Cloud Run)の静的
     アセットとして同梱する軽量参照データとする想定とし、Firestore等の専用データストアは
     不要と判断する(会場数が少数〈主要12会場〉かつ更新頻度が低いため)。会場名表記揺れの
     名寄せロジック(README.md既出の検討課題)は、将来会場数が増えた場合にFirestore化を
     再検討する。
4. **LLM(4出力生成)**
   - 入力(+会場マスタ参照結果)→ schema/output.schema.jsonの構造化出力形式で出力4種
     (itinerary_draft・day_timetable・cost_estimate・hashigo_check)を生成する。
     他ventureと同様、status(generated/out_of_scope/insufficient_input)に応じた分岐方針
     を踏襲する。
5. **決済**
   - payment-method-design.mdで整理した通り、プラン選択結果に応じてStripe Checkout
     Sessionを`mode=payment`(都度プラン)または`mode=subscription`(月額フリーパス)の
     いずれかで生成する2分岐ロジックとする。
   - 都度プランは決済完了後その場で4出力を生成・表示するワンショット処理で足りるため、
     event-komiguai-pashaのone-time-checkout-no-account-design.md(決済→結果ページ発行→
     TTL付きアクセス)の考え方を流用できる。
6. **月額フリーパス利用者の識別(新規の検討課題)**
   - 都度プラン・event-komiguai-pashaはいずれも「1回の決済=1回の利用」で完結し、利用者を
     横断的に識別する必要がない。一方、月額フリーパス(当月内の生成回数無制限)は「同一
     利用者が今月すでに決済済みか」を次回以降の利用時に判定する必要があり、本venture独自の
     要件となる。
   - LINEアカウント前提の他6ventureはLINEユーザーIDを識別子として利用できるが、本venture
     はLINE非依存のためこの手法は使えない。Web単体でアカウント登録なしに利用者を識別する
     方法(Stripe Customer Portalのマジックリンク、メールアドレス+ワンタイムリンク等)の
     選定は、会員管理を持たないという本venture方針(README.md)と矛盾しない範囲で次回以降
     検討する必要がある未解決の課題として残す。
7. **月額フリーパスの生成回数カウント**
   - 上記6の識別方法が決まった後、course-set-pashaのusage_counter(`UsageCounterProtocol`、
     `get_count`/`increment`)と同様の軽量データストア(Firestore想定)が必要になる見込み
     だが、識別方法が未確定のため本フェーズでは設計を保留する。

## 他6ventureとの構成上の違い(まとめ)

| 観点 | 他6venture(B2B) | 本venture(B2C) |
|---|---|---|
| 入力チャネル | LINE公式アカウント(LIFF) | Webフォーム単体 |
| 利用者識別 | LINEユーザーID | 未確定(次回検討課題) |
| 決済モード | サブスクのみ(`mode=subscription`) | 都度(`mode=payment`)/月額(`mode=subscription`)の2分岐 |
| 永続データストア | Firestore(予約枠・会話状態等) | 当面不要(都度プランのみなら)。月額フリーパス導入時は軽量カウンタのみ検討 |

## 初期投資・ランニングコストの目安

- 開発: 既存クラウドサービス・LLM APIの組み合わせのみで、専用インフラ購入は不要。
  event-komiguai-pashaと同様、追加のGCPプロダクト依存を増やさない設計とする。
- ランニング: LLM API従量課金+Stripe決済手数料のみ。LINE Messaging APIの利用がない分、
  他6ventureより依存先サービス数は少ない。
- 実際のGCPプロジェクト作成・Cloud Runデプロイ・Stripeアカウント接続自体は、他venture同様
  オーナー承認待ちの範囲(pending-approval.md参照)。今回は技術構成の設計整理のみに留める。

## 次のステップ候補

- 月額フリーパス利用者の識別方法の検討(コンポーネント6、会員登録なしという方針との整合)。
- venue-master-draft.mdの各会場のアクセス情報精査(WebSearchでの裏取り、README.md既出の
  残課題)。
- 会場名表記揺れの名寄せ方法の検討(README.md既出の残課題)。
- 都度プラン⇔月額フリーパスのプラン変更時の扱いの検討(pricing-plan.md既出の残課題)。

実LLM呼び出し・Stripe等決済代行サービスとの実接続、実際のGCPプロジェクト・アカウント開設
自体はオーナー承認が必要なアクションに該当するため、本メモは設計・仮説の検討に留める(コード
実装・外部サービスへの接続は一切行っていない)。
