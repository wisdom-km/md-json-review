"""Split one reviewed page into question drafts. No files and no guessing.

Rules come from the caller. Fewer options than needs_confirm_threshold marks
the question needs_confirm, unless the rules refuse the whole page. Two
conflicting signals become an unresolved draft instead of a guessed type.
"""

from __future__ import annotations

import re

from core.convert import normalize_newlines
from core.split_rules import SplitRules, marker_spans

_QUESTION = re.compile(r"^(\d+)[.．、]\s*(.*)$")
_DIVIDER = re.compile(r"^[\u4e00-\u9fff]{2,12}$")
_SECTION_SHAPE = re.compile(r"^[一二三四五六七八九十]+[.．、]\s*\S.{0,24}$")
_BLANK = re.compile(r"_{2,}")
_MULTI = re.compile(r"多选|哪些")
_CONFIRMABLE = {"single_choice", "multiple_choice", "fill_blank", "solution"}


def split_questions(markdown: str, rules: SplitRules) -> dict:
    """Return preface text and question drafts for one page."""
    text = normalize_newlines(markdown).strip("\n")
    lines = text.split("\n") if text else []
    preface: list[str] = []
    drafts: list[dict] = []
    raw: list[dict] = []
    mode = False
    section_type: str | None = None
    section_title = ""
    section_index = 0
    current: dict | None = None

    def flush() -> None:
        nonlocal current
        if current is None:
            return
        raw.append(current)
        current = None

    for index, line in enumerate(lines):
        stripped = line.strip()
        matched = rules.match_type(stripped)
        if matched is not None:
            flush()
            mode = True
            section_index += 1
            section_title = stripped
            section_type = matched
            continue
        if _SECTION_SHAPE.match(stripped):
            flush()
            mode = True
            section_index += 1
            section_title = stripped
            section_type = None
            continue
        if not mode:
            preface.append(line)
            continue
        if _is_divider(lines, index):
            flush()
            section_index += 1
            section_title = stripped
            section_type = None
            continue
        question = _QUESTION.match(stripped)
        if question:
            flush()
            current = {
                "number": question.group(1),
                "lines": [question.group(2)],
                "section": section_title,
                "section_type": section_type,
                "section_index": section_index,
            }
            continue
        if current is None:
            continue
        current["lines"].append(line)
    flush()

    refused = False
    for item in raw:
        draft, missing_options = _build(item, rules)
        if missing_options and rules.reject_on_missing_options:
            refused = True
            break
        if missing_options and draft["status"] == "candidate":
            draft["status"] = "needs_confirm"
        drafts.append(draft)
    if refused:
        return {
            "ok": False,
            "reason": "有选择题没有足够的选项，这一页没有拆成草稿。",
            "preface": "\n".join(preface).strip(),
            "questions": [],
        }
    return {
        "ok": True,
        "reason": "",
        "preface": "\n".join(preface).strip(),
        "questions": drafts,
    }


def apply_type_overrides(split: dict, overrides: object) -> dict:
    """A teacher may set a type. Unknown keys and unknown types are ignored."""
    if not split.get("ok") or not isinstance(overrides, dict):
        return split
    questions = []
    for question in split["questions"]:
        chosen = overrides.get(question["key"])
        if chosen in _CONFIRMABLE:
            updated = dict(question)
            updated["type"] = chosen
            updated["status"] = "confirmed"
            questions.append(updated)
        else:
            questions.append(question)
    return {**split, "questions": questions}


def _is_divider(lines: list[str], index: int) -> bool:
    """A short heading between questions, such as 省考接轨. Stem lines stay put."""
    stripped = lines[index].strip()
    if not stripped or _DIVIDER.match(stripped) is None:
        return False
    if index == 0 or lines[index - 1].strip():
        return False
    for later in lines[index + 1 :]:
        later_stripped = later.strip()
        if not later_stripped:
            continue
        return _QUESTION.match(later_stripped) is not None
    return False


def _build(item: dict, rules: SplitRules) -> tuple[dict, bool]:
    body = "\n".join(item["lines"]).strip()
    section_type = item["section_type"]
    if section_type == "solution" or section_type is None:
        stem_source, subquestions = _peel_subs(body, rules)
    else:
        stem_source, subquestions = body, []
    stem_text, options = _peel_options(stem_source, rules)
    kind, status = _resolve(section_type, stem_text, options, subquestions, rules)
    missing = section_type in rules.option_required_types and len(options) < rules.needs_confirm_threshold
    draft = {
        "key": f"{item['section_index']}:{item['number']}",
        "section": item["section"],
        "number": item["number"],
        "type": kind,
        "status": status,
        "stem": _parts(stem_text),
        "options": options,
        "subquestions": subquestions,
    }
    return draft, missing


def _resolve(
    section_type: str | None,
    stem: str,
    options: list,
    subs: list,
    rules: SplitRules,
) -> tuple[str, str]:
    has_options = len(options) >= rules.needs_confirm_threshold
    has_blank = _BLANK.search(stem) is not None
    wants_multi = _MULTI.search(stem) is not None
    if section_type == "single_choice":
        return "single_choice", "candidate" if has_options else "needs_confirm"
    if section_type == "multiple_choice":
        return "multiple_choice", "candidate" if has_options else "needs_confirm"
    if section_type == "choice":
        if not has_options or has_blank:
            return "unresolved", "needs_confirm"
        if wants_multi:
            return "multiple_choice", "needs_confirm"
        return "single_choice", "needs_confirm"
    if section_type == "fill_blank":
        if has_options:
            return "unresolved", "needs_confirm"
        return "fill_blank", "candidate"
    if section_type == "solution":
        if has_options:
            return "unresolved", "needs_confirm"
        return "solution", "candidate"
    if has_options and has_blank:
        return "unresolved", "needs_confirm"
    if has_options and wants_multi:
        return "multiple_choice", "needs_confirm"
    if has_options:
        return "single_choice", "needs_confirm"
    if subs:
        return "solution", "needs_confirm"
    if has_blank:
        return "fill_blank", "candidate"
    return "unresolved", "needs_confirm"


def _peel_subs(body: str, rules: SplitRules) -> tuple[str, list[dict]]:
    marks = marker_spans(body, rules.subquestion_markers)
    if not marks:
        return body.strip(), []
    if len(marks) == 1:
        line_start = body.rfind("\n", 0, marks[0].start()) + 1
        if body[line_start : marks[0].start()].strip():
            return body.strip(), []
    stem = body[: marks[0].start()].strip()
    subs = []
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(body)
        subs.append({"number": mark.group(1), "stem": _parts(body[mark.end() : end])})
    return stem, subs


def _peel_options(text: str, rules: SplitRules) -> tuple[str, list[dict]]:
    marks = list(rules.option_pattern.finditer(text))
    if len(marks) < rules.needs_confirm_threshold:
        return text.strip(), []
    stem = text[: marks[0].start()].strip()
    options = []
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        options.append({"key": mark.group(1), "content": _parts(text[mark.end() : end])})
    return stem, options


def _parts(text: str) -> list[dict]:
    source = text.strip()
    if not source:
        return []
    parts: list[dict] = []
    index = 0
    while index < len(source):
        if source.startswith("$$", index):
            end = source.find("$$", index + 2)
            if end == -1:
                parts.append({"type": "text", "value": source[index:]})
                break
            latex = source[index + 2 : end].strip()
            if latex:
                parts.append({"type": "math", "latex": latex})
            index = end + 2
            continue
        if source[index] == "$":
            end = source.find("$", index + 1)
            if end == -1:
                parts.append({"type": "text", "value": source[index:]})
                break
            latex = source[index + 1 : end].strip()
            if latex:
                parts.append({"type": "math", "latex": latex})
            index = end + 1
            continue
        end = source.find("$", index)
        chunk = source[index:] if end == -1 else source[index:end]
        if chunk:
            parts.append({"type": "text", "value": chunk})
        index = len(source) if end == -1 else end
    return parts
