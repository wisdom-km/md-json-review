"""Install handle for the review tool. The program still imports no third-party package.

setuptools is used only while pip builds this package. It is not imported here.
"""

from __future__ import annotations

from pathlib import Path


def rules_text() -> str:
    """Return config/split_rules.json. An installed copy uses the file beside this module."""
    repo = Path(__file__).resolve().parents[2] / "config" / "split_rules.json"
    if repo.is_file():
        return repo.read_text(encoding="utf-8")
    return Path(__file__).with_name("split_rules.json").read_text(encoding="utf-8")
