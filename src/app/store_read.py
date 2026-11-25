"""Read a book folder. Original files are not changed here."""

from __future__ import annotations

import json
import re
from pathlib import Path

from core.convert import ConvertError, iter_blocks, normalize_newlines

SKIP_DIRS = {".git", "node_modules", "_review_backups", "__pycache__"}
PAGE_NO = re.compile(r"page_(\d+)", re.IGNORECASE)
MAX_MARKDOWN_FILES = 2000


def open_book(book_dir: str, pdf_path: str) -> tuple[Path, Path]:
    book = _existing_dir(book_dir)
    if book == Path(book.anchor):
        raise ConvertError("BAD_PATH", "请选一本书的目录，不要选整个磁盘。")
    pdf = Path(pdf_path)
    if pdf.suffix.lower() != ".pdf" or not pdf.is_file():
        raise ConvertError("MISSING_PDF", "没有找到这个 PDF 文件。请重新选择以 .pdf 结尾的文件。")
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
    from app.store_pipeline import preview_document

    md_path = _page_md(book, rel)
    json_path = md_path.with_suffix(".json")
    if not json_path.is_file():
        raise ConvertError("NOT_FOUND", "这一页没有同名 JSON，没有打开。")
    reviewed_md = _reviewed_md(md_path)
    source = reviewed_md if reviewed_md.is_file() else md_path
    markdown = source.read_text(encoding="utf-8-sig")
    document = _load_json(json_path)
    block_count = len(iter_blocks(document))
    preview, preview_error = preview_document(document, markdown)
    text = normalize_newlines(markdown)
    role = _read_role(md_path)
    payload = {
        "rel": rel,
        "page_no": page_number(rel),
        "label": _page_label(rel),
        "markdown": text,
        "loaded_from": "reviewed" if source == reviewed_md else "original",
        "block_count": block_count,
        "preview": preview,
        "preview_error": preview_error,
        "page_role": role,
        "questions": _questions_or_none(text, role),
        "answers": _saved_answers(md_path) if role == "answers" else [],
        "has_reviewed": reviewed_md.is_file(),
        "default_lesson": "",
        "answer_meta": None,
    }
    if role == "answers":
        default_lesson, answer_meta = _load_answer_meta(md_path)
        payload["default_lesson"] = default_lesson
        payload["answer_meta"] = answer_meta
    return payload


def _questions_or_none(text: str, role: str):
    if role != "questions":
        return None
    from app.split_rules import load_split_rules
    from core.split import split_questions

    return split_questions(text, load_split_rules())


def _load_json(path: Path) -> object:
    if not path.is_file():
        raise ConvertError("NOT_FOUND", "这一页没有同名 JSON，没有打开。")
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        raise ConvertError("BAD_JSON", "这一页的 JSON 无法解析，没有写入。") from None


def _existing_dir(raw: str) -> Path:
    if not raw or not str(raw).strip():
        raise ConvertError("BAD_PATH", "还没有选择书目录。")
    path = Path(raw)
    if not path.is_dir():
        raise ConvertError("MISSING_BOOK", "这个书目录不存在。请重新选择。")
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


def _role_path(md_path: Path) -> Path:
    return md_path.with_name(md_path.stem + ".page-role.txt")


def _answer_dir(md_path: Path) -> Path:
    return md_path.with_name(md_path.stem + ".answers")


def _meta_path(md_path: Path) -> Path:
    """Lesson sidecar beside .answers/, never inside it.

    The question bank reads every JSON in .answers/ as a k12-answer-draft.
    """
    return md_path.with_name(md_path.stem + ".answers-meta.json")


def _clean_role(raw: object) -> str:
    return "answers" if raw == "answers" else "questions"


def _read_role(md_path: Path) -> str:
    path = _role_path(md_path)
    if not path.is_file():
        return "questions"
    return _clean_role(path.read_text(encoding="utf-8").strip())


def _load_answer_meta(md_path: Path) -> tuple[str, dict | None]:
    path = _meta_path(md_path)
    if not path.is_file():
        return "", None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return "", None
    if not isinstance(payload, dict):
        return "", None
    raw_default = payload.get("default_lesson", "")
    default_lesson = raw_default.strip() if isinstance(raw_default, str) else ""
    answers = payload.get("answers")
    clean = []
    if isinstance(answers, list):
        for item in answers:
            if not isinstance(item, dict):
                continue
            key = item.get("key")
            question_key = item.get("question_key")
            title = item.get("lesson_title", "")
            if not isinstance(key, str) or not isinstance(question_key, str):
                continue
            if not isinstance(title, str):
                title = ""
            clean.append({"key": key, "question_key": question_key, "lesson_title": title})
    pdf_page = payload.get("pdf_page")
    if isinstance(pdf_page, bool) or not isinstance(pdf_page, int):
        pdf_page = page_number(md_path.as_posix())
    return default_lesson, {
        "schema_version": 1,
        "pdf_page": pdf_page,
        "default_lesson": default_lesson,
        "answers": clean,
    }


def _saved_answers(md_path: Path) -> list[dict]:
    directory = _answer_dir(md_path)
    if not directory.is_dir():
        return []
    found = []
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            found.append(payload)
    return found


def _page_label(rel: str) -> str:
    number = page_number(rel)
    if number is None:
        return Path(rel).stem
    return f"第 {number} 页"
