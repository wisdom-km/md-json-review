"""Split one reviewed answer page into one draft per question. No database.

The section headings and question numbers match the question splitter, so
`1:1` on this page is the same key as question `1:1`. A choice answer keeps
the option letters only. Other answers keep text and math parts.
"""

from __future__ import annotations

import re

from core.convert import normalize_newlines
from core.split import _parts

_SECTION = re.compile(
    r"^[一二三四五六七八九十]+[.．、]\s*(单选题|多选题|选择题|填空题|解答题)\s*$"
)
_QUESTION = re.compile(r"^(\d+)[.．、]\s*(.*)$")
_SUB = re.compile(r"[（(](\d+)[）)]")
_DIVIDER = re.compile(r"^[\u4e00-\u9fff]{2,12}$")
_STEP = re.compile(r"^(?:解[:：]|步骤\s*\d*[:：.]?)\s*(.*)$")
_LETTER_SPLIT = re.compile(r"[,、，\s]+")
_CHOICE = {"单选题", "多选题", "选择题"}


def split_answers(markdown: str) -> dict:
    """Return answer drafts for one page. A page block list is not accepted here."""
    text = normalize_newlines(markdown).strip("\n")
    lines = text.split("\n") if text else []
    preface: list[str] = []
    raw: list[dict] = []
    mode = False
    section_label = ""
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
        section = _SECTION.match(stripped)
        if section:
            flush()
            mode = True
            section_index += 1
            section_label = section.group(1)
            continue
        if not mode:
            preface.append(line)
            continue
        if _is_divider(lines, index):
            flush()
            section_index += 1
            section_label = ""
            continue
        question = _QUESTION.match(stripped)
        if question:
            flush()
            current = {
                "number": question.group(1),
                "lines": [question.group(2)],
                "section_label": section_label,
                "section_index": section_index,
            }
            continue
        if current is None:
            continue
        current["lines"].append(line)
    flush()

    seen: dict[str, int] = {}
    answers = []
    for item in raw:
        question_key = f"{item['section_index']}:{item['number']}"
        seen[question_key] = seen.get(question_key, 0) + 1
        answers.append(_build(item, question_key, seen[question_key]))
    return {
        "ok": True,
        "reason": "" if answers or not text else "",
        "preface": "\n".join(preface).strip(),
        "answers": answers,
    }


def _build(item: dict, question_key: str, ordinal: int) -> dict:
    body = "\n".join(item["lines"]).strip()
    label = item["section_label"]
    status = "candidate"
    if ordinal > 1 or not body:
        status = "needs_confirm"
    if label in _CHOICE:
        content, choice_status = _choice_content(body)
        if choice_status == "needs_confirm":
            status = "needs_confirm"
        return {
            "question_key": question_key,
            "key": f"{question_key}:ocr:{ordinal}",
            "status": status,
            "content": content,
            "parts": [],
        }
    shared, subs = _peel_subs(body)
    if subs:
        shared_result, shared_steps = _steps(shared)
        content = _parts(shared_result)
        parts: list[dict] = []
        order = _append_steps(parts, shared_steps, "", 1)
        order = _append_subs(parts, subs, order)
        if not content and not parts:
            status = "needs_confirm"
        return {
            "question_key": question_key,
            "key": f"{question_key}:ocr:{ordinal}",
            "status": status,
            "content": content,
            "parts": parts,
        }
    result, steps = _steps(body)
    content = _parts(result)
    parts: list[dict] = []
    _append_steps(parts, steps, "", 1)
    if not content and not parts:
        status = "needs_confirm"
    return {
        "question_key": question_key,
        "key": f"{question_key}:ocr:{ordinal}",
        "status": status,
        "content": content,
        "parts": parts,
    }


def _choice_content(body: str) -> tuple[list[dict], str]:
    compact = re.sub(r"\s+", "", body)
    if not compact:
        return [], "needs_confirm"
    if re.fullmatch(r"[A-D](?:[,、，][A-D])*|[A-D]{1,4}", compact) is None:
        return _parts(body), "needs_confirm"
    if any(mark in compact for mark in (",", "、", "，")):
        letters = [part for part in _LETTER_SPLIT.split(compact) if part]
    else:
        letters = list(compact)
    if len(letters) != len(set(letters)) or any(len(letter) != 1 for letter in letters):
        return _parts(body), "needs_confirm"
    value = letters[0] if len(letters) == 1 else ",".join(letters)
    return [{"type": "text", "value": value}], "candidate"


def _peel_subs(body: str) -> tuple[str, list[tuple[str, str]]]:
    marks = list(_SUB.finditer(body))
    if len(marks) < 2:
        return body.strip(), []
    shared = body[: marks[0].start()].strip()
    subs = []
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(body)
        subs.append((mark.group(1), body[mark.end() : end].strip()))
    return shared, subs


def _append_subs(parts: list[dict], subs: list[tuple[str, str]], order: int) -> int:
    for number, text in subs:
        result, steps = _steps(text)
        result_content = _parts(result)
        if result_content:
            parts.append(
                {"sub_key": number, "role": "result", "order": order, "content": result_content}
            )
            order += 1
        order = _append_steps(parts, steps, number, order)
    return order


def _append_steps(parts: list[dict], steps: list[str], sub_key: str, order: int) -> int:
    for step in steps:
        step_content = _parts(step)
        if not step_content:
            continue
        parts.append({"sub_key": sub_key, "role": "step", "order": order, "content": step_content})
        order += 1
    return order


def _steps(text: str) -> tuple[str, list[str]]:
    result: list[str] = []
    steps: list[str] = []
    current: list[str] | None = None
    for line in text.split("\n"):
        matched = _STEP.match(line.strip())
        if matched:
            if current is not None:
                steps.append("\n".join(current).strip())
            current = [matched.group(1)]
            continue
        if current is None:
            result.append(line)
        else:
            current.append(line)
    if current is not None:
        steps.append("\n".join(current).strip())
    return "\n".join(result).strip(), [step for step in steps if step]


def _is_divider(lines: list[str], index: int) -> bool:
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
