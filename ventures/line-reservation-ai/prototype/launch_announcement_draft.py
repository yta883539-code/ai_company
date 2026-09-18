#!/usr/bin/env python3
"""
launch-announcement-draft-design.mdを実行可能なコードに落とし込んだもの。

位置づけ: onboarding-guide.mdステップ5(本番公開・顧客への告知)を後押しする、
本サービスの主機能(予約対応)とは別スコープの追加機能。店舗名・友だち追加URL等の
店舗設定から、店頭POP文言・SNS告知文の下書きを組み立てる純粋関数のみで構成する
(LLM呼び出し・LINE送信・QRコード画像生成は持たない。design 2節参照)。

コマンド方式での配線本体(cloud_function_process_event.pyへの`_maybe_render_
launch_announcement_reply()`追加)はdesign 7節に基づき本フェーズで実施した
(is_launch_announcement_trigger()がそのトリガー判定を担う純粋関数)。
"""

from __future__ import annotations

MESSAGE_TONES = ("formal", "standard", "casual")

_GENERIC_HASHTAGS = ("#LINE予約", "#ネット予約")

# design 3節準拠。オーナーがトークルームに送るとPOP・SNS告知文の下書きを返す
# トリガーキーワード(owner_faq_router.pyの`_MENU_TRIGGER_KEYWORD`と同じ設計思想)。
_LAUNCH_ANNOUNCEMENT_TRIGGER_KEYWORD = "告知文"

# design 4.1節「LINE公式アカウントの友だち追加URL(必須、実LINE公式アカウント開設後に
# 確定するプレースホルダ)」準拠。kura-pashaのOWNER_LINE_USER_ID_PLACEHOLDER等と同じ
# 「実接続前は差し込み文字列のまま送ることを許容する」プレースホルダパターン。
FRIEND_ADD_URL_PLACEHOLDER = "{LINE公式アカウント友だち追加URL}"


def is_launch_announcement_trigger(text: str) -> bool:
    """本文が告知文下書き生成のトリガーキーワードと一致するか判定する。
    前後の空白は無視する。日本語キーワードのため大文字小文字の区別は行わない
    (owner_faq_router.is_owner_faq_menu_trigger()と対称の設計)。
    """
    return text.strip() == _LAUNCH_ANNOUNCEMENT_TRIGGER_KEYWORD


def _render_by_tone(tone: str, variants: dict) -> str:
    """未知のtone値はstandardにフォールバックする
    (onboarding_completion_message.pyと同じ安全側の挙動)。"""
    return variants.get(tone, variants["standard"])


def _brand_hashtag(store_name: str) -> str:
    return "#" + store_name.replace(" ", "").replace("　", "")


def render_launch_announcement_pop(
    store_name: str, friend_add_url: str, tone: str = "standard"
) -> str:
    """店頭POP用の下書きを組み立てる(design 4.2節)。"""
    if not store_name:
        raise ValueError("store_name must not be empty")
    if not friend_add_url:
        raise ValueError("friend_add_url must not be empty")

    templates = {
        "formal": """【LINEでのご予約を承っております】

{store_name}の空き状況確認・ご予約を、
お手持ちのLINEより24時間いつでも承っております。

▼ 友だち追加はこちらから
{url}

ぜひご利用くださいませ。""",
        "standard": """【LINEで予約できます】

{store_name}の空き状況確認・ご予約が、
お手持ちのLINEから24時間いつでもできるようになりました。

▼ 友だち追加はこちら
{url}

ぜひお試しください。""",
        "casual": """【LINEで予約できるようになりました✨】

{store_name}の空き状況チェック・予約が、
LINEでいつでもサクッとできちゃいます!

▼ 友だち追加はこちら
{url}

ぜひ使ってみてください!""",
    }
    template = _render_by_tone(tone, templates)
    return template.format(store_name=store_name, url=friend_add_url)


def render_launch_announcement_sns(
    store_name: str, friend_add_url: str, tone: str = "standard"
) -> str:
    """SNS告知文用の下書きを組み立てる(design 4.2節)。

    ハッシュタグは(1)一般ハッシュタグ・(2)店舗名ブランドタグの2種類とし、
    地域タグは店舗設定に地域名の項目が無いため含めない(design 4.2節・6節)。
    """
    if not store_name:
        raise ValueError("store_name must not be empty")
    if not friend_add_url:
        raise ValueError("friend_add_url must not be empty")

    templates = {
        "formal": """{store_name}のご予約が、LINEより承れるようになりました。
お電話が繋がりにくいお時間でも、いつでも空き状況をご確認・ご予約いただけます。

▼ 友だち追加はこちらから
{url}

{hashtags}""",
        "standard": """{store_name}のご予約が、LINEから簡単にできるようになりました🙌
お電話が繋がりにくい時間帯でも、いつでも空き状況を確認してご予約いただけます。

▼ 友だち追加はこちら
{url}

{hashtags}""",
        "casual": """{store_name}の予約、LINEでできるようになったよ〜📱
電話しづらい時間でも、いつでも空き状況チェック&予約OK!

▼ 友だち追加はこちら
{url}

{hashtags}""",
    }
    template = _render_by_tone(tone, templates)
    hashtags = " ".join((*_GENERIC_HASHTAGS, _brand_hashtag(store_name)))
    return template.format(store_name=store_name, url=friend_add_url, hashtags=hashtags)
