"""One test command: unit tests, secret scan, and install from the lock file."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(args: list[str]) -> None:
    print("+", " ".join(args), flush=True)
    completed = subprocess.run(args, cwd=ROOT)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> None:
    python = sys.executable
    run([python, "-m", "unittest", "discover", "-s", "tests", "-v"])
    run([python, str(ROOT / "scripts" / "scan_secrets.py")])
    run([python, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")])


if __name__ == "__main__":
    main()
