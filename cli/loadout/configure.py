"""Configure wizard: defaults stay as the kit ships them; choices go into the personal layer (spec §6.4)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Callable

from . import catalog, paths, profiles, runner, scaffold, ui
from .backup import Backup
from .jsonio import load_json, save_json

Ask = Callable[[str], str]
PREFS = [("effortLevel", "Effort level (low/medium/high)", str),
         ("alwaysThinkingEnabled", "Always use extended thinking (true/false)", None)]


@dataclass
class Addon:
    key: str
    label: str
    category: str
    reason: str
    kind: str        # plugin | mcp
    target: str      # plugin id or catalog id
    default_on: bool


def _personal_settings_path():
    return paths.personal_root() / "settings.json"


def _kit_plugins() -> dict:
    return load_json(paths.kit_root() / "settings.base.json").get("enabledPlugins", {})


def addons() -> list[Addon]:
    out, seen = [], set()
    for pid, on in _kit_plugins().items():
        entry = catalog.match("plugin", pid) or {}
        out.append(Addon(f"plugin:{pid}", pid, entry.get("category", "kit default"), entry.get("reason", "Enabled by the kit."), "plugin", pid, bool(on)))
        seen.add(pid)
    for name in profiles.list_profiles():
        prof = profiles.load_profile(name)
        for pid in prof.install:
            if pid not in seen:
                out.append(Addon(f"plugin:{pid}", pid, f"profile {name}", prof.description, "plugin", pid, False))
                seen.add(pid)
    for entry in catalog.load():
        offer = entry.get("offer")
        if not offer:
            continue
        if "plugin" in offer and offer["plugin"] not in seen:
            out.append(Addon(f"plugin:{offer['plugin']}", offer["plugin"], entry.get("category", "other"), entry["reason"], "plugin", offer["plugin"], False))
            seen.add(offer["plugin"])
        elif "mcp" in offer:
            out.append(Addon(f"mcp:{entry['id']}", ", ".join(offer["mcp"]), entry.get("category", "other"), entry["reason"], "mcp", entry["id"], False))
    return out


def is_on(addon: Addon) -> bool:
    if addon.kind == "plugin":
        personal = load_json(_personal_settings_path()).get("enabledPlugins", {})
        return personal.get(addon.target, addon.default_on)
    entry = next(e for e in catalog.load() if e["id"] == addon.target)
    servers = load_json(paths.personal_root() / "mcp.json").get("mcpServers", {})
    return all(name in servers for name in entry["offer"]["mcp"])


def set_plugin(plugin_id: str, on: bool) -> None:
    data = load_json(_personal_settings_path())
    plugins = data.setdefault("enabledPlugins", {})
    if bool(_kit_plugins().get(plugin_id, False)) == on:
        plugins.pop(plugin_id, None)   # same as the kit default: no override needed
    else:
        plugins[plugin_id] = on
    if not plugins:
        data.pop("enabledPlugins")
    save_json(_personal_settings_path(), data)


SWITCH = {"on": True, "true": True, "yes": True, "off": False, "false": False, "no": False}


def parse_switch(value: str, kind: str = "plugin|mcp") -> bool:
    try:
        return SWITCH[value.strip().lower()]
    except KeyError:
        raise ValueError(f"usage: loadout configure set {kind} <id> on|off (got '{value}')") from None


def _mcp_offer(name: str) -> dict | None:
    """By catalog id (addon-dbhub-global) or by server name (dbhub)."""
    offers = [e for e in catalog.load() if "mcp" in e.get("offer", {})]
    return (next((e for e in offers if e["id"] == name), None)
            or next((e for e in offers if name in e["offer"]["mcp"]), None))


def set_mcp(catalog_id: str, on: bool) -> list[str]:
    entry = _mcp_offer(catalog_id)
    if entry is None:
        names = ", ".join(f"{e['id']} ({', '.join(e['offer']['mcp'])})" for e in catalog.load() if "mcp" in e.get("offer", {}))
        raise ValueError(f"no MCP add-on '{catalog_id}' in the catalog (available: {names})")
    path = paths.personal_root() / "mcp.json"
    data = load_json(path)
    servers = data.setdefault("mcpServers", {})
    for name, cfg in entry["offer"]["mcp"].items():
        if on:
            servers[name] = cfg
        else:
            servers.pop(name, None)
    save_json(path, data)
    return [f"{var} is not set: add it to {paths.secrets_file()}" for var in entry["offer"].get("needs", [])
            if on and not os.environ.get(var)]


def set_pref(key: str, raw_json: str) -> None:
    try:
        value = json.loads(raw_json)
    except json.JSONDecodeError:
        value = raw_json
    data = load_json(_personal_settings_path())
    data[key] = value
    save_json(_personal_settings_path(), data)


def show() -> str:
    lines = ["Change one with: loadout configure set <plugin|mcp> <id> on|off"]
    for a in addons():
        on = is_on(a)
        source = "default" if on == a.default_on else "personal"
        lines.append(f"{'on' if on else 'off'} ({source})  [{a.category}] {a.label}  — id: {a.kind} {a.target}")
    personal = load_json(_personal_settings_path())
    prefs = {k: v for k, v in personal.items() if k not in ("enabledPlugins", "extraKnownMarketplaces")}
    if prefs:
        lines.append("preferences: " + json.dumps(prefs, ensure_ascii=False))
    return "\n".join(lines)


def apply_all(ask: Ask, setup: bool = True) -> None:
    """setup=False: the caller (bootstrap) applies settings, MCP servers and plugins itself afterwards."""
    from . import bootstrap
    from .personal_mcp import apply_mcp
    from .settings_merge import apply_settings

    if setup:
        apply_settings()
        for line in bootstrap.setup_plugins() + apply_mcp():
            print(line)
    root = paths.personal_root()
    if (root / ".git").exists():
        status = runner.run(["git", "-C", str(root), "status", "--porcelain"])
        if status.stdout.strip() and ask("commit and push your personal layer? [y/N] ").strip().lower() == "y":
            runner.run(["git", "-C", str(root), "add", "-A"])
            runner.run(["git", "-C", str(root), "commit", "-m", "chore: update loadout preferences"])
            runner.run(["git", "-C", str(root), "push"])
    if setup:
        print("Restart Claude Code (or run /reload-plugins) to load the changes.")


def _about_you(ask: Ask, bk: Backup) -> None:
    me = paths.personal_root() / "rules" / "me.md"
    if me.exists():
        if not ui.confirm(ask, f"{me} already exists. Replace it with a new one? (the current one is backed up) [y/N] "):
            print(f"kept {me}")
            return
    values = {
        "NAME": ask("Your name: ").strip() or "me",
        "ROLE": ask("Your role (e.g. backend developer, CS student): ").strip() or "developer",
        "LANGUAGES": ask("Main languages/stacks: ").strip() or "(not specified)",
        "PREFERENCES": ask("Working preferences (e.g. concise answers, ask before deleting): ").strip() or "(not specified)",
    }
    template = (paths.kit_root() / "templates/personal/rules/me.md").read_text(encoding="utf-8")
    me.parent.mkdir(parents=True, exist_ok=True)
    if me.exists():
        bk.save_copy(me, "personal me.md before configure")
    else:
        bk.record_created(me, "created personal me.md")
    me.write_text(scaffold.render(template, values), encoding="utf-8")


def wizard(ask: Ask, first_run: bool, setup: bool = True) -> int:
    bk = Backup(description="configure")
    if first_run or not (paths.personal_root() / "rules" / "me.md").exists():
        print("\n-- About you (stored in your personal layer, loaded every session)")
        _about_you(ask, bk)
    print("\n-- Preferences (enter = keep current)")
    personal = load_json(_personal_settings_path())
    for key, label, _ in PREFS:
        answer = ask(f"{label} [{personal.get(key, 'kit default')}]: ").strip()
        if answer:
            set_pref(key, answer if answer in ("true", "false") else json.dumps(answer))
    menu = addons()
    while True:
        print("\n-- Global add-ons (toggle by number; enter = done)")
        category = None
        for i, a in enumerate(menu, 1):
            if a.category != category:
                category = a.category
                print(f"  {category}")
            print(f"   {i:2d}. [{'x' if is_on(a) else ' '}] {a.label} — {a.reason}")
        answer = ask("toggle: ").strip()
        if not answer:
            break
        for token in answer.replace(" ", "").split(","):
            if token.isdigit() and 1 <= int(token) <= len(menu):
                a = menu[int(token) - 1]
                if a.kind == "plugin":
                    set_plugin(a.target, not is_on(a))
                else:
                    for warning in set_mcp(a.target, not is_on(a)):
                        print(f"  note: {warning}")
    if not bk.empty:
        print(f"backup: {bk.root}  (undo: loadout restore {bk.root})")
    apply_all(ask, setup=setup)
    return 0
