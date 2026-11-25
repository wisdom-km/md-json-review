"""One OCR answer file. The keys are the future answer-table columns."""

from __future__ import annotations

CONTRACT = "k12-answer-draft"
CONTRACT_VERSION = 1
SCHEMA_VERSION = 1


def to_answer_files(split: dict, pdf_page: int | None, confirms: object) -> list[dict]:
    """One dict per answer. A teacher confirm marks that one file applicable."""
    chosen = confirms if isinstance(confirms, (set, list, tuple)) else []
    chosen_keys = {item for item in chosen if isinstance(item, str)}
    files = []
    for item in split.get("answers") or []:
        confirmed = item["key"] in chosen_keys
        files.append(
            {
                "contract": CONTRACT,
                "contract_version": CONTRACT_VERSION,
                "schema_version": SCHEMA_VERSION,
                "ok": True,
                "reason": "",
                "question_key": item["question_key"],
                "key": item["key"],
                "origin": "ocr",
                "status": "confirmed" if confirmed else item["status"],
                "applicable": confirmed,
                "source": {"pdf_page": pdf_page},
                "content": item["content"],
                "parts": item["parts"],
                "assets": [],
            }
        )
    return files


def to_answer_meta(split: dict, pdf_page: int | None, default_lesson: str) -> dict:
    """Lesson titles sit beside the drafts. They are not answer-draft fields."""
    lesson = default_lesson.strip() if isinstance(default_lesson, str) else ""
    rows = []
    for item in split.get("answers") or []:
        title = item.get("lesson_title") or ""
        rows.append(
            {
                "key": item["key"],
                "question_key": item["question_key"],
                "lesson_title": title if isinstance(title, str) else "",
            }
        )
    return {
        "schema_version": 1,
        "pdf_page": pdf_page,
        "default_lesson": lesson,
        "answers": rows,
    }


def answer_filename(answer_key: str) -> str:
    """Windows file name. The JSON key still uses colons."""
    return answer_key.replace(":", "-") + ".json"
