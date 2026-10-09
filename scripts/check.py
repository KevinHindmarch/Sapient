"""Run the project's fast local checks (used by CI too).

    python scripts/check.py            # tests + compile + frontend build
    python scripts/check.py --no-frontend
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEST_PATTERNS = (
    "test_safety_spec.py",
    "test_tws_readonly_check.py",
    "test_execution_safety_unit.py",
    "test_execution_safety_sqlite.py",
    "test_local_api.py",
    "test_tws.py",
    "test_upgrades.py",
    "test_strategy.py",
    "test_paper.py",
    "test_live.py", "test_g1_safety.py", "test_g2_ledger.py",
)


def run(cmd, cwd=ROOT):
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-frontend", action="store_true")
    args = parser.parse_args()

    for pattern in TEST_PATTERNS:
        run([sys.executable, "-m", "unittest", "discover", "-v", "-s", "tests", "-p", pattern])
    run([sys.executable, "-m", "compileall", "-q", "core", "backend", "safety_spec", "scripts"])

    if not args.no_frontend:
        npm = shutil.which("npm")
        if npm is None:
            sys.exit("npm not found")
        run([npm, "ci"], cwd=ROOT / "frontend")
        run([npm, "run", "build"], cwd=ROOT / "frontend")
    print("All checks passed")


if __name__ == "__main__":
    main()
