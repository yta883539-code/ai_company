#!/usr/bin/env python3
"""
onboarding-completion-message-design.md を、実行可能なコードに落とし込んだもの。

位置づけ:
- 「MVPの最低限必須項目が初めて全て揃ったか」を判定し1回だけ発火させる処理本体は
  store_profile_store.evaluate_onboarding_completion_message_dispatch()として
  実装済み(2026-08-30)。本モジュールはtrial_end_report_scheduler.pyと同じ役割分担
  (判断・整形ロジックのうちメッセージ文言の組み立て部分のみを担う)。
  判定→整形→LinePushClientでの実送信の配線本体は
  cloud_function_send_onboarding_completion_message.handle_onboarding_completion_
  message_dispatch()を参照(2026-08-31実装)。
- owner-settings-wireframe.mdのフォーム保存処理自体(Firestore書き込み・実UI)は
  ホスティング基盤確定後の配線が引き続き必要(design 4節・残課題、オーナー承認待ち)。

設計の参照元: onboarding-completion-message-design.md 3節・4節
"""

from __future__ import annotations

MESSAGE_TONES = ("formal", "standard", "casual")


def _render_by_tone(tone: str, variants: dict) -> str:
    """未知のtone値はstandardにフォールバックする
    (trial_end_report_scheduler.py/dunning_notification_scheduler.pyと同じ安全側の挙動)。"""
    return variants.get(tone, variants["standard"])


# design 3節のトーン別文言。トライアル終了レポート(trial_end_report_scheduler.py)と異なり
# 利用実績の集計値は持たず、決済ページURLのプレースホルダのみを埋め込む。
_MESSAGE_ONBOARDING_COMPLETION = {
    "formal": """【予約とれる君】設定が完了いたしました

営業情報・メニューのご登録、お疲れさまでございました。
これで顧客対応の準備が整いましたので、このままトライアルをお試しくださいませ。

なお、トライアル期間中でも、いつでも下記より有料プランへお切り替えいただけます。
ご登録いただくまでは自動課金されませんのでご安心ください。

▼ プランを見る・登録する
{決済ページURL}

ご不明点はこのトークルームにご返信くださいませ。""",
    "standard": """【予約とれる君】設定が完了しました

営業情報・メニューのご登録、お疲れさまでした。
これで顧客対応の準備が整いましたので、このままトライアルをお試しください。

なお、トライアル期間中でも、いつでも下記から有料プランへ切り替えられます。
ご登録いただくまでは自動課金されませんのでご安心ください。

▼ プランを見る・登録する
{決済ページURL}

ご不明点はこのトークルームにご返信ください。""",
    "casual": """【予約とれる君】設定完了しました🎉

営業情報・メニューの登録、おつかれさまでした!
これで顧客対応の準備はバッチリです。このままトライアルを試してみてくださいね。

トライアル中でも、いつでも下記から有料プランに切り替えられます。
登録するまでは自動課金されないので安心してください。

▼ プランを見る・登録する
{決済ページURL}

わからないことがあれば、このトークルームに返信してください!""",
}


def render_onboarding_completion_message(payment_page_url: str, tone: str = "standard") -> str:
    """design 3節のオンボーディング完了メッセージを組み立てる。

    payment_page_urlには、checkout-initiation-flow-design.md 5節の
    build_checkout_session_params()を呼び出すLIFFページのURL(実LIFF登録後に確定する
    プレースホルダ)を渡す想定。
    """
    if not payment_page_url:
        raise ValueError("payment_page_url must not be empty")
    template = _render_by_tone(tone, _MESSAGE_ONBOARDING_COMPLETION)
    return template.format(決済ページURL=payment_page_url)
