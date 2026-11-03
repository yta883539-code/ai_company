"""draft.md(人間向け下書き)とvenue-master.json(構造化データ)の会場名を突き合わせ、
どちらか一方にしか存在しない会場名をレポートする差分チェックスクリプト。

venture README.mdフェーズ69・71で発見されたparity gap(draft.mdには記載済みだが
venue-master.jsonへの反映が漏れていた会場が複数件存在した事例)の再発防止策として、
フェーズ71次回候補(1)に対応して新規作成した。

使い方: python3 schema/check_venue_master_parity.py
  - 差分なし: 終了コード0、"OK"メッセージのみ出力。
  - 差分あり: 終了コード1、draft.mdのみ/venue-master.jsonのみに存在する会場名を列挙。

このスクリプトは読み取り専用で、draft.md・venue-master.jsonのどちらも書き換えない。
表記揺れの自動吸収はあえて行わない(誤って「一致」と判定して実際の欠落を見逃すリスクを
避けるため、venue-name-normalization-design.mdが採用した「部分一致は留保付き」という
既存方針を踏襲し、本スクリプトも完全一致〈正規化後〉のみを「一致」とみなす)。
"""
import json
import re
import sys
from pathlib import Path

VENTURE_DIR = Path(__file__).resolve().parent.parent
DRAFT_PATH = VENTURE_DIR / "venue-master-draft.md"
JSON_PATH = Path(__file__).resolve().parent / "venue-master.json"


def normalize(name: str) -> str:
    """表記ゆれ最小限の正規化(全角スペース除去・前後空白除去のみ)。"""
    return name.replace("　", " ").strip()


def name_variants(name: str) -> set[str]:
    """名称1件から、完全形と「(...)より前の部分」の2通りの比較用表記を返す。"""
    name = normalize(name)
    variants = {name}
    base = re.split(r"[(（]", name, maxsplit=1)[0].strip()
    if base:
        variants.add(base)
    return variants


def extract_draft_venue_names(draft_text: str) -> list[str]:
    """venue-master-draft.mdの「## 」見出し配下にあるMarkdownテーブルの会場名列を抽出する。"""
    names = []
    for line in draft_text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not cells:
            continue
        first = cells[0]
        if first in ("会場名",) or re.fullmatch(r"-{2,}", first):
            continue
        if not first:
            continue
        names.append(first)
    return names


def build_json_variant_index(venues: list[dict]) -> dict[str, str]:
    """venue-master.jsonの各会場について、canonical_name・aliasesの表記バリアントから
    canonical_nameへ逆引きできる辞書を作る。"""
    index: dict[str, str] = {}
    for v in venues:
        canonical = v["canonical_name"]
        all_names = [canonical] + v.get("aliases", [])
        for n in all_names:
            for variant in name_variants(n):
                index[variant] = canonical
    return index


def main() -> int:
    draft_text = DRAFT_PATH.read_text(encoding="utf-8")
    venue_master = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    venues = venue_master["venues"]

    draft_names = extract_draft_venue_names(draft_text)
    json_index = build_json_variant_index(venues)

    missing_in_json = []
    for draft_name in draft_names:
        variants = name_variants(draft_name)
        if not variants & json_index.keys():
            missing_in_json.append(draft_name)

    draft_variant_pool: set[str] = set()
    for draft_name in draft_names:
        draft_variant_pool |= name_variants(draft_name)

    missing_in_draft = []
    for v in venues:
        canonical = v["canonical_name"]
        all_names = [canonical] + v.get("aliases", [])
        found = False
        for n in all_names:
            if name_variants(n) & draft_variant_pool:
                found = True
                break
        if not found:
            missing_in_draft.append(canonical)

    ok = True
    if missing_in_json:
        ok = False
        print(f"[NG] draft.mdにあるがvenue-master.jsonに見つからない会場名 "
              f"({len(missing_in_json)}件):")
        for n in missing_in_json:
            print(f"  - {n}")
    if missing_in_draft:
        ok = False
        print(f"[NG] venue-master.jsonにあるがdraft.mdに見つからない会場名 "
              f"({len(missing_in_draft)}件):")
        for n in missing_in_draft:
            print(f"  - {n}")

    if ok:
        print(f"[OK] draft.md({len(draft_names)}件)とvenue-master.json({len(venues)}件)の "
              f"会場名に差分なし。")
        return 0

    print("\n注記: このスクリプトは表記ゆれを自動吸収しない完全一致(正規化後)のみの"
          "チェックであり、意図的な構成変更(施設の分割・統合・改称等)も差分として"
          "検出する。差分が見つかった場合は人間/次回以降のフェーズでdraft.mdと"
          "venue-master.jsonのどちらが最新かを個別に確認すること。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
