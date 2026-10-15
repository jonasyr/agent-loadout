"""Serena's documented Codex hooks (oraios.github.io/serena, clients page) as loadout-owned entries in
~/.codex/hooks.json: added when missing, never twice, the user's entries byte for byte (ADR 0029)."""
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


def _present(data: dict, event: str, sub: str) -> bool:
    rx = re.compile(rf"(?:^|[\s/\\\"'])serena-hooks(?:\.exe)?[\"']?\s+{re.escape(sub)}\b.*--client[= ]codex")
    for ev in ALSO.get(sub, (event,)):
        for group in data.get("hooks", {}).get(ev, []) or []:
            for hook in (group.get("hooks", []) if isinstance(group, dict) else []):
                if isinstance(hook, dict) and isinstance(hook.get("command"), str) and rx.search(hook["command"]):
                    return True
    return False


def _record() -> dict:
    from . import codex
    return codex.read_record()


def apply(bk, dry_run: bool = False) -> list[str]:
    from . import codex
    p = path()
    old = p.read_text(encoding="utf-8") if p.exists() else ""
    try:
        data = json.loads(old) if old.strip() else {}
    except ValueError as exc:
        return [f"skipped {p}: it is not valid JSON ({exc}); fix it, then run loadout bootstrap"]
    if not isinstance(data, dict) or not isinstance(data.get("hooks", {}), dict):
        return [f"skipped {p}: it has no hooks object; nothing written"]
    record = _record()
    owned = [o for o in record.get("hooks", []) if isinstance(o, dict)]
    wanted = SERENA_HOOKS if runner.have("serena-hooks") else ()
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
        events.setdefault(e, []).append(group)
        kept.append({"event": e, "group": _canon(group)})
        changed = True
    for ev in [ev for ev, groups in events.items() if groups == []]:
        if not any(ev == o.get("event") for o in owned):
            continue
        del events[ev]
    new = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    new_record = {**record, "hooks": kept}
    if not new_record["hooks"]:
        new_record.pop("hooks")
    if not changed:
        if new_record != record and not dry_run:
            save_json(codex.record_path(), new_record)
        return []
    if old and json.dumps(json.loads(old), indent=2, ensure_ascii=False) + "\n" != old:
        snippet = ", ".join(f"{e}: serena-hooks {s} --client=codex" for e, _, s, _ in missing)
        return [f"{p}: Serena hooks missing, add these yourself (loadout does not rewrite a file in another format): "
                f"{snippet}" if missing else f"{p}: loadout's old Serena hooks are still in it; remove them yourself"]
    if dry_run:
        return [f"{p}: Serena hooks pending"]
    if p.exists() and not record.get("hooks"):
        bk.save_copy(p, "Codex hooks.json before loadout's first change")
    elif not p.exists():
        bk.record_created(p, "created Codex hooks.json")
    p.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(p, new)
    codex.record_path().parent.mkdir(parents=True, exist_ok=True)
    save_json(codex.record_path(), new_record)
    added = [s for _, _, s, _ in missing]
    return [f"hooks.json: added Serena's hooks ({', '.join(added)}); approve them in Codex: /hooks"] if added else \
           ["hooks.json: removed loadout's Serena hooks"]
