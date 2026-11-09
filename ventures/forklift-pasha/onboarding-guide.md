# 事業者向けオンボーディングガイド(初回メモ、フェーズ225)

INDEX.md「既知の運営課題」節とは別に、INDEX.mdの他venture(kura-pasha・course-set-pasha)との
横断比較で、「申込から実際に点検記録の整形・リマインド生成が始まるまで、事業者は何を
どの順番で行うのか」という一連の導入フローの整理(onboarding-guide.md)自体が、本ventureに
cross-venture parityギャップとして未着手のまま残っていたことを発見した(フェーズ224の次回
候補(3)「他ventureのINDEX.mdとの横断比較で本ventureに固有の運営課題がないかの確認」に対応)。
kura-pasha/onboarding-guide.mdの構成を踏襲しつつ、本venture固有の
(1)LINEではなく汎用Webフォーム(アクセストークン方式)を導入起点とする点、
(2)車両(`vehicle_id`)はオンボーディング手順として明示登録せず、点検メモ送信時に自動発行
される点(vehicle-label-duplicate-handling-design.md)、
(3)daily/monthly/annualの3区分で入力頻度・画面が大きく異なる点(web-form-ui-design.md)
を反映する。

**本ドキュメントは手順の設計のみを行うものであり、実際の申込受付・課金開始・メール送信等の
運用は一切行わない。**

## 前提

- 対象は専任の安全担当者を置かない個人経営・従業員数名規模の倉庫業・運送業・建設業で、
  フォークリフトを1〜数台保有する事業者(market-research.md)。
- aircon-pasha・course-set-pasha・kura-pasha・line-reservation-aiと異なり、LINE公式
  アカウントへの友だち追加を導入起点としない。本ventureはtech-stack.md(フェーズ70)で
  入力チャネルを汎用Webフォーム(LINE非依存)に決定しており、識別子も
  payment-identity-verification-design.md(フェーズ95)・access-token-reissue-design.md
  (フェーズ96)の確定方針どおり、メールアドレス入力を起点に発行する**アクセストークン**
  (`https://<ドメイン>/f/{accessToken}`)である。

## オンボーディングの全体フロー(案)

1. **初回登録(メールアドレス入力)**
   事業者がLP(landing-page-copy-draft.md)経由でWebフォームに入力する。
   - 入力項目: メールアドレスのみ(payment-identity-verification-design.md 2節「1. 初回
     登録」。氏名・事業者名・車両情報等は入力を求めない最小構成)。
   - サーバー側で`fleet_operator/{internal_id}`(Firestore自動生成ID)を新規作成し、
     推測不能なランダム文字列を`accessToken`として発行する。この時点で無料トライアルが
     開始する(pricing-plan.md「無料トライアル条件」、trial-end-condition-design.md
     「初回生成から30日間、または生成5回到達のいずれか早い方」)。
   - 到達性確認(ダブルオプトイン)は設けない(payment-identity-verification-design.md
     3節。アクセスURLが届かなければ本人がそもそも利用開始できないため、確認ステップ追加の
     コストに対し効果が薄いと判断済み)。

2. **アクセスURLの受け取り**
   入力したメールアドレス宛に`https://<ドメイン>/f/{accessToken}`形式のアクセスURLが
   送信される(実メール送信自体はメール連携接続後の運用、pending-approval.md記載の既存
   承認済み運用方針に従う)。ログインID/パスワードは発行せず、以降の点検メモ入力・設定
   変更・プラン申込はすべてこのURL配下のページ(`index.html`→daily/monthly/annual/
   settings/plan-selectionの各リンク)経由で行う。

3. **接続テスト・試験入力**
   事業者が、実際の始業前点検を模した簡単なメモ(例:「1号機、異常なし」)をdaily区分の
   入力画面から送信し、mvp-flow-draft.mdの出力1(点検記録整形テキスト)が想定通り返って
   くるかを本番運用前に確認するステップ。web-form-ui-design.mdのdaily区分UI(車両ボタン→
   「異常なし」ボタン→送信の3タップ)であれば試験入力自体の手間も小さい。
   - この時点で初めて`vehicle_id`が自動発行される(vehicle-label-duplicate-handling-design.md
     「2. vehicle_idの発行方式」。`(operatorInternalId, vehicleLabel)`の完全一致判定。
     事業者が別途「車両登録」操作を行う手順は設計上存在しない)。

4. **本番運用開始(日次・月次・年次の各区分)**
   事業者(または点検担当者)が試験入力の内容に問題ないと判断したら、実際の点検の都度、
   区分に応じたURL(daily/monthly/annual)からメモを送信し、返ってきた点検記録整形
   テキストをスプレッドシート等へ貼り付けて業務に用いる運用を開始する。点検結果の良否
   判断・修理要否の判断・特定自主検査の実施自体はAIが行わない(mvp-flow-draft.md「範囲外」)。
   - **daily**(月20〜25回/台、高頻度): web-form-ui-design.mdのボタン選択中心UIで入力負荷を
     最小化。
   - **monthly**(月1回/台): 自由記述欄を多めに残した入力画面。
   - **annual**(年1回/台): `inspector_company`(検査業者名)が必須入力の自由記述欄として
     追加される。送信完了画面には法定保存義務注意カード(data-retention-policy.md・
     legal-notices-draft.md 2.5節)が表示される。
   - 次回実施期限が近い場合(monthly/annualのみ)、同画面にリマインド通知文(出力2)が
     併記される。

5. **トライアル終了・プラン選択**
   trial-end-condition-design.mdの判定(初回生成から30日経過、または生成5回到達の
   いずれか早い方)に従い、トライアル終了時は自動課金せず、settings.htmlの「あなたの
   アクセスURL」経由でplan-selection.htmlへ誘導する。事業者はpricing-plan.mdの3プラン
   (ライト/スタンダード/複数台、保有台数を主軸とした区分)から選び、プラン選択ページの
   「このプランで申し込む」リンク(plan-selection-submission-wiring-design.md)から
   Stripe Checkoutへ遷移して申込む。限度接近時(月間生成回数90%・保有台数プラン超過)の
   通知はoverage_notifications.pyの設計に従う。

6. **アクセスURLの再発行(必要時)**
   アクセスURLの到達性に依存する識別子方式のため、URLの紛失・漏洩が懸念される場合は
   settings.htmlの「アクセスURLを再発行する」操作で新トークンを即時発行し旧トークンを
   失効させられる(access-token-reissue-design.md)。再発行後は新URLが(現在登録済みの、
   または変更後の)メールアドレス宛に送られる。

## 他ventureとの違い(まとめ)

- 導入起点がLINE友だち追加ではなくメールアドレス入力+アクセストークンである点が、LINEを
  起点とする他4venture(aircon-pasha・course-set-pasha・kura-pasha・line-reservation-ai)
  との最大の違い。ログインID/パスワードを発行しない点はLINEのuser_id方式と共通するが、
  「URLの到達性そのものが利用開始の前提条件」という設計上のトレードオフ(payment-identity-
  verification-design.md 3節)は本venture固有。
- 車両という「契約者とは別の管理対象」が存在する点はkura-pashaのworkshop(職人単位)構造に
  近いが、本ventureは事前登録ステップを設けず点検メモ送信時に自動発行する点が異なる
  (kura-pashaのworkshop作成は申込フォーム入力時点で明示的に行われる)。
- 3区分(daily/monthly/annual)の利用頻度差が1桁〜2桁に及ぶ(月20〜25回 vs 月1回 vs 年1回)
  ため、区分ごとに全く異なる入力画面を用意する設計(web-form-ui-design.md「区分別に入力
  画面を分ける」)は他venture(単一の会話的入力画面)には無い本venture固有の構造。

## 未検証の仮説(要検証)

- 事業者が初回登録時に入力するメールアドレスを誤記した場合、ダブルオプトインを設けない
  方針(手順1)により本人がそもそも利用開始できないまま離脱する可能性がある。実際の
  誤記率・離脱率は実メール送信の運用開始後(オーナー承認待ち)でなければ検証できない。
- 手順3(接続テスト)を事業者が実際に自発的に行うか、省略していきなり本番の日次点検
  入力を開始し、試験入力のつもりで送った内容がそのまま`vehicle_id`として本登録されて
  しまう(例: 車両番号表記のタイプミスがそのまま確定する)リスクがある。kura-pashaの
  first-generation-self-check-notification-design.md相当の「初回生成成功時の確認案内」が
  本ventureにはまだ存在しない。

## 次のステップ候補

- 手順3「未検証の仮説」2点目に対応する、初回daily入力成功時の確認案内(kura-pasha/
  first-generation-self-check-notification-design.md相当)の本venture向け設計。
- 手順1のメールアドレス入力画面(現状web-form-mockup/に図版化されたページが存在しない)の
  モックアップ作成。
- 実メール送信・実Stripe/実GCPプロジェクト接続後、本ガイドの各手順が実際の画面遷移と
  一致しているかのエンドツーエンド確認(オーナー承認待ち、本フェーズ時点ではまだ着手不可)。
