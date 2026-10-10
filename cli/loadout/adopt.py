"""`loadout adopt`: migrate an existing machine onto the kit (spec §6.2)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

from . import catalog, inventory, own, paths, pkgmgr, runner, secrets, ui
from .backup import Backup
from .inventory import Verdict
from .jsonio import InvalidJSON, load_json, save_json
from .secrets import redact

GROUP_ORDER = ["remove", "migrate", "scope-down", "update", "install", "review", "own", "keep"]
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
    "own": "not managed by loadout; they stay only on this machine unless you choose.",
    "keep": "nothing to do.",
}
VERB = {"remove": "remove", "migrate": "remove", "scope-down": "disable globally", "update": "update",
        "install": "install", "review": "remove", "own": "remove"}
MIGRATED_MARKER = "<!-- Global instructions live in"
Ask = Callable[[str], str]


def prefill_settings() -> dict:
    """The user's own values in ~/.claude/settings.json (minus what the kit applied), used to prefill
    the preference questions so existing values (effortLevel, attribution, autoMode, ...) stay as they are."""
    from .settings_merge import get_path, leaves

    try:
        current = load_json(paths.claude_home() / "settings.json")
        applied = load_json(paths.state_dir() / "managed-settings.json")
    except InvalidJSON:
        return {}
    own = json.loads(json.dumps(current))
    for path, value in leaves(applied):
        if get_path(own, path) == value:
            node = own
            for key in path[:-1]:
                node = node[key]
            del node[path[-1]]
    return own


def _verb(v: Verdict) -> str:
    return "move into your personal layer:" if v.item.kind == "claude-md" else VERB[v.action]


def render_plan(verdicts: list[Verdict], findings: list) -> str:
    lines = []
    for group in GROUP_ORDER:
        members = [v for v in verdicts if v.action == group]
        if not members:
            continue
        title = "YOUR OWN TOOLS" if group == "own" else group.upper()
        lines.append(f"\n{title} ({len(members)}) — {GROUP_HELP[group]}")
        if any(v.item.kind == "claude-md" for v in members):
            lines.append("  (CLAUDE.md: picking moves its content into your personal layer instead; restorable.)")
        if group == "keep":
            bins = [v for v in members if v.item.kind == "binary"]
            if bins:
                lines.append("  binaries: " + ", ".join(f"{v.item.name} {v.item.detail}".rstrip() for v in bins))
            members = [v for v in members if v.item.kind != "binary"]
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


def select(verdicts: list[Verdict], groups: set[str] | None, skip: set[str], ask: Ask,
           keep_global: list | None = None) -> list[Verdict]:
    if groups is not None:
        valid = set(GROUP_ORDER) - {"keep", "own"}
        if "own" in groups:
            raise ValueError("group 'own': decide per item with --own NAME=CHOICE,... (see loadout configure own)")
        for g in sorted(groups - valid):
            raise ValueError(f"unknown group '{g}' (valid: {', '.join(x for x in GROUP_ORDER if x in valid)})")
        return [v for v in verdicts if v.action in groups and v.item.name not in skip]
    chosen = []
    for group in GROUP_ORDER[:-1]:
        if group == "own":
            continue
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
            for v in members:
                keepable = keep_global is not None and group == "scope-down" and v.item.kind == "plugin"
                hint = " [y/N/k=keep global] " if keepable else " [y/N] "
                reply = ask(f"  {_verb(v)} {v.item.kind} {v.item.name}?{hint}").strip().lower()
                if reply in ui.YES:
                    chosen.append(v)
                elif keepable and reply in ("k", "keep"):
                    keep_global.append(v)
    return chosen


def _claude(args: list[str]) -> str:
    res = runner.run(["claude", *args])
    return "ok" if res.ok else f"failed: {res.stderr.strip()}"


def _manual(bk: Backup, title: str, cmds: list[list[str]], undo: list[list[str]] | None = None) -> str:
    bk._ensure_root()
    return runner.write_manual_commands(bk.root, title + " (full commands, contains secrets)", cmds, undo)


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
        where = _manual(bk, f"mcp {v.item.name}: remove", [remove], undo=[undo])
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
    # only the ~/.claude/skills entry: a shared ~/.agents/skills source also serves Codex and other agents
    bk.move(Path(v.item.location), f"skill {v.item.name}")
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
        res = runner.run(cmd, cwd=pkgmgr.run_cwd(cmd), timeout=900)
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


def fix_secrets(findings: list, bk: Backup) -> list[str]:
    from .personal_mcp import replace_user_server

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
        servers = claude_json.get("mcpServers")
        original = servers.get(server) if isinstance(servers, dict) else None
        if original is None:
            out.append(f"{server}: not found in ~/.claude.json, skipped")
            continue
        if any("\n" in f.value or "\r" in f.value for f in group):
            out.append(f"{server}: a secret value contains a newline; move it to secrets.env by hand (skipped)")
            continue
        cfg, lines, names = secrets.rewrite(server, original, group, known)
        secrets.append_env(secrets_path, lines, bk)
        refs = ", ".join("${" + n + "}" for n in names)
        res = replace_user_server(server, original, cfg, bk)
        if res.startswith("manual: "):
            out.append(f"{server} -> {refs}: not changed in claude (Windows .cmd shim cannot take JSON); "
                       f"secrets.env is updated, run the commands in {res[8:]}")
            continue
        out.append(f"{server} -> {refs}: {res}")
    return out


def apply(selected: list[Verdict], bk: Backup, ask: Ask = lambda q: "", confirm_cmds: bool = True) -> list[str]:
    out, moved = [], set()
    selected = [v for v in selected if v.action != "keep"]  # keep never acts, whatever was passed in
    for v in selected:
        kind = v.item.kind
        n = len(out)
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
        entry = catalog.by_id(v.entry_id) if v.action == "scope-down" else None
        if entry and entry.get("profile") and len(out) > n:
            out[-1] += f" (enable it per project: loadout profile {entry['profile']})"
    out += _apply_hooks([v for v in selected if v.item.kind == "hook"], bk)
    return out


def run(apply_changes: bool, groups: set | None, skip: set, yes: bool, ask: Ask, with_versions: bool = True,
        interactive: bool | None = None, own_spec: str | None = None) -> int:
    import sys

    if interactive is None:
        interactive = ui.is_interactive()
    verdicts = inventory.classify(inventory.collect(with_versions=with_versions))
    findings = secrets.scan_all()
    try:
        own_pairs = own.resolve(own.parse_spec(own_spec), verdicts) if own_spec is not None else None
    except ValueError as exc:
        print(f"loadout: {exc}", file=sys.stderr)
        return 2
    print(render_plan(verdicts, findings))
    if not apply_changes:
        print("\n(dry run — nothing changed. Re-run with --apply to choose and apply.)")
        return 0
    if not interactive and not yes and groups is None and own_pairs is None:
        print("\nnon-interactive: re-run with --yes, --groups GROUP,... or --own NAME=CHOICE,... to apply (nothing changed).")
        return 2
    explicit = groups is not None
    keep_global: list = []
    if own_pairs is not None and not interactive and not yes and not explicit:
        chosen = []  # --own alone: only the named items
    else:
        chosen = select(verdicts, groups if explicit else (DEFAULT_ALL if yes else None), skip, ask,
                        keep_global=keep_global if interactive and not yes else None)
    if own_pairs is None:
        own_pairs = (own.ask_choices([v for v in own.unmanaged(verdicts) if v.item.name not in skip], ask)
                     if interactive and not yes else [])
    own_pairs = own_pairs + [(v, own.Choice("global")) for v in keep_global]
    acting = [p for p in own_pairs if p[1].action != "leave"]
    if (chosen or acting) and interactive and not yes:
        if not ui.confirm(ask, f"Apply {len(chosen) + len(acting)} change(s)? [y/N] "):
            print("nothing changed")
            return 0
    elif not chosen and not own_pairs and not findings:
        print("nothing selected")
        return 0
    bk = Backup(description="adopt")
    try:
        lines, new_profiles = apply_own(own_pairs, bk, chosen, ask if interactive else (lambda q: ""),
                                        confirm_cmds=not (yes and explicit))
        for line in lines:
            print(redact(line))
        done = {v.item.name for v in chosen if v.item.kind == "mcp"} | {v.item.name for v, c in acting if v.item.kind == "mcp"}
        remaining = [f for f in findings if f.fixable and f.server not in done]
        if remaining and (yes or (interactive and ui.confirm(ask, "move detected plaintext secrets to secrets.env? [y/N] "))):
            for line in fix_secrets(remaining, bk):
                print(redact(line))
        if interactive and own_spec is None:
            _offer_profiles(new_profiles, ask)
        if acting and interactive and own_spec is None:
            from .configure import offer_commit
            offer_commit(ask)
    finally:
        if not bk.empty:
            print(f"\nbackup: {bk.root}  (undo: loadout restore {bk.root}; it holds old configs, keep it private)")
    return 0


def _offer_profiles(new_profiles: dict, ask: Ask) -> None:
    from . import project

    if new_profiles:
        print("\n(applying writes the repo's committed .claude/settings.json / .mcp.json "
              "and is not undone by loadout restore)")
    for name, items in new_profiles.items():
        found = sorted({repo for item in items for repo in own.candidate_repos(item)})
        print(f"\nprofile {name} is in your personal layer. Apply it to repos now?")
        if found:
            print("  detected: " + ", ".join(str(r) for r in found))
            answer = ask("  apply to these repos? [y/N/paths]: ").strip()
            if answer.lower() in ("", "n", "no"):
                repos = []
            elif answer.lower() in ("y", "yes"):
                repos = found
            else:
                repos = [Path(a.strip()).expanduser() for a in answer.split(",") if a.strip()]
        else:
            answer = ask("  repos (comma-separated paths; Enter: none): ").strip()
            repos = [Path(a.strip()).expanduser() for a in answer.split(",") if a.strip()]
        for repo in repos:
            if not repo.is_dir():
                print(f"  {repo.resolve()}: not a folder, skipped")
                continue
            try:
                project.add_profile(repo, name)
                print(f"  {repo.resolve()}: profile {name} applied")
            except (OSError, InvalidJSON, ValueError) as exc:
                print(redact(f"  {repo.resolve()}: failed: {exc}"))


def apply_own(pairs: list, bk: Backup, others: list[Verdict] = (), ask: Ask = lambda q: "",
              confirm_cmds: bool = True) -> tuple[list[str], dict]:
    """Record own-tool choices, run every removal (others + converted choices), then the deferred
    machine steps (content-based, so earlier index-based hook removals cannot shift them).
    An item in both `pairs` and `others` is acted on once, by its own choice. One item's I/O error is
    reported as a 'failed:' line and does not stop the others."""
    from . import link, settings_merge

    mine = {own.decision_key(v.item) for v, _ in pairs}
    out, machine, recorded_profiles, personal_changed = [], [], {}, False
    removals = [v for v in others if own.decision_key(v.item) not in mine]
    backed_up = False

    def fail(v, exc):
        out.append(redact(f"{v.item.kind} {v.item.name}: failed: {exc}"))

    def backup_decisions():
        nonlocal backed_up
        if not backed_up:
            own.backup_decisions(bk)
            backed_up = True

    for v, choice in pairs:
        if choice.action == "leave":
            try:
                backup_decisions()
                own.remember_leave(v.item)
            except (OSError, InvalidJSON) as exc:
                fail(v, exc)
                continue
            out.append(f"{v.item.kind} {v.item.name}: left on this machine (not asked again; loadout configure own --all)")
            continue
        if choice.action == "remove":
            try:
                backup_decisions()
                own.forget(v.item)
            except (OSError, InvalidJSON) as exc:
                fail(v, exc)
                continue
            removals.append(Verdict(v.item, "remove", v.reason))
            continue
        try:
            rec = own.record_global(v, bk) if choice.action == "global" else own.record_project(v, choice.profile, bk)
        except (OSError, InvalidJSON) as exc:
            fail(v, exc)
            continue
        out += rec.lines
        if not rec.ok:
            continue
        try:
            backup_decisions()
            own.forget(v.item)
        except (OSError, InvalidJSON) as exc:
            fail(v, exc)
        personal_changed = True
        if rec.machine:
            machine.append((v, rec.machine))
        if choice.action == "project":
            recorded_profiles.setdefault(choice.profile, []).append(v.item)
            removals.append(Verdict(v.item, "scope-down" if v.item.kind == "plugin" else "remove", v.reason))
            out.append(f"{v.item.kind} {v.item.name}: enable it per project with `loadout profile {choice.profile}`")
    if removals:
        out += apply(removals, bk, ask, confirm_cmds)
    for v, step in machine:
        try:
            out += step()
        except (OSError, InvalidJSON) as exc:
            fail(v, exc)
    if personal_changed:
        try:
            out += link.link_all(bk)
            settings_path = paths.claude_home() / "settings.json"
            if settings_path.exists() and settings_merge.would_change():
                bk.save_copy(settings_path, "settings.json before loadout merge")
            settings_merge.backup_snapshot(bk)
            settings_merge.apply_settings()
        except (OSError, InvalidJSON) as exc:
            out.append(redact(f"settings: failed: {exc}"))
    return out, recorded_profiles
