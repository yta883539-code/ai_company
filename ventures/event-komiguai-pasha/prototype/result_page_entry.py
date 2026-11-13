#!/usr/bin/env python3
"""
get-result-page-http-entry-point-design.md(フェーズ112)で設計した、結果ページ
`/result/{draft_id}`への実GETリクエストを受け取り、`draft_id`抽出〜
`OneTimeDraftStoreProtocol.get()`への委譲〜`status`別のレスポンス整形までを行う
受信処理の本体。

位置づけ:
- `inquiry_form_http_entry.receive_inquiry_form_submission()`等と同じ「本体はdict/文字列
  のみを扱い実クラウド接続なしでテスト可能、`main(request)`だけが実`functions_framework`
  リクエストオブジェクトを扱う薄い配線」構成を踏襲する(薄い配線側は
  `cloud_function_get_result_page.py`)。
- 既出3関数(POSTでJSON本文を受け取る)と異なり本関数はGETでURLパスのみから`draft_id`を
  取り出す点が構成上唯一の差異(design 2節)。

設計の参照元: get-result-page-http-entry-point-design.md、
prototype/stripe_webhook.py(OneTimeDraft・OneTimeDraftStoreProtocol)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

# design 2節2点目で列挙した、ドキュメントが存在する場合にそのままpage_stateへ転用する
# status値(statusの文字列表現をpage_state名としても使う)。
_PASSTHROUGH_STATUSES = frozenset(
    {
        "out_of_scope",
        "insufficient_input",
        "generation_failed",
        "refunded",
        "expired_after_payment",
    }
)

# design 2節2点目「awaiting_payment」: 決済待ち・決済済み生成中を、`page_state`としては
# 引き続き"generating"に統合する(利用者への表示文言自体は区別しない、design 4節の
# フェーズ114決定を参照)。ただし裏側のstatus値はstripe_webhook.mark_payment_confirmed()
# (フェーズ114)により"awaiting_payment"→"payment_confirmed"へ遷移するようになったため、
# 両方をここで列挙する。"awaiting_payment"はWebhook受信前に結果ページが開かれた場合の
# 理論上のケース(通常は決済完了後にのみ`success_url`へ遷移するため稀)として残す。
_GENERATING_STATUSES = frozenset({"awaiting_payment", "payment_confirmed"})


@dataclass
class ResultPageResult:
    """`receive_result_page_request()`の結果。design 2節のレスポンス形状
    (`{"ok": true, "page_state": str, "output": dict|None}`、draft_id抽出失敗時のみ
    `{"ok": false, "error": str}`)とHTTPステータスコードを両方保持する。"""

    status_code: int
    body: dict

    def to_json_body(self) -> str:
        return json.dumps(self.body)


def _extract_draft_id_from_path(request_path: str) -> Optional[str]:
    """`/result/{draft_id}`形式のパスから末尾セグメント(`draft_id`)を取り出す。

    `/`区切りの空セグメント(先頭・末尾のスラッシュ、連続スラッシュ)はすべて無視する。
    `draft_id`部分が存在しない場合(例: 空文字列・`/result`・`/result/`)は、空でない
    セグメントが1個以下になるため`None`を返す(`/result/{draft_id}`は常に2セグメント
    以上になる前提)。
    """
    if not request_path:
        return None
    segments = [segment for segment in request_path.split("/") if segment]
    if len(segments) < 2:
        return None
    return segments[-1]


def receive_result_page_request(request_path: str, *, draft_store) -> ResultPageResult:
    """design 2節の処理順序(draft_id抽出 → `draft_store.get()`への委譲 → status別の
    レスポンス整形)を実装する。

    - `request_path`から`draft_id`を抽出できない場合(想定外の呼び出し)は400を返す。
    - いずれの`page_state`でも200を返す(design 2節: ドキュメント不存在〈TTL失効〉時も
      通常の404ではなく専用の案内へ分岐させるため)。
    """
    draft_id = _extract_draft_id_from_path(request_path)
    if draft_id is None:
        return ResultPageResult(
            status_code=400,
            body={"ok": False, "error": "draft_id could not be extracted from request path"},
        )

    draft = draft_store.get(draft_id)
    if draft is None:
        return ResultPageResult(
            status_code=200,
            body={"ok": True, "page_state": "ttl_expired_or_invalid", "output": None},
        )

    status = draft.status
    if status == "generated" or status in _PASSTHROUGH_STATUSES:
        return ResultPageResult(
            status_code=200,
            body={"ok": True, "page_state": status, "output": draft.generated_output},
        )

    if status in _GENERATING_STATUSES:
        return ResultPageResult(
            status_code=200,
            body={"ok": True, "page_state": "generating", "output": None},
        )

    # design上は到達しない想定(未知のstatus値)だが、クラッシュさせず防御的にgeneratingへ
    # フォールバックする(他venture共通の「想定外は安全側」方針を踏襲)。
    return ResultPageResult(
        status_code=200,
        body={"ok": True, "page_state": "generating", "output": None},
    )


def _demo() -> None:
    from stripe_webhook import InMemoryOneTimeDraftStore

    store = InMemoryOneTimeDraftStore()
    store.create_draft("draft_abc123", event_memo={"capacity": "300人"})
    store.mark_generation_result(
        "draft_abc123",
        status="generated",
        output={"status": "generated", "checklist": []},
    )
    result = receive_result_page_request("/result/draft_abc123", draft_store=store)
    print(f"status_code={result.status_code}, body={result.to_json_body()}")


if __name__ == "__main__":
    _demo()
