"""Serena's documented Codex hooks (oraios.github.io/serena, clients page) as loadout-owned entries in
~/.codex/hooks.json: added when missing, never twice, the user's entries byte for byte (ADR 0028)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import paths, runner
from .jsonio import dumps_like, json_style, save_json, write_atomic

# (event, matcher or None, serena-hooks subcommand, timeout or None), exactly as Serena documents them
SERENA_HOOKS = (("PreToolUse", "Bash", "remind", 5), ("PreToolUse", "^mcp__serena__", "plan-guard", 5),
                ("PostToolUse", "^mcp__serena__.*$", "reset", None), ("SessionStart", "startup|resume", "activate", 5),
                ("UserPromptSubmit", None, "plan-context", 5), ("SessionEnd", None, "cleanup", 3))
ALSO = {"cleanup": ("SessionEnd", "Stop")}  # Serena: cleanup under exactly one of these, never both


def path() -> Path:
    return paths.codex_home() / "hooks.json"


def _group(matcher, sub, timeout) -> dict:
    hook = {"type": "command", "command": f"serena-hooks {sub} --client=codex", **({"timeout": timeout} if timeout else {})}
    return {**({"matcher": matcher} if matcher is not None else {}), "hooks": [hook]}


def _canon(group) -> str:
    return json.dumps(group, sort_keys=True)


_TOOL = re.compile(r"(?:^|[\s/\\\"'])serena-hooks(?:\.exe)?[\"']?(?=\s|$)")


def _runs(command: str, sub: str) -> bool:
    """`serena-hooks <sub> --client=codex` in any flag order, by a full path or quoted."""
    m = _TOOL.search(command)
    if m is None:
        return False
    words = [w.strip("\"'") for w in command[m.end():].split()]
    codex = "--client=codex" in words or any(a == "--client" and b == "codex" for a, b in zip(words, words[1:]))
    return sub in words and codex


def _inline() -> dict:
    """Hook groups the user defined inline as [hooks] in config.toml (Codex reads both forms), by event."""
    import tomllib
    cfg = paths.codex_home() / "config.toml"
    try:
        hooks = tomllib.loads(cfg.read_text(encoding="utf-8")).get("hooks", {}) if cfg.exists() else {}
    except Exception:
        return {}
    return {ev: groups for ev, groups in hooks.items() if ev != "state" and isinstance(groups, list)} \
        if isinstance(hooks, dict) else {}


def _present(data: dict, event: str, sub: str) -> bool:
    for ev in ALSO.get(sub, (event,)):
        for group in data.get("hooks", {}).get(ev, []) or []:
            hooks_ = group.get("hooks") if isinstance(group, dict) else None
            for hook in (hooks_ if isinstance(hooks_, list) else []):
                if isinstance(hook, dict) and isinstance(hook.get("command"), str) and _runs(hook["command"], sub):
                    return True
    return False


def serena_items() -> dict[str, str]:
    """Every Serena hook in hooks.json, loadout's or the user's own (Codex runs neither before /hooks), as Codex's
    [hooks.state] key '<absolute path>:<event_snake>:<group>:<hook>' (codex-rs/hooks/src/lib.rs, discovery.rs) ->
    its content (event, the group's matcher, the handler), canonical."""
    try:
        events = json.loads(path().read_bytes().decode("utf-8")).get("hooks", {}) if path().exists() else {}
    except (OSError, ValueError, AttributeError):
        return {}
    snake = lambda name: re.sub(r"(?<!^)([A-Z])", r"_\1", name).lower()  # noqa: E731
    subs = {s for _, _, s, _ in SERENA_HOOKS}
    items = {}
    for event, groups in (events.items() if isinstance(events, dict) else []):
        for gi, group in enumerate(groups if isinstance(groups, list) else []):
            hooks_ = group.get("hooks") if isinstance(group, dict) else None
            for hi, hook in enumerate(hooks_ if isinstance(hooks_, list) else []):
                command = hook.get("command") if isinstance(hook, dict) else None
                if isinstance(command, str) and any(_runs(command, sub) for sub in subs):
                    items[f"{path()}:{snake(event)}:{gi}:{hi}"] = json.dumps([event, group.get("matcher"), hook],
                                                                             sort_keys=True)
    return items


def trust_keys() -> set[str]:
    return set(serena_items())


def _record() -> dict:
    from . import codex
    return codex.read_record()


INLINE_MISSING = "add these yourself to its [hooks]"  # markers of apply's lines; codex._hooks_fix keys the fix on them
FORMAT_MISSING = "add these yourself (loadout cannot reproduce"
OLD_LEFT = "loadout's old Serena hooks are still in it"
MOVED = "hooks.json: removed loadout's Serena remind"  # apply._codex_facts: serena_remind_moved


def apply(bk, dry_run: bool = False, keep: bool = False) -> list[str]:
    """keep: never remove loadout's entries (the background sync, whose PATH can lack Serena's folder; a removal
    would also shift the positions Codex keys its approvals on)."""
    from . import codex
    p = path()
    try:  # bytes, so line endings count
        old = p.read_bytes().decode("utf-8") if p.exists() else ""
        data = json.loads(old) if old else {}
    except (OSError, ValueError) as exc:
        return [f"skipped {p}: it is not valid JSON ({exc}); fix it, then run loadout bootstrap"]
    if not isinstance(data, dict) or not isinstance(data.get("hooks", {}), dict):
        return [f"skipped {p}: it has no hooks object; nothing written"]
    odd = sorted(ev for ev, groups in data.get("hooks", {}).items() if not isinstance(groups, list))
    if odd:
        return [f"skipped {p}: {', '.join(odd)} is not a list of hook groups; nothing written"]
    record = _record()
    owned = [o for o in record.get("hooks", []) if isinstance(o, dict)]
    created = {ev for ev in record.get("hook_events", []) if isinstance(ev, str)}  # event keys loadout added
    if runner.have("serena-hooks"):
        wanted = SERENA_HOOKS
    elif runner.have("serena"):  # Serena is there, only serena-hooks is not on this PATH (a background run): keep
        return []
    elif keep:
        return []
    else:
        wanted = ()
    moved = wanted is SERENA_HOOKS and codex.plugin_runs_remind()  # the plugin's copy runs remind, guarded
    if moved and not keep:  # loadout's recorded remind goes (backed up below); the background sync never migrates
        wanted = tuple(row for row in SERENA_HOOKS if row[2] != "remind")
    events = data.setdefault("hooks", {})
    kept, changed, gone = [], False, []
    for o in owned:  # loadout's entries: drop the unwanted ones, forget the ones the user changed
        groups = events.get(o.get("event"), [])
        hit = next((g for g in groups if _canon(g) == o.get("group")), None)
        if hit is None:
            continue  # changed or removed by the user: theirs now
        if not any(e == o["event"] and _canon(_group(m, s, t)) == o["group"] for e, m, s, t in wanted):
            groups.remove(hit)
            gone.append(hit)
            changed = True
            continue
        kept.append(o)
    inline = _inline()
    both = {"hooks": {ev: [*(events.get(ev) or []), *(inline.get(ev) or [])] for ev in {*events, *inline}}}
    missing = [(e, m, s, t) for e, m, s, t in wanted if not _present(both, e, s) and not (moved and s == "remind")]
    if missing and inline and not p.exists():  # the user keeps hooks in config.toml: a hooks.json beside it is mixed
        snippet = "; ".join(f"{e}: {json.dumps(_group(m, s, t))}" for e, m, s, t in missing)
        return [f"{paths.codex_home() / 'config.toml'}: Serena hooks missing, {INLINE_MISSING} "
                f"(loadout creates no hooks.json next to inline hooks): {snippet}"]
    for e, m, s, t in missing:
        group = _group(m, s, t)
        if e not in events:
            created.add(e)
        events.setdefault(e, []).append(group)
        kept.append({"event": e, "group": _canon(group)})
        changed = True
    for ev in [ev for ev in created if events.get(ev) == []]:  # only event keys loadout itself added
        del events[ev]
    created = {ev for ev in created if ev in events}
    style = json_style(old) if old else None  # the file's own format (indent, line endings, ASCII escapes)
    if old and style is not None and dumps_like(style, json.loads(old)) != old:
        style = None  # not byte-exact: never rewrite
    new = dumps_like(style, data) if style else json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    new_record = {**record, "hooks": kept, "hook_events": sorted(created)}
    for key in ("hooks", "hook_events"):
        if not new_record[key]:
            new_record.pop(key)
    if not changed:
        if new_record != record and not dry_run:
            save_json(codex.record_path(), new_record)
        return []
    if old and style is None:
        snippet = "; ".join(f"{e}: {json.dumps(_group(m, s, t))}" for e, m, s, t in missing)
        snippet += " (the table in docs/reference/hooks.md, section \"Serena's hooks in Codex\")"
        return [f"{p}: Serena hooks missing, {FORMAT_MISSING} that file's format): "
                f"{snippet}" if missing else f"{p}: {OLD_LEFT}; remove them yourself"]
    if dry_run:
        return [f"{p}: Serena hooks pending"]
    if p.exists():  # every rewrite, so `loadout restore` of this run puts the file back as it was
        bk.save_copy(p, "Codex hooks.json before loadout changed it")
    else:
        bk.record_created(p, "created Codex hooks.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(p, new)
    codex.record_path().parent.mkdir(parents=True, exist_ok=True)
    save_json(codex.record_path(), new_record)
    added = [s for _, _, s, _ in missing]
    remind_gone = _present({"hooks": {"PreToolUse": gone}}, "PreToolUse", "remind")
    out = [f"hooks.json: added Serena's hooks ({', '.join(added)}); approve them in Codex: /hooks"] if added else []
    if moved and remind_gone:
        out.append(f"{MOVED} (loadout's plugin runs it now); approve the changed hooks in Codex: /hooks")
    return out or ["hooks.json: removed loadout's Serena hooks; if Codex asks about your other hooks, review them in /hooks"]
