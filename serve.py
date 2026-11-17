"""Start the local review page. Run: py -3 serve.py"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from app.server import main

if __name__ == "__main__":
    main()
