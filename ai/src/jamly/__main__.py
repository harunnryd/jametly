from __future__ import annotations

import os
import sys
from pathlib import Path

from . import bridge
from .db import LocalStore


def _resolve_db_path() -> Path:
    home = os.environ.get("JAMETLY_HOME")
    if home:
        root = Path(home) / ".config" / "jametly"
    else:
        root = Path.home() / ".config" / "jametly"
    root.mkdir(parents=True, exist_ok=True)
    return root / "jametly.sqlite"


def main() -> None:
    store = LocalStore(_resolve_db_path())
    try:
        bridge.run(sys.stdin, sys.stdout, store=store)
    finally:
        store.close()


if __name__ == "__main__":
    main()
