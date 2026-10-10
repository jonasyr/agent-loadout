"""`loadout check`: report problems, never fix them; every failure names its fix."""
from __future__ import annotations

import os
import stat
from dataclasses import dataclass

from . import catalog, link, paths, runner, settings_merge
from .jsonio import InvalidJSON, load_json


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
        wanted = [p for p, on in settings_merge.desired_settings().get("enabledPlugins", {}).items() if on]
        installed = load_json(paths.claude_home() / "plugins" / "installed_plugins.json").get("plugins", {})
        if not isinstance(installed, dict):
            raise InvalidJSON("installed_plugins.json: 'plugins' is not an object")
    except InvalidJSON as exc:
        return [CheckResult("plugins installed", False, str(exc), "fix the JSON syntax", "warn")]
    missing = [p for p in wanted if p not in installed]
    # Claude Code installs enabled plugins from known marketplaces at its next start
    return [CheckResult("plugins installed", not missing, ", ".join(missing),
                        "they install automatically at the next Claude Code start (or run loadout bootstrap)", "warn")]


def _binaries() -> list[CheckResult]:
    out = []
    for entry in catalog.binaries():
        name = entry["id"]
        ok = runner.have(name)
        severity = "error" if entry.get("required") else "warn"
        fix = ("loadout bootstrap --install" if catalog.platform_cmds(entry, "install")
               else entry.get("manual") or f"install {name} and make sure it is on PATH")
        out.append(CheckResult(f"binary {name}", ok, "" if ok else "not on PATH", fix, severity))
    return out


def _gh() -> list[CheckResult]:
    if not runner.have("gh"):
        return []
    res = runner.run(["gh", "auth", "status"], timeout=20)
    return [CheckResult("gh auth", res.ok, "" if res.ok else "not logged in", "gh auth login && gh auth setup-git", "warn")]


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


def run_checks() -> list[CheckResult]:
    return [*_links(), *_skills_json(), *_settings(), *_plugins(), *_binaries(), *_gh(), *_secrets(), *_repos()]


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
