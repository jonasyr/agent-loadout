"""`loadout check`: report problems, never fix them; every failure names its fix."""
from __future__ import annotations

import json
import math
import os
import re
import shlex
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from . import catalog, link, paths, runner, settings_merge, wsl
from .jsonio import InvalidJSON, get_dict, load_json
from .out import printable


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
        desired = settings_merge.desired_settings()
        wanted = [p for p, on in get_dict(desired, "enabledPlugins").items() if on]
        plugins_dir = paths.claude_home() / "plugins"
        installed = load_json(plugins_dir / "installed_plugins.json").get("plugins", {})
        if not isinstance(installed, dict):
            raise InvalidJSON("installed_plugins.json: 'plugins' is not an object")
        known = load_json(plugins_dir / "known_marketplaces.json")
    except InvalidJSON as exc:
        return [CheckResult("plugins installed", False, str(exc), "fix the JSON syntax", "warn")]
    missing = [p for p in wanted if p not in installed]
    no_market = sorted({m for p in missing if "@" in p and (m := p.rpartition("@")[2]) not in known})
    detail = ", ".join(missing)
    if no_market:
        detail += f"; marketplace not added: {', '.join(no_market)}"
        from . import profiles
        addable = set(get_dict(desired, "extraKnownMarketplaces")) | set(profiles.kit_marketplaces())
        unknown = [m for m in no_market if m not in addable]
        if unknown:
            fix = (f"declare {', '.join(unknown)} in your personal settings.json (extraKnownMarketplaces), "
                   "then run loadout update")
        else:
            fix = "run loadout update (adds the marketplace, then installs them)"
    else:
        fix = "run loadout update (or loadout bootstrap)"
    return [CheckResult("plugins installed", not missing, detail, fix, "warn")]


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
        if name == "codex" and not ok:
            from . import codex
            if codex.enabled() and codex.extension_state()[0] is not None:
                continue  # VS Code's Codex extension runs its own: the `Codex CLI` row says the CLI is optional
        if name == "claude" and not ok:
            from . import vscode
            found = vscode.bundled_claude()
            if found is not None:  # loadout's claude commands run it; a terminal still has no claude
                out.append(CheckResult(f"binary {name}", False,
                                       printable(f"not on PATH; loadout runs VS Code's Claude Code extension's own "
                                                 f"({found})"),
                                       "loadout bootstrap --install (a claude on PATH for the terminal and the "
                                       "extension's terminal mode)", "warn"))
                continue
        out.append(CheckResult(f"binary {name}", ok, "" if ok else "not on PATH", fix, severity))
    return out


def _cbm_auto_index() -> list[CheckResult]:
    """The cbm_auto_index row; none without codebase-memory-mcp. An OK row carries its state in the name, since
    `loadout check` prints details only for warnings."""
    from . import cbm
    now = cbm.query()
    if now is None:
        return []
    name = "codebase-memory auto_index"
    if now == cbm.UNREADABLE:
        return [CheckResult(name, False, "could not read it (codebase-memory-mcp config get auto_index failed)",
                            "run codebase-memory-mcp config get auto_index to see why", "warn")]
    if now:
        detail = "on"
    elif cbm.answer() == "off":
        detail = "off (your answer)"
    elif cbm._record():  # loadout turned it on and you turned it off
        detail = "off (yours)"
    else:
        return [CheckResult(name, False, "off (loadout turns it on at the next update)", "loadout update", "warn")]
    return [CheckResult(f"{name}: {detail}", True, detail, "", "warn")]


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


def _is_serena_server(cfg: dict) -> bool:
    command, args = cfg.get("command"), cfg.get("args")
    if not isinstance(command, str):
        return False
    base = re.split(r"[\\/]", command)[-1].lower().removesuffix(".exe")
    args = [a for a in args if isinstance(a, str)] if isinstance(args, list) else []
    return base in ("serena", "serena-agent") or (base in ("uvx", "uv") and any("serena" in a for a in args))


def _is_cbm_server(cfg: dict) -> bool:
    command = cfg.get("command")
    return isinstance(command, str) and re.split(r"[\\/]", command)[-1].lower().removesuffix(".exe") == "codebase-memory-mcp"


def _user_servers(cwd: Path) -> list[tuple[str, dict, str, bool]]:
    """(name, config, file, user scope) of the servers in ~/.claude.json (user and this folder's project scope)
    and <cwd>/.mcp.json."""
    config = load_json(paths.claude_json())
    out = [(n, c, "~/.claude.json", True) for n, c in get_dict(config, "mcpServers").items() if isinstance(c, dict)]
    projects = get_dict(config, "projects")
    for folder in (cwd, *cwd.parents):
        entry = next((projects[k] for k in (str(folder), folder.as_posix()) if k in projects), None)
        if isinstance(entry, dict):
            out += [(n, c, "~/.claude.json", False) for n, c in get_dict(entry, "mcpServers").items()
                    if isinstance(c, dict)]
            break
    out += [(n, c, ".mcp.json", False) for n, c in get_dict(load_json(cwd / ".mcp.json"), "mcpServers").items()
            if isinstance(c, dict)]
    return out


def _tool_setups() -> list[CheckResult]:
    """Serena or codebase-memory run next to the plugin's: your own hooks, a second server. Read only; the
    tools are never run."""
    from . import duplicates, own
    from .inventory import Item
    out = []
    try:
        cwd = Path(os.path.abspath(Path.cwd()))
        hooks = duplicates.equivalent_user_hooks(str(cwd))
        if hooks:
            files = ", ".join(dict.fromkeys(f for _, _, f in hooks))
            out.append(CheckResult("Serena hooks", True, f"yours in {files}; the plugin's copy stays silent",
                                   "loadout configure own", "warn"))
        servers = _user_servers(cwd)
        for label, test, tool in (("Serena", _is_serena_server, "serena"),
                                  ("codebase-memory", _is_cbm_server, "codebase-memory-mcp")):
            if duplicates.plugin_server_off(tool, str(cwd)):
                continue  # the plugin's is off here: yours is the only one
            mine = [(n, f) for n, c, f, user in servers if test(c) and not (
                user and duplicates.is_duplicate_mcp(Item("mcp", n, "", f, {"config": c})))
                and not own.is_left(Item("mcp", n, "", f, {}))]
            if mine:
                n, f = mine[0]
                out.append(CheckResult(f"{label} servers", False,
                                       f"two {label} servers: the plugin's and yours ({n} in {f})",
                                       f"keep one: in Claude Code's /mcp, disable plugin:loadout:{tool}; or remove "
                                       f"yours, or keep both (leave), with loadout configure own", "warn"))
        n_cbm = [(f, 1) for ev, words, f in duplicates.user_hooks(str(cwd)) if "hook-augment" in words]
        if n_cbm:
            files = ", ".join(dict.fromkeys(f for f, _ in n_cbm))
            out.append(CheckResult(
                "codebase-memory hooks", False,
                f"codebase-memory's own hooks ({len(n_cbm)} in {files}) add up to 2 s per call and print nothing "
                "in codebase-memory 0.12 (upstream #2683)", "loadout configure own (remove, or leave them)", "warn"))
    except Exception:  # an odd file shape never breaks the report
        return out
    return out


def _cbm_refresh() -> list[CheckResult]:
    """A row per repo whose last background refresh (hooks/refresh.py) failed; nothing while they succeed."""
    out = []
    try:
        files = sorted((paths.state_dir() / "cbm-refresh").glob("*.json"))[:64]
    except OSError:
        return out
    for f in files:
        try:
            data = load_json(f)
        except (InvalidJSON, OSError):
            continue
        last, root = data.get("last"), data.get("root")
        if not isinstance(last, dict) or last.get("ok") is not False or not isinstance(root, str) \
                or not Path(root).is_dir():
            continue  # no failure, or a repo that is gone
        at = last.get("at")
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(at)) if isinstance(at, (int, float)) else "?"
        error = last.get("error") if isinstance(last.get("error"), str) else ""
        out.append(CheckResult("codebase-memory refresh", False,
                               printable(f"{root}: the last re-index failed ({when}): {error}"),
                               printable(f"codebase-memory-mcp cli index_repository --repo-path {shlex.quote(root)}; "
                                         "the next change retries"), "warn"))
    return out


_CBM_LOG = "logs/daemon-conflicts.ndjson"
_CBM_TAIL = 64 * 1024  # only the newest records matter; a huge log is never read whole
_CBM_WINDOW = 24 * 3600


def _cbm_records(path: Path) -> list[dict]:
    """The parseable records in the last 64 KiB of one log file; anything else is skipped."""
    try:
        with path.open("rb") as f:
            start = max(0, f.seek(0, os.SEEK_END) - _CBM_TAIL)
            f.seek(max(0, start - 1))
            data = f.read(_CBM_TAIL + (1 if start else 0))
    except OSError:
        return []
    lines = data.split(b"\n")
    if start:
        lines = lines[1:]  # the byte before the tail (a newline, or the cut line's head) is not part of it
    out = []
    for line in lines:
        try:
            rec = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError):  # RecursionError: a deeply nested line
            continue
        ts = rec.get("timestamp_unix_s") if isinstance(rec, dict) else None
        if not isinstance(ts, (int, float)) or isinstance(ts, bool):
            continue
        try:
            ts = float(ts)  # an integer too large for a float would raise later, in the age arithmetic
        except OverflowError:
            continue
        if math.isfinite(ts):
            out.append({**rec, "timestamp_unix_s": ts})
    return out


def _cbm_conflict() -> list[CheckResult]:
    """codebase-memory-mcp 0.12 runs one daemon per account; a session for another cache folder or version fails
    and writes why into its own cache folder ($CBM_CACHE_DIR, else ~/.cache/codebase-memory-mcp). Read only: the
    binary is never run (its `daemon status` hangs)."""
    if os.name == "nt":
        return []
    default = paths.home() / ".cache/codebase-memory-mcp"
    folders = [(default, False)]
    env = os.environ.get("CBM_CACHE_DIR")
    if env and Path(env) != default:
        folders.append((Path(env), True))
    now, best = time.time(), None
    for folder, from_env in folders:
        for name in (_CBM_LOG, _CBM_LOG + ".1"):
            for rec in _cbm_records(folder / name):
                if abs(now - rec["timestamp_unix_s"]) <= _CBM_WINDOW and (
                        best is None or rec["timestamp_unix_s"] > best[0]["timestamp_unix_s"]):
                    best = (rec, folder, from_env)
    if best is None:
        return []
    rec, folder, from_env = best
    active, requested = rec.get("active_version"), rec.get("requested_version")
    if rec.get("reason") != "cache_root" and isinstance(active, str) and isinstance(requested, str) \
            and active != requested:
        detail = (f"a codebase-memory-mcp {requested} session could not start "
                  f"(version {active} already runs for your account)")
        fix = ("update every codebase-memory-mcp to one version, or close the other sessions (Codex, Claude Code, "
               "VS Code); codebase-memory-mcp daemon stop retires the daemon once no session uses it")
    else:
        detail = ("a codebase-memory-mcp session with a different cache folder could not start "
                  "(another one already runs for your account)")
        fix = ("close the other sessions (Codex, Claude Code, VS Code) or give them the same CBM_CACHE_DIR; "
               "codebase-memory-mcp daemon stop retires the daemon once no session uses it")
    if from_env:
        detail += f"; logged in {folder}, the CBM_CACHE_DIR of this check's own environment"
    return [CheckResult("codebase-memory-mcp daemon", False, printable(detail), fix, "warn")]


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
    """Dirty alone is fine (git refuses a pull only when it would overwrite something); a recorded refusal is not."""
    from . import maintenance
    from .out import printable
    from .update import _paused_fix  # the fix `loadout update` names: commit or stash only when git named files
    held = maintenance.paused()
    out = []
    for label, root in (("kit", paths.kit_root()), ("personal", paths.personal_root())):
        if not (root / ".git").exists():
            continue
        rec = held.get(str(root))
        if rec is None:
            out.append(CheckResult(f"{label} repo clean", True))
            continue
        files = [printable(str(f)) for f in rec.get("files") or []]
        detail = f"daily sync paused: {printable(rec['reason'])}" + (f": {', '.join(files)}" if files else "")
        out.append(CheckResult(f"{label} repo clean", False, detail,
                               _paused_fix(label, root, "", files)[1], "warn"))
    return out


def _repo_skill_links() -> list[CheckResult]:
    """The repo of the current folder: committed skill links this checkout wrote as plain files (spec Part 3)."""
    from . import skill_links
    from .new_skill import repo_root
    try:
        root = repo_root(Path(os.path.abspath(Path.cwd())))
    except OSError:  # the current folder was deleted: no repo to check
        return []
    if root is None or Path(os.path.realpath(root)) == Path(os.path.realpath(paths.home())):
        return []  # outside a repo, or a dotfiles repo in the home folder (.claude/skills there is Claude Code's own)
    lines = skill_links.report(skill_links.plain_files(root))
    if not lines:
        return []
    text = [l[len(skill_links.PREFIX):] for l in lines]
    return [CheckResult("repo skill links", False, f"{root}: " + "; ".join(text[:-1]),
                        text[-1].removeprefix("fix: "), "warn")]


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


def _vscode(cs) -> list[CheckResult]:
    """In WSL with Codex in WSL: VS Code's Codex extension must run that Codex too (spec Part 4); a folder's or a
    profile's settings that turn the switch off are named, never edited (spec Part 3)."""
    if cs is None or cs.side not in ("wsl", "both") or cs.windows_home is None:
        return []
    from . import vscode
    folder = vscode.folder_setting(wsl.WIN_SETTING)
    rows = []
    if folder is True:
        rows.append(CheckResult("VS Code", True, "in this folder the Codex extension runs Codex in WSL (its "
                                                 ".vscode/settings.json)"))
    elif cs.vscode_windows and folder is not False:
        rows.append(CheckResult("VS Code", False, "the Codex extension runs Codex on Windows, not the Codex in WSL",
                                f"loadout bootstrap --codex-side wsl --vscode-wsl, or {wsl.MANUAL}", "warn"))
    elif wsl.vscode_wsl_mode(cs.windows_home) is True and folder is not False:
        rows.append(CheckResult("VS Code", True, "the Codex extension runs Codex in WSL"))
    for kind, path in vscode.wsl_switch_overrides(cs.windows_home):
        detail, fix = vscode.override_text(kind, path)
        rows.append(CheckResult("VS Code", False, printable(detail), fix, "warn"))
    return rows


_HOME_PATH = re.compile(r"(?:^|=)(/home/(?!linuxbrew/)[^/]+/|/Users/[^/]+/|/mnt/[A-Za-z]/(?i:users)/[^/]+/|"
                        r"[A-Za-z]:[\\/](?i:users)[\\/][^\\/]+[\\/])")  # a user name may hold spaces


def _codex_cli_here() -> bool:
    """A Codex CLI that shares this side's ~/.codex: in WSL a Windows shim under /mnt/<drive>/ does not count."""
    if wsl.detect() is None:
        return runner.have("codex")
    found = runner.which("codex")
    return bool(found) and not wsl.is_windows_program("codex")


def _surface_rows(ext, windows_only: bool = False, vscode_row: bool = False) -> list[CheckResult]:
    """One extension in one window type: what it lacks, each with its fix; one ok row when nothing.
    vscode_row: the "VS Code" row already says the Codex extension runs Codex on Windows."""
    from . import codex, vscode
    name, gaps = vscode.row_name(ext), []
    if ext.agent == "codex":
        if ext.override_bad is not None:
            gaps.append((printable(f"chatgpt.cliExecutable names {ext.override_bad}, which is not a file it can run, "
                                   "and the extension starts Codex through it"),
                         "point it at an installed codex, or remove the setting from VS Code's user settings"))
        if ext.install.where == "windows" and not vscode.runs_in_wsl(ext) and not vscode_row:
            home = vscode.reads_home(ext)
            try:
                ours = codex.START in (home / "AGENTS.md").read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                ours = False
            if not ours:
                gaps.append((printable(f"the Codex extension in a Windows window reads {home}, which loadout has "
                                       "not set up"),
                             "switch it to WSL (loadout bootstrap --codex-side wsl --vscode-wsl), open repos with "
                             "`code .` from WSL, or run bootstrap.ps1 on Windows (docs/how-to/wsl.md#codex)"))
        if ext.binary is None and ext.override_bad is None:
            gaps.append(("the extension has no bundled Codex for this platform", "reinstall the Codex extension in VS Code"))
        else:
            version = vscode.bundled_version(ext)
            if version is not None and vscode.too_old(version) and ext.override:
                gaps.append((printable(f"the Codex that chatgpt.cliExecutable names ({ext.binary}) is {version}; "
                                       "loadout's Codex setup needs 0.161 or newer"),
                             "update that Codex, or remove chatgpt.cliExecutable from VS Code's settings so the "
                             "extension runs its own"))
            elif version is not None and vscode.too_old(version):
                gaps.append((f"its bundled Codex is {version}; it may not load what the Codex CLI set up (loadout needs "
                             "0.161 or newer)" if _codex_cli_here() else
                             f"its bundled Codex is {version}; loadout's Codex setup needs 0.161 or newer",
                             "update the Codex extension in VS Code (Extensions view)"))
        if ext.install.where == "remote-wsl" and windows_only:
            gaps.append(("the Codex extension in a Remote-WSL window reads the WSL ~/.codex, which loadout does not "
                         "set up while your Codex runs on Windows",
                         "open the repo in a Windows window, or set up Codex in WSL with loadout bootstrap "
                         "--codex-side wsl (docs/how-to/wsl.md#codex)"))
    else:
        if ext.install.where == "windows":  # the home first; whether it can start Claude below, for every window
            home = vscode.reads_home(ext)
            if not os.path.isdir(home / "rules" / "loadout"):  # bootstrap.ps1 links the kit's rules there
                gaps.append((printable(f"the Claude Code extension in a Windows window reads {home}, which loadout "
                                       "in WSL does not set up"),
                             "open repos with `code .` from WSL (a Remote-WSL window), or set loadout up on Windows "
                             "with bootstrap.ps1; if you use only Remote-WSL windows, uninstall the extension from "
                             "VS Code on Windows (its Remote-WSL copy stays)"))
        mode = vscode.setting(ext.install, "claudeCode.useTerminal")
        if mode is None and ext.desktop is not None:  # a Remote-WSL window: the desktop's user value, unless overridden
            mode = vscode.setting(ext.desktop, "claudeCode.useTerminal")
        terminal = mode is True
        terminal_ok = terminal and (vscode.windows_claude(ext.install) if ext.install.where == "windows"
                                    else runner.have("claude"))
        if terminal and not terminal_ok:
            if ext.install.where != "windows":
                gaps.append(("terminal mode (claudeCode.useTerminal) starts the claude on PATH, and no claude is on "
                             "PATH", "install Claude Code (loadout bootstrap --install; on native Windows "
                             "bootstrap.ps1 --install), or turn claudeCode.useTerminal off"))
            else:
                gaps.append(("terminal mode (claudeCode.useTerminal) starts the claude on the Windows PATH, and it "
                             "may not find one (none where the Windows installers put it)",
                             "install Claude Code on Windows (bootstrap.ps1 --install), or turn claudeCode.useTerminal "
                             "off"))
        configured = vscode.setting(ext.install, "claudeCode.claudeProcessWrapper")
        if not terminal_ok and isinstance(configured, str) and configured.strip() and vscode.wrapper(ext.install) is None:
            gaps.append((printable(f"claudeCode.claudeProcessWrapper names {configured.strip()}, which is not a file "
                                   "it can run, and the extension starts Claude through it"),
                         f"point it at an installed claude, or remove the setting from {vscode.settings_label(ext.install)}"))
        elif ext.binary is None and not terminal_ok and vscode.wrapper(ext.install) is None:
            # it never uses the claude on PATH, except in terminal mode on Windows
            profile = (" (a VS Code profile sets claudeCode.claudeProcessWrapper; loadout cannot tell which profile "
                       "is active)") if vscode.profile_wrapper(ext.install) else ""
            gaps.append(("the extension has no bundled Claude Code for this platform, so it cannot start Claude"
                         + profile,
                         f"set claudeCode.claudeProcessWrapper in {vscode.settings_label(ext.install)} to an installed "
                         "claude (loadout bootstrap --install installs one), or reinstall the extension"))
    if not gaps:
        return [CheckResult(name, True)]
    return [CheckResult(name, False, detail, fix, "warn") for detail, fix in gaps]


def _vscode_path(found, windows_only: bool = False) -> list[CheckResult]:
    """An MCP server whose command the extension's agent may not find on its PATH: a Remote-WSL window's Codex gets
    VS Code's server PATH (no shell startup file runs there); the others get the shell's PATH (Claude Code reads
    the login shell, a desktop-launched VS Code the shell environment). A Windows window seen from WSL is not
    checked: its PATH is not readable from here. loadout's own plugin servers have their own MCP PATH row."""
    from . import vscode
    from .new_skill import repo_root
    try:
        project = repo_root(Path(os.path.abspath(Path.cwd())))
    except OSError:
        project = None
    rows, seen = [], set()
    for ext in found:
        if (ext.install.where == "windows" and not vscode.runs_in_wsl(ext)) or (ext.agent == "codex" and windows_only):
            continue
        remote = ext.agent == "codex" and ext.install.where == "remote-wsl"
        if (ext.agent, remote) in seen:
            continue
        seen.add((ext.agent, remote))
        if ext.agent == "codex":
            servers = vscode.mcp_commands("codex", project)
        else:
            servers = vscode.mcp_commands("claude", project, plugin=False)
        if remote:
            dirs = vscode.remote_path_dirs()
            missing = sorted(n for n, cmd in servers.items() if not vscode.findable(cmd, dirs))
        else:
            missing = sorted(n for n, cmd in servers.items()
                             if not (vscode.findable(cmd, []) if os.path.isabs(cmd) else runner.which(cmd)))
        if not missing:
            continue
        label = vscode.LABEL[ext.agent]
        if remote:
            rows.append(CheckResult("VS Code PATH", False,
                                    printable(f"in a Remote-WSL window the Codex extension may not find the command "
                                              f"of the MCP servers {', '.join(missing)}: no shell startup files run "
                                              "there"),
                                    "loadout bootstrap --vscode-path puts loadout's tool folders on PATH in "
                                    f"~/{vscode.SERVER_ENV} (then restart VS Code's WSL server: close every Remote-WSL window, run "
                                    "wsl --shutdown in Windows, reopen); for a command elsewhere, use "
                                    "an absolute command in the server entry", "warn"))
        else:
            rows.append(CheckResult("VS Code PATH", False,
                                    printable(f"the {label} extension may not find the command of the MCP servers "
                                              f"{', '.join(missing)}: it is not on your shell's PATH"),
                                    "install it, or use an absolute command in the server entry", "warn"))
    return rows


def _vscode_surfaces(cs=None) -> list[CheckResult]:
    """VS Code's agent extensions, per window type, for the agents that are on (spec Part 4)."""
    from . import targets, vscode
    on = {"claude": targets.claude_enabled(), "codex": targets.codex_enabled()}
    # Codex on in WSL: codex_side already looked for the Windows home, so it is not looked up twice
    found = vscode.extensions(on, win_home=getattr(cs, "windows_home", None), look=cs is None)
    only = _windows_only(cs) if hasattr(cs, "side") else False  # ADR 0029: the WSL Codex home is not theirs
    if only and any(vscode.runs_in_wsl(e) for e in found):
        only = False  # the open folder switches the extension to WSL: the WSL home is the one it reads
    broken = []
    folder = vscode.folder_settings() if found else None
    read = [i for e in found for i in (e.install, e.desktop) if i is not None]  # every install whose settings count
    def opens(install, p) -> str:  # how VS Code opens that file
        if install.user_dir is None:
            return "Preferences: Open Remote Settings (JSON)"
        if p.parent.parent == install.user_dir / "profiles":
            return "switch to that VS Code profile, then Preferences: Open User Settings (JSON)"
        return "Preferences: Open User Settings (JSON)"
    files = [(p, opens(install, p)) for install in dict.fromkeys(read) for p in vscode.broken_settings(install)]
    if folder is not None and os.path.isfile(folder) and vscode.read_jsonc(folder) is None:
        files.append((folder, "Preferences: Open Workspace Settings (JSON)"))  # the folder's: they override the user's
    for p, how in files:
        broken += [CheckResult("VS Code settings", False,
                               printable(f"{p} does not parse, so loadout cannot read the settings that matter there"),
                               f"fix its JSON in VS Code ({how})", "warn")]
    said = bool(cs is not None and getattr(cs, "side", None) in ("wsl", "both") and getattr(cs, "vscode_windows", False))
    return [*broken, *(row for ext in found for row in _surface_rows(ext, only, said)), *_vscode_path(found, only)]


def _repo_mcp_paths() -> list[CheckResult]:
    """The current repo's committed .mcp.json: a server whose command or arguments sit in one person's home cannot
    start for teammates. Reported, never changed; only server names and the home prefix are printed."""
    from .new_skill import repo_root
    try:
        root = repo_root(Path(os.path.abspath(Path.cwd())))
    except OSError:
        return []
    if root is None or Path(os.path.realpath(root)) == Path(os.path.realpath(paths.home())):
        return []
    from . import repo_config
    try:
        if not repo_config.agents(root)["claude"]:
            return []  # .mcp.json is Claude Code's project file; the repo is not for Claude Code (ADR 0030)
    except ValueError:  # an invalid .loadout.json: init, profile and explain stop on it and say why; check stays quiet here
        return []
    path = root / ".mcp.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(servers, dict):
        return []
    hits = {}
    for name, srv in servers.items():
        if not isinstance(srv, dict):
            continue
        args = srv.get("args") if isinstance(srv.get("args"), list) else []
        for value in [srv.get("command"), *args]:
            m = _HOME_PATH.search(value) if isinstance(value, str) else None
            if m:
                hits[name] = m.group(1)
                break
    if not hits:
        return []
    res = runner.run(["git", "-C", str(root), "ls-files", "--error-unmatch", ".mcp.json"], timeout=20)
    if not res.ok:
        return []  # not committed: the person's own file
    names = ", ".join(sorted(hits))
    prefix = sorted(set(hits.values()))[0]
    return [CheckResult("repo .mcp.json", False,  # names and paths come from the repo: printed escaped
                        printable(f"{root}: the committed .mcp.json starts {names} from a path in one person's "
                                  f"home ({prefix}…), so teammates' agents cannot start it"),
                        "move it to local scope (claude mcp add --scope local …) or a user-level server; "
                        "loadout does not change the file", "warn")]


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
    return [*_python(), *_wsl(cs), *_codex_side(cs), *_vscode(cs), *_vscode_surfaces(cs), *_legacy_state(),
            *(_links() if on else []), *_skills_json(), *(_settings() if on else []), *(_plugins() if on else []),
            *_codex(cs), *(_without_codex(_plugin_copies) if _windows_only(cs) else _plugin_copies()), *(_connectors() if on else []), *(_without_codex(_own) if _windows_only(cs) else _own()),
            *_binaries(cs), *_mcp_path(), *_cbm_auto_index(), *(_tool_setups() if on else []), *_cbm_refresh(), *_cbm_conflict(), *_gh(), *_secrets(), *_repos(), *_repo_skill_links(), *_repo_mcp_paths()]


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
