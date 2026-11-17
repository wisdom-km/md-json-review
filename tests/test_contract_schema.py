"""Generated drafts match the copied schema. A bad shape is refused before a write."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.contracts import require_question_draft
from core.convert import ConvertError
from core.draft_contract import to_draft_file
from core.schema_check import schema_problems, unknown_schema_keywords
from core.split import split_questions
from rules_loader import shipped_rules

ROOT = Path(__file__).resolve().parents[1]
PAGE = """一. 选择题
1. 负数有（ ）
A. 4个 B. 3个 C. 2个 D. 1个
"""


class ContractSchemaTest(unittest.TestCase):
    def test_copied_files_use_only_implemented_keywords(self) -> None:
        for name in ("k12-question-draft.v1.schema.json", "k12-answer-draft.v1.schema.json"):
            schema = json.loads((ROOT / "contracts" / name).read_text(encoding="utf-8"))
            self.assertEqual(unknown_schema_keywords(schema), [])

    def test_generated_question_file_matches_and_an_extra_field_is_refused(self) -> None:
        schema = json.loads((ROOT / "contracts" / "k12-question-draft.v1.schema.json").read_text(encoding="utf-8"))
        draft = to_draft_file(split_questions(PAGE, shipped_rules()), 1)
        self.assertEqual(schema_problems(schema, draft), [])
        draft["note"] = "no"
        with self.assertRaises(ConvertError) as caught:
            require_question_draft(draft)
        self.assertEqual(caught.exception.code, "CONTRACT")
        self.assertIn("note", caught.exception.message)


if __name__ == "__main__":
    unittest.main()
