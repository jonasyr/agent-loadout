"""`loadout bootstrap` (spec §6.1). Safe to re-run."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from . import adopt, catalog, check, link, paths, runner, scaffold, settings_merge
from .backup import Backup
from .jsonio import load_json

Ask = Callable[[str], str]
RC_MARKER = "# loadout secrets"
RC_LINE = (f'{RC_MARKER}\n[ -f "$HOME/.config/loadout/secrets.env" ] && '
           'set -a && . "$HOME/.config/loadout/secrets.env" && set +a\n')
PS_BLOCK = (f"{RC_MARKER}\n$f = Join-Path $HOME '.config/loadout/secrets.env'\n"
            "if (Test-Path $f) { Get-Content $f | ForEach-Object { if ($_ -match '^\\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') "
            "{ [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2].Trim('\"'), 'Process') } } }\n")


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
            runner.run(["gh", "auth", "setup-git"], timeout=20)
        else:
            print("gh is not logged in: run `gh auth login` (needed for private marketplaces)")
    return missing


def ensure_personal(ask: Ask) -> str:
    root = paths.personal_root()
    if root.exists():
        return f"personal layer: {root}"
    url = ask("Personal layer: git URL to clone (empty = create a starter one): ").strip()
    if url:
        res = runner.run(["git", "clone", url, str(root)], timeout=300)
        return f"cloned {url} -> {root}" if res.ok else f"clone failed: {res.stderr.strip()}"
    values = {
        "NAME": ask("Your name: ").strip() or "me",
        "ROLE": ask("Your role (e.g. backend developer, CS student): ").strip() or "developer",
        "LANGUAGES": ask("Main languages/stacks: ").strip() or "(not specified)",
        "PREFERENCES": ask("Working preferences (e.g. concise answers, ask before deleting): ").strip() or "(not specified)",
    }
    template = paths.kit_root() / "templates" / "personal"
    for src in template.rglob("*"):
        if src.is_file():
            dest = root / src.relative_to(template)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(scaffold.render(src.read_text(encoding="utf-8"), values), encoding="utf-8")
    return f"created starter personal layer at {root} (make it a git repo to sync it across machines)"


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


def setup_secrets() -> list[str]:
    out = []
    path = paths.secrets_file()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text((paths.kit_root() / "secrets.env.example").read_text(encoding="utf-8"), encoding="utf-8")
        out.append(f"created {path}")
    if os.name != "nt":
        os.chmod(path, 0o600)
        targets = [r for r in (paths.home() / ".bashrc", paths.home() / ".zshrc") if r.exists()]
        if not targets:
            zsh = os.path.basename(os.environ.get("SHELL", "")) == "zsh"
            targets = [paths.home() / (".zshrc" if zsh else ".bashrc")]
        block = RC_LINE
    else:
        res = runner.run(["powershell", "-NoProfile", "-Command", "$PROFILE"], timeout=30)
        targets = [Path(res.stdout.strip())] if res.ok and res.stdout.strip() else []
        block = PS_BLOCK
    for rc in targets:
        text = rc.read_text(encoding="utf-8") if rc.exists() else ""
        if RC_MARKER in text:
            continue
        rc.parent.mkdir(parents=True, exist_ok=True)
        rc.write_text(text + ("" if text.endswith("\n") or not text else "\n") + block, encoding="utf-8")
        out.append(f"added secrets loading to {rc}")
    empty = [line.split("=", 1)[0] for line in path.read_text(encoding="utf-8").splitlines()
             if line and not line.startswith("#") and line.endswith("=")]
    if empty:
        out.append(f"empty secrets: {', '.join(empty)}")
    return out


def _settings_would_change() -> bool:
    current = load_json(paths.claude_home() / "settings.json")
    previous = load_json(paths.state_dir() / "managed-settings.json")
    return settings_merge.merge_settings(current, settings_merge.desired_settings(), previous) != current


def bootstrap(install: bool, yes: bool, plugins: bool, adopt_step: bool, ask: Ask) -> int:
    _step("Prerequisites")
    check_prereqs(install, ask)
    _step("Personal layer")
    print(ensure_personal(ask))
    _step("Links")
    bk = Backup()
    for line in link.link_all(bk) + link.link_bin(bk):
        print(line)
    _step("Settings")
    settings_path = paths.claude_home() / "settings.json"
    if settings_path.exists() and _settings_would_change():
        bk.save_copy(settings_path, "settings.json before loadout merge")
    before, after = settings_merge.apply_settings()
    print("settings updated" if before != after else "settings already up to date")
    if plugins:
        _step("Marketplaces and plugins")
        for line in setup_plugins():
            print(line)
    if adopt_step:
        _step("Adopt existing setup")
        adopt.run(apply_changes=True, groups=None, skip=set(), yes=yes, ask=ask)
    _step("Secrets")
    for line in setup_secrets():
        print(line)
    if not bk.empty:
        print(f"\nbackup: {bk.root}  (undo: loadout restore {bk.root})")
    _step("Check")
    text, code = check.format_results(check.run_checks())
    print(text)
    print("\nRestart Claude Code to load plugins and rules.")
    return code
