#!/usr/bin/env python3
"""
LLM構造化出力(schema/output.schema.json)を受け取った後に、プログラム側で機械的に
検証する後処理チェック。

位置づけ:
- schema/output.schema.jsonのフィールド説明で「本文中の言及との突き合わせ検証」を
  意図として記載していた`sns_post.mentions_photo`(厳守事項3)・`unchanged_areas`
  (厳守事項2)の2点について、これまで方針の記述のみだったものを初めて実行可能な
  コードに落とし込んだ(line-reservation-aiのvalidate_test_cases.py・prototype/engine.pyと
  同じ位置づけ)。2026-08-09追記: 厳守事項9(絵文字の使用箇所・個数制限)も同じ位置づけで
  機械チェック化した。同日追記: history_rows[].countとsns_post/line_web_notice本文中の
  本数記載との整合性チェックも追加した(厳守事項4・5の「本数を明示する」指示と、
  history_rows(構造化データ)側の本数が食い違っていないかの突き合わせ)。
- ここでの検証はあくまでヒューリスティック(キーワード近傍探索・絵文字の文字コード範囲判定)
  であり、LLMの厳守事項違反を確実に検出できるわけではない。実LLM接続後は、ここで拾いきれない
  違反パターンの収集・ルール改善が引き続き必要になる。
- 2026-08-09追記: history_rows[].countと本文中の本数記載との整合性チェック(厳守事項4・5)に
  続き、history_rows[]に登場するエリア名自体が本文中に一切言及されていないケース
  (厳守事項4・5の「エリア・改訂日の明示」指示への違反疑い)を検出するチェックも追加した。
- 実LLM呼び出しは行わない(APIキー・課金が必要なため、実行にはオーナー承認が必要な範囲)。
"""

import re

PHOTO_REFERENCE_KEYWORDS = ("写真の課題", "写真")
NEW_CONTENT_KEYWORDS = ("新着", "追加", "入れ替え", "新規")
UNCHANGED_KEYWORDS = ("変更なし", "変更ありません", "変わりません", "変更はありません")

# 厳守事項9の機械チェック用。絵文字そのものを網羅する完全な判定は困難なため、
# 実際に投稿文で使われやすい絵文字が集中する主要ブロック(顔文字・記号・ピクトグラム等)を
# 対象としたヒューリスティックとする。
EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FAFF"  # 各種絵文字・記号(顔・乗り物・アクティビティ等)
    "☀-➿"  # その他の記号・装飾記号(☀☕✨➿等)
    "⬀-⯿"  # 矢印・星等の追加記号(⭐⬛等)
    "\U0001F1E6-\U0001F1FF"  # 地域指示記号(組み合わせで国旗絵文字になる)
    "\U0001F200-\U0001F2FF"  # 囲みCJK文字・月間補助記号(🈚🈵🈲等、SNS投稿で使われうる)
    "️"  # 異体字セレクタ(絵文字表示指定)
    "‍"  # ゼロ幅接合子(複合絵文字)
    "]"
)
SNS_POST_MAX_EMOJI = 2

# 厳守事項7の機械チェック用。会員管理・予約受付・決済に関する話題への言及があるかを
# 検出するためのキーワード。本venture(告知文・記録の下書き作成支援)の性質上、
# 生成本文にこれらの語が登場すること自体が想定外(厳守事項7逸脱の疑い)であるため、
# 厳守事項2・3のような文脈判定(近傍に打消し語がないか等)は行わず、出現の有無のみで判定する。
# 2026-08-15追記: 「会員」「決済」等の直接語のみでは、ボルダリングジムで実際によく使われる
# 会員管理・予約関連の言い回し(月会費・会費の話題、予約のキャンセル)を「予約」「決済」を
# 含まない表現で取りこぼす疑いがあったため、フェーズ57のPORTAL_KEYWORDS拡張と同じ考え方で
# 語彙を追加した。「月会費」は「会費」の部分文字列一致で既に検出できるため別途追加しない。
OUT_OF_SCOPE_TOPIC_KEYWORDS = (
    "会員", "入会", "退会", "予約", "決済", "支払い", "振込", "クレジットカード",
    "会費", "キャンセル",
)

# 厳守事項7a(解約意図検知)の機械チェック用。subscription-cancellation-flow-design.md
# 「1. 解約意図検知時の案内メッセージ」の文言例、およびllm-system-prompt-draft.md厳守事項7a(iv)
# 「(cancellation_unclearのときは)手続き完了・Stripeカスタマーポータルへの言及は含めない」を
# 突き合わせるためのキーワード。
# 2026-08-15追記: 「ポータル」を含まない別表現(line-reservation-aiのbilling-upgrade-flow-design.md
# が実際に使う「マイページ」「決済ページ」表記等)でも同じ案内が成立しうるため、語彙を追加した。
# あわせて、本文中にURLプレースホルダ({...URL}形式)やhttp(s)リンクそのものが含まれる場合は、
# 用いている単語によらず手続きページへの案内が行われていると判断する。
# 2026-08-16追記: フェーズ57の残課題(「短縮リンクサービス名のみ」の取りこぼし)に対応。
# httpスキームを付けずに短縮URLサービスのドメインのみを本文に貼るケース(例:
# 「手続きはこちら bit.ly/xxxxx」)はLINK_PLACEHOLDER_PATTERNのhttps?://判定を素通りするため、
# 主要な短縮URLサービスのドメイン名をSHORT_URL_DOMAIN_PATTERNとして別途検出対象に追加した。
# 「こちらまでご連絡ください」のような、リンク・サービス名を一切伴わない婉曲表現は依然として
# 検出できない既知の限界として残る(本文にドメイン・URLの手がかりが一切無いため機械判定不能)。
PORTAL_KEYWORDS = ("カスタマーポータル", "ポータル", "マイページ", "決済ページ", "手続きページ")
PROCEDURE_COMPLETION_KEYWORDS = ("手続き完了", "解約が完了", "手続きが完了", "解約は完了")
LINK_PLACEHOLDER_PATTERN = re.compile(r"\{[^{}]*URL[^{}]*\}|https?://")
SHORT_URL_DOMAIN_PATTERN = re.compile(
    r"\b(?:bit\.ly|lin\.ee|tinyurl\.com|t\.co|x\.gd|is\.gd)/\S+"
)


def check_mentions_photo_consistency(instance):
    """厳守事項3準拠チェック。sns_post.mentions_photoの値と、本文中に実際に写真への
    言及があるかどうかが一致しているかを確認する。

    - mentions_photo=trueなのに本文に写真言及が無い: 「写真の課題」に言及する形で
      文面を組み立てる、という指示が守られていない疑い。
    - mentions_photo=falseなのに本文に写真言及がある: 写真が無いのに言及してしまっている疑い。
    """
    errors = []
    sns_post = instance.get("sns_post")
    if sns_post is None:
        return errors

    body = sns_post.get("body", "")
    mentions_photo = sns_post.get("mentions_photo")
    body_mentions_photo = any(kw in body for kw in PHOTO_REFERENCE_KEYWORDS)

    if mentions_photo is True and not body_mentions_photo:
        errors.append(
            "sns_post: mentions_photo=trueだが本文に写真への言及が見つかりません(厳守事項3違反の疑い)"
        )
    if mentions_photo is False and body_mentions_photo:
        errors.append(
            "sns_post: mentions_photo=falseだが本文に写真への言及が含まれています(厳守事項3違反の疑い)"
        )
    return errors


def _split_sentences(text):
    """「。」を区切りとして文単位に分割する(区切り文字は直前の文に含める)。"""
    return [s for s in re.split(r"(?<=。)", text) if s]


def _split_into_area_segments(sentence, known_area_names):
    """sentenceを、known_area_names内の各エリア名の出現位置を境界としてセグメントに
    分割する。各セグメントは、あるエリア名の出現位置から次のエリア名(自身含む)の
    出現位置の直前まで(無ければ文末まで)の範囲となる。既知のエリア名が1つも
    見つからない場合は文全体を1セグメントとして返す。"""
    if not known_area_names:
        return [(None, sentence)]
    pattern = re.compile(
        "|".join(re.escape(a) for a in sorted(set(known_area_names), key=len, reverse=True))
    )
    matches = list(pattern.finditer(sentence))
    if not matches:
        return [(None, sentence)]
    segments = []
    if matches[0].start() > 0:
        segments.append((None, sentence[: matches[0].start()]))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(sentence)
        segments.append((m.group(), sentence[m.start() : end]))
    return segments


def _find_suspicious_area_mentions(text, area, other_known_area_names=()):
    """area名を含む文ごとに、NEW_CONTENT_KEYWORDSが含まれ、かつUNCHANGED_KEYWORDSが
    含まれないセグメント(=新着扱いされている疑いのある箇所)を返す。「エリアCは
    変更ありません」のように同じ文中で変更なし文脈が言及される場合は許容する。

    文単位で判定するのは、固定文字数の近傍窓(旧実装)だと「エリアDは変更ありません。
    エリアCに新着課題を追加しました。」のように、直前の文にある別エリア(D)の
    「変更ありません」が窓内に入り込み、エリアC自身の新着扱い(=本来の違反)を
    誤って見逃す(false negative)ケースがあったため。

    さらに「エリアDは変更なし、エリアCは新着課題を追加しました。」のように読点区切りで
    1文にまとまっている場合に備え、other_known_area_names(unchanged_areas・history_rows
    から集めた既知のエリア名一覧)が渡された場合は、文をエリア名の出現位置ごとの
    セグメントに分割してから判定する。これにより、同じ文中に別エリアの言及が
    混在していても、対象エリア自身のセグメント内のキーワードのみで判定できる。
    既知のエリア名が対象area以外に無い場合は文全体をそのまま1セグメントとして扱うため、
    「エリアCは、新着課題を追加しました。」のように対象エリア自身の文が読点を含む
    ケースを誤って分断することはない。"""
    hits = []
    known_area_names = set(other_known_area_names) | {area}
    for sentence in _split_sentences(text):
        if area not in sentence:
            continue
        for seg_area, segment in _split_into_area_segments(sentence, known_area_names):
            if seg_area != area:
                continue
            has_new = any(kw in segment for kw in NEW_CONTENT_KEYWORDS)
            has_unchanged = any(kw in segment for kw in UNCHANGED_KEYWORDS)
            if has_new and not has_unchanged:
                hits.append(segment)
    return hits


def check_unchanged_areas_not_mentioned_as_new(instance):
    """厳守事項2準拠チェック。unchanged_areasに含まれるエリア名が、sns_post.body /
    line_web_notice.body内で新着課題があるかのような文脈(「新着」「追加」等の近傍)に
    登場していないかを確認する。"""
    errors = []
    unchanged_areas = instance.get("unchanged_areas") or []
    if not unchanged_areas:
        return errors

    history_rows = instance.get("history_rows") or []
    changed_area_names = {row.get("area") for row in history_rows if row.get("area")}
    known_area_names = set(unchanged_areas) | changed_area_names

    texts = []
    sns_post = instance.get("sns_post")
    if sns_post:
        texts.append(("sns_post.body", sns_post.get("body", "")))
    line_web_notice = instance.get("line_web_notice")
    if line_web_notice:
        texts.append(("line_web_notice.body", line_web_notice.get("body", "")))

    for field_name, text in texts:
        for area in unchanged_areas:
            other_known_area_names = known_area_names - {area}
            for hit in _find_suspicious_area_mentions(text, area, other_known_area_names):
                errors.append(
                    f"{field_name}: 変更なしエリア「{area}」が新着を示唆する文脈で"
                    f"言及されている疑いがあります: ...{hit}..."
                )
    return errors


def check_emoji_usage_rules(instance):
    """厳守事項9準拠チェック。絵文字は出力1(SNS投稿文)のみ1〜2個程度までとし、
    出力2(公式LINE/Web告知文)・出力3(履歴記録)には一切使用しない、というルールを
    本文中の絵文字出現数から機械的に確認する。

    - sns_post.body: 絵文字がSNS_POST_MAX_EMOJI(2個)を超える場合のみ違反とする
      (「1〜2個程度まで」という目安のため、0個は許容し上限超過のみを検出する)。
    - line_web_notice.body: 絵文字が1個でもあれば違反。
    - history_rows[].feature_keywords: 表形式の記録であり絵文字を使う想定が無いため、
      1個でもあれば違反。tape_color_or_grade_band/areaは入力メモの転記が中心のため
      対象外とする。
    """
    errors = []

    sns_post = instance.get("sns_post")
    if sns_post:
        body = sns_post.get("body", "")
        count = len(EMOJI_PATTERN.findall(body))
        if count > SNS_POST_MAX_EMOJI:
            errors.append(
                f"sns_post: 絵文字が{count}個含まれています"
                f"(厳守事項9違反の疑い、上限は{SNS_POST_MAX_EMOJI}個程度)"
            )

    line_web_notice = instance.get("line_web_notice")
    if line_web_notice:
        body = line_web_notice.get("body", "")
        if EMOJI_PATTERN.search(body):
            errors.append(
                "line_web_notice: 絵文字が含まれています(厳守事項9違反の疑い、出力2は絵文字不使用)"
            )

    for row in instance.get("history_rows") or []:
        for keyword in row.get("feature_keywords") or []:
            if EMOJI_PATTERN.search(keyword):
                errors.append(
                    f"history_rows: feature_keywords「{keyword}」に絵文字が含まれています"
                    "(厳守事項9違反の疑い、出力3は絵文字不使用)"
                )

    return errors


def check_history_row_counts_mentioned_in_text(instance):
    """厳守事項4・5準拠チェック(本数の明示)。history_rows[].count(null以外)の値が、
    sns_post.body・line_web_notice.bodyのいずれかに数字として登場しているかを確認する。

    「本数を明示する」という厳守事項4・5の指示自体は本文側にのみ課されているが、
    history_rows(構造化データ)側の本数と本文側の本数が食い違っていれば、どちらかが
    LLMの生成ミス・入力の取り違えである疑いが強い。check_mentions_photo_consistency・
    check_unchanged_areas_not_mentioned_as_newと同じく、構造化フィールドと本文の
    突き合わせによる整合性チェックという位置づけ。

    countが同じ値の別エリアが複数ある場合や、本数以外の文脈で偶然同じ数字が登場する
    場合(例:日付の一部)は誤って一致と判定しうるヒューリスティックであり、既存の
    キーワード近傍探索と同じ限界を持つ。
    """
    errors = []
    history_rows = instance.get("history_rows") or []
    if not history_rows:
        return errors

    bodies = []
    sns_post = instance.get("sns_post")
    if sns_post:
        bodies.append(sns_post.get("body", ""))
    line_web_notice = instance.get("line_web_notice")
    if line_web_notice:
        bodies.append(line_web_notice.get("body", ""))
    combined = "\n".join(bodies)

    for row in history_rows:
        count = row.get("count")
        if count is None:
            continue
        area = row.get("area") or "(エリア名不明)"
        if str(count) not in combined:
            errors.append(
                f"history_rows: エリア「{area}」の本数({count})が"
                "sns_post.body・line_web_notice.bodyのいずれにも見つかりません"
                "(本文とhistory_rowsの本数不一致の疑い)"
            )
    return errors


def check_updated_areas_mentioned_in_text(instance):
    """厳守事項4・5準拠チェック(エリアの明示)。history_rows[].area(実際に更新された
    エリア名)が、sns_post.body・line_web_notice.bodyのいずれにも一切登場していない
    ケースを検出する。

    check_history_row_counts_mentioned_in_text()がhistory_rows[].countと本文の本数
    記載との整合性を確認するのに対し、本チェックはエリア名自体の言及漏れを確認する
    (「エリア・改訂日の明示」を求める厳守事項4・5の指示のうち、本数側だけで
    エリア名側の突き合わせが未検証のまま残っていた)。

    同一エリア名が別の綴り(略称等)で言及される場合や、複数エリアの記述が省略された
    箇条書き(multi-area-mixed-case-review.md想定の3エリア以上の簡潔化パターン)で
    エリア名自体は残る前提のため、エリア名文字列の完全一致のみで判定するヒューリスティック
    である点は既存チェックと同じ限界を持つ。
    """
    errors = []
    history_rows = instance.get("history_rows") or []
    if not history_rows:
        return errors

    bodies = []
    sns_post = instance.get("sns_post")
    if sns_post:
        bodies.append(sns_post.get("body", ""))
    line_web_notice = instance.get("line_web_notice")
    if line_web_notice:
        bodies.append(line_web_notice.get("body", ""))
    combined = "\n".join(bodies)

    for row in history_rows:
        area = row.get("area")
        if not area:
            continue
        if area not in combined:
            errors.append(
                f"history_rows: エリア「{area}」が"
                "sns_post.body・line_web_notice.bodyのいずれにも見つかりません"
                "(厳守事項4・5違反の疑い、エリア名の明示漏れ)"
            )
    return errors


def check_no_out_of_scope_topics_in_generated_output(instance):
    """厳守事項7準拠チェック。status=generated(=通常の3出力生成)のとき、
    sns_post.body・line_web_notice.bodyに会員管理・予約受付・決済に関する話題への
    言及が紛れ込んでいないかを確認する。

    厳守事項7は「入力メモに会員管理・予約受付・決済の記述が含まれていても一切応答しない」
    ことを求めているが、これまでの機械チェック(schema/validate_test_cases.pyの
    validate_cross_field_rules())はstatus=out_of_scope分岐そのものの妥当性
    (out_of_scope_message等のnull/非null依存関係)しか検証しておらず、LLMが
    status=generatedと判定したケースの本文自体にこれらの話題が紛れ込んでいないかは
    未検証のまま残っていた。status=out_of_scopeのout_of_scope_message自体は
    「会員管理・予約受付・決済のご案内はできません」のように意図的にこれらの語を
    含むため、このチェックの対象はsns_post/line_web_notice(status=generatedのときのみ
    非null)に限定する。
    """
    errors = []
    if instance.get("status") != "generated":
        return errors

    texts = []
    sns_post = instance.get("sns_post")
    if sns_post:
        texts.append(("sns_post.body", sns_post.get("body", "")))
    line_web_notice = instance.get("line_web_notice")
    if line_web_notice:
        texts.append(("line_web_notice.body", line_web_notice.get("body", "")))

    for field_name, text in texts:
        for kw in OUT_OF_SCOPE_TOPIC_KEYWORDS:
            if kw in text:
                errors.append(
                    f"{field_name}: 会員管理・予約・決済に関する話題と疑われる語「{kw}」が"
                    "含まれています(厳守事項7違反の疑い)"
                )
    return errors


def check_subscription_notice_consistency(instance):
    """厳守事項7a準拠チェック。subscription_procedure_notice.bodyの文言が、
    kind別の制約(subscription-cancellation-flow-design.md記載)と整合しているかを確認する。

    - kind=cancellation_unclear: 厳守事項7a(iv)により、意思確認の一言のみを求めており、
      Stripeカスタマーポータルへの言及や手続き完了を前提にした文言を含んではならない
      (schema/output.schema.jsonのincludes_portal_link=falseとの整合)。
    - kind=cancellation_intent/downgrade_intent: includes_portal_link=trueが期待される
      ケースであり、check_mentions_photo_consistencyと同じ考え方で、本文中に実際に
      カスタマーポータルへの案内が含まれているかを突き合わせる。
    """
    errors = []
    notice = instance.get("subscription_procedure_notice")
    if notice is None:
        return errors

    kind = notice.get("kind")
    body = notice.get("body", "")
    body_mentions_portal = (
        any(kw in body for kw in PORTAL_KEYWORDS)
        or bool(LINK_PLACEHOLDER_PATTERN.search(body))
        or bool(SHORT_URL_DOMAIN_PATTERN.search(body))
    )
    body_mentions_completion = any(kw in body for kw in PROCEDURE_COMPLETION_KEYWORDS)

    if kind == "cancellation_unclear":
        if body_mentions_portal:
            errors.append(
                "subscription_procedure_notice: kind=cancellation_unclearだが本文に"
                "カスタマーポータルへの言及が含まれています(厳守事項7a(iv)違反の疑い)"
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
                "本文にカスタマーポータルへの言及が見つかりません(文言とフラグの不一致の疑い)"
            )

    return errors


def run_all_checks(instance):
    """後処理チェックをまとめて実行し、エラーメッセージのリストを返す。"""
    errors = []
    errors += check_mentions_photo_consistency(instance)
    errors += check_unchanged_areas_not_mentioned_as_new(instance)
    errors += check_emoji_usage_rules(instance)
    errors += check_history_row_counts_mentioned_in_text(instance)
    errors += check_updated_areas_mentioned_in_text(instance)
    errors += check_no_out_of_scope_topics_in_generated_output(instance)
    errors += check_subscription_notice_consistency(instance)
    return errors
