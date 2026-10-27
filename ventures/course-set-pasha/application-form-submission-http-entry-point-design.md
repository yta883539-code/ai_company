# 申込フォーム提出フロー: Cloud Functions HTTPエントリポイント設計

作成日: 2026-10-13(フェーズ295)

## 1. 背景・残っていた欠落

- application-form-submission-flow-design.md(フェーズ76)は`handle_form_submission()`
  (`user_id`直接受領版)の設計・実装までで止まっていた。
- その後line-user-id-linking-design.md(フェーズ77)で「フォーム入力はuser_id直接入力ではなく
  連携コード(6文字)」に設計変更され、`user_id_linking.py`に
  `handle_form_submission_with_linking_code()`(連携コード→user_id解決→
  `handle_form_submission()`への委譲)まで実装・テスト済みだった。
- しかし、他の全Cloud Function(`cloud_function_webhook.py`・
  `cloud_function_send_deletion_candidate_final_confirmations.py`等)が備える
  「実`functions_framework`リクエストオブジェクトを受け取る薄い`main(request)`配線」が
  申込フォーム提出経路にだけ存在せず、`handle_form_submission_with_linking_code()`を
  実際のGAS Webhook POSTリクエストから呼び出す経路が未設計のまま放置されていた
  (本フェーズの棚卸しで発見)。本ドキュメントはこの欠落を埋める。

## 2. 認証方式(共有シークレット)

- 本venture内の他Webhook(LINE: `X-Line-Signature`によるHMAC署名検証、Stripe:
  `stripe_webhook.py`の署名検証)はいずれも送信元プラットフォームが提供するHMAC署名方式を
  持つが、Google Apps Script(GAS)の`UrlFetchApp.fetch()`にはそのような標準署名機能が無い。
- MVPとしては、GAS側`PropertiesService`(スクリプトプロパティ、GASエディタ上で手動設定・
  コードにハードコードしない)に保存した共有シークレット文字列を、GASが
  `UrlFetchApp.fetch(url, {headers: {"X-Form-Webhook-Secret": secret}, ...})`で
  リクエストヘッダに載せて送信し、Cloud Function側は環境変数
  `FORM_WEBHOOK_SHARED_SECRET`(LINE_CHANNEL_SECRETと同じ、実デプロイ時にオーナーが
  Cloud Functions環境変数として設定する想定)と比較する方式を採用する。
  - 比較は`hmac.compare_digest()`でタイミング攻撃を避ける(定数時間比較)。
  - 一致しない場合は401を返し、`handle_form_submission_with_linking_code()`へは
    処理を進めない(ペイロード検証より認証を先に行う)。
  - シークレット自体の値の生成・設定作業(GAS Script Properties設定・Cloud Functions
    環境変数設定)は外部サービス側の実設定操作であり、GASアプリ自体の登録
    (pending-approval.md記載の承認待ち事項3「LIFFアプリ登録」とは別件、Googleフォーム+
    GAS Webhook自体は同事項2「Googleフォーム作成 + GAS Webhook設定」の範囲)と合わせて
    オーナー承認後に行う。本ドキュメント・実装はロジック設計のみで新たな承認待ち事項を
    追加するものではない。

## 3. リクエスト・レスポンス形状

- リクエスト: `POST`、JSON本文
  ```json
  {
    "linking_code": "7K9XPQ",
    "gym_area_pairs_raw": "クライミングジムA/○○区, ボルダリングジムB/△△市",
    "email": "owner@example.com"
  }
  ```
  ヘッダ: `X-Form-Webhook-Secret: <共有シークレット>`
- レスポンス(すべてJSON本文、`{"ok": bool, "error": str|null}`):
  - 200: 書き込み成功。
  - 401: `X-Form-Webhook-Secret`ヘッダ欠落または不一致。
  - 400: JSON本文が不正(パース不能)、または`linking_code`/`email`の検証エラー
    (`handle_form_submission_with_linking_code()`・`resolve_linking_code()`が
    返すエラー文言をそのまま使う)。
- GAS側は本レスポンスのHTTPステータスをログに残すのみで、フォーム回答者への追加の
  エラー表示は行わない(Googleフォーム自体の標準完了画面を変更しない、MVPの割り切り)。
  再試行が必要な場合(401等)はオーナーが手動でGAS実行ログを確認する運用とする。

## 4. プロトタイプ実装方針

- `application_form_submission_http_entry.py`(新規)に、実クラウド接続なしで検証可能な
  `receive_application_form_submission(raw_body, secret_header, expected_secret,
  profile_store, linking_store, now) -> FormSubmissionReceiveResult`を実装する。
  `cloud_function_webhook.receive_webhook()`と同じ「本体はdict/bytesのみを扱いテスト可能、
  `main(request)`だけが実`functions_framework`オブジェクトに依存する」構成を踏襲する。
  `user_id_linking.py`・`application_form_submission_flow.py`の双方に依存するため、
  循環import回避のためどちらのモジュールにも追記せず新規ファイルとした。
- `cloud_function_application_form_submission.py`(新規)に薄い`main(request)`を実装する。
  `request.get_data()`でbytesを取得、`request.headers.get("X-Form-Webhook-Secret")`で
  ヘッダを取得、環境変数`FORM_WEBHOOK_SHARED_SECRET`(未設定時は空文字列、
  `cloud_function_webhook.main()`の`LINE_CHANNEL_SECRET`未設定時と同じ安全側挙動)を
  読み、`receive_application_form_submission()`に委譲する。
- 実Firestore接続(`profile_store`・`linking_store`)は他Cloud Function同様、実GCP
  プロジェクト・Googleフォーム+GAS Webhook自体がオーナー承認待ちのため、現時点では
  `InMemoryUserProfileStore`・`InMemoryLinkingCodeStore`を返す
  `get_application_form_submission_runtime_dependencies()`を使う。

## 5. GAS側スクリプト草案

- 実際のGoogleフォーム作成・GASプロジェクトの作成・デプロイ自体はオーナー承認待ち
  (pending-approval.md承認待ち事項2)だが、承認後すぐに貼り付けられるよう、
  `onFormSubmit`トリガーで呼ばれる想定のGAS(`.gs`、JavaScript方言)コード草案を
  `gas-script-draft.md`に記録した(コード自体は実行・デプロイされておらず、
  リポジトリ内のテキストとして保持するのみ)。

## 6. 次回候補

- 承認待ち事項1〜5(launch-readiness-checklist.md参照)がオーナーから承認された場合、
  実シークレット値の環境変数設定・GASへの貼り付けから着手する。
- 他venture・アイデア領域の前進。
- [フェーズ338で対応済み] 本節が定義していなかった「依存構築
  (`get_application_form_submission_runtime_dependencies()`)自体が失敗した場合の`main()`
  側レスポンス」は、firestore-runtime-dependency-failure-form-submission-response-
  design.mdとして新規設計済み(既存401/400と同じ`{"ok", "error"}`のJSON形状で503を返し、
  GAS側スクリプトでの指数バックオフリトライを対応方針とした。aircon-pashaフェーズ347が
  次回候補として残した横展開確認への対応)。
