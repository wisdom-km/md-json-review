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


def answer_filename(answer_key: str) -> str:
    """Windows file name. The JSON key still uses colons."""
    return answer_key.replace(":", "-") + ".json"
