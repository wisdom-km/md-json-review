"""Boundary pages: noisy headings, a thin choice, and an unknown heading."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.split import split_questions
from rules_loader import shipped_rules

RULES = shipped_rules()


class SplitEdgeTests(unittest.TestCase):
    def test_ocr_spaces_inside_a_type_heading_still_match(self):
        result = split_questions("一. 单 选 题\n1. 负数有（ ）\nA. 1 B. 2 C. 3 D. 4\n", RULES)
        self.assertTrue(result["ok"])
        question = result["questions"][0]
        self.assertEqual(question["type"], "single_choice")
        self.assertEqual(question["status"], "candidate")
        self.assertEqual([item["key"] for item in question["options"]], ["A", "B", "C", "D"])

    def test_choice_with_one_option_needs_confirm_and_keeps_the_page(self):
        result = split_questions("一. 选择题\n1. 只有 A\nA. 1\n2. 下一题\nA. 1 B. 2\n", RULES)
        self.assertTrue(result["ok"])
        self.assertEqual(result["reason"], "")
        self.assertEqual(result["questions"][0]["options"], [])
        self.assertEqual(result["questions"][0]["status"], "needs_confirm")
        self.assertEqual(result["questions"][1]["key"], "1:2")

    def test_unknown_heading_is_kept_and_not_confirmed(self):
        result = split_questions("一. 判断题\n1. 下列说法正确的是\nA. 对 B. 错\n", RULES)
        self.assertTrue(result["ok"])
        question = result["questions"][0]
        self.assertEqual(question["key"], "1:1")
        self.assertEqual(question["section"], "一. 判断题")
        self.assertEqual(question["status"], "needs_confirm")
        self.assertNotEqual(question["status"], "confirmed")


if __name__ == "__main__":
    unittest.main()
