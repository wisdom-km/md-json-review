"""Local review server. It listens on 127.0.0.1 only."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.log import JsonLogger
from app.store import list_pages, open_book, preview_page, read_page, save_page
from core.convert import ConvertError, refuse_drill

ROOT = Path(__file__).resolve().parents[2]
STATIC = Path(__file__).resolve().parent / "static"
MAX_BODY = 2_500_000
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class Session:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.book: Path | None = None
        self.pdf: Path | None = None

    def require_book(self) -> Path:
        if self.book is None:
            raise ConvertError("NO_BOOK", "还没有打开书目录。")
        return self.book


def load_env(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip("\"'")


def require_loopback(host: str) -> str:
    if host not in LOOPBACK:
        raise SystemExit(f"拒绝监听 {host}。这个工具只允许 127.0.0.1，避免别人访问。")
    if host == "localhost":
        return "127.0.0.1"
    if host == "::1":
        return "::1"
    return host


def make_server(host: str, port: int, logger: JsonLogger, session: Session) -> ThreadingHTTPServer:
    bound = require_loopback(host)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            self._handle("GET")

        def do_POST(self) -> None:
            self._handle("POST")

        def _handle(self, method: str) -> None:
            started = time.perf_counter()
            request_id = uuid.uuid4().hex[:12]
            parsed = urlparse(self.path)
            route = parsed.path
            logger.event(
                "INFO",
                "request_in",
                request_id,
                "app.http",
                result="start",
                method=method,
                route=route,
            )
            try:
                status = self._dispatch(method, parsed, request_id)
            except ConvertError as exc:
                logger.event(
                    "ERROR",
                    "request_failed",
                    request_id,
                    "app.http",
                    result="error",
                    error=exc.code,
                )
                status = self._send_json(
                    400,
                    {
                        "ok": False,
                        "error_code": exc.code,
                        "message": exc.message,
                        "request_id": request_id,
                    },
                )
            except Exception as exc:
                logger.event(
                    "ERROR",
                    "request_failed",
                    request_id,
                    "app.http",
                    result="error",
                    error=type(exc).__name__,
                )
                status = self._send_json(
                    500,
                    {
                        "ok": False,
                        "error_code": "INTERNAL",
                        "message": "程序内部出错。请拿请求编号到日志里查看，没有写入文件。",
                        "request_id": request_id,
                    },
                )
            duration_ms = int((time.perf_counter() - started) * 1000)
            logger.event(
                "INFO",
                "request_out",
                request_id,
                "app.http",
                result="ok" if status < 400 else "error",
                status=status,
                duration_ms=duration_ms,
            )

        def _dispatch(self, method: str, parsed, request_id: str) -> int:
            route = parsed.path
            if method == "GET" and route == "/":
                return self._send_file(STATIC / "index.html", "text/html; charset=utf-8")
            if method == "GET" and route == "/app.css":
                return self._send_file(STATIC / "app.css", "text/css; charset=utf-8")
            if method == "GET" and route == "/app.js":
                return self._send_file(STATIC / "app.js", "text/javascript; charset=utf-8")
            if method == "GET" and route == "/favicon.ico":
                return self._send_bytes(204, b"", "image/x-icon")
            if method == "GET" and route == "/api/health":
                return self._send_json(200, {"ok": True})
            if method == "GET" and route == "/api/drill-error":
                refuse_drill(logger, request_id)
                return 500
            if method == "GET" and route == "/pdf":
                return self._send_pdf()
            if method == "GET" and route == "/api/page":
                rel = parse_qs(parsed.query).get("rel", [""])[0]
                with session.lock:
                    payload = read_page(session.require_book(), rel)
                payload["ok"] = True
                payload["request_id"] = request_id
                return self._send_json(200, payload)
            if method == "POST" and route == "/api/open":
                body = self._read_json()
                book, pdf = open_book(str(body.get("book_dir", "")), str(body.get("pdf_path", "")))
                pages = list_pages(book)
                with session.lock:
                    session.book = book
                    session.pdf = pdf
                return self._send_json(200, {"ok": True, "request_id": request_id, "pages": pages})
            if method == "POST" and route == "/api/preview":
                body = self._read_json()
                with session.lock:
                    payload = preview_page(
                        session.require_book(),
                        str(body.get("rel", "")),
                        body.get("markdown", ""),
                    )
                payload["ok"] = True
                payload["request_id"] = request_id
                return self._send_json(200, payload)
            if method == "POST" and route == "/api/save":
                body = self._read_json()
                with session.lock:
                    payload = save_page(
                        session.require_book(),
                        str(body.get("rel", "")),
                        body.get("markdown", ""),
                        sink=logger,
                        request_id=request_id,
                    )
                logger.event(
                    "INFO",
                    "reviewed_saved",
                    request_id,
                    "app.store",
                    result="ok",
                    backed_up=payload["backed_up"],
                )
                payload["ok"] = True
                payload["request_id"] = request_id
                payload["message"] = "已另存。原始 Markdown 和原始 JSON 没有改。"
                return self._send_json(200, payload)
            return self._send_json(
                404,
                {
                    "ok": False,
                    "error_code": "NOT_FOUND",
                    "message": "没有这个地址。",
                    "request_id": request_id,
                },
            )

        def _send_pdf(self) -> int:
            with session.lock:
                pdf = session.pdf
            if pdf is None or not pdf.is_file():
                raise ConvertError("MISSING_PDF", "还没有打开 PDF。")
            body = pdf.read_bytes()
            return self._send_bytes(200, body, "application/pdf")

        def _read_json(self) -> dict:
            content_type = self.headers.get("Content-Type", "")
            if "application/json" not in content_type:
                raise ConvertError("BAD_REQUEST", "请求格式不对，没有处理。")
            length = int(self.headers.get("Content-Length", "0") or "0")
            if length < 0 or length > MAX_BODY:
                raise ConvertError("TOO_LARGE", "内容超过 2MB，没有写入。")
            raw = self.rfile.read(length)
            try:
                body = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ConvertError("BAD_REQUEST", "请求不是 JSON，没有处理。") from None
            if not isinstance(body, dict):
                raise ConvertError("BAD_REQUEST", "请求不是 JSON 对象，没有处理。")
            return body

        def _send_file(self, path: Path, content_type: str) -> int:
            if not path.is_file():
                return self._send_bytes(404, "页面文件缺失。".encode("utf-8"), "text/plain; charset=utf-8")
            return self._send_bytes(200, path.read_bytes(), content_type)

        def _send_json(self, status: int, payload: dict) -> int:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            return self._send_bytes(status, body, "application/json; charset=utf-8")

        def _send_bytes(self, status: int, body: bytes, content_type: str) -> int:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if body:
                self.wfile.write(body)
            return status

    server = ThreadingHTTPServer((bound, port), Handler)
    server.daemon_threads = True
    return server


def main() -> None:
    load_env(ROOT / ".env")
    host = require_loopback(os.environ.get("HOST", "127.0.0.1"))
    port = int(os.environ.get("PORT", "8765"))
    level = os.environ.get("MD_JSON_LOG_LEVEL", "INFO")
    logger = JsonLogger(ROOT / "logs" / "app.jsonl", level)
    session = Session()
    try:
        server = make_server(host, port, logger, session)
    except OSError:
        print(f"端口 {port} 打不开。关掉占用它的程序，或换一个 PORT。", flush=True)
        raise SystemExit(1) from None
    url = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"核对题页已启动：{url}", flush=True)
    print(f"日志文件：{logger.path}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("已停止。", flush=True)
    finally:
        server.server_close()
