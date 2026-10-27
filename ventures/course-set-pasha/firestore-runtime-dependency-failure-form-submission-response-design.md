# 申込フォーム提出エントリポイント: Firestoreランタイム依存構築失敗時のレスポンス設計(フェーズ338)

aircon-pashaフェーズ347(`firestore-runtime-dependency-failure-form-submission-response-
design.md`)5節で「他venture(course-set-pasha・kura-pasha)のうち、Googleフォーム経由の
申込チャネルを持つのはcourse-set-pashaのみであり、同種の欠落が無いかの確認は
course-set-pasha側の次回候補として記録する」と残されていた。本フェーズで確認し、実際に
同種の欠落が存在することを確認したため設計する。

## 1. 欠落の確認

application-form-submission-http-entry-point-design.md 3節は200/401/400の3パターンのみを
定義し、依存構築(`cloud_function_application_form_submission.
get_application_form_submission_runtime_dependencies()`)自体が失敗した場合の
`main(request)`側レスポンスが未定義のまま残っていた(aircon-pashaフェーズ347時点と同型の
欠落)。cloud-monitoring-alert-policy-design.md 5節(フェーズ335)は構築失敗時のログベース
指標・アラートポリシー自体は既に本ventureの申込フォーム関数を含めて定義済みだが、
その例外を`main()`側がHTTPレスポンスとしてどう返すかは別論点として残っていた。

## 2. 呼び出し元の確認: aircon-pashaと同じGAS経由のサーバー間リクエスト

本venture申込フォーム経路もapplication-form-submission-http-entry-point-design.md 2節の
通り、Google Apps Script(GAS)の`onFormSubmit`トリガーが`UrlFetchApp.fetch()`で送信する
サーバー間リクエストであり、申込者(クライミングジム利用者)本人がこのHTTPレスポンスを
直接目にすることはない。したがってaircon-pashaフェーズ347と同じ前提が成立し、
forklift-pasha版のような人間向け案内HTMLは不要である。

## 3. aircon-pasha版との相違点: レスポンス形状

aircon-pasha版は200時に発行した`linking_code`自体をHTTPレスポンスに含める必要がある
(フォーム送信が連携コードの発行契機そのものであるため)ため、レスポンスは
`{"ok", "linking_code", "error"}`の3キー構成だった。

これに対し本venture側は、application-form-submission-http-entry-point-design.md 1節の
通り「フォーム入力はLINE友だち追加時に発行済みの連携コードを受け取ってuser_idを解決する」
構成であり、フォーム送信自体は連携コードを発行しない。実際に
`application_form_submission_http_entry.FormSubmissionReceiveResult.to_json_body()`の
実装(`prototype/application_form_submission_http_entry.py`)を確認したところ、既存の
200/401/400レスポンスはいずれも`{"ok": bool, "error": str|null}`の2キー構成のみで
`linking_code`キーを持たない。よって503時もこの既存2キー構成を維持し、新たに
`linking_code`キーを追加しない。

```python
def main(request):
    try:
        dependencies = get_application_form_submission_runtime_dependencies()
    except Exception:
        # get_application_form_submission_runtime_dependencies() は
        # cloud-monitoring-alert-policy-design.md 5.1節の方針通り、構築失敗時に
        # logger.exception(...) で先にログ出力してから再raiseする。
        # main() 側のcatch追加はこのログ出力・ログベース指標には影響しない。
        return {"ok": False, "error": "internal_error"}, 503

    body = request.get_data()
    secret_header = request.headers.get("X-Form-Webhook-Secret")
    result = receive_application_form_submission(
        body, secret_header, expected_secret, now=..., **dependencies,
    )
    return result.to_json_body(), result.status_code
```

- `error`文言は技術的詳細(Firestore・GCP等の語)を含まない固定値`"internal_error"`とする
  (aircon-pashaフェーズ347・forklift-pashaフェーズ194と同じ考え方)。
- ステータスコードは401(シークレット不一致)・400(ペイロード検証エラー)とは意味を
  区別し503(Service Unavailable)とする。

## 4. 実際の申込者への影響: aircon-pasha版より影響範囲は狭いが「無言で取り残される」点は同じ

aircon-pasha版は「`linking_code`が発行されなければ申込者はLINE連携自体を完了できない」
という重大な影響だったが、本venture側は既にLINE連携が確立済みの利用者が追加情報
(`gym_area_pairs_raw`・`email`)を送信する局面であるため、503発生時もLINE連携状態自体は
既存のまま維持され、連携そのものが不可能になるわけではない。失われるのは「ジム・エリア
希望の登録内容」のみであり、影響範囲はaircon-pasha版より狭い。

ただし、401(シークレット不一致、設定ミス起因)・400(入力内容自体に起因し再入力で解消
しうる)とは異なり、503は申込者が正しく入力・送信したにもかかわらず本venture側の一時的な
不具合でジム・エリア希望が記録されない事象であり、「ログに残すのみ」(application-form-
submission-http-entry-point-design.md 5節が401/400について整理した扱い)を503にそのまま
流用するのは、aircon-pasha版と同じ理由で不適切と判断する。

## 5. 対応方針: aircon-pashaフェーズ347と同一の結論を採用

呼び出し元の構成(GAS `UrlFetchApp.fetch()`、自動リトライ機構を持たない)・本Cloud
Function側に自己リトライロジックを追加するのが過剰である点は、いずれもaircon-pasha版と
同一の事情であるため、本venture固有の検討を新たに行う必要はなく、同じ結論を採用する。

- Cloud Function側は2節のJSON 503レスポンスを返すのみとする。
- GAS側`onFormSubmit`トリガー内で`UrlFetchApp.fetch()`を最大3回・指数バックオフ
  (`Utilities.sleep()`、1秒→2秒→4秒)でリトライし、3回とも503(または例外)であれば
  GAS側`Logger.log()`に記録して終了する方針を`gas-script-draft.md`への反映対象とする
  (人間が必ず確認するログ監視導線の新設は、Googleフォーム+GAS Webhook自体の承認待ち事項
  〈pending-approval.md記載〉の範囲内で検討する次回候補として残す)。

## 6. 残課題

- 本`main()`側catch追加・JSON 503レスポンスの実`.py`実装への反映、およびGAS側リトライ
  ループの`gas-script-draft.md`への追記は、他venture同様、実Firestore導入・Googleフォーム+
  GAS Webhook自体の結合実装フェーズ(承認後)とセットで着手する(本フェーズは設計のみ)。
- GAS側リトライが3回とも失敗した場合に、申込者本人に何らかの形で再試行を促す手段を設ける
  かは、実際の失敗頻度を観察してから判断する次回候補として残す(現時点ではCloud
  Monitoringアラート〈cloud-monitoring-alert-policy-design.md 5.2節〉がオーナー自身への
  通知手段として機能するため、申込者本人への追加導線は本フェーズ時点では必須と判断しない)。
- 本設計により、aircon-pashaフェーズ347の次回候補(「Googleフォーム経由の申込チャネルを
  持つ他venture〈course-set-pasha〉に同種の欠落が無いかの確認」)は解消済みとなる。
  kura-pasha・line-reservation-aiはLINE友だち追加起点のみでGoogleフォーム経由の申込
  チャネル自体を持たないため、本論点の対象外である(aircon-pashaフェーズ347時点で確認済み)。

最終更新: 2026-10-27 14:00 UTC(フェーズ338: aircon-pashaフェーズ347が次回候補として残した
「course-set-pasha側に同種の欠落が無いかの確認」に対応。application-form-submission-
http-entry-point-design.md 3節が200/401/400の3パターンのみを定義し、依存構築失敗時の
`main()`側レスポンスが未定義であることを確認し、aircon-pasha版と同じ503 JSON方針
(GAS側指数バックオフリトライ最大3回)を採用する一方、本venture側の既存レスポンス形状
(`{"ok", "error"}`の2キー、`linking_code`キーを持たない)との相違・影響範囲の違い
(LINE連携自体は既に確立済みのため連携不可にはならない)を明記した。コード変更なし
〈設計文書新規作成のみ〉、回帰確認として`python3 -m unittest discover -s prototype
-p "test_*.py"`(863件、変更なし)・`python3 schema/validate_test_cases.py`(21件、
変更なし)を実行しいずれもパスすることを確認した(回帰なし)。承認が必要なアクション
(支払い・アカウント作成・外部公開・送信等)は今回発生していないためpending-approval.md
への追記なし。)
