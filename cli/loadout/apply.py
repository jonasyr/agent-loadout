"""The apply steps bootstrap, configure and update share. Each returns a StepResult: the status-line text, the
per-item lines (callers print them their own way) and the facts, what the step changed:

- link_step: rules_linked
- settings_step: settings_changed, mcp_changed
- claude_plugins_step: claude_plugins_installed, claude_marketplace_added
- codex_step: codex_block_written, codex_config_changed, serena_hooks_added, codex_hooks_removed,
  codex_skills_linked, codex_plugins_installed, codex_plugins_updated
- any step: failed:<step> (links, settings, claude_plugins, codex) when one of its lines has a failure in the
  forms loadout prints (": failed", "failed to ") or a change it refused ("skipped <file>: …", "left as is",
  "by hand", "cannot", …; apply.refused lists them)
- codex_step: skipped:codex when it did not run (another loadout run held the Codex lock): nothing changed, but
  nothing was checked either

codex_config_changed covers what apply_config writes to config.toml; the `enabled = true` lines `codex plugin add`
writes there itself are not counted (codex_plugins_installed covers those).

With dry=True a step changes nothing and its facts are what it would change. An agent that is off gives an empty
StepResult, and nothing of that agent is read."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import out, targets
from .backup import Backup


_FAILED = re.compile(r": failed\b|\bfailed to ")
# a change the step refused to make (unbalanced markers, a file that does not parse, an entry the user owns): a
# problem line in the forms loadout prints. "skipped: " (with the colon) is the busy Codex lock: skipped:codex.
_REFUSED = re.compile(r"^skipped (?!:)|\bleft as is\b|\bby hand\b|\bcannot\b|\bcould not\b|\bnot changed\b"
                      r"|\bnot effective\b|\bdo not run\b|^warning:")


def refused(lines: list[str]) -> list[str]:
    """The lines of a step that name a failure or a refused change (what update lists one by one)."""
    return [line for line in lines if _FAILED.search(line) or _REFUSED.search(line)]


@dataclass
class StepResult:
    name: str
    summary: str
    lines: list[str] = field(default_factory=list)
    facts: set[str] = field(default_factory=set)
    level: str = "ok"


def _finish(result: StepResult, step: str) -> StepResult:
    """Redact every line (a failed clone's stderr can carry a token in a rewritten URL) before any caller prints it,
    then read the facts and the level from the lines."""
    from .secrets import redact
    result.lines = [redact(line) for line in result.lines]
    if refused(result.lines):
        result.facts.add(f"failed:{step}")
    if any(out.PROBLEM.search(line) for line in result.lines):
        result.level = "warn"
    return result


def link_step(bk: Backup, claude_on: bool, retry_symlinks: bool = False) -> StepResult:
    """Rule links (Claude Code only) and the launcher, which every agent uses."""
    from . import link
    lines = (link.link_all(bk, retry_symlinks=retry_symlinks) if claude_on else []) + link.link_bin(bk)
    if any(line.endswith("(symlinks unavailable)") for line in lines):
        # one visible line for what changes in practice; the per-file lines stay with --verbose
        lines.append("warning: symlinks unavailable, so rules, skills and hooks are copies, refreshed by bootstrap "
                     "and the daily sync; edit them in the kit or your personal layer (Windows: turn on Developer "
                     "Mode for links)")
    facts = {"rules_linked"} if claude_on and any(line.startswith(("linked ", "copied ")) for line in lines) else set()
    return _finish(StepResult("Links", "linked", lines, facts), "links")


def settings_step(bk: Backup, on: bool | None = None) -> StepResult:
    """Claude Code's settings.json merge (a copy into bk first) and the personal MCP servers.
    on: whether Claude Code is on (default: targets.json)."""
    if not (targets.claude_enabled() if on is None else on):
        return StepResult("Settings", "")
    from . import paths, settings_merge
    from .personal_mcp import apply_mcp
    settings_path = paths.claude_home() / "settings.json"
    if settings_path.exists() and settings_merge.would_change():
        bk.save_copy(settings_path, "settings.json before loadout merge")
    settings_merge.backup_snapshot(bk)
    before, after = settings_merge.apply_settings()
    mcp = apply_mcp()
    facts = {"settings_changed"} if before != after else set()
    if any(line.endswith((": added", ": removed")) for line in mcp):
        facts.add("mcp_changed")
    lines = ["settings updated" if before != after else "settings already up to date", *mcp]
    return _finish(StepResult("Settings", "settings merged" if before != after else "settings up to date", lines,
                              facts), "settings")


def _plugins_summary(lines: list[str]) -> str:
    from . import settings_merge
    from .jsonio import get_dict
    total = sum(1 for on in get_dict(settings_merge.desired_settings(), "enabledPlugins").values() if on)
    failed = sum(1 for line in lines if out.PROBLEM.search(line))
    return f"{total} kit plugins ready" if not failed else f"{failed} failed (below)"


def claude_plugins_step(say=None, dry: bool = False, on: bool | None = None, planned: tuple | None = None) -> StepResult:
    """Claude Code's kit marketplaces and plugins (bootstrap.setup_plugins), then the settings again when a
    marketplace was added (the CLI rewrites marketplace entries and drops autoUpdate).
    dry: only the marketplaces to add and the plugins to install, as lines; nothing is added or installed.
    planned: run exactly these (marketplaces, plugins), as `loadout update`'s plan showed them."""
    if not (targets.claude_enabled() if on is None else on):
        return StepResult("Plugins", "")
    from . import bootstrap, settings_merge
    if dry:
        lines, markets, plugins = bootstrap.plugins_plan()
        lines = [*lines, *(f"marketplace {out.printable(name)}: to add ({out.printable(origin)})"
                           for name, origin in markets),
                 *(f"plugin {out.printable(pid)}: to install" for pid in plugins)]
        facts = ({"claude_marketplace_added"} if markets else set()) | ({"claude_plugins_installed"} if plugins else set())
        summary = f"{len(markets)} marketplace(s) to add, {len(plugins)} plugin(s) to install"
        return _finish(StepResult("Plugins", summary, lines, facts), "claude_plugins")
    lines = bootstrap.setup_plugins(say=say) if planned is None else bootstrap.setup_plugins(say=say, planned=planned)
    if any(line.endswith(": added") for line in lines):
        settings_merge.apply_settings()
    facts = set()
    if any(line.startswith("plugin ") and line.endswith(": installed") for line in lines):
        facts.add("claude_plugins_installed")
    if any(line.startswith("marketplace ") and line.endswith(": added") for line in lines):
        facts.add("claude_marketplace_added")
    return _finish(StepResult("Plugins", _plugins_summary(lines), lines, facts), "claude_plugins")


def _codex_facts(lines: list[str]) -> set[str]:
    facts = set()
    for line in lines:
        if line.startswith("instructions written to "):
            facts.add("codex_block_written")
        elif line.startswith("hooks.json: added Serena's hooks"):
            facts.add("serena_hooks_added")
        elif line.startswith("hooks.json: removed loadout's Serena hooks"):
            facts.add("codex_hooks_removed")
        elif line.startswith(("linked ", "copied ")):
            facts.add("codex_skills_linked")
        elif line.startswith("plugin ") and line.endswith(": installed"):
            facts.add("codex_plugins_installed")
    return facts


def _codex_summary(lines: list[str]) -> str:
    from . import runner
    failed = sum(1 for line in lines if out.PROBLEM.search(line))
    done = ("rules, plugins, MCP servers and skills set up" if runner.have("codex")
            else "rules, MCP servers and skills set up for VS Code's Codex extension")
    return done if not failed else f"{failed} problem(s) (below)"


def codex_step(bk: Backup, *, refresh_plugins: bool, auto: bool, keep: bool, say=None,
               skip_unchanged: bool = False, dry: bool = False, on: bool | None = None, command: str = "setup",
               on_wait=None, plugins: bool = True, skips: tuple | None = None) -> StepResult:
    """Codex's rules block, config.toml, Serena's hooks, skills and plugins (codex.apply_all, under the Codex lock).
    The caller checks codex.unavailable() first. refresh_plugins: re-add every plugin and upgrade the marketplaces;
    auto: the daily sync's freeze of `autoUpdate: false` marketplaces; keep: never remove Serena's hooks.
    skip_unchanged: passed through (Codex marketplaces and plugins whose upstream did not move). on: whether Codex is on (default: targets.json).
    command, on_wait: for the Codex lock, as in codex.apply_all (the wait line's command; a run holding another lock
    touches it in on_wait). plugins: False leaves Codex's marketplaces and plugins alone. skips: (marketplace sources,
    plugin ids) decided by a plan, used instead of comparing the upstream heads again."""
    if not (targets.codex_enabled() if on is None else on):
        return StepResult("Codex", "")
    if dry:
        return _codex_dry(refresh_plugins, auto, keep)
    from . import codex
    changed: set[str] = set()
    lines = codex.apply_all(bk, refresh=refresh_plugins, say=say, auto=auto, keep=keep,
                            skip_unchanged=skip_unchanged, changed=changed, command=command, on_wait=on_wait,
                            plugins=plugins, skips=skips)
    facts = _codex_facts(lines)
    if any(line.startswith("skipped: ") for line in lines):
        facts.add("skipped:codex")
    if "config" in changed:
        facts.add("codex_config_changed")
    if "plugins_updated" in changed:
        facts.add("codex_plugins_updated")
    return _finish(StepResult("Codex", _codex_summary(lines), lines, facts), "codex")


def _codex_dry(refresh_plugins: bool, auto: bool, keep: bool) -> StepResult:
    """What codex_step would change; read-only (config.toml and hooks.json through their dry runs). auto and keep as
    in the real run: frozen marketplaces are not refreshed, and Serena's hooks are not removed."""
    from . import codex, codex_hooks, link, paths, runner, settings_merge
    lines, facts = [], set()
    path = paths.codex_home() / "AGENTS.md"
    old = codex._read_exact(path) if path.exists() else ""
    new = codex.splice(old, codex.render_instructions())
    if new is None:
        lines.append(f"skipped {path}: its loadout markers are unbalanced or duplicated; fix them by hand")
    elif new != old:
        lines.append(f"instructions: to write to {codex._tilde(path)}")
        facts.add("codex_block_written")
    config = codex.apply_config(object(), dry_run=True)
    lines += config
    if "config.toml: changes pending" in config:
        facts.add("codex_config_changed")
    lines += codex_hooks.apply(object(), dry_run=True, keep=keep)
    skills = [(dest, src) for dest, src in codex.skill_links() if src.exists() and not link._points_to(dest, src)]
    lines += [f"skill {out.printable(dest.name)}: to link" for dest, _ in skills]
    if skills:
        facts.add("codex_skills_linked")
    if not runner.have("codex"):
        lines.append(codex.PLUGINS_EXTENSION)
    else:
        from .jsonio import get_dict
        desired = settings_merge.desired_settings()
        routes, missing = codex.plugin_routes(desired)
        frozen = {codex.OFFICIAL if name == "claude-plugins-official" else get_dict(cfg, "source").get("repo")
                  for name, cfg in
                  get_dict(desired, "extraKnownMarketplaces").items()
                  if auto and isinstance(cfg, dict) and cfg.get("autoUpdate") is False}
        lines += [f"plugin {out.printable(pid)}: no Codex route (its marketplace is not on GitHub)" for pid in missing]
        have = {pid.split("@")[0] for pid in codex.installed_plugins() or ()}
        new_plugins = [name for names in routes.values() for name in names if name not in have]
        lines += [f"plugin {out.printable(name)}: to install" for name in new_plugins]
        if new_plugins:
            facts.add("codex_plugins_installed")
        if refresh_plugins:
            lines += [f"marketplace {out.printable(src)}: to refresh" for src in routes if src not in frozen]
    summary = f"{len(facts)} part(s) to change" if facts else "up to date"
    return _finish(StepResult("Codex", summary, lines, facts), "codex")
