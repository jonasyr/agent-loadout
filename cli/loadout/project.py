"""`loadout init` and `loadout profile`."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from . import detect, profiles, runner, scaffold, ui

Ask = Callable[[str], str]


def _install(profile: profiles.Profile, project: Path, dry_run: bool) -> bool:
    """Returns whether every command succeeded."""
    ok = True
    from . import targets
    for plugin_id in (profile.install if targets.claude_enabled() else []):  # Codex: codex_project.plugins
        cmd = ["claude", "plugin", "install", plugin_id, "--scope", "project"]
        print(("would run: " if dry_run else "running: ") + " ".join(cmd))
        if not dry_run:
            res = runner.run(cmd, cwd=str(project))
            if not res.ok:
                ok = False
                print(f"  failed: {res.stderr.strip()}")
    for cmd in profile.commands:
        print(("would run: " if dry_run else "running: ") + " ".join(cmd))
        if not dry_run:
            res = runner.run(cmd, cwd=str(project))
            if not res.ok:
                ok = False
                print(f"  failed: {res.stderr.strip()}")
    return ok


def add_profile(project: Path, name: str, install: bool = True, dry_run: bool = False) -> int:
    prof = profiles.load_profile(name)
    skipped: list[str] = []
    if dry_run:
        print(f"would apply profile {name}: {prof.description}")
    else:
        changed, skipped = profiles.apply_profile(prof, project)
        for path in changed:
            print(f"updated {path}")
        for line in skipped:
            print(line)
    for line in profiles.copy_skills(prof, project, dry_run=dry_run):
        print(line)
    ok = _install(prof, project, dry_run) if install else True
    if skipped:
        ok = False
    from . import codex_project, targets
    if targets.codex_enabled():
        for line in codex_project.apply(prof, project, install=install, dry_run=dry_run):
            print(line)
            if line.startswith("skipped") or any(s in line for s in (": failed", "not installed", "no Codex route", "not linked",
                                                                  "switched off", "left as is")):
                ok = False
    if prof.notes:
        print(f"note ({name}): {prof.notes}")
    if not ok:
        print(f"profile {name}: applied with problems (see the lines above)")
    return 0 if ok else 1


def init(project: Path, names: list[str], yes: bool, install: bool, dry_run: bool, ask: Ask,
         interactive: bool | None = None) -> int:
    if interactive is None:
        interactive = ui.is_interactive()
    project = project.resolve()
    for name in names:
        profiles.load_profile(name)  # validate every name before changing anything
    if not (project / ".git").exists():
        if dry_run:
            print("would offer: git init")
        elif yes or ui.confirm(ask, f"{project} is not a git repository. Run git init? [y/N] "):
            runner.run(["git", "init"], cwd=str(project))
    chosen = list(names)
    if not chosen:
        suggested = detect.detect_profiles(project)
        print(f"suggested profiles: {', '.join(suggested) or '(none)'} — available: {', '.join(profiles.list_profiles())}")
        if yes or dry_run:
            chosen = suggested
        elif not interactive:
            print("non-interactive: no profiles applied (name them, e.g. `loadout init web`, or pass --yes)")
        else:
            answer = ask("profiles to apply (comma separated, empty = suggested, '-' = none): ").strip()
            chosen = suggested if answer == "" else [] if answer == "-" else [a.strip() for a in answer.split(",") if a.strip()]
            for name in chosen:
                profiles.load_profile(name)
    rc = 0
    for name in chosen:
        rc = add_profile(project, name, install=install, dry_run=dry_run) or rc
    created, notes = scaffold.scaffold(project, dry_run=dry_run)
    for path in created:
        print(("would create " if dry_run else "created ") + str(path.relative_to(project)))
    for line in scaffold.ensure_gitignore(project, dry_run=dry_run):
        print(("would add to .gitignore: " if dry_run else "added to .gitignore: ") + line)
    for note in notes:
        print(f"note: {note}")
    from . import targets
    if targets.claude_enabled():
        print("next: start Claude Code here and run /loadout:onboard")
    else:
        print("next: start Codex here and ask it to use the loadout:onboard skill")
    return rc
