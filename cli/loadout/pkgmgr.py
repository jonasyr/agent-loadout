"""Update a catalog binary through the package manager that installed it (mise, Homebrew).

A tool installed by mise or brew must be upgraded by them: its own self-updater would
either fail or create a second copy the package manager does not know about.
"""
from __future__ import annotations

import json
import os

from . import catalog, runner

MISE_INSTALLS = "/mise/installs/"
MISE_SHIMS = "/mise/shims/"


def _norm(path: str) -> str:
    return path.replace("\\", "/")


def _realpath(path: str) -> str:
    return os.path.realpath(path)


def _home() -> str:
    from . import paths
    return str(paths.home())  # not the user's cwd: a project mise.toml must not change the answer


def _mise_tool(entry: dict, path: str) -> str | None:
    if not runner.have("mise"):
        return None
    p = _norm(path)
    if MISE_SHIMS in p:
        res = runner.run(["mise", "which", entry["id"]], cwd=_home(), timeout=20)
        if res.ok and res.stdout.strip():
            p = _norm(res.stdout.strip())
    if MISE_INSTALLS not in p:
        return None
    if entry.get("mise"):
        return entry["mise"]
    install_dir = p.split(MISE_INSTALLS, 1)[1].split("/", 1)[0]
    if install_dir.startswith("npm-"):
        npm = entry.get("version", {}).get("npm", "")
        # mise flattens scoped names (npm:@scope/pkg -> npm-scope-pkg); the catalog keeps the real one
        if npm and install_dir == "npm-" + npm.replace("@", "").replace("/", "-"):
            return f"npm:{npm}"
        return f"npm:{install_dir[4:]}"
    return entry["id"]


def run_cwd(cmd: list[str]) -> str | None:
    """mise commands run in HOME, so a project's mise.toml in the current directory does not apply."""
    return _home() if cmd and cmd[0] == "mise" else None


def mise_tool(entry: dict) -> str | None:
    path = runner.which(entry["id"])
    return _mise_tool(entry, path) if path else None


def mise_outdated(tool: str) -> tuple | None:
    """What mise itself would upgrade (it honours minimum_release_age and pins).

    None: unknown (mise failed); (): up to date; (current, latest): outdated.
    """
    from .versions import parse_version
    res = runner.run(["mise", "outdated", tool, "--json"], cwd=_home(), timeout=60)
    if not res.ok:
        return None
    try:
        data = json.loads(res.stdout or "{}")
    except ValueError:
        return None
    rows = list(data.values()) if isinstance(data, dict) else data if isinstance(data, list) else []
    for row in rows:
        if isinstance(row, dict) and row.get("latest"):
            current, latest = parse_version(str(row.get("current", ""))), parse_version(str(row["latest"]))
            if latest and (current is None or latest > current):
                return (current, latest)
    return ()


def _brew_formula(entry: dict, path: str) -> str | None:
    """Only a proven formula install (<prefix>/Cellar/<formula>/...). Casks and npm globals under brew's
    node are not brew formulae: they keep the catalog command."""
    if not runner.have("brew"):
        return None
    real = _norm(_realpath(path))
    if "/Cellar/" in real:
        return real.split("/Cellar/", 1)[1].split("/", 1)[0]
    return None


def update_plan(entry: dict) -> tuple[list[list[str]], str]:
    """(commands, how): how is 'mise', 'brew' or 'catalog' (the entry's own update command)."""
    path = runner.which(entry["id"])
    if path:
        tool = _mise_tool(entry, path)
        if tool:
            return [["mise", "upgrade", tool]], "mise"
        formula = _brew_formula(entry, path)
        if formula:
            return [["brew", "upgrade", formula]], "brew"
    return catalog.platform_cmds(entry, "update"), "catalog"
