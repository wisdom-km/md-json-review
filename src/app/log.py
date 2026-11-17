"""JSON-lines logger. One event is one line. The home directory is redacted."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}


def one_line(value: object, limit: int = 500) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    home = str(Path.home())
    if home:
        text = text.replace(home, "~")
    return text[:limit]


class JsonLogger:
    def __init__(self, path: Path, level: str = "INFO") -> None:
        self.path = path
        self.level = LEVELS.get(level.upper(), LEVELS["INFO"])
        path.parent.mkdir(parents=True, exist_ok=True)

    def event(
        self,
        level: str,
        event: str,
        request_id: str,
        module: str,
        **fields: object,
    ) -> None:
        number = LEVELS.get(level.upper())
        if number is None or number < self.level:
            return
        record: dict[str, object] = {
            "time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": level.upper(),
            "event": one_line(event, 80),
            "request_id": one_line(request_id, 64),
            "module": one_line(module, 80),
        }
        for key, value in fields.items():
            if value is None:
                continue
            record[key] = value if isinstance(value, (int, float)) else one_line(value)
        line = json.dumps(record, ensure_ascii=False)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")
        print(line, flush=True)
