"""Serena's documented Codex hooks (oraios.github.io/serena, clients page) as loadout-owned entries in
~/.codex/hooks.json: added when missing, never twice, the user's entries byte for byte (ADR 0028)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from . import paths, runner
from .jsonio import save_json, write_atomic

# (event, matcher or None, serena-hooks subcommand, timeout or None), exactly as Serena documents them
SERENA_HOOKS = (("PreToolUse", "Bash", "remind", 5), ("PreToolUse", "^mcp__serena__", "plan-guard", None),
                ("PostToolUse", "^mcp__serena__.*$", "reset", None), ("SessionStart", "startup|resume", "activate", None),
                ("UserPromptSubmit", None, "plan-context", None), ("SessionEnd", None, "cleanup", 3))
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


def apply(bk, dry_run: bool = False, keep: bool = False) -> list[str]:
    """keep: never remove loadout's entries (the background sync, whose PATH can lack Serena's folder; a removal
    would also shift the positions Codex keys its approvals on)."""
    from . import codex
    p = path()
    try:  # bytes, so line endings count: a CRLF file is "another format" and never rewritten
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
    events = data.setdefault("hooks", {})
    kept, changed = [], False
    for o in owned:  # loadout's entries: drop the unwanted ones, forget the ones the user changed
        groups = events.get(o.get("event"), [])
        hit = next((g for g in groups if _canon(g) == o.get("group")), None)
        if hit is None:
            continue  # changed or removed by the user: theirs now
        if not any(e == o["event"] and _canon(_group(m, s, t)) == o["group"] for e, m, s, t in wanted):
            groups.remove(hit)
            changed = True
            continue
        kept.append(o)
    missing = [(e, m, s, t) for e, m, s, t in wanted if not _present(data, e, s)]
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
    new = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    new_record = {**record, "hooks": kept, "hook_events": sorted(created)}
    for key in ("hooks", "hook_events"):
        if not new_record[key]:
            new_record.pop(key)
    if not changed:
        if new_record != record and not dry_run:
            save_json(codex.record_path(), new_record)
        return []
    if old and json.dumps(json.loads(old), indent=2, ensure_ascii=False) + "\n" != old:
        snippet = "; ".join(f"{e}: {json.dumps(_group(m, s, t))}" for e, m, s, t in missing)
        snippet += " (the table in docs/reference/hooks.md, section \"Serena's hooks in Codex\")"
        return [f"{p}: Serena hooks missing, add these yourself (loadout does not rewrite a file in another format): "
                f"{snippet}" if missing else f"{p}: loadout's old Serena hooks are still in it; remove them yourself"]
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
    return [f"hooks.json: added Serena's hooks ({', '.join(added)}); approve them in Codex: /hooks"] if added else \
           ["hooks.json: removed loadout's Serena hooks; if Codex asks about your other hooks, review them in /hooks"]
