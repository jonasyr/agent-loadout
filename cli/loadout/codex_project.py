"""The Codex side of `loadout init` and `loadout profile`: the repo's .codex/config.toml, .agents/skills and plugins."""
from __future__ import annotations

import os
from pathlib import Path

from . import codex, paths, profiles

TRUST_NOTE = ("Codex reads the repo's .codex/config.toml only in a trusted project: start `codex` here once and "
              "accept the trust question")


def _inside(path: Path, project: Path) -> bool:
    try:
        path.resolve().relative_to(project.resolve())
        return True
    except ValueError:
        return False


def _wanted(prof: profiles.Profile) -> tuple[dict[str, str], list[str], list[str]]:
    """(table text by name, plugin ids, skipped lines)."""
    servers = prof.mcp.get("mcpServers", {}) if isinstance(prof.mcp, dict) else {}
    off = set(prof.settings.get("disabledMcpjsonServers", []) or [])
    tables, skipped = {}, []
    for name, cfg in (servers if isinstance(servers, dict) else {}).items():
        try:
            text = codex.table_text(name, codex.server(name, cfg))
        except codex.Refused as exc:
            skipped.append(f"skipped {exc}")
            continue
        tables[name] = text + ("enabled = false\n" if name in off else "")
    plugins = [p for p in prof.install if isinstance(p, str) and "@" in p]
    return tables, plugins, skipped


def config(prof: profiles.Profile, project: Path, dry_run: bool) -> list[str]:
    """Add the profile's servers and plugin switches to the repo's .codex/config.toml. Only adds tables; a table of
    the same name is the user's and stays."""
    path = project / ".codex" / "config.toml"
    if not _inside(path.parent, project) or not _inside(path, project):
        return [f"skipped {path}: it points outside {project} (a symlinked .codex or config.toml)"]
    tl = codex._tomllib()
    if tl is None:
        return [f"skipped {path}: editing it safely needs Python 3.11 or newer"]
    tables, plugins, lines = _wanted(prof)
    if not tables and not plugins:
        return lines
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    try:
        before = tl.loads(old)
    except Exception as exc:
        return lines + [f"skipped {path}: it does not parse now ({exc}); fix it, then run loadout profile again"]
    added, keys = [], []
    for name, text in tables.items():
        if name in before.get("mcp_servers", {}):
            if before["mcp_servers"][name] != tl.loads(text)["mcp_servers"][name]:
                lines.append(f"mcp {name}: left as is in {path} (a server of that name is already there)")
            continue
        added.append(text)
        lines.append(("would add" if dry_run else "added") + f" mcp {name} to {path}")
    for pid in plugins:
        if pid in before.get("plugins", {}):
            continue
        added.append(f"[plugins.{codex.toml_key(pid)}]\nenabled = true\n")
        keys.append(f"plugins.{codex.toml_key(pid)}.enabled")
        lines.append(("would enable" if dry_run else "enabled") + f" plugin {pid} in {path}")
    if not added or dry_run:
        return lines
    new = (old.rstrip("\n") + "\n\n" if old.strip() else "") + "\n".join(added)
    try:
        after = tl.loads(new)
    except Exception as exc:
        return lines + [f"skipped {path}: the result would not parse ({exc}); nothing written"]
    if codex._without_owned(before, set(tables), keys, tl) != codex._without_owned(after, set(tables), keys, tl):
        return lines + [f"skipped {path}: the edit would change entries loadout does not own; nothing written"]
    from .jsonio import write_atomic
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, new)
    return lines


def skills(project: Path, dry_run: bool) -> list[str]:
    """Link each skill in the repo's .claude/skills into .agents/skills (relative, so the link works in every clone)."""
    src_root, dest_root = project / ".claude" / "skills", project / ".agents" / "skills"
    if not src_root.is_dir():
        return []
    if not _inside(dest_root.parent, project) or not _inside(dest_root, project):
        return [f"skills not linked: {dest_root} points outside {project} (a symlinked .agents or .agents/skills)"]
    out = []
    for entry in sorted(src_root.iterdir()):
        if entry.name.startswith(".") or not entry.is_dir():
            continue
        dest = dest_root / entry.name
        if dest.exists() or dest.is_symlink():
            continue
        if dry_run:
            out.append(f"would link skill {entry.name} for Codex -> .agents/skills/{entry.name}")
            continue
        dest_root.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(f"../../.claude/skills/{entry.name}", dest, target_is_directory=True)
        except OSError as exc:  # e.g. Windows without symlink rights
            out.append(f"skill {entry.name}: not linked for Codex ({exc.strerror or exc})")
            continue
        out.append(f"linked skill {entry.name} for Codex -> .agents/skills/{entry.name}")
    return out


def plugins(prof: profiles.Profile, dry_run: bool) -> list[str]:
    """Install the profile's plugins in Codex; one that is not on everywhere stays switched off outside its projects."""
    from . import backup
    from .settings_merge import desired_settings
    _, wanted, _ = _wanted(prof)
    if not wanted:
        return []
    desired = desired_settings()
    markets = {**desired.get("extraKnownMarketplaces", {}), **prof.settings.get("extraKnownMarketplaces", {})}
    routes, missing = codex.plugin_routes({"enabledPlugins": {p: True for p in wanted}, "extraKnownMarketplaces": markets})
    lines = [f"plugin {pid}: no Codex route (its marketplace is not on GitHub)" for pid in missing]
    if dry_run:
        return lines + [f"would install plugin {name} for Codex (from {src})" for src, names in routes.items() for name in names]
    bk = backup.Backup(description=f"loadout profile {prof.name} (Codex)")
    out, installed = codex._install_routes(routes, bk, False, lambda line: None, codex.installed_plugins())
    lines += out
    on = desired.get("enabledPlugins", {})
    for pid in wanted:
        if pid in installed and on.get(pid) is not True:
            codex.add_project_plugin(pid)
    return lines + codex.apply_config(bk)


def _trusted(project: Path) -> bool:
    tl = codex._tomllib()
    path = paths.codex_home() / "config.toml"
    if tl is None or not path.exists():
        return False
    try:
        data = tl.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    entry = data.get("projects", {}).get(str(project.resolve()), {})
    return isinstance(entry, dict) and entry.get("trust_level") == "trusted"


def apply(prof: profiles.Profile, project: Path, install: bool, dry_run: bool) -> list[str]:
    lines = config(prof, project, dry_run) + skills(project, dry_run)
    if install:
        lines += plugins(prof, dry_run)
    if lines and not dry_run and not _trusted(project):
        lines.append(TRUST_NOTE)
    return lines
