"""Load the shipped contract schemas. Core checks the dict and does not read it."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from core.convert import ConvertError
from core.schema_check import schema_problems

_ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=4)
def _schema(file_name: str) -> dict:
    return json.loads((_ROOT / "contracts" / file_name).read_text(encoding="utf-8"))


def require_question_draft(payload: object) -> None:
    """Refuse a question file that misses k12-question-draft v1. Call before writing."""
    problems = schema_problems(_schema("k12-question-draft.v1.schema.json"), payload)
    if problems:
        raise ConvertError("CONTRACT", problems[0])


def require_answer_draft(payload: object) -> None:
    """Refuse an answer file that misses k12-answer-draft v1. Call before writing."""
    problems = schema_problems(_schema("k12-answer-draft.v1.schema.json"), payload)
    if problems:
        raise ConvertError("CONTRACT", problems[0])
