"""Write reviewed copies and exports. Original .md and .json files stay untouched."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from app.store_pipeline import checked_drafts
from app.store_read import (
    _answer_dir,
    _clean_role,
    _inside,
    _load_json,
    _meta_path,
    _page_md,
    _reviewed_md,
    _role_path,
    page_number,
)
from core.answer_contract import answer_filename
from core.convert import ConvertError, apply_markdown, dump_json, normalize_newlines


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
    default_lesson: str = "",
) -> dict:
    """Write reviewed copies beside the book. Does not touch originals.

    Automatic saves pass backup=False. They write only the .reviewed files and
    do not replace .questions.json, .answers, or the sibling .answers-meta.json.
    A manual save keeps the previous reviewed copy and then overwrites the draft files.
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
    if backup:
        answer_files, draft, meta = checked_drafts(
            text,
            page_number(rel),
            role,
            answer_confirms,
            type_overrides,
            default_lesson=default_lesson,
        )
    else:
        answer_files, draft, meta = [], None, None
    _inside(book, reviewed_md)
    _inside(book, reviewed_json)
    targets = [reviewed_md, reviewed_json]
    meta_path = _meta_path(md_path)
    if backup:
        _inside(book, role_path)
        targets.append(role_path)
        if role == "answers":
            _inside(book, answer_dir)
            _inside(book, meta_path)
            targets.extend(path for path in answer_dir.glob("*.json"))
            targets.append(meta_path)
        else:
            _inside(book, questions_path)
            targets.append(questions_path)
    backed_up = _backup_existing(book, targets) if backup else False
    _atomic_text(reviewed_md, text)
    _atomic_text(reviewed_json, dump_json(updated))
    if backup:
        _atomic_text(role_path, role + "\n")
        if role == "answers":
            _write_answer_files(book, answer_dir, answer_files)
            _atomic_text(meta_path, _meta_text(meta))
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
    default_lesson: str = "",
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
    answer_files, draft, meta = checked_drafts(
        text,
        page_number(rel),
        role,
        answer_confirms,
        type_overrides,
        default_lesson=default_lesson,
    )
    if role == "answers":
        role_file = dest / f"{md_path.stem}.page-role.txt"
        answer_dest = dest / f"{md_path.stem}.answers"
        meta_dest = dest / f"{md_path.stem}.answers-meta.json"
        targets.append(role_file)
        targets.append(meta_dest)
        if answer_dest.is_dir():
            targets.extend(answer_dest.glob("*.json"))
    else:
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
        _atomic_text(dest / f"{md_path.stem}.answers-meta.json", _meta_text(meta))
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
        "export_dir": str(dest),
    }


def _meta_text(meta: dict | None) -> str:
    payload = meta or {
        "schema_version": 1,
        "pdf_page": None,
        "default_lesson": "",
        "answers": [],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


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
