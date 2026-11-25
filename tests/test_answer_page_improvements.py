"""Numeric type headings, same-line answers, and the lesson sidecar.

Fixtures are synthetic. They are not pages from a book.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.contracts import require_answer_draft
from app.store import export_page, preview_page, read_page, save_page
from core.answer_contract import to_answer_files
from core.answer_split import split_answers
from core.split import split_questions
from rules_loader import shipped_rules

RULES = shipped_rules()

CHOICE = "1. synth-stem\nA. 左\nB. 右\n"
STEM = "page_0001/input_1_page_0001/input_1_page_0001"


def write_book(root: Path) -> str:
    page = root / "page_0001" / "input_1_page_0001"
    page.mkdir(parents=True)
    document = [[{"index": 0, "label": "text", "content": "旧", "bbox_2d": None}]]
    rel = STEM + ".md"
    (root / rel).write_text("旧\n", encoding="utf-8", newline="\n")
    (root / rel).with_suffix(".json").write_text(
        json.dumps(document, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return rel


class NumericHeadingTests(unittest.TestCase):
    def test_arabic_type_headings_open_sections_on_both_pages(self):
        page = "1. 选择题\n" + CHOICE + "2. 填空题\n1. synth-blank\n3. 解答题\n1. synth-work\n"
        questions = split_questions(page, RULES)
        self.assertTrue(questions["ok"])
        self.assertEqual([item["key"] for item in questions["questions"]], ["1:1", "2:1", "3:1"])
        self.assertEqual(
            [item["type"] for item in questions["questions"]],
            ["single_choice", "fill_blank", "solution"],
        )
        self.assertEqual(questions["questions"][0]["section"], "1. 选择题")
        named = "1、单选题\n" + CHOICE + "2．多选题\n" + CHOICE
        named_questions = split_questions(named, RULES)["questions"]
        self.assertEqual(
            [item["type"] for item in named_questions],
            ["single_choice", "multiple_choice"],
        )
        self.assertEqual([item["status"] for item in named_questions], ["candidate", "candidate"])
        answers = split_answers(page, RULES)["answers"]
        self.assertEqual([item["question_key"] for item in answers], ["1:1", "2:1", "3:1"])
        self.assertEqual(answers[1]["content"], [{"type": "text", "value": "synth-blank"}])
        self.assertEqual(answers[2]["content"], [{"type": "text", "value": "synth-work"}])
        named_answers = split_answers("1、单选题\n1. A\n2．多选题\n1. A、C\n", RULES)["answers"]
        self.assertEqual(named_answers[0]["content"], [{"type": "text", "value": "A"}])
        self.assertEqual(named_answers[1]["content"], [{"type": "text", "value": "A,C"}])

    def test_a_short_digit_line_is_not_a_type_heading(self):
        page = "1. A\n1. synth-stem\n"
        self.assertEqual(split_questions(page, RULES)["questions"], [])
        self.assertEqual(split_answers(page, RULES)["answers"], [])
        self.assertIn("1. A", split_questions(page, RULES)["preface"])
        stayed = split_questions("1. 填空题\n1. A  2. B  3. C\n", RULES)["questions"]
        self.assertEqual(len(stayed), 1)
        self.assertEqual(stayed[0]["key"], "1:1")


class SameLineAnswerTests(unittest.TestCase):
    def test_choice_answers_on_one_line_become_three_drafts(self):
        split = split_answers("1. 选择题\n1. A  2. B  3. C\n1、A  2、B\n", RULES)
        keys = [item["key"] for item in split["answers"]]
        self.assertEqual(keys[:3], ["1:1:ocr:1", "1:2:ocr:1", "1:3:ocr:1"])
        self.assertEqual(
            [item["content"][0]["value"] for item in split["answers"][:3]],
            ["A", "B", "C"],
        )
        self.assertEqual([item["content"][0]["value"] for item in split["answers"][3:]], ["A", "B"])

    def test_fill_decimals_stay_inside_one_answer(self):
        split = split_answers("2. 填空题\n4. -2  5. 3.5  6. 0\n", RULES)
        self.assertEqual([item["question_key"] for item in split["answers"]], ["1:4", "1:5", "1:6"])
        self.assertEqual(
            [item["content"][0]["value"] for item in split["answers"]],
            ["-2", "3.5", "0"],
        )

    def test_math_and_steps_and_decreasing_numbers_stay_together(self):
        math = split_answers("1. 填空题\n1. $1.5 + 2.5$\n", RULES)
        self.assertEqual(len(math["answers"]), 1)
        self.assertEqual(math["answers"][0]["content"], [{"type": "math", "latex": "1.5 + 2.5"}])
        step = split_answers("1. 填空题\n1. 先算 步骤 2. 再合并\n", RULES)
        self.assertEqual(len(step["answers"]), 1)
        self.assertIn("步骤 2.", step["answers"][0]["content"][0]["value"])
        down = split_answers("1. 填空题\n8. 见 3. 说明\n1. 见 1. 再写\n", RULES)
        self.assertEqual(len(down["answers"]), 2)
        self.assertIn("3. 说明", down["answers"][0]["content"][0]["value"])
        self.assertIn("1. 再写", down["answers"][1]["content"][0]["value"])

    def test_a_following_line_belongs_to_the_last_piece(self):
        split = split_answers("1. 填空题\n1. synth-a  2. synth-b\n续行\n", RULES)
        self.assertEqual(len(split["answers"]), 2)
        self.assertEqual(split["answers"][0]["content"][0]["value"], "synth-a")
        self.assertIn("synth-b", split["answers"][1]["content"][0]["value"])
        self.assertIn("续行", split["answers"][1]["content"][0]["value"])
        self.assertNotIn("续行", split["answers"][0]["content"][0]["value"])

    def test_one_line_and_worked_solution_stay_one_answer(self):
        single = split_answers("1. 填空题\n1. synth-only\n", RULES)
        self.assertEqual([item["key"] for item in single["answers"]], ["1:1:ocr:1"])
        page = "3. 解答题\n7. 结果 $2$\n解：先算\n(1) $1$\n步骤：再写\n(2) $3$\n"
        worked = split_answers(page, RULES)["answers"]
        self.assertEqual(len(worked), 1)
        self.assertEqual(worked[0]["question_key"], "1:7")
        roles = [(part["sub_key"], part["role"]) for part in worked[0]["parts"]]
        self.assertEqual(roles, [("", "step"), ("1", "result"), ("1", "step"), ("2", "result")])


class LessonSidecarTests(unittest.TestCase):
    def test_two_lessons_may_repeat_a_question_key(self):
        page = (
            "## synth-lesson-1\n1. 选择题\n1. A\n"
            "## synth-lesson-2\n1. 选择题\n1. B\n"
        )
        answers = split_answers(page, RULES)["answers"]
        self.assertEqual([item["question_key"] for item in answers], ["1:1", "1:1"])
        self.assertEqual([item["key"] for item in answers], ["1:1:ocr:1", "1:1:ocr:2"])
        self.assertEqual(
            [item["lesson_title"] for item in answers],
            ["synth-lesson-1", "synth-lesson-2"],
        )
        self.assertEqual([item["status"] for item in answers], ["candidate", "candidate"])
        typed = split_answers("## 1. 选择题\n1. A\n", RULES)["answers"]
        self.assertEqual(len(typed), 1)
        self.assertEqual(typed[0]["lesson_title"], "")

    def test_the_same_lesson_marks_a_repeated_key(self):
        page = "## synth-lesson-1\n1. 选择题\n1. A\n1. B\n"
        answers = split_answers(page, RULES)["answers"]
        self.assertEqual([item["key"] for item in answers], ["1:1:ocr:1", "1:1:ocr:2"])
        self.assertEqual([item["status"] for item in answers], ["candidate", "needs_confirm"])
        self.assertEqual(answers[0]["lesson_title"], "synth-lesson-1")

    def test_default_lesson_holds_until_a_new_heading(self):
        page = (
            "## 参考答案\n## 目录\n## 第1章 synth\n"
            "课时：synth-mark\n1. 选择题\n1. A\n"
            "## 1.1 synth-lesson\n1. 选择题\n1. B\n"
        )
        answers = split_answers(page, RULES, default_lesson="  synth-carried  ")["answers"]
        self.assertEqual(
            [item["lesson_title"] for item in answers],
            ["synth-mark", "1.1 synth-lesson"],
        )
        carried = split_answers("1. 选择题\n1. A\n", RULES, "synth-carried")["answers"]
        self.assertEqual(carried[0]["lesson_title"], "synth-carried")
        bracket = split_answers("【课时】synth-bracket\n1. 选择题\n1. C\n", RULES)["answers"]
        self.assertEqual(bracket[0]["lesson_title"], "synth-bracket")

    def test_answer_files_keep_the_contract_and_the_sidecar_stays_outside(self):
        page = "## synth-lesson-1\n1. 选择题\n1. A\n## synth-lesson-2\n1. 选择题\n1. B\n"
        split = split_answers(page, RULES, "synth-carried")
        files = to_answer_files(split, 1, [])
        for item in files:
            require_answer_draft(item)
            self.assertNotIn("lesson_title", item)
        with tempfile.TemporaryDirectory() as temporary:
            book = Path(temporary)
            rel = write_book(book)
            original_md = (book / rel).read_bytes()
            original_json = (book / rel).with_suffix(".json").read_bytes()
            folder = book / "page_0001" / "input_1_page_0001"
            meta = folder / "input_1_page_0001.answers-meta.json"
            answers = folder / "input_1_page_0001.answers"
            save_page(
                book,
                rel,
                page,
                backup=False,
                page_role="answers",
                default_lesson="synth-carried",
            )
            self.assertFalse(meta.exists())
            self.assertFalse(answers.exists())
            save_page(
                book,
                rel,
                page,
                backup=True,
                page_role="answers",
                default_lesson=" synth-carried ",
            )
            self.assertTrue(meta.is_file())
            self.assertEqual(meta.parent, answers.parent)
            self.assertFalse((answers / meta.name).exists())
            stored = json.loads(meta.read_text(encoding="utf-8"))
            self.assertEqual(stored["schema_version"], 1)
            self.assertEqual(stored["pdf_page"], 1)
            self.assertEqual(stored["default_lesson"], "synth-carried")
            self.assertEqual(
                [(row["key"], row["question_key"], row["lesson_title"]) for row in stored["answers"]],
                [
                    ("1:1:ocr:1", "1:1", "synth-lesson-1"),
                    ("1:1:ocr:2", "1:1", "synth-lesson-2"),
                ],
            )
            for path in answers.glob("*.json"):
                payload = json.loads(path.read_text(encoding="utf-8"))
                require_answer_draft(payload)
                self.assertNotIn("lesson_title", payload)
            loaded = read_page(book, rel)
            self.assertEqual(loaded["default_lesson"], "synth-carried")
            self.assertEqual(loaded["answer_meta"]["answers"][1]["lesson_title"], "synth-lesson-2")
            frozen = meta.read_bytes()
            save_page(
                book,
                rel,
                page + "\n",
                backup=False,
                page_role="answers",
                default_lesson="synth-other",
            )
            self.assertEqual(meta.read_bytes(), frozen)
            self.assertEqual(sorted(path.name for path in answers.glob("*.json")), ["1-1-ocr-1.json", "1-1-ocr-2.json"])
            save_page(
                book,
                rel,
                "1. 选择题\n1. C\n",
                backup=True,
                page_role="answers",
                default_lesson="synth-next",
            )
            backups = list((book / "_review_backups").rglob("input_1_page_0001.answers-meta.json"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(json.loads(backups[0].read_text(encoding="utf-8"))["default_lesson"], "synth-carried")
            current = json.loads(meta.read_text(encoding="utf-8"))
            self.assertEqual(current["default_lesson"], "synth-next")
            self.assertEqual(current["answers"][0]["lesson_title"], "synth-next")
            self.assertEqual((book / rel).read_bytes(), original_md)
            self.assertEqual((book / rel).with_suffix(".json").read_bytes(), original_json)
            preview = preview_page(
                book,
                rel,
                "1. 选择题\n1. D\n",
                page_role="answers",
                default_lesson="synth-preview",
            )
            self.assertEqual(preview["default_lesson"], "synth-preview")
            self.assertEqual(preview["answer_meta"]["answers"][0]["lesson_title"], "synth-preview")
            self.assertNotIn("lesson_title", preview["answers"][0])

    def test_export_writes_the_sidecar_beside_the_answers_and_backs_it_up(self):
        with tempfile.TemporaryDirectory() as temporary:
            book = Path(temporary) / "book"
            book.mkdir()
            rel = write_book(book)
            original_md = (book / rel).read_bytes()
            original_json = (book / rel).with_suffix(".json").read_bytes()
            dest = Path(temporary) / "out"
            dest.mkdir()
            export_page(
                book,
                rel,
                "## synth-lesson-1\n1. 选择题\n1. A\n",
                str(dest),
                page_role="answers",
                default_lesson="synth-carried",
            )
            meta = dest / "input_1_page_0001.answers-meta.json"
            answers = dest / "input_1_page_0001.answers"
            self.assertTrue(meta.is_file())
            self.assertEqual(meta.parent, answers.parent)
            self.assertFalse((answers / meta.name).exists())
            first = json.loads(meta.read_text(encoding="utf-8"))
            self.assertEqual(first["answers"][0]["lesson_title"], "synth-lesson-1")
            export_page(
                book,
                rel,
                "1. 选择题\n1. B\n",
                str(dest),
                page_role="answers",
                default_lesson="synth-next",
            )
            backups = list((dest / "_export_backups").rglob("input_1_page_0001.answers-meta.json"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(json.loads(backups[0].read_text(encoding="utf-8"))["default_lesson"], "synth-carried")
            second = json.loads(meta.read_text(encoding="utf-8"))
            self.assertEqual(second["default_lesson"], "synth-next")
            self.assertEqual(second["answers"][0]["lesson_title"], "synth-next")
            self.assertEqual((book / rel).read_bytes(), original_md)
            self.assertEqual((book / rel).with_suffix(".json").read_bytes(), original_json)


if __name__ == "__main__":
    unittest.main()
