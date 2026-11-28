"""venue-matcher-llm-postprocessing-integration-design.md(フェーズ81)の机上実装。

LLM構造化出力(schema/output.schema.jsonのitinerary_draft配列)を受け取った後、
venue_matcher.match_venue()の判定結果でvenue_matched・nearest_station_noteを上書きする
後処理。LLMの学習時点の知識より会場マスタ(schema/venue-master.json)の方が最新かつ
出典付きで管理されているため、判定はvenue_matcher.py側を常に優先する(設計doc 1節)。

実LLM呼び出し・Cloud Functionsへの実配線は行わない(オーナー承認が必要な範囲)。

フェーズ170(venue-info-staleness-output-reflection-design.md案3)で、venue_matcher.pyが
組み立てた`info_caution_note`(ネーミングライツ注記・情報鮮度注記)を`venue_matched`・
`nearest_station_note`と同様に常に上書きする対象として追加した。LLM自己申告の値との
食い違いはconflicts検知の対象外とする(`venue_info_caution_note`はLLMに判定させる
フィールドではなく、venue_matcher.py側の機械的な導出結果をそのまま採用する一方通行の
フィールドのため、design doc節2・3が定義する「LLMとマッチャーの判定が食い違う場合の
検知」はvenue_matched判定にのみ適用される)。

フェーズ82(cloud-monitoring-alert-policy-design.md 5節)でconflicts検知を構造化ログに
結線した。本venture・他venture既存のCloud Functions未捕捉例外ログと同じ
`extra={"json_fields": {"event": "..."}}`方式に揃え、Cloud Monitoring側のログベース指標
`jsonPayload.event="venue_match_conflict"`でフィルタできるようにする。実際のロガー設定
(ハンドラ・フォーマッタ、Cloud Logging向け構造化ログハンドラの導入)は実Cloud Functions
デプロイ時に行う前提で、本フェーズでは`logging.getLogger(__name__)`への呼び出し追加のみ
行う(外部サービスへの接続は一切行っていない)。
"""

import logging

from venue_matcher import match_venue

logger = logging.getLogger(__name__)


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
            conflict = {
                "venue_name_input": item["venue_name_input"],
                "llm_claimed_matched": item.get("venue_matched"),
                "matcher_matched": match["venue_matched"],
                "match_confidence": match["match_confidence"],
            }
            conflicts.append(conflict)
            logger.warning(
                "venue_match_conflict: %s",
                conflict,
                extra={"json_fields": {"event": "venue_match_conflict", **conflict}},
            )

        new_item = dict(item)
        new_item["venue_matched"] = match["venue_matched"]
        new_item["nearest_station_note"] = note
        new_item["venue_info_caution_note"] = match["info_caution_note"]
        updated.append(new_item)

    return updated, conflicts
