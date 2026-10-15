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
  // design 2節の想定(サンクスページ表示・確認メール送信)は実装未着手(次回候補参照)。
  var linkingCode = JSON.parse(response.getContentText()).linking_code;
  console.log("issued linking_code=" + linkingCode + " for email=" + email);
}
```

## 残課題

- 質問文の部分一致によるマッピングは、フォーム編集時の文言変更に弱い(質問文を
  「屋号」を含まない文言に変えると取りこぼす)。実デプロイ時にフォーム項目の文言を
  最終確定させ、本コードのマッピング文字列もそれに合わせて確定させる必要がある
  (承認後の着手事項)。
- design 7節で記録した通り、Googleフォーム標準の完了画面はGAS onFormSubmitトリガー
  (送信後に非同期実行)からは動的に書き換えられない制約があるため、上記草案は
  `linking_code`をログに残すのみに留めている。design 2節が想定する「サンクスページへの
  表示」「確認メール送信」をどちらで実現するかは実デプロイ時に確定させる必要がある
  (`MailApp.sendEmail()`によるメール送信が最も現実的な候補)。
- 本コード自体はApps Scriptエディタに貼り付けて初めて動作確認できるため、
  本リポジトリ内では構文・ロジックの机上レビューまでに留まる(実行環境を
  持たないため自動テスト対象外。Cloud Functions側の
  `application_form_submission_http_entry.py`・`cloud_function_application_form_
  submission.py`は`python3 -m unittest`で検証可能)。
