#!/usr/bin/env python3
"""access-token-reissue-design.md(フェーズ96〜102)が設計した`fleet_operator.accessToken`
フィールドの発行・再発行・読み取り、および`lastAccessedAt`(6節)の読み取り→表示用保持→
書き込み、を行う実ストアを実装する(README.mdフェーズ133「次回候補(2)」)。

位置づけ:
- 実Firestore接続はGCPプロジェクト作成(アカウント作成に該当)後の作業であり、
  pending-approval.md記載の既存承認待ち事項の範囲内のため、本モジュールでは
  trial_management.FleetOperatorStoreProtocol/InMemoryFleetOperatorStoreと同じ方針で
  Protocol + InMemory実装のみを用意する(新たな承認待ち事項ではない)。
- `trial_end_email_scheduler.AccessUrlProvider`はこれまで具象実装を持たなかった
  (常にNoneを返す未接続状態)。本モジュールの`AccessTokenStoreUrlProvider`がその
  具象実装となり、`AccessTokenStoreProtocol`から`https://<ドメイン>/f/{accessToken}`
  形式のURLを組み立てる。

設計の参照元: access-token-reissue-design.md
"""

from __future__ import annotations

import secrets
from datetime import datetime
from typing import Protocol


class AccessTokenStoreProtocol:
    """`fleet_operator/{internal_id}`の`accessToken`・`lastAccessedAt`フィールドの
    読み書きを模したProtocol(access-token-reissue-design.md 1節・6節)。実際のFirestore
    接続は未実装で、本venture内では`InMemoryAccessTokenStore`のみを実装として用意する
    (trial_management.FleetOperatorStoreProtocolと同じ方針)。
    """

    def get_access_token(self, internal_id: str) -> "str | None":
        raise NotImplementedError

    def set_access_token(self, internal_id: str, value: str) -> None:
        """上書き可(2節の再発行フロー・漏洩時に旧トークンを即時失効させるための書き換え)。
        trial_management.set_upgraded_at等と同じ「上書き可」方針。"""
        raise NotImplementedError

    def get_internal_id_by_access_token(self, access_token: str) -> "str | None":
        """アクセスURL受信時のドキュメント特定(1節、`accessToken`フィールドへの単一
        フィールドクエリ相当)。旧トークンでの照会は常にNoneを返す(=2節4.の「自然な失効」)。
        """
        raise NotImplementedError

    def get_last_accessed_at(self, internal_id: str) -> "datetime | None":
        raise NotImplementedError

    def set_last_accessed_at(self, internal_id: str, value: datetime) -> None:
        """上書き可。呼び出し側は6節「表示方法」の順序(読み取り→表示用に保持→書き込み)を
        守ること(本Protocol自体は読み取りと書き込みを同時に行わない)。"""
        raise NotImplementedError


class InMemoryAccessTokenStore(AccessTokenStoreProtocol):
    """`fleet_operator`の`accessToken`・`lastAccessedAt`フィールドを模したInMemory実装
    (Firestore接続は未実装のまま)。"""

    def __init__(self) -> None:
        self._access_token: "dict[str, str]" = {}
        self._internal_id_by_access_token: "dict[str, str]" = {}
        self._last_accessed_at: "dict[str, datetime]" = {}

    def get_access_token(self, internal_id: str) -> "str | None":
        return self._access_token.get(internal_id)

    def set_access_token(self, internal_id: str, value: str) -> None:
        old = self._access_token.get(internal_id)
        if old is not None:
            # 2節4.: 旧トークンでの以降の照会は見つからない状態にする(自然な失効)。
            self._internal_id_by_access_token.pop(old, None)
        self._access_token[internal_id] = value
        self._internal_id_by_access_token[value] = internal_id

    def get_internal_id_by_access_token(self, access_token: str) -> "str | None":
        return self._internal_id_by_access_token.get(access_token)

    def get_last_accessed_at(self, internal_id: str) -> "datetime | None":
        return self._last_accessed_at.get(internal_id)

    def set_last_accessed_at(self, internal_id: str, value: datetime) -> None:
        self._last_accessed_at[internal_id] = value


def generate_access_token() -> str:
    """サーバー側ランダム発行(firestore-data-model.md「サーバー側ランダム発行」)。
    `secrets.token_urlsafe`はURLパス(`https://<ドメイン>/f/{accessToken}`)に安全に
    埋め込める文字集合を返すため採用する(推測不能性はpayment-identity-verification-
    design.mdが要求する水準を満たすデフォルトの32バイト長に委ねる)。"""

    return secrets.token_urlsafe(32)


def issue_initial_access_token(
    store: AccessTokenStoreProtocol, internal_id: str
) -> str:
    """Webフォーム初回登録時に1度だけ呼ぶ想定。既にトークンが存在する場合でも新規発行
    せず既存値を返す(trial_management.set_trial_start_atと同じ「初回のみ設定」方針。
    初回登録フローからの誤った二重呼び出しでURLが変わってしまう事故を防ぐ)。"""

    existing = store.get_access_token(internal_id)
    if existing is not None:
        return existing
    token = generate_access_token()
    store.set_access_token(internal_id, token)
    return token


def reissue_access_token(store: AccessTokenStoreProtocol, internal_id: str) -> str:
    """2節の再発行フロー(漏洩時・メールアドレス変更時)。常に新トークンを発行して
    上書きする(issue_initial_access_tokenと異なり「初回のみ」の制約は設けない)。"""

    token = generate_access_token()
    store.set_access_token(internal_id, token)
    return token


def record_access_and_get_previous(
    store: AccessTokenStoreProtocol, internal_id: str, now: datetime
) -> "datetime | None":
    """access-token-reissue-design.md 6節「表示方法」の順序を実装する。今回のアクセスで
    上書きする前の値(=前回アクセス時点の値)を読み取ってから書き込み、前回値を返す
    (読み取りと書き込みを同時に行うと「前回」の意味を失うため、1つの関数にまとめて
    呼び出し側に順序を誤らせないようにする)。"""

    previous = store.get_last_accessed_at(internal_id)
    store.set_last_accessed_at(internal_id, now)
    return previous


class AccessUrlProvider(Protocol):
    """trial_end_email_scheduler.AccessUrlProviderと同一の契約(構造的サブタイピングの
    ためProtocolを再掲。実体は同じ`get_access_url(internal_id) -> str | None`)。"""

    def get_access_url(self, internal_id: str) -> "str | None":
        ...


class AccessTokenStoreUrlProvider:
    """trial_end_email_scheduler.AccessUrlProviderの具象実装。`AccessTokenStoreProtocol`
    からトークンを読み取り、`https://<base_url>/f/{accessToken}`形式のURLを組み立てる。
    トークンが未発行(internal_idに対応するfleet_operatorがまだ存在しない等)の場合は
    Noneを返し、呼び出し側(render_trial_end_email_body等)の既存フォールバックに委ねる。
    """

    def __init__(self, store: AccessTokenStoreProtocol, base_url: str) -> None:
        self._store = store
        # 末尾スラッシュの有無による二重スラッシュ/欠落を避ける。
        self._base_url = base_url.rstrip("/")

    def get_access_url(self, internal_id: str) -> "str | None":
        token = self._store.get_access_token(internal_id)
        if token is None:
            return None
        return f"{self._base_url}/f/{token}"
