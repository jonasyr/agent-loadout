"""`loadout check`: report problems, never fix them; every failure names its fix."""
from __future__ import annotations

import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

from . import catalog, link, paths, runner, settings_merge, wsl
from .jsonio import InvalidJSON, get_dict, load_json


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    fix: str = ""
    severity: str = "error"


def _links() -> list[CheckResult]:
    out = []
    for dest, src in link.LINKS():
        if not src.exists() and dest.parent.name != "rules":
            continue  # optional personal-layer source (hooks/, skills): nothing to link
        name = f"link {dest.parent.name}/{dest.name}"
        if link.is_copy_mode():
            ok = link._points_to(dest, src) or link._is_kit_copy(dest, src)
        else:
            ok = dest.is_symlink() and dest.resolve() == src.resolve()
        out.append(CheckResult(name, ok, "" if ok else f"{dest} does not point to {src}", "loadout bootstrap"))
    return out


def _skills_json() -> list[CheckResult]:
    path = paths.personal_root() / "skills.json"
    if not path.exists():
        return []
    try:
        load_json(path)
    except InvalidJSON as exc:
        return [CheckResult("skills.json", False, str(exc), f"fix the JSON syntax in {path}", "warn")]
    return [CheckResult("skills.json", True)]


def _settings() -> list[CheckResult]:
    try:
        load_json(paths.claude_home() / "settings.json")
        drift = settings_merge.drift()
    except InvalidJSON as exc:
        return [CheckResult("settings.json", False, str(exc), "fix the JSON syntax, then run loadout apply-settings")]
    personal = paths.personal_root() / "settings.json"
    return [
        CheckResult("settings.json", True),
        CheckResult("settings drift", not drift, ", ".join(drift),
                    f"loadout apply-settings (to keep your own value instead, put the override in {personal})", "warn"),
    ]


def _plugins() -> list[CheckResult]:
    try:
        wanted = [p for p, on in get_dict(settings_merge.desired_settings(), "enabledPlugins").items() if on]
        installed = load_json(paths.claude_home() / "plugins" / "installed_plugins.json").get("plugins", {})
        if not isinstance(installed, dict):
            raise InvalidJSON("installed_plugins.json: 'plugins' is not an object")
    except InvalidJSON as exc:
        return [CheckResult("plugins installed", False, str(exc), "fix the JSON syntax", "warn")]
    missing = [p for p in wanted if p not in installed]
    # Claude Code installs enabled plugins from known marketplaces at its next start
    return [CheckResult("plugins installed", not missing, ", ".join(missing),
                        "they install automatically at the next Claude Code start (or run loadout bootstrap)", "warn")]


PLUGIN_ID = "loadout@agent-loadout"
AGENT_FILES = {".in_use", "__pycache__"}  # what the agents or Python add to a copy; never part of the kit
NOT_RUN = {"evals", "evals-browser"}  # never run by an agent; eval runs write gitignored reports into them


def _plugin_files(root: Path) -> set[Path]:
    """The plugin's files that can run, relative to root: without what agents or Python add and the eval folders."""
    return {rel for f in root.rglob("*")
            if not (AGENT_FILES & set((rel := f.relative_to(root)).parts) or rel.parts[0] in NOT_RUN
                    or f.suffix == ".pyc") and f.is_file()}


def _runnable(path: Path) -> bool:
    """The owner's executable bit (hooks run run.sh and tool_hint.sh directly); Windows has none, so always False."""
    return os.name != "nt" and bool(path.stat().st_mode & stat.S_IXUSR)


def _same_files(kit: Path, copy: Path) -> bool:
    """The same files with the same bytes, both ways: a file only in the copy can still run (Codex loads every
    folder under skills/, so a skill the kit removed or renamed would keep working from an old copy)."""
    try:
        files = _plugin_files(kit)
        if files != _plugin_files(copy):
            return False
        return all((kit / rel).read_bytes() == (copy / rel).read_bytes() and _runnable(kit / rel) == _runnable(copy / rel)
                   for rel in files)
    except OSError:
        return False


UPDATE = "loadout update --yes, then "
CLAUDE_RELOAD = "/reload-plugins in Claude Code"


def _claude_copies() -> list[tuple[str, Path, str]]:
    """(label, folder, fix) per recorded copy: user scope, and project or local scope, which runs in its project."""
    try:
        installed = get_dict(load_json(paths.claude_home() / "plugins" / "installed_plugins.json"), "plugins")
    except InvalidJSON:
        return []  # "plugins installed" reports the broken file
    entries = installed.get(PLUGIN_ID)
    out, seen = [], set()
    for e in entries if isinstance(entries, list) else []:
        if not isinstance(e, dict) or not isinstance(e.get("installPath"), str):
            continue
        path, scope = Path(e["installPath"]), e.get("scope")
        if path in seen or not path.is_dir():
            continue
        seen.add(path)
        if scope == "user":
            out.append(("Claude Code", path, UPDATE + CLAUDE_RELOAD))
        elif scope in ("project", "local"):
            where = f" {e['projectPath']}" if isinstance(e.get("projectPath"), str) else ""
            out.append((f"Claude Code, {scope}{where}", path,  # loadout update refreshes only the user scope
                        f"in that project: claude plugin update {PLUGIN_ID} --scope {scope}, then {CLAUDE_RELOAD}"))
    return out


def _codex_copies() -> list[tuple[str, Path, str]]:
    folder = paths.codex_home() / "plugins" / "cache" / "agent-loadout" / "loadout"
    fix = UPDATE + "approve the changed hooks in Codex's /hooks"
    if (folder / "local").is_dir():
        return [("Codex", folder / "local", fix)]  # a marketplace cloned from a repo installs as "local"
    try:
        dirs = [d for d in folder.iterdir() if d.is_dir()] if folder.is_dir() else []
    except OSError:
        return []
    return [("Codex", max(dirs, key=lambda d: d.stat().st_mtime), fix)] if dirs else []


def _plugin_copies() -> list[CheckResult]:
    """The installed loadout plugin, per agent that is on, against the kit's plugins/loadout: an old copy runs old
    hooks and skills, which can act on state that has moved. No line when the agent has no copy, or when the plugin
    is turned off (its leftover copy runs nothing, and `loadout update` skips it)."""
    from . import targets
    kit = paths.kit_root() / "plugins" / "loadout"
    try:
        wanted = get_dict(settings_merge.desired_settings(), "enabledPlugins").get(PLUGIN_ID)
    except InvalidJSON:
        return []  # "settings.json" and "own tools" report the broken file
    if not kit.is_dir() or not wanted:
        return []
    copies = [*(_claude_copies() if targets.claude_enabled() else []),
              *(_codex_copies() if targets.codex_enabled() else [])]
    out = []
    for label, copy, fix in copies:
        ok = _same_files(kit, copy)
        out.append(CheckResult(f"loadout plugin ({label})", ok,
                               "" if ok else "the installed copy differs from the kit, so its hooks and skills may be old",
                               fix, "warn"))
    return out


def _connectors() -> list[CheckResult]:
    """A kit-known plugin enabled next to the claude.ai connector with the same tools."""
    try:
        enabled = get_dict(load_json(paths.claude_home() / "settings.json"), "enabledPlugins")
        connected = load_json(paths.claude_json()).get("claudeAiMcpEverConnected", [])
    except (InvalidJSON, OSError, UnicodeDecodeError):
        return []  # settings.json errors are reported by _settings; ~/.claude.json is Claude Code's
    if not isinstance(enabled, dict) or not isinstance(connected, list):
        return []
    out = []
    for entry in catalog.load():
        name = entry.get("connector")
        if entry["kind"] != "plugin" or not name or name not in connected:
            continue
        for plugin in entry["match"].get("names", []):
            if enabled.get(plugin) is True:
                out.append(CheckResult(
                    f"duplicate {plugin}", False,
                    f"the plugin and the connector {name} provide the same tools "
                    "(if the connector is still connected)",
                    f"disconnect the connector on claude.ai, or run loadout configure set plugin {plugin} off",
                    "warn"))
    return out


def _json_fix(exc: InvalidJSON) -> str:
    """Fix text for an InvalidJSON error; jsonio puts the file in the message as `invalid JSON in <path>: ...`."""
    m = re.match(r"invalid JSON in (.+?): (?:Expecting|Extra|Invalid|Unterminated|expected)", str(exc))
    return f"fix the JSON syntax in {m.group(1)}" if m else "fix the JSON syntax in the file named above"


def _own() -> list[CheckResult]:
    from . import inventory, own

    try:
        n = len(own.unmanaged(inventory.classify(inventory.collect(with_versions=False))))
    except InvalidJSON as exc:
        return [CheckResult("own tools", False, str(exc), _json_fix(exc), "warn")]
    return [CheckResult("own tools", n == 0, f"{n} tool(s) not managed by loadout (they stay on this machine only)",
                        "decide with `loadout adopt --apply` or `loadout configure own`", "warn")]


def _binaries(cs=None) -> list[CheckResult]:
    out = []
    for entry in catalog.binaries():
        if entry.get("helper") or (entry["id"] == "codex" and _windows_only(cs)):  # it runs on Windows (ADR 0029)
            continue
        name = entry["id"]
        ok = runner.have(name)
        severity = "error" if entry.get("required") else "warn"
        fix = ("loadout bootstrap --install" if catalog.platform_cmds(entry, "install")
               else entry.get("manual") or f"install {name} and make sure it is on PATH")
        out.append(CheckResult(f"binary {name}", ok, "" if ok else "not on PATH", fix, severity))
    return out


def _mcp_path() -> list[CheckResult]:
    """Claude Code starts the plugin's servers by name, so a new terminal's PATH must find them."""
    hidden, absent = {}, False
    for name in ("serena", "codebase-memory-mcp"):
        if runner.which(name):
            continue
        for d in paths.tool_dirs():
            if any((d / f).exists() for f in (name, name + ".exe", name + ".cmd")):
                hidden[name] = d
                break
        else:
            absent = True
    if absent and not hidden:
        return []  # its "binary" line already fails with the install hint
    dirs = sorted({str(d) for d in hidden.values()})
    return [CheckResult("MCP servers on PATH", not hidden, ", ".join(hidden),
                        f"open a new terminal, or add {', '.join(dirs)} to PATH", "warn")]


def _gh() -> list[CheckResult]:
    if not runner.have("gh"):
        return []
    res = runner.run(["gh", "auth", "status"], timeout=20)
    return [CheckResult("gh auth", res.ok, "" if res.ok else "not logged in", "run `gh auth login`, then `gh auth setup-git`", "warn")]


def _secrets() -> list[CheckResult]:
    path = paths.secrets_file()
    if not path.exists():
        return [CheckResult("secrets.env", False, f"{path} missing", "loadout bootstrap", "warn")]
    if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) & 0o077:
        return [CheckResult("secrets.env", False, "permissions too open", f"chmod 600 {path}", "warn")]
    return [CheckResult("secrets.env", True)]


def _repos() -> list[CheckResult]:
    out = []
    for label, root in (("kit", paths.kit_root()), ("personal", paths.personal_root())):
        if not (root / ".git").exists():
            continue
        res = runner.run(["git", "-C", str(root), "status", "--porcelain"], timeout=20)
        clean = res.ok and not res.stdout.strip()
        out.append(CheckResult(f"{label} repo clean", clean, "" if clean else "uncommitted changes (daily sync paused)",
                               f"commit or discard changes in {root}", "warn"))
    return out


def _python() -> list[CheckResult]:
    return [CheckResult(f"Python {sys.version_info[0]}.{sys.version_info[1]}", True)]


def _wsl(cs=None) -> list[CheckResult]:
    version = wsl.detect()
    if version is None:
        return []
    problems = wsl.problems(version, wsl.current_dir())
    if _windows_only(cs):  # a Windows codex on PATH is the user's choice, not a problem
        problems = [(p, f) for p, f in problems if not p.startswith("codex resolves")]
    return [CheckResult(f"WSL {version}", True),
            *(CheckResult("WSL", False, problem, fix, "warn") for problem, fix in problems)]


def _wsl_codex_side():
    """In WSL with Codex on: which side the user's Codex runs on (read once per check); else None."""
    from . import targets
    if wsl.detect() is None or not targets.codex_enabled():
        return None
    return wsl.codex_side()


def _windows_only(cs) -> bool:
    """The user's only Codex is the Windows one: the WSL home is not theirs to check (ADR 0029)."""
    return cs is not None and cs.side == "windows" and not cs.shared_home


def _without_codex(fn):
    """Run a check as if Codex were off: with only the Windows Codex, the WSL Codex home is not the user's."""
    from . import targets
    old = targets.OVERRIDE
    targets.OVERRIDE = {"claude": targets.claude_enabled(), "codex": False}
    try:
        return fn()
    finally:
        targets.OVERRIDE = old


def _codex_side(cs=False) -> list[CheckResult]:
    """WSL only: the Windows Codex side, read-only (one loadout per side, ADR 0029)."""
    from . import codex
    cs = _wsl_codex_side() if cs is False else cs
    if cs is None:
        return []
    out = []
    if cs.shared_home:
        out.append(CheckResult("Codex home", False, "CODEX_HOME points into Windows: one config serves both sides, "
                               "and its commands fit only one", "unset CODEX_HOME in WSL (docs/how-to/wsl.md#codex)", "warn"))
    if cs.windows_home is not None and cs.windows_used:
        agents = cs.windows_home / ".codex" / "AGENTS.md"
        try:
            ok = codex.START in agents.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            ok = False
        out.append(CheckResult("Codex (Windows side)", ok, "" if ok else
                               "you use Codex on Windows too, and loadout has not set it up there",
                               "in PowerShell on Windows: run loadout's bootstrap.ps1 with the same personal layer "
                               "(docs/how-to/wsl.md#codex)", "warn"))
    return out


def _codex(cs=None) -> list[CheckResult]:
    from . import codex
    if _windows_only(cs) and codex.enabled():
        return [CheckResult("Codex", True, "runs on Windows: loadout sets it up there with bootstrap.ps1 "
                            "(docs/how-to/wsl.md#codex)")]
    return codex.checks()


def _legacy_state() -> list[CheckResult]:
    """What the move out of ~/.claude (ADR 0025) could not settle: old entries kept because both places have them,
    or old entries not copied yet. Old copies waiting to be retired are normal and not listed."""
    from . import migrate
    try:
        left = migrate.leftovers()
        waiting = migrate.pending()
    except OSError as exc:
        return [CheckResult("loadout state", False, f"cannot read the old folder in ~/.claude ({exc})",
                            "check its permissions, then run loadout again", "warn")]
    if waiting:
        return [CheckResult("loadout state", False, "not everything was copied out of ~/.claude yet",
                            "run any loadout command; if this stays, move the entry it names by hand", "warn")]
    if not left:
        return [CheckResult("loadout state", True)]
    names = ", ".join(str(p) for p in left[:5]) + (" …" if len(left) > 5 else "")
    return [CheckResult("loadout state", False, f"kept in ~/.claude because both places have it: {names}",
                        f"compare with {paths.state_dir()} and delete them by hand", "warn")]


def run_checks(codex_windows: bool = False) -> list[CheckResult]:
    """codex_windows: bootstrap chose the Windows side for Codex in this run, whatever the detection says."""
    from . import targets
    on = targets.claude_enabled()  # Codex only: no Claude Code links, settings, plugins or own tools to check
    cs = _wsl_codex_side()
    if codex_windows and cs is not None:
        from dataclasses import replace
        cs = replace(cs, side="windows", shared_home=False)
    return [*_python(), *_wsl(cs), *_codex_side(cs), *_legacy_state(),
            *(_links() if on else []), *_skills_json(), *(_settings() if on else []), *(_plugins() if on else []),
            *_codex(cs), *(_without_codex(_plugin_copies) if _windows_only(cs) else _plugin_copies()), *(_connectors() if on else []), *(_without_codex(_own) if _windows_only(cs) else _own()),
            *_binaries(cs), *_mcp_path(), *_gh(), *_secrets(), *_repos()]


def format_results(results: list[CheckResult]) -> tuple[str, int]:
    lines, code = [], 0
    for r in results:
        mark = "ok  " if r.ok else ("FAIL" if r.severity == "error" else "warn")
        line = f"[{mark}] {r.name}"
        if not r.ok:
            line += f": {r.detail}" if r.detail else ""
            line += f"\n        fix: {r.fix}" if r.fix else ""
            if r.severity == "error":
                code = 1
        lines.append(line)
    return "\n".join(lines), code


def format_summary(results: list[CheckResult]) -> tuple[str, int]:
    """One count line, then only the warnings and failures (same lines as format_results)."""
    bad = [r for r in results if not r.ok]
    text, code = format_results(bad)
    head = f"Health check: {len(results) - len(bad)} of {len(results)} OK"
    return (f"{head}\n{text}" if bad else head), code
