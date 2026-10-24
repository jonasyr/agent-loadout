"""Inventory of a machine's Claude Code setup and its classification against the catalog."""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace

from . import catalog, paths, runner, settings_merge, versions
from .jsonio import get_dict, load_json


@dataclass(frozen=True)
class Item:
    kind: str          # mcp | plugin | marketplace | skill | hook | binary | claude-md | installer
    name: str
    detail: str = ""
    location: str = ""
    extra: dict = field(default_factory=dict, compare=False, hash=False)


@dataclass
class Verdict:
    item: Item
    action: str        # remove | migrate | scope-down | update | install | review | own | keep
    reason: str
    entry_id: str = ""


def _mcp_items() -> list[Item]:
    items = []
    sources = [(paths.claude_json(), "~/.claude.json"), (paths.claude_home() / ".mcp.json", "~/.claude/.mcp.json")]
    for path, label in sources:
        servers = load_json(path).get("mcpServers")
        for name, cfg in (servers if isinstance(servers, dict) else {}).items():
            if not isinstance(cfg, dict):
                continue
            args = cfg.get("args")
            args = [str(a) for a in args if isinstance(a, str)] if isinstance(args, list) else []
            detail = " ".join([str(cfg.get("command") or ""), *args, str(cfg.get("url") or "")]).strip()
            items.append(Item("mcp", name, detail, label, {"config": cfg}))
    return items


def _plugin_items() -> list[Item]:
    installed = load_json(paths.claude_home() / "plugins" / "installed_plugins.json").get("plugins")
    out = []
    for pid, entries in (installed if isinstance(installed, dict) else {}).items():
        entries = [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []
        if any(e.get("scope") == "user" for e in entries):
            out.append(Item("plugin", pid, str(entries[0].get("version", "")), "user", {}))
    return out


def _marketplace_items() -> list[Item]:
    known = load_json(paths.claude_home() / "plugins" / "known_marketplaces.json")
    out = []
    for name, cfg in known.items():
        if not isinstance(cfg, dict):
            continue
        src = cfg.get("source") if isinstance(cfg.get("source"), dict) else {}
        out.append(Item("marketplace", name, str(src.get("repo") or src.get("url", "")), "user", {"source": src}))
    return out


def _skill_items() -> list[Item]:
    root = paths.claude_home() / "skills"
    if not root.exists():
        return []
    out = []
    for entry in sorted(root.iterdir()):
        if entry.name == "synced":
            continue
        target = os.readlink(entry) if entry.is_symlink() else str(entry)
        out.append(Item("skill", entry.name, str(target), str(entry), {}))
    return out


def _hook_items() -> list[Item]:
    hooks = load_json(paths.claude_home() / "settings.json").get("hooks")
    out = []
    for event, groups in (hooks if isinstance(hooks, dict) else {}).items():
        for gi, group in enumerate(groups if isinstance(groups, list) else []):
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                continue
            for hi, hook in enumerate(group["hooks"]):
                if not isinstance(hook, dict):
                    continue
                extra = {"event": event, "group": gi, "hook": hi}  # a null matcher is named like a missing one
                if "args" in hook:  # an exec-form hook: its identity is its command plus args
                    extra["args"] = hook["args"]
                out.append(Item("hook", f"{event}:{settings_merge.matcher_of(group)}", hook.get("command", ""),
                                "~/.claude/settings.json", extra))
    return out


def _claude_md_items() -> list[Item]:
    path = paths.claude_home() / "CLAUDE.md"
    if path.is_symlink() or not path.exists() or not path.read_text(encoding="utf-8").strip():
        return []
    first = path.read_text(encoding="utf-8").strip().splitlines()[0]
    return [Item("claude-md", "CLAUDE.md", first, str(path), {})]


def _binary_items(with_versions: bool) -> list[Item]:
    out = []
    for entry in catalog.binaries():
        name = entry["id"]
        if not runner.have(name):
            if not entry.get("helper"):  # a helper (mise) is installed only when another tool needs it
                out.append(Item("binary", name, "missing", "PATH", {"entry": entry, "state": "missing"}))
            continue
        if not with_versions or entry.get("helper"):  # helpers (mise) only install other tools
            out.append(Item("binary", name, "installed", "PATH", {"entry": entry, "state": "ok"}))
            continue
        local = versions.local_version(entry)
        latest = versions.latest_version(entry)
        state = "outdated" if local and latest and latest > local else "ok"
        detail = f"{versions.fmt(local)} -> {versions.fmt(latest)}" if state == "outdated" else versions.fmt(local)
        out.append(Item("binary", name, detail, "PATH", {"entry": entry, "state": state}))
    return out


def _codex_items() -> list[Item]:
    from . import codex, targets
    if not targets.codex_enabled():
        return []
    items = []
    claude = get_dict(load_json(paths.claude_json()), "mcpServers") if targets.claude_enabled() else {}
    skip = codex._plugin_servers() | set(claude)
    for name, table in codex.user_servers().items():
        if name in skip or codex.is_serena(table) or (name != codex.CBM_NAME and codex.is_cbm(table)):  # the kit's tools, however set up (cbm: classify)
            continue
        try:
            cfg, problem = codex.to_claude(name, table), ""
        except codex.Refused as exc:
            cfg, problem = None, str(exc)
        args = table.get("args") if isinstance(table.get("args"), list) else []  # odd shapes are refused above
        detail = " ".join([str(table.get("command") or ""), *map(str, args), str(table.get("url") or "")]).strip()
        items.append(Item("mcp", name, detail, codex.CONFIG_LOCATION, {"config": cfg, "problem": problem}))
    for path in codex.codex_only_skills():
        target = os.readlink(path) if path.is_symlink() else str(path)
        items.append(Item("skill", path.name, str(target), str(path), {}))
    return items


def _installer_items() -> list[Item]:
    """The removable files codebase-memory-mcp's installer wrote (cbm_installer.find gates each agent). Its Claude
    Code settings hooks are hook items already (the catalog's hook-codebase-memory), so they are not repeated."""
    from . import cbm_installer
    return [cbm_installer.adopt_item(a) for a in cbm_installer.find() if a.removable and a.kind != "claude-hook"]


def collect(with_versions: bool = True) -> list[Item]:
    from . import targets
    claude = [*_mcp_items(), *_plugin_items(), *_marketplace_items(), *_skill_items(), *_hook_items(),
              *_claude_md_items()] if targets.claude_enabled() else []  # Codex only: Claude Code's files stay as they are
    return [*claude, *_codex_items(), *_installer_items(), *_binary_items(with_versions)]


def _why(entry: dict) -> str:
    return entry["reason"] + (f" Replacement: {entry['by']}." if entry.get("by") else "")


INSTALLER_REASON = "Written by codebase-memory-mcp install; loadout's plugin provides the same."
BUNDLED_CLAUDE = ("a claude on PATH for the terminal (VS Code's Claude Code extension's claude runs loadout's "
                  "commands now)")


def classify(items: list[Item]) -> list[Verdict]:
    from . import codex, own

    kit = load_json(paths.kit_root() / "settings.base.json")
    kit_plugins = {p for p, on in get_dict(kit, "enabledPlugins").items() if on}
    from . import profiles
    kit_markets = set(profiles.kit_marketplaces()) | {"claude-plugins-official"}  # a profile's too (ADR 0037)
    index = own.personal_index()
    left = own.decisions()
    out = []
    for item in items:
        if item.kind == "binary":
            entry, state = item.extra["entry"], item.extra["state"]
            if state == "missing" and item.name == "claude" and runner._fallback("claude"):
                # VS Code's Claude Code extension's claude runs loadout's commands: one on PATH is optional
                out.append(Verdict(replace(item, detail="optional"), "keep", BUNDLED_CLAUDE, entry["id"]))
            elif state == "missing":
                action = "install" if entry.get("required") or entry["status"] == "recommended" else "keep"
                out.append(Verdict(item, action, entry["reason"], entry["id"]))
            elif state == "outdated":
                out.append(Verdict(item, "update", entry["reason"], entry["id"]))
            else:
                out.append(Verdict(item, "keep", entry["reason"], entry["id"]))
            continue
        if item.kind == "installer":
            out.append(Verdict(item, "keep", own.LEFT_REASON) if own.decided(left, item) == "leave"
                       else Verdict(item, "migrate", INSTALLER_REASON, "mcp-codebase-memory"))
            continue
        if item.kind == "claude-md":
            out.append(Verdict(item, "review", "Global CLAUDE.md content can move into your personal layer (rules/personal/me.md)."))
            continue
        if item.kind == "plugin" and item.name in kit_plugins:
            out.append(Verdict(item, "keep", "Enabled by the kit."))
            continue
        if item.kind == "marketplace" and item.name in kit_markets:
            out.append(Verdict(item, "keep", "Declared by the kit."))
            continue
        personal = own.in_personal_layer(item, index)
        if personal:
            out.append(Verdict(item, "keep", personal))
            continue
        if own.decided(left, item) == "leave":
            out.append(Verdict(item, "keep", own.LEFT_REASON))
            continue
        if own.is_codex(item):
            out.append(Verdict(item, "own", own.own_reason(item)))
            continue
        cfg = item.extra.get("config") if item.kind == "mcp" else None
        if isinstance(cfg, dict) and codex.is_cbm(cfg):  # by its command, whatever its name (ADR 0041)
            if codex.cbm_has_own_settings(cfg, path_counts=False):  # removing it could change which index you use
                out.append(Verdict(item, "keep", CBM_OWN_CLAUDE, "mcp-codebase-memory"))
            else:
                entry = catalog.match("mcp", "codebase-memory-mcp") or {"reason": ""}
                out.append(Verdict(item, "migrate", f"Provided by loadout; this copy duplicates it. {entry['reason']}",
                                   "mcp-codebase-memory"))
            continue
        entry = catalog.match(item.kind, item.name, item.detail)
        if item.kind == "hook" and entry is None:
            from . import cbm_installer  # the installer's hooks by what they run (`.exe`, quoted, its script path)
            entry = catalog.by_id("hook-codebase-memory") if cbm_installer.is_installer_hook(item) else None
        if entry is None:
            out.append(Verdict(item, "own", own.own_reason(item)))
            continue
        status = entry["status"]
        if status == "core":
            action = "keep" if item.kind in ("plugin", "marketplace") else "migrate"
            reason = entry["reason"] if action == "keep" else f"Provided by loadout; this copy duplicates it. {entry['reason']}"
        elif status == "profile":
            action, reason = "scope-down", f"{entry['reason']} (`loadout profile {entry['profile']}` in the repos that need it)"
        elif status in ("superseded", "deprecated"):
            action, reason = "remove", _why(entry)
        elif status == "review":
            action, reason = "review", entry["reason"]
        else:
            action, reason = "keep", _why(entry)
        out.append(Verdict(item, action, reason, entry["id"]))
    return out + _codex_cbm_verdicts(left)


CBM_PROVIDED = "Provided by loadout's Codex plugin; this table starts a second codebase-memory server."
CBM_OWN_CLAUDE = ("It starts codebase-memory with settings of its own (env or args); remove it yourself if "
                  "loadout's plugin should serve it.")
CBM_ONLY = ("Codex's only codebase-memory server here: loadout's plugin does not serve it (not installed, or "
            "switched off); keep it, or turn the plugin on first.")
CBM_OWN = ("It starts codebase-memory with settings of its own (env, args or a fixed path); remove it yourself if "
           "loadout's plugin should serve it.")


def _codex_cbm_verdicts(left: dict) -> list[Verdict]:
    """A user's Codex table that starts codebase-memory under another name: never offered for Claude Code (so no
    item in collect), but adopt may remove it, after a yes, unless it carries settings of its own."""
    from . import codex, own, targets
    if not targets.codex_enabled():
        return []
    out = []
    claude = get_dict(load_json(paths.claude_json()), "mcpServers") if targets.claude_enabled() else {}
    served = None  # asked only when a table needs it: `codex plugin list` runs once, never on a machine without one
    for name, table in codex.user_cbm().items():
        if name == codex.CBM_NAME or name in claude:  # the plugin's name keeps its usual handling; Claude's copy rules
            continue
        if table.get("enabled") is False:  # switched off: it starts nothing, so it is no second server
            continue
        item = Item("mcp", name, " ".join([str(table.get("command") or ""), *map(str, table.get("args") or [])]).strip(),
                    codex.CONFIG_LOCATION, {"config": None, "problem": "", "cbm": True})
        if own.decided(left, item) == "leave":
            out.append(Verdict(item, "keep", own.LEFT_REASON))
        elif not (served := codex.plugin_serves_cbm() if served is None else served):  # it would leave Codex without one
            out.append(Verdict(item, "keep", CBM_ONLY, "mcp-codebase-memory"))
        elif codex.cbm_has_own_settings(table):
            out.append(Verdict(item, "keep", CBM_OWN, "mcp-codebase-memory"))
        else:
            out.append(Verdict(item, "migrate", CBM_PROVIDED, "mcp-codebase-memory"))
    return out
