"""`loadout init` and `loadout profile`."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from . import detect, profiles, runner, scaffold

Ask = Callable[[str], str]


def _install(profile: profiles.Profile, project: Path, dry_run: bool) -> None:
    for plugin_id in profile.install:
        cmd = ["claude", "plugin", "install", plugin_id, "--scope", "project"]
        print(("would run: " if dry_run else "running: ") + " ".join(cmd))
        if not dry_run:
            res = runner.run(cmd, cwd=str(project))
            if not res.ok:
                print(f"  failed: {res.stderr.strip()}")
    for cmd in profile.commands:
        print(("would run: " if dry_run else "running: ") + " ".join(cmd))
        if not dry_run:
            res = runner.run(cmd, cwd=str(project))
            if not res.ok:
                print(f"  failed: {res.stderr.strip()}")


def add_profile(project: Path, name: str, install: bool = True, dry_run: bool = False) -> int:
    prof = profiles.load_profile(name)
    if dry_run:
        print(f"would apply profile {name}: {prof.description}")
    else:
        for path in profiles.apply_profile(prof, project):
            print(f"updated {path}")
    if install:
        _install(prof, project, dry_run)
    if prof.notes:
        print(f"note ({name}): {prof.notes}")
    return 0


def init(project: Path, names: list[str], yes: bool, install: bool, dry_run: bool, ask: Ask) -> int:
    project = project.resolve()
    if not (project / ".git").exists():
        if dry_run:
            print("would offer: git init")
        elif yes or ask(f"{project} is not a git repository. Run git init? [y/N] ").strip().lower() == "y":
            runner.run(["git", "init"], cwd=str(project))
    chosen = list(names)
    if not chosen:
        suggested = detect.detect_profiles(project)
        print(f"suggested profiles: {', '.join(suggested) or '(none)'} — available: {', '.join(profiles.list_profiles())}")
        if yes or dry_run:
            chosen = suggested
        else:
            answer = ask("profiles to apply (comma separated, empty = suggested, '-' = none): ").strip()
            chosen = suggested if answer == "" else [] if answer == "-" else [a.strip() for a in answer.split(",") if a.strip()]
    for name in chosen:
        add_profile(project, name, install=install, dry_run=dry_run)
    created, notes = scaffold.scaffold(project, dry_run=dry_run)
    for path in created:
        print(("would create " if dry_run else "created ") + str(path.relative_to(project)))
    for line in scaffold.ensure_gitignore(project, dry_run=dry_run):
        print(("would add to .gitignore: " if dry_run else "added to .gitignore: ") + line)
    for note in notes:
        print(f"note: {note}")
    print("next: start Claude Code here and run /loadout:onboard")
    return 0
