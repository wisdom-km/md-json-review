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

from app.contracts import require_answer_draft, require_question_draft
from core.answer_contract import answer_filename, to_answer_files
from core.answer_split import split_answers
from core.convert import ConvertError, apply_markdown, dump_json, iter_blocks, normalize_newlines
from core.draft_contract import to_draft_file
from core.split import apply_type_overrides, split_questions

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
    text = normalize_newlines(markdown)
    role = _read_role(md_path)
    return {
        "rel": rel,
        "page_no": page_number(rel),
        "label": _page_label(rel),
        "markdown": text,
        "loaded_from": "reviewed" if source == reviewed_md else "original",
        "block_count": block_count,
        "preview": preview,
        "preview_error": preview_error,
        "page_role": role,
        "questions": split_questions(text) if role == "questions" else None,
        "answers": _saved_answers(md_path) if role == "answers" else [],
        "has_reviewed": reviewed_md.is_file(),
    }


def preview_page(
    book: Path,
    rel: str,
    markdown: str,
    *,
    page_role: str = "questions",
    answer_confirms: object = None,
) -> dict:
    md_path = _page_md(book, rel)
    document = _load_json(md_path.with_suffix(".json"))
    preview, preview_error = _preview_document(document, markdown)
    if preview_error:
        raise ConvertError(preview_error["error_code"], preview_error["message"])
    text = normalize_newlines(markdown)
    role = _clean_role(page_role)
    payload = {
        "preview": preview,
        "block_count": len(iter_blocks(document)),
        "page_role": role,
        "questions": None,
        "answers": [],
    }
    if role == "answers":
        answer_files = to_answer_files(split_answers(text), page_number(rel), answer_confirms)
        for item in answer_files:
            require_answer_draft(item)
        payload["answers"] = answer_files
    else:
        payload["questions"] = split_questions(text)
        require_question_draft(to_draft_file(payload["questions"], page_number(rel)))
    return payload


def save_page(
    book: Path,
    rel: str,
    markdown: str,
    *,
    sink: object | None = None,
    request_id: str = "",
    backup: bool = True,
    type_overrides: object = None,
    page_role: str = "questions",
    answer_confirms: object = None,
) -> dict:
    """Write reviewed copies beside the book. Does not touch originals.

    Automatic saves pass backup=False so a pause in typing does not create a
    new backup folder. A manual save keeps the previous reviewed copy.
    """
    md_path = _page_md(book, rel)
    json_path = md_path.with_suffix(".json")
    original_md = md_path.read_bytes()
    original_json = json_path.read_bytes()
    document = _load_json(json_path)
    updated = apply_markdown(document, markdown, sink=sink, request_id=request_id)
    text = normalize_newlines(markdown)
    reviewed_md = _reviewed_md(md_path)
    reviewed_json = json_path.with_name(json_path.stem + ".reviewed.json")
    role = _clean_role(page_role)
    role_path = _role_path(md_path)
    questions_path = md_path.with_name(md_path.stem + ".questions.json")
    answer_dir = _answer_dir(md_path)
    answer_files: list[dict] = []
    draft: dict | None = None
    if role == "answers":
        answer_files = to_answer_files(split_answers(text), page_number(rel), answer_confirms)
        for item in answer_files:
            require_answer_draft(item)
    else:
        draft = to_draft_file(apply_type_overrides(split_questions(text), type_overrides), page_number(rel))
        require_question_draft(draft)
    _inside(book, reviewed_md)
    _inside(book, reviewed_json)
    _inside(book, role_path)
    targets = [reviewed_md, reviewed_json, role_path]
    if role == "answers":
        _inside(book, answer_dir)
        targets.extend(path for path in answer_dir.glob("*.json"))
    else:
        _inside(book, questions_path)
        targets.append(questions_path)
    backed_up = _backup_existing(book, targets) if backup else False
    _atomic_text(reviewed_md, text)
    _atomic_text(reviewed_json, dump_json(updated))
    _atomic_text(role_path, role + "\n")
    if role == "answers":
        _write_answer_files(book, answer_dir, answer_files)
    else:
        assert draft is not None
        _atomic_text(questions_path, json.dumps(draft, ensure_ascii=False, indent=2) + "\n")
    if md_path.read_bytes() != original_md or json_path.read_bytes() != original_json:
        raise ConvertError("WRITE_FAILED", "原始文件被改动了，请停止使用并检查这一页。")
    return {
        "reviewed_md": reviewed_md.relative_to(book).as_posix(),
        "reviewed_json": reviewed_json.relative_to(book).as_posix(),
        "page_role": role,
        "answer_count": len(answer_files),
        "backed_up": backed_up,
    }


def export_page(
    book: Path,
    rel: str,
    markdown: str,
    export_dir: str,
    *,
    sink: object | None = None,
    request_id: str = "",
    page_role: str = "questions",
    answer_confirms: object = None,
    type_overrides: object = None,
) -> dict:
    """Copy the current page and its draft files. Originals stay put."""
    md_path = _page_md(book, rel)
    json_path = md_path.with_suffix(".json")
    original_md_bytes = md_path.read_bytes()
    original_json_bytes = json_path.read_bytes()
    document = _load_json(json_path)
    updated = apply_markdown(document, markdown, sink=sink, request_id=request_id)
    text = normalize_newlines(markdown)
    dest = _export_dir(export_dir)
    out_md = dest / f"{md_path.stem}.md"
    out_json = dest / f"{json_path.stem}.json"
    role = _clean_role(page_role)
    targets = [out_md, out_json]
    answer_files: list[dict] = []
    draft: dict | None = None
    if role == "answers":
        answer_files = to_answer_files(split_answers(text), page_number(rel), answer_confirms)
        for item in answer_files:
            require_answer_draft(item)
        role_file = dest / f"{md_path.stem}.page-role.txt"
        answer_dest = dest / f"{md_path.stem}.answers"
        targets.append(role_file)
        if answer_dest.is_dir():
            targets.extend(answer_dest.glob("*.json"))
    else:
        draft = to_draft_file(apply_type_overrides(split_questions(text), type_overrides), page_number(rel))
        require_question_draft(draft)
        questions_path = dest / f"{md_path.stem}.questions.json"
        targets.append(questions_path)
    for target in targets:
        _refuse_original(md_path, target)
        _refuse_original(json_path, target)
    backed_up = _backup_named(dest / "_export_backups", targets)
    _atomic_text(out_md, text)
    _atomic_text(out_json, dump_json(updated))
    if role == "answers":
        _atomic_text(dest / f"{md_path.stem}.page-role.txt", "answers\n")
        _write_answer_files(dest, dest / f"{md_path.stem}.answers", answer_files)
    else:
        assert draft is not None
        _atomic_text(
            dest / f"{md_path.stem}.questions.json",
            json.dumps(draft, ensure_ascii=False, indent=2) + "\n",
        )
    if md_path.read_bytes() != original_md_bytes or json_path.read_bytes() != original_json_bytes:
        raise ConvertError("WRITE_FAILED", "原始文件被改动了，请停止使用并检查这一页。")
    return {
        "folder_name": dest.name,
        "markdown_name": out_md.name,
        "json_name": out_json.name,
        "page_role": role,
        "answer_count": len(answer_files),
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
        raise ConvertError("BAD_PATH", "还没有选择书目录。")
    path = Path(raw)
    if not path.is_dir():
        raise ConvertError("MISSING_BOOK", "这个书目录不存在。请重新选择。")
    return path.resolve()


def _export_dir(raw: str) -> Path:
    if not raw or not str(raw).strip():
        raise ConvertError("BAD_PATH", "还没有选择导出文件夹。")
    path = Path(raw)
    if not path.is_dir():
        raise ConvertError("MISSING_EXPORT", "这个导出文件夹不存在。请重新选择。")
    return path.resolve()


def _refuse_original(original: Path, target: Path) -> None:
    if target.resolve() == original.resolve():
        raise ConvertError("EXPORT_ORIGINAL", "这个位置会覆盖原始文件，没有导出。请另选一个文件夹。")


def _backup_named(dest_root: Path, paths: list[Path]) -> bool:
    existing = [path for path in paths if path.is_file()]
    if not existing:
        return False
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    folder = dest_root / stamp
    suffix = 0
    while folder.exists():
        suffix += 1
        folder = dest_root / f"{stamp}-{suffix}"
    for source in existing:
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, folder / source.name)
    return True


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


def _clean_role(raw: object) -> str:
    return "answers" if raw == "answers" else "questions"


def _read_role(md_path: Path) -> str:
    path = _role_path(md_path)
    if not path.is_file():
        return "questions"
    return _clean_role(path.read_text(encoding="utf-8").strip())


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


def _write_answer_files(book: Path, directory: Path, files: list[dict]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    keep: set[str] = set()
    for item in files:
        path = _inside(book, directory / answer_filename(item["key"]))
        _atomic_text(path, json.dumps(item, ensure_ascii=False, indent=2) + "\n")
        keep.add(path.name)
    for old in directory.glob("*.json"):
        if old.name not in keep:
            old.unlink()


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
