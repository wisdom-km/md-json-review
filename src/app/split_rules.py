"""Load config/split_rules.json. Core checks the dictionary and does not read it."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from core.convert import ConvertError
from core.schema_check import schema_problems
from core.split_rules import SplitRules, compile_rules

_ROOT = Path(__file__).resolve().parents[2]
_SCHEMA = "split-rules.v1.schema.json"


@lru_cache(maxsize=1)
def _split_schema() -> dict:
    path = _ROOT / "contracts" / _SCHEMA
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConvertError("SPLIT_RULES", "没有读到拆分规则的形状 contracts/split-rules.v1.schema.json。") from exc
    except json.JSONDecodeError as exc:
        raise ConvertError("SPLIT_RULES", "拆分规则的形状不是合法的 JSON。") from exc


def validate_split_rules(payload: object) -> SplitRules:
    """Check the rule object against the shipped schema, then compile it."""
    problems = schema_problems(_split_schema(), payload)
    if problems:
        raise ConvertError("SPLIT_RULES", problems[0])
    try:
        return compile_rules(payload)
    except ValueError as exc:
        raise ConvertError("SPLIT_RULES", str(exc)) from exc


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
    return validate_split_rules(payload)
