"""`loadout adopt`: migrate an existing machine onto the kit (spec §6.2)."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Callable

from . import catalog, inventory, paths, pkgmgr, runner, secrets, ui
from .backup import Backup
from .inventory import Verdict
from .jsonio import load_json, save_json
from .secrets import redact

GROUP_ORDER = ["remove", "migrate", "scope-down", "update", "install", "review", "unknown", "keep"]
# Selected by Enter at the prompt and by --yes. Binary update/install never are: they need
# --groups update/install or an interactive pick, and each command is shown and confirmed.
DEFAULT_ALL = {"remove", "migrate", "scope-down"}
GROUP_HELP = {
    "remove": "uninstall/remove; restorable.",
    "migrate": "remove your copy, because the loadout plugin provides it.",
    "scope-down": "disable globally; enable per project with `loadout profile X`.",
    "update": "run the tool's update command (each command is shown and confirmed first).",
    "install": "run the tool's install command (each command is shown and confirmed first).",
    "review": "picking removes it; restorable.",
    "unknown": "picking removes it; restorable.",
    "keep": "nothing to do.",
}
VERB = {"remove": "remove", "migrate": "remove", "scope-down": "disable globally", "update": "update",
        "install": "install", "review": "remove", "unknown": "remove"}
MIGRATED_MARKER = "<!-- Global instructions live in"
Ask = Callable[[str], str]


def _verb(v: Verdict) -> str:
    return "move into your personal layer:" if v.item.kind == "claude-md" else VERB[v.action]


def render_plan(verdicts: list[Verdict], findings: list) -> str:
    lines = []
    for group in GROUP_ORDER:
        members = [v for v in verdicts if v.action == group]
        if not members:
            continue
        lines.append(f"\n{group.upper()} ({len(members)}) — {GROUP_HELP[group]}")
        if any(v.item.kind == "claude-md" for v in members):
            lines.append("  (CLAUDE.md: picking moves its content into your personal layer instead; restorable.)")
        for v in members:
            lines.append(redact(f"  [{v.item.kind}] {v.item.name}  {v.item.detail}".rstrip()))
            lines.append(redact(f"      {v.reason}"))
            if v.item.kind == "marketplace" and group != "keep":
                lines.append("      note: plugins from a removed marketplace stay installed unless picked too.")
    if findings:
        lines.append("\nPLAINTEXT SECRETS (values hidden)")
        for f in findings:
            how = "can move to secrets.env" if f.fixable else "report only: move it to secrets.env by hand"
            lines.append(f"  {f.server}.{f.field}.{f.key} ({f.location}) — {how}")
    return "\n".join(lines)


def select(verdicts: list[Verdict], groups: set[str] | None, skip: set[str], ask: Ask) -> list[Verdict]:
    if groups is not None:
        valid = set(GROUP_ORDER) - {"keep"}
        for g in sorted(groups - valid):
            raise ValueError(f"unknown group '{g}' (valid: {', '.join(x for x in GROUP_ORDER if x in valid)})")
        return [v for v in verdicts if v.action in groups and v.item.name not in skip]
    chosen = []
    for group in GROUP_ORDER[:-1]:
        members = [v for v in verdicts if v.action == group and v.item.name not in skip]
        if not members:
            continue
        default = "a" if group in DEFAULT_ALL else "n"
        question = (f"{group}: {len(members)} item(s) — {GROUP_HELP[group]} "
                    f"[a]ll / [n]one / [p]ick (default {'all' if default == 'a' else 'none'}): ")
        answer = ui.choose_group(ask, question, default)
        if answer == "a":
            chosen += members
        elif answer == "p":
            chosen += [v for v in members if ui.confirm(ask, f"  {_verb(v)} {v.item.kind} {v.item.name}? [y/N] ")]
    return chosen


def _claude(args: list[str]) -> str:
    res = runner.run(["claude", *args])
    return "ok" if res.ok else f"failed: {res.stderr.strip()}"


def _manual(bk: Backup, title: str, cmds: list[list[str]]) -> str:
    bk._ensure_root()
    return runner.write_manual_commands(bk.root, title + " (full commands, contains secrets)", cmds)


def _apply_mcp(v: Verdict, bk: Backup, moved: set, selected: list[Verdict]) -> str:
    if v.item.location == "~/.claude/.mcp.json":
        path = paths.claude_home() / ".mcp.json"
        if str(path) in moved or not path.exists():
            return f"mcp {v.item.name}: {path} already handled"
        moved.add(str(path))
        chosen = {x.item.name for x in selected if x.item.kind == "mcp" and x.item.location == v.item.location}
        data = load_json(path)
        servers = data.get("mcpServers", {})
        if set(servers) <= chosen:
            bk.move(path, f"moved {path}")
            return f"moved {path} to backup"
        bk.save_copy(path, f"{path} before removing servers")
        data["mcpServers"] = {k: c for k, c in servers.items() if k not in chosen}
        save_json(path, data)
        return f"removed {sorted(chosen & set(servers))} from {path}"
    cfg = json.dumps(v.item.extra.get("config", {}))
    undo = ["claude", "mcp", "add-json", "-s", "user", v.item.name, cfg]
    remove = ["claude", "mcp", "remove", "-s", "user", v.item.name]
    if runner.would_refuse(undo):  # the undo could not be replayed: do not remove
        where = _manual(bk, f"mcp {v.item.name}: remove (undo: add-json below)", [remove, undo])
        return f"mcp {v.item.name}: not removed, its undo cannot run through this claude (Windows .cmd shim); commands are in {where}"
    bk.record_command(f"mcp {v.item.name}", undo)
    return f"mcp {v.item.name}: " + _claude(["mcp", "remove", "-s", "user", v.item.name])


def _apply_plugin(v: Verdict, bk: Backup) -> str:
    if v.action == "scope-down":
        bk.record_command(f"plugin {v.item.name}", ["claude", "plugin", "enable", v.item.name, "--scope", "user"])
        return f"plugin {v.item.name} disabled globally: " + _claude(["plugin", "disable", v.item.name, "--scope", "user"])
    bk.record_command(f"plugin {v.item.name}", ["claude", "plugin", "install", v.item.name, "--scope", "user"])
    # --keep-data: the plugin's ~/.claude/plugins/data/<id>/ survives, so the undo (reinstall) is complete
    return f"plugin {v.item.name} uninstalled: " + _claude(["plugin", "uninstall", v.item.name, "--scope", "user", "--keep-data"])


def _apply_marketplace(v: Verdict, bk: Backup) -> str:
    src = v.item.extra.get("source", {})
    origin = src.get("repo") or src.get("url") or src.get("path")
    if not origin:
        return f"marketplace {v.item.name}: skipped (no source to restore from)"
    bk.record_command(f"marketplace {v.item.name}", ["claude", "plugin", "marketplace", "add", origin], source=src)
    extra = {k: val for k, val in src.items() if k not in ("source", "repo", "url", "path")}
    note = f" (restore re-adds {origin}; also recorded: {json.dumps(extra)})" if extra else ""
    return f"marketplace {v.item.name}: " + _claude(["plugin", "marketplace", "remove", v.item.name]) + note


def _apply_skill(v: Verdict, bk: Backup) -> str:
    link = Path(v.item.location)
    target = None
    if link.is_symlink():
        resolved = Path(os.path.normpath(link.parent / os.readlink(link)))
        if "/.agents/skills/" in resolved.as_posix() and resolved.exists():
            target = resolved
    bk.move(link, f"skill {v.item.name}")
    if target is not None:
        bk.move(target, f"skill source {target}")
    return f"skill {v.item.name} moved to backup"


def _apply_hooks(hook_verdicts: list[Verdict], bk: Backup) -> list[str]:
    if not hook_verdicts:
        return []
    path = paths.claude_home() / "settings.json"
    bk.save_copy(path, "settings.json before hook removal")
    data = load_json(path)
    drop = {(v.item.extra["event"], v.item.extra["group"], v.item.extra["hook"]) for v in hook_verdicts}
    hooks = data.get("hooks", {})
    for event in list(hooks):
        if not isinstance(hooks[event], list):
            continue
        new_groups = []
        for gi, group in enumerate(hooks[event]):
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                new_groups.append(group)  # malformed: not ours to fix, keep as-is
                continue
            kept = [h for hi, h in enumerate(group.get("hooks", [])) if (event, gi, hi) not in drop]
            if kept:
                new_groups.append({**group, "hooks": kept})
        if new_groups:
            hooks[event] = new_groups
        else:
            del hooks[event]
    if not hooks:
        data.pop("hooks", None)
    save_json(path, data)
    return [f"hook {v.item.name}: removed ({v.item.detail[:60]})" for v in hook_verdicts]


def _apply_binary(v: Verdict, ask: Ask, confirm_cmds: bool) -> str:
    key = "install" if v.action == "install" else "update"
    entry = v.item.extra["entry"]
    cmds = pkgmgr.update_plan(entry)[0] if key == "update" else catalog.platform_cmds(entry, key)
    if not cmds:
        return f"{v.item.name}: no {key} command for this platform. {entry.get('manual', '')}".strip()
    print(f"{v.item.name} {key}:")
    for cmd in cmds:
        print("  command: " + " ".join(cmd))
    if confirm_cmds and not ui.confirm(ask, "  run it? [y/N] "):
        return f"{v.item.name} {key}: skipped"
    results = []
    for cmd in cmds:
        res = runner.run(cmd, timeout=900)
        results.append("ok" if res.ok else f"failed: {res.stderr.strip()[:200]}")
    return f"{v.item.name} {key}: " + ", ".join(results)


def migrate_claude_md(bk: Backup) -> list[str]:
    src = paths.claude_home() / "CLAUDE.md"
    if src.is_symlink():
        return ["skipped: ~/.claude/CLAUDE.md is a symlink"]
    if not src.exists():
        return []
    content = src.read_text(encoding="utf-8").strip()
    if not content or content.startswith(MIGRATED_MARKER):
        return ["~/.claude/CLAUDE.md already migrated"]
    me = paths.personal_root() / "rules" / "me.md"
    me.parent.mkdir(parents=True, exist_ok=True)
    content, notes = _rewrite_imports(content, me)
    if me.exists():
        bk.save_copy(me, "personal me.md before migration")
    else:
        bk.record_created(me, "created personal me.md")
    existing = me.read_text(encoding="utf-8") if me.exists() else "# About me\n"
    me.write_text(existing.rstrip() + "\n\n## Migrated from ~/.claude/CLAUDE.md\n\n" + content + "\n", encoding="utf-8")
    bk.save_copy(src, "global CLAUDE.md")
    src.write_text(MIGRATED_MARKER + " ~/.claude/rules/ (loadout). -->\n", encoding="utf-8")
    return [f"moved ~/.claude/CLAUDE.md content into {me}", *notes]


def _rewrite_imports(content: str, me: Path) -> tuple[str, list[str]]:
    """Relative @imports resolved from ~/.claude; after the move they would resolve from the personal layer."""
    lines, notes = [], []
    for line in content.splitlines():
        if line.startswith("@"):
            target = line[1:].strip()
            relative = target and not target.startswith(("/", "~")) and not re.match(r"^[A-Za-z]:[\\/]", target)
            if relative:
                if (paths.claude_home() / target).exists():
                    line = f"@~/.claude/{target}"
                    notes.append(f"rewrote @{target} -> {line}")
                else:
                    notes.append(f"warning: @{target} kept as-is, but ~/.claude/{target} does not exist; "
                                 f"it now resolves from {me.parent}")
        lines.append(line)
    return "\n".join(lines), notes


def _open_secrets_file(path: Path, bk: Backup):
    """Append handle to secrets.env; a new file is created 0600 from the start and recorded as created."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        bk.save_copy(path, "secrets.env before additions")
    else:
        os.close(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
        bk.record_created(path, "created secrets.env")
    if os.name != "nt":
        os.chmod(path, 0o600)
    return path.open("a", encoding="utf-8", newline="\n")


def fix_secrets(findings: list, bk: Backup) -> list[str]:
    out = []
    claude_json = load_json(paths.claude_json())
    secrets_path = paths.secrets_file()
    fixable: dict[str, list] = {}
    for f in findings:
        if f.fixable:
            fixable.setdefault(f.server, []).append(f)
        else:
            out.append(f"{f.server}: secret in {f.field} ({f.location}): move it to secrets.env by hand")
    known = secrets.load_env(secrets_path)
    for server, group in fixable.items():
        original = claude_json.get("mcpServers", {}).get(server)
        if original is None:
            out.append(f"{server}: not found in ~/.claude.json, skipped")
            continue
        if any("\n" in f.value or "\r" in f.value for f in group):
            out.append(f"{server}: a secret value contains a newline; move it to secrets.env by hand (skipped)")
            continue
        cfg = json.loads(json.dumps(original))
        new_lines, names = [], []
        for f in group:
            var = secrets.var_name(f.server, f.key)
            n = 2
            while var in known and known[var] != f.value:  # same name, different value: never overwrite
                var = f"{secrets.var_name(f.server, f.key)}_{n}"
                n += 1
            if var not in known:
                known[var] = f.value
                new_lines.append(f"{var}={secrets.quote(f.value)}\n")
            cfg[f.field][f.key] = cfg[f.field][f.key].replace(f.value, "${" + var + "}")
            names.append(var)
        if new_lines:
            existing = secrets_path.read_bytes() if secrets_path.exists() else b""
            with _open_secrets_file(secrets_path, bk) as fh:
                if existing and not existing.endswith(b"\n"):
                    fh.write("\n")
                fh.writelines(new_lines)
        add_cfg = ["claude", "mcp", "add-json", "-s", "user", server, json.dumps(cfg)]
        if runner.would_refuse(add_cfg):  # nothing is removed: a refused add would lose the user's server
            where = _manual(bk, f"secrets {server}", [["claude", "mcp", "remove", "-s", "user", server], add_cfg])
            out.append(f"{server} -> " + ", ".join("${" + n + "}" for n in names)
                       + f": not changed in claude (Windows .cmd shim cannot take JSON); secrets.env is updated, run the commands in {where}")
            continue
        # reverse replay: remove the ${VAR} server first, then re-add the original
        bk.record_command(f"secrets {server} (original)", ["claude", "mcp", "add-json", "-s", "user", server, json.dumps(original)])
        bk.record_command(f"secrets {server} (remove rewritten)", ["claude", "mcp", "remove", "-s", "user", server])
        _claude(["mcp", "remove", "-s", "user", server])
        res = _claude(["mcp", "add-json", "-s", "user", server, json.dumps(cfg)])
        if res != "ok":
            back = _claude(["mcp", "add-json", "-s", "user", server, json.dumps(original)])  # never leave the server missing
            res += f" (original re-added: {back})"
        out.append(f"{server} -> " + ", ".join("${" + n + "}" for n in names) + ": " + res)
    return out


def apply(selected: list[Verdict], bk: Backup, ask: Ask = lambda q: "", confirm_cmds: bool = True) -> list[str]:
    out, moved = [], set()
    selected = [v for v in selected if v.action != "keep"]  # keep never acts, whatever was passed in
    for v in selected:
        kind = v.item.kind
        if kind == "binary" and v.action not in ("install", "update"):
            out.append(f"binary {v.item.name}: nothing to run for '{v.action}'")
        elif kind == "mcp":
            out.append(_apply_mcp(v, bk, moved, selected))
        elif kind == "plugin":
            out.append(_apply_plugin(v, bk))
        elif kind == "marketplace":
            out.append(_apply_marketplace(v, bk))
        elif kind == "skill":
            out.append(_apply_skill(v, bk))
        elif kind == "binary":
            out.append(_apply_binary(v, ask, confirm_cmds))
        elif kind == "claude-md":
            out += migrate_claude_md(bk)
    out += _apply_hooks([v for v in selected if v.item.kind == "hook"], bk)
    return out


def run(apply_changes: bool, groups: set | None, skip: set, yes: bool, ask: Ask, with_versions: bool = True,
        interactive: bool | None = None) -> int:
    if interactive is None:
        interactive = ui.is_interactive()
    verdicts = inventory.classify(inventory.collect(with_versions=with_versions))
    findings = secrets.scan_all()
    print(render_plan(verdicts, findings))
    if not apply_changes:
        print("\n(dry run — nothing changed. Re-run with --apply to choose and apply.)")
        return 0
    if not interactive and not yes and groups is None:
        print("\nnon-interactive: re-run with --yes or --groups GROUP,... to apply (nothing changed).")
        return 2
    explicit = groups is not None
    chosen = select(verdicts, groups if explicit else (DEFAULT_ALL if yes else None), skip, ask)
    if chosen and interactive and not yes:
        if not ui.confirm(ask, f"Apply {len(chosen)} change(s)? [y/N] "):
            print("nothing changed")
            return 0
    elif not chosen and not findings:
        print("nothing selected")
        return 0
    bk = Backup(description="adopt")
    for line in apply(chosen, bk, ask if interactive else (lambda q: ""), confirm_cmds=not (yes and explicit)):
        print(redact(line))
    remaining = [f for f in findings if f.fixable
                 and f.server not in {v.item.name for v in chosen if v.item.kind == "mcp"}]
    if remaining and (yes or (interactive and ui.confirm(ask, "move detected plaintext secrets to secrets.env? [y/N] "))):
        for line in fix_secrets(remaining, bk):
            print(redact(line))
    if not bk.empty:
        print(f"\nbackup: {bk.root}  (undo: loadout restore {bk.root}; it holds old configs, keep it private)")
    return 0
