"""Turn one page of Markdown into a preview and draft objects. No files are written."""

from __future__ import annotations

from pathlib import Path

from app.contracts import require_answer_draft, require_question_draft
from app.split_rules import load_split_rules
from app.store_read import _clean_role, _load_json, _page_md, page_number
from core.answer_contract import to_answer_files, to_answer_meta
from core.answer_split import split_answers
from core.convert import ConvertError, apply_markdown, dump_json, iter_blocks, normalize_newlines
from core.draft_contract import to_draft_file
from core.split import apply_type_overrides, split_questions


def preview_document(document: object, markdown: str) -> tuple[str, dict | None]:
    try:
        updated = apply_markdown(document, markdown)
    except ConvertError as exc:
        return "", {"error_code": exc.code, "message": exc.message}
    return dump_json(updated), None


def preview_page(
    book: Path,
    rel: str,
    markdown: str,
    *,
    page_role: str = "questions",
    answer_confirms: object = None,
    default_lesson: str = "",
) -> dict:
    md_path = _page_md(book, rel)
    document = _load_json(md_path.with_suffix(".json"))
    preview, preview_error = preview_document(document, markdown)
    if preview_error:
        raise ConvertError(preview_error["error_code"], preview_error["message"])
    text = normalize_newlines(markdown)
    role = _clean_role(page_role)
    answers, _draft, meta = checked_drafts(
        text,
        page_number(rel),
        role,
        answer_confirms,
        None,
        default_lesson=default_lesson,
    )
    return {
        "preview": preview,
        "block_count": len(iter_blocks(document)),
        "page_role": role,
        "questions": None if role == "answers" else split_questions(text, load_split_rules()),
        "answers": answers,
        "default_lesson": meta["default_lesson"] if meta else "",
        "answer_meta": meta,
    }


def checked_drafts(
    text: str,
    pdf_page: int | None,
    role: str,
    answer_confirms: object,
    type_overrides: object,
    default_lesson: str = "",
) -> tuple[list[dict], dict | None, dict | None]:
    """Return answer files, or one question draft. The contract check runs before any write."""
    rules = load_split_rules()
    if role == "answers":
        lesson = default_lesson.strip() if isinstance(default_lesson, str) else ""
        split = split_answers(text, rules, lesson)
        answer_files = to_answer_files(split, pdf_page, answer_confirms)
        for item in answer_files:
            require_answer_draft(item)
        return answer_files, None, to_answer_meta(split, pdf_page, lesson)
    draft = to_draft_file(apply_type_overrides(split_questions(text, rules), type_overrides), pdf_page)
    require_question_draft(draft)
    return [], draft, None
