"""inquiry-form-http-entry-point-design.md(フェーズ109)4節で設計した、Firestore
`inquiry`コレクションへの書き込みを最小インターフェースとして抽象化するモジュール。

`firestore_idempotency_key_index_adapter.py`と同じ方針(実`google-cloud-firestore`
SDKをimportせず、`add(document_id, data)`の最小インターフェースのみに依存する)を踏襲する。
実際のFirestore接続は実GCPプロジェクト作成(pending-approval.md記載、オーナー承認待ち)後の
課題として残し、本モジュールは検証用のインメモリ実装のみを提供する。
"""

from __future__ import annotations


class InquiryCollectionProtocol:
    """`inquiry`コレクションへの書き込みを抽象化するインターフェース。"""

    def add(self, inquiry_id: str, document: dict) -> None:
        """`inquiry/{inquiry_id}`ドキュメントを新規作成する。呼び出し側
        (inquiry_form_http_entry.receive_inquiry_form_submission)は、
        `inquiry_form_intake.handle_inquiry_form_submission()`の戻り値の`document`が
        `None`でない場合のみ本メソッドを呼ぶ(重複検知時は再書き込みしない)。"""
        raise NotImplementedError


class InMemoryInquiryCollection(InquiryCollectionProtocol):
    """検証用のインメモリ実装(実Firestore接続は実GCPプロジェクト作成後の課題)。"""

    def __init__(self) -> None:
        self._documents: dict = {}

    def add(self, inquiry_id: str, document: dict) -> None:
        self._documents[inquiry_id] = document

    def get(self, inquiry_id: str):
        return self._documents.get(inquiry_id)
