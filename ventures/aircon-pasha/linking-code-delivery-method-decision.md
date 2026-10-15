# 連携コードの顧客への届け方: 確認メール方式の決定

作成日: 2026-10-15(フェーズ317、application-form-submission-http-entry-point-design.md
7節「次回候補」の検討)

## 1. 検討対象の課題

- application-form-submission-http-entry-point-design.md 7節が残した課題:
  GAS側`onFormSubmit`がCloud Functionsから受け取った`linking_code`を、
  (A)フォーム送信完了画面(サンクスページ)への表示、(B)入力済みメールアドレス宛への
  確認メール送信、(C)Googleフォームを埋め込んだ独自LPへの切り替え、のいずれで顧客に
  届けるか。

## 2. 各案の評価

- (A) サンクスページ表示: design 7節が既に確認した通り、Googleフォーム標準の完了画面は
  GASの`onFormSubmit`トリガー(フォーム送信**後**に非同期で実行される)からは動的に
  書き換えられない制約があり、技術的に実現不可能。採用しない。
- (C) 独自LP + フォーム埋め込み: Googleフォームを独自ドメインのLPにiframe埋め込みすれば
  送信後にJavaScriptで任意の内容を表示できるが、そのためには(i)LP自体のホスティング先
  (静的サイト)、(ii)埋め込み元フォームの送信完了をLP側JSが検知する仕組み(Googleフォーム
  埋め込みは送信後に埋め込み元ページ内でサンクス表示に遷移するが、`linking_code`という
  動的な値をJS側に渡す標準手段がない=結局Cloud Functionsへの別途問い合わせが必要)が
  新たに必要になる。本venture(aircon-pasha)の売りである「Googleフォーム+GAS+LINE公式
  アカウントのみで初期投資ほぼ不要」という前提(tech-stack.md想定)から外れ、独自LPの
  実装・ホスティングという新たな構築コストを持ち込む。採用しない。
- (B) 確認メール送信(`MailApp.sendEmail()`): GAS標準APIのみで実現できる
  (追加のホスティング・外部サービス契約が不要、Gmail/Google Workspaceの送信枠内)。
  フォーム項目に既にメールアドレスを必須回答として含んでいる(user-account-linking-
  design.md 1節)ため、追加の個人情報取得は発生しない。
  tone-and-manner-guideline.md「連携コード関連文言の最終確定」節が確定させた
  `LINKING_REQUIRED_MESSAGE`の文言が、そもそも「お申込みフォーム送信完了画面
  **またはメール記載**の6文字の連携コード」という両対応の言い回しで設計されており、
  メール経由を前提の一つとして既に想定済みだった。

## 3. 決定

- (B) 確認メール送信(`MailApp.sendEmail()`)を採用する。サンクスページ表示・独自LPは
  いずれも不採用。

## 4. メール本文草案

- 件名: 「【{{サービス名}}】お申込み内容の確認と連携コードのご案内」
  (`{{サービス名}}`はローンチ時に確定する屋号、pricing-plan.md・landing-page-copy-
  draft.md等と合わせる。現時点では仮称のため本ドキュメントではプレースホルダのまま)
- 本文(ですます調・絵文字不使用、tone-and-manner-guideline.mdの既存方針を踏襲):

  ```
  {{business_name}} 様

  お申込みフォームよりご回答いただき、ありがとうございます。
  LINE公式アカウントとの連携のため、以下の手順をお願いいたします。

  1. LINE公式アカウント「{{サービス名}}」を友だち追加してください。
     {{LINE_ADD_FRIEND_URL_OR_QR}}
  2. 友だち追加後、最初のトークで下記の連携コードをそのまま送信してください。

     連携コード: {{linking_code}}

  連携コードは発行から24時間以内のみ有効です。時間が経過した場合は、
  お手数ですが再度お申込みフォームよりご回答ください。

  ご不明点がございましたら、本メールへの返信、またはLINE公式アカウントの
  トークにてお問い合わせください。
  ```

- `{{LINE_ADD_FRIEND_URL_OR_QR}}`: onboarding-guide.md 2節が既に「実LINE API接続着手時に
  あわせて着手する」として残した、LINE公式アカウントのQRコード・友だち追加URL
  (`page.line.me/...`形式、initial-contact-message-draft.mdの既存顧客調査で確認した
  他社事例と同形式)の未確定値をそのまま再利用する。本venture自身の公式アカウントが
  実際に開設されるのはpending-approval.md記載の承認待ち事項(Googleフォーム作成+GAS
  Webhook設定、および別途のLINE公式アカウント開設)が承認された後であるため、本メール
  本文もその時点で値を確定させる(新たな承認待ち事項の追加ではない)。

## 5. GAS側実装方針

- `onFormSubmit`内、Cloud Functionsからの200応答で`linking_code`を取得した直後に
  `sendLinkingCodeConfirmationEmail(email, businessName, linkingCode)`を呼ぶ
  (gas-script-draft.md 本体に追記、下記「6. 残課題」参照)。
- `MailApp.sendEmail(email, subject, body)`を使う(GAS標準、追加のAPI有効化不要)。
  送信元はGASプロジェクト実行者のGoogleアカウント名で送信される(GAS標準挙動、
  独自の送信元ドメイン設定は行わない。MVPの割り切り)。
- メール送信が失敗した場合(`MailApp`が例外を投げるケース、例: 1日の送信上限超過)は
  `try/catch`で捕捉し、design 4節の「401/400時はログのみ残す」と同じ方針でログに残すに
  留める(連携コード自体はFirestore `pending_links`に発行済みのため、メール送信失敗時も
  オーナーがGAS実行ログを確認して手動でコードを伝える代替手段が残る。自動リトライは
  MVPでは実装しない)。

## 6. 次回候補

- 承認待ち事項(Googleフォーム作成+GAS Webhook設定、LINE公式アカウント開設)が
  オーナーから承認された場合、`{{サービス名}}`・`{{LINE_ADD_FRIEND_URL_OR_QR}}`の
  実値確定とメール本文の最終稿化から着手する。
- 本決定に基づき、gas-script-draft.mdの`onFormSubmit`コード草案に
  `sendLinkingCodeConfirmationEmail()`呼び出しを追記する(本フェーズ内で実施、
  gas-script-draft.md側の更新を参照)。
- 他venture・アイデア領域の前進。
