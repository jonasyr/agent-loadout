"""The files `codebase-memory-mcp install` (0.12) writes next to loadout's plugin: found for `check`, removed by
`adopt` only after a yes, each with a backup first so `loadout restore` reverts it.

Only what is certainly the installer's is removable; anything unsure (unbalanced markers, a JSON layout loadout
cannot reproduce byte for byte, inline config.toml hooks) is named, never changed. Rows and lines carry paths and
labels only, never a file's content. The new script names are not `duplicates.LEGACY_SCRIPTS`: `loadout update`
never removes them (ADR 0035 covers the old `cbm-*` names only).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import paths

NEW_SCRIPTS = ("codebase-memory-session.sh", "codebase-memory-coverage.sh")
AGENTS_START = "<!-- codebase-memory-mcp:start -->"
AGENTS_END = "<!-- codebase-memory-mcp:end -->"
PROGRAM = "codebase-memory-mcp"
AGENT_FILE = "codebase-memory.md"
POINTER_EVENTS = ("SessionStart", "SubagentStart")  # what loadout's project pointer (cbm_project.py) answers
INLINE_FIX = "remove it from config.toml by hand"
BLOCK_FIX = "remove the codebase-memory-mcp block from AGENTS.md by hand (its markers are unbalanced or repeated)"
STYLE_FIX = "remove it from hooks.json by hand (loadout cannot rewrite that file's layout byte for byte)"


@dataclass
class Artefact:
    kind: str    # claude-hook | claude-script | claude-agent | codex-agents-block | codex-hook | codex-inline-hook
    agent: str   # claude | codex
    path: Path
    label: str   # for the row: never file content
    removable: bool
    where: dict = field(default_factory=dict)
    doubles: str = "hooks"  # routing | project pointer | hooks
    fix: str = "loadout adopt"


# --- recognising the installer's commands


def _program(word: str) -> str:
    from .duplicates import _program as program
    return program(word).lower()


def _expand(word: str) -> str:
    home = str(paths.home())
    for prefix in ("~/", "$HOME/", "${HOME}/"):
        if word.startswith(prefix):
            return home + "/" + word[len(prefix):]
    return word


def _words(hook: dict) -> list[str]:
    from .duplicates import _hook_words
    return _hook_words(hook)


def _runs(words: list[str], sub_prefix: str | None = None) -> bool:
    """A word whose program is codebase-memory-mcp (not right after echo/printf/#), with the first non-flag word
    after it starting with sub_prefix when given."""
    from .duplicates import at_command
    for i, w in enumerate(words):
        if _program(w) != PROGRAM or not at_command(words, i):
            continue
        rest = [x for x in words[i + 1:] if not x.startswith("-")]
        if sub_prefix is None or (rest and rest[0].startswith(sub_prefix)):
            return True
    return False


def _script(words: list[str], hooks_dir: Path | None = None) -> str | None:
    """The NEW_SCRIPTS name a hook runs (in hooks_dir when given), not right after echo/printf/#."""
    import os
    from .duplicates import at_command
    for i, w in enumerate(words):
        name = w.strip("'\"").replace("\\", "/").rsplit("/", 1)[-1]
        if name not in NEW_SCRIPTS or not at_command(words, i):
            continue
        if hooks_dir is None or os.path.normpath(os.path.dirname(_expand(w.strip("'\"")))) == os.path.normpath(str(hooks_dir)):
            return name
    return None


def runs_new_script(command) -> bool:
    """A Claude Code hook command that runs ~/.claude/hooks/<NEW_SCRIPTS> (update's note stays quiet for it)."""
    from .duplicates import _split
    return isinstance(command, str) and _script(_split(command), paths.claude_home() / "hooks") is not None


def claude_hook_words(words: list[str]) -> bool:
    """A Claude Code settings hook the installer wrote: it runs `codebase-memory-mcp hook…` or one of the
    NEW_SCRIPTS from ~/.claude/hooks (never a same-named script elsewhere, never a name inside echo text)."""
    return _runs(words, "hook") or _script(words, paths.claude_home() / "hooks") is not None


def is_installer_hook(item) -> bool:
    """inventory's hook item (~/.claude/settings.json) for such a hook: classify offers it as the kit's."""
    from .duplicates import _hook_words
    hook = {"command": item.detail, **({"args": item.extra["args"]} if "args" in item.extra else {})}
    return item.kind == "hook" and claude_hook_words(_hook_words(hook))


def adopt_item(a: Artefact):
    """The inventory item adopt shows for an artefact (its leave decision is keyed on it): a claude-hook is
    inventory's hook item, any other an `installer` item."""
    from .inventory import Item
    if a.kind == "claude-hook":
        w = a.where
        extra = {"event": w["event"], "group": w["group"], "hook": w["hook"],
                 **({"args": w["args"]} if "args" in w else {})}
        return Item("hook", f"{w['event']}:{w['matcher']}", w["command"], "~/.claude/settings.json", extra)
    return Item("installer", a.label, a.kind, str(a.path), {"artefact": a})


def _echo(words: list[str], command: str) -> bool:
    return bool(words) and _program(words[0]) in ("echo", "printf") and PROGRAM in command


def _doubles(event: str) -> str:
    return "project pointer" if event in POINTER_EVENTS else "hooks"


def _tilde(path: Path) -> str:
    from .codex import _tilde
    return _tilde(path)


# --- finding


def _claude_plugin_on() -> bool:
    from . import duplicates
    try:
        return duplicates.plugin_enabled()
    except Exception:
        return False


def _codex_config() -> dict | None:
    """config.toml as data, or None when it cannot be read."""
    import tomllib
    cfg = paths.codex_home() / "config.toml"
    try:
        return tomllib.loads(cfg.read_text(encoding="utf-8")) if cfg.exists() else {}
    except Exception:
        return None


def _codex_plugin_on(data: dict | None) -> bool:
    from .codex import _plugin_hooks_on
    return data is not None and _plugin_hooks_on(data)


def _claude() -> list[Artefact]:
    from .jsonio import get_dict, get_list, load_json
    from .settings_merge import matcher_of
    home = paths.claude_home()
    hooks_dir = home / "hooks"
    settings = home / "settings.json"
    out = []
    try:
        data = load_json(settings)
    except Exception:
        data = {}
    for event, groups in get_dict(data, "hooks").items():
        for gi, group in enumerate(groups if isinstance(groups, list) else []):
            for hi, hook in enumerate(get_list(group, "hooks")):
                if not isinstance(hook, dict) or not isinstance(group, dict):
                    continue
                words = _words(hook)
                if claude_hook_words(words):
                    where = {"event": event, "group": gi, "hook": hi, "matcher": matcher_of(group),
                             "command": hook.get("command", ""), "augment": "hook-augment" in words}
                    if "args" in hook:
                        where["args"] = hook["args"]
                    out.append(Artefact("claude-hook", "claude", settings, f"{event}:{matcher_of(group)} hook", True,
                                        where, _doubles(event)))
    from .maintenance import _hook_references
    refs = _hook_references()
    codex_refs = _codex_hook_text()
    for name in NEW_SCRIPTS:
        path = hooks_dir / name
        if path.is_file() and name not in refs:
            # a Codex hook that still runs it (one loadout names but never removes, or one you left) keeps it
            out.append(Artefact("claude-script", "claude", path, f"hook script {name}", name not in codex_refs, {},
                                "project pointer" if name == NEW_SCRIPTS[0] else "hooks"))
    agent = home / "agents" / AGENT_FILE
    if agent.is_file() or agent.is_symlink():
        out.append(Artefact("claude-agent", "claude", agent, f"agent {AGENT_FILE}", True, {}, "routing"))
    return out


def _block_span(text: str) -> tuple[int, int] | None:
    """(start, end) of the installer's one block, end past its marker and one following newline; None when the
    markers are unbalanced, repeated or out of order, or the span holds loadout's own markers."""
    from .codex import END, START
    if text.count(AGENTS_START) != 1 or text.count(AGENTS_END) != 1:
        return None
    start, end = text.index(AGENTS_START), text.index(AGENTS_END)
    if end < start:
        return None
    end += len(AGENTS_END)
    if START in text[start:end] or END in text[start:end]:
        return None
    if text.startswith("\r\n", end):
        end += 2
    elif text.startswith("\n", end):
        end += 1
    return start, end


def _read_exact(path: Path) -> str | None:
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _codex_hooks_style(text: str):
    """The file's JSON style when loadout can rewrite it byte for byte, else None."""
    from .jsonio import dumps_like, json_style
    style = json_style(text)
    if style is None:
        return None
    try:
        return style if dumps_like(style, json.loads(text)) == text else None
    except ValueError:
        return None


def _owned(event: str, group) -> bool:
    from .codex import read_record
    canon = json.dumps(group, sort_keys=True)
    return any(isinstance(o, dict) and o.get("event") == event and o.get("group") == canon
               for o in read_record().get("hooks", []) or [])


def _is_cbm_hook(hook) -> bool:
    if not isinstance(hook, dict) or not isinstance(hook.get("command"), str):
        return False
    words = _words(hook)  # the installer's forms only: `codebase-memory-mcp hook…`, its scripts, its echo reminder
    scripts = paths.home() / ".claude" / "hooks"  # a path to compare with, not Claude Code's files: Codex stays apart
    return _runs(words, "hook") or _script(words, scripts) is not None or _echo(words, hook["command"])


def _hook_groups(events) -> list[tuple[str, int, int, dict, dict]]:
    out = []
    for event, groups in (events.items() if isinstance(events, dict) else []):
        for gi, group in enumerate(groups if isinstance(groups, list) else []):
            hooks = group.get("hooks") if isinstance(group, dict) else None
            for hi, hook in enumerate(hooks if isinstance(hooks, list) else []):
                if _is_cbm_hook(hook):
                    out.append((event, gi, hi, group, hook))
    return out


def _codex(config: dict | None) -> list[Artefact]:
    home = paths.codex_home()
    out = []
    agents = home / "AGENTS.md"
    text = _read_exact(agents) if agents.is_file() else None
    if text is not None and (AGENTS_START in text or AGENTS_END in text):
        ok = _block_span(text) is not None
        out.append(Artefact("codex-agents-block", "codex", agents, "codebase-memory-mcp block", ok, {}, "routing",
                            "loadout adopt" if ok else BLOCK_FIX))
    hooks_json = home / "hooks.json"
    text = _read_exact(hooks_json) if hooks_json.is_file() else None
    try:
        data = json.loads(text) if text else {}
    except ValueError:
        data = {}
    if isinstance(data, dict):
        style = _codex_hooks_style(text) if text else None
        for event, gi, hi, group, hook in _hook_groups(data.get("hooks")):
            if _owned(event, group):
                continue  # loadout's own entry (codex_hooks), never the installer's
            out.append(Artefact("codex-hook", "codex", hooks_json, f"{event} hook", style is not None,
                                {"event": event, "group": gi, "hook": hi, "canon": json.dumps(hook, sort_keys=True)},
                                _doubles(event), "loadout adopt" if style is not None else STYLE_FIX))
    inline = config.get("hooks") if isinstance(config, dict) else None
    if isinstance(inline, dict):
        events = {ev: g for ev, g in inline.items() if ev != "state"}
        for event, gi, hi, _, _ in _hook_groups(events):
            out.append(Artefact("codex-inline-hook", "codex", home / "config.toml", f"{event} hook in [hooks]", False,
                                {"event": event, "group": gi, "hook": hi}, _doubles(event), INLINE_FIX))
    return out


def _numbered(found: list[Artefact]) -> list[Artefact]:
    """Labels that repeat within one file get #2, #3, ... so each row and adopt item has its own name."""
    seen: dict[tuple, int] = {}
    for a in found:
        key = (str(a.path), a.label)
        seen[key] = seen.get(key, 0) + 1
        if seen[key] > 1:
            a.label = f"{a.label} #{seen[key]}"
    return found


def _codex_hook_text() -> str:
    """The text of Codex's hook files (hooks.json, config.toml), read only with Codex on: what may still run a
    wrapper script."""
    from . import targets
    if not targets.codex_enabled():
        return ""
    parts = []
    for path in (paths.codex_home() / "hooks.json", paths.codex_home() / "config.toml"):
        try:
            parts.append(path.read_text(encoding="utf-8", errors="replace") if path.is_file() else "")
        except OSError:
            parts.append("")
    return "\n".join(parts)


def find() -> list[Artefact]:
    """The installer's files, for each agent that is on and has loadout's plugin on. Read only."""
    from . import targets
    found: list[Artefact] = []
    if targets.claude_enabled() and _claude_plugin_on():
        found += _claude()
    if targets.codex_enabled():
        config = _codex_config()
        if _codex_plugin_on(config):
            found += _codex(config)
    return _numbered(found)


# --- removing (adopt, after a yes)


def _remove_block(a: Artefact, bk) -> str:
    from .jsonio import write_atomic_bytes
    text = _read_exact(a.path)
    span = _block_span(text) if text is not None else None
    if span is None:
        raise ValueError(f"{_tilde(a.path)}: the codebase-memory-mcp block is no longer one balanced block")
    bk.save_copy(a.path, "Codex AGENTS.md before loadout removed codebase-memory-mcp's block")
    write_atomic_bytes(a.path, (text[:span[0]] + text[span[1]:]).encode("utf-8"))
    return f"{_tilde(a.path)}: removed codebase-memory-mcp's block (the text around it is unchanged)"


def _remove_hook(a: Artefact, bk) -> str:
    from .jsonio import dumps_like, write_atomic
    text = _read_exact(a.path)
    style = _codex_hooks_style(text) if text else None
    if style is None:
        raise ValueError(f"{_tilde(a.path)}: its layout changed; loadout cannot rewrite it byte for byte")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{_tilde(a.path)}: it is no longer a JSON object")
    event, canon = a.where["event"], a.where["canon"]
    groups = data.get("hooks", {}).get(event) if isinstance(data.get("hooks"), dict) else None
    spots = [(gi, hi) for ev, gi, hi, _, hook in _hook_groups({event: groups})
             if json.dumps(hook, sort_keys=True) == canon and not _owned(event, groups[gi])]
    if not spots:
        raise ValueError(f"{_tilde(a.path)}: the {a.label} is no longer there")
    gi, hi = (a.where["group"], a.where["hook"]) if (a.where["group"], a.where["hook"]) in spots else spots[0]
    bk.save_copy(a.path, "Codex hooks.json before loadout removed a codebase-memory-mcp hook")
    del groups[gi]["hooks"][hi]
    if not groups[gi]["hooks"]:
        del groups[gi]
    if not groups:
        del data["hooks"][event]
    write_atomic(a.path, dumps_like(style, data))
    return (f"{_tilde(a.path)}: removed codebase-memory-mcp's {a.label}; if Codex asks about your other hooks, "
            "review them in /hooks")


def remove(a: Artefact, bk) -> str:
    """Remove one artefact with a backup first; ValueError when it is not removable (or no longer as found)."""
    if not a.removable:
        raise ValueError(f"{a.label} ({_tilde(a.path)}) is not removed by loadout: {a.fix}")
    if a.kind in ("claude-script", "claude-agent"):
        if not (a.path.is_file() or a.path.is_symlink()):
            raise ValueError(f"{_tilde(a.path)} is no longer there")
        bk.move(a.path, f"codebase-memory-mcp {a.label}")
        return f"{_tilde(a.path)}: moved to the backup"
    if a.kind == "codex-agents-block":
        return _remove_block(a, bk)
    if a.kind == "codex-hook":
        return _remove_hook(a, bk)
    raise ValueError(f"{a.label}: removed through adopt's hook entries, not here")
