"""`loadout init` and `loadout profile`."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from . import detect, paths, profiles, runner, scaffold, secrets, ui

Ask = Callable[[str], str]


def _install(profile: profiles.Profile, project: Path, dry_run: bool, info=print, warn=print,
             ran: list | None = None, calm: bool = False) -> bool:
    """Returns whether every command succeeded. info: progress lines; warn: problems; ran: collects what ran;
    calm: a failure names its command, since the "running:" line before it is not shown."""
    ok = True
    from . import targets
    for plugin_id in (profile.install if targets.claude_enabled() else []):  # Codex: codex_project.plugins
        if not (isinstance(plugin_id, str) and profiles.PLUGIN_ID.match(plugin_id)):
            warn(f"plugin {plugin_id!r}: not a name@marketplace id, skipped")
            ok = False
            continue
        cmd = ["claude", "plugin", "install", plugin_id, "--scope", "project"]
        info(secrets.redact(("would run: " if dry_run else "running: ") + " ".join(cmd)))
        if not dry_run:
            res = runner.run(cmd, cwd=str(project))
            if not res.ok:
                ok = False
                warn(secrets.redact(f"plugin {plugin_id}: failed: {res.stderr.strip()}" if calm
                                    else f"  failed: {res.stderr.strip()}"))
            elif ran is not None:
                ran.append(f"plugin {plugin_id}")
    for cmd in profile.commands:
        if not (isinstance(cmd, list) and cmd and all(isinstance(part, str) for part in cmd)):
            warn(f"command {cmd!r}: not a list of words, skipped")
            ok = False
            continue
        info(secrets.redact(("would run: " if dry_run else "running: ") + " ".join(cmd)))
        if not dry_run:
            res = runner.run(cmd, cwd=str(project))
            if not res.ok:
                ok = False
                warn(secrets.redact(f"{cmd[0]}: failed: {res.stderr.strip()}" if calm else f"  failed: {res.stderr.strip()}"))
            elif ran is not None:
                ran.append(cmd[0])
    return ok


def _calm() -> bool:
    from . import out
    return not out.VERBOSE


def add_profile(project: Path, name: str, install: bool = True, dry_run: bool = False) -> int:
    """Calm (default, not a dry run): one status line, problems below it. --verbose and --dry-run: every line."""
    from . import out
    calm = not dry_run and _calm()
    problems: list[str] = []
    steps: list[str] = []  # what the user still has to do or may want to undo: shown in calm mode too
    info = (lambda line: None) if calm else print
    warn = problems.append if calm else print
    prof = profiles.load_profile(name)
    skipped: list[str] = []
    parts: list[str] = []
    if dry_run:
        print(f"would apply profile {name}: {prof.description}")
    else:
        changed, skipped = profiles.apply_profile(prof, project)
        for path in changed:
            info(f"updated {path}")
            parts.append(path.relative_to(project).as_posix() if paths.inside(path, project) else path.name)
        for line in skipped:
            warn(line)
    skills_ok = True
    for line in profiles.copy_skills(prof, project, dry_run=dry_run):
        good = line.startswith(("copied skill", "would copy skill"))
        (info if good else warn)(line)
        if line.startswith("copied skill"):
            parts.append(line.split()[2] + " skill")
        skills_ok = skills_ok and not line.startswith("skills not copied")
    ran: list[str] = []
    ok = _install(prof, project, dry_run, info, warn, ran, calm) if install else True
    parts += [f"ran {what}" for what in ran]
    if skipped or not skills_ok:
        ok = False
    from . import codex_project, targets
    if targets.codex_enabled():
        codex_ok = True
        for line in codex_project.apply(prof, project, install=install, dry_run=dry_run):
            bad = line.startswith("skipped") or any(s in line for s in (
                ": failed", "not installed", "no Codex route", "not linked", "switched off", "left as is"))
            step = line == codex_project.TRUST_NOTE or line.startswith("backup: ")
            (warn if bad else steps.append if step and calm else info)(line)
            if bad:
                ok = codex_ok = False
        if not dry_run and codex_ok:
            parts.append("Codex")
    if prof.notes:
        info(f"note ({name}): {prof.notes}")
    if calm:
        summary = ", ".join(parts) or "nothing to change"
        out.status(f"Profile {name}", summary if ok else "applied with problems (below)", "ok" if ok else "warn")
        for line in problems + steps:
            out.problem(line.strip())
    elif not ok:
        print(f"profile {name}: applied with problems (see the lines above)")
    return 0 if ok else 1


def init(project: Path, names: list[str], yes: bool, install: bool, dry_run: bool, ask: Ask,
         interactive: bool | None = None) -> int:
    if interactive is None:
        interactive = ui.is_interactive()
    project = project.resolve()
    for name in names:
        profiles.load_profile(name)  # validate every name before changing anything
    rc = 0
    git_dir = project / ".git"
    if git_dir.is_symlink() and not paths.inside(git_dir, project):  # git init would follow it out of the repo
        print("skipped git init: .git points outside the repo")
        rc = 1
    elif not git_dir.exists():
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
    for name in chosen:
        rc = add_profile(project, name, install=install, dry_run=dry_run) or rc
    calm = not dry_run and _calm()
    created, notes = scaffold.scaffold(project, dry_run=dry_run)
    made = [path.relative_to(project).as_posix() for path in created]
    if not calm:
        for rel in made:
            print(("would create " if dry_run else "created ") + rel)
    problems = []
    if not paths.inside(project / ".gitignore", project):
        problems.append("skipped .gitignore: it points outside the repo")
        rc = 1
    ignored = scaffold.ensure_gitignore(project, dry_run=dry_run)
    if not calm:
        for line in ignored:
            print(("would add to .gitignore: " if dry_run else "added to .gitignore: ") + line)
    for note in notes:
        problems.append(note if note.startswith("skipped") else f"note: {note}")
        if note.startswith("skipped"):
            rc = 1
    if calm:
        from . import out
        summary = ", ".join(made + ([".gitignore"] if ignored else [])) or "already there"
        out.status("Scaffold", summary, "warn" if any(p.startswith("skipped") for p in problems) else "ok")
        for line in problems:
            out.problem(line)
    else:
        for line in problems:
            print(line)
    from . import targets
    if targets.claude_enabled():
        print("next: start Claude Code here and run /loadout:onboard")
    else:
        print("next: start Codex here and ask it to use the loadout:onboard skill")
    return rc
