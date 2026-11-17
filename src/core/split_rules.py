"""Compile split rules from a dictionary. This module does not read a file."""

from __future__ import annotations

import re
from dataclasses import dataclass

_KEYS = {
    "type_patterns",
    "option_pattern",
    "option_keys",
    "option_required_types",
    "subquestion_markers",
    "reject_on_missing_options",
    "needs_confirm_threshold",
}
_SECTION_TYPES = {"single_choice", "multiple_choice", "choice", "fill_blank", "solution"}


@dataclass(frozen=True)
class SplitRules:
    type_patterns: tuple[tuple[re.Pattern[str], str], ...]
    option_pattern: re.Pattern[str]
    option_keys: tuple[str, ...]
    option_required_types: frozenset[str]
    subquestion_markers: tuple[re.Pattern[str], ...]
    reject_on_missing_options: bool
    needs_confirm_threshold: int
    choice_body: re.Pattern[str]

    def match_type(self, line: str) -> str | None:
        for pattern, type_code in self.type_patterns:
            if pattern.match(line):
                return type_code
        return None


def compile_rules(payload: object) -> SplitRules:
    """Check the rule object and compile its patterns. A bad field raises ValueError."""
    if not isinstance(payload, dict):
        raise ValueError("拆分规则必须是一个对象。")
    extra = sorted(set(payload) - _KEYS)
    missing = sorted(_KEYS - set(payload))
    if extra:
        raise ValueError("拆分规则有不认识的字段：" + "、".join(extra) + "。")
    if missing:
        raise ValueError("拆分规则缺少字段：" + "、".join(missing) + "。")
    type_patterns = _type_patterns(payload["type_patterns"])
    option_pattern = _pattern(payload["option_pattern"], "option_pattern", groups=1)
    option_keys = _option_keys(payload["option_keys"])
    required = _required_types(payload["option_required_types"])
    markers = _markers(payload["subquestion_markers"])
    reject = payload["reject_on_missing_options"]
    if type(reject) is not bool:
        raise ValueError("reject_on_missing_options 必须是布尔值。")
    threshold = payload["needs_confirm_threshold"]
    if type(threshold) is not int or isinstance(threshold, bool) or threshold < 1:
        raise ValueError("needs_confirm_threshold 必须是大于 0 的整数。")
    letters = "".join(re.escape(key) for key in option_keys)
    choice_body = re.compile(
        rf"[{letters}](?:[,、，][{letters}])*|[{letters}]{{1,{len(option_keys)}}}"
    )
    return SplitRules(
        type_patterns=type_patterns,
        option_pattern=option_pattern,
        option_keys=option_keys,
        option_required_types=required,
        subquestion_markers=markers,
        reject_on_missing_options=reject,
        needs_confirm_threshold=threshold,
        choice_body=choice_body,
    )


def marker_spans(body: str, patterns: tuple[re.Pattern[str], ...]) -> list[re.Match[str]]:
    """Return non-overlapping marker matches from the left."""
    found: list[re.Match[str]] = []
    for pattern in patterns:
        found.extend(pattern.finditer(body))
    found.sort(key=lambda item: item.start())
    kept: list[re.Match[str]] = []
    last_end = -1
    for item in found:
        if item.start() < last_end:
            continue
        kept.append(item)
        last_end = item.end()
    return kept


def _type_patterns(raw: object) -> tuple[tuple[re.Pattern[str], str], ...]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("type_patterns 必须是非空列表。")
    compiled: list[tuple[re.Pattern[str], str]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, dict) or set(item) != {"pattern", "type"}:
            raise ValueError(f"type_patterns 第 {index} 条必须有 pattern 和 type。")
        type_code = item["type"]
        if type_code not in _SECTION_TYPES:
            raise ValueError(f"type_patterns 第 {index} 条的 type 不认识。")
        compiled.append((_pattern(item["pattern"], f"type_patterns 第 {index} 条"), type_code))
    return tuple(compiled)


def _required_types(raw: object) -> frozenset[str]:
    if not isinstance(raw, list) or not raw or any(type(item) is not str for item in raw):
        raise ValueError("option_required_types 必须是非空的字符串列表。")
    unknown = [item for item in raw if item not in _SECTION_TYPES]
    if unknown:
        raise ValueError("option_required_types 有不认识的题型：" + "、".join(unknown) + "。")
    return frozenset(raw)


def _markers(raw: object) -> tuple[re.Pattern[str], ...]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("subquestion_markers 必须是非空的字符串列表。")
    return tuple(_pattern(item, f"subquestion_markers 第 {index} 条", groups=1) for index, item in enumerate(raw, start=1))


def _option_keys(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("option_keys 必须是非空列表。")
    if any(type(item) is not str or len(item) != 1 or not item.isascii() or not item.isalpha() for item in raw):
        raise ValueError("option_keys 的每一项必须是一个字母。")
    if len(set(raw)) != len(raw):
        raise ValueError("option_keys 不能重复。")
    return tuple(raw)


def _pattern(raw: object, label: str, groups: int = 0) -> re.Pattern[str]:
    if type(raw) is not str or not raw:
        raise ValueError(f"{label} 必须是非空字符串。")
    try:
        compiled = re.compile(raw)
    except re.error as exc:
        raise ValueError(f"{label} 的正则写错了。") from exc
    if compiled.groups < groups:
        raise ValueError(f"{label} 必须有一个捕获组。")
    return compiled
