# GAS(Google Apps Script)Webhook草案

作成日: 2026-10-13(フェーズ295、application-form-submission-http-entry-point-design.md 5節)

位置づけ: 実際のGoogleフォーム作成・GASプロジェクトのデプロイ自体はオーナー承認待ち
(pending-approval.md承認待ち事項2)。本ファイルはコード自体の実行・デプロイを一切伴わない、
承認後に貼り付けるためのテキスト草案。

## 前提

- Googleフォームの質問は3問: 「ジム名・地域名(任意、複数可、カンマ区切り)」
  「連絡先メールアドレス」「LINE連携コード(6文字)」(いずれも自由記述、
  onboarding-settings-and-self-check-design.md 1.・contact-email-field-design.md・
  line-user-id-linking-design.mdの設計通り)。
- GASプロジェクトの「スクリプト プロパティ」(Project Settings > Script properties)に、
  以下2つを事前設定する(コードにハードコードしない):
  - `ENDPOINT_URL`: デプロイ後のCloud FunctionsのHTTPS URL。
  - `SHARED_SECRET`: Cloud Functions側の環境変数`FORM_WEBHOOK_SHARED_SECRET`と
    同じ値(オーナーが生成・両方に設定)。
- フォームの「回答を送信するたびに通知を受け取る」トリガーではなく、
  エディタの「トリガー」設定で対象フォームの「フォーム送信時」`onFormSubmit`を
  紐付ける(application-form-submission-flow-design.md 1.が選定したGAS Webhook方式)。

## コード草案

```javascript
/**
 * Googleフォームの「フォーム送信時」トリガーに紐付ける関数。
 * application-form-submission-http-entry-point-design.md 3節のリクエスト形状に
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

  var gymAreaPairsRaw = "";
  var email = "";
  var linkingCode = "";
  for (var title in answers) {
    if (title.indexOf("ジム名") !== -1) {
      gymAreaPairsRaw = answers[title];
    } else if (title.indexOf("メールアドレス") !== -1) {
      email = answers[title];
    } else if (title.indexOf("連携コード") !== -1) {
      linkingCode = answers[title];
    }
  }

  var props = PropertiesService.getScriptProperties();
  var endpointUrl = props.getProperty("ENDPOINT_URL");
  var sharedSecret = props.getProperty("SHARED_SECRET");

  var payload = {
    linking_code: linkingCode,
    gym_area_pairs_raw: gymAreaPairsRaw,
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
    // design 3節の通りフォーム回答者への追加エラー表示は行わず、ログのみ残す。
    // オーナーがGAS実行ログ(実行数、表示: 拡張機能 > Apps Script > 実行数)を
    // 手動確認して個別対応する運用(MVPの割り切り)。
    console.error(
      "application form submission failed: status=" + statusCode +
      " body=" + response.getContentText()
    );
  }
}
```

## 残課題

- 質問文の部分一致によるマッピングは、フォーム編集時の文言変更に弱い(質問文を
  「ジム名」を含まない文言に変えると取りこぼす)。実デプロイ時にフォーム項目の文言を
  最終確定させ、本コードのマッピング文字列もそれに合わせて確定させる必要がある
  (承認後の着手事項)。
- GAS実行の失敗(401/400等)をオーナーへ能動的に通知する経路(例:
  失敗時にオーナー宛メール送信、`MailApp.sendEmail()`)は本草案では未実装。
  件数が少ない前提(低頻度のB2B申込)であれば定期的なログ確認で足りると判断し、
  MVPでは見送った。申込件数が増えた場合は再検討する(次回候補)。
- 本コード自体はApps Scriptエディタに貼り付けて初めて動作確認できるため、
  本リポジトリ内では構文・ロジックの机上レビューまでに留まる(実行環境を
  持たないため自動テスト対象外。Cloud Functions側の
  `application_form_submission_http_entry.py`・`cloud_function_application_form_
  submission.py`は`python3 -m unittest`で検証可能)。
