"""`loadout bootstrap` (spec §6.1). Safe to re-run."""
from __future__ import annotations

import codecs
import locale
import os
from pathlib import Path
from typing import Callable

from . import adopt, catalog, check, link, paths, runner, secrets, settings_merge, ui
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


def check_prereqs(install: bool, ask: Ask) -> list[str]:
    missing = []
    for entry in catalog.binaries():
        name = entry["id"]
        if runner.have(name) or not (entry.get("required") or entry["status"] == "recommended"):
            continue
        cmds = catalog.platform_cmds(entry, "install")
        if install and cmds:
            for cmd in cmds:
                print("installing: " + " ".join(cmd))
                res = runner.run(cmd, timeout=900)
                if not res.ok:
                    print(f"  failed: {res.stderr.strip()[:300]}")
        if not runner.have(name):
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


def _add_block(rc: Path, block: str, bk: Backup | None, windows: bool) -> str | None:
    if rc.exists():
        raw = rc.read_bytes()
        if windows:
            text, enc = _decode_profile(raw)
            if RC_MARKER in text:
                return None
            if "\r\n" in text:
                block = block.replace("\n", "\r\n")
            sep = "" if not text or text.endswith("\n") else ("\r\n" if "\r\n" in text else "\n")
            # encode the whole text again so a UTF-16 profile stays UTF-16 (one BOM, at the start)
            data = (text + sep + block).encode(enc, errors="surrogateescape")
            if bk is not None:
                bk.save_copy(rc, f"{rc} before adding secrets loading")
            from .jsonio import write_atomic_bytes
            write_atomic_bytes(rc, data)
        else:
            if RC_MARKER.encode() in raw:
                return None
            with rc.open("ab") as fh:  # append: never re-encode the user's rc file
                fh.write((b"" if not raw or raw.endswith(b"\n") else b"\n") + block.encode("utf-8"))
        return f"added secrets loading to {rc}"
    rc.parent.mkdir(parents=True, exist_ok=True)
    rc.write_bytes(block.encode("utf-8"))
    if bk is not None:
        bk.record_created(rc, f"created {rc}")
    return f"created {rc} with secrets loading"


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


def _settings_would_change() -> bool:
    current = load_json(paths.claude_home() / "settings.json")
    previous = load_json(paths.state_dir() / "managed-settings.json")
    return settings_merge.merge_settings(current, settings_merge.desired_settings(), previous) != current


def bootstrap(install: bool, yes: bool, plugins: bool, adopt_step: bool, ask: Ask, interactive: bool | None = None) -> int:
    if interactive is None:
        interactive = ui.is_interactive()
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
    if settings_path.exists() and _settings_would_change():
        bk.save_copy(settings_path, "settings.json before loadout merge")
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
    if not bk.empty:
        print(f"\nbackup: {bk.root}  (undo: loadout restore {bk.root})")
    _step("Check")
    text, code = check.format_results(check.run_checks())
    print(text)
    print("\nRestart Claude Code to load plugins and rules.")
    if not personal_ok:
        print("personal layer: the clone failed (see above); re-run bootstrap after fixing access")
        return 1
    return code
