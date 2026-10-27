"""The recommended setup cell of this machine and its bootstrap flags (docs/reference/setup-matrix.md).

FLAGS mirrors the `--` code spans of the matrix's cells; tests/test_recommend.py pins it against the matrix."""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import paths, runner

MATRIX = "docs/reference/setup-matrix.md"
COLUMN = {("claude",): "Claude Code", ("codex",): "Codex", ("claude", "codex"): "Both"}
ROW = {"cli": "CLI only", "none": "CLI only", "vscode": "VS Code extension",
       "vscode+cli": "VS Code extension + CLI (optional)", "windows-window": "A Windows window anyway (not recommended)"}
CODEX_ROW = {"windows": "On Windows only", "both": "On both sides"}
PLATFORMS = {"linux": "Linux", "macos": "macOS", "wsl": "WSL 2", "windows": "Windows (experimental)"}
SURFACES = {"cli": "CLI", "vscode": "VS Code extension", "vscode+cli": "VS Code extension + CLI",
            "windows-window": "VS Code extension in a Windows window",
            "none": "no CLI or VS Code extension found yet"}

# (table, row, column) -> the cell's code spans that start with `--`, in order
FLAGS: dict[tuple[str, str, str], tuple[str, ...]] = {
    ("linux-macos", "CLI only", "Claude Code"): ("--install --agents claude",),
    ("linux-macos", "CLI only", "Codex"): ("--install --agents codex",),
    ("linux-macos", "CLI only", "Both"): ("--install --agents claude,codex",),
    ("linux-macos", "VS Code extension", "Claude Code"): ("--install --agents claude",),
    ("linux-macos", "VS Code extension", "Codex"): ("--install --agents codex",),
    ("linux-macos", "VS Code extension", "Both"): ("--install --agents claude,codex",),
    ("linux-macos", "VS Code extension + CLI (optional)", "Claude Code"): ("--install --agents claude",),
    ("linux-macos", "VS Code extension + CLI (optional)", "Codex"): ("--install --agents codex",),
    ("linux-macos", "VS Code extension + CLI (optional)", "Both"): ("--install --agents claude,codex",),
    ("wsl", "CLI only", "Claude Code"): ("--install --agents claude",),
    ("wsl", "CLI only", "Codex"): ("--install --agents codex", "--codex-side wsl"),
    ("wsl", "CLI only", "Both"): ("--install --agents claude,codex",),
    ("wsl", "VS Code extension", "Claude Code"): ("--install --agents claude",),
    ("wsl", "VS Code extension", "Codex"): ("--install --agents codex", "--codex-side wsl"),
    ("wsl", "VS Code extension", "Both"): ("--install --agents claude,codex",),
    ("wsl", "VS Code extension + CLI (optional)", "Claude Code"): ("--install --agents claude",),
    ("wsl", "VS Code extension + CLI (optional)", "Codex"): ("--install --agents codex", "--codex-side wsl"),
    ("wsl", "VS Code extension + CLI (optional)", "Both"): ("--install --agents claude,codex",),
    ("wsl", "A Windows window anyway (not recommended)", "Codex"): ("--vscode-wsl",),
    ("wsl", "A Windows window anyway (not recommended)", "Both"): ("--vscode-wsl",),
    ("codex-windows", "On Windows only", "Codex"): ("--install --agents codex",),
    ("codex-windows", "On Windows only", "Both"): ("--install --agents claude,codex", "--codex-side windows"),
    ("codex-windows", "On both sides", "Codex"): ("--install --agents codex",),
    ("codex-windows", "On both sides", "Both"): ("--install --agents claude,codex",),
}


@dataclass(frozen=True)
class Cell:
    platform: str  # "linux", "macos", "wsl" or "windows"
    agents: tuple[str, ...]
    surface: str  # "cli", "vscode", "vscode+cli", "windows-window" (WSL only) or "none"
    codex_side: str | None  # "windows" or "both" in WSL with Codex on, else None


def _platform() -> str:
    from . import bootstrap, wsl
    return "wsl" if wsl.detect() == 2 else bootstrap.os_key()


def detect(chosen: dict[str, bool], cs=None, codex_windows: bool = False, found: list | None = None) -> Cell:
    from . import vscode
    platform = _platform()
    agents = tuple(a for a in ("claude", "codex") if chosen.get(a)) or ("claude",)
    if found is None:  # nothing of an agent that is off is read
        found = vscode.extensions(chosen, win_home=getattr(cs, "windows_home", None), look=cs is None)
    found = [e for e in found if e.agent in agents]
    cli = any(runner.have(a) for a in agents)
    if platform == "wsl" and found and all(e.install.where == "windows" and not vscode.runs_in_wsl(e)
                                           for e in found):
        surface = "windows-window"
    elif found:
        surface = "vscode+cli" if cli else "vscode"
    else:
        surface = "cli" if cli else "none"
    side = None
    if platform == "wsl" and "codex" in agents:
        if codex_windows:
            side = "windows"
        elif cs is not None and cs.side in CODEX_ROW:
            side = cs.side
    return Cell(platform, agents, surface, side)


def describe(cell: Cell) -> str:
    names = {"claude": "Claude Code", "codex": "Codex"}
    parts = [PLATFORMS[cell.platform], " + ".join(names[a] for a in cell.agents), SURFACES[cell.surface]]
    if cell.codex_side:
        parts.append("Codex on Windows" if cell.codex_side == "windows" else "Codex on both sides")
    return " · ".join(parts)


def _key(cell: Cell) -> tuple[str, str, str]:
    col = COLUMN[cell.agents]
    if cell.codex_side:
        return ("codex-windows", CODEX_ROW[cell.codex_side], col)
    table = "wsl" if cell.platform == "wsl" else "linux-macos"
    return (table, ROW[cell.surface], col)


def flags(cell: Cell) -> str:
    table, row, col = _key(cell)
    if cell.surface == "windows-window" and not cell.codex_side:
        # the Windows-window row only adds to the VS Code extension row (the Claude Code column adds nothing)
        base = FLAGS[(table, ROW["vscode"], col)]
        return " ".join(base + FLAGS.get((table, row, col), ()))
    return " ".join(FLAGS[(table, row, col)])


def anchor(cell: Cell) -> str:
    if cell.codex_side:
        name = "codex-on-windows-or-on-both-sides"
    else:
        name = {"wsl": "wsl-2", "windows": "native-windows-experimental"}.get(cell.platform, "linux-and-macos")
    return f"docs/reference/setup-matrix.md#{name}"


def differences(cell: Cell, chosen: dict[str, bool], install: bool, missing: list[str], vscode_wsl: bool,
                codex_cli: bool) -> list[str]:
    out = []
    if not install and missing:
        out.append(f"{', '.join(missing)} missing and no --install: the recommended setup installs missing tools")
    if cell.platform == "wsl" and chosen.get("codex") and cell.surface == "windows-window" and not vscode_wsl:
        out.append("Codex's VS Code extension runs on Windows and no --vscode-wsl: the recommended setup adds it")
    if not chosen.get("codex") and runner.have("codex"):
        out.append("a Codex CLI is on PATH but Codex is not chosen (--agents)")
    if chosen.get("codex") and not codex_cli and runner.have("codex"):
        out.append("--without-codex-cli given while a Codex CLI is on PATH")
    return out


def _tables() -> dict[str, dict[str, dict[str, tuple[str, ...]]]]:
    heads = {"## Linux and macOS": "linux-macos", "## WSL 2": "wsl",
             "### Codex on Windows, or on both sides": "codex-windows"}
    lines = (paths.kit_root() / MATRIX).read_text(encoding="utf-8").splitlines()
    out: dict = {}
    for i, line in enumerate(lines):
        if line.strip() not in heads:
            continue
        table, rows, started = {}, [], False
        for row in lines[i + 1:]:
            if row.startswith("|"):
                started = True
                rows.append([c.strip() for c in row.strip().strip("|").split("|")])
            elif started:
                break
        cols = rows[0][1:]
        prev: dict[str, tuple[str, ...]] = {}
        for cells in rows[2:]:
            cur = {}
            for col, text in zip(cols, cells[1:]):
                spans = tuple(s for s in re.findall(r"`([^`]+)`", text) if s.startswith("--"))
                cur[col] = prev.get(col, ()) if text.lower().startswith("as in the row above") else spans
            table[cells[0]] = prev = cur
        out[heads[line.strip()]] = table
    return out


def matrix_flags(key: tuple[str, str, str]) -> tuple[str, ...]:
    table, row, col = key
    return _tables()[table][row][col]


def matrix_keys() -> list[tuple[str, str, str]]:
    return [(t, r, c) for t, rows in _tables().items() for r, cols in rows.items()
            for c, spans in cols.items() if spans]
