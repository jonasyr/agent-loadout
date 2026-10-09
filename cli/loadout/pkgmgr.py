"""Update a catalog binary through the package manager that installed it (mise, Homebrew).

A tool installed by mise or brew must be upgraded by them: its own self-updater would
either fail or create a second copy the package manager does not know about.
"""
from __future__ import annotations

import os

from . import catalog, runner

MISE_INSTALLS = "/mise/installs/"
MISE_SHIMS = "/mise/shims/"


def _norm(path: str) -> str:
    return path.replace("\\", "/")


def _realpath(path: str) -> str:
    return os.path.realpath(path)


def _mise_tool(entry: dict, path: str) -> str | None:
    p = _norm(path)
    if MISE_SHIMS in p and runner.have("mise"):
        res = runner.run(["mise", "which", entry["id"]], timeout=20)
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


def _brew_formula(entry: dict, path: str) -> str | None:
    if not runner.have("brew"):
        return None
    real = _norm(_realpath(path))
    if "/Cellar/" in real:
        return entry.get("brew") or real.split("/Cellar/", 1)[1].split("/", 1)[0]
    res = runner.run(["brew", "--prefix"], timeout=20)
    prefix = _norm(res.stdout.strip()).rstrip("/") if res.ok else ""
    if prefix and _norm(path).startswith(prefix + "/"):
        return entry.get("brew") or entry["id"]
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
