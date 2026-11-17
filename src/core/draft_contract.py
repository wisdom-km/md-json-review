"""The question-draft file both tools agree on. No database and no files."""

from __future__ import annotations

CONTRACT = "k12-question-draft"
CONTRACT_VERSION = 1
# A new label maps onto a structure. A new structure would need its own child rows.
STRUCTURE = {
    "single_choice": "choice",
    "multiple_choice": "choice",
    "fill_blank": "blank",
    "solution": "worked",
    "unresolved": "unresolved",
    "composite": "composite",
}


def to_draft_file(split: dict, pdf_page: int | None) -> dict:
    """Wrap one page split. geometry stays empty until an editor exists."""
    questions = []
    for item in split.get("questions") or []:
        questions.append(
            {
                "key": item["key"],
                "section": item["section"],
                "number": item["number"],
                "type": item["type"],
                "structure": STRUCTURE[item["type"]],
                "status": item["status"],
                "stem": item["stem"],
                "options": item["options"],
                "subquestions": item["subquestions"],
                "assets": [],
                "geometry": None,
            }
        )
    return {
        "contract": CONTRACT,
        "contract_version": CONTRACT_VERSION,
        "ok": bool(split.get("ok")),
        "reason": split.get("reason") or "",
        "preface": split.get("preface") or "",
        "source": {"pdf_page": pdf_page},
        "questions": questions,
    }
