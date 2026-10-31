# 月額フリーパス利用者の識別方法の検討(フェーズ34)

tech-stack.md「想定コンポーネント6」の残課題(会員登録なしで月額フリーパス利用者を
識別する方法の選定)に対応する。

## 1. 前提の整理

- README.mdの方針「会員管理・予約受付・決済は当面扱わない」は、都度プラン(1回の決済=
  1回の利用で完結)には矛盾しないが、月額フリーパス(当月内の生成回数無制限)は「同一
  利用者が今月すでに課金済みか」を次回以降の利用時に判定する必要があり、何らかの識別子を
  利用者側に持たせる必要がある。
- 他6venture(aircon-pasha・course-set-pasha・kura-pasha・forklift-pasha・
  line-reservation-ai・event-komiguai-pasha)はLINEユーザーIDを識別子に使えるが、本
  ventureはpayment-method-design.md(フェーズ5)で確定した「Web単体(LINE非依存)」方針
  のためこの手法は使えない。

## 2. 既存venture内の2パターンの比較

本venture内でも都度プランと月額フリーパスでは利用形態が異なるため、既存6ventureが
確立済みの2つの識別パターンをそれぞれ使い分ける方針とする。

### (A) 都度プラン: event-komiguai-pashaの「一度限りアクセスURL」方式を流用

event-komiguai-pashaのone-time-checkout-no-account-design.md(決済→結果ページ発行→
TTL付きアクセス)は、「1回の決済=1回の利用」で完結する点が本ventureの都度プランと
完全に一致する。決済完了後に発行する結果ページURLにはTTL(有効期限)を設け、再利用・
識別の継続は不要という単純な設計のまま流用できる。

### (B) 月額フリーパス: forklift-pashaの「accessToken方式」を流用

forklift-pashaのaccess-token-reissue-design.md(フェーズ96)が確立した、以下の設計を
本venture向けに適用する。

- Firestoreドキュメントの自動生成ID(`internal_id`)とユーザーに配布するアクセス
  トークン(`accessToken`フィールド)を分離する。
- アクセスURLは`https://<ドメイン>/m/{accessToken}`形式(月額フリーパス専用パスとして
  forklift-pashaの`/f/`と区別する)。
- アクセスURL受信時の利用者特定は、`accessToken`フィールドへの単一フィールドクエリで
  行う(Firestoreが自動作成するインデックスで追加設定不要、forklift-pashaと同じ)。
- 有効期限は無期限(forklift-pashaフェーズ98の決定を踏襲)。サブスクリプション契約期間中
  繰り返し使う「ログインID/パスワード」的な性質を持つため、短命TTLとは別物として扱う。
- 漏洩時・アクセスURLを失った場合の再発行は、forklift-pashaと同じ「現在のトークンを
  失効させ新トークンを発行してメール送信する」フローに統一する(Stripe Checkout
  `mode=subscription`完了時にメールアドレスを取得済みであるため、再発行の宛先はその
  メールアドレスを使う)。

## 3. 本venture固有の差分

forklift-pashaはB2B(事業者が1組織1トークン)だが、本ventureはB2C(個人のファン)である
点に起因する差分が2点ある。

1. **複数デバイス利用の想定**: ファンは自宅PC・外出先のスマートフォン等、複数デバイスから
   同じ月額フリーパスを使う可能性がforklift-pashaの事業者よりも高いと想定される。
   `accessToken`自体はデバイスを問わず同一URLでアクセス可能なため技術的な障害はないが、
   利用者への案内文(メール本文・LPのFAQ想定)に「このURLをブックマークし、どの端末からも
   同じURLで利用できる」旨を明記する必要がある(次回候補、legal-notices-draft.md・
   landing-page-copy-draft.mdへの反映)。
2. **解約後の`accessToken`の扱い**: forklift-pashaは法令上の記録保存義務(安衛則3年保存)
   があるため解約後も一定期間ドキュメントを保持する前提だが、本ventureにそのような保存
   義務はない。解約(`subscription`のcanceled化)後は`accessToken`によるアクセス時に
   「生成機能」への導線は閉じ、月額フリーパスへの再加入を促す簡易ページを表示する分岐を
   設ける(aircon-pasha等のsubscription-canceled-immediate-block-design.md相当の分岐を
   流用できる見込み、次回候補で詳細設計)。

## 4. 残課題・次回候補

- 上記3節(2)の解約後ブロック分岐の詳細設計(aircon-pashaのsubscription-canceled-
  immediate-block-design.mdを参照した具体化)。
- firestore-data-model.md相当の文書が本ventureに未作成のため、`fan_pass/{internal_id}`
  コレクション(`accessToken`・`stripeCustomerId`・`subscriptionStatus`・
  `currentPeriodEnd`等)の定義を新規作成する必要がある(次回候補)。
- course-set-pashaのusage_counter(`UsageCounterProtocol`)と同様の生成回数カウンタ設計
  (tech-stack.mdコンポーネント7で保留していた論点)は、本フェーズで識別方法が確定した
  ことにより着手可能になった(次回候補)。
- venue-master-draft.mdの各会場のアクセス情報精査、会場名表記揺れの名寄せ方法の検討
  (README.md既出の残課題、未着手のまま持ち越し)。

実LLM呼び出し・Stripe等決済代行サービスとの実接続、実際のGCPプロジェクト・Firestore
データベース・Stripeアカウントの開設自体はオーナー承認が必要なアクションに該当するため、
本メモは設計・仮説の検討に留める(コード実装・外部サービスへの接続は一切行っていない)。
