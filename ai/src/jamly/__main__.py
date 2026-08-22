from __future__ import annotations

import os
import sys
from pathlib import Path

from . import bridge
from .config import AppConfig, ConfigPaths, load_config
from .db import LocalStore


def _resolve_paths() -> ConfigPaths:
    home = os.environ.get("JAMETLY_HOME")
    if home:
        return ConfigPaths.from_home(Path(home))
    return ConfigPaths.from_home(Path.home())


def _exit_without_joining_the_blocked_stdin_reader(code: int) -> None:
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)


def main() -> None:
    paths = _resolve_paths()
    store = LocalStore(paths.config_file.with_name("jametly.sqlite"))
    try:
        config = load_config(paths.config_file)
    except FileNotFoundError:
        config = AppConfig()
    code = bridge.EXIT_CLEAN
    try:
        code = bridge.run(
            sys.stdin,
            sys.stdout,
            store=store,
            config=config,
            config_path=paths.config_file,
        )
    finally:
        store.close()

    if code == bridge.EXIT_SIGNALLED:
        _exit_without_joining_the_blocked_stdin_reader(code)
    sys.exit(code)


if __name__ == "__main__":
    main()
