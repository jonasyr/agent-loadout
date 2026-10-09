"""Export formats. Each module in this package defines NAME (str) and render(tasks) -> str,
where tasks is a list of tasklog.store.Task. Modules are discovered automatically by name;
`tasklog export --format NAME` picks one. Adding a format never touches another module."""
from __future__ import annotations

import importlib
import pkgutil


def formats() -> dict:
    out = {}
    for info in pkgutil.iter_modules(__path__):
        module = importlib.import_module(f"{__name__}.{info.name}")
        out[module.NAME] = module.render
    return out
