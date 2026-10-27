# Stripe WebhookエントリポイントのFirestoreランタイム依存構築失敗時のレスポンス設計(フェーズ348)

cloud-monitoring-alert-policy-design.md 5.2節(フェーズ344)は、`get_stripe_runtime_
dependencies()`を含む5つのランタイム依存ファクトリ全てを「Firestoreランタイム依存構築失敗」
アラートの対象として一括して定義済みだが、その構築例外が`stripe_webhook.main(request)`側で
どう処理されるかはstripe-webhook-http-entry-point-design.md(フェーズ127・150)に未反映の
まま残っていた(同文書は401(署名不正)・400(JSON不正/非dict)・200の3パターンのみを定義し、
`get_stripe_runtime_dependencies()`自体の構築失敗は扱っていない)。

本件は、フェーズ347がapplication-form-submission-http-entry-point-design.md向けに設計した
「Firestoreランタイム依存構築失敗時のmain()側レスポンス」と同種のギャップであり、
firestore-runtime-dependency-failure-form-submission-response-design.md 5節の次回候補
(1)「本venture側の他エントリポイントへの横展開」には明記していなかったが、同一venture内の
対称な欠落であるため本フェーズで対応する。

## 1. 前提の違い: 呼び出し元がStripe自身であり、Stripe側に自動再送機構が既にある

フェーズ347(申込フォーム版)はGASの`UrlFetchApp.fetch()`に自動リトライが無いことを前提に
GAS側スクリプトでの指数バックオフリトライ設計が必要だった。本venture・stripe_webhook.pyの
呼び出し元はStripe自身のWebhook配信機構であり、5xx応答(および2xx以外全般)に対する自動再送
(exponential backoff、最大3日間程度の再送期間)をStripe側が標準で備えている
(stripe-webhook-http-entry-point-design.md 4節コメント「Stripe側の再送ループを避けるため」が
既に前提としている仕組みと同じ)。したがって本件はforklift-pashaフェーズ194(人間のブラウザが
直接見る`<a href>`起点、案内HTML必須)・フェーズ347(GAS起点、GAS側リトライ必須)のいずれとも
異なり、呼び出し元側に新たな対応ロジックを設計する必要がない。

## 2. 方針: 既存401/400と同じ形(プレーン文字列+status_code)で503を返す(`main()`側のcatchのみ追加)

`get_stripe_runtime_dependencies()`自体(cloud-monitoring-alert-policy-design.md 5.1節が
参照する構築ロジック)は、他venture共通の方針(ログ出力の上で例外を再raise、InMemoryへの
自動フォールバック禁止)を維持し変更しない。`stripe_webhook.main(request)`側にのみ、依存構築
呼び出しを囲むcatchを追加する。

```python
def main(request):
    body = request.get_data()
    signature_header = request.headers.get("Stripe-Signature")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    try:
        dependencies = get_stripe_runtime_dependencies()
    except Exception:
        # get_stripe_runtime_dependencies() は cloud-monitoring-alert-policy-design.md
        # 5.1節の通り構築失敗時に logger.exception(...) で先にログ出力してから再raiseする。
        # main() 側のcatch追加はこのログ出力・ログベース指標には影響しない。
        return "internal_error", 503

    result = receive_stripe_webhook(body, signature_header, webhook_secret, **dependencies)

    if result.status_code == 200:
        return "OK", 200
    return (result.error or "error"), result.status_code
```

- 既存の401/400は`(result.error or "error"), result.status_code`というプレーン文字列+
  status_codeの形でレスポンスを返しており(JSON dict形ではない、application-form-submission
  版の`to_json_body()`とは異なる既存の実装形)、503も同じ形に揃える。Stripe側は配信結果の判定を
  HTTPステータスコードのみで行い(2xx以外は再送対象)、レスポンス本文は再送判定に使わないため、
  本文形式を揃える意味は主にログ上の一貫性のためである。
- `error`文言はapplication-form-submission版と同じく技術的詳細(Firestore・GCP等の語)を
  含まない固定値`"internal_error"`とする。

## 3. 401/400との扱いの違い: 503はStripe側の自動再送に任せてよい

stripe-webhook-http-entry-point-design.md 4節は401・400について「不正なリクエストへの余計な
処理を避ける」整理のみで、申込フォーム版5節のような「ログに残すのみで申込者への追加のエラー
表示は行わない」という利用者への影響の検討は行っていなかった(Stripe自身がHTTPクライアントで
あり人間の利用者が直接レスポンスを見る経路ではないため、そもそも検討の必要が薄かったと
考えられる)。

503についても同様に、Stripe側の自動再送が完了するまでの間、該当イベント(例:
`customer.subscription.deleted`)の処理が一時的に遅延するのみであり、フェーズ347の3節が
指摘した「申込者が正しく入力したにもかかわらず無言で取り残される」ような利用者への実害は
生じない(Stripe側の再送が成功すれば処理は完了する)。したがって、GAS側リトライのような
venture側での追加対応は不要と判断する。

## 4. 残課題

- 本`main()`側catch追加の実`.py`実装への反映は、他venture同様、実Firestore導入・実GCP
  プロジェクト作成(オーナー承認待ち)後の結合実装フェーズとセットで着手する(本フェーズは
  設計のみ)。
- cloud-monitoring-alert-policy-design.md 5.2節が列挙する残り3エントリポイント
  (`get_runtime_dependencies()`〈LINE webhook〉・`get_daily_checks_runtime_dependencies()`・
  `get_deletion_candidate_final_confirmation_runtime_dependencies()`)についても同種の欠落が
  各*-design.mdに無いか確認できていない。ただし`get_runtime_dependencies()`(LINE webhook)は
  現状常に空dict`{}`を返す設計(cloud_function_webhook.py内コメント参照)であり、何も構築
  しないため構築失敗自体が発生しない(本節の対象外)。残り2エントリポイントの確認は次回候補
  として残す。
- 他venture(course-set-pasha・forklift-pasha・kura-pasha・line-reservation-ai)のStripe
  Webhookエントリポイントに同種の欠落が無いかの確認は本venture側の対応範囲外のため着手せず、
  各venture側の次回候補として記録するに留める。

最終更新: 2026-10-27 09:00 UTC(フェーズ348: stripe-webhook-http-entry-point-design.mdに
欠落していた、Firestoreランタイム依存構築失敗時の`main()`側レスポンスを新規設計。呼び出し元が
Stripe自身であり標準の自動再送機構を備えるため、フェーズ347(GAS起点、GAS側リトライ必須)とは
異なりventure側での追加リトライ設計は不要と判断し、既存401/400と同じプレーン文字列形式で503を
返す方針とした。コード変更なし〈設計文書新規作成のみ〉、回帰確認として`python3 -m unittest
discover -s prototype -p "test_*.py"`(789件、変更なし)・`python3 schema/validate_test_cases.py`
(25件、変更なし)を実行しいずれも変更なしでパスすることを確認した(回帰なし)。承認が必要な
アクション(支払い・アカウント作成・外部公開・送信等)は今回発生していないためpending-
approval.mdへの追記なし。)
