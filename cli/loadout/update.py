"""`loadout update`: one run that brings a machine current. `run` takes the lock, pulls the kit and the personal
layer, restarts into the pulled kit code, then shows the numbered plan and its one question (spec decision 7, ADR
0011: every tool's exact command is shown before it runs), re-applies the setup through the shared apply steps,
refreshes plugins, updates tools, undoes what installers re-registered, checks the machine and prints "What changed".
The plan reads state and runs nothing; an agent that is off is neither read nor named."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Callable, NoReturn

from . import apply, bootstrap, check, codex, locks, maintenance, out, paths, pkgmgr, runner, steps, targets, ui, versions
from .backup import Backup
from .jsonio import get_dict, load_json, write_atomic_bytes
from .secrets import redact

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
    entry: dict | None = None  # the catalog entry (tool items)
    local: tuple = ()  # the installed version (tool-update)
    how: str = ""  # who updates it: mise, brew or the catalog command (tool-update)
    ids: tuple = ()  # the plugin ids the item refreshes (claude-plugins-refresh)
    groups: tuple = ()  # (what, its commands) per marketplace and plugin (codex-plugins); render shows these
    needs: tuple = ()  # the tool ids of the plan's other tool-install items it needs first (tool-install)


def _date(ts) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts)) if isinstance(ts, (int, float)) and ts else "an earlier run"


def _codex_item(items: list) -> None:
    """The Codex marketplaces and plugins to refresh, and those skipped because upstream did not move. Lists what
    runs (ADR 0011): per marketplace "refresh", "add" (new) or "skip", each plugin to add or re-add, and the commands
    in the shape codex._install_routes runs them."""
    if codex.unavailable() is not None or not runner.have("codex"):  # unusable, or extension mode: no plugins
        return
    from .settings_merge import desired_settings
    routes, _ = codex.plugin_routes(desired_settings())
    if not routes:
        return
    installed = codex.installed_plugins()
    skip_m, skip_p = codex.unchanged_routes(routes, installed)
    installed = installed or set()
    record = codex._load_record()
    listed = codex.marketplaces() or {}
    refresh = [src for src in routes if src not in skip_m]
    times = [get_dict(record, src).get("at") for src in skip_m]
    times = [t for t in times if isinstance(t, (int, float)) and t]
    label = f"Codex marketplaces and plugins: refresh {len(refresh)}"
    if skip_m:
        label += f", skip {len(skip_m)} (unchanged since {_date(min(times) if times else None)})"
    groups: list[tuple[str, list[list[str]]]] = []
    adds = readds = 0
    for src, names in routes.items():
        name = out.printable(src)
        market = get_dict(record, src).get("name")
        market = market if isinstance(market, str) and market in listed else None
        if src in skip_m:
            at = get_dict(record, src).get("at")
            groups.append((f"skip marketplace {name} (unchanged since {_date(at)})", []))
        elif market is None:  # no record of it: Codex may have it already, and then upgrades it
            groups.append((f"add or refresh marketplace {name}",
                           [["codex", "plugin", "marketplace", "add", name, "--json"],
                            ["codex", "plugin", "marketplace", "upgrade", f"<{name}'s marketplace>",
                             "(only when Codex had it)"]]))
        else:
            groups.append((f"refresh marketplace {name}", [["codex", "plugin", "marketplace", "add", name, "--json"],
                                                           ["codex", "plugin", "marketplace", "upgrade",
                                                            out.printable(market)]]))
        for plugin in names:
            pid = f"{plugin}@{market}" if market else f"{plugin}@<{src}'s marketplace>"  # its name comes from the add
            if pid in skip_p:
                continue
            again = pid in installed
            adds, readds = adds + (not again), readds + again
            groups.append((f"{'re-add' if again else 'add'} plugin {out.printable(pid)}",
                           [["codex", "plugin", "add", out.printable(pid), "--json"]]))
    if adds or readds:
        label += "; plugins: " + ", ".join(p for p in (f"add {adds}" if adds else "",
                                                       f"re-add {readds}" if readds else "") if p)
    cmds = [cmd for _, group in groups for cmd in group]
    items.append(("codex-plugins", label, cmds, False, "", (), None, (), "", (), tuple(groups)))


def _claude_refresh_todo() -> list[str]:
    """The plugins the kit enables that are installed at user scope (the ones `claude plugin update` refreshes)."""
    from .settings_merge import desired_settings
    installed = get_dict(load_json(paths.claude_home() / "plugins" / "installed_plugins.json"), "plugins")
    return [pid for pid, on in get_dict(desired_settings(), "enabledPlugins").items()
            if on and isinstance(installed.get(pid), list)
            and any(isinstance(e, dict) and e.get("scope") == "user" for e in installed[pid])]


def _claude_refresh_item(items: list) -> None:
    todo = _claude_refresh_todo()
    if not todo:
        return
    cmds = [["claude", "plugin", "marketplace", "update"],
            *(["claude", "plugin", "update", out.printable(pid), "--scope", "user"] for pid in todo)]
    items.append(("claude-plugins-refresh", f"Claude Code plugins: refresh {len(todo)}", cmds, False, "", (), None, (),
                  "", tuple(todo)))


def build_plan(claude_on: bool, codex_on: bool, notes: list[str] | None = None) -> list[PlanItem]:
    """Item 1 re-applies the setup; then new kit plugins, plugin refreshes, tool updates, tool installs. Reads
    only: the apply steps run dry, nothing is added or run. An agent that is off is not looked at.
    notes, when given, gets the lines about what the plan cannot do (a tool with no update command here, Codex
    plugins without the Codex CLI)."""
    notes = [] if notes is None else notes
    items: list[tuple] = []
    parts = []
    if claude_on:
        step = apply.claude_plugins_step(dry=True, on=True)
        parts.append(f"Claude Code ({step.summary or 'rules and settings'})")
        _, _, new_plugins = bootstrap.plugins_plan()
        if new_plugins:
            cmds = [["claude", "plugin", "install", out.printable(p), "--scope", "user"] for p in new_plugins]
            items.append(("claude-plugin-install", f"Claude Code: install {len(new_plugins)} new kit plugin(s): "
                          + ", ".join(out.printable(p) for p in new_plugins), cmds, False, "", (), None, (), ""))
        _claude_refresh_item(items)
    if codex_on:
        step = apply.codex_step(object(), refresh_plugins=True, auto=False, keep=False, skip_unchanged=True,
                         dry=True, on=True)
        parts.append(f"Codex ({step.summary or 'rules block and config'})")
        if not runner.have("codex"):
            notes.append(codex.PLUGINS_EXTENSION)
        _codex_item(items)
    for entry, local, latest in maintenance.find_outdated():
        cmds, how = pkgmgr.update_plan(entry)
        label = f"{entry['id']}: {versions.fmt(local)} -> {versions.fmt(latest)}" + (f" (via {how})" if how != "catalog" else "")
        if not cmds:  # nothing to run on this platform: say how to do it by hand
            notes.append(f"{label}: no update command for this platform. {entry.get('manual', '')}".rstrip())
            continue
        items.append(("tool-update", label, cmds, False, entry["id"], latest, entry, local, how))
    for entry, cmds, optional in bootstrap.missing_tools():
        items.append(("tool-install", f"install {entry['id']} (new, recommended)" if optional else f"install {entry['id']}",
                      cmds, optional, entry["id"], (), entry, (), ""))
    first = "Re-apply the loadout setup" + (f": {', '.join(parts)}" if parts else "")
    plan = [PlanItem(1, "reapply", first, [])]
    for kind, label, cmds, optional, key, latest, entry, local, how, *rest in items:
        plan.append(PlanItem(len(plan) + 1, kind, label, cmds, optional, key, latest, entry, local, how,
                             rest[0] if rest else (), rest[1] if len(rest) > 1 else ()))
    missing = {i.key for i in plan if i.kind == "tool-install"}
    for item in plan:
        if item.kind == "tool-install" and item.entry:
            item.needs = tuple(d for d in item.entry.get("needs", []) if d in missing and d != item.key)
    return plan


def _needs_text(item: PlanItem, plan: list[PlanItem]) -> str:
    nums = {i.key: i.n for i in plan if i.kind == "tool-install"}
    return ", ".join(f"needs {out.printable(d)} (item {nums[d]})" for d in item.needs if d in nums)


def render(plan: list[PlanItem]) -> list[str]:
    lines = []
    for item in plan:
        needs = _needs_text(item, plan)
        lines.append(f"{item.n}. {item.label}" + (f"; {needs}, installed with it" if needs else "")
                     + ("  [optional: type its number to install it]" if item.optional else ""))
        if item.groups:
            for what, cmds in item.groups:
                lines.append("     " + what)
                lines += ["       command: " + " ".join(cmd) for cmd in cmds]
        else:
            lines += ["     command: " + " ".join(cmd) for cmd in item.commands]
    return lines


def choose(plan: list[PlanItem], answer: str) -> list[PlanItem] | None:
    """The items to run for an answer: "", y, yes: every non-optional one; n, no: none; numbers (space or comma
    separated): every non-optional item except those, and an optional item whose number is named. Anything
    else, or a number not in the plan: None (ask again)."""
    words = answer.replace(",", " ").lower().split()
    if not words:
        return _with_needs(plan, {i.n for i in plan if not i.optional}, set())
    nums = None
    if words[0] in ("y", "yes", "n", "no"):
        if words[0] in ("n", "no") and len(words) == 1:
            return []
        if words[0] in ("n", "no"):
            return None
        words = words[1:]
        if not words:
            return _with_needs(plan, {i.n for i in plan if not i.optional}, set())
    try:
        nums = {int(w) for w in words}
    except ValueError:
        return None
    if not nums <= {i.n for i in plan}:
        return None
    return _with_needs(plan, {i.n for i in plan if (i.optional and i.n in nums) or (not i.optional and i.n not in nums)},
                       {i.n for i in plan if not i.optional and i.n in nums})


def _with_needs(plan: list[PlanItem], picked: set[int], left_out: set[int]) -> list[PlanItem]:
    """A chosen tool brings the missing tools it needs (an optional rust-analyzer brings mise); a tool whose
    prerequisite was left out by its number is left out too (it would run without it)."""
    by_key = {i.key: i for i in plan if i.kind == "tool-install"}
    changed = True
    while changed:
        changed = False
        for item in plan:
            if item.n not in picked:
                continue
            for dep in (by_key[d] for d in item.needs if d in by_key):
                if dep.n in left_out:
                    picked.discard(item.n)
                    changed = True
                    break
                if dep.n not in picked:
                    picked.add(dep.n)
                    changed = True
    return [i for i in plan if i.n in picked]


def confirm(plan: list[PlanItem], yes: bool, ask: Callable[[str], str], interactive: bool | None = None,
            notes: list[str] = ()) -> list[PlanItem] | None:
    """Show the plan (and the notes below it) and ask once; the chosen items, or None when nothing was asked or
    applied (no terminal and no --yes). Call it outside every out.step. Tool updates left out are declined: no
    weekly notice until newer."""
    print("\n".join(render(plan)))
    for note in notes:
        print(f"note: {note}")
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


# --- the run: lock, pull, restart, plan, apply, report ----------------------------------------------------------

PULLED = "LOADOUT_UPDATE_PULLED"  # set by the restart after a kit pull: the new process neither pulls nor restarts
AGAIN = "run loadout update again"

FACT_LINES = {  # one plain "What changed" line per fact a step reported
    "rules_linked": "rules: Claude Code's rule links refreshed",
    "settings_changed": "settings: ~/.claude/settings.json merged again",
    "mcp_changed": "MCP servers: your personal servers added to or removed from Claude Code",
    "claude_marketplace_added": "Claude Code: kit marketplace added",
    "claude_plugins_installed": "Claude Code: new kit plugins installed",
    "codex_block_written": "rules: Codex's AGENTS.md block updated",
    "codex_config_changed": "Codex: loadout's config.toml entries updated",
    "serena_hooks_added": "Codex: Serena's hooks added to hooks.json",
    "codex_hooks_removed": "Codex: loadout's old Serena hooks removed from hooks.json",
    "codex_skills_linked": "Codex: skill links refreshed",
    "codex_plugins_installed": "Codex: new plugins installed",
    "codex_plugins_updated": "Codex: plugins updated",
}
STEP_NAMES = {"links": "links", "settings": "rules and settings", "claude_plugins": "Claude Code plugins",
              "codex": "Codex setup"}


@dataclass
class Summary:
    """What one update run did. changed: one plain line each (backups with their undo); failed: (what, fix);
    steps: the person's open steps ("Now do this"; steps.derive). facts: the apply steps' facts plus claude_plugins_updated;
    upgraded: the tool ids updated or installed in this run (for the MCP-server steps)."""
    changed: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    steps: list[steps.Step] = field(default_factory=list)
    facts: set[str] = field(default_factory=set)
    upgraded: list[str] = field(default_factory=list)


def _exec(argv: list[str], windows: bool | None = None) -> NoReturn:
    """Continue in the pulled code: the same Python runs the kit's launcher again (as bin/loadout's continue_under).
    POSIX replaces the process; Windows has no real exec (os.execv returns at once and splits arguments), so it waits
    for the child and exits with its code. Ctrl+C reaches both there: the parent keeps waiting until the child has
    ended (its finally releases the locks; Windows has no dead-holder probe, a killed child would block for an hour)."""
    exe = sys.executable
    cmd = [exe, str(paths.kit_root() / "bin" / "loadout"), *argv]
    sys.stdout.flush()
    sys.stderr.flush()
    if os.name == "nt" if windows is None else windows:
        try:
            child = subprocess.Popen(cmd)
        except OSError as exc:
            _no_restart(exc)
        while True:
            try:
                code = child.wait()
                break
            except KeyboardInterrupt:  # the child prints the interrupt message and cleans up; wait for it
                continue
        sys.exit(code)
    try:
        os.execv(exe, cmd)
    except OSError as exc:  # the launcher is missing or broken in the pulled commit
        _no_restart(exc)


def _no_restart(exc: OSError) -> NoReturn:
    print(f"could not continue in the pulled code ({out.printable(str(exc))}); {AGAIN}")
    sys.exit(1)


def run(yes: bool, ask: Callable[[str], str], *, argv: list[str]) -> int:
    """`loadout update`: one run brings the machine current. argv: the command's flags, passed on to the restart.
    0 when finished (failed items are listed, not an exit code); 1 when another run still holds the lock.
    The kit's HEAD is read before the lock: another run (the daily sync) can pull the kit while this one waits, and
    this run must then continue in the pulled code too."""
    start = None if os.environ.get(PULLED) else _kit_head()
    if not maintenance._acquire_lock("update", locks.foreground_wait()):
        print(locks.busy_message(maintenance.LOCK))
        return 1
    try:
        summary = Summary()
        if os.environ.get(PULLED):
            _after_restart(summary, os.environ[PULLED])  # runner.run keeps it from every child (runner.PROCESS_ONLY)
        elif _pull(summary, start):
            maintenance._release_lock()  # the new process takes it again (POSIX keeps the pid, Windows gets a new one)
            # "1": the kit moved; "personal": the personal layer moved too (the new process names both)
            os.environ[PULLED] = "personal" if "personal layer: pulled new commits" in summary.changed else "1"
            out.status("Restart", "continuing in the pulled code")
            return _exec(["update", *argv])
        _apply(yes, ask, summary)
        return 0
    finally:
        maintenance._release_lock()


def _paused_fix(label: str, root, reason: str, files: list[str]) -> tuple[str, str]:
    what = f"{label}: not pulled: {out.printable(reason)}"
    if files:
        what += ": " + ", ".join(out.printable(f) for f in files)
        return what, f"commit or stash them in {out.printable(str(root))}, then run loadout update"
    return what, f"resolve it in {out.printable(str(root))}, then run loadout update"


def _after_restart(summary: Summary, marker: str) -> None:
    """The restarted run: what the first process pulled (marker: the PULLED value), and every pull git refused
    (sync-paused.json)."""
    summary.changed.append("kit: pulled new commits (this run continued in them)")
    if marker == "personal":
        summary.changed.append("personal layer: pulled new commits")
    paused = maintenance.paused()
    for label, root in (("kit", paths.kit_root()), ("personal layer", paths.personal_root())):
        entry = paused.get(str(root))
        if entry:
            files = [f for f in entry.get("files") or [] if isinstance(f, str)]
            summary.failed.append(_paused_fix(label, root, entry["reason"], files))


def _kit_head() -> str | None:
    """The kit checkout's HEAD; None when it is no git checkout, pulls are off or git cannot tell."""
    root = paths.kit_root()
    if os.environ.get("LOADOUT_NO_AUTO_PULL") == "1" or not (root / ".git").exists():
        return None
    res = runner.run(["git", "-C", str(root), "rev-parse", "HEAD"], timeout=30)
    return (res.stdout.strip() or None) if res.ok else None


def _pull(summary: Summary, start: str | None = None) -> bool:
    """Pull the kit and the personal layer (each only as a git checkout), as the daily sync does; a pull git
    refuses is recorded (sync-paused.json) and listed, a later one clears it. True when the kit moved: by this pull,
    or since start (the kit's HEAD before this run took the lock: another run pulled meanwhile)."""
    if os.environ.get("LOADOUT_NO_AUTO_PULL") == "1":
        out.status("Pull", "skipped (LOADOUT_NO_AUTO_PULL=1)")
        return False
    kit_moved = False
    pulled_any = False
    for label, root in (("kit", paths.kit_root()), ("personal layer", paths.personal_root())):
        if not (root / ".git").exists():
            continue
        res = maintenance.pull(root)
        pulled_any = pulled_any or not res.offline  # offline: the daily sync tries again soon
        if res.paused:
            summary.failed.append(_paused_fix(label, root, res.paused, res.files))
            out.status(label.capitalize(), f"not pulled: {out.printable(res.paused)}", "warn")
        elif res.offline:
            reason = out.printable(res.offline)
            summary.failed.append((f"{label}: {out.printable(str(root))}: not refreshed ({reason})",
                                   "run loadout update again when online"))
            out.status(label.capitalize(), f"not refreshed ({reason})", "warn")
        elif res.pulled:
            out.status(label.capitalize(), "pulled new commits")
            if label == "kit":
                kit_moved = True
            else:
                summary.changed.append("personal layer: pulled new commits")
        else:
            out.status(label.capitalize(), "up to date")
    if pulled_any:
        maintenance.touch("last-pull", time.time())
    if not kit_moved and start is not None:
        now = _kit_head()
        kit_moved = now is not None and now != start
    return kit_moved


def _show(result: apply.StepResult, summary: Summary) -> None:
    if not result.summary and not result.lines:
        return
    bootstrap._report(result.name, result.summary, result.lines)
    summary.facts |= result.facts
    for fact in sorted(result.facts):
        if fact == "skipped:codex":
            summary.failed.append(("Codex: not run (another loadout run held its lock)", AGAIN))
        elif fact.startswith("failed:"):
            step = fact.split(":", 1)[1]
            summary.failed.append((f"{STEP_NAMES.get(step, step)}: some items failed (listed above)",
                                   f"{AGAIN}; details with loadout update --verbose"))
        elif fact in FACT_LINES:
            summary.changed.append(FACT_LINES[fact])


def _say(st: out.Step):
    return lambda line: st.item(line.strip())


def _reapply(bk: Backup, claude_on: bool, codex_ok: bool, kinds: set[str], in_plan: set[str], summary: Summary) -> None:
    """Bootstrap's apply steps for each agent that is on, in its order: links, settings, Claude Code's kit
    marketplaces and new plugins, Codex. Item 1 (the re-apply) covers all of them except two items of their own: new
    Claude Code plugins (run when that item is kept) and the Codex plugin refresh (only together with item 1)."""
    reapply = "reapply" in kinds
    if reapply:
        _show(apply.link_step(bk, claude_on), summary)
        if claude_on:
            _show(apply.settings_step(bk, on=True), summary)
    if claude_on and ("claude-plugin-install" in kinds or (reapply and "claude-plugin-install" not in in_plan)):
        with out.step("Claude Code plugins") as st:
            result = apply.claude_plugins_step(say=_say(st), on=True)
        _show(result, summary)
    if codex_ok and reapply:
        refresh = "codex-plugins" in kinds or "codex-plugins" not in in_plan  # no item: nothing was left out
        slow = "Codex clones each changed plugin's source; this can take a few minutes" if refresh else None
        with out.step("Codex", slow=slow) as st:
            result = apply.codex_step(bk, refresh_plugins=refresh, auto=False, keep=False, skip_unchanged=True,
                                      say=_say(st), on=True, command="update", on_wait=maintenance._touch_lock)
        _show(result, summary)
    elif codex_ok and "codex-plugins" in kinds:
        summary.changed.append("Codex plugins: left as they are (they refresh together with item 1, the re-apply)")


def _refresh_claude_plugins(item: PlanItem, summary: Summary) -> None:
    """Exactly the plugins the plan showed (a plugin installed by this run is already current)."""
    todo = list(item.ids)
    market = runner.run(["claude", "plugin", "marketplace", "update"], timeout=300)  # the marketplaces first
    stale = not market.ok  # offline or signed out: the plugin updates below can only use the cached catalog
    if stale:
        reason = out.printable(redact((market.stderr or market.stdout).strip()[:300])) or "no output"
        summary.failed.append((f"Claude Code marketplaces: not refreshed: {reason}; the plugins were checked "
                               "against the cached catalog only", f"{AGAIN} when online (or signed in to claude)"))
        out.status("Marketplaces", "not refreshed; updating plugins from the cached catalog", "warn")
    updated = failed = 0
    with out.step("Claude Code plugins", total=len(todo)) as st:
        for pid in todo:
            st.item(out.printable(pid))
            maintenance._touch_lock()
            res = runner.run(["claude", "plugin", "update", pid, "--scope", "user"], timeout=300)
            if not res.ok:
                failed += 1
                summary.failed.append((f"plugin {out.printable(pid)}: failed: "
                                       f"{out.printable(redact((res.stderr or res.stdout).strip()[:300]))}", AGAIN))
            elif "already at the latest version" not in res.stdout.lower() + res.stderr.lower():
                updated += 1
                summary.changed.append(f"plugin {out.printable(pid)}: updated in Claude Code")
                summary.facts.add("claude_plugins_updated")
    text = (f"{updated} updated" if updated else "already up to date") if not stale else \
        f"{updated} updated from the cached catalog (newer versions may exist)"
    out.status("Plugin refresh", text + (f", {failed} failed (below)" if failed else ""), "warn" if failed else "ok")


def _update_tool(item: PlanItem, summary: Summary) -> None:
    entry, local, latest, how, tid = item.entry or {"id": item.key}, item.local, item.latest, item.how, item.key
    maintenance._touch_lock()
    all_ok, errors = True, []
    with out.step(f"Updating {out.printable(tid)}"):
        for cmd in item.commands:
            if out.VERBOSE:
                print("  command: " + " ".join(cmd))
            res = runner.run(cmd, cwd=pkgmgr.run_cwd(cmd), timeout=900)
            all_ok = all_ok and res.ok
            text = redact((res.stderr or res.stdout).strip()[:300])
            if not res.ok:
                errors.append(text)
            out.detail("ok" if res.ok else f"failed: {out.printable(text)}")
    now = versions.local_version(entry)
    if how == "mise":  # mise decides what is outdated (minimum_release_age): no bookkeeping of our own
        maintenance._remember_refused(tid, None)
    elif now is not None and now >= latest:
        maintenance._remember_refused(tid, None)
    elif not all_ok or now is None:
        pass  # a failure is not a refusal: keep notifying
    elif now == local:
        maintenance._remember_refused(tid, latest)
    else:
        maintenance._remember_refused(tid, None)
    name = out.printable(tid)
    if not all_ok:
        manual = entry.get("manual", "")
        summary.failed.append((f"{name} {versions.fmt(local)} -> {versions.fmt(latest)}: failed: "
                               f"{out.printable(redact('; '.join(errors)) or 'no output')}",
                               AGAIN + (f", or by hand: {manual}" if manual else "")))
    elif now is None:
        summary.changed.append(f"{name}: update ran (its version could not be read)")
        summary.upgraded.append(tid)
    elif now == local:
        summary.changed.append(f"{name}: still {versions.fmt(now)}; the package manager installed nothing newer "
                               f"(no new notice until a version newer than {versions.fmt(latest)} appears)")
    elif now < latest:
        summary.changed.append(f"{name}: updated to {versions.fmt(now)} (from {versions.fmt(local)}); "
                               f"{versions.fmt(latest)} was not installed (held back by the package manager?)")
        summary.upgraded.append(tid)
    else:
        summary.changed.append(f"{name} {versions.fmt(local)} -> {versions.fmt(now)}")
        summary.upgraded.append(tid)


def _install_tool(item: PlanItem, summary: Summary) -> None:
    maintenance._touch_lock()
    ok, lines = bootstrap.install_tool(item.entry or {"id": item.key}, item.commands)
    if ok:
        summary.changed.append(f"{out.printable(item.key)}: installed")
        summary.upgraded.append(item.key)
    else:
        summary.failed.append((out.printable(redact(lines[0]) if lines else f"{item.key}: not installed"),
                               AGAIN + ", or install it by hand"))


def _apply(yes: bool, ask: Callable[[str], str], summary: Summary) -> Summary:
    claude_on, codex_on = targets.claude_enabled(), targets.codex_enabled()
    codex_ok = codex_on
    if codex_on and (reason := codex.unavailable()) is not None:
        out.status("Codex", f"{reason}; its setup and plugins are left as they are", "warn")
        summary.failed.append((f"Codex: not set up: {out.printable(reason)}",
                               "install or update codex (mise use -g codex), or: loadout configure set target codex off"))
        codex_ok = False
    notes: list[str] = []
    plan = build_plan(claude_on, codex_ok, notes=notes)
    chosen = confirm(plan, yes, ask, notes=notes)
    if chosen is None:
        return summary
    kinds, in_plan = {i.kind for i in chosen}, {i.kind for i in plan}
    bk = Backup(description="update: re-apply the setup")
    _reapply(bk, claude_on, codex_ok, kinds, in_plan, summary)
    for item in chosen:
        if claude_on and item.kind == "claude-plugins-refresh":
            _refresh_claude_plugins(item, summary)
    settings_path = paths.claude_home() / "settings.json"
    before = _read_bytes(settings_path) if claude_on else None  # Codex only: Claude Code's file is not read at all
    ran = False
    for item in chosen:
        if item.kind == "tool-update":
            ran = True
            _update_tool(item, summary)
        elif item.kind == "tool-install":
            ran = True
            _install_tool(item, summary)
    if claude_on:  # Codex only: Claude Code's settings and servers are not loadout's to fix
        _guard_settings(settings_path, before, summary)
        if ran:  # installers re-register what the loadout plugin already provides
            dupes = Backup(description="update: duplicates re-registered by installers")
            removed, reported = maintenance.undo_reregistered(dupes)
            if removed:
                print("\nundid duplicates that an installer re-registered (the loadout plugin provides them):")
                for line in removed:
                    print(f"  {redact(line)}")
            for line in reported:
                print(f"note: {redact(line)}")
            if not dupes.empty:
                summary.changed.append(f"an installer's {len(removed)} re-registered duplicate(s) moved to a backup "
                                       f"(undo: loadout restore {out.printable(str(dupes.root))})")
    if not bk.empty:
        summary.changed.append(f"files the re-apply replaced are in a backup (undo: loadout restore {out.printable(str(bk.root))})")
    results = _health()
    try:  # a failure here must not hide the report
        steps.save(steps.derive(summary.facts, summary.upgraded, claude_on, codex_ok, results))
        steps.settle(claude_on, codex_on, results)  # drop what no longer holds
        summary.steps = [s for agent in steps.NAMES for s in steps.pending(agent)]  # also the ones still open
    except Exception:
        pass
    report(summary)
    return summary


def _read_bytes(path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def _parsed(data: bytes | None) -> tuple[dict | None, str]:
    """The settings an installer may have left: (the object, "") or (None, why it cannot be read)."""
    if data is None:
        return {}, ""
    try:
        text = data.decode("utf-8-sig").strip()
    except UnicodeDecodeError as exc:
        return None, f"not UTF-8 text ({exc.reason})"
    if not text:
        return {}, ""
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"
    return (value, "") if isinstance(value, dict) else (None, "not a JSON object at the top level")


def _guard_settings(path, before: bytes | None, summary: Summary) -> None:
    """Undo what the tool installers did to ~/.claude/settings.json: their version goes into a backup first, then
    the bytes from before they ran come back atomically. An unreadable file (malformed, not UTF-8) is undone the
    same way, never parsed into a crash that leaves it broken."""
    after = _read_bytes(path)
    if after == before:
        return
    old, _ = _parsed(before)
    new, why = _parsed(after)  # equal values in other bytes (indent, line ends, BOM, key order) are undone too
    guard = Backup(description="update: settings.json as modified by an installer")
    if after is None:
        if before is not None:
            write_atomic_bytes(path, before)
        what = "removed it"
    elif before is None:  # it did not exist: the installer's file moves into the backup (restore puts it back)
        guard.move(path, "settings.json as created by an installer")
        what = "created it"
    else:
        guard.save_copy(path, "settings.json as modified by an installer")
        write_atomic_bytes(path, before)
        what = "left it unreadable: " + why if new is None else "changed it"
    if new is None:
        detail = f"it could not be read: {why}"
    else:
        keys = sorted(k for k in set(old or {}) | set(new) if (old or {}).get(k) != new.get(k)) if old is not None else []
        detail = ("keys: " + ", ".join(out.printable(k) for k in keys) if keys
                  else what if what != "changed it" else "only its formatting")
    where = f" The installer's version is in {guard.root}" if not guard.empty else ""
    print(f"an installer modified ~/.claude/settings.json ({out.printable(detail)}); reverting to the kit-merged "
          f"version.{where}")
    line = (f"settings: an installer's change to ~/.claude/settings.json undone"
            + (f" ({out.printable(detail)})" if new is None else ""))
    if not guard.empty:
        line += f" (undo: loadout restore {out.printable(str(guard.root))})"
    summary.changed.append(line)


def _health() -> list:
    results = check.run_checks()
    bad = [r for r in results if not r.ok]
    _, code = check.format_results(bad)
    out.status("Health check", f"{len(results) - len(bad)} of {len(results)} OK"
               + ("; details: loadout check" if bad else ""), "fail" if code else "warn" if bad else "ok")
    return results


def report(summary: Summary) -> None:
    """The closing block: "What changed" (failed items with their fix) and "Now do this"."""
    print("\nWhat changed")
    for line in summary.changed:
        print(f"  {line}")
    for what, fix in summary.failed:
        print(f"  {what} (fix: {fix})")
    if not summary.changed and not summary.failed:
        print("  nothing: everything was already current")
    lines = steps.block(summary.steps, targets.claude_enabled(), targets.codex_enabled())
    if lines:
        print("\n" + "\n".join(lines))
