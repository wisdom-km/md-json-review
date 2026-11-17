"""Load config/split_rules.json. Core checks the dictionary and does not read it."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from core.convert import ConvertError
from core.split_rules import SplitRules, compile_rules

_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def load_split_rules() -> SplitRules:
    path = _ROOT / "config" / "split_rules.json"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConvertError("SPLIT_RULES", "没有读到拆分规则 config/split_rules.json。") from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConvertError("SPLIT_RULES", "拆分规则不是合法的 JSON。") from exc
    try:
        return compile_rules(payload)
    except ValueError as exc:
        raise ConvertError("SPLIT_RULES", str(exc)) from exc
