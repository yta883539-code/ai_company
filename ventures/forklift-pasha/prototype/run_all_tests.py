#!/usr/bin/env python3
"""prototype/配下の全test_*.pyを個別プロセスで実行し、結果を集約表示する。

`python3 -m unittest discover`はtest_post_generation_checks.py(unittest.TestCase
ベース)しか収集せず、他3ファイル(test_due_date_logic.py・test_due_date_integration.py・
test_should_remind_integration.py、check()/PASS/FAILパターンのスクリプト形式)を見逃す
非互換がある(kura-pashaのprototype/run_all_tests.pyと同種の問題、本venture側でci-setup.md
新設時に発見)。本スクリプトは各test_*.pyを`python3 <file>`として個別実行し、終了コードで
合否判定することで、discover非互換を回避しつつ全ファイルを一括実行できるようにする。
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def main() -> int:
    test_files = sorted(HERE.glob("test_*.py"))
    results = []
    for test_file in test_files:
        proc = subprocess.run(
            [sys.executable, str(test_file)],
            cwd=HERE,
            capture_output=True,
            text=True,
        )
        ok = proc.returncode == 0
        results.append((test_file.name, ok, proc))
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {test_file.name}")
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
