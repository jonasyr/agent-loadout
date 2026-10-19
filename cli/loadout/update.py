"""`loadout update`: the numbered plan and its one question (spec decision 7, ADR 0011: every tool's exact command
is shown before it runs). The plan reads state and runs nothing; an agent that is off is neither read nor named."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from . import apply, bootstrap, codex, maintenance, out, paths, pkgmgr, runner, targets, ui, versions
from .jsonio import get_dict, load_json

PROMPT = "Apply all? [Y/n, or the numbers to leave out, e.g. 3 5] "
NO_TERMINAL = "nothing changed (run loadout update --yes to apply)"
BAD_ANSWER = "  please answer y, n, or the numbers of the items to leave out"


@dataclass
class PlanItem:
    n: int
    kind: str  # reapply, claude-plugin-install, claude-plugins-refresh, codex-plugins, tool-update, tool-install
    label: str
    commands: list[list[str]]
    optional: bool = False  # left out unless its number is named
    key: str = ""  # the tool's id (tool items)
    latest: tuple = ()  # the offered version (tool-update): what `decline` remembers


def _date(ts) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts)) if isinstance(ts, (int, float)) and ts else "an earlier run"


def _codex_item(items: list) -> None:
    """The Codex marketplaces and plugins to refresh, and those skipped because upstream did not move."""
    if codex.unavailable() is not None or not runner.have("codex"):  # unusable, or extension mode: no plugins
        return
    from .settings_merge import desired_settings
    routes, _ = codex.plugin_routes(desired_settings())
    if not routes:
        return
    skip_m, _skip_p = codex.unchanged_routes(routes)
    refresh = [src for src in routes if src not in skip_m]
    record = codex._load_record()
    times = [get_dict(record, src).get("at") for src in skip_m]
    times = [t for t in times if isinstance(t, (int, float)) and t]
    label = f"Codex marketplaces and plugins: refresh {len(refresh)}"
    if skip_m:
        label += f", skip {len(skip_m)} (unchanged since {_date(min(times) if times else None)})"
    cmds = [["codex", "plugin", "marketplace", "upgrade", out.printable(src)] for src in refresh]
    items.append(("codex-plugins", label, cmds, False, "", ()))


def _claude_refresh_item(items: list) -> None:
    from .settings_merge import desired_settings
    installed = get_dict(load_json(paths.claude_home() / "plugins" / "installed_plugins.json"), "plugins")
    todo = [pid for pid, on in get_dict(desired_settings(), "enabledPlugins").items()
            if on and isinstance(installed.get(pid), list)
            and any(isinstance(e, dict) and e.get("scope") == "user" for e in installed[pid])]
    if not todo:
        return
    cmds = [["claude", "plugin", "marketplace", "update"],
            *(["claude", "plugin", "update", out.printable(pid), "--scope", "user"] for pid in todo)]
    items.append(("claude-plugins-refresh", f"Claude Code plugins: refresh {len(todo)}", cmds, False, "", ()))


def build_plan(claude_on: bool, codex_on: bool) -> list[PlanItem]:
    """Item 1 re-applies the setup; then new kit plugins, plugin refreshes, tool updates, tool installs. Reads
    only: the apply steps run dry, nothing is added or run. An agent that is off is not looked at."""
    items: list[tuple] = []
    parts = []
    if claude_on:
        step = apply.claude_plugins_step(dry=True, on=True)
        parts.append(f"Claude Code ({step.summary or 'rules and settings'})")
        _, _, new_plugins = bootstrap.plugins_plan()
        if new_plugins:
            cmds = [["claude", "plugin", "install", out.printable(p), "--scope", "user"] for p in new_plugins]
            items.append(("claude-plugin-install", f"Claude Code: install {len(new_plugins)} new kit plugin(s): "
                          + ", ".join(out.printable(p) for p in new_plugins), cmds, False, "", ()))
        _claude_refresh_item(items)
    if codex_on:
        step = apply.codex_step(object(), refresh_plugins=True, auto=False, keep=False, skip_unchanged=True,
                         dry=True, on=True)
        parts.append(f"Codex ({step.summary or 'rules block and config'})")
        _codex_item(items)
    for entry, local, latest in maintenance.find_outdated():
        cmds, how = pkgmgr.update_plan(entry)
        if not cmds:
            continue  # nothing to run on this platform; `loadout check` names it
        label = f"{entry['id']}: {versions.fmt(local)} -> {versions.fmt(latest)}" + (f" (via {how})" if how != "catalog" else "")
        items.append(("tool-update", label, cmds, False, entry["id"], latest))
    for entry, cmds, optional in bootstrap.missing_tools():
        items.append(("tool-install", f"install {entry['id']} (new, recommended)" if optional else f"install {entry['id']}",
                      cmds, optional, entry["id"], ()))
    first = "Re-apply the loadout setup" + (f": {', '.join(parts)}" if parts else "")
    plan = [PlanItem(1, "reapply", first, [])]
    for kind, label, cmds, optional, key, latest in items:
        plan.append(PlanItem(len(plan) + 1, kind, label, cmds, optional, key, latest))
    return plan


def render(plan: list[PlanItem]) -> list[str]:
    lines = []
    for item in plan:
        lines.append(f"{item.n}. {item.label}" + ("  [optional: type its number to install it]" if item.optional else ""))
        lines += ["     command: " + " ".join(cmd) for cmd in item.commands]
    return lines


def choose(plan: list[PlanItem], answer: str) -> list[PlanItem] | None:
    """The items to run for an answer: "", y, yes: every non-optional one; n, no: none; numbers (space or comma
    separated): every non-optional item except those, and an optional item whose number is named. Anything
    else, or a number not in the plan: None (ask again)."""
    words = answer.replace(",", " ").lower().split()
    if not words:
        return [i for i in plan if not i.optional]
    nums = None
    if words[0] in ("y", "yes", "n", "no"):
        if words[0] in ("n", "no") and len(words) == 1:
            return []
        if words[0] in ("n", "no"):
            return None
        words = words[1:]
        if not words:
            return [i for i in plan if not i.optional]
    try:
        nums = {int(w) for w in words}
    except ValueError:
        return None
    if not nums <= {i.n for i in plan}:
        return None
    return [i for i in plan if (i.optional and i.n in nums) or (not i.optional and i.n not in nums)]


def confirm(plan: list[PlanItem], yes: bool, ask: Callable[[str], str], interactive: bool | None = None
            ) -> list[PlanItem] | None:
    """Show the plan and ask once; the chosen items, or None when nothing was asked or applied (no terminal and no
    --yes). Call it outside every out.step. Tool updates left out are declined: no weekly notice until newer."""
    print("\n".join(render(plan)))
    if yes:
        return choose(plan, "")
    if not (ui.is_interactive() if interactive is None else interactive):
        print(NO_TERMINAL)
        return None
    chosen = None
    while chosen is None:
        chosen = choose(plan, ask(PROMPT))
        if chosen is None:
            print(BAD_ANSWER)
    kept = {i.n for i in chosen}
    for item in plan:
        if item.kind == "tool-update" and item.n not in kept and item.latest:
            maintenance.decline(item.key, item.latest)
    return chosen
