# Checkout Session発行時のFirestoreランタイム依存構築失敗、申込者向けエラー表示設計(フェーズ194)

cloud-monitoring-alert-policy-design.md 3節「スコープ外」の次回候補
「`get_checkout_runtime_dependencies()`で発生した場合の申込者向けエラー表示自体の
文面設計は、本ファイルの範囲外(承認後の結合実装フェーズでの別途検討)」に対応し、
本ファイルで設計する。

## 1. 課題: Webhook/定期スケジューラとは呼び出し元の性質が異なる

runtime-dependency-switching-design.md 5.3節は、フラグON時に実Firestoreクライアント
構築が失敗して例外が伝播した場合の挙動を呼び出し元別に整理済みだが、
`get_checkout_runtime_dependencies()`(チェックアウト起点、`checkout_session.main()`
経由)についてはWebhookエントリポイントと同じ「5xxレスポンスを返す」という整理に
留まっていた。しかし両者の呼び出し元の性質は異なる。

- Webhook(Stripe発、`get_stripe_runtime_dependencies()`): 呼び出し元はStripeの
  自動再送機構であり、人間が5xxレスポンスの内容を直接目にすることはない。
- チェックアウト起点(申込者発、`get_checkout_runtime_dependencies()`):
  plan-selection-submission-wiring-design.mdで確定した通り、申込者がブラウザ上で
  `<a href>`(プレーンなリンク)を直接クリックしてこのエンドポイントへ遷移する。
  したがってこのレスポンスの内容を人間の申込者がブラウザ画面でそのまま目にする。
  Cloud Functionsのデフォルトのエラーページ(定型の「Internal Server Error」相当の
  素のテキスト)をそのまま表示すると、申込者には「操作ミスなのか、サービス自体が
  終了したのか、再度試してよいのか」が一切伝わらず、申し込み自体を諦めてしまう
  離脱要因になり得る。

## 2. 方針: `main(request)`内で専用のcatchを追加し、申込者向けの案内文を返す

`get_checkout_runtime_dependencies()`自体(5.2節の擬似コード)は、方針5.1「例外は
握り潰さずそのまま伝播させる」を維持し、変更しない(`logger.exception(...)`による
Cloud Monitoring向けのログ出力・再raiseはそのまま)。本設計が変更するのは
`checkout_session.main(request)`側のみであり、`get_checkout_runtime_dependencies()`
呼び出しをtry/exceptで囲み、例外を捕捉した上で申込者向けの案内文を返す。

```python
def main(request):
    access_token = request.args.get("access_token")
    plan_id = request.args.get("plan")
    try:
        dependencies = get_checkout_runtime_dependencies()
    except Exception:
        # get_checkout_runtime_dependencies() has already logged via
        # logger.exception(...) before re-raising (5.2節); catching here only
        # changes what the applicant sees, it does not suppress that log line
        # or the Cloud Monitoring log-based metric derived from it.
        return APPLICANT_FACING_ERROR_HTML, 503

    result = create_checkout_session(access_token, plan_id, **dependencies)
    if result.status_code == 200:
        return result.checkout_session_params, 200
    return (result.error or "error"), result.status_code
```

- ステータスコードは503(Service Unavailable)とする。404(トークン無効)・400
  (不明なプランID)は申込者側の入力・リンクの誤りを示すのに対し、本件は申込者側に
  誤りがない一時的なサーバー側の不具合であるため、既存の2コードとは意味的に区別する。
- `get_checkout_runtime_dependencies()`内の`logger.exception(...)`は`try`ブロックに
  入る前ではなく関数内部で例外発生時に実行されるため、`main()`側でのcatch追加は
  1節のログベース指標・アラート発火には影響しない(ログ出力→再raise→`main()`での
  catchという順序であり、ログ出力自体は`main()`側の変更と独立している)。

## 3. 案内文(`APPLICANT_FACING_ERROR_HTML`)の下書き

`plan-selection.html`等本venture他ページがプレーンなHTML・CSSのみ(JS不使用)である
方針を踏襲し、本エラー画面もプレーンなHTMLとする。

```
現在、システムの一時的な不具合によりお申し込み手続きを完了できませんでした。

お手数ですが、少し時間をおいてから、もう一度このページの「このプランで申し込む」
ボタンを押し直してください。

このメッセージが繰り返し表示される場合は、下記の問い合わせ先までご連絡ください。
その際、表示されていたプラン名と、おおよその発生時刻を伝えていただけますと
確認がスムーズです。

問い合わせ先: [OWNER_SUPPORT_CONTACT_PLACEHOLDER]
```

- Stripeのwebhook(自動再送)とは異なり、チェックアウト起点では「自動的に再試行
  される」仕組みが無いため、申込者自身に「もう一度ボタンを押し直す」という具体的な
  再試行手段を明示する(Webhook側の案内文とは異なり、本venture側で新たに必要になる
  文面)。
- 障害の技術的な原因(Firestore・GCP等の語)は申込者向け文面に一切含めない
  (他「パシャっと」系venture・本venture他ページの通知文設計と同様、技術的詳細は
  運営者向け文書のみに記載する方針を踏襲)。
- 問い合わせ先(`OWNER_SUPPORT_CONTACT_PLACEHOLDER`)は、本venture他の設計文書
  (cloud-monitoring-alert-policy-design.md`OWNER_ALERT_EMAIL_PLACEHOLDER`等)と
  同様、実デプロイ・実問い合わせ窓口確定後にオーナー自身が設定する前提のプレース
  ホルダとする。

## 4. 残課題

- 本HTML文面の実`.py`実装への反映(`APPLICANT_FACING_ERROR_HTML`定数の実コード化・
  `main()`のtry/except追加)は、実Firestore導入・本venture用Firestoreアダプタの
  結合実装フェーズとセットで着手する(本フェーズは設計のみ)。
- 実際の問い合わせ窓口(メールアドレス・電話番号等)の確定は、承認待ち事項
  (pending-approval.md記載のStripeアカウント開設等)と合わせてオーナー自身が
  今後決定する。
- HTMLの見た目(CSS)を`web-form-mockup`配下の既存ページ(`plan-selection.html`等)
  とどこまで共通化するか(共通のエラーページテンプレートとして切り出すか、本
  エンドポイント専用の最小限のインラインスタイルで済ませるか)は、実装時に検討する
  次回候補として残す。
- `get_stripe_runtime_dependencies()`・`get_deletion_confirmation_runtime_
  dependencies()`・`get_trial_end_email_runtime_dependencies()`の3エントリポイントは
  いずれも人間が直接レスポンスを目にする呼び出し元ではない(Stripe自動再送/Cloud
  Loggingのみ)ため、本設計の対象外のまま5.3節の既存整理(5xxレスポンス/ログ記録の
  み)を維持する。

最終更新: 2026-10-27 05:00 UTC(フェーズ194: cloud-monitoring-alert-policy-design.md
3節で「本ファイルの範囲外」としていた、チェックアウト起点でのFirestoreランタイム
依存構築失敗時の申込者向けエラー表示を新規設計。`get_checkout_runtime_dependencies()`
自体の例外伝播方針〈5.1節〉は変更せず、`checkout_session.main()`側でのみ例外を
catchして申込者向けの再試行案内文(503)を返す方式とし、ログベース指標・アラート
発火への影響がないことを確認した。コード変更なし〈設計文書新規作成のみ〉、回帰確認
としてテスト93件・schema検証11件いずれも変更なしでパス)
