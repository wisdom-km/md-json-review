import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.convert import ConvertError, apply_markdown, assign_parts, dump_json


ONE = [[{"index": 0, "label": "text", "content": "旧", "bbox_2d": None, "extra": 1}]]
THREE = [
    [{"index": 0, "label": "text", "content": "a", "bbox_2d": [1, 2, 3, 4]}],
    [{"index": 0, "label": "image", "content": "b", "bbox_2d": None}],
    [{"index": 1, "label": "text", "content": "c", "bbox_2d": None}],
]


class ConvertTests(unittest.TestCase):
    def test_one_block_keeps_separator_and_fields(self):
        markdown = "甲\n\n---\n\n乙\n"
        updated = apply_markdown(ONE, markdown)
        self.assertEqual(ONE[0][0]["content"], "旧")
        block = updated[0][0]
        self.assertEqual(block["content"], markdown)
        self.assertEqual(block["index"], 0)
        self.assertEqual(block["label"], "text")
        self.assertIsNone(block["bbox_2d"])
        self.assertEqual(block["extra"], 1)
        self.assertIn("甲", dump_json(updated))

    def test_three_blocks_split_on_rule_line(self):
        markdown = "甲\n\n---\n\n乙\n\n---\n\n丙\n"
        updated = apply_markdown(THREE, markdown)
        contents = [group[0]["content"] for group in updated]
        self.assertEqual(contents, ["甲", "乙", "丙"])
        self.assertEqual(updated[1][0]["label"], "image")
        self.assertEqual(updated[0][0]["bbox_2d"], [1, 2, 3, 4])

    def test_mismatch_refuses(self):
        with self.assertRaises(ConvertError) as caught:
            apply_markdown(THREE, "只有一段")
        self.assertEqual(caught.exception.code, "BLOCK_MISMATCH")

    def test_assign_parts_for_one_block_does_not_split(self):
        self.assertEqual(assign_parts("甲\n---\n乙", 1), ["甲\n---\n乙"])

    def test_formula_split_by_separator_stays_whole_on_one_block(self):
        formula = "计算 $$\n---\n\\frac{1}{2}\n$$"
        self.assertEqual(assign_parts(formula, 1), [formula])
        updated = apply_markdown(ONE, formula)
        self.assertEqual(updated[0][0]["content"], formula)
        self.assertEqual(ONE[0][0]["content"], "旧")

    def test_formula_split_by_separator_stops_when_block_count_differs(self):
        formula = "计算 $$\n---\n\\frac{1}{2}\n$$"
        before = [group[0]["content"] for group in THREE]
        with self.assertRaises(ConvertError) as caught:
            apply_markdown(THREE, formula)
        self.assertEqual(caught.exception.code, "BLOCK_MISMATCH")
        self.assertIn("没有写入", caught.exception.message)
        self.assertEqual([group[0]["content"] for group in THREE], before)

    def test_bad_json_missing_key(self):
        with self.assertRaises(ConvertError) as caught:
            apply_markdown([[{"index": 0, "label": "text"}]], "甲")
        self.assertEqual(caught.exception.code, "BAD_JSON")


if __name__ == "__main__":
    unittest.main()
