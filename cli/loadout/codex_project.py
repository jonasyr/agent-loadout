"""The Codex side of `loadout init` and `loadout profile`: the repo's .codex/config.toml, .agents/skills and plugins."""
from __future__ import annotations

from pathlib import Path

from . import codex, paths, profiles
from .jsonio import get_dict, get_list

TRUST_NOTE = ("Codex reads the repo's .codex/config.toml only in a trusted project: start `codex` here once and "
              "accept the trust question")


def _wanted(prof: profiles.Profile) -> tuple[dict[str, str], list[str], list[str]]:
    """(table text by name, plugin ids, skipped lines)."""
    servers = get_dict(prof.mcp, "mcpServers")
    off = {n for n in get_list(prof.settings, "disabledMcpjsonServers") if isinstance(n, str)}
    tables, skipped = {}, []
    for name, cfg in servers.items():
        try:
            text = codex.table_text(name, codex.server(name, cfg))
        except codex.Refused as exc:
            skipped.append(f"skipped {exc}")
            continue
        tables[name] = text + ("enabled = false\n" if name in off else "")
    plugins = []
    for p in prof.install:
        if isinstance(p, str) and profiles.PLUGIN_ID.match(p):
            plugins.append(p)
        else:
            skipped.append(f"plugin {p!r}: not a name@marketplace id, skipped")
    return tables, plugins, skipped


def config(prof: profiles.Profile, project: Path, dry_run: bool, skip: frozenset = frozenset()) -> list[str]:
    """Add the profile's servers and plugin switches to the repo's .codex/config.toml. Only adds tables; a table of
    the same name is the user's and stays. skip: plugins that did not install, so the repo does not name them."""
    path = project / ".codex" / "config.toml"
    if not paths.inside(path.parent, project) or not paths.inside(path, project):
        return [f"skipped {path}: it points outside {project} (a symlinked .codex or config.toml)"]
    tl = codex._tomllib()
    tables, plugins, lines = _wanted(prof)
    plugins = [p for p in plugins if p not in skip]
    if not tables and not plugins:
        return lines
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    try:
        before = tl.loads(old)
    except Exception as exc:
        return lines + [f"skipped {path}: it does not parse now ({exc}); fix it, then run loadout profile again"]
    odd = [k for k in ("mcp_servers", "plugins") if not isinstance(before.get(k, {}), dict)]
    if odd:
        return lines + [f"skipped {path}: {', '.join(odd)} is not a table; fix it, then run loadout profile again"]
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
            entry = before["plugins"][pid]
            if not (isinstance(entry, dict) and entry.get("enabled", True) is True):
                lines.append(f"plugin {pid}: switched off in {path}, left as is (Codex will not load it here)")
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


def plugins(prof: profiles.Profile, dry_run: bool) -> list[str]:
    """Install the profile's plugins in Codex; one that is not on everywhere stays switched off outside its projects."""
    from . import backup
    from .settings_merge import desired_settings
    _, wanted, _ = _wanted(prof)
    if not wanted:
        return []
    desired = desired_settings()
    markets = {**get_dict(desired, "extraKnownMarketplaces"), **get_dict(prof.settings, "extraKnownMarketplaces")}
    routes, missing = codex.plugin_routes({"enabledPlugins": {p: True for p in wanted}, "extraKnownMarketplaces": markets})
    lines = [f"plugin {pid}: no Codex route (its marketplace is not on GitHub)" for pid in missing]
    if dry_run:
        return lines + [f"would install plugin {name} for Codex (from {src})" for src, names in routes.items() for name in names]
    listed = codex.installed_plugins()
    if listed is None:  # without the list, loadout cannot tell your plugins from new ones: install nothing
        return lines + [f"plugin {name}@?: not installed (could not list Codex plugins; run loadout profile again)"
                        for names in routes.values() for name in names]
    bk = backup.Backup(description=f"loadout profile {prof.name} (Codex)")
    out, installed = codex._install_routes(routes, bk, False, lambda line: None, listed)
    lines += out
    for pid in wanted:  # name each plugin of a failed marketplace by its full id, so only that route is skipped
        src = next(iter(codex.plugin_routes({"enabledPlugins": {pid: True}, "extraKnownMarketplaces": markets})[0]), None)
        if src is not None and f"marketplace {src}: failed:" in "\n".join(out):
            lines.append(f"plugin {pid}: not installed (its marketplace failed)")
    on = get_dict(desired, "enabledPlugins")
    for pid in wanted:
        if on.get(pid) is True or pid in codex.project_plugins():
            continue
        if pid in (listed or ()):  # installed by the user: their switch stays as it is
            lines.append(f"plugin {pid}: already installed in Codex, left on everywhere")
        elif pid in installed:
            cfg = paths.codex_home() / "config.toml"
            if cfg.exists():  # the switch below goes into it; restore must take it out again
                bk.save_copy(cfg, f"Codex config.toml before switching {pid} off outside its projects")
            record = codex.record_path()
            if record.exists():
                bk.save_copy(record, "codex-config.json before recording a project plugin")
            else:
                bk.record_created(record, "codex-config.json")
            codex.add_project_plugin(pid)
    lines += codex.apply_config(bk)
    if not bk.empty:
        lines.append(f"backup: {bk.root} (undo: loadout restore {bk.root})")
    return lines


def _trusted(project: Path) -> bool:
    tl = codex._tomllib()
    path = paths.codex_home() / "config.toml"
    if not path.exists():
        return False
    try:
        data = tl.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    projects = data.get("projects", {})
    entry = projects.get(str(project.resolve()), {}) if isinstance(projects, dict) else {}
    return isinstance(entry, dict) and entry.get("trust_level") == "trusted"


def failed_plugins(prof: profiles.Profile, lines: list[str]) -> frozenset:
    """The profile's plugins that a line reports as not installed."""
    bad = (": failed", "not installed", "no Codex route")
    return frozenset(pid for pid in _wanted(prof)[1]
                     if any(l.startswith((f"plugin {pid}:", f"plugin {pid.split('@')[0]}@?:")) and any(b in l for b in bad)  # @?: all failed
                            for l in lines))


def apply(prof: profiles.Profile, project: Path, install: bool, dry_run: bool) -> list[str]:
    lines = plugins(prof, dry_run) if install else []
    lines = config(prof, project, dry_run, skip=failed_plugins(prof, lines)) + lines  # skills: profiles.link_skills
    tables, plugins_, _ = _wanted(prof)
    has_codex_parts = bool(tables or plugins_) or any((project / ".agents" / "skills").glob("*"))
    if has_codex_parts and not dry_run and not _trusted(project):  # on every run until trusted, not only on changes
        lines.append(TRUST_NOTE)
    return lines
