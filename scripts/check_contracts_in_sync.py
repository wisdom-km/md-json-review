"""Fail when contracts/ differs from k12-qbank main.

The two schema files are copies. This compares sha256 after turning CRLF into
LF, so a Windows checkout does not look different from the GitHub file.
"""

from __future__ import annotations

import hashlib
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "k12-question-draft.v1.schema.json",
    "k12-answer-draft.v1.schema.json",
)
REMOTE = (
    "https://raw.githubusercontent.com/wisdom-km/k12-qbank/main/"
    "backend/catalog/contracts/{name}"
)


class ContractSyncError(Exception):
    """The remote schema could not be read. The message has no local path."""


def canonical(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def digest(data: bytes) -> str:
    return hashlib.sha256(canonical(data)).hexdigest()


def differences(local_dir: Path, remote_bytes: dict[str, bytes]) -> list[str]:
    """Return one line per file whose sha256 does not match k12-qbank main."""
    problems: list[str] = []
    for name in FILES:
        remote = remote_bytes.get(name)
        if remote is None:
            problems.append(f"{name} 没有从 k12-qbank main 读到。")
            continue
        local_path = local_dir / name
        if not local_path.is_file():
            problems.append(f"{name} 本地没有这份契约。")
            continue
        local_hash = digest(local_path.read_bytes())
        remote_hash = digest(remote)
        if local_hash != remote_hash:
            problems.append(
                f"{name} sha256 不一致。本地 {local_hash}，k12-qbank main {remote_hash}。"
            )
    return problems


def fetch_remote() -> dict[str, bytes]:
    found: dict[str, bytes] = {}
    for name in FILES:
        url = REMOTE.format(name=name)
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                found[name] = response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ContractSyncError(f"无法读取 k12-qbank main 上的 {name}。") from exc
    return found


def main(fetch=fetch_remote) -> int:
    try:
        remote = fetch()
    except ContractSyncError as exc:
        print(exc)
        return 1
    problems = differences(ROOT / "contracts", remote)
    if problems:
        for item in problems:
            print(item)
        return 1
    print("契约与 k12-qbank main 一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
