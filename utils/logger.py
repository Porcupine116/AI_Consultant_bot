from __future__ import annotations

import logging
import sys
from pathlib import Path

from utils.helpers import ensure_parent_dir


def setup_logging(level: str = "INFO", log_file: str | Path = "logs/bot.log") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())

    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    file_path = Path(log_file)
    ensure_parent_dir(file_path)
    file_handler = logging.FileHandler(file_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
