"""OCR answer pages become one k12-answer-draft file per answer."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.store import export_page, read_page, save_page
from core.answer_contract import answer_filename, to_answer_files
from core.answer_split import split_answers
from core.split import split_questions
from rules_loader import shipped_rules

RULES = shipped_rules()

FILE_KEYS = {
    "contract",
    "contract_version",
    "schema_version",
    "ok",
    "reason",
    "question_key",
    "key",
    "origin",
    "status",
    "applicable",
    "source",
    "content",
    "parts",
    "assets",
}


def write_book(root: Path) -> None:
    page = root / "page_0001" / "input_1_page_0001"
    page.mkdir(parents=True)
    document = [[{"index": 0, "label": "text", "content": "旧", "bbox_2d": None}]]
    (page / "input_1_page_0001.md").write_text("旧\n", encoding="utf-8", newline="\n")
    (page / "input_1_page_0001.json").write_text(
        json.dumps(document, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


class AnswerSplitTests(unittest.TestCase):
    def test_choice_letters_match_the_question_key(self):
        page = "一. 选择题\n1. A\n2. AC\n"
        split = split_answers(page, RULES)
        self.assertTrue(split["ok"])
        self.assertEqual([item["key"] for item in split["answers"]], ["1:1:ocr:1", "1:2:ocr:1"])
        self.assertEqual(split["answers"][0]["content"], [{"type": "text", "value": "A"}])
        self.assertEqual(split["answers"][1]["content"], [{"type": "text", "value": "A,C"}])
        self.assertEqual(split["answers"][0]["parts"], [])
        as_questions = split_questions(page, RULES)
        self.assertTrue(as_questions["ok"])
        self.assertEqual(as_questions["questions"][0]["status"], "needs_confirm")

    def test_choice_answers_on_separate_lines_become_separate_drafts(self):
        page = "一. 选择题\n1. C\n2. C\n3. A\n"
        split = split_answers(page, RULES)
        self.assertEqual(
            [item["content"] for item in split["answers"]],
            [
                [{"type": "text", "value": "C"}],
                [{"type": "text", "value": "C"}],
                [{"type": "text", "value": "A"}],
            ],
        )

    def test_words_and_repeated_letters_need_confirm(self):
        split = split_answers("一. 选择题\n1. 见解析\n2. A,A\n", RULES)
        self.assertEqual(split["answers"][0]["status"], "needs_confirm")
        self.assertEqual(split["answers"][0]["content"][0]["value"], "见解析")
        self.assertEqual(split["answers"][1]["status"], "needs_confirm")

    def test_fill_math_and_worked_steps_keep_parts(self):
        page = "一. 填空题\n4. $2$\n\n二. 解答题\n7. 结果 $2$\n解：先算\n(1) $1$\n解：再算\n(2) $3$\n"
        split = split_answers(page, RULES)
        fill = split["answers"][0]
        worked = split["answers"][1]
        self.assertEqual(fill["question_key"], "1:4")
        self.assertEqual(fill["content"], [{"type": "math", "latex": "2"}])
        self.assertEqual(worked["question_key"], "2:7")
        self.assertEqual(worked["content"][0]["type"], "text")
        self.assertEqual(worked["content"][1], {"type": "math", "latex": "2"})
        roles = [(part["sub_key"], part["role"], part["order"]) for part in worked["parts"]]
        self.assertEqual(roles, [("", "step", 1), ("1", "result", 2), ("1", "step", 3), ("2", "result", 4)])

    def test_confirm_writes_the_answer_table_keys(self):
        files = to_answer_files(
            split_answers("一. 选择题\n1. A\n", RULES),
            3,
            ["1:1:ocr:1"],
        )
        self.assertEqual(len(files), 1)
        self.assertEqual(set(files[0]), FILE_KEYS)
        self.assertEqual(files[0]["contract"], "k12-answer-draft")
        self.assertEqual(files[0]["contract_version"], 1)
        self.assertIs(files[0]["contract_version"], 1)
        self.assertEqual(files[0]["schema_version"], 1)
        self.assertIs(files[0]["schema_version"], 1)
        self.assertEqual(files[0]["origin"], "ocr")
        self.assertEqual(files[0]["status"], "confirmed")
        self.assertTrue(files[0]["applicable"])
        self.assertEqual(files[0]["source"], {"pdf_page": 3})
        self.assertEqual(files[0]["assets"], [])
        self.assertEqual(answer_filename(files[0]["key"]), "1-1-ocr-1.json")


class AnswerStoreTests(unittest.TestCase):
    def test_save_writes_one_file_per_answer_and_leaves_originals(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            book = Path(temporary)
            write_book(book)
            rel = "page_0001/input_1_page_0001/input_1_page_0001.md"
            original_md = (book / rel).read_bytes()
            original_json = (book / rel).with_suffix(".json").read_bytes()
            markdown = "一. 选择题\n1. A\n2. C\n"
            saved = save_page(
                book,
                rel,
                markdown,
                backup=True,
                page_role="answers",
                answer_confirms=["1:1:ocr:1"],
            )
            self.assertEqual(saved["page_role"], "answers")
            self.assertEqual(saved["answer_count"], 2)
            self.assertEqual((book / rel).read_bytes(), original_md)
            self.assertEqual((book / rel).with_suffix(".json").read_bytes(), original_json)
            folder = book / "page_0001" / "input_1_page_0001"
            self.assertFalse((folder / "input_1_page_0001.questions.json").exists())
            role = (folder / "input_1_page_0001.page-role.txt").read_text(encoding="utf-8")
            self.assertEqual(role, "answers\n")
            adopted = json.loads((folder / "input_1_page_0001.answers" / "1-1-ocr-1.json").read_text(encoding="utf-8"))
            other = json.loads((folder / "input_1_page_0001.answers" / "1-2-ocr-1.json").read_text(encoding="utf-8"))
            self.assertTrue(adopted["applicable"])
            self.assertEqual(adopted["status"], "confirmed")
            self.assertFalse(other["applicable"])
            self.assertEqual(other["content"], [{"type": "text", "value": "C"}])
            loaded = read_page(book, rel)
            self.assertEqual(loaded["page_role"], "answers")
            self.assertIsNone(loaded["questions"])
            self.assertEqual(len(loaded["answers"]), 2)

    def test_question_save_does_not_delete_answer_files(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            book = Path(temporary)
            write_book(book)
            rel = "page_0001/input_1_page_0001/input_1_page_0001.md"
            save_page(book, rel, "一. 选择题\n1. A\n", backup=True, page_role="answers")
            save_page(book, rel, "一. 选择题\n1. 题干\nA. 甲\nB. 乙\n", backup=True, page_role="questions")
            folder = book / "page_0001" / "input_1_page_0001"
            self.assertTrue((folder / "input_1_page_0001.questions.json").is_file())
            self.assertTrue((folder / "input_1_page_0001.answers" / "1-1-ocr-1.json").is_file())
            loaded = read_page(book, rel)
            self.assertEqual(loaded["page_role"], "questions")
            self.assertEqual(loaded["answers"], [])

    def test_a_later_answer_save_drops_a_removed_file(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            book = Path(temporary)
            write_book(book)
            rel = "page_0001/input_1_page_0001/input_1_page_0001.md"
            save_page(book, rel, "一. 选择题\n1. A\n2. C\n", backup=True, page_role="answers")
            save_page(book, rel, "一. 选择题\n1. B\n", backup=True, page_role="answers")
            folder = book / "page_0001" / "input_1_page_0001" / "input_1_page_0001.answers"
            names = sorted(path.name for path in folder.glob("*.json"))
            self.assertEqual(names, ["1-1-ocr-1.json"])
            backups = list((book / "_review_backups").rglob("1-2-ocr-1.json"))
            self.assertEqual(len(backups), 1)

    def test_export_copies_the_answer_files(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            book = Path(temporary) / "book"
            book.mkdir()
            write_book(book)
            rel = "page_0001/input_1_page_0001/input_1_page_0001.md"
            dest = Path(temporary) / "out"
            dest.mkdir()
            exported = export_page(
                book,
                rel,
                "一. 选择题\n1. A\n",
                str(dest),
                page_role="answers",
                answer_confirms=["1:1:ocr:1"],
            )
            self.assertEqual(exported["answer_count"], 1)
            copied = json.loads((dest / "input_1_page_0001.answers" / "1-1-ocr-1.json").read_text(encoding="utf-8"))
            self.assertEqual(copied["contract"], "k12-answer-draft")
            self.assertTrue(copied["applicable"])
            self.assertFalse((dest / "input_1_page_0001.questions.json").exists())


if __name__ == "__main__":
    unittest.main()
