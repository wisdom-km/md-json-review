"""Load the shipped split rules for tests. Not a test module."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from core.split_rules import SplitRules, compile_rules


def shipped_rules() -> SplitRules:
    payload = json.loads((ROOT / "config" / "split_rules.json").read_text(encoding="utf-8"))
    return compile_rules(payload)


def rules_with(**changes: object) -> SplitRules:
    payload = json.loads((ROOT / "config" / "split_rules.json").read_text(encoding="utf-8"))
    payload.update(changes)
    return compile_rules(payload)
