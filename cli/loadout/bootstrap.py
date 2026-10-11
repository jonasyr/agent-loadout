"""`loadout bootstrap` (spec §6.1). Safe to re-run."""
from __future__ import annotations

import codecs
import locale
import os
import re
from pathlib import Path
from typing import Callable

from . import adopt, catalog, check, link, paths, runner, secrets, settings_merge, ui, wsl
from .backup import Backup
from .jsonio import load_json
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


def _step(title: str) -> None:
    print(f"\n== {title}")


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


def still_to_do(key: str) -> list[str]:
    out = []
    if not runner.have("git"):
        out.append(f"install git: {MANUAL_STEPS['git'][key]}")
    if runner.have("claude") and not _claude_logged_in():
        out.append("log in to Claude Code: claude   (or set ANTHROPIC_API_KEY)")
    if runner.have("gh") and not runner.run(["gh", "auth", "status"], timeout=20).ok:
        out.append("log in to GitHub: gh auth login && gh auth setup-git")
    return out


def prepend_tool_dirs() -> None:
    parts = os.environ.get("PATH", "").split(os.pathsep)
    new = [str(d) for d in paths.tool_dirs() if str(d) not in parts]
    if new:
        os.environ["PATH"] = os.pathsep.join(new + [p for p in parts if p])


def _wanted(entry: dict) -> bool:
    return bool(entry.get("required") or entry["status"] == "recommended")


def check_prereqs(install: bool, ask: Ask) -> list[str]:
    from . import pkgmgr
    prepend_tool_dirs()
    entries = catalog.install_order(catalog.binaries())
    # helpers are wanted only when a missing, wanted binary needs them
    needed = {d for e in entries if not e.get("helper") and _wanted(e) and not runner.have(e["id"])
              for d in e.get("needs", [])}
    missing, failed = [], set()
    for entry in entries:
        name = entry["id"]
        wanted = name in needed if entry.get("helper") else _wanted(entry)
        if not wanted or runner.have(name):
            continue
        cmds = catalog.platform_cmds(entry, "install")
        blocked = [d for d in entry.get("needs", []) if d in failed]
        if install and cmds and blocked:
            print(f"missing {name}: skipped: needs {', '.join(blocked)}")
        elif install and cmds:
            for cmd in cmds:
                print("installing: " + " ".join(cmd))
                res = runner.run(cmd, cwd=pkgmgr.run_cwd(cmd), timeout=900)
                if not res.ok:
                    print(f"  failed: {res.stderr.strip()[:300]}")
            prepend_tool_dirs()
            if name in ("playwright-cli", "pyright", "typescript-language-server") and runner.have("mise"):
                runner.run(["mise", "reshim"], cwd=pkgmgr.run_cwd(["mise"]), timeout=120)  # shims for npm globals
                prepend_tool_dirs()
        if not runner.have(name):
            failed.add(name)
            if not entry.get("helper"):
                hint = "re-run with --install" if cmds else entry.get("manual", "")
                print(f"missing {'(required) ' if entry.get('required') else ''}{name}: {hint}")
                missing.append(name)
    if runner.have("gh"):
        if runner.run(["gh", "auth", "status"], timeout=20).ok:
            res = runner.run(["gh", "auth", "setup-git"], timeout=20)
            if res.ok:
                print("git uses your gh login for GitHub (gh auth setup-git; undo: git config --global --unset-all credential.https://github.com.helper)")
        else:
            print("gh is not logged in: run `gh auth login` (needed for private marketplaces)")
    return missing


def ensure_personal(ask: Ask, bk: Backup | None = None, interactive: bool | None = None) -> tuple[str, bool]:
    """Returns (message, ok). ok is False only when a clone was asked for and failed."""
    bk = bk if bk is not None else Backup(description="bootstrap")
    interactive = ui.is_interactive() if interactive is None else interactive
    root = paths.personal_root()
    if root.exists():
        return f"personal layer: {root}", True
    url = ask("Personal layer: git URL to clone (empty = create a starter one): ").strip()
    if url:
        res = runner.run(["git", "clone", "--", url, str(root)], timeout=300)
        if res.ok:
            return f"cloned {url} -> {root}", True
        return (f"clone failed: {redact(res.stderr.strip())}\n"
                f"  fix access (e.g. `gh auth login`), then re-run bootstrap; continuing without a personal layer"), False
    root.mkdir(parents=True, exist_ok=True)
    (root / "settings.json").write_text("{}\n", encoding="utf-8")
    bk.record_created(root / "settings.json", "created personal settings.json")
    from .configure import _about_you, ask_preferences
    _about_you(ask, bk)
    ask_preferences(ask, fill_defaults=True, interactive=interactive, bk=bk)
    return f"created starter personal layer at {root} (make it a git repo to sync it across machines)", True


def setup_plugins() -> list[str]:
    out = []
    desired = settings_merge.desired_settings()
    listed = runner.run(["claude", "plugin", "marketplace", "list"], timeout=60).stdout
    for name, cfg in desired.get("extraKnownMarketplaces", {}).items():
        if name in listed:
            continue
        src = cfg["source"]
        origin = src.get("repo") or src.get("url")
        res = runner.run(["claude", "plugin", "marketplace", "add", origin], timeout=300)
        out.append(f"marketplace {name}: {'added' if res.ok else 'failed: ' + res.stderr.strip()}")
    installed = load_json(paths.claude_home() / "plugins" / "installed_plugins.json").get("plugins", {})
    for plugin_id, on in desired.get("enabledPlugins", {}).items():
        if on and plugin_id not in installed:
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
WIN_PATH_GET = ("[Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Environment').GetValue('Path', '', "
                "[Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)")


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
    start = raw.find(PATH_MARKER.encode() + b"\n")
    if start < 0:
        return None  # no block yet: the caller appends one
    end_tag = PATH_END.encode() + b"\n"
    end = raw.find(end_tag, start)
    if end >= 0:
        end += len(end_tag)
    else:  # a block without end marker ends at its `export PATH`
        tail = b"export PATH\n"
        end = raw.find(tail, start)
        if end < 0:
            return ""
        end += len(tail)
    new = block.encode("utf-8")
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
        return _setup_windows_path(dirs)
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


def _expand_user_vars(entry: str) -> str:
    local = os.environ.get("LOCALAPPDATA") or str(paths.home() / "AppData" / "Local")
    for var, value in (("%USERPROFILE%", str(paths.home())), ("%LOCALAPPDATA%", local)):
        entry = re.sub(re.escape(var), lambda _m, v=value: v, entry, flags=re.IGNORECASE)
    return entry


def _setup_windows_path(dirs: list[Path]) -> tuple[list[str], bool]:
    hand = f"add {', '.join(map(str, dirs))} to it by hand"
    res = runner.run(["powershell", "-NoProfile", "-Command", WIN_PATH_GET], timeout=30)
    if not res.ok:
        return [f"could not read your user PATH; {hand}"], False
    current = [p for p in res.stdout.strip().split(";") if p]  # raw: %VARS% stay unexpanded
    def norm(x: str) -> str:
        return x.replace("\\", "/").rstrip("/").lower()
    present = {norm(x) for p in current for x in (p, _expand_user_vars(p))}
    new = [str(d) for d in dirs if norm(str(d)) not in present]
    if not new:
        return [], False
    value = ";".join(new + current).replace("'", "''")
    set_cmd = ("$k = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey('Environment', $true); "
               f"$k.SetValue('Path', '{value}', [Microsoft.Win32.RegistryValueKind]::ExpandString)")
    if not runner.run(["powershell", "-NoProfile", "-Command", set_cmd], timeout=30).ok:
        return [f"could not update your user PATH; {hand}"], False
    return [f"added {', '.join(new)} to your user PATH (was: {';'.join(current) or 'empty'})"], True


def bootstrap(install: bool, yes: bool, plugins: bool, adopt_step: bool, ask: Ask, interactive: bool | None = None) -> int:
    if interactive is None:
        interactive = ui.is_interactive()
    version = wsl.detect()
    if version is not None:
        _step("WSL")
        for line in wsl.report_lines(version, wsl.current_dir()):
            print(line)
    _step("Prerequisites")
    check_prereqs(install, ask)
    bk = Backup(description="bootstrap")
    _step("Personal layer")
    fresh = not paths.personal_root().exists()
    message, personal_ok = ensure_personal(ask, bk, interactive)
    # a starter layer was just created and its preference questions asked (a clone has .git)
    starter = fresh and personal_ok and paths.personal_root().exists() and not (paths.personal_root() / ".git").exists()
    print(message)
    _step("Links")
    for line in link.link_all(bk, retry_symlinks=True) + link.link_bin(bk):
        print(line)
    if not yes and not interactive:
        print("\nnon-interactive: skipping the configure prompt (run `loadout configure` later)")
    elif not yes and ui.confirm(ask, "\nCustomize preferences and global add-ons now? [y/N] "):
        from .configure import wizard
        wizard(ask, first_run=False, setup=False, interactive=interactive, preferences_asked=starter)  # settings, MCP servers and plugins are applied below
    _step("Settings")
    settings_path = paths.claude_home() / "settings.json"
    if settings_path.exists() and settings_merge.would_change():
        bk.save_copy(settings_path, "settings.json before loadout merge")
    settings_merge.backup_snapshot(bk)
    before, after = settings_merge.apply_settings()
    print("settings updated" if before != after else "settings already up to date")
    from .personal_mcp import apply_mcp
    for line in apply_mcp():
        print(line)
    if plugins:
        _step("Marketplaces and plugins")
        lines = setup_plugins()
        for line in lines:
            print(line)
        if any(line.endswith(": added") for line in lines):
            settings_merge.apply_settings()  # the CLI rewrites marketplace entries and drops autoUpdate
    if adopt_step:
        _step("Adopt existing setup")
        if not yes and not interactive:
            print("non-interactive: skipping adopt (review with `loadout adopt`, apply with `loadout adopt --apply`)")
        else:
            adopt.run(apply_changes=True, groups=None, skip=set(), yes=yes, ask=ask, interactive=interactive)
    _step("Secrets")
    for line in setup_secrets(bk):
        print(line)
    _step("PATH")
    path_lines, path_changed = setup_path(bk)
    for line in path_lines or ["PATH already set up"]:
        print(line)
    if not bk.empty:
        print(f"\nbackup: {bk.root}  (undo: loadout restore {bk.root})")
    _step("Check")
    text, code = check.format_results(check.run_checks())
    print(text)
    todo = still_to_do(os_key())
    if todo:
        print("\nStill to do:")
        for line in todo:
            print(f"  - {line}")
    print("\nOpen a new terminal so the new PATH applies, then start Claude Code." if path_changed
          else "\nRestart Claude Code to load plugins and rules.")
    if not personal_ok:
        print("personal layer: the clone failed (see above); re-run bootstrap after fixing access")
        return 1
    return code
