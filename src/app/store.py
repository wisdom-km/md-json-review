"""Read a book folder and write reviewed copies beside the originals.

Original .md and .json files are only read. Reviewed files may be replaced,
and the previous reviewed bytes are copied under _review_backups first.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

from core.convert import ConvertError, apply_markdown, dump_json, iter_blocks, normalize_newlines

SKIP_DIRS = {".git", "node_modules", "_review_backups", "__pycache__"}
PAGE_NO = re.compile(r"page_(\d+)", re.IGNORECASE)
MAX_MARKDOWN_FILES = 2000


def open_book(book_dir: str, pdf_path: str) -> tuple[Path, Path]:
    book = _existing_dir(book_dir)
    if book == Path(book.anchor):
        raise ConvertError("BAD_PATH", "请选一本书的目录，不要选整个磁盘。")
    pdf = Path(pdf_path)
    if pdf.suffix.lower() != ".pdf" or not pdf.is_file():
        raise ConvertError("MISSING_PDF", "这个 PDF 文件不存在，没有打开。")
    return book, pdf.resolve()


def list_pages(book: Path) -> list[dict]:
    found = 0
    pages: list[dict] = []
    for md_path in book.rglob("*.md"):
        found += 1
        if found > MAX_MARKDOWN_FILES:
            raise ConvertError(
                "BAD_PATH",
                "这个目录里的 Markdown 超过 2000 个，请改选更小的书目录。",
            )
        relative = md_path.relative_to(book)
        if any(part in SKIP_DIRS or part.startswith(".") for part in relative.parts):
            continue
        if md_path.name.endswith(".reviewed.md"):
            continue
        json_path = md_path.with_suffix(".json")
        if not json_path.is_file():
            continue
        rel = relative.as_posix()
        reviewed_md = _reviewed_md(md_path)
        pages.append(
            {
                "rel": rel,
                "page_no": page_number(rel),
                "label": _page_label(rel),
                "has_reviewed": reviewed_md.is_file(),
            }
        )
    pages.sort(key=lambda item: (item["page_no"] is None, item["page_no"] or 0, item["rel"]))
    if not pages:
        raise ConvertError("NO_PAGES", "这个目录里没有成对的 .md 和 .json，没有打开。")
    return pages


def page_number(rel: str) -> int | None:
    matches = PAGE_NO.findall(rel)
    if not matches:
        return None
    return int(matches[-1])


def read_page(book: Path, rel: str) -> dict:
    md_path = _page_md(book, rel)
    json_path = md_path.with_suffix(".json")
    if not json_path.is_file():
        raise ConvertError("NOT_FOUND", "这一页没有同名 JSON，没有打开。")
    reviewed_md = _reviewed_md(md_path)
    source = reviewed_md if reviewed_md.is_file() else md_path
    markdown = source.read_text(encoding="utf-8-sig")
    document = _load_json(json_path)
    block_count = len(iter_blocks(document))
    preview, preview_error = _preview_document(document, markdown)
    return {
        "rel": rel,
        "page_no": page_number(rel),
        "label": _page_label(rel),
        "markdown": normalize_newlines(markdown),
        "loaded_from": "reviewed" if source == reviewed_md else "original",
        "block_count": block_count,
        "preview": preview,
        "preview_error": preview_error,
        "has_reviewed": reviewed_md.is_file(),
    }


def preview_page(book: Path, rel: str, markdown: str) -> dict:
    md_path = _page_md(book, rel)
    document = _load_json(md_path.with_suffix(".json"))
    preview, preview_error = _preview_document(document, markdown)
    if preview_error:
        raise ConvertError(preview_error["error_code"], preview_error["message"])
    return {"preview": preview, "block_count": len(iter_blocks(document))}


def save_page(
    book: Path,
    rel: str,
    markdown: str,
    *,
    sink: object | None = None,
    request_id: str = "",
) -> dict:
    """Write reviewed copies. Returns relative paths. Does not touch originals."""
    md_path = _page_md(book, rel)
    json_path = md_path.with_suffix(".json")
    original_md = md_path.read_bytes()
    original_json = json_path.read_bytes()
    document = _load_json(json_path)
    updated = apply_markdown(document, markdown, sink=sink, request_id=request_id)
    text = normalize_newlines(markdown)
    reviewed_md = _reviewed_md(md_path)
    reviewed_json = json_path.with_name(json_path.stem + ".reviewed.json")
    _inside(book, reviewed_md)
    _inside(book, reviewed_json)
    backed_up = _backup_existing(book, [reviewed_md, reviewed_json])
    _atomic_text(reviewed_md, text)
    _atomic_text(reviewed_json, dump_json(updated))
    if md_path.read_bytes() != original_md or json_path.read_bytes() != original_json:
        raise ConvertError("WRITE_FAILED", "原始文件被改动了，请停止使用并检查这一页。")
    return {
        "reviewed_md": reviewed_md.relative_to(book).as_posix(),
        "reviewed_json": reviewed_json.relative_to(book).as_posix(),
        "backed_up": backed_up,
    }


def _preview_document(document: object, markdown: str) -> tuple[str, dict | None]:
    try:
        updated = apply_markdown(document, markdown)
    except ConvertError as exc:
        return "", {"error_code": exc.code, "message": exc.message}
    return dump_json(updated), None


def _load_json(path: Path) -> object:
    if not path.is_file():
        raise ConvertError("NOT_FOUND", "这一页没有同名 JSON，没有打开。")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        raise ConvertError("BAD_JSON", "这一页的 JSON 无法解析，没有写入。") from None


def _existing_dir(raw: str) -> Path:
    if not raw or not str(raw).strip():
        raise ConvertError("BAD_PATH", "还没有填写书目录。")
    path = Path(raw)
    if not path.is_dir():
        raise ConvertError("MISSING_BOOK", "这本书的目录不存在，没有打开。")
    return path.resolve()


def _page_md(book: Path, rel: str) -> Path:
    if not rel or "\\" in rel:
        raise ConvertError("BAD_PATH", "页路径不合法，没有读取或写入。")
    parts = Path(rel).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise ConvertError("BAD_PATH", "页路径不合法，没有读取或写入。")
    md_path = _inside(book, book / rel)
    if not md_path.is_file() or md_path.suffix.lower() != ".md":
        raise ConvertError("NOT_FOUND", "这一页的 Markdown 不存在，没有打开。")
    if md_path.name.endswith(".reviewed.md"):
        raise ConvertError("BAD_PATH", "请打开原始 Markdown，不要把另存稿当作一页。")
    return md_path


def _inside(book: Path, candidate: Path) -> Path:
    root = book.resolve()
    resolved = candidate.resolve()
    if resolved != root and root not in resolved.parents:
        raise ConvertError("BAD_PATH", "路径超出了这本书的目录，没有读取或写入。")
    return resolved


def _reviewed_md(md_path: Path) -> Path:
    return md_path.with_name(md_path.stem + ".reviewed.md")


def _backup_existing(book: Path, paths: list[Path]) -> bool:
    existing = [path for path in paths if path.is_file()]
    if not existing:
        return False
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    dest_root = book / "_review_backups" / stamp
    suffix = 0
    while dest_root.exists():
        suffix += 1
        dest_root = book / "_review_backups" / f"{stamp}-{suffix}"
    for source in existing:
        target = dest_root / source.relative_to(book)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return True


def _atomic_text(path: Path, text: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(text, encoding="utf-8", newline="\n")
        temporary.replace(path)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise


def _page_label(rel: str) -> str:
    number = page_number(rel)
    if number is None:
        return Path(rel).stem
    return f"第 {number} 页"
