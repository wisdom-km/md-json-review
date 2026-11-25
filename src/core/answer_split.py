"""Split one reviewed answer page into one draft per question. No database.

The section headings and question numbers match the question splitter, so
`1:1` on this page is the same key as question `1:1`. A choice answer keeps
the option letters only. Other answers keep text and math parts.
"""

from __future__ import annotations

import re

from core.convert import normalize_newlines
from core.split import _SECTION_SHAPE, _parts
from core.split_rules import SplitRules, marker_spans

_QUESTION = re.compile(r"^(\d+)[.．、]\s*(.*)$")
_DIVIDER = re.compile(r"^[\u4e00-\u9fff]{2,12}$")
_STEP = re.compile(r"^(?:解[:：]|步骤\s*\d*[:：.]?)\s*(.*)$")
_LETTER_SPLIT = re.compile(r"[,、，\s]+")
_HEADING = re.compile(r"^(#{2,4})(?!#)\s*(.*?)\s*$")
_INLINE = re.compile(r"\s+(\d+)[.．、](?!\d)")
_CHAPTER = re.compile(r"^第.+章")
_CN_CHAPTER = re.compile(r"^[一二三四五六七八九十]+、")
_FINER_LESSON = re.compile(r"\d+\.\d+|第.+节|课时")
_LESSON_MARK = re.compile(r"^(?:课时[:：]|【课时】)\s*(.*)$")


def split_answers(markdown: str, rules: SplitRules, default_lesson: str = "") -> dict:
    """Return answer drafts for one page. A page block list is not accepted here.

    default_lesson is the lesson already open on the previous page. Headings on
    this page replace it. lesson_title stays on the in-memory row and is not a
    k12-answer-draft field.
    """
    text = normalize_newlines(markdown).strip("\n")
    lines = text.split("\n") if text else []
    preface: list[str] = []
    raw: list[dict] = []
    mode = False
    section_label = ""
    section_index = 0
    current: dict | None = None
    current_lesson = default_lesson.strip() if isinstance(default_lesson, str) else ""

    def flush() -> None:
        nonlocal current
        if current is None:
            return
        raw.append(current)
        current = None

    def open_section(label: str) -> None:
        nonlocal mode, section_index, section_label
        flush()
        mode = True
        section_index += 1
        section_label = label

    def open_lesson(title: str) -> None:
        nonlocal mode, section_index, section_label, current_lesson
        flush()
        current_lesson = title.strip()
        section_index = 0
        mode = False
        section_label = ""

    for index, line in enumerate(lines):
        stripped = line.strip()
        heading = _HEADING.match(stripped)
        if heading:
            title = heading.group(2).strip()
            if not title or "参考答案" in title or title == "目录":
                continue
            matched = rules.match_type(title)
            if matched is not None:
                open_section(matched)
                continue
            if _SECTION_SHAPE.match(title):
                open_section("")
                continue
            if _is_pure_chapter(title):
                continue
            open_lesson(title)
            continue
        if not mode:
            mark = _LESSON_MARK.match(stripped)
            if mark:
                current_lesson = mark.group(1).strip()
                continue
        matched = rules.match_type(stripped)
        if matched is not None:
            open_section(matched)
            continue
        if _SECTION_SHAPE.match(stripped):
            open_section("")
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
            pieces = _inline_pieces(stripped)
            flush()
            if not pieces:
                current = _raw_item(
                    question.group(1),
                    question.group(2),
                    section_label,
                    section_index,
                    current_lesson,
                )
                continue
            for number, body in pieces[:-1]:
                raw.append(_raw_item(number, body, section_label, section_index, current_lesson))
            number, body = pieces[-1]
            current = _raw_item(number, body, section_label, section_index, current_lesson)
            continue
        if current is None:
            continue
        current["lines"].append(line)
    flush()

    seen_page: dict[str, int] = {}
    seen_lesson: dict[tuple[str, str], int] = {}
    answers = []
    for item in raw:
        question_key = f"{item['section_index']}:{item['number']}"
        lesson_title = item.get("lesson_title") or ""
        seen_page[question_key] = seen_page.get(question_key, 0) + 1
        pair = (lesson_title, question_key)
        seen_lesson[pair] = seen_lesson.get(pair, 0) + 1
        answers.append(
            _build(item, question_key, seen_page[question_key], seen_lesson[pair], rules)
        )
    return {
        "ok": True,
        "reason": "" if answers or not text else "",
        "preface": "\n".join(preface).strip(),
        "answers": answers,
    }


def _build(
    item: dict,
    question_key: str,
    page_ordinal: int,
    lesson_ordinal: int,
    rules: SplitRules,
) -> dict:
    body = "\n".join(item["lines"]).strip()
    label = item["section_label"]
    status = "candidate"
    if lesson_ordinal > 1 or not body:
        status = "needs_confirm"
    if label in rules.option_required_types:
        content, choice_status = _choice_content(body, rules)
        if choice_status == "needs_confirm":
            status = "needs_confirm"
        return {
            "question_key": question_key,
            "key": f"{question_key}:ocr:{page_ordinal}",
            "lesson_title": item.get("lesson_title") or "",
            "status": status,
            "content": content,
            "parts": [],
        }
    shared, subs = _peel_subs(body, rules)
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
            "key": f"{question_key}:ocr:{page_ordinal}",
            "lesson_title": item.get("lesson_title") or "",
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
        "key": f"{question_key}:ocr:{page_ordinal}",
            "lesson_title": item.get("lesson_title") or "",
        "status": status,
        "content": content,
        "parts": parts,
    }


def _raw_item(
    number: str,
    body: str,
    section_label: str,
    section_index: int,
    lesson_title: str,
) -> dict:
    return {
        "number": number,
        "lines": [body],
        "section_label": section_label,
        "section_index": section_index,
        "lesson_title": lesson_title,
    }


def _is_pure_chapter(title: str) -> bool:
    """A chapter line is not a lesson, and it must not replace a finer lesson."""
    if _FINER_LESSON.search(title):
        return False
    return _CHAPTER.match(title) is not None or _CN_CHAPTER.match(title) is not None


def _inline_pieces(line: str) -> list[tuple[str, str]] | None:
    """Split one answer line on later, strictly increasing question numbers.

    Markers inside $...$ or $$...$$ stay put. A decimal such as 3.5 is not a
    marker. Text ending in 步骤 or 第 is not a marker either.
    """
    head = _QUESTION.match(line)
    if head is None:
        return None
    spans = _math_spans(line)
    previous = int(head.group(1))
    cuts: list[tuple[int, int, str]] = []
    for match in _INLINE.finditer(line):
        number_at = match.start(1)
        if _in_span(spans, number_at):
            continue
        if line[: match.start()].endswith(("步骤", "第")):
            continue
        number = int(match.group(1))
        if number <= previous:
            continue
        previous = number
        cuts.append((match.start(), match.end(), match.group(1)))
    if not cuts:
        return None
    pieces: list[tuple[str, str]] = []
    first_from = head.start(2)
    first_end = _rstrip_index(line, cuts[0][0], first_from)
    pieces.append((head.group(1), line[first_from:first_end].strip()))
    for index, (_whitespace_at, content_at, number) in enumerate(cuts):
        if index + 1 < len(cuts):
            end = _rstrip_index(line, cuts[index + 1][0], content_at)
            body = line[content_at:end].strip()
        else:
            body = line[content_at:].strip()
        pieces.append((number, body))
    return pieces


def _rstrip_index(line: str, index: int, stop: int) -> int:
    while index > stop and line[index - 1].isspace():
        index -= 1
    return index


def _math_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    index = 0
    limit = len(text)
    while index < limit:
        if text.startswith("$$", index):
            end = text.find("$$", index + 2)
            if end < 0:
                spans.append((index, limit))
                break
            spans.append((index, end + 2))
            index = end + 2
            continue
        if text[index] == "$":
            end = text.find("$", index + 1)
            if end < 0:
                spans.append((index, limit))
                break
            spans.append((index, end + 1))
            index = end + 1
            continue
        index += 1
    return spans


def _in_span(spans: list[tuple[int, int]], pos: int) -> bool:
    return any(start <= pos < end for start, end in spans)


def _choice_content(body: str, rules: SplitRules) -> tuple[list[dict], str]:
    compact = re.sub(r"\s+", "", body)
    if not compact:
        return [], "needs_confirm"
    if rules.choice_body.fullmatch(compact) is None:
        return _parts(body), "needs_confirm"
    if any(mark in compact for mark in (",", "、", "，")):
        letters = [part for part in _LETTER_SPLIT.split(compact) if part]
    else:
        letters = list(compact)
    if len(letters) != len(set(letters)) or any(letter not in rules.option_keys for letter in letters):
        return _parts(body), "needs_confirm"
    value = letters[0] if len(letters) == 1 else ",".join(letters)
    return [{"type": "text", "value": value}], "candidate"


def _peel_subs(body: str, rules: SplitRules) -> tuple[str, list[tuple[str, str]]]:
    marks = marker_spans(body, rules.subquestion_markers)
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
