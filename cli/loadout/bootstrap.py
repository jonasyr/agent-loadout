"""`loadout bootstrap` (spec §6.1). Safe to re-run."""
from __future__ import annotations

import codecs
import json
import locale
import os
import re
from pathlib import Path
from typing import Callable

from . import adopt, apply, catalog, check, out, paths, runner, secrets, settings_merge, ui, vscode, wsl
from .backup import Backup
from .jsonio import get_dict, load_json
from .secrets import redact

Ask = Callable[[str], str]
RC_MARKER = "# loadout secrets"
RC_LINE = (f'{RC_MARKER}\n[ -f "$HOME/.config/loadout/secrets.env" ] && '
           '{ set -a; . "$HOME/.config/loadout/secrets.env"; set +a; }\n')
# Parses secrets.env's NAME='value' format (POSIX quoting: '\'' is a literal quote).
# `& { }` runs in a child scope, so no variables leak into the session.
PS_BLOCK = f"""{RC_MARKER}
& {{
  $f = Join-Path $HOME '.config/loadout/secrets.env'
  if (Test-Path $f) {{
    Get-Content -Encoding UTF8 $f | ForEach-Object {{
      if ($_ -match '^\\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {{
        $v = $Matches[2].Trim()
        if ($v.Length -ge 2 -and $v.StartsWith("'") -and $v.EndsWith("'")) {{ $v = $v.Substring(1, $v.Length - 2).Replace("'\\''", "'") }}
        elseif ($v.Length -ge 2 -and $v.StartsWith('"') -and $v.EndsWith('"')) {{ $v = $v.Substring(1, $v.Length - 2) }}
        [Environment]::SetEnvironmentVariable($Matches[1], $v, 'Process')
      }}
    }}
  }}
}}
"""
POLICY_NOTE = ("PowerShell's execution policy is Restricted, so profiles (and the secrets loader) do not run. "
               "To allow them: Set-ExecutionPolicy -Scope CurrentUser RemoteSigned")


INTRO = "loadout sets up your coding agent with a reviewed kit of plugins, rules and tools."
PROBLEM = out.PROBLEM
INSTALL_FAILED_HINT = "the install failed (see above); fix that, then run loadout bootstrap --install again"


def _step(title: str) -> None:
    if out.VERBOSE:
        print(f"\n== {title}")


def _tilde(path: Path) -> str:
    home = str(paths.home())
    return "~" + str(path)[len(home):] if str(path).startswith(home) else str(path)


def _report(name: str, summary: str, lines: list[str] = (), level: str = "ok") -> None:
    """One status line; problem lines always follow it, the rest only with --verbose."""
    bad = [line for line in lines if PROBLEM.search(line)]
    out.status(name, summary, "warn" if bad and level == "ok" else level)
    for line in lines:
        if line.removeprefix(f"{name}: ") == summary:
            continue  # only repeats the status line
        (out.problem if line in bad else out.detail)(line)


def _prereq_summary(missing: list[str], installed: list[str],
                    recommended: frozenset = frozenset()) -> tuple[str, str]:
    entries = [e for e in catalog.binaries() if not e.get("helper") and _wanted(e)]
    ready = sum(1 for e in entries if not missing_binary(e["id"]))
    text = f"{ready} tools ready"
    if installed:
        text += f", installed {', '.join(installed)}"
    if missing:
        text += f", missing {', '.join(missing)}"
    required = {e["id"] for e in entries if e.get("required")}
    return text, ("fail" if set(missing) & (required - recommended) else "warn" if missing else "ok")


MANUAL_STEPS = {
    "git": {"linux": "sudo apt install git   (Debian/Ubuntu; other distros: their package manager)",
            "macos": "xcode-select --install",
            "windows": "winget install --id Git.Git -e   (Git Bash runs the hooks)"},
}


def os_key() -> str:
    import sys
    if paths.platform_key() == "windows":
        return "windows"
    return "macos" if sys.platform == "darwin" else "linux"


def _claude_logged_in() -> bool:
    try:
        return bool(load_json(paths.claude_json()).get("oauthAccount"))
    except Exception:
        return False


PERSONAL_REPO_HOWTO = "docs/how-to/personal-repo.md"


def still_to_do(key: str, codex_here: bool = True) -> list[str]:
    out = []
    if not runner.have("git"):
        out.append(f"install git: {MANUAL_STEPS['git'][key]}")
    from . import targets
    if targets.claude_enabled() and runner.have("claude") and not _claude_logged_in():
        out.append("log in to Claude Code: claude   (or set ANTHROPIC_API_KEY)")
    if runner.have("gh") and not runner.run(["gh", "auth", "status"], timeout=20).ok:
        out.append("log in to GitHub: `gh auth login`, then `gh auth setup-git`")
    from . import codex
    out += codex.open_steps() if codex_here else []  # the Windows side: its steps belong to bootstrap.ps1
    if paths.personal_root().is_dir() and not (paths.personal_root() / ".git").exists():
        out.append(f"optional: keep your personal layer in a private git repo to sync it: {_tilde(paths.kit_root() / PERSONAL_REPO_HOWTO)}")
    return out


def npm_global_dir() -> Path | None:
    """Windows: npm puts global commands into its prefix, which can be anywhere (mise's Node, Node's installer,
    an npmrc), and mise's shims do not cover them. POSIX needs no lookup: mise reshim and ~/.local/bin cover it."""
    if paths.platform_key() != "windows" or not runner.have("npm"):
        return None
    res = runner.run(["npm", "prefix", "-g"], cwd=str(paths.home()), timeout=60)
    found = Path(res.stdout.strip()) if res.ok and res.stdout.strip() else None
    return found if found and found.is_dir() else None


def prepend_tool_dirs(extra: list[Path] | None = None) -> None:
    parts = os.environ.get("PATH", "").split(os.pathsep)
    new = [str(d) for d in [*paths.tool_dirs(), *(extra or [])] if str(d) not in parts]
    if new:
        os.environ["PATH"] = os.pathsep.join(new + [p for p in parts if p])


def _wanted(entry: dict) -> bool:
    return bool(entry.get("required") or entry["status"] == "recommended")


def _ensure_local_bin() -> None:
    """Installers create ~/.local/bin with the umask, which is 002 on Debian and Ubuntu;
    codebase-memory-mcp refuses a folder that others can write to."""
    d = paths.home() / ".local" / "bin"
    if paths.platform_key() == "windows" or d.exists():
        return
    d.mkdir(parents=True)
    d.chmod(0o755)


def _open_local_bin_hint() -> str:
    d = paths.home() / ".local" / "bin"
    try:
        mode = d.stat().st_mode & 0o777
    except OSError:
        return ""
    if paths.platform_key() == "windows" or not mode & 0o022:
        return ""
    return (f"note: {d} can be written by other users (mode {mode:04o}), and some installers refuse that.\n"
            f"fix: chmod go-w {d}   then run this again")


def _tail(res: runner.Result, limit: int = 400) -> str:
    text = (res.stderr.strip() or res.stdout.strip())[-limit:]
    return text.split("\n", 1)[1] if len(text) == limit and "\n" in text else text


def missing_binary(name: str) -> bool:
    """Not on PATH, or (in WSL) one that resolves to a Windows program under /mnt/<drive>/ (node also when its npm
    does): --install then installs the Linux copy in the home; the Windows one stays untouched."""
    if not runner.have(name):
        return True
    if wsl.detect() is None:
        return False
    return any(wsl.is_windows_program(n) for n in (("node", "npm") if name == "node" else (name,)))


def _linux_folder(name: str) -> str:
    """Where the Linux copy of a tool lands: the tool folder that holds it, else (before an install) mise's shims
    folder for a tool mise installs, else ~/.local/bin."""
    for d in paths.tool_dirs():
        if (d / name).exists():
            return str(d)
    entry = next((e for e in catalog.binaries() if e["id"] == name), None)
    if entry and any(cmd and cmd[0] == "mise" for cmd in catalog.platform_cmds(entry, "install")):
        return "~/.local/share/mise/shims"
    return "~/.local/bin"


def windows_first(name: str) -> bool:
    """WSL: the tool (for node: node or its npm) resolves to the Windows program."""
    return wsl.detect() is not None and any(wsl.is_windows_program(n)
                                            for n in (("node", "npm") if name == "node" else (name,)))


def _linux_copy_first(name: str) -> bool:
    """WSL, right after an install: put the folder that holds the new Linux copy first in this run's PATH, so the
    next installs (npm install -g, mise use) run the Linux tool, not the Windows one; new shells still need the
    profile line. Returns whether the Linux copy is now the one found."""
    for d in paths.tool_dirs():  # try each folder that has it: an older copy (node without npm) may not suffice
        if (d / name).is_file():
            parts = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p and p != str(d)]
            os.environ["PATH"] = os.pathsep.join([str(d), *parts])
            if not missing_binary(name):
                return True
    return not missing_binary(name)


def _windows_first_note(name: str, installed: bool = False) -> str:
    """A WSL line for a tool whose Windows copy is still found first. Bootstrap does not change the PATH order."""
    folder = _linux_folder(name)
    shown = next((n for n in (("node", "npm") if name == "node" else (name,)) if wsl.is_windows_program(n)), name)
    found = runner.which(shown)  # for node: whichever of node or npm is the Windows program
    still = "still " if installed else ""
    return (f"{shown} {still}resolves to the Windows program {found}; the Windows one stays untouched. Put {folder} "
            f"first in PATH (a line in your shell profile: export PATH=\"{folder}:$PATH\"), or set "
            "`appendWindowsPath = false` in `/etc/wsl.conf`; bootstrap does not change the order")


RECOMMENDED_WHY = {"codex": "optional next to VS Code's Codex extension, for codex in a terminal",
                   "claude": "VS Code's Claude Code extension's own runs loadout's claude commands meanwhile"}
CLAUDE_BUNDLED = ("not on PATH: loadout runs VS Code's Claude Code extension's own ({path}) for claude plugin and "
                  "claude mcp; --install puts a claude on PATH for the terminal")


def _claude_bundled_line(path: Path) -> str:
    """The plan line naming the bundled binary; its folder name is printed escaped."""
    return CLAUDE_BUNDLED.format(path=out.printable(str(path)))


def missing_tools(skip: set[str] = frozenset(), recommended: set[str] = frozenset()
                  ) -> list[tuple[dict, list[list[str]], bool]]:
    """The wanted binaries that are missing, in install order, with their install commands; nothing runs.
    A helper is listed only when a missing, wanted binary needs it. optional: a recommended tool (or one named in
    recommended), which a person may leave out; a helper is optional when only optional tools need it."""
    prepend_tool_dirs()
    entries = [e for e in catalog.install_order(catalog.binaries()) if e["id"] not in skip]

    def optional(e: dict) -> bool:
        return not e.get("required") or e["id"] in recommended
    wanting = [e for e in entries if not e.get("helper") and _wanted(e) and missing_binary(e["id"])]
    needed = {d for e in wanting for d in e.get("needs", [])}
    found = []
    for entry in entries:
        name = entry["id"]
        wanted = name in needed if entry.get("helper") else _wanted(entry)
        if not wanted or not missing_binary(name):
            continue
        opt = (all(optional(e) for e in wanting if name in e.get("needs", [])) if entry.get("helper")
               else optional(entry))
        found.append((entry, catalog.platform_cmds(entry, "install"), opt))
    return found


def install_tool(entry: dict, cmds: list[list[str]], on_problem=None) -> tuple[bool, list[str]]:
    """Runs a tool's install commands (progress lines print at once: an install can take minutes).
    Returns whether the tool is there afterwards and the problem lines; on_problem, when given, also gets each
    problem line as it happens (between the commands)."""
    from . import pkgmgr
    name, lines = entry["id"], []
    for cmd in cmds:
        if out.VERBOSE:
            print(redact("installing: " + " ".join(cmd)))
        elif cmd is cmds[0]:
            print(f"  installing {name}…")
        res = runner.run(cmd, cwd=pkgmgr.run_cwd(cmd), timeout=900)
        if not res.ok:
            found = [f"failed to install {name}: {_tail(res)}", _open_local_bin_hint()]
            for line in filter(None, found):
                lines.append(line)
                if on_problem is not None:
                    on_problem(line)
    npm = npm_global_dir() if any(cmd[0] == "npm" for cmd in cmds) else None
    prepend_tool_dirs([npm] if npm else None)
    if name in ("playwright-cli", "pyright", "typescript-language-server") and runner.have("mise"):
        runner.run(["mise", "reshim"], cwd=pkgmgr.run_cwd(["mise"]), timeout=120)  # shims for npm globals
        prepend_tool_dirs()
    return not missing_binary(name), lines


def check_prereqs(install: bool, ask: Ask, installed: list | None = None, notes: list | None = None,
                  skip: frozenset = frozenset(), recommended: frozenset = frozenset()) -> list[str]:
    """notes: collects the missing and failed lines for the caller to print under its status line (else printed now).
    skip: binaries not wanted this run (codex when, in WSL, the user's Codex is the Windows one).
    Progress lines ("installing …") always print at once: an install can take minutes."""
    def note(line: str, problem: bool = False) -> None:
        if notes is not None:
            notes.append(line)
        elif problem:
            out.problem(line)
        else:
            print(line)
    if install:
        _ensure_local_bin()
    missing, failed, tried = [], set(), set()
    for entry, cmds, _optional in missing_tools(skip, recommended):
        name = entry["id"]
        if not missing_binary(name):  # an earlier install brought it
            continue
        blocked = [d for d in entry.get("needs", []) if d in failed]
        if install and cmds and blocked:
            failed.add(name)
            if not entry.get("helper"):
                note(f"missing {name}: not installed because {', '.join(blocked)} failed to install")
                missing.append(name)
            continue
        if install and cmds:
            tried.add(name)
            _, problems = install_tool(entry, cmds, on_problem=lambda line: note(line, problem=True))
            if installed is not None and not missing_binary(name) and not entry.get("helper"):
                installed.append(name)
            if missing_binary(name) and windows_first(name):
                note(_windows_first_note(name, installed=True), problem=True)
                if _linux_copy_first(name):  # also after a failed reinstall: an existing Linux copy may do
                    if installed is not None and not entry.get("helper"):
                        installed.append(name)
                    continue  # this run uses the Linux copy now; new shells need the PATH line the note names
                if not problems:  # no Linux copy to put first: what needs it must not run the Windows tool
                    failed.add(name)
                    if not entry.get("helper"):
                        note(f"missing {name}: the install left no Linux {name} to use; what needs it waits")
                        missing.append(name)
                    continue
        if missing_binary(name):
            failed.add(name)
            if not entry.get("helper"):
                if name in tried:
                    hint = f"install it by hand: {entry['manual']}" if entry.get("manual") else INSTALL_FAILED_HINT
                else:
                    hint = "re-run with --install" if cmds else entry.get("manual", "")
                if wsl.detect() is not None and wsl.is_windows_program(name):
                    if cmds:
                        hint = f"{hint}; {_windows_first_note(name)}"
                    elif name == "git":
                        hint = "install git inside WSL with your package manager (sudo apt install git)"
                why = RECOMMENDED_WHY.get(name, "") if name in recommended else ""
                tag = f"({why}) " if why else "(required) " if entry.get("required") else ""
                note(f"missing {tag}{name}: {hint}")
                missing.append(name)
    if not _gh_for_git() and runner.have("gh"):
        note("gh is not logged in: run `gh auth login` (needed for private marketplaces)", problem=True)
    return missing


def _gh_for_git() -> bool:
    """A logged-in gh becomes git's GitHub credential helper. Returns whether gh is logged in."""
    if not runner.have("gh") or not runner.run(["gh", "auth", "status"], timeout=20).ok:
        return False
    if runner.run(["gh", "auth", "setup-git"], timeout=20).ok:
        out.detail("git uses your gh login for GitHub (gh auth setup-git; undo: git config --global --unset-all credential.https://github.com.helper)")
    return True


def ensure_personal(ask: Ask, bk: Backup | None = None, interactive: bool | None = None,
                    before_starter=None, personal: str | None = None, given=None,
                    ask_missing: bool = True) -> tuple[str, bool]:
    """Returns (message, ok). ok is False only when a clone was asked for and failed.
    before_starter: called before a starter layer asks its questions (bootstrap settles the agents there).
    personal: --personal (new, or a git URL to clone); given: --answers for a starter layer;
    ask_missing False: nothing is asked (no terminal, or --yes)."""
    bk = bk if bk is not None else Backup(description="bootstrap")
    interactive = ui.is_interactive() if interactive is None else interactive
    root = paths.personal_root()
    if root.exists():
        return f"personal layer: {root}", True
    if personal is not None:
        url = "" if personal == "new" else personal
    elif ask_missing:
        url = ask("Personal layer: git URL to clone (empty = create a starter one): ").strip()
    else:
        url = ""
    if url:
        prepend_tool_dirs()  # the clone runs before the prerequisites step: find tools installed earlier,
        _gh_for_git()        # and let a logged-in gh answer for git (a private HTTPS repo)
        # no prompt: output is captured, so git's password prompt would be invisible and wait until the timeout
        res = runner.run(["git", "clone", "--", url, str(root)], timeout=300,
                         env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        if res.ok:
            return f"cloned {redact(url)} -> {root}", True
        access = ("log in with `gh auth login`, then `gh auth setup-git`, or use an SSH URL" if runner.have("gh")
                  else "use an SSH URL, or install gh (bootstrap --install) and log in")
        return (f"clone failed: {redact(res.stderr.strip())}\n"
                f"  {access}, then re-run bootstrap; continuing without a personal layer"), False
    if before_starter is not None:
        before_starter()
    root.mkdir(parents=True, exist_ok=True)
    (root / "settings.json").write_text("{}\n", encoding="utf-8")
    bk.record_created(root / "settings.json", "created personal settings.json")
    from .configure import _about_you, ask_preferences
    _about_you(ask, bk, given=given.about if given else None, ask_missing=ask_missing)
    ask_preferences(ask, fill_defaults=True, interactive=interactive and ask_missing, bk=bk, quick=True,
                    given=given.prefs if given else None)
    return f"created starter personal layer at {root} (to sync it across machines, make it a private git repo: {_tilde(paths.kit_root() / PERSONAL_REPO_HOWTO)})", True


_MARKET_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def listed_marketplaces() -> set[str] | None:
    """The marketplace names Claude Code has added (`claude plugin marketplace list --json`); when that output is
    not usable JSON, the names from its text form, up to the "From claude.ai:" section (offered there, not added).
    When `--json` fails (an older Claude Code without it), the plain list once. None only when that fails too."""
    res = runner.run(["claude", "plugin", "marketplace", "list", "--json"], timeout=60)
    if not res.ok:
        res = runner.run(["claude", "plugin", "marketplace", "list"], timeout=60)
        if not res.ok:
            return None
    try:
        data = json.loads(res.stdout)
    except ValueError:
        data = None
    if isinstance(data, list):
        return {e["name"] for e in data if isinstance(e, dict) and isinstance(e.get("name"), str)}
    names = set()
    for line in res.stdout.splitlines():
        line = line.strip()
        if line == "From claude.ai:":
            break
        line = line.removeprefix("❯").strip()
        if not line or line.endswith(":"):
            continue
        token = line.split()[0]
        if _MARKET_NAME.fullmatch(token):
            names.add(token)
    return names


def plugins_plan() -> tuple[list[str], list[tuple[str, str]], list[str]]:
    """What setup_plugins would do, without changing anything (it only lists the marketplaces): the skip lines, the
    kit marketplaces to add as (name, origin), and the enabled plugins not installed yet. A declared marketplace is
    added only when it is loadout's own or an enabled plugin comes from it. An enabled plugin's marketplace that the
    merged settings do not declare but a kit profile does (`thesis`'s, ADR 0037) is added from the profile's
    declaration; settings.json does not get it."""
    from . import profiles
    out = []
    desired = settings_merge.desired_settings()
    listed = listed_marketplaces() or set()
    enabled = [pid for pid, on in get_dict(desired, "enabledPlugins").items() if on]
    used = {pid.rpartition("@")[2] for pid in enabled if "@" in pid}
    declared = get_dict(desired, "extraKnownMarketplaces")
    kit = profiles.kit_marketplaces()
    from_kit = {name: kit[name] for name in sorted(used) if name not in declared and name in kit}
    markets = []
    for name, cfg in {**declared, **from_kit}.items():
        if name in listed or (name != "agent-loadout" and name not in used):
            continue
        src = get_dict(cfg, "source")
        origin = src.get("repo") or src.get("url")
        if not isinstance(origin, str):
            out.append(f"marketplace {name}: skipped, no repo or url in its source (fix it in your personal settings.json)")
            continue
        markets.append((name, origin))
    installed = get_dict(load_json(paths.claude_home() / "plugins" / "installed_plugins.json"), "plugins")
    plugins = [pid for pid in enabled if pid not in installed]
    return out, markets, plugins


def setup_plugins(say=None, planned: tuple | None = None) -> list[str]:
    """say: called with a progress line before each slow step (marketplace clones, plugin installs).
    planned: (marketplaces as (name, origin), plugin ids) to run exactly, as a plan showed them (ADR 0011);
    None plans now (plugins_plan)."""
    say = say or (lambda line: None)
    out, markets, plugins = plugins_plan() if planned is None else ([], list(planned[0]), list(planned[1]))
    total, step = len(markets) + len(plugins), 0
    for name, origin in markets:
        step += 1
        say(f"  adding marketplace {origin}, a git clone ({step} of {total})…")
        res = runner.run(["claude", "plugin", "marketplace", "add", origin], timeout=300)
        out.append(f"marketplace {name}: {'added' if res.ok else 'failed: ' + res.stderr.strip()}")
    for plugin_id in plugins:
        step += 1
        say(f"  installing plugin {plugin_id} ({step} of {total})…")
        res = runner.run(["claude", "plugin", "install", plugin_id, "--scope", "user"], timeout=600)
        out.append(f"plugin {plugin_id}: {'installed' if res.ok else 'failed: ' + res.stderr.strip()}")
    return out


def _decode_profile(raw: bytes) -> tuple[str, str]:
    """PowerShell 5.1 writes UTF-16 (Out-File, >) or ANSI; keep whatever the file uses."""
    if raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return raw.decode("utf-16"), "utf-16"
    if raw.startswith(codecs.BOM_UTF8):
        return raw.decode("utf-8-sig"), "utf-8-sig"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        enc = locale.getpreferredencoding(False)
        # surrogateescape: undecodable bytes survive the round trip unchanged
        return raw.decode(enc, errors="surrogateescape"), enc


def _powershell_profiles() -> tuple[list[Path], list[str]]:
    targets, notes = [], []
    for exe in ("powershell", "pwsh"):  # Windows PowerShell 5.1 and PowerShell 7 use different profiles
        if not runner.have(exe):
            continue
        res = runner.run([exe, "-NoProfile", "-Command", "$PROFILE"], timeout=30)
        if res.ok and res.stdout.strip():
            targets.append(Path(res.stdout.strip()))
    for exe in ("powershell", "pwsh"):
        if runner.have(exe):
            policy = runner.run([exe, "-NoProfile", "-Command", "Get-ExecutionPolicy"], timeout=30)
            if policy.ok and policy.stdout.strip() == "Restricted":
                notes.append(POLICY_NOTE)
            break
    return list(dict.fromkeys(targets)), notes


def _add_block(rc: Path, block: str, bk: Backup | None, windows: bool,
               marker: str = RC_MARKER, what: str = "secrets loading") -> str | None:
    if rc.exists():
        raw = rc.read_bytes()
        if windows:
            text, enc = _decode_profile(raw)
            if marker in text:
                return None
            if "\r\n" in text:
                block = block.replace("\n", "\r\n")
            sep = "" if not text or text.endswith("\n") else ("\r\n" if "\r\n" in text else "\n")
            # encode the whole text again so a UTF-16 profile stays UTF-16 (one BOM, at the start)
            data = (text + sep + block).encode(enc, errors="surrogateescape")
            if bk is not None:
                bk.save_copy(rc, f"{rc} before adding {what}")
            from .jsonio import write_atomic_bytes
            write_atomic_bytes(rc, data)
        else:
            if marker.encode() in raw:
                return None
            with rc.open("ab") as fh:  # append: never re-encode the user's rc file
                fh.write((b"" if not raw or raw.endswith(b"\n") else b"\n") + block.encode("utf-8"))
        return f"added {what} to {rc}"
    rc.parent.mkdir(parents=True, exist_ok=True)
    rc.write_bytes(block.encode("utf-8"))
    if bk is not None:
        bk.record_created(rc, f"created {rc}")
    return f"created {rc} with {what}"


def setup_secrets(bk: Backup | None = None) -> list[str]:
    out = []
    path = paths.secrets_file()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write((paths.kit_root() / "secrets.env.example").read_text(encoding="utf-8"))
        if bk is not None:
            bk.record_created(path, "created secrets.env")
        out.append(f"created {path}")
    if os.name != "nt":
        os.chmod(path, 0o600)
    windows = paths.platform_key() == "windows"
    if windows:
        targets, notes = _powershell_profiles()
        block = PS_BLOCK
        out += notes
    else:
        home = paths.home()
        targets = [r for r in (home / ".bashrc", home / ".zshrc") if r.exists()]
        shell = os.path.basename(os.environ.get("SHELL", ""))
        own = {"zsh": home / ".zshrc", "bash": home / ".bashrc"}.get(shell)
        if own is not None and own not in targets:
            targets.append(own)  # always the rc of the user's shell (macOS: zsh, often with an old .bashrc)
        if not targets:
            targets = [home / ".bashrc"]
        block = RC_LINE
    for rc in targets:
        line = _add_block(rc, block, bk, windows)
        if line:
            out.append(line)
    empty = [name for name, value in secrets.load_env(path).items() if value == ""]
    if empty:
        out.append(f"empty secrets: {', '.join(empty)}")
    return out


PATH_MARKER = "# loadout PATH"
PATH_END = "# loadout PATH end"
# One read-modify-write of the user PATH, in PowerShell. Values travel in environment variables (never
# spliced into the command), the old value is saved as UTF-8 before anything changes, and only a fixed
# ASCII status comes back on stdout (Windows PowerShell writes stdout in the OEM code page).
WIN_PATH_SCRIPT = r"""$ErrorActionPreference = 'Stop'
$k = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('Environment')
$old = [string]$k.GetValue('Path', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
$parts = @($old -split ';' | Where-Object { $_ })
function Norm([string]$x) { $x.Replace('\', '/').TrimEnd('/').ToLowerInvariant() }
$have = @{}
foreach ($p in $parts) { $have[(Norm $p)] = 1; $have[(Norm ([Environment]::ExpandEnvironmentVariables($p)))] = 1 }
$want = @($env:LOADOUT_PATH_ADD -split "`n" | Where-Object { $_ })
$added = @(); $idx = @()
for ($i = 0; $i -lt $want.Count; $i++) {
  if (-not $have.ContainsKey((Norm $want[$i]))) { $added += $want[$i]; $idx += $i; $have[(Norm $want[$i])] = 1 }
}
if ($added.Count -eq 0) { 'UNCHANGED'; exit 0 }
[IO.File]::WriteAllText($env:LOADOUT_PATH_BACKUP, $old, (New-Object System.Text.UTF8Encoding $false))
$k.SetValue('Path', (($added + $parts) -join ';'), [Microsoft.Win32.RegistryValueKind]::ExpandString)
$k.Close()
[Environment]::SetEnvironmentVariable('LOADOUT_PATH_REFRESH', $null, 'User')  # broadcasts WM_SETTINGCHANGE
'CHANGED ' + ($idx -join ' ')
"""


def _path_block(dirs: list[Path]) -> str:
    home = paths.home()
    lines = [PATH_MARKER]
    for d in reversed(dirs):  # prepend in reverse, so the first folder ends up first
        rel = d.relative_to(home).as_posix()
        lines.append(f'case ":$PATH:" in *":$HOME/{rel}:"*) ;; *) PATH="$HOME/{rel}":"$PATH" ;; esac')
    lines.append("export PATH")
    lines.append(PATH_END)
    return "\n".join(lines) + "\n"


def _refresh_path_block(rc: Path, block: str, bk: Backup | None) -> str | None:
    """A profile that already has our block gets it replaced when the content differs; the rest stays as is."""
    raw = rc.read_bytes() if rc.exists() else b""
    nl = b"\r\n" if raw.find(PATH_MARKER.encode() + b"\r\n") >= 0 else b"\n"  # keep a CRLF profile CRLF
    start = raw.find(PATH_MARKER.encode() + nl)
    if start < 0:
        return None  # no block yet: the caller appends one
    end_tag = PATH_END.encode() + nl
    end = raw.find(end_tag, start)
    if end >= 0:
        end += len(end_tag)
    else:  # a block without end marker ends at its `export PATH`
        tail = b"export PATH" + nl
        end = raw.find(tail, start)
        if end < 0:
            return ""
        end += len(tail)
    new = block.encode("utf-8").replace(b"\n", nl)
    if raw[start:end] == new:
        return ""
    if bk is not None:
        bk.save_copy(rc, f"{rc} before updating the tool folders on PATH")
    from .jsonio import write_atomic_bytes
    write_atomic_bytes(rc, raw[:start] + new + raw[end:])
    return f"updated the tool folders on PATH in {rc}"


def setup_path(bk: Backup | None = None) -> tuple[list[str], bool]:
    """Make the folders user-space installers use visible to new terminals (and to Claude Code).
    Returns (lines to print, whether anything changed)."""
    home = paths.home()
    dirs = [d for d in paths.tool_dirs() if d == home or home in d.parents]
    if not dirs:
        return [], False
    if paths.platform_key() == "windows":
        npm = npm_global_dir()  # may be outside home (e.g. C:\npm\prefix from an npmrc)
        return _setup_windows_path(dirs + [npm] if npm and npm not in dirs else dirs, bk)
    shell = os.path.basename(os.environ.get("SHELL", ""))
    targets = [r for r in (home / ".bashrc", home / ".zshrc") if r.exists()]
    own = {"zsh": home / ".zshrc", "bash": home / ".bashrc"}.get(shell)
    if own is not None and own not in targets:
        targets.append(own)
    # login shells (bash -l, hook shells, CI) skip an interactive-only .bashrc
    login = home / ".bash_profile" if (home / ".bash_profile").exists() else home / ".profile"
    targets.append(login)
    block = _path_block(dirs)
    out = []
    for rc in dict.fromkeys(targets):
        line = _refresh_path_block(rc, block, bk)
        if line is None:
            line = _add_block(rc, block, bk, False, marker=PATH_MARKER, what="the tool folders to PATH")
        if line:
            out.append(line)
    return out, bool(out)



SERVER_ENV_QUESTION = ("Add loadout's tool folders to PATH for VS Code's Remote-WSL windows "
                       "(~/.vscode-server/server-env-setup, backup first)? [y/N] ")
SERVER_ENV_AFTER = ("takes effect when VS Code's WSL server restarts: close every Remote-WSL window, run "
                    "wsl --shutdown in Windows (it stops every WSL distro), then reopen the folder")


def vscode_path_wanted() -> bool:
    """In WSL with VS Code's Remote-WSL server (~/.vscode-server): its windows run no shell startup file."""
    return wsl.detect() is not None and (paths.home() / ".vscode-server").is_dir()


def _home_tool_dirs() -> list[Path]:
    home = paths.home()
    return [d for d in paths.tool_dirs() if d == home or home in d.parents]


def setup_vscode_path(bk: Backup | None) -> str:
    """Add or refresh loadout's PATH block in ~/.vscode-server/server-env-setup; the user's lines stay byte for byte.
    Returns the line to print, "" when nothing changed."""
    from . import vscode
    dirs = _home_tool_dirs()
    if not dirs:
        return ""
    target = paths.home() / vscode.SERVER_ENV
    if target.is_symlink():  # a dotfiles link, dangling or not: write and record its target, the link stays
        target = Path(os.path.realpath(target))
    block = _path_block(dirs)
    line = _refresh_path_block(target, block, bk)
    if line is None and target.exists():
        raw = target.read_bytes()
        if bk is not None:  # the addition is undone from the copy
            bk.save_copy(target, f"{target} before adding the tool folders to PATH")
        from .jsonio import write_atomic_bytes  # the user's bytes plus the block, never half a block
        write_atomic_bytes(target, raw + (b"" if not raw or raw.endswith(b"\n") else b"\n") + block.encode("utf-8"))
        line = f"added the tool folders to PATH to {target}"
    elif line is None:
        line = _add_block(target, block, bk, False, marker=PATH_MARKER, what="the tool folders to PATH")
    return line or ""


def _vscode_path_step(ask: Ask, interactive: bool, flag: bool, bk: Backup | None) -> None:
    """--vscode-path, or a yes in a terminal when a tool folder is missing from the Remote-WSL PATH; a block written
    earlier is kept current (spec Part 3)."""
    from . import vscode
    if not vscode_path_wanted():
        if flag:
            out.status("VS Code PATH", "--vscode-path applies in WSL with VS Code's Remote-WSL server "
                                       "(~/.vscode-server); nothing changed", "warn")
        return
    target = paths.home() / vscode.SERVER_ENV
    try:
        ours = PATH_MARKER.encode() in target.read_bytes()
    except OSError:
        ours = False
    if not (flag or ours):
        have = set(vscode.remote_path_dirs())
        missing = [d for d in _home_tool_dirs() if str(d) not in have]
        if not missing or not interactive:
            return
        print(f"\nplan: add a PATH block to {target} for {', '.join(map(str, missing))} "
              f"({SERVER_ENV_AFTER}; undo: loadout restore)")
        if not ui.confirm(ask, SERVER_ENV_QUESTION):
            return
    line = setup_vscode_path(bk)
    if line:
        out.status("VS Code PATH", f"{line}; {SERVER_ENV_AFTER}", "ok")
    elif flag:
        out.status("VS Code PATH", f"already set up in {target}", "ok")

def _win_path_command() -> list[str]:
    import base64
    encoded = base64.b64encode(WIN_PATH_SCRIPT.encode("utf-16-le")).decode("ascii")
    return ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded]


def _setup_windows_path(dirs: list[Path], bk: Backup | None) -> tuple[list[str], bool]:
    failed = [f"could not update your user PATH; add {', '.join(map(str, dirs))} to it by hand"], False
    state = paths.state_dir()
    state.mkdir(parents=True, exist_ok=True)
    saved = state / f"user-PATH-before-{os.getpid()}.txt"
    env = {**os.environ, "LOADOUT_PATH_ADD": "\n".join(map(str, dirs)), "LOADOUT_PATH_BACKUP": str(saved)}
    try:
        res = runner.run(_win_path_command(), timeout=60, env=env)
        words = res.stdout.split()
        if not res.ok or not words or words[0] not in ("CHANGED", "UNCHANGED"):
            return failed
        if words[0] == "UNCHANGED":
            return [], False
        added = [str(dirs[int(i)]) for i in words[1:] if i.isdigit() and int(i) < len(dirs)] or list(map(str, dirs))
        if saved.is_file():
            (bk if bk is not None else Backup(description="user PATH")).keep(
                saved, "your user PATH before loadout added the tool folders")
        return [f"added {', '.join(added)} to your user PATH (old value saved in the backup)"], True
    finally:
        saved.unlink(missing_ok=True)


AGENT_QUESTION = "Which coding agents should loadout set up?  1) Claude Code  2) Codex  3) both  [{default}] "
_ANSWERS = {"1": {"claude": True, "codex": False}, "2": {"claude": False, "codex": True},
            "3": {"claude": True, "codex": True}}


def choose_agents(ask, interactive: bool, flag) -> dict:
    return _choose_agents(ask, interactive, flag)[0]


def _codex_seen() -> bool:
    """A Codex on PATH, or (in WSL) a Windows codex.exe: worth asking which agents to set up."""
    return runner.have("codex") or (wsl.detect() is not None and bool(runner.which("codex.exe")))


CODEX_SIDE_QUESTION = ("Your Codex runs on Windows. Set loadout up for:  1) Codex in WSL (installs Codex here; switch the "
                       "VS Code extension to WSL)  2) Codex on Windows (run bootstrap.ps1 in PowerShell)  [1] ")
WINDOWS_WAY = ("Codex on Windows: run loadout's bootstrap.ps1 in PowerShell there, with the same personal layer "
               "(docs/how-to/wsl.md#codex)")


SKIPPED = "Codex step skipped: "


def codex_gate_needed(chosen: dict) -> bool:
    return bool(chosen.get("codex")) and wsl.detect() is not None


VSCODE_QUESTION = "Switch the VS Code Codex extension to WSL now (settings.json, backup first)? [y/N] "


def _offer_vscode(cs, ask, bk) -> None:
    """After choosing Codex in WSL: VS Code's extension still runs the Windows Codex until its switch is on."""
    home = cs.windows_home
    if home is None or not wsl.vscode_settings(home).is_file() or wsl.vscode_wsl_mode(home) is True:
        return
    if not ask(VSCODE_QUESTION).strip().lower().startswith("y"):
        return
    message = wsl.set_vscode_wsl_mode(bk, home) if bk is not None else wsl.MANUAL
    out.status("VS Code", message, _vscode_level(message))


VSCODE_FLAG_HINT = "or run bootstrap again with --vscode-wsl"
VSCODE_DONE = ("VS Code: the Codex extension now runs", "VS Code already runs Codex in WSL")


CODEX_CLI_QUESTION = ("\nVS Code's Codex extension runs its own Codex, and loadout sets it up fully. "
                      "Install the Codex CLI too (optional, for codex in a terminal)? [y/N] ")
CODEX_CLI_WHY = "installed alongside VS Code's Codex extension (optional, for codex in a terminal)"
CODEX_CLI_DECLINED = "not installed (optional): VS Code's Codex extension runs its own, and loadout set Codex up for it"


CLAUDE_CLI_QUESTION = ("\nVS Code's Claude Code extension runs its own claude, and loadout sets it up fully. "
                       "Install the Claude Code CLI too (optional, for claude in a terminal)? [y/N] ")
CLAUDE_CLI_WHY = "installed alongside VS Code's Claude Code extension (optional, for claude in a terminal)"
CLAUDE_CLI_DECLINED = vscode.CLAUDE_CLI_OPTIONAL


def claude_cli_choice(install: bool, ask: Ask, interactive: bool, wanted: bool,
                      bundled: Path | None) -> tuple[str | None, bool]:
    """(the Claude Code CLI line to print or None, skip its install): as codex_cli_choice, for a missing claude next
    to VS Code's Claude Code extension, whose bundled claude runs loadout's commands (spec 2026-10-29 G3)."""
    if runner.have("claude") or bundled is None:
        return None, False
    if not wanted:
        return CLAUDE_CLI_DECLINED, True
    if not install:
        return None, False  # nothing installs this run; the missing line says it is recommended
    if interactive and ask(CLAUDE_CLI_QUESTION).strip().lower() not in ("y", "yes"):  # optional: no unless asked
        return CLAUDE_CLI_DECLINED, True
    return CLAUDE_CLI_WHY, False


def codex_recommended(chosen: dict, gate) -> frozenset:
    """{"codex"} when the Codex CLI is recommended, not required: no codex on PATH and VS Code's Codex extension on
    this side runs a usable one."""
    from . import codex
    if not chosen.get("codex") or gate or runner.have("codex") or codex.extension_state()[0] is None:
        return frozenset()
    return frozenset({"codex"})


def codex_cli_choice(install: bool, ask: Ask, interactive: bool, wanted: bool) -> tuple[str | None, bool]:
    """(the Codex CLI line to print or None, skip its install). Only when the Codex CLI is missing and VS Code's Codex
    extension on this side can run Codex: the CLI is recommended there, not required (spec Part 2)."""
    from . import codex
    if runner.have("codex") or codex.extension_state()[0] is None:  # a CLI, or a Windows shim in WSL: as today
        return None, False
    if not wanted:
        return CODEX_CLI_DECLINED, True
    if not install:
        return None, False  # nothing installs this run; the missing line says it is recommended
    if interactive and ask(CODEX_CLI_QUESTION).strip().lower() not in ("y", "yes"):  # optional: no unless asked
        return CODEX_CLI_DECLINED, True
    return CODEX_CLI_WHY, False


def _vscode_level(message: str) -> str:
    """ok only when the switch is on now; every other answer (no settings, another value, a write error) is a warning."""
    return "ok" if message.startswith(VSCODE_DONE) else "warn"


def _vscode_step(cs, ask, interactive: bool, bk, vscode: bool) -> None:
    """Codex runs in WSL: switch VS Code's extension to it (--vscode-wsl), offer it (a terminal), or print the manual
    step (no terminal) when the extension still runs the Windows Codex (spec Part 4). A folder's or a profile's
    setting that turns it off again is named, never edited (spec Part 3)."""
    home = cs.windows_home if cs is not None else None
    if vscode:
        if home is None:
            out.status("VS Code", f"Windows home not found; {wsl.MANUAL}", "warn")
        else:
            message = wsl.set_vscode_wsl_mode(bk, home) if bk is not None else wsl.MANUAL
            out.status("VS Code", message, _vscode_level(message))
    elif interactive:
        _offer_vscode(cs, ask, bk)
    elif cs is not None and cs.vscode_windows:
        out.status("VS Code", f"the Codex extension runs Codex on Windows; {wsl.MANUAL} ({VSCODE_FLAG_HINT})", "warn")
    if home is not None:
        from . import vscode as vs
        for kind, path in vs.wsl_switch_overrides(home):
            detail, fix = vs.override_text(kind, path)
            out.status("VS Code", out.printable(f"{detail}; {fix}"), "warn")  # a folder name is untrusted


def codex_gate(flag, ask, interactive: bool, bk: Backup | None = None, vscode: bool = False) -> str | None:
    """In WSL: None to set up this side's Codex, else the line that explains why not (one loadout per side, ADR 0029).
    vscode: --vscode-wsl, switch VS Code's Codex extension to WSL without asking; a stopped Codex step says the flag
    changed nothing."""
    stopped = _codex_gate(flag, ask, interactive, bk, vscode)
    if stopped is not None and vscode:
        out.status("VS Code", "--vscode-wsl: the Codex step in WSL was skipped, so nothing changed", "warn")
    return stopped


def _codex_gate(flag, ask, interactive: bool, bk: Backup | None, vscode: bool) -> str | None:
    if wsl.detect() is None:
        return None
    if flag == "wsl":
        _vscode_step(wsl.codex_side(), ask, interactive, bk, vscode)
        return None
    if flag == "windows":
        return SKIPPED + WINDOWS_WAY
    cs = wsl.codex_side()
    why = "; ".join(cs.reasons)
    if cs.shared_home:
        return (f"Codex step skipped: {why}. One config would be read by both sides, but its commands fit only one. "
                "Unset CODEX_HOME in WSL, or pass --codex-side wsl to set it up anyway")
    if cs.side != "windows":
        if vscode or (cs.side == "both" and cs.vscode_windows):  # Codex in WSL, VS Code's extension may run the other
            _vscode_step(cs, ask, interactive, bk, vscode)
        return None
    if interactive:
        answer = ask("\n" + CODEX_SIDE_QUESTION).strip() or "1"
        if answer == "2":
            return SKIPPED + WINDOWS_WAY
        if answer != "1":
            return (f"{SKIPPED}no such choice ({answer!r}). Re-run and answer 1 or 2, or pass "
                    "--codex-side wsl or --codex-side windows")
        _vscode_step(cs, ask, True, bk, vscode)
        return None
    return (f"Codex step skipped: {why}. Choose a side: --codex-side wsl (with --install, installs Codex in WSL), "
            f"or {WINDOWS_WAY}")


def _choose_agents(ask, interactive: bool, flag, existing: bool | None = None) -> tuple[dict, bool]:
    """(choice, store it): --agents first, then a decided personal layer, then the question (interactive), else
    Claude Code as before. Only an explicit choice is stored: writing the default into an existing git-backed
    personal layer would leave it dirty and pause the daily sync."""
    from . import targets
    if flag is not None:
        return targets.parse_agents(flag), True
    stored = targets.from_file()
    if stored is not None:
        return stored, False
    if existing is None:
        existing = paths.personal_root().exists()
    if not interactive or (existing and not _codex_seen()):
        return {"claude": True, "codex": False}, False  # as before this change: no new question without Codex
    default = "3" if _codex_seen() else "1"
    answer = ask("\n" + AGENT_QUESTION.format(default=default)).strip() or default
    if answer not in _ANSWERS:
        print(f"no such choice ({answer!r}); using {default} (change it later: loadout configure set target)")
        answer = default
    return dict(_ANSWERS[answer]), True


def _no_question(question: str) -> str:
    """bootstrap without a terminal, or with --yes: every question takes its default, unasked."""
    return ""


def _this_machine(chosen: dict, gate, install: bool, vscode_wsl: bool, codex_cli: bool,
                  claude_cli: bool = True) -> None:
    """This machine's setup cell, its recommended flags and how this run differs; text only, never a question
    (spec 2026-10-27). A detection error never stops bootstrap."""
    from . import recommend
    try:
        from dataclasses import replace
        cs = wsl.codex_side() if wsl.detect() is not None and chosen["codex"] else None
        if cs is not None and gate is None and cs.side == "windows":
            cs = replace(cs, side="wsl")  # the gate set Codex up on this side (--codex-side wsl, or answer 1)
        cell = recommend.detect(chosen, cs, codex_windows=bool(gate) and WINDOWS_WAY in gate)
        lines = [f"recommended: {recommend.flags(cell)}  ({recommend.anchor(cell)})"]
        if cell.surface == "none":
            lines.append(f"using VS Code? see {recommend.anchor(cell)}")
        # missing tools: Prerequisites in the same run names them, so not again here
        lines += recommend.differences(cell, chosen, install, [], vscode_wsl, codex_cli, claude_cli)
    except Exception:
        return
    _step("This machine")
    out.status("This machine", recommend.describe(cell))
    for line in lines:
        out.problem(line)


def bootstrap(install: bool, yes: bool, plugins: bool, adopt_step: bool, ask: Ask, interactive: bool | None = None,
              agents: str | None = None, codex_side: str | None = None, personal: str | None = None,
              answers: str | None = None, vscode_wsl: bool = False, codex_cli: bool = True,
              vscode_path: bool = False, claude_cli: bool = True) -> int:
    from . import targets
    try:
        return _bootstrap(install, yes, plugins, adopt_step, ask, interactive, agents, codex_side, personal, answers,
                          vscode_wsl, codex_cli, vscode_path, claude_cli)
    finally:
        targets.OVERRIDE = None


def _bootstrap(install: bool, yes: bool, plugins: bool, adopt_step: bool, ask: Ask, interactive: bool | None,
               agents: str | None, codex_side: str | None = None, personal: str | None = None,
               answers: str | None = None, vscode_wsl: bool = False, codex_cli: bool = True,
               vscode_path: bool = False, claude_cli: bool = True) -> int:
    from . import codex, targets
    if interactive is None:
        interactive = ui.is_interactive()
    if agents is not None:
        targets.parse_agents(agents)  # a typo in --agents stops here, before any question or clone (ValueError)
    personal = personal.strip() if personal is not None else None
    if personal is not None and personal.lower() == "new":
        personal = "new"
    if personal is not None and (not personal or personal.startswith("-")):
        raise ValueError("--personal: give `new` or the git URL of your personal layer")
    from . import answers as answers_mod
    given = answers_mod.load(answers) if answers is not None else None  # a bad file stops here too
    if not interactive or yes:
        ask = _no_question  # an agent's shell may keep stdin open: never wait for an answer
    print(INTRO)
    if not out.VERBOSE:
        print()
    version = wsl.detect()
    if version is not None:
        _step("WSL")
        out.status("WSL", f"WSL {version}")
        for line in wsl.report_lines(version, wsl.current_dir()):
            out.problem(line)
    # the personal layer first: a layer that already chose (a clone, or this machine's) is never asked again;
    # a starter asks before its own questions, which read only the chosen agents' files
    bk = Backup(description="bootstrap")
    _step("Personal layer")
    fresh = not paths.personal_root().exists()
    decided: dict = {}

    def decide() -> None:
        decided["choice"] = _choose_agents(ask, interactive and not yes, agents, existing=not fresh)
        targets.OVERRIDE = decided["choice"][0]  # the starter's questions and the installs follow the choice

    message, personal_ok = ensure_personal(ask, bk, interactive, before_starter=decide, personal=personal,
                                           given=given, ask_missing=interactive and not yes)
    starter = fresh and personal_ok and paths.personal_root().exists() and not (paths.personal_root() / ".git").exists()
    unused = (["--personal"] if personal is not None and not fresh else []) + (["--answers"] if given is not None and not starter else [])
    where = _tilde(paths.personal_root())
    if personal_ok:
        _report("Personal layer", f"created {where}" if starter else f"cloned into {where}" if fresh else f"using {where}",
                [message])
        if unused:  # shown in calm mode too: an agent that passed them must see they did nothing
            out.problem(f"{' and '.join(unused)}: not used; they apply only to a new one, and this personal layer "
                        "keeps its own answers (change them with loadout configure prefs)")
    else:
        out.status("Personal layer", "clone failed", "fail")
        out.problem(message)
    if "choice" not in decided:
        cloned_choice = fresh and personal_ok and agents is None and targets.from_file() is not None
        decide()
        if cloned_choice:
            names = " and ".join(n for n, on in (("Claude Code", decided["choice"][0]["claude"]),
                                                 ("Codex", decided["choice"][0]["codex"])) if on)
            print(f"using your personal layer's agents: {names}")
    chosen, store = decided["choice"]
    if personal_ok and store:
        targets.set_agents(chosen)
    # in WSL the Codex side is settled first: a Windows-side choice installs no Linux Codex (ADR 0029)
    gate = codex_gate(codex_side, ask, interactive and not yes, bk, vscode=vscode_wsl) if codex_gate_needed(chosen) else None
    if vscode_wsl and wsl.detect() is not None and not codex_gate_needed(chosen):  # outside WSL the CLI already said so
        out.status("VS Code", "--vscode-wsl: Codex is not set up in WSL in this run; nothing changed", "warn")
    _this_machine(chosen, gate, install, vscode_wsl, codex_cli, claude_cli)
    _step("Prerequisites")
    installed: list[str] = []
    notes: list[str] = []
    prepend_tool_dirs()  # a CLI installed by an earlier run, not yet on this shell's PATH, counts as installed
    from . import vscode
    claude_bundled = vscode.use_bundled_claude(on=chosen["claude"])
    cli_line, cli_skip = (codex_cli_choice(install, ask, interactive and not yes, codex_cli)
                          if chosen["codex"] and not gate else (None, False))
    claude_line, claude_skip = (claude_cli_choice(install, ask, interactive and not yes, claude_cli, claude_bundled)
                                if chosen["claude"] else (None, False))
    recommended = codex_recommended(chosen, gate) | (frozenset({"claude"}) if claude_bundled else frozenset())
    skip = (frozenset({"codex"}) if gate or cli_skip else frozenset()) | (
        frozenset({"claude"}) if claude_skip else frozenset())
    missing = check_prereqs(install, ask, installed=installed, notes=notes, skip=skip, recommended=recommended)
    summary, level = _prereq_summary(missing, installed, recommended)
    out.status("Prerequisites", summary, level)
    if cli_line is not None and (cli_skip or "codex" in installed):
        out.status("Codex CLI", cli_line, "warn" if cli_skip else "ok")
    if claude_line is not None and (claude_skip or "claude" in installed):
        out.status("Claude Code CLI", claude_line, "warn" if claude_skip else "ok")
    elif claude_bundled is not None and missing_binary("claude"):  # no --install: nothing was decided this run
        out.status("Claude Code CLI", _claude_bundled_line(claude_bundled), "warn")
    if not claude_cli and not claude_skip:  # as --without-codex-cli: say that it did nothing
        out.problem("--without-claude-cli: not used; it applies only with VS Code's Claude Code extension and no "
                    "Claude Code CLI on PATH")
    if not codex_cli and not cli_skip:  # shown in calm mode too: an agent that passed it must see it did nothing
        out.problem("--without-codex-cli: not used; it applies only with VS Code's Codex extension and no Codex CLI "
                    "on PATH")
    for line in notes:
        out.problem(line)
    claude_on = chosen["claude"]
    _step("Links")
    link_lines = apply.link_step(bk, claude_on, retry_symlinks=True).lines
    # after a failed clone nothing may write into the personal layer: a partial folder would stop the next run
    # from asking for the URL again (the wizard and adopt both write there)
    if not personal_ok:
        print("no personal layer yet: skipping the preferences prompt and adopt until bootstrap runs again")
    elif not yes and not interactive:
        print("non-interactive: skipping the configure prompt (run `loadout configure` later)")
    elif not yes and ui.confirm(ask, "\nCustomize preferences and global add-ons now? [y/N] "):
        from .configure import wizard
        wizard(ask, first_run=False, setup=False, interactive=interactive, preferences_asked=starter)  # settings, MCP servers and plugins are applied below
    if claude_on:
        _step("Settings")
        settings = apply.settings_step(bk, on=True)
        _report("Rules and settings", "linked, " + settings.summary, link_lines + settings.lines)
    else:
        _report("Launcher", "linked", link_lines)
    if plugins and claude_on:
        _step("Marketplaces and plugins")
        result = apply.claude_plugins_step(say=out.progress, on=True)
        out.end_progress()
        _report(result.name, result.summary, result.lines)
    if claude_on or chosen["codex"]:
        result = apply.cbm_step(bk)
        if result.lines:
            _step("codebase-memory")
            _report(result.name, result.summary, result.lines)
    result = apply.rtk_step(bk)  # also with Claude Code off: removes loadout's line when it no longer provides the hook
    if result.lines:
        _step("rtk")
        _report(result.name, result.summary, result.lines)
    if chosen["codex"]:
        _step("Codex")
        problem = gate or (codex.unavailable(allow_shared_home=True) if codex_side == "wsl" else codex.unavailable())
        if problem:
            out.status("Codex", problem, "warn")
        else:
            result = apply.codex_step(bk, refresh_plugins=False, auto=False, keep=False, say=out.progress, on=True,
                                     plugins=plugins)
            out.end_progress()
            _report(result.name, result.summary, result.lines)
            if codex.own_serena() is not None:  # loadout wrote no serena of its own: say why, once per bootstrap
                out.problem(codex.SERENA_KEPT)
    adopt.LAST_BACKUP = None
    if adopt_step and personal_ok and claude_on:
        _step("Adopt existing setup")
        if not yes and not interactive:
            print("non-interactive: skipping adopt (review with `loadout adopt`, apply with `loadout adopt --apply`)")
        else:
            print()
            adopt.run(apply_changes=True, groups=None, skip=set(), yes=yes, ask=ask, interactive=interactive,
                      embedded=True)
            print()
    _step("Secrets")
    _report("Secrets", f"{_tilde(paths.secrets_file())} ready", setup_secrets(bk))
    _step("PATH")
    path_lines, path_changed = setup_path(bk)
    _report("PATH", "tool folders added (new terminals)" if path_changed else "already set up",
            path_lines or ["PATH already set up"])
    _vscode_path_step(ask, interactive and not yes, vscode_path, bk)
    if not bk.empty:
        out.detail(f"backup: {bk.root}  (undo: loadout restore {bk.root})")
    _step("Check")
    results = check.run_checks(codex_windows=True) if gate and WINDOWS_WAY in gate else check.run_checks()
    if out.VERBOSE:
        text, code = check.format_results(results)
        print(text)
    else:
        bad = [r for r in results if not r.ok]
        text, code = check.format_results(bad, fixes=False)  # each fix is in "Still to do" below
        out.status("Health check", f"{len(results) - len(bad)} of {len(results)} OK",
                   "fail" if code else "warn" if bad else "ok")
        if bad:
            print(text)
    here = {**chosen, "codex": chosen["codex"] and gate is None}  # agents this run set up on this side
    todo = still_to_do(os_key(), codex_here=here["codex"])
    from . import steps
    try:  # the steps visible without a run's facts (hooks, plugin copy), as `loadout update` leaves them: shown at that agent's next session until done
        steps.save(steps.derive(set(), [], here["claude"], here["codex"]))
        steps.settle(here["claude"], chosen["codex"], results)  # Codex on but set up on the Windows side keeps its steps
    except Exception:
        pass
    if not out.VERBOSE and (not bk.empty or adopt.LAST_BACKUP is not None):
        print(f"\n{adopt.UNDO_LINE}")
    if path_changed and out.VERBOSE:
        print("\nOpen a new terminal so the new PATH applies.")
    try:  # steps an earlier run left open (the hooks one is in still_to_do's own items)
        saved = steps.open_items(here["claude"], chosen["codex"], skip={"codex/hooks"})
    except Exception:
        saved = []
    # rows still_to_do already says; Codex set up on the other side (bootstrap.ps1): its rows are that side's
    skip_rows = steps.STILL_TO_DO_ROWS | (set() if here["codex"] else {"Codex"})
    fails, warns = steps.row_items(results, skip_rows, after_bootstrap=True, said=todo)
    lines = steps.todo_block("Still to do (in a new terminal):" if path_changed else "Still to do:",
                             fails, todo, saved, warns, here["claude"], here["codex"])
    if lines:
        print("\n" + "\n".join(lines))
    extension = here["codex"] and codex.mode() == "extension"
    claude_ext = here["claude"] and claude_bundled is not None and not runner.have("claude")
    run = " or ".join(f"`{a}`" for a in ("claude", "codex")
                      if here[a] and not (a == "claude" and claude_ext) and (a == "claude" or not extension))
    if (extension or claude_ext) and not run:  # extension mode: the extension is where the agent runs
        names = " and ".join(n for n, on in (("Claude Code", claude_ext), ("Codex", extension)) if on)
        word = "extensions" if extension and claude_ext else "extension"
        hooks = extension and codex.hooks_status() in ("untrusted", "changed")
        print(f"\nNext: open VS Code's {names} {word} (reload the window if it is open)"
              + (" and approve loadout's hooks: the hooks icon in the prompt bar, then Allow all." if hooks
                 else ". The kit loads automatically."))
        if not personal_ok:
            print("personal layer: the clone failed (see above); re-run bootstrap after fixing access")
            return 1
        return code
    names = " or ".join(n for n, a in (("Claude Code", "claude"), ("Codex", "codex"))
                        if here[a] and not (a == "claude" and claude_ext))
    also = ", and open VS Code's Claude Code extension" if claude_ext else ""  # it runs Claude Code here
    # an extension next to its CLI: either one runs the agent (tour 2026-10-28 E2)
    too = [n for n, on in (("Claude Code", here["claude"] and not claude_ext and runner.have("claude")
                            and vscode.bundled_claude() is not None),
                           ("Codex", here["codex"] and not extension and codex.extension_state()[0] is not None))
           if on]
    if too:
        also += f", or open VS Code's {' or '.join(too)} extension (reload the window if it is open)"
    if not run:  # Codex only, and its step stopped: on Windows, or a CODEX_HOME shared with Windows
        print(f"\nNext: {WINDOWS_WAY}." if WINDOWS_WAY in gate else "\nNext: settle Codex's side (see the Codex step above).")
    elif out.VERBOSE:
        print(f"\nThen start {names}{also}." if path_changed else f"\nRestart {names} to load plugins and rules{also}.")
    else:
        print(f"\nNext: run {run} in a new terminal{also}." if path_changed
              else f"\nNext: run {run} (restart it if it is open){also}. The kit loads automatically.")
    if not personal_ok:
        print("personal layer: the clone failed (see above); re-run bootstrap after fixing access")
        return 1
    return code
