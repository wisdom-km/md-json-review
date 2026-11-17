import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.store import export_page, list_pages, read_page, save_page
from core.convert import ConvertError


def write_book(root: Path) -> None:
    page = root / "page_0001" / "input_1_page_0001"
    page.mkdir(parents=True)
    document = [[{"index": 0, "label": "text", "content": "旧", "bbox_2d": None}]]
    (page / "input_1_page_0001.md").write_text("旧\n", encoding="utf-8", newline="\n")
    (page / "input_1_page_0001.json").write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


class StoreTests(unittest.TestCase):
    def test_save_leaves_originals_and_second_save_backs_up(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            book = Path(temporary)
            write_book(book)
            rel = "page_0001/input_1_page_0001/input_1_page_0001.md"
            original_md = (book / rel).read_bytes()
            original_json = (book / rel).with_suffix(".json").read_bytes()
            first = save_page(book, rel, "新的正文\n")
            self.assertFalse(first["backed_up"])
            self.assertEqual((book / rel).read_bytes(), original_md)
            self.assertEqual((book / rel).with_suffix(".json").read_bytes(), original_json)
            reviewed = (book / first["reviewed_md"]).read_text(encoding="utf-8")
            self.assertEqual(reviewed, "新的正文\n")
            questions = json.loads(
                (book / "page_0001" / "input_1_page_0001" / "input_1_page_0001.questions.json").read_text(encoding="utf-8")
            )
            self.assertEqual(questions["contract"], "k12-question-draft")
            self.assertEqual(questions["contract_version"], 1)
            self.assertEqual(questions["schema_version"], 1)
            self.assertEqual(questions["source"], {"pdf_page": 1})
            self.assertTrue(questions["ok"])
            self.assertEqual(questions["questions"], [])
            saved_json = json.loads((book / first["reviewed_json"]).read_text(encoding="utf-8"))
            self.assertEqual(saved_json[0][0]["content"], "新的正文\n")
            second = save_page(book, rel, "第二次\n")
            self.assertTrue(second["backed_up"])
            backups = list((book / "_review_backups").rglob("*.reviewed.md"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding="utf-8"), "新的正文\n")
            self.assertEqual((book / rel).read_bytes(), original_md)
            restored = backups[0].read_text(encoding="utf-8")
            self.assertEqual(restored, "新的正文\n")

    def test_mismatch_writes_nothing(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            book = Path(temporary)
            page = book / "page_0002" / "item"
            page.mkdir(parents=True)
            document = [
                [{"index": 0, "label": "text", "content": "a", "bbox_2d": None}],
                [{"index": 0, "label": "text", "content": "b", "bbox_2d": None}],
            ]
            md = page / "item.md"
            js = page / "item.json"
            md.write_text("a\n\n---\n\nb\n", encoding="utf-8", newline="\n")
            js.write_text(json.dumps(document), encoding="utf-8")
            before = sorted(p.name for p in page.iterdir())
            with self.assertRaises(ConvertError) as caught:
                save_page(book, "page_0002/item/item.md", "没有分隔")
            self.assertEqual(caught.exception.code, "BLOCK_MISMATCH")
            self.assertEqual(sorted(p.name for p in page.iterdir()), before)

    def test_escape_is_refused(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            book = Path(temporary)
            write_book(book)
            with self.assertRaises(ConvertError) as caught:
                read_page(book, "../outside.md")
            self.assertEqual(caught.exception.code, "BAD_PATH")

    def test_list_skips_reviewed_copies(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            book = Path(temporary)
            write_book(book)
            rel = "page_0001/input_1_page_0001/input_1_page_0001.md"
            save_page(book, rel, "新的正文\n")
            pages = list_pages(book)
            self.assertEqual(len(pages), 1)
            self.assertTrue(pages[0]["has_reviewed"])
            self.assertEqual(pages[0]["page_no"], 1)

    def test_automatic_save_does_not_backup_each_pause(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            book = Path(temporary)
            write_book(book)
            rel = "page_0001/input_1_page_0001/input_1_page_0001.md"
            save_page(book, rel, "第一次\n", backup=False)
            save_page(book, rel, "第二次\n", backup=False)
            self.assertFalse((book / "_review_backups").exists())
            reviewed = book / "page_0001" / "input_1_page_0001" / "input_1_page_0001.reviewed.md"
            self.assertEqual(reviewed.read_text(encoding="utf-8"), "第二次\n")
            self.assertFalse((reviewed.with_name("input_1_page_0001.questions.json")).exists())

    def test_export_writes_a_copy_and_refuses_the_original_path(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            book = Path(temporary) / "book"
            book.mkdir()
            write_book(book)
            rel = "page_0001/input_1_page_0001/input_1_page_0001.md"
            original = (book / rel).read_bytes()
            dest = Path(temporary) / "out"
            dest.mkdir()
            exported = export_page(book, rel, "导出的正文\n", str(dest))
            self.assertEqual(exported["markdown_name"], "input_1_page_0001.md")
            self.assertEqual((dest / "input_1_page_0001.md").read_text(encoding="utf-8"), "导出的正文\n")
            saved = json.loads((dest / "input_1_page_0001.json").read_text(encoding="utf-8"))
            self.assertEqual(saved[0][0]["content"], "导出的正文\n")
            exported_draft = json.loads((dest / "input_1_page_0001.questions.json").read_text(encoding="utf-8"))
            self.assertEqual(exported_draft["contract"], "k12-question-draft")
            self.assertEqual((book / rel).read_bytes(), original)
            page_dir = str((book / rel).parent)
            with self.assertRaises(ConvertError) as caught:
                export_page(book, rel, "再导出\n", page_dir)
            self.assertEqual(caught.exception.code, "EXPORT_ORIGINAL")

    def test_k12_question_draft_autosave_does_not_overwrite_the_draft(self):
        import tempfile

        with tempfile.TemporaryDirectory() as temporary:
            book = Path(temporary)
            write_book(book)
            rel = "page_0001/input_1_page_0001/input_1_page_0001.md"
            folder = book / "page_0001" / "input_1_page_0001"
            save_page(book, rel, "一. 选择题\n1. 题干\nA. 甲\nB. 乙\n", backup=True)
            questions = folder / "input_1_page_0001.questions.json"
            before = questions.read_bytes()
            save_page(book, rel, "一. 选择题\n1. 改过的题干\nA. 甲\nB. 乙\n", backup=False)
            self.assertEqual(questions.read_bytes(), before)
            reviewed = (folder / "input_1_page_0001.reviewed.md").read_text(encoding="utf-8")
            self.assertIn("改过的题干", reviewed)
            save_page(book, rel, "一. 选择题\n1. A\n", backup=True, page_role="answers")
            answer = folder / "input_1_page_0001.answers" / "1-1-ocr-1.json"
            answer_before = answer.read_bytes()
            save_page(book, rel, "一. 选择题\n1. B\n", backup=False, page_role="answers")
            self.assertEqual(answer.read_bytes(), answer_before)


if __name__ == "__main__":
    unittest.main()
