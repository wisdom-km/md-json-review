import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.log import JsonLogger


class DailyLogTests(unittest.TestCase):
    def test_local_midnight_opens_the_next_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary) / "logs" / "app.jsonl"
            logger = JsonLogger(base, "INFO")
            local = datetime.now().astimezone().tzinfo
            before = datetime(2026, 11, 17, 23, 50, tzinfo=local)
            after = datetime(2026, 11, 18, 0, 10, tzinfo=local)
            self.assertEqual(logger.file_for(before).name, "app-2026-11-17.jsonl")
            self.assertEqual(logger.file_for(after).name, "app-2026-11-18.jsonl")
            utc_moment = datetime(2026, 11, 17, 16, 30, tzinfo=timezone.utc)
            expected = utc_moment.astimezone().strftime("%Y-%m-%d")
            self.assertEqual(logger.file_for(utc_moment).name, f"app-{expected}.jsonl")

    def test_event_appends_to_today_and_leaves_the_stem_alone(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary) / "app.jsonl"
            logger = JsonLogger(base, "INFO")
            logger.event("INFO", "started", "req-1", "app.http", detail=str(Path.home()))
            today = datetime.now().astimezone().strftime("%Y-%m-%d")
            written = base.with_name(f"app-{today}.jsonl")
            self.assertTrue(written.is_file())
            self.assertFalse(base.exists())
            record = json.loads(written.read_text(encoding="utf-8"))
            self.assertTrue(record["time"].endswith("Z"))
            self.assertNotIn(str(Path.home()), written.read_text(encoding="utf-8"))
            self.assertIn("~", record["detail"])
