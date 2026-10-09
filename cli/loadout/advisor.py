"""`loadout advisor-mark <plan>`: record that /loadout:execution-advisor evaluated a plan.

The hash and state format live in the plugin's hook script (plugins/loadout/hooks/advisor.py),
which this module loads, so the Stop hook and this command can never disagree."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from . import paths


def _hook():
    path = paths.kit_root() / "plugins" / "loadout" / "hooks" / "advisor.py"
    spec = importlib.util.spec_from_file_location("loadout_advisor_hook", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def mark(plan: str) -> str:
    p = Path(plan).expanduser()
    if not p.is_file():
        raise ValueError(f"no such plan: {plan}")
    digest = _hook().mark(str(p.resolve()))
    return f"marked {p} as evaluated ({digest[:12]})"
