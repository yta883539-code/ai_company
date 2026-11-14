#!/usr/bin/env python3
"""prototype/配下の全test_*.pyを個別プロセスで実行し、結果を集約表示する。

`python3 -m unittest discover`はunittest.TestCaseベースの3ファイル
(test_access_url_resend_handler.py・test_checkout_result_page_handler.py・
test_post_generation_checks.py、計31件)しか収集せず、他5ファイル
(test_fan_pass_store.py・test_itinerary_draft_postprocessor.py・test_stripe_webhook.py・
test_usage_counter.py・test_venue_matcher.py、check()/PASS/FAILパターンのスクリプト形式)を
見逃す非互換がある(kura-pasha・forklift-pashaのprototype/run_all_tests.pyと同種の問題、
cross-venture-discover-compatibility-review.md作成時点〈フェーズ89〉では本ventureが
未作成だったため横展開対象から漏れていた。フェーズ103で発見)。本スクリプトは各test_*.pyを
`python3 <file>`として個別実行し、終了コードで合否判定することで、discover非互換を回避しつつ
全ファイルを一括実行できるようにする。

venue-master-draft.mdフェーズ72次回候補(1)に対応し、schema/check_venue_master_parity.py
(draft.md⇔venue-master.jsonの会場名parity差分チェック)もこの一括実行に含める(フェーズ119)。
test_*.pyと異なりunittestパターンではないため、他のテストファイルと同様に個別プロセスで
実行し終了コードのみで合否判定する。
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
VENTURE_DIR = HERE.parent
PARITY_CHECK = VENTURE_DIR / "schema" / "check_venue_master_parity.py"


def main() -> int:
    test_files = sorted(HERE.glob("test_*.py"))
    checks = [(f, f.name) for f in test_files]
    checks.append((PARITY_CHECK, "schema/check_venue_master_parity.py"))

    results = []
    for check_file, label in checks:
        proc = subprocess.run(
            [sys.executable, str(check_file)],
            cwd=VENTURE_DIR,
            capture_output=True,
            text=True,
        )
        ok = proc.returncode == 0
        results.append((label, ok, proc))
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {label}")
        if not ok:
            print(proc.stdout)
            print(proc.stderr, file=sys.stderr)

    failed = [name for name, ok, _ in results if not ok]
    print(f"\n{len(results)} files run, {len(results) - len(failed)} passed, {len(failed)} failed")
    if failed:
        print("failed files:", ", ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
