"""venue-name-normalization-design.md (フェーズ16/17/22/25) の段階的マッチング設計の実コード化。

手順: 1.正規化 -> 2.正式名称完全一致 -> 3.エイリアス完全一致 ->
      3.5.混同注意リスト(ambiguity-watchlist.json)照合 -> 4.部分一致フォールバック(留保付き) ->
      5.非該当。

schema/output.schema.json本体はmatch_confidence拡張・venue_operational_status_note追加を
実LLM安定生成未検証のため見送り中(venue-name-normalization-design.md「schemaへの反映について」・
venue-operational-status-output-reflection-design.md 3節)であり、本モジュールもその方針を
踏襲し、戻り値はoutput.schema.jsonの`venue_matched`/`nearest_station_note`に加えて、
将来のスキーマ拡張時に使う内部情報(`match_confidence`・`operational_status_note`)を
別フィールドとして保持するに留める(LLMへの直接結線・schema変更は行わない)。
"""
import unicodedata


def _normalize(text):
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("　", " ").strip()
    while "  " in text:
        text = text.replace("  ", " ")
    return text


def _operational_status_note(venue):
    status = venue.get("operational_status", "active")
    if status == "active":
        return None
    if status == "closed":
        note = venue.get("verification_note") or ""
        return (
            "この会場名は現在イベント会場として稼働していない可能性があります。"
            "最新の開催会場情報を主催者発表でご確認ください。"
            + (f"(補足: {note})" if note else "")
        )
    if status == "uncertain":
        return (
            "この会場の現在の稼働状況を確認できていません。"
            "最新の開催会場情報を主催者発表でご確認ください。"
        )
    return None


def _station_note(venue):
    return f"{venue['nearest_station']}({venue.get('walk_minutes_note', '徒歩目安不明')})"


def _partial_match_note(venue_name_input, candidate_names):
    """venue-name-normalization-design.md フェーズ122「部分一致(フォールバック)時の
    案内文の具体例」の文例A(候補1件)・文例B(候補複数件)をそのまま実コード化したもの。
    tone-and-manner-guideline.mdの方針(ですます調・断定しない表現)に沿い、"断定はできません"
    "判別できません"のように言い切らない表現を保つ。
    """
    if len(candidate_names) == 1:
        return (
            f"入力いただいた会場名「{venue_name_input}」は、登録されている会場名と完全には"
            f"一致しませんでした。もしかすると「{candidate_names[0]}」のことかもしれませんが、"
            "断定はできません。お手数ですが、チケットや当選メールに記載の正式な会場名をご確認の"
            "うえ、再度ご入力いただけますと幸いです。"
        )
    joined = "」「".join(candidate_names)
    return (
        f"入力いただいた会場名「{venue_name_input}」は、登録されている会場名と完全には"
        f"一致しませんでした。「{joined}」のいずれかの可能性がありますが、本サービスでは"
        "判別できません。お手数ですが、チケットや当選メールに記載の正式な会場名をご確認の"
        "うえ、再度ご入力いただけますと幸いです。"
    )


def match_venue(venue_name_input, venue_master, ambiguity_watchlist=None):
    """venue_name_input: 利用者入力の会場名文字列。
    venue_master: schema/venue-master.jsonをjson.loadした辞書(キー"venues"を持つ)。
    ambiguity_watchlist: schema/ambiguity-watchlist.jsonをjson.loadした辞書(キー"entries")。
                         Noneの場合は混同注意リスト照合をスキップする。

    戻り値(dict):
      venue_matched: bool (output.schema.json準拠)
      nearest_station_note: str (output.schema.json準拠)
      match_confidence: "exact" | "alias" | "partial" | "none" (内部用、スキーマ未反映)
      operational_status_note: str | None (内部用、スキーマ未反映)
      matched_canonical_name: str | None
    """
    normalized = _normalize(venue_name_input)
    venues = venue_master.get("venues", [])

    for venue in venues:
        if _normalize(venue["canonical_name"]) == normalized:
            return {
                "venue_matched": True,
                "nearest_station_note": _station_note(venue),
                "match_confidence": "exact",
                "operational_status_note": _operational_status_note(venue),
                "matched_canonical_name": venue["canonical_name"],
            }

    for venue in venues:
        for alias in venue.get("aliases", []):
            if _normalize(alias) == normalized:
                return {
                    "venue_matched": True,
                    "nearest_station_note": _station_note(venue),
                    "match_confidence": "alias",
                    "operational_status_note": _operational_status_note(venue),
                    "matched_canonical_name": venue["canonical_name"],
                }

    if ambiguity_watchlist:
        for entry in ambiguity_watchlist.get("entries", []):
            if _normalize(entry["ambiguous_input_pattern"]) in normalized:
                return {
                    "venue_matched": False,
                    "nearest_station_note": entry["note"],
                    "match_confidence": "none",
                    "operational_status_note": None,
                    "matched_canonical_name": None,
                }

    partial_candidate_names = []
    for venue in venues:
        candidates = [venue["canonical_name"]] + venue.get("aliases", [])
        for candidate in candidates:
            normalized_candidate = _normalize(candidate)
            if normalized_candidate and normalized_candidate in normalized:
                if venue["canonical_name"] not in partial_candidate_names:
                    partial_candidate_names.append(venue["canonical_name"])
                break

    if partial_candidate_names:
        return {
            "venue_matched": False,
            "nearest_station_note": _partial_match_note(
                venue_name_input, partial_candidate_names
            ),
            "match_confidence": "partial",
            "operational_status_note": None,
            "matched_canonical_name": None,
        }

    return {
        "venue_matched": False,
        "nearest_station_note": "会場名を確認できなかったため、一般的な調べ方をご案内します。",
        "match_confidence": "none",
        "operational_status_note": None,
        "matched_canonical_name": None,
    }
