#!/usr/bin/env python3
"""
get-result-page-http-entry-point-design.md(フェーズ112)3節で設計した、結果ページ
`/result/{draft_id}`への実GETリクエストを受け取る薄いCloud Functionsエントリポイント
(`get_result_page`関数)。

位置づけ:
- `cloud_function_submit_event_form.py`等と同じ「本体は依存注入でテスト可能、main(request)
  だけが実functions_frameworkリクエストオブジェクトを扱う薄い配線」構成を踏襲する。
- 実Firestore接続(`one_time_draft`コレクション)はいずれも実GCPプロジェクト作成
  (pending-approval.md記載、オーナー承認待ち)後の課題のため、現時点では
  `get_get_result_page_runtime_dependencies()`が検証用のInMemory実装を返す。承認・実接続後は
  この関数の中身を実Firestoreクライアントを返すように差し替えるだけで`main()`・
  `receive_result_page_request()`双方を変更せずに接続できる。

設計の参照元: get-result-page-http-entry-point-design.md
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from result_page_entry import receive_result_page_request  # noqa: E402
from stripe_webhook import InMemoryOneTimeDraftStore  # noqa: E402


def get_get_result_page_runtime_dependencies() -> dict:
    """main()が使う依存の既定値を組み立てる(他3関数の`get_submit_*_runtime_dependencies()`
    と対称の構成)。

    実Firestore接続はオーナー承認後でなければ構築できないため、現時点では検証用の
    InMemory実装を返す。呼び出しごとに新規生成されるため、実Cloud Functions環境でも
    呼び出しをまたいで状態(draft)が保持されない既知の限界が残る(他3関数同様、実接続後に
    解消される)。
    """
    return {"draft_store": InMemoryOneTimeDraftStore()}


def main(request):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定)。

    `request.path`(Flask Request互換オブジェクトの`.path`属性)を取り出し、
    `receive_result_page_request()`に委譲する。
    """
    deps = get_get_result_page_runtime_dependencies()
    result = receive_result_page_request(request.path, **deps)
    return result.to_json_body(), result.status_code


def _demo() -> None:
    class _StubRequest:
        def __init__(self, path: str) -> None:
            self.path = path

    body, status_code = main(_StubRequest("/result/draft_nonexistent"))
    print(f"body={body!r}, status_code={status_code}")


if __name__ == "__main__":
    _demo()
