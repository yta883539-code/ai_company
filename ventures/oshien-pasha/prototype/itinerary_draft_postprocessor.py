"""venue-matcher-llm-postprocessing-integration-design.md(フェーズ81)の机上実装。

LLM構造化出力(schema/output.schema.jsonのitinerary_draft配列)を受け取った後、
venue_matcher.match_venue()の判定結果でvenue_matched・nearest_station_noteを上書きする
後処理。LLMの学習時点の知識より会場マスタ(schema/venue-master.json)の方が最新かつ
出典付きで管理されているため、判定はvenue_matcher.py側を常に優先する(設計doc 1節)。

実LLM呼び出し・Cloud Functionsへの実配線は行わない(オーナー承認が必要な範囲)。
"""

from venue_matcher import match_venue


def apply_venue_match_postprocessing(itinerary_draft, venue_master, ambiguity_watchlist=None):
    """itinerary_draft: output.schema.jsonのitinerary_draft配列、またはNone
    (status=generated以外のとき。何もせずそのまま返す)。
    venue_master: schema/venue-master.jsonをjson.loadした辞書。
    ambiguity_watchlist: schema/ambiguity-watchlist.jsonをjson.loadした辞書(省略可)。

    戻り値: (上書き後のitinerary_draft, conflictsリスト)
      conflictsの各要素: {venue_name_input, llm_claimed_matched, matcher_matched,
                           match_confidence}
      (LLM自己申告のvenue_matchedとvenue_matcher.pyの判定が異なった場合のみ記録、
       設計doc 2節4・3節参照。出力本体には混入しない。)
    """
    if itinerary_draft is None:
        return None, []

    conflicts = []
    updated = []
    for item in itinerary_draft:
        match = match_venue(item["venue_name_input"], venue_master, ambiguity_watchlist)

        note = match["nearest_station_note"]
        if match["operational_status_note"]:
            note = f"{note} {match['operational_status_note']}"

        if item.get("venue_matched") != match["venue_matched"]:
            conflicts.append(
                {
                    "venue_name_input": item["venue_name_input"],
                    "llm_claimed_matched": item.get("venue_matched"),
                    "matcher_matched": match["venue_matched"],
                    "match_confidence": match["match_confidence"],
                }
            )

        new_item = dict(item)
        new_item["venue_matched"] = match["venue_matched"]
        new_item["nearest_station_note"] = note
        updated.append(new_item)

    return updated, conflicts
