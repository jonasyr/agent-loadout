"""Where tasklog keeps its data."""
from __future__ import annotations

import os
from pathlib import Path


def data_dir() -> Path:
    """TASKLOG_HOME overrides the default ~/.local/share/tasklog."""
    env = os.environ.get("TASKLOG_HOME")
    return Path(env) if env else Path.home() / ".local" / "share" / "tasklog"


def db_path() -> Path:
    return data_dir() / "tasks.db"
