"""Inventory of a machine's Claude Code setup and its classification against the catalog."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from . import catalog, paths, runner, versions
from .jsonio import load_json


@dataclass(frozen=True)
class Item:
    kind: str          # mcp | plugin | marketplace | skill | hook | binary | claude-md
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
                out.append(Item("hook", f"{event}:{group.get('matcher', '')}", hook.get("command", ""),
                                "~/.claude/settings.json", {"event": event, "group": gi, "hook": hi}))
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
            out.append(Item("binary", name, "missing", "PATH", {"entry": entry, "state": "missing"}))
            continue
        if not with_versions:
            out.append(Item("binary", name, "installed", "PATH", {"entry": entry, "state": "ok"}))
            continue
        local = versions.local_version(entry)
        latest = versions.latest_version(entry)
        state = "outdated" if local and latest and latest > local else "ok"
        detail = f"{versions.fmt(local)} -> {versions.fmt(latest)}" if state == "outdated" else versions.fmt(local)
        out.append(Item("binary", name, detail, "PATH", {"entry": entry, "state": state}))
    return out


def collect(with_versions: bool = True) -> list[Item]:
    return [*_mcp_items(), *_plugin_items(), *_marketplace_items(), *_skill_items(),
            *_hook_items(), *_claude_md_items(), *_binary_items(with_versions)]


def _why(entry: dict) -> str:
    return entry["reason"] + (f" Replacement: {entry['by']}." if entry.get("by") else "")


def classify(items: list[Item]) -> list[Verdict]:
    from . import own

    kit = load_json(paths.kit_root() / "settings.base.json")
    kit_plugins = {p for p, on in kit.get("enabledPlugins", {}).items() if on}
    kit_markets = set(kit.get("extraKnownMarketplaces", {})) | {"claude-plugins-official"}
    index = own.personal_index()
    left = own.decisions()
    out = []
    for item in items:
        if item.kind == "binary":
            entry, state = item.extra["entry"], item.extra["state"]
            if state == "missing":
                action = "install" if entry.get("required") or entry["status"] == "recommended" else "keep"
                out.append(Verdict(item, action, entry["reason"], entry["id"]))
            elif state == "outdated":
                out.append(Verdict(item, "update", entry["reason"], entry["id"]))
            else:
                out.append(Verdict(item, "keep", entry["reason"], entry["id"]))
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
        if left.get(own.decision_key(item)) == "leave":
            out.append(Verdict(item, "keep", own.LEFT_REASON))
            continue
        entry = catalog.match(item.kind, item.name, item.detail)
        if entry is None:
            out.append(Verdict(item, "own", own.OWN_REASON))
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
    return out
