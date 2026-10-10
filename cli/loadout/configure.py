"""Configure wizard: defaults stay as the kit ships them; choices go into the personal layer (spec §6.4)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Callable

from . import catalog, paths, preferences, profiles, runner, scaffold, secrets, ui
from .backup import Backup
from .jsonio import load_json, save_json
from .secrets import redact

Ask = Callable[[str], str]


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


def set_pref_choice(pid: str, value: str, ask: Ask, interactive: bool) -> list[str]:
    bk = Backup(description="configure preferences")
    out = preferences.set_choice(pid, value, ask=ask, interactive=interactive, bk=bk)
    if not bk.empty:
        out.append(f"backup: {bk.root}  (undo: loadout restore {bk.root})")
    return out


def show() -> str:
    lines = ["Change one with: loadout configure set <plugin|mcp> <id> on|off"]
    for a in addons():
        on = is_on(a)
        source = "default" if on == a.default_on else "personal"
        hint = f" (recommended per project: loadout profile {a.category[8:]})" if a.category.startswith("profile ") else ""
        lines.append(f"{'on' if on else 'off'} ({source})  [{a.category}] {a.label}{hint}  — id: {a.kind} {a.target}")
        lines.append(f"      {a.reason}")
    lines += preferences.show_lines()
    personal = load_json(_personal_settings_path())
    other = {k: v for k, v in preferences.without_owned_settings(personal).items()
             if k not in ("enabledPlugins", "extraKnownMarketplaces")}
    if other:
        lines.append(redact("other personal settings (set with: loadout configure set pref <key> <json>): "
                            + json.dumps(other, ensure_ascii=False)))
    return "\n".join(lines)


def offer_commit(ask: Ask) -> None:
    root = paths.personal_root()
    if (root / ".git").exists():
        # porcelain v1 is the --short format with a stable layout; -uall lists files inside new dirs
        status = runner.run(["git", "-C", str(root), "status", "--porcelain", "-uall"])
        if status.stdout.strip():
            print(f"changes in your personal layer ({root}):")
            print(status.stdout.rstrip("\n"))
        changed = [line[3:].split(" -> ")[-1].strip().strip('"') for line in status.stdout.splitlines() if line.strip()]
        private = [p for p in changed if p.rsplit("/", 1)[-1].endswith(".env") or secrets.private_path(p)]
        if private:
            print(f"not offering to commit the personal layer: {', '.join(private)} would be committed "
                  f"(keys and secrets never belong there; secrets go in {paths.secrets_file()}; "
                  f"remove them or add them to {root / '.gitignore'})")
        elif status.stdout.strip() and ask("commit and push your personal layer? [y/N] ").strip().lower() == "y":
            runner.run(["git", "-C", str(root), "add", "-A"])
            runner.run(["git", "-C", str(root), "commit", "-m", "chore: update loadout preferences"])
            runner.run(["git", "-C", str(root), "push"])


def apply_all(ask: Ask, setup: bool = True) -> None:
    """setup=False: the caller (bootstrap) applies settings, MCP servers and plugins itself afterwards."""
    from . import bootstrap
    from .personal_mcp import apply_mcp
    from .settings_merge import apply_settings

    if setup:
        apply_settings()
        plugin_lines = bootstrap.setup_plugins()
        if any(line.endswith(": added") for line in plugin_lines):
            apply_settings()  # the CLI rewrites marketplace entries and drops autoUpdate
        for line in plugin_lines + apply_mcp():
            print(line)
    offer_commit(ask)
    if setup:
        print("Restart Claude Code (or run /reload-plugins) to load the changes.")


def _about_you(ask: Ask, bk: Backup) -> bool:
    """True when a new me.md was written (its preference answers are then asked with defaults)."""
    me = paths.personal_root() / "rules" / "me.md"
    if me.exists():
        if not ui.confirm(ask, f"{me} already exists. Replace it with a new one? (the current one is backed up) [y/N] "):
            print(f"kept {me}")
            return False
    values = {
        "NAME": ask("Your name: ").strip() or "me",
        "ROLE": ask("Your role (e.g. backend developer, CS student): ").strip() or "developer",
        "LANGUAGES": ask("Main languages/stacks: ").strip() or "(not specified)",
        "PREFERENCES": ask("Anything else about how you like to work (the next questions cover language, "
                           "commits and answer style): ").strip() or "(not specified)",
    }
    template = (paths.kit_root() / "templates/personal/rules/me.md").read_text(encoding="utf-8")
    me.parent.mkdir(parents=True, exist_ok=True)
    if me.exists():
        bk.save_copy(me, "personal me.md before configure")
    else:
        bk.record_created(me, "created personal me.md")
    me.write_text(scaffold.render(template, values), encoding="utf-8")
    return True


def ask_preferences(ask: Ask, fill_defaults: bool, interactive: bool, bk: Backup) -> None:
    if interactive:
        print("\n-- Working preferences (enter = keep the current answer"
              + ("; new answers start at the recommended default)" if fill_defaults else ")"))
    for line in preferences.ask_all(ask, fill_defaults=fill_defaults, interactive=interactive, bk=bk):
        print(f"  {line}")
    if not interactive and fill_defaults:
        print("preferences: defaults applied (auto mode skipped); change them with `loadout configure prefs`")


def prefs(ask: Ask, interactive: bool | None = None) -> int:
    """`loadout configure prefs`: only the preference questions, then apply."""
    interactive = ui.is_interactive() if interactive is None else interactive
    bk = Backup(description="configure preferences")
    ask_preferences(ask, fill_defaults=False, interactive=interactive, bk=bk)
    if not bk.empty:
        print(f"backup: {bk.root}  (undo: loadout restore {bk.root})")
    apply_all(ask)
    return 0


def wizard(ask: Ask, first_run: bool, setup: bool = True, interactive: bool | None = None,
           preferences_asked: bool = False) -> int:
    """preferences_asked: the caller (bootstrap's starter layer) just asked them; do not ask twice."""
    interactive = ui.is_interactive() if interactive is None else interactive
    bk = Backup(description="configure")
    new_me = False
    if first_run or not (paths.personal_root() / "rules" / "me.md").exists():
        print("\n-- About you (stored in your personal layer, loaded every session)")
        new_me = _about_you(ask, bk)
    if not preferences_asked:
        ask_preferences(ask, fill_defaults=new_me, interactive=interactive, bk=bk)
    menu = addons()
    while True:
        print("\n-- Global add-ons (toggle by number; enter = done)")
        category = None
        for i, a in enumerate(menu, 1):
            if a.category != category:
                category = a.category
                print(f"  {category}")
            per_project = " (recommended per project instead)" if a.category.startswith("profile ") else ""
            print(f"   {i:2d}. [{'x' if is_on(a) else ' '}] {a.label}{per_project} — {a.reason}")
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


def _own_verdicts():
    from . import inventory
    return inventory.classify(inventory.collect(with_versions=False))


def own_lines(include_left: bool) -> list[str]:
    from . import own

    verdicts = _own_verdicts()
    found = own.unmanaged(verdicts, include_left)
    names = own.qualified_names(own.unmanaged(verdicts, True))
    if not found:
        lines = ["Nothing to decide: loadout or your personal layer manages every tool."]
        if not include_left and any(v.action == "keep" and v.reason == own.LEFT_REASON for v in verdicts):
            lines.append("Tools you chose to leave on this machine: `loadout configure own --all`")
        return lines
    lines = ["Not managed by loadout (they stay on this machine only). Choose with:",
             "  loadout configure set own <name> global|project:<profile>|leave|remove"]
    for v in found:
        lines.append(redact(f"  [{v.item.kind}] {names.get(id(v.item), v.item.name)}  {v.item.detail}".rstrip()))
        left = "  (left on this machine)" if own.is_left(v.item) else ""
        lines.append(f"      options: {', '.join(own.options(v.item))}{left}")
    return lines


def set_own(name: str, choice: str) -> int:
    import sys

    from . import adopt, own

    try:
        pairs = own.resolve(own.parse_spec(f"{name}={choice}"), _own_verdicts())
    except ValueError as exc:
        print(f"loadout: {exc}", file=sys.stderr)
        return 2
    bk = Backup(description="configure own")
    for note in own.profile_notes(pairs):
        print(note)
    changed: list = []
    lines, profiles_changed = adopt.apply_own(pairs, bk, changed=changed, project_hint=False)
    for line in lines:
        print(redact(line))
    if changed:
        print(adopt.RESTART_NOTE)
    for profile in profiles_changed:
        print(f"apply it in a repo: cd <repo> && loadout profile {profile}")
    if not bk.empty:
        print(f"backup: {bk.root}  (undo: loadout restore {bk.root})")
    return 1 if any(line.startswith("skipped:") or ": failed:" in line for line in lines) else 0
