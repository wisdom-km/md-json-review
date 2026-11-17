"""Fail if tracked-looking files contain a secret shape. Skips nothing by content size."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "logs", "__pycache__", ".venv"}
PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"postgres(?:ql)?://[^/\s:]+:[^/\s@]+@"),
]


def main() -> int:
    failures: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        if path.suffix.lower() in {".png", ".pdf", ".pyc"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in PATTERNS:
            if pattern.search(text):
                failures.append(f"{path.relative_to(ROOT)}:{pattern.pattern}")
    if failures:
        print("密钥扫描失败：")
        for item in failures:
            print(item)
        return 1
    print("密钥扫描通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
