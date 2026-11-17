import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.draft_contract import to_draft_file
from core.split import apply_type_overrides, split_questions
from core.split_rules import compile_rules
from rules_loader import rules_with, shipped_rules

RULES = shipped_rules()

PAGE = """知识导读
1. 大于 0 的数。

一. 选择题
1. 负数有（ ）
A. 4个 B. 3个 C. 2个 D. 1个
2. 既是负数又是分数的是（ ）
A. -2 B. $\\frac{1}{3}$ C. -1.5 D. 0
3. 正确的有（ ）
第一句
A. 1个 B. 2个 C. 3个 D. 4个

二. 填空题
4. 写成负数：___。
5. 正数有___，负数有___。

三. 解答题
7. 分别表示什么意义？
(1)25元
(2)-12元

省考接轨
1. 属于负数的个数为___个.
2. 向___走___米.
"""


class SplitTests(unittest.TestCase):
    def test_sample_shape_splits_without_merging_restarted_numbers(self):
        result = split_questions(PAGE, RULES)
        self.assertTrue(result["ok"])
        self.assertIn("知识导读", result["preface"])
        self.assertNotIn("负数有", result["preface"])
        questions = result["questions"]
        self.assertEqual([item["number"] for item in questions], ["1", "2", "3", "4", "5", "7", "1", "2"])
        self.assertEqual(questions[0]["key"], "1:1")
        self.assertEqual(questions[6]["key"], "4:1")
        kinds = [item["type"] for item in questions]
        self.assertEqual(kinds, [
            "single_choice",
            "single_choice",
            "single_choice",
            "fill_blank",
            "fill_blank",
            "solution",
            "fill_blank",
            "fill_blank",
        ])
        self.assertEqual(questions[1]["options"][1]["content"], [{"type": "math", "latex": "\\frac{1}{3}"}])
        self.assertEqual(questions[2]["status"], "needs_confirm")
        self.assertEqual([item["number"] for item in questions[5]["subquestions"]], ["1", "2"])
        self.assertNotIn("multiple_choice", kinds)

    def test_subquestions_on_one_line_stay_one_question(self):
        text = "三. 解答题\n7. 分别表示什么？\n(1)25元； (2)7.3元； (3)-12元； (4)0元\n"
        result = split_questions(text, RULES)
        self.assertEqual(len(result["questions"]), 1)
        self.assertEqual(
            [item["number"] for item in result["questions"][0]["subquestions"]],
            ["1", "2", "3", "4"],
        )

    def test_choice_without_options_stays_and_needs_confirm(self):
        result = split_questions("一. 选择题\n1. 只有题干\n2. 下一题\nA. 1 B. 2\n", RULES)
        self.assertTrue(result["ok"])
        self.assertEqual(result["questions"][0]["status"], "needs_confirm")
        self.assertEqual(result["questions"][0]["options"], [])
        self.assertEqual(result["questions"][1]["type"], "single_choice")

    def test_reject_flag_still_drops_the_whole_page(self):
        result = split_questions(
            "一. 选择题\n1. 只有题干\n",
            rules_with(reject_on_missing_options=True),
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["questions"], [])
        self.assertIn("选项", result["reason"])

    def test_caller_patterns_replace_the_shipped_headings(self):
        plain = split_questions("单选题\n1. 题干\nA. 1 B. 2\n", RULES)
        self.assertEqual(plain["questions"], [])
        custom = rules_with(
            type_patterns=[{"pattern": "^单选\\s*题\\s*$", "type": "single_choice"}]
        )
        found = split_questions("单选题\n1. 题干\nA. 1 B. 2\n", custom)
        self.assertEqual(found["questions"][0]["type"], "single_choice")
        self.assertEqual(found["questions"][0]["status"], "candidate")

    def test_bad_rules_name_the_field(self):
        payload = json.loads((Path(__file__).resolve().parents[1] / "config" / "split_rules.json").read_text(encoding="utf-8"))
        payload["option_pattern"] = "A-D"
        with self.assertRaises(ValueError) as caught:
            compile_rules(payload)
        self.assertIn("option_pattern", str(caught.exception))

    def test_explicit_multiple_and_conflict(self):
        multi = split_questions("一. 多选题\n1. 哪些是负数\nA. -1 B. 2\n", RULES)
        self.assertEqual(multi["questions"][0]["type"], "multiple_choice")
        self.assertEqual(multi["questions"][0]["status"], "candidate")
        mixed = split_questions("一. 填空题\n1. 选一个___\nA. 1 B. 2\n", RULES)
        self.assertEqual(mixed["questions"][0]["type"], "unresolved")
        self.assertEqual(mixed["questions"][0]["status"], "needs_confirm")

    def test_override_confirms_only_known_types(self):
        result = split_questions(PAGE, RULES)
        updated = apply_type_overrides(result, {"1:3": "multiple_choice", "1:1": "essay"})
        third = next(item for item in updated["questions"] if item["key"] == "1:3")
        first = next(item for item in updated["questions"] if item["key"] == "1:1")
        self.assertEqual(third["type"], "multiple_choice")
        self.assertEqual(third["status"], "confirmed")
        self.assertEqual(first["type"], "single_choice")
        self.assertEqual(first["status"], "needs_confirm")

    def test_draft_file_keeps_geometry_empty(self):
        draft = to_draft_file(split_questions(PAGE, RULES), 1)
        self.assertEqual(draft["contract"], "k12-question-draft")
        self.assertEqual(draft["contract_version"], 1)
        self.assertEqual(draft["schema_version"], 1)
        self.assertIs(draft["schema_version"], 1)
        self.assertEqual(draft["source"], {"pdf_page": 1})
        self.assertTrue(draft["questions"])
        for question in draft["questions"]:
            self.assertEqual(question["assets"], [])
            self.assertIsNone(question["geometry"])
            self.assertIn(question["structure"], {"choice", "blank", "worked", "unresolved"})


if __name__ == "__main__":
    unittest.main()
