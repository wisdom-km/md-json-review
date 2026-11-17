"""The contract copy check names a sha256 mismatch and does not call GitHub."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "check_contracts_in_sync",
    ROOT / "scripts" / "check_contracts_in_sync.py",
)
assert SPEC is not None and SPEC.loader is not None
sync = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sync)


class ContractSyncTest(unittest.TestCase):
    def test_k12_question_draft_sha256_mismatch_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            (folder / "k12-question-draft.v1.schema.json").write_bytes(b"{}\n")
            (folder / "k12-answer-draft.v1.schema.json").write_bytes(b"{}\n")
            same = sync.differences(
                folder,
                {
                    "k12-question-draft.v1.schema.json": b"{}\n",
                    "k12-answer-draft.v1.schema.json": b"{}\n",
                },
            )
            self.assertEqual(same, [])
            problems = sync.differences(
                folder,
                {
                    "k12-question-draft.v1.schema.json": b'{"version": 2}\n',
                    "k12-answer-draft.v1.schema.json": b"{}\n",
                },
            )
        self.assertEqual(len(problems), 1)
        self.assertIn("k12-question-draft.v1.schema.json", problems[0])
        self.assertIn("sha256", problems[0])

    def test_crlf_matches_lf_for_k12_answer_draft(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            folder = Path(raw)
            (folder / "k12-question-draft.v1.schema.json").write_bytes(b"{}\n")
            (folder / "k12-answer-draft.v1.schema.json").write_bytes(b'{"version": 1}\r\n')
            problems = sync.differences(
                folder,
                {
                    "k12-question-draft.v1.schema.json": b"{}\n",
                    "k12-answer-draft.v1.schema.json": b'{"version": 1}\n',
                },
            )
        self.assertEqual(problems, [])

    def test_missing_local_copy_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            problems = sync.differences(
                Path(raw),
                {
                    "k12-question-draft.v1.schema.json": b"{}\n",
                    "k12-answer-draft.v1.schema.json": b"{}\n",
                },
            )
        self.assertEqual(len(problems), 2)
        self.assertIn("本地没有", problems[0])


if __name__ == "__main__":
    unittest.main()
