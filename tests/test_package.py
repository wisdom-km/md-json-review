"""The installable copy of the split rules matches config/split_rules.json."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from md_json_review import rules_text


class PackageDataTest(unittest.TestCase):
    def test_packaged_split_rules_match_the_config_file(self) -> None:
        config = (ROOT / "config" / "split_rules.json").read_bytes().replace(b"\r\n", b"\n")
        packaged = (ROOT / "src" / "md_json_review" / "split_rules.json").read_bytes().replace(b"\r\n", b"\n")
        self.assertEqual(config, packaged)
        self.assertEqual(rules_text().encode("utf-8").replace(b"\r\n", b"\n"), config)


if __name__ == "__main__":
    unittest.main()
