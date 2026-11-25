import tempfile
import unittest
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.dialogs import starting_folder


class StartingFolderTests(unittest.TestCase):
    def test_a_file_opens_its_parent_and_a_missing_path_does_not(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            pdf = folder / "lesson.pdf"
            pdf.write_bytes(b"%PDF-1.1\n")
            self.assertEqual(starting_folder(str(pdf)), str(folder.resolve()))
            self.assertEqual(starting_folder(str(folder)), str(folder.resolve()))
            self.assertEqual(starting_folder(str(folder / "missing.pdf")), "")
            self.assertEqual(starting_folder(""), "")
            self.assertEqual(starting_folder("   "), "")
