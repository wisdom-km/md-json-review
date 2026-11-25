"""JSON-lines logger. One event is one line, in the local calendar day's file.

The constructor path is only the stem, for example logs/app.jsonl. Each event
appends to logs/app-YYYY-MM-DD.jsonl. The record's time field stays UTC.
The home directory is redacted.
"""

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

    def file_for(self, moment: datetime | None = None) -> Path:
        when = datetime.now() if moment is None else moment
        day = when.astimezone().strftime("%Y-%m-%d")
        return self.path.with_name(f"{self.path.stem}-{day}{self.path.suffix}")

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
        now = datetime.now().astimezone()
        record: dict[str, object] = {
            "time": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
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
        path = self.file_for(now)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")
        print(line, flush=True)
