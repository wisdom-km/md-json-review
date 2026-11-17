"""Pure rules for writing edited Markdown back into GLM-OCR blocks.

No file or network access lives here. Callers pass the parsed JSON and the
Markdown text, and get either a new document or a ConvertError.
"""

from __future__ import annotations

import copy
import json
from typing import Protocol


class ConvertError(Exception):
    """A refusal the user can fix. code is stable; message is for people."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class LogSink(Protocol):
    def event(
        self,
        level: str,
        event: str,
        request_id: str,
        module: str,
        **fields: object,
    ) -> None:
        """Structured log event. Implementations must not raise."""


REQUIRED_KEYS = ("index", "label", "content", "bbox_2d")


def normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def iter_blocks(document: object) -> list[dict]:
    """Content blocks in read order. One OCR group is a list of blocks."""
    if not isinstance(document, list) or not document:
        raise ConvertError("BAD_JSON", "JSON 顶层不是非空数组，没有写入。")
    blocks: list[dict] = []
    for group_index, group in enumerate(document, start=1):
        if not isinstance(group, list) or not group:
            raise ConvertError("BAD_JSON", f"第 {group_index} 组不是非空数组，没有写入。")
        for block in group:
            if not isinstance(block, dict):
                raise ConvertError("BAD_JSON", f"第 {group_index} 组里有不是对象的块，没有写入。")
            missing = [key for key in REQUIRED_KEYS if key not in block]
            if missing:
                names = "、".join(missing)
                raise ConvertError("BAD_JSON", f"有块缺少 {names}，没有写入。")
            if not isinstance(block["content"], str):
                raise ConvertError("BAD_JSON", "有块的 content 不是字符串，没有写入。")
            blocks.append(block)
    return blocks


def split_marked_parts(markdown: str) -> list[str]:
    """Split on a line whose trimmed text is exactly ---. Padding newlines drop."""
    parts: list[list[str]] = [[]]
    for line in markdown.split("\n"):
        if line.strip() == "---":
            parts.append([])
        else:
            parts[-1].append(line)
    return ["\n".join(part).strip("\n") for part in parts]


def assign_parts(markdown: str, block_count: int) -> list[str]:
    """One block keeps the whole text, including any --- lines.

    Several blocks must split into exactly that many parts. A mismatch is a stop,
    not a guess.
    """
    if block_count < 1:
        raise ConvertError("BAD_JSON", "没有可写回的块，没有写入。")
    if block_count == 1:
        return [markdown]
    parts = split_marked_parts(markdown)
    if len(parts) != block_count:
        raise ConvertError(
            "BLOCK_MISMATCH",
            f"Markdown 按单独一行的 --- 分成了 {len(parts)} 段，原 JSON 有 {block_count} 块。没有写入文件。",
        )
    return parts


def apply_markdown(
    document: object,
    markdown: str,
    *,
    sink: LogSink | None = None,
    request_id: str = "",
) -> list:
    """Return a deep copy with content replaced. The input document is unchanged."""
    try:
        if not isinstance(markdown, str):
            raise ConvertError("BAD_MARKDOWN", "Markdown 不是文本，没有写入。")
        text = normalize_newlines(markdown)
        copied = copy.deepcopy(document)
        blocks = iter_blocks(copied)
        parts = assign_parts(text, len(blocks))
    except ConvertError as exc:
        _log(sink, "ERROR", "content_refused", request_id, result="error", error=exc.code)
        raise
    for block, part in zip(blocks, parts):
        block["content"] = part
    _log(
        sink,
        "INFO",
        "content_applied",
        request_id,
        result="ok",
        block_count=len(blocks),
    )
    return copied


def dump_json(document: object) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def refuse_drill(sink: LogSink | None = None, request_id: str = "") -> None:
    """Deliberate failure used to prove a request id reaches this layer."""
    _log(sink, "ERROR", "drill_refused", request_id, result="error", error="DRILL")
    raise ConvertError("DRILL", "这是一次故意失败，用来核对日志。没有写入文件。")


def _log(
    sink: LogSink | None,
    level: str,
    event: str,
    request_id: str,
    **fields: object,
) -> None:
    if sink is None:
        return
    sink.event(level, event, request_id, "core.convert", **fields)
