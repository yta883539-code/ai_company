#!/usr/bin/env python3
"""
customer-email-normalization-design.md(フェーズ56)で確定した、`customer_email`の
正規化・一致判定ロジック。draft-id-last4-collision-design.md(フェーズ53)4節の
二段階照合(末尾4文字で絞り込み→`customer_email`一致で確定)の2段目に使う。

決済経路(Stripe Checkout入力)と問い合わせ経路(問い合わせフォーム手入力)の
2回の入力で生じ得る表記揺れ(全角/半角・大文字小文字・前後の空白)を吸収する。
Gmailのドット無視・`+`エイリアス等プロバイダ固有の揺れは対象外(設計文書2節参照)。

実LLM呼び出し・実Firestore接続は行わない(オーナー承認待ちの範囲)。
"""

import unicodedata


def normalize_customer_email(raw: str) -> str:
    """NFKC正規化→前後の空白除去→小文字化、の順に適用する。"""
    normalized = unicodedata.normalize("NFKC", raw)
    return normalized.strip().lower()


def customer_emails_match(a: str, b: str) -> bool:
    """正規化後の文字列を比較する。正規化後にどちらかが空文字列になる場合はFalse。"""
    normalized_a = normalize_customer_email(a)
    normalized_b = normalize_customer_email(b)
    if not normalized_a or not normalized_b:
        return False
    return normalized_a == normalized_b
