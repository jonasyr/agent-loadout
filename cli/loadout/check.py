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


def _same_files(kit: Path, copy: Path) -> bool:
    """The same files with the same bytes, both ways: a file only in the copy can still run (Codex loads every
    folder under skills/, so a skill the kit removed or renamed would keep working from an old copy)."""
    try:
        files = _plugin_files(kit)
        if files != _plugin_files(copy):
            return False
        return all((kit / rel).read_bytes() == (copy / rel).read_bytes() for rel in files)
    except OSError:
        return False


def _claude_copy() -> Path | None:
    try:
        installed = get_dict(load_json(paths.claude_home() / "plugins" / "installed_plugins.json"), "plugins")
    except InvalidJSON:
        return None  # "plugins installed" reports the broken file
    entries = installed.get(PLUGIN_ID)
    for e in entries if isinstance(entries, list) else []:
        if isinstance(e, dict) and e.get("scope") == "user" and isinstance(e.get("installPath"), str):
            path = Path(e["installPath"])
            return path if path.is_dir() else None
    return None


def _codex_copy() -> Path | None:
    folder = paths.codex_home() / "plugins" / "cache" / "agent-loadout" / "loadout"
    if (folder / "local").is_dir():
        return folder / "local"  # a marketplace from git installs as "local"
    try:
        dirs = [d for d in folder.iterdir() if d.is_dir()] if folder.is_dir() else []
    except OSError:
        return None
    return max(dirs, key=lambda d: d.stat().st_mtime) if dirs else None


def _plugin_copies() -> list[CheckResult]:
    """The installed loadout plugin, per agent that is on, against the kit's plugins/loadout: an old copy runs old
    hooks and skills, which can act on state that has moved. No line when the agent has no copy."""
    from . import targets
    kit = paths.kit_root() / "plugins" / "loadout"
    if not kit.is_dir():
        return []
    out = []
    for name, on, find, reload in (
            ("Claude Code", targets.claude_enabled(), _claude_copy, "then /reload-plugins in Claude Code"),
            ("Codex", targets.codex_enabled(), _codex_copy, "then approve the changed hooks in Codex's /hooks")):
        copy = find() if on else None
        if copy is None:
            continue
        ok = _same_files(kit, copy)
        out.append(CheckResult(f"loadout plugin ({name})", ok,
                               "" if ok else "the installed copy differs from the kit, so its hooks and skills may be old",
                               f"loadout update --yes, {reload}", "warn"))
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


def _binaries() -> list[CheckResult]:
    out = []
    for entry in catalog.binaries():
        if entry.get("helper"):
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


def _wsl() -> list[CheckResult]:
    version = wsl.detect()
    if version is None:
        return []
    return [CheckResult(f"WSL {version}", True),
            *(CheckResult("WSL", False, problem, fix, "warn") for problem, fix in wsl.problems(version, wsl.current_dir()))]


def _codex() -> list[CheckResult]:
    from . import codex
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


def run_checks() -> list[CheckResult]:
    from . import targets
    on = targets.claude_enabled()  # Codex only: no Claude Code links, settings, plugins or own tools to check
    return [*_python(), *_wsl(), *_legacy_state(),
            *(_links() if on else []), *_skills_json(), *(_settings() if on else []), *(_plugins() if on else []),
            *_codex(), *_plugin_copies(), *(_connectors() if on else []), *_own(),
            *_binaries(), *_mcp_path(), *_gh(), *_secrets(), *_repos()]


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
