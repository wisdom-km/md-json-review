"""split-rules v1 is checked before the port opens."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.split_rules import load_split_rules, validate_split_rules
from core.convert import ConvertError
from core.schema_check import schema_problems, unknown_schema_keywords


def _payload() -> dict:
    return json.loads((ROOT / "config" / "split_rules.json").read_text(encoding="utf-8"))


def _schema() -> dict:
    return json.loads((ROOT / "contracts" / "split-rules.v1.schema.json").read_text(encoding="utf-8"))


class SplitRulesSchemaTest(unittest.TestCase):
    def test_split_rules_v1_shipped_file_matches(self) -> None:
        schema = _schema()
        self.assertEqual(unknown_schema_keywords(schema), [])
        self.assertEqual(schema_problems(schema, _payload()), [])
        self.assertEqual(load_split_rules().needs_confirm_threshold, 2)

    def test_split_rules_v1_missing_field_is_split_rules(self) -> None:
        payload = _payload()
        del payload["needs_confirm_threshold"]
        with self.assertRaises(ConvertError) as caught:
            validate_split_rules(payload)
        self.assertEqual(caught.exception.code, "SPLIT_RULES")
        self.assertIn("needs_confirm_threshold", caught.exception.message)

    def test_startup_refuses_split_rules_before_the_port(self) -> None:
        import app.server as server

        def refuse() -> None:
            raise ConvertError("SPLIT_RULES", "$.needs_confirm_threshold：缺少")

        def opened(*_args: object, **_kwargs: object) -> None:
            raise AssertionError("port opened")

        original_load = server.load_split_rules
        original_make = server.make_server
        server.load_split_rules = refuse
        server.make_server = opened
        try:
            with self.assertRaises(SystemExit) as caught:
                server.main()
            self.assertEqual(caught.exception.code, 1)
        finally:
            server.load_split_rules = original_load
            server.make_server = original_make


if __name__ == "__main__":
    unittest.main()
