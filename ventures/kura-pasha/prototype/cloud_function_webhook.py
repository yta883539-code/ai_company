"""kura-pasha LINE Messaging Webhook層の基盤部分(フェーズ62)。

trial-end-notification-design.md「6. 今後の課題」で繰り返し残っていた「本venture自体に
LINE Webhook層(cloud_function_webhook.py相当)が存在しない」というギャップに対応する
最初の一歩。aircon-pashaのwebhook-http-entry-point-design.md(フェーズ115)・
trial-end-condition-a-cta-design.md(フェーズ137)と同じ構成要素を踏襲するが、本venture側は
process_memo_event()本体(LLM呼び出し・schema/output.schema.jsonの17通りのstatus分岐を
テキスト返信へ変換する処理)がまだ存在しないため、本フェーズは以下の基盤部品のみに
スコープを絞る。

1. verify_line_signature(): 署名検証(line-reservation-ai/course-set-pasha/aircon-pashaと
   同じHMAC-SHA256実装)。
2. QuickReplyButton / ReplyClient / InMemoryReplyClient: 返信へpostbackボタンを添付する
   ための抽象化(aircon-pashaのReplyClient.quick_reply引数と同じ設計)。
3. format_trial_end_notification_message(): trial-end-notification-design.md 3節の
   通知文言を実装する(経路(A)生涯最初の生成完了時の返信への便乗、経路(B)期間到達時の
   プッシュ送信のいずれからも呼び出せる共通関数)。

process_memo_event()本体(LLM出力の17通りのstatus分岐をテキストへ変換する処理)・
receive_webhook()(HTTPエントリポイント)・dispatch_webhook_events()は本フェーズの対象外
とし、次の課題として残す(README.md参照)。実LINE Messaging API接続・実チャネルシークレット
の取得はいずれもオーナー承認待ち(pending-approval.md参照)のため、本モジュールは検証用の
InMemory実装にとどめる。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass
from typing import List, Optional, Protocol, Tuple

from checkout_session import START_CHECKOUT_POSTBACK_DATA


def verify_line_signature(
    body: bytes, signature_header: Optional[str], channel_secret: str
) -> bool:
    """line-reservation-ai/course-set-pasha/aircon-pashaと同じHMAC-SHA256実装。

    - signature_headerが空(None・空文字列)の場合は即False。
    - channel_secretでのHMAC-SHA256署名をBase64エンコードした値と、
      signature_headerをhmac.compare_digest()で比較する(タイミング攻撃対策)。
    - 実際のchannel_secretの値はLINE公式アカウント開設(アカウント作成、オーナー承認待ち)
      後に得られる値のため、検証ロジック自体はここで実装するが実運用の検証はその後になる。
    """
    if not signature_header:
        return False
    digest = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    return hmac.compare_digest(expected, signature_header)


@dataclass(frozen=True)
class QuickReplyButton:
    """テキスト返信・プッシュメッセージに添付するpostbackボタン1個分
    (trial-end-notification-design.md 3節・3.1節)。aircon-pashaの同名クラスと同じ設計だが、
    本ventureは複数プランの出し分け(aircon-pashaのcheckout-session-plan-selection-
    design.md相当)を採用していないため、ボタン1個分の単純な構造にとどめる。
    """

    label: str
    postback_data: str


class ReplyClient(Protocol):
    def reply(
        self,
        reply_token: str,
        message_text: str,
        *,
        quick_reply: Optional[QuickReplyButton] = None,
    ) -> None:
        """呼び出し自体が失敗した場合は例外を送出する契約とする(実LINE API接続は
        オーナー承認待ちのため未実装)。quick_replyが渡された場合、実装側はLINE
        Messaging APIのテキストメッセージオブジェクトに`quickReply.items`として
        1件分のpostbackアクションを追加する想定。"""
        ...


class InMemoryReplyClient:
    """実LINE API接続の代わりに送信内容を記録するだけの検証用クライアント。

    `sent`は`(reply_token, message_text)`の2要素タプル、quick_replyは別属性
    `quick_replies_sent`(indexが`sent`と対応)に記録する(aircon-pashaの
    InMemoryReplyClientと同じ方針)。
    """

    def __init__(self) -> None:
        self.sent: List[Tuple[str, str]] = []
        self.quick_replies_sent: List[Optional[QuickReplyButton]] = []

    def reply(
        self,
        reply_token: str,
        message_text: str,
        *,
        quick_reply: Optional[QuickReplyButton] = None,
    ) -> None:
        self.sent.append((reply_token, message_text))
        self.quick_replies_sent.append(quick_reply)


# trial-end-notification-design.md 3節。checkout_session.START_CHECKOUT_POSTBACK_DATA
# (フェーズ61、"action=start_checkout")と揃える(プラン未指定の汎用ボタン、
# parse_start_checkout_postback_data()がDEFAULT_CHECKOUT_PLANとして解釈する)。
TRIAL_END_BUTTON_LABEL = "有料プランへ進む"
TRIAL_END_QUICK_REPLY = QuickReplyButton(
    label=TRIAL_END_BUTTON_LABEL, postback_data=START_CHECKOUT_POSTBACK_DATA
)

# content-generation-time-estimate.md(フェーズ18)「1回あたり平均20分と仮定」の仮置き値。
_MINUTES_PER_GENERATION = 20


def format_trial_end_notification_message(generation_count: int) -> str:
    """trial-end-notification-design.md 3節の通知文言を組み立てる。

    generation_count: これまでの生成実績回数。経路(A)(生涯最初の生成完了)では常に1、
    経路(B)(30日間一度も生成されないまま期間到達)では常に0として呼び出す想定(design 2節)。
    0の場合は「浮いた事務作業時間の目安」の行を省略する(design 3節: 浮いた時間が0分と
    なり訴求にならないため省略する分岐)。ボタン本体(TRIAL_END_QUICK_REPLY)はLINEの
    quickReplyとして別途添付する想定のため、本文中には実際のURLやpostbackデータそのものを
    埋め込まない(aircon-pashaと同じ方針)。
    """
    if generation_count < 0:
        raise ValueError(f"generation_count must be >= 0: {generation_count!r}")
    lines = [
        "[鞍パシャッと] 無料トライアル、お疲れさまでした!",
        "",
        "これまでの生成実績:",
        f"・受注内容整理メモ・納品案内・お手入れ案内の生成: {generation_count}回",
    ]
    if generation_count > 0:
        minutes = generation_count * _MINUTES_PER_GENERATION
        lines += [
            "",
            f"浮いた事務作業時間の目安: 約{minutes}分(1回あたり平均20分と仮定、"
            "content-generation-time-estimate.md参照)",
        ]
    lines += [
        "",
        "引き続きご利用いただく場合は、下のボタンから有料プランをお選びください。",
        "このまま何もしなければ自動課金は発生せず、生成のみ一時停止となります。",
    ]
    return "\n".join(lines)


def _demo() -> None:
    print(format_trial_end_notification_message(1))
    print("---")
    print(format_trial_end_notification_message(0))
    print("---quick reply---")
    print(TRIAL_END_QUICK_REPLY)


if __name__ == "__main__":
    _demo()
