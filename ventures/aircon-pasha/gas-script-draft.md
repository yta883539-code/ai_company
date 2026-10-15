# GAS(Google Apps Script)Webhook草案

作成日: 2026-10-15(フェーズ316、application-form-submission-http-entry-point-design.md 6節)

位置づけ: 実際のGoogleフォーム作成・GASプロジェクトのデプロイ自体はオーナー承認待ち
(pending-approval.md 2026-08-23 04:00 UTC記載)。本ファイルはコード自体の実行・デプロイを
一切伴わない、承認後に貼り付けるためのテキスト草案(course-set-pasha/gas-script-draft.mdと
同じ位置づけ)。

## 前提

- Googleフォームの質問は3問: 「屋号」「事業形態(独立系/フランチャイズ加盟等)」
  「連絡先メールアドレス」(いずれも自由記述、user-account-linking-design.md 1節の
  onboarding-guide.md想定通り)。
- GASプロジェクトの「スクリプト プロパティ」(Project Settings > Script properties)に、
  以下2つを事前設定する(コードにハードコードしない):
  - `ENDPOINT_URL`: デプロイ後のCloud FunctionsのHTTPS URL。
  - `SHARED_SECRET`: Cloud Functions側の環境変数`FORM_WEBHOOK_SHARED_SECRET`と
    同じ値(オーナーが生成・両方に設定)。
  - `SERVICE_DISPLAY_NAME`: 確認メール文中に表示するサービス名・LINE公式アカウント名
    (linking-code-delivery-method-decision.md 4節、ローンチ時に確定)。
  - `LINE_ADD_FRIEND_URL`: LINE公式アカウントの友だち追加URL(`page.line.me/...`形式、
    onboarding-guide.md 2節と同じくLINE公式アカウント開設後に確定)。
- フォームの「回答を送信するたびに通知を受け取る」トリガーではなく、
  エディタの「トリガー」設定で対象フォームの「フォーム送信時」`onFormSubmit`を
  紐付ける(course-set-pashaと同じGAS Webhook方式)。

## コード草案

```javascript
/**
 * Googleフォームの「フォーム送信時」トリガーに紐付ける関数。
 * application-form-submission-http-entry-point-design.md 4節のリクエスト形状に
 * 合わせてJSONを組み立て、Cloud Functionsエンドポイントへ送信する。
 *
 * 設問の並び順はフォーム編集時に変わりうるため、質問文の完全一致ではなく部分一致
 * (includes)で項目を特定する。質問文自体を変更した場合はこのマッピングも
 * 更新が必要(残課題、下記参照)。
 */
function onFormSubmit(e) {
  var itemResponses = e.response.getItemResponses();
  var answers = {};
  for (var i = 0; i < itemResponses.length; i++) {
    var title = itemResponses[i].getItem().getTitle();
    answers[title] = itemResponses[i].getResponse();
  }

  var businessName = "";
  var businessType = "";
  var email = "";
  for (var title in answers) {
    if (title.indexOf("屋号") !== -1) {
      businessName = answers[title];
    } else if (title.indexOf("事業形態") !== -1) {
      businessType = answers[title];
    } else if (title.indexOf("メールアドレス") !== -1) {
      email = answers[title];
    }
  }

  var props = PropertiesService.getScriptProperties();
  var endpointUrl = props.getProperty("ENDPOINT_URL");
  var sharedSecret = props.getProperty("SHARED_SECRET");

  var payload = {
    form_submission_id: e.response.getId(),
    business_name: businessName,
    business_type: businessType,
    email: email,
  };

  var options = {
    method: "post",
    contentType: "application/json",
    headers: { "X-Form-Webhook-Secret": sharedSecret },
    payload: JSON.stringify(payload),
    // 4xx/5xxでも例外を投げず戻り値から判定する(ログに残して後で確認するため)。
    muteHttpExceptions: true,
  };

  var response = UrlFetchApp.fetch(endpointUrl, options);
  var statusCode = response.getResponseCode();
  if (statusCode !== 200) {
    // design 4節の通りフォーム回答者への追加エラー表示は行わず、ログのみ残す。
    // オーナーがGAS実行ログ(実行数、表示: 拡張機能 > Apps Script > 実行数)を
    // 手動確認して個別対応する運用(MVPの割り切り)。
    console.error(
      "application form submission failed: status=" + statusCode +
      " body=" + response.getContentText()
    );
    return;
  }

  // design 4節: 成功時のレスポンスに発行済みlinking_codeが入っている。
  // linking-code-delivery-method-decision.mdの決定により、確認メール送信で顧客に届ける
  // (サンクスページ表示・独自LPはいずれも不採用)。
  var linkingCode = JSON.parse(response.getContentText()).linking_code;
  console.log("issued linking_code=" + linkingCode + " for email=" + email);
  sendLinkingCodeConfirmationEmail(email, businessName, linkingCode);
}

/**
 * linking-code-delivery-method-decision.md 5節の決定に基づき、発行済みlinking_codeを
 * 確認メールで送信する。MailApp.sendEmail()が失敗しても例外を外へ伝播させず、ログのみ
 * 残す(連携コード自体はFirestore pending_linksに発行済みのため、メール送信失敗時も
 * オーナーがGAS実行ログを確認して手動でコードを伝える代替手段が残る)。
 */
function sendLinkingCodeConfirmationEmail(email, businessName, linkingCode) {
  var props = PropertiesService.getScriptProperties();
  var serviceName = props.getProperty("SERVICE_DISPLAY_NAME");
  var addFriendUrlOrQr = props.getProperty("LINE_ADD_FRIEND_URL");

  var subject = "【" + serviceName + "】お申込み内容の確認と連携コードのご案内";
  var body =
    businessName + " 様\n\n" +
    "お申込みフォームよりご回答いただき、ありがとうございます。\n" +
    "LINE公式アカウントとの連携のため、以下の手順をお願いいたします。\n\n" +
    "1. LINE公式アカウント「" + serviceName + "」を友だち追加してください。\n" +
    "   " + addFriendUrlOrQr + "\n" +
    "2. 友だち追加後、最初のトークで下記の連携コードをそのまま送信してください。\n\n" +
    "   連携コード: " + linkingCode + "\n\n" +
    "連携コードは発行から24時間以内のみ有効です。時間が経過した場合は、\n" +
    "お手数ですが再度お申込みフォームよりご回答ください。\n\n" +
    "ご不明点がございましたら、本メールへの返信、またはLINE公式アカウントの\n" +
    "トークにてお問い合わせください。";

  try {
    MailApp.sendEmail(email, subject, body);
  } catch (err) {
    console.error(
      "linking_code confirmation email failed: email=" + email +
      " error=" + err
    );
  }
}
```

## 残課題

- 質問文の部分一致によるマッピングは、フォーム編集時の文言変更に弱い(質問文を
  「屋号」を含まない文言に変えると取りこぼす)。実デプロイ時にフォーム項目の文言を
  最終確定させ、本コードのマッピング文字列もそれに合わせて確定させる必要がある
  (承認後の着手事項)。
- (解消済み・フェーズ317: linking-code-delivery-method-decision.mdにて確認メール送信
  〈`MailApp.sendEmail()`〉を採用する決定を行い、`sendLinkingCodeConfirmationEmail()`を
  上記コード草案に追記した。`SERVICE_DISPLAY_NAME`・`LINE_ADD_FRIEND_URL`の実値は
  ローンチ・LINE公式アカウント開設時に確定させる必要がある点が残課題として残る)。
- 本コード自体はApps Scriptエディタに貼り付けて初めて動作確認できるため、
  本リポジトリ内では構文・ロジックの机上レビューまでに留まる(実行環境を
  持たないため自動テスト対象外。Cloud Functions側の
  `application_form_submission_http_entry.py`・`cloud_function_application_form_
  submission.py`は`python3 -m unittest`で検証可能)。
