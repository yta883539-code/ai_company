#!/usr/bin/env python3
"""
LLM構造化出力(schema/output.schema.json)を受け取った後に、プログラム側で機械的に
検証する後処理チェック。course-set-pasha/aircon-pashaのprototype/post_generation_checks.py
と同じ位置づけ(schema/validate_test_cases.pyのvalidate_cross_field_rulesが担う
「status値に応じたnull/非null依存関係」の検証だけでは拾えない、本文テキストの内容自体が
厳守事項を守っているかのヒューリスティック検証)。本venture固有の差分として、course-set-pasha
向けのSNS投稿文用絵文字ルール(1〜2個まで許容)ではなく、厳守事項8(絵文字は終始不使用)に
合わせて全出力本文で絵文字ゼロを求める点、およびincludes_checkout_url・includes_invite_code
がkindによらず常にfalseである(course-set-pashaには存在しないworkshop招待コード関連の)
設計のため、値の一致チェックではなく本文中に実際のURL・招待コードらしき文字列が
紛れ込んでいないかの絶対的な不在チェックとする点が異なる。

- ここでの検証はあくまでヒューリスティック(キーワード一致・正規表現によるパターン判定)
  であり、LLMの厳守事項違反を確実に検出できるわけではない。実LLM接続後は、ここで拾いきれない
  違反パターンの収集・ルール改善が引き続き必要になる(course-set-pasha/aircon-pashaと同じ限界)。
- 実LLM呼び出しは行わない(APIキー取得はオーナー承認待ち、pending-approval.md参照)。
"""

import re

# 厳守事項8の機械チェック用。course-set-pasha/post_generation_checks.pyのEMOJI_PATTERNと
# 同じ文字コード範囲を踏襲する(顔文字・記号・ピクトグラム等が集中する主要ブロックを
# 対象としたヒューリスティック)。
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"  # 各種絵文字・記号(顔・乗り物・アクティビティ等)
    "☀-➿"  # その他の記号・装飾記号(☀☕✨➿等)
    "⬀-⯿"  # 矢印・星等の追加記号(⭐⬛等)
    "\U0001F100-\U0001F1E5"  # 囲み英数字補助のうち地域指示記号と重複しない範囲(🅰🅱🅾🆚等)
    "\U0001F1E6-\U0001F1FF"  # 地域指示記号(組み合わせで国旗絵文字になる)
    "\U0001F200-\U0001F2FF"  # 囲みCJK文字・月間補助記号(🈚🈵🈲等)
    "️"  # 異体字セレクタ(絵文字表示指定)
    "‍"  # ゼロ幅接合子(複合絵文字)
    "]"
)

# 厳守事項6の機械チェック用。course-set-pasha/post_generation_checks.pyのOUT_OF_SCOPE_TOPIC_
# KEYWORDSを踏襲する(README.mdの前提「会員管理・予約受付・決済に関する高度な機能はMVPの
# 範囲外」への逸脱疑いを出現の有無のみで判定する)。
OUT_OF_SCOPE_TOPIC_KEYWORDS = (
    "会員", "入会", "退会", "予約", "決済", "支払い", "振込", "クレジットカード",
    "会費", "キャンセル",
)

# 厳守事項7a(iv)の機械チェック用。course-set-pasha/post_generation_checks.pyのPORTAL_
# KEYWORDSを踏襲しつつ、本venture固有のsubscription_procedure_notice本文(C1/C2の
# 「下記リンクから解約手続きをお願いいたします」)が実際に使う「リンク」を追加した。
PORTAL_KEYWORDS = ("カスタマーポータル", "ポータル", "マイページ", "決済ページ", "手続きページ", "リンク")
PROCEDURE_COMPLETION_KEYWORDS = ("手続き完了", "解約が完了", "手続きが完了", "解約は完了")

# 厳守事項7b(i)・7c(i)の機械チェック用。checkout_notice.body・workshop_invite_notice.bodyは
# includes_checkout_url・includes_invite_codeがkindによらず常にfalseの設計であるため、
# 実際のURL・URLプレースホルダが本文に紛れ込んでいないかを判定する。
LINK_PLACEHOLDER_PATTERN = re.compile(r"\{[^{}]*URL[^{}]*\}|https?://")
SHORT_URL_DOMAIN_PATTERN = re.compile(
    r"\b(?:bit\.ly|lin\.ee|tinyurl\.com|t\.co|x\.gd|is\.gd)/\S+"
)

# 厳守事項7c(i)の機械チェック用。craftsman-account-linking-design.md 2節・11.1節の招待コード
# 仕様(6文字、視認性の低い0/O・1/I/Lを除いた31種のアルファベット)と同じ文字集合からなる
# 6文字トークンが本文に登場していないかを判定する。実際の英単語・型番等との偶然一致もありうる
# ヒューリスティックだが、includes_invite_codeが常にfalseの設計を補強する目的では十分と判断する。
_INVITE_CODE_ALPHABET = "".join(
    c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" if c not in "0O1IL"
)
# \bは日本語(Unicode上は\w扱い)と直接隣接すると境界と判定されないため使わず、
# 前後がASCII英数字で連続していない(=独立した6文字トークンである)ことを
# 明示的な否定先読み・後読みで判定する。
INVITE_CODE_LOOKALIKE_PATTERN = re.compile(
    rf"(?<![A-Za-z0-9])[{_INVITE_CODE_ALPHABET}]{{6}}(?![A-Za-z0-9])"
)


def _collect_all_body_texts(instance):
    """厳守事項8(絵文字は終始不使用)の対象となる、全出力本文テキストを
    [(フィールド名, テキスト), ...]の形で集める。statusに関わらず、非nullの
    フィールドはすべて対象とする(course-set-pashaと異なりフィールドごとの絵文字
    許容個数の出し分けは無いため、statusによる絞り込みは不要)。"""
    texts = []

    order_summary = instance.get("order_summary")
    if order_summary:
        texts.append(("order_summary.body", order_summary.get("body", "")))

    delivery_notice = instance.get("delivery_notice")
    if delivery_notice:
        texts.append(("delivery_notice.body", delivery_notice.get("body", "")))

    care_notice = instance.get("care_notice")
    if care_notice:
        texts.append(("care_notice", care_notice))

    for field, (parent, key) in (
        ("subscription_procedure_notice", ("subscription_procedure_notice", "body")),
        ("member_retention_notice", ("member_retention_notice", "body")),
        ("contractor_transfer_notice", ("contractor_transfer_notice", "body")),
        ("contractor_transfer_confirmation", ("contractor_transfer_confirmation", "body")),
        ("contractor_transfer_expired_notice", ("contractor_transfer_expired_notice", "body")),
        ("checkout_notice", ("checkout_notice", "body")),
        ("workshop_invite_notice", ("workshop_invite_notice", "body")),
    ):
        obj = instance.get(parent)
        if obj:
            texts.append((f"{field}.{key}", obj.get(key, "")))

    return texts


def check_no_emoji_anywhere(instance):
    """厳守事項8準拠チェック。course-set-pashaのSNS投稿文向けルール(1〜2個まで許容)とは
    異なり、本ventureは職人向けの実務文書であるため全出力本文で絵文字ゼロを求める。
    """
    errors = []
    for field_name, text in _collect_all_body_texts(instance):
        if EMOJI_PATTERN.search(text):
            errors.append(
                f"{field_name}: 絵文字が含まれています(厳守事項8違反の疑い、本venture全体で絵文字不使用)"
            )
    return errors


def check_no_out_of_scope_topics_in_generated_output(instance):
    """厳守事項6準拠チェック。status=generatedのとき、order_summary.body・
    delivery_notice.body・care_noticeに会員管理・予約受付・決済に関する話題への言及が
    紛れ込んでいないかを確認する(course-set-pashaの同名関数と同じ設計思想)。
    """
    errors = []
    if instance.get("status") != "generated":
        return errors

    texts = []
    order_summary = instance.get("order_summary")
    if order_summary:
        texts.append(("order_summary.body", order_summary.get("body", "")))
    delivery_notice = instance.get("delivery_notice")
    if delivery_notice:
        texts.append(("delivery_notice.body", delivery_notice.get("body", "")))
    care_notice = instance.get("care_notice")
    if care_notice:
        texts.append(("care_notice", care_notice))

    for field_name, text in texts:
        for kw in OUT_OF_SCOPE_TOPIC_KEYWORDS:
            if kw in text:
                errors.append(
                    f"{field_name}: 会員管理・予約・決済に関する話題と疑われる語「{kw}」が"
                    "含まれています(厳守事項6違反の疑い)"
                )
    return errors


def check_delivery_notice_category_text_consistency(instance):
    """厳守事項4準拠チェック。delivery_notice.category=repairのとき、本文に「修理」という
    語が実際に登場しているか(修理箇所の説明を含める指示が守られているか)、逆に
    category=newのとき「修理」という語が紛れ込んでいないか(新規制作の案内に修理向けの
    文言が誤って混入していないか)を確認する。schema/validate_test_cases.pyの
    validate_cross_field_rulesはorder_summary.categoryとdelivery_notice.categoryの一致
    (フィールド値同士の整合性)のみを検証しており、本文の内容自体がcategoryに応じて
    出し分けられているかは未検証だった。
    """
    errors = []
    delivery_notice = instance.get("delivery_notice")
    if not delivery_notice:
        return errors

    category = delivery_notice.get("category")
    body = delivery_notice.get("body", "")
    mentions_repair = "修理" in body

    if category == "repair" and not mentions_repair:
        errors.append(
            "delivery_notice: category=repairだが本文に「修理」への言及が見つかりません"
            "(厳守事項4違反の疑い)"
        )
    if category == "new" and mentions_repair:
        errors.append(
            "delivery_notice: category=newだが本文に「修理」への言及が含まれています"
            "(厳守事項4違反の疑い、修理向け文言の混入疑い)"
        )
    return errors


def check_subscription_notice_consistency(instance):
    """厳守事項7a(iv)準拠チェック。course-set-pasha/post_generation_checks.pyの
    check_subscription_notice_consistency()と同じ設計。kind=cancellation_unclearのときは
    カスタマーポータル等への言及・手続き完了を前提にした文言を含んではならず、
    kind=cancellation_intent/downgrade_intentでincludes_portal_link=trueのときは本文に
    実際にリンクへの言及が含まれているかを突き合わせる。
    """
    errors = []
    notice = instance.get("subscription_procedure_notice")
    if notice is None:
        return errors

    kind = notice.get("kind")
    body = notice.get("body", "")
    body_mentions_portal = any(kw in body for kw in PORTAL_KEYWORDS)
    body_mentions_completion = any(kw in body for kw in PROCEDURE_COMPLETION_KEYWORDS)

    if kind == "cancellation_unclear":
        if body_mentions_portal:
            errors.append(
                "subscription_procedure_notice: kind=cancellation_unclearだが本文に"
                "手続きページへの言及が含まれています(厳守事項7a(iv)違反の疑い)"
            )
        if body_mentions_completion:
            errors.append(
                "subscription_procedure_notice: kind=cancellation_unclearだが本文に"
                "手続き完了を前提にした文言が含まれています(厳守事項7a(iv)違反の疑い)"
            )
    elif kind in ("cancellation_intent", "downgrade_intent"):
        if notice.get("includes_portal_link") is True and not body_mentions_portal:
            errors.append(
                f"subscription_procedure_notice: kind={kind}・includes_portal_link=trueだが"
                "本文に手続きページへの言及が見つかりません(文言とフラグの不一致の疑い)"
            )

    return errors


def check_checkout_notice_no_url(instance):
    """厳守事項7b(i)準拠チェック。checkout_notice.includes_checkout_urlはkindによらず
    常にfalseである設計(実際のCheckout Session URL発行・案内はhandle_checkout_intent
    〈Python側〉に委ねる)のため、フィールド値・本文の両方でこの前提が崩れていないかを
    確認する。
    """
    errors = []
    notice = instance.get("checkout_notice")
    if notice is None:
        return errors

    body = notice.get("body", "")
    body_mentions_url = (
        bool(LINK_PLACEHOLDER_PATTERN.search(body))
        or bool(SHORT_URL_DOMAIN_PATTERN.search(body))
    )

    if notice.get("includes_checkout_url") is True:
        errors.append(
            "checkout_notice: includes_checkout_url=trueは想定されていません"
            "(厳守事項7b(i)違反の疑い。kindによらず常にfalseのはず)"
        )
    if body_mentions_url:
        errors.append(
            "checkout_notice: bodyに実際のURLと疑われる記述が含まれています"
            "(厳守事項7b(i)違反の疑い。includes_checkout_url=falseの設計と矛盾)"
        )
    return errors


def check_workshop_invite_notice_no_code(instance):
    """厳守事項7c(i)準拠チェック。workshop_invite_notice.includes_invite_codeはkindに
    よらず常にfalseである設計(実際の招待コード発行はissue_invite_code_for_workshop
    〈Python側〉に委ね、LLM側は一次応答文言のみを返す)のため、フィールド値・本文の
    両方でこの前提が崩れていないかを確認する。checkout_notice向けのURL不在チェックと
    同じ設計思想だが、本フィールドは招待コード(craftsman-account-linking-design.md
    2節・11.1節の6文字コード仕様)らしき文字列の不在も追加で確認する。
    """
    errors = []
    notice = instance.get("workshop_invite_notice")
    if notice is None:
        return errors

    body = notice.get("body", "")
    body_mentions_url = (
        bool(LINK_PLACEHOLDER_PATTERN.search(body))
        or bool(SHORT_URL_DOMAIN_PATTERN.search(body))
    )
    body_mentions_code_lookalike = bool(INVITE_CODE_LOOKALIKE_PATTERN.search(body))

    if notice.get("includes_invite_code") is True:
        errors.append(
            "workshop_invite_notice: includes_invite_code=trueは想定されていません"
            "(厳守事項7c(i)違反の疑い。kindによらず常にfalseのはず)"
        )
    if body_mentions_url:
        errors.append(
            "workshop_invite_notice: bodyに実際のURLと疑われる記述が含まれています"
            "(厳守事項7c(i)違反の疑い。includes_invite_code=falseの設計と矛盾)"
        )
    if body_mentions_code_lookalike:
        errors.append(
            "workshop_invite_notice: bodyに招待コードらしき6文字の文字列が含まれています"
            "(厳守事項7c(i)違反の疑い。includes_invite_code=falseの設計と矛盾)"
        )
    return errors


def check_no_third_party_name_leak_in_customer_facing_notices(instance):
    """厳守事項9準拠チェック(2026-09-26追加、フェーズ183、design.md 4節の限定的な
    人名突き合わせ方式)。order_summary.third_party_names(備考欄等から抽出された、
    依頼者本人以外の第三者を特定できる氏名らしき文字列)が、依頼者へ実際に転送される
    出力2(delivery_notice.body)・出力3(care_notice)にそのまま出現していないかを
    確認する。出力1(order_summary.body)は職人本人の備忘用であり厳守事項9の対象外
    (design.md 1節の宛先整理)のため、突き合わせ先には含めない。

    design.md 4節が明記する通り、人名らしき文字列の抽出自体が信頼できる技術ではない
    ため、本チェックはあくまで『明らかな見落としを拾う補助的な網』であり、厳守事項9の
    実効性の主体はプロンプト側の指示(厳守事項9本文)に置く。third_party_namesが
    未設定・空の場合は検証対象なしとして扱う(requiredフィールドではないため)。
    """
    errors = []
    order_summary = instance.get("order_summary")
    if not order_summary:
        return errors

    names = order_summary.get("third_party_names") or []
    delivery_notice = instance.get("delivery_notice")
    delivery_body = delivery_notice.get("body", "") if delivery_notice else ""
    care_notice = instance.get("care_notice") or ""

    for name in names:
        if not name:
            continue
        if name in delivery_body:
            errors.append(
                f"delivery_notice.body: 第三者名候補「{name}」がそのまま含まれています"
                "(厳守事項9違反の疑い)"
            )
        if name in care_notice:
            errors.append(
                f"care_notice: 第三者名候補「{name}」がそのまま含まれています"
                "(厳守事項9違反の疑い)"
            )
    return errors


def run_all_checks(instance):
    """後処理チェックをまとめて実行し、エラーメッセージのリストを返す。"""
    errors = []
    errors += check_no_emoji_anywhere(instance)
    errors += check_no_out_of_scope_topics_in_generated_output(instance)
    errors += check_delivery_notice_category_text_consistency(instance)
    errors += check_subscription_notice_consistency(instance)
    errors += check_checkout_notice_no_url(instance)
    errors += check_workshop_invite_notice_no_code(instance)
    errors += check_no_third_party_name_leak_in_customer_facing_notices(instance)
    return errors
