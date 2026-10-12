#!/usr/bin/env python3
"""settings.html(フェーズ101・102)の「アクセスURLを再発行する」ボタン・
「新しいメールアドレス(変更する場合のみ入力)」欄の送信操作を、
access_token_store.reissue_access_token()・trial_management(fleet_operatorの
メールアドレス)への実際の呼び出しに配線する(README.mdフェーズ134「次回候補(2)」対応)。

位置づけ:
- settings.htmlの「新しいURLをメールで受け取る」ボタンはJS不使用のモックアップのため
  <button disabled>のままで、本モジュールへの実際の接続(HTTPエンドポイント化)は
  Webフォーム側のバックエンド実装(本venture全体の稼働に必須の前提である実Firestore
  接続・実ドメイン確定と同じ、オーナー承認待ち事項の範囲内)が整って初めて可能になる。
  本モジュールは、接続後に呼ばれることになる処理本体(リクエストの意味づけ・各ストアへの
  書き込み順序)を先に机上実装し、依存注入によるテストで動作を固めておく
  (trial_end_email_scheduler.py等と同じ「ロジック本体を先に作り、配線は承認後」の方針)。
- 実際の新アクセスURLのメール送信自体は行わない(既存の承認待ち事項、pending-approval.md
  2026-10-10 18:00 UTC記載の範囲内)。本モジュールは「次に送るべき宛先と本文に使うURL」を
  組み立てるところまでを担い、送信は呼び出し側(メール連携接続後、送信直前の毎回オーナー
  確認を経てのみ送信する既存運用)に委ねる。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from access_token_store import AccessTokenStoreProtocol, reissue_access_token


class _EmailFieldStoreProtocol(Protocol):
    """trial_management.FleetOperatorStoreProtocolの`get_email`/`set_email`のみを
    使うための最小Protocol(本モジュールは他のfleet_operatorフィールドを参照しない)。"""

    def get_email(self, internal_id: str) -> "str | None": ...

    def set_email(self, internal_id: str, value: str) -> None: ...


class _AccessUrlProviderProtocol(Protocol):
    """access_token_store.AccessUrlProviderと同一の契約(構造的サブタイピングのため再掲)。"""

    def get_access_url(self, internal_id: str) -> "str | None": ...


class ReissueRequestRejected(Exception):
    """新しいメールアドレスの入力値が不正な場合に送出する(トークンの再発行自体は
    まだ行っていない状態で止めるため、例外として扱う)。"""


@dataclass(frozen=True)
class ReissueRequestResult:
    internal_id: str
    new_access_url: "str | None"
    destination_email: "str | None"
    email_changed: bool


def _is_plausible_email(value: str) -> bool:
    """settings.html側は`type="email"`のブラウザバリデーションに委ねているだけなので、
    サーバー側でも「少なくとも`@`を含み前後に文字がある」程度の最小チェックを行う
    (厳密なRFC準拠の検証はせず、明らかな誤入力の弾き出しのみを目的とする)。"""

    if "@" not in value:
        return False
    local, _, domain = value.partition("@")
    return bool(local) and bool(domain) and "@" not in domain


def handle_reissue_request(
    access_token_store: AccessTokenStoreProtocol,
    email_store: _EmailFieldStoreProtocol,
    access_url_provider: _AccessUrlProviderProtocol,
    internal_id: str,
    new_email: "str | None" = None,
) -> ReissueRequestResult:
    """settings.htmlの確認メッセージ内「新しいURLをメールで受け取る」ボタン押下に対応する
    処理本体。access-token-reissue-design.md 2節の手順どおり、

    1. (メールアドレス変更欄に入力があれば先に)fleet_operatorのメールアドレスを更新する。
       アクセストークンの再発行より先にメールアドレスを確定させることで、再発行後に
       `destination_email`を読み直すだけで新アドレスが取れるようにする(読み取り→書き込みの
       順序を1関数に閉じ込め、呼び出し側が順序を誤れないようにするaccess_token_store.
       record_access_and_get_previous()と同じ考え方)。
    2. `reissue_access_token()`で新トークンを発行する(常に新規発行、旧トークンは
       access_token_store側の方針により自然に失効する)。
    3. 送信先メールアドレス(通常ケースは既存の登録アドレス、変更ケースは新アドレス)と、
       新しいアクセスURLを組み立てて返す。

    `new_email`が空文字列・空白のみ・Noneのいずれかの場合は「変更なし」とみなし、既存の
    登録アドレス宛への単純な再発行として扱う(settings.html「空欄のまま送信すると、現在
    登録されているメールアドレス宛に新しいURLを送ります」の仕様どおり)。
    """

    email_changed = False
    stripped_new_email = (new_email or "").strip()
    if stripped_new_email:
        if not _is_plausible_email(stripped_new_email):
            raise ReissueRequestRejected(
                f"新しいメールアドレスの形式が不正です: {new_email!r}"
            )
        email_store.set_email(internal_id, stripped_new_email)
        email_changed = True

    reissue_access_token(access_token_store, internal_id)

    return ReissueRequestResult(
        internal_id=internal_id,
        new_access_url=access_url_provider.get_access_url(internal_id),
        destination_email=email_store.get_email(internal_id),
        email_changed=email_changed,
    )
