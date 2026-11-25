import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.log import JsonLogger
from app.server import Session, make_server, require_loopback, resolve_port
from core.convert import ConvertError


def write_book(root: Path) -> None:
    page = root / "page_0001" / "input_1_page_0001"
    page.mkdir(parents=True)
    document = [[{"index": 0, "label": "text", "content": "旧", "bbox_2d": None}]]
    (page / "input_1_page_0001.md").write_text("旧\n", encoding="utf-8", newline="\n")
    (page / "input_1_page_0001.json").write_text(
        json.dumps(document, ensure_ascii=False),
        encoding="utf-8",
    )
    (root / "origin.pdf").write_bytes(b"%PDF-1.1\n")


class HttpTests(unittest.TestCase):
    def test_loopback_only(self):
        with self.assertRaises(SystemExit):
            require_loopback("0.0.0.0")

    def test_save_and_drill_share_request_ids_in_the_log(self):
        with tempfile.TemporaryDirectory() as temporary:
            book = Path(temporary)
            write_book(book)
            log_path = book / "app.jsonl"
            logger = JsonLogger(log_path, "INFO")
            server = make_server("127.0.0.1", 0, logger, Session())
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            port = server.server_address[1]
            base = f"http://127.0.0.1:{port}"
            try:
                opened = post(
                    base + "/api/open",
                    {"book_dir": str(book), "pdf_path": str(book / "origin.pdf")},
                )
                self.assertTrue(opened["ok"])
                self.assertEqual(opened["pages"][0]["page_no"], 1)
                rel = opened["pages"][0]["rel"]
                saved = post(
                    base + "/api/save",
                    {"rel": rel, "markdown": "改过的正文\n"},
                )
                self.assertTrue(saved["ok"], saved)
                self.assertIn("保存成功", saved["message"])
                original = (book / rel).read_text(encoding="utf-8")
                self.assertEqual(original, "旧\n")
                reviewed = book / saved["reviewed_json"]
                document = json.loads(reviewed.read_text(encoding="utf-8"))
                self.assertEqual(document[0][0]["content"], "改过的正文\n")
                drill = get(base + "/api/drill-error")
                self.assertFalse(drill["ok"])
                self.assertEqual(drill["error_code"], "DRILL")
                self.assertEqual(drill["code"], "DRILL")
                daily = logger.file_for()
                self.assertFalse(log_path.exists())
                lines = [
                    json.loads(line)
                    for line in daily.read_text(encoding="utf-8").splitlines()
                ]
                drill_lines = [line for line in lines if line["request_id"] == drill["request_id"]]
                modules = {line["module"] for line in drill_lines}
                self.assertIn("app.http", modules)
                self.assertIn("core.convert", modules)
                self.assertTrue(any(line["level"] == "ERROR" for line in drill_lines))
                save_lines = [line for line in lines if line["request_id"] == saved["request_id"]]
                save_modules = {line["module"] for line in save_lines}
                self.assertIn("core.convert", save_modules)
                self.assertIn("app.store", save_modules)
                self.assertNotIn("改过的正文", daily.read_text(encoding="utf-8"))
                other = book / "other.pdf"
                other.write_bytes(b"%PDF-other\n")
                reopened = post(
                    base + "/api/open",
                    {"book_dir": str(book), "pdf_path": str(other)},
                )
                self.assertTrue(reopened["ok"], reopened)
                with urllib.request.urlopen(base + "/pdf?v=other&page=1") as response:
                    self.assertEqual(response.read(), b"%PDF-other\n")
                    self.assertEqual(response.headers.get("Cache-Control"), "no-store")
                dest = Path(temporary) / "out"
                dest.mkdir()
                exported = post(
                    base + "/api/export",
                    {"rel": rel, "markdown": "改过的正文\n", "export_dir": str(dest)},
                )
                self.assertTrue(exported["ok"], exported)
                self.assertIn("导出成功", exported["message"])
                self.assertIn(str(dest.resolve()), exported["message"])
                self.assertNotIn(str(dest.resolve()), daily.read_text(encoding="utf-8"))
            finally:
                server.shutdown()
                server.server_close()


def post(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


def get(url: str) -> dict:
    try:
        with urllib.request.urlopen(url) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read().decode("utf-8"))
        finally:
            exc.close()


class PortTests(unittest.TestCase):
    def test_flag_overrides_env_and_default_is_8765(self):
        self.assertEqual(resolve_port(["--port", "8790"], {"PORT": "8765"}), 8790)
        self.assertEqual(resolve_port(["--port=8792"], {}), 8792)
        self.assertEqual(resolve_port([], {}), 8765)
        self.assertEqual(resolve_port([], {"PORT": "8791"}), 8791)

    def test_bad_port_names_the_source(self):
        with self.assertRaises(SystemExit) as caught:
            resolve_port(["--port", "0"], {})
        self.assertIn("65535", str(caught.exception))
        with self.assertRaises(SystemExit) as missing:
            resolve_port(["--port"], {})
        self.assertIn("--port", str(missing.exception))


if __name__ == "__main__":
    unittest.main()
