"""Codex CLI as a second target: the same kit and personal layer, mapped to Codex (docs/how-to/codex.md)."""
from __future__ import annotations

import re
from pathlib import Path

from . import paths, runner
from .jsonio import load_json, save_json

MIN_VERSION = (0, 161)


def targets_path() -> Path:
    return paths.personal_root() / "targets.json"


def enabled() -> bool:
    return load_json(targets_path()).get("codex") is True


def decided() -> bool:
    return "codex" in load_json(targets_path())


def set_enabled(on: bool) -> str:
    data = load_json(targets_path())
    data["codex"] = on
    targets_path().parent.mkdir(parents=True, exist_ok=True)
    save_json(targets_path(), data)
    return f"codex: {'on' if on else 'off'}"


def unavailable() -> str | None:
    """None when a usable codex is on PATH, else the reason in one line."""
    if not runner.have("codex"):
        return "codex not found on PATH"
    res = runner.run(["codex", "--version"], timeout=20)
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", res.stdout)
    if not m:
        return "could not read codex --version"
    if (int(m.group(1)), int(m.group(2))) < MIN_VERSION:
        return f"codex {m.group(0)} is too old; loadout needs 0.161 or newer (update it: mise upgrade codex)"
    return None


START = "<!-- loadout:start -->"
END = "<!-- loadout:end -->"


def _tilde(path: Path) -> str:
    home = str(paths.home())
    return "~" + str(path)[len(home):] if str(path).startswith(home) else str(path)


def render_instructions() -> str:
    """Codex has no @include and no rules folder, so the rules are copied in; their files stay the only source."""
    kit, personal = paths.kit_root() / "rules", paths.personal_root() / "rules"
    parts = [START, f"<!-- Managed by loadout from {_tilde(kit)} and {_tilde(personal)}; "
                    "edit those files, not this block. -->"]
    for folder in (kit, personal):
        if folder.is_dir():
            parts += [f.read_text(encoding="utf-8").strip() for f in sorted(folder.glob("*.md"))]
    parts.append(END)
    return "\n\n".join(parts) + "\n"


def splice(text: str, block: str) -> str | None:
    """text with the block replaced or appended; None when the markers are unbalanced or duplicated."""
    starts, ends = text.count(START), text.count(END)
    if starts == ends == 0:
        return block if not text.strip() else text.rstrip("\n") + "\n\n" + block
    if starts == ends == 1 and text.index(START) < text.index(END):
        before, rest = text.split(START, 1)
        after = rest.split(END, 1)[1]
        return before + block.rstrip("\n") + after
    return None


def apply_instructions(bk) -> str:
    path = paths.codex_home() / "AGENTS.md"
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    new = splice(old, render_instructions())
    if new is None:
        return f"skipped {path}: its loadout markers are unbalanced or duplicated; fix them by hand"
    if new == old:
        return "instructions up to date"
    if path.exists() and START not in old:
        bk.save_copy(path, "Codex AGENTS.md before loadout added its block")
    elif not path.exists():
        bk.record_created(path, "created Codex AGENTS.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new, encoding="utf-8", newline="\n")
    return f"instructions written to {_tilde(path)}"
