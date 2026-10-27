# 申込フォーム提出エントリポイント: Firestoreランタイム依存構築失敗時のレスポンス設計(フェーズ347)

cloud-monitoring-alert-policy-design.md 5節(フェーズ344)が定義した
`get_application_form_submission_runtime_dependencies()`の構築失敗ログ・アラート自体は
既に設計済みだが、その例外が`cloud_function_application_form_submission.main(request)`側で
どう処理されるか(forklift-pashaフェーズ194の「申込者向けエラー表示」設計に相当する部分)は
application-form-submission-http-entry-point-design.md 4節に未反映のまま残っていた
(同節は200/401/400の3パターンのみを定義し、依存構築自体が失敗した場合の扱いが欠落していた)。
本ファイルで設計する。

## 1. forklift-pashaフェーズ194との前提の違い: 呼び出し元がGASであり人間のブラウザではない

forklift-pashaの`get_checkout_runtime_dependencies()`は申込者が`<a href>`を直接クリックして
遷移する経路であり、レスポンス本文を人間がブラウザでそのまま目にするため、プレーンHTMLの
案内文を新設する必要があった。

本ventureの`get_application_form_submission_runtime_dependencies()`はこれと異なり、
application-form-submission-http-entry-point-design.md 3節の通り、呼び出し元はGoogle Apps
Script(GAS)の`onFormSubmit`トリガーが`UrlFetchApp.fetch()`で送信するサーバー間リクエストで
あり、申込者(クリーニング事業主等)本人がこのレスポンスを直接目にすることはない。申込者が
実際に見るのはGoogleフォーム自体の標準完了画面であり、これはフォーム送信と同時にブラウザ側で
表示され、`onFormSubmit`トリガー(送信後に非同期実行)の結果を待たずに確定している
(application-form-submission-http-entry-point-design.md 7節が既に指摘済みの制約と同じ)。
したがって本ventureでは、forklift-pasha版のような「人間向け案内HTML」を新設する必要はない。

## 2. 方針: 401/400と同じJSON形状で503を返す(`main()`側のcatchのみ追加)

`get_application_form_submission_runtime_dependencies()`自体(cloud-monitoring-alert-
policy-design.md 5.1節が参照する構築ロジック)は、他venture共通の方針(ログ出力の上で
例外を再raise、InMemoryへの自動フォールバック禁止)を維持し変更しない。
`cloud_function_application_form_submission.main(request)`側にのみ、依存構築呼び出しを囲む
catchを追加する。

```python
def main(request):
    try:
        dependencies = get_application_form_submission_runtime_dependencies()
    except Exception:
        # get_application_form_submission_runtime_dependencies() は
        # cloud-monitoring-alert-policy-design.md 5.1節の通り構築失敗時に
        # logger.exception(...) で先にログ出力してから再raiseする。
        # main() 側のcatch追加はこのログ出力・ログベース指標には影響しない。
        return {"ok": False, "linking_code": None, "error": "internal_error"}, 503

    raw_body = request.get_data()
    secret_header = request.headers.get("X-Form-Webhook-Secret")
    result = receive_application_form_submission(
        raw_body, secret_header, expected_secret, **dependencies,
    )
    ...
```

- レスポンス形状は既存の401/400(application-form-submission-http-entry-point-design.md
  4節)と同じJSONキー構成(`{"ok", "linking_code", "error"}`)に揃える。GAS側の
  受信コード(`UrlFetchApp`レスポンスのJSONパース)を401/400/503で分岐させずに共通化できる
  ようにするため。
- ステータスコードは403/400とは意味を区別し503(Service Unavailable)とする。401は
  共有シークレット不一致、400はペイロード検証エラーであり、いずれも「このリクエスト自体」に
  起因するのに対し、503は申込者(フォーム回答者)側に何の誤りもない一時的なサーバー側の
  不具合であるため。
- `error`文言は技術的詳細(Firestore・GCP等の語)を含まない固定値`"internal_error"`とする。
  GAS側が万一このフィールドをログ以外の用途(メール本文等)に転記しても技術詳細が漏れない
  ようにするため(forklift-pashaフェーズ194 3節と同じ考え方)。

## 3. 実際の申込者への影響: 401/400とは異なり「正しく入力した申込者」が無言で取り残される

application-form-submission-http-entry-point-design.md 5節は、401/400について「ログに残す
のみでフォーム回答者への追加のエラー表示は行わない(Googleフォーム自体の標準完了画面は
変更しない、MVPの割り切り)」と整理済みだが、503はこれと同じ扱いで済ませてよいかを
本フェーズで検討する。

- 401(シークレット不一致)は実運用上ほぼ発生しない設定ミス起因であり、400(検証エラー)は
  申込者が入力した内容そのものに起因するため、申込者側が再入力すれば解消しうる。
- これに対し503は、申込者が正しくフォームに入力・送信したにもかかわらず、本venture側の
  一時的な不具合によって`linking_code`が発行されない事象である。
  user-account-linking-design.md 2節の通り、この`linking_code`はLINE公式アカウントとの
  紐付けに必須であり、発行されなければ申込者はLINE連携を完了できず、サービスを利用開始
  できないまま放置される。401/400と同列に「ログに残すのみ」とするのは、申込者に何の
  落ち度もない失敗を無言で握り潰すことになり、401/400の整理をそのまま流用するのは不適切と
  判断する。

## 4. 対応方針: GAS側リトライをスクリプト内で実装し、本Cloud Function側では新たな通知導線を設けない

- Stripeのwebhookは自動再送機構を持つためforklift-pasha側は「再送に任せる」整理で足りたが、
  GASの`UrlFetchApp.fetch()`には自動リトライ機構が無い(`muteHttpExceptions: true`指定時は
  1回呼び出して結果を受け取るだけ)。したがって本venture側で何もしなければ、503は
  1回限りの呼び出し失敗がそのまま最終結果になる。
- 一方で、本Cloud Function側(Python)に新たなリトライ・通知ロジックを追加するのは過剰である
  (依存構築自体の信頼性はGCPプロジェクト・Firestore側の問題であり、関数内で自分自身を
  再試行しても解決しない)。リトライは呼び出し元であるGAS側スクリプト内で行うのが筋が良い。
- よって本フェーズでは、Cloud Function側は2節のJSON 503レスポンスを返すのみとし、
  GAS側`onFormSubmit`トリガー内で`UrlFetchApp.fetch()`を最大3回・指数バックオフ
  (`Utilities.sleep()`、例: 1秒→2秒→4秒)でリトライし、3回とも503(または例外)であれば
  GAS側で`Logger.log()`に記録して終了する方針とする(人間が必ず確認するログ監視導線を
  新設する承認待ちアクションにはしない。実際のログ監視〈スプレッドシートへの記録等〉を
  オーナーがGAS側で追加するかは、Googleフォーム+GAS Webhook自体の承認待ち事項
  〈pending-approval.md 2026-08-23 04:00 UTC記載〉の範囲内で検討する次回候補として残す)。

## 5. 残課題

- 本`main()`側catch追加・JSON 503レスポンスの実`.py`実装への反映、およびGAS側リトライループの
  `gas-script-draft.md`への追記は、他venture同様、実Firestore導入・Googleフォーム+GAS
  Webhook自体の結合実装フェーズ(承認後)とセットで着手する(本フェーズは設計のみ)。
- GAS側リトライが3回とも失敗した場合に、申込者本人に何らかの形で再試行を促す手段
  (フォーム回答の統計を定期確認する運用、あるいは別途のメール通知導線の新設)を設けるかは、
  実際の失敗頻度を観察してから判断する次回候補として残す(現時点ではCloud Monitoringアラート
  〈5節〉がオーナー自身への通知手段として機能するため、申込者本人への追加導線は本フェーズ
  時点では必須と判断しない)。
- 他venture(course-set-pasha・kura-pasha)のうち、Googleフォーム経由の申込チャネルを持つのは
  course-set-pashaのみ(kura-pasha・line-reservation-aiはLINE友だち追加起点のみでこの論点が
  発生しないことは本ファイル1節参照元の横展開調査〈application-form-submission-http-
  entry-point-design.md 1節〉で既に確認済み)。course-set-pasha側に同種の欠落が無いかの確認は
  本venture側の対応範囲外のため着手せず、course-set-pasha側の次回候補として記録するに留める。

最終更新: 2026-10-27 07:00 UTC(フェーズ347: application-form-submission-http-entry-point-
design.md 4節に欠落していた、Firestoreランタイム依存構築失敗時の`main()`側レスポンスを
新規設計。forklift-pashaフェーズ194(人間が直接レスポンスを見る`<a href>`起点)とは異なり
本venture申込フォーム経路の呼び出し元はGAS(`UrlFetchApp.fetch()`)であるため人間向けHTML
案内文は不要と判断し、既存401/400と同じJSON形状で503を返す方針とした。一方で401/400とは
異なり申込者本人に落ち度のない失敗である点を踏まえ、GAS側スクリプトでの指数バックオフ
リトライ(最大3回)を対応方針として設計した。コード変更なし〈設計文書新規作成のみ〉、回帰
確認として`python3 -m unittest discover -s prototype -p "test_*.py"`(789件、変更なし)・
`python3 schema/validate_test_cases.py`(25件、変更なし)を実行しいずれもパスすることを
確認した(回帰なし)。承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は
今回発生していないためpending-approval.mdへの追記なし。)
