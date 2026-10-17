"""`loadout init` and `loadout profile`."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from . import detect, paths, profiles, runner, scaffold, secrets, ui

Ask = Callable[[str], str]

MANAGE_OFF = "manage is false in .loadout.json: nothing written"
NO_TERMINAL = "no terminal: nothing written (run it again with --yes to apply this plan)"
DECLINED = "nothing changed"
QUESTION = "Apply these changes? [y/N] "
AGENTS_QUESTION = ("Which agents is this repo for? 1 Claude Code, 2 Codex, 3 both (Enter: {default}; it decides "
                   "the repo's files for everyone who clones it) ")
CLAUDE_OFF = "not installed for Claude Code, which is off for you (a Claude Code user installs it with loadout profile here)"


def _install(profile: profiles.Profile, project: Path, dry_run: bool, info=print, warn=print,
             ran: list | None = None, calm: bool = False, bk=None) -> bool:
    """Returns whether every command succeeded. info: progress lines; warn: problems; ran: collects what ran;
    calm: a failure names its command, since the "running:" line before it is not shown. bk: the run's backup,
    which saves .claude/settings.json before `claude plugin install` changes it."""
    ok = True
    from . import repo_config, targets
    claude = repo_config.agents(project)["claude"]
    if claude and not targets.claude_enabled():
        for plugin_id in profile.install:
            info(f"plugin {plugin_id}: {CLAUDE_OFF}")
    for plugin_id in (profile.install if claude and targets.claude_enabled() else []):  # Codex: codex_project.plugins
        if not (isinstance(plugin_id, str) and profiles.PLUGIN_ID.match(plugin_id)):
            warn(f"plugin {plugin_id!r}: not a name@marketplace id, skipped")
            ok = False
            continue
        cmd = ["claude", "plugin", "install", plugin_id, "--scope", "project"]
        info(secrets.redact(("would run: " if dry_run else "running: ") + " ".join(cmd)))
        if not dry_run:
            if bk is not None:
                from .repo_writes import RepoWrites
                RepoWrites(project)._record_touch(project / ".claude" / "settings.json", "claude", bk)
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


def approver(yes: bool, ask: Ask, interactive: bool):
    """The yes for a plan: --yes, else the question in a terminal; without a terminal, no."""
    def approve(plan: list[str]) -> bool:
        if yes:
            return True
        if not interactive:
            print(NO_TERMINAL)
            return False
        return ui.confirm(ask, QUESTION)
    return approve


def _agent_names(on: dict) -> str:
    return " and ".join(n for n, k in (("Claude Code", "claude"), ("Codex", "codex")) if on[k]) or "none"


def _show(project: Path, title: str, w, notes: list[str]) -> list[str]:
    from . import repo_config
    plan = [f"Plan for {project} ({title}; this repo's agents: {_agent_names(repo_config.agents(project))}):"]
    plan += w.render() or ["  (no file changes)"]
    plan += [secrets.redact(f"  note    {n}") for n in notes]
    print("\n".join(plan))
    return plan


CODEX_BAD = (": failed", "not installed", "no Codex route", "not linked", "switched off", "left as is")


def _plan_profile(prof: profiles.Profile, project: Path, w, install: bool) -> tuple[list[str], list[str]]:
    """Collect everything a profile changes in the repo into `w`. Returns (notes, failures): both are shown in the
    plan; failures also make the run end with problems (exit 1), as `_profile_now` does."""
    import os
    from . import codex_project, repo_config, targets
    on = repo_config.agents(project)
    notes: list[str] = []
    failures: list[str] = []
    _, skipped = profiles.apply_profile(prof, project, w=w)
    failures += skipped
    notes += profiles.repo_off_notes(prof, project)
    before = len(w.changes)
    for line in profiles.copy_skills(prof, project, w=w):
        if not line.startswith("copied skill"):
            (failures if line.startswith("skills not copied") else notes).append(line)
    real, other = profiles.repo_skill_dirs(project)
    if other is not None:  # skills planned for copying get their link in the same plan
        for c in w.changes[before:]:
            if c.kind == "copy" and c.path.parent == real:
                rel = real.relative_to(project).as_posix()
                agent = profiles.AGENT_OF[other.relative_to(project).as_posix()]
                w.link(other / c.path.name, os.path.join("..", "..", *rel.split("/"), c.path.name),
                       f"skill {c.path.name} for {agent}")
    if install:
        for pid in prof.install:
            if not (isinstance(pid, str) and profiles.PLUGIN_ID.match(pid)):
                failures.append(f"plugin {pid!r}: not a name@marketplace id, skipped")
            elif on["claude"] and targets.claude_enabled():
                w.run(["claude", "plugin", "install", pid, "--scope", "project"], profiles.reason(prof),
                      touches=(project / ".claude" / "settings.json",))
            elif on["claude"]:
                notes.append(f"plugin {pid}: {CLAUDE_OFF}")
        for cmd in prof.commands:
            if isinstance(cmd, list) and cmd and all(isinstance(part, str) for part in cmd):
                w.run(cmd, profiles.reason(prof))
            else:
                failures.append(f"command {cmd!r}: not a list of words, skipped")
    failures += [l for l in profiles.link_skills(project, False, w=w) if "not linked" in l or "left as is" in l]
    if on["codex"]:
        for line in codex_project.config(prof, project, False, w=w):
            if line.startswith(("added", "enabled", "would")):
                continue
            (failures if line.startswith("skipped") or any(b in line for b in CODEX_BAD) else notes).append(line)
        if install and not targets.codex_enabled() and codex_project._wanted(prof)[1]:
            notes.append(f"Codex plugins of profile {prof.name}: not installed for Codex, which is off for you "
                         "(a Codex user installs them with loadout profile here)")
        if install and targets.codex_enabled() and codex_project._wanted(prof)[1]:
            notes.append(f"Codex plugins of profile {prof.name}: installed in your Codex (outside this repo, "
                         "with their own backup)")
    return notes, failures


def _codex_after_installs(project: Path, install: bool) -> bool:
    """True when the repo's .codex/config.toml waits for the Codex plugin installs (so it names only plugins that
    installed: a subset of what the plan showed)."""
    from . import repo_config, targets
    return install and repo_config.agents(project)["codex"] and targets.codex_enabled()


def _after_apply(prof: profiles.Profile, project: Path, bk, install: bool, drive_note: bool,
                 notes: list[str], problems: list[str], approve=None) -> None:
    """After the plan's files and commands: a follow-up plan for skills the commands installed, then the Codex
    plugins and the repo's Codex config without the plugins that failed."""
    from . import codex_project, repo_config, targets, wsl
    from .repo_writes import RepoWrites
    later = RepoWrites(project)
    late = profiles.link_skills(project, False, w=later)
    problems += [l for l in late if "not linked" in l or "left as is" in l]
    if later.changes:
        follow = [f"The commands of profile {prof.name} added skills; link them for the repo's other agent:"]
        follow += later.render()
        print("\n".join(follow))
        if approve is None or approve(follow):
            problems += later.apply(bk)
        else:
            notes.append(f"skills the commands added are not linked; run loadout profile {prof.name} again to link them")
    if repo_config.agents(project)["codex"] and targets.codex_enabled():
        if install:
            lines = codex_project.plugins(prof, False)
            for line in lines:
                if line.startswith("backup: "):  # Codex's own backup: its undo line must reach the user
                    notes.append(line)
                elif line.startswith("skipped") or any(s in line for s in (": failed", "not installed", "no Codex route")):
                    problems.append(line)
            failed = codex_project.failed_plugins(prof, lines)
            for line in codex_project.config(prof, project, False, skip=failed, w=RepoWrites(project, now=True, bk=bk)):
                if line.startswith("skipped") or "left as is" in line:
                    problems.append(line)
            for pid in sorted(failed):
                notes.append(f"plugin {pid}: not named in .codex/config.toml, its install failed")
        tables, plugins_, _ = codex_project._wanted(prof)
        if (tables or plugins_ or any((project / ".agents" / "skills").glob("*"))) and not codex_project._trusted(project):
            if codex_project.TRUST_NOTE not in notes:
                notes.append(codex_project.TRUST_NOTE)
    note = wsl.repo_note(project) if drive_note else None
    if note and note not in notes:
        notes.append(note)
    if prof.notes:
        notes.append(f"note ({prof.name}): {prof.notes}")


def _report(title: str, bk, notes: list[str], problems: list[str]) -> int:
    from . import out
    out.status(title, "applied" if not problems else "applied with problems (below)", "ok" if not problems else "warn")
    for line in problems + notes:
        out.problem(secrets.redact(line))
    if not bk.empty:
        print(f"undo: loadout restore {bk.root}")
    return 1 if problems else 0


def _config_or_report(project: Path):
    from . import repo_config
    try:
        return repo_config.load(project)
    except repo_config.Invalid as exc:
        print(exc)
        return None


def add_profile(project: Path, name: str, install: bool = True, dry_run: bool = False, drive_note: bool = True,
                approve=None) -> int:
    """approve(plan lines) -> bool: show the plan and ask (the CLI). None: apply at once, backed up (callers that
    already asked). dry_run: show the plan, change nothing."""
    from . import backup, repo_config
    from .repo_writes import RepoWrites
    cfg = _config_or_report(project)
    if cfg is None:
        return 1
    prof = profiles.load_profile(name)
    if approve is None and not dry_run and cfg.manage:
        bk = backup.Backup(description=f"loadout profile {name} in {project}", repo=project)
        rc = _profile_now(project, prof, install, drive_note, bk)
        if not bk.empty:
            print(f"undo: loadout restore {bk.root}")
        return rc
    w = RepoWrites(project)
    w.watch(project / repo_config.FILE)  # the agent choice the plan was made for
    notes: list[str] = []
    if not cfg.exists:
        mine = frozenset(a for a, on in repo_config.user_agents().items() if on)
        w.create(project / repo_config.FILE, repo_config.new_text(project, mine),
                 "loadout: which agents this repo is for (commit it)")
    planned_notes, failures = _plan_profile(prof, project, w, install)
    notes += planned_notes
    plan = _show(project, f"profile {name}", w, failures + notes)
    if not cfg.manage:
        print(MANAGE_OFF)
        return 0
    if dry_run:
        print("dry run: nothing changed")
        return 0
    if approve is not None and not approve(plan):
        print(DECLINED)
        return 0
    bk = backup.Backup(description=f"loadout profile {name} in {project}", repo=project)
    hold = frozenset({project / ".codex" / "config.toml"}) if _codex_after_installs(project, install) else frozenset()
    problems = failures + w.apply(bk, hold=hold)
    notes = [n for n in notes if not n.startswith(("Codex plugins of profile",))]
    _after_apply(prof, project, bk, install, drive_note, notes, problems, approve=approve)
    return _report(f"Profile {name}", bk, notes, problems)


def _profile_now(project: Path, prof: profiles.Profile, install: bool, drive_note: bool, bk) -> int:
    """Apply a profile at once, every write backed up in `bk` (callers that already asked, e.g. adopt). Calm
    (default): one status line, problems below it; --verbose: every line. drive_note: the WSL note for a repo on a
    Windows drive (init prints it with the first profile only)."""
    from . import out, repo_config
    from .repo_writes import RepoWrites
    name, dry_run = prof.name, False
    w = RepoWrites(project, now=True, bk=bk)
    on = repo_config.agents(project)
    calm = _calm()
    problems: list[str] = []
    steps: list[str] = []  # what the user still has to do or may want to undo: shown in calm mode too
    info = (lambda line: None) if calm else print
    warn = problems.append if calm else print
    skipped: list[str] = []
    parts: list[str] = []
    changed, skipped = profiles.apply_profile(prof, project, w=w)
    for path in changed:
        info(f"updated {path}")
        parts.append(path.relative_to(project).as_posix() if paths.inside(path, project) else path.name)
    for line in skipped:
        warn(line)
    for line in profiles.repo_off_notes(prof, project):
        (steps.append if calm else info)(line)
    skills_ok = True
    for line in profiles.copy_skills(prof, project, w=w):
        good = line.startswith(("copied skill", "would copy skill"))
        (info if good else warn)(line)
        if line.startswith("copied skill"):
            parts.append(line.split()[2] + " skill")
        skills_ok = skills_ok and not line.startswith("skills not copied")
    ran: list[str] = []
    ok = _install(prof, project, dry_run, info, warn, ran, calm, bk=bk) if install else True
    parts += [f"ran {what}" for what in ran]
    links_ok = True
    for line in profiles.link_skills(project, dry_run, w=w):  # after the commands, which may install skills
        bad = "not linked" in line or "left as is" in line
        (warn if bad else info)(line)
        links_ok = links_ok and not bad
        if line.startswith("linked skill"):
            parts.append(line.split()[2] + " skill link")
    if not links_ok:
        ok = False
    if skipped or not skills_ok:
        ok = False
    from . import codex_project, targets
    if on["codex"]:  # the repo's Codex file; installs only for a user with Codex on
        codex_ok = links_ok
        for line in codex_project.apply(prof, project, install=install, dry_run=dry_run, w=w,
                                        user_codex=targets.codex_enabled()):
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
    from . import wsl
    note = wsl.repo_note(project) if drive_note else None
    if note:
        (steps.append if calm else info)(note)
    if calm:
        summary = ", ".join(parts) or "nothing to change"
        out.status(f"Profile {name}", summary if ok else "applied with problems (below)", "ok" if ok else "warn")
        for line in problems + steps:
            out.problem(line.strip())
    elif not ok:
        print(f"profile {name}: applied with problems (see the lines above)")
    return 0 if ok else 1


def init(project: Path, names: list[str], yes: bool, install: bool, dry_run: bool, ask: Ask,
         interactive: bool | None = None, agents: frozenset | None = None) -> int:
    """Plan the repo's setup (agents, profiles, scaffold, .gitignore), show it, and apply it after a yes."""
    from . import backup, repo_config
    from .repo_writes import RepoWrites
    if interactive is None:
        interactive = ui.is_interactive()
    project = project.resolve()
    for name in names:
        profiles.load_profile(name)  # validate every name before changing anything
    cfg = _config_or_report(project)
    if cfg is None:
        return 1
    rc = 0
    git_dir = project / ".git"
    if git_dir.is_symlink() and not paths.inside(git_dir, project):  # git init would follow it out of the repo
        print("skipped git init: .git points outside the repo")
        rc = 1
    git_init = not git_dir.exists() and not git_dir.is_symlink()  # planned below, so a declined plan skips it too
    mine = frozenset(a for a, on in repo_config.user_agents().items() if on)
    if agents is None and cfg.agents is None:
        agents = mine
        if interactive and not yes and not dry_run and cfg.manage:
            default = _agent_names({a: a in mine for a in repo_config.AGENTS})
            answer = ask(AGENTS_QUESTION.format(default=default)).strip()
            agents = {"1": frozenset({"claude"}), "2": frozenset({"codex"}),
                      "3": frozenset({"claude", "codex"})}.get(answer, mine)
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
    w = RepoWrites(project)
    w.watch(project / repo_config.FILE)  # the agent choice the plan was made for
    notes: list[str] = []
    failures: list[str] = []
    if git_init:
        w.run(["git", "init"], "init: make this folder a git repository")
    if agents is not None:
        try:
            text = repo_config.new_text(project, agents)
        except repo_config.Invalid as exc:
            print(exc)
            return 1
        if text is not None:
            (w.modify if cfg.exists else w.create)(project / repo_config.FILE, text,
                                                   "init: which agents this repo is for (commit it)")
        dropped = (cfg.agents or frozenset()) - agents
        left = [r for r in ("CLAUDE.md", ".claude/settings.json", ".mcp.json") if "claude" in dropped and (project / r).exists()]
        left += [r for r in (".codex/config.toml",) if "codex" in dropped and (project / r).exists()]
        if left:
            notes.append(f"no longer needed for this repo's agents (yours to remove): {', '.join(left)}")
    profs = [profiles.load_profile(name) for name in chosen]
    with repo_config.pending(project, agents):
        for prof in profs:
            planned_notes, planned_failures = _plan_profile(prof, project, w, install)
            notes += planned_notes
            failures += planned_failures
        _, scaffold_notes = scaffold.scaffold(project, w=w)
        if not paths.inside(project / ".gitignore", project):
            notes.append("skipped .gitignore: it points outside the repo")
            rc = 1
        scaffold.ensure_gitignore(project, w=w)
        for note in scaffold_notes:
            notes.append(note if note.startswith("skipped") else f"note: {note}")
            if note.startswith("skipped"):
                rc = 1
        title = "init" + (f", profiles {', '.join(chosen)}" if chosen else "")
        plan = _show(project, title, w, failures + notes)
    if not cfg.manage:
        print(MANAGE_OFF)
        return 0
    if dry_run:
        print("dry run: nothing changed")
        return 0
    if not approver(yes, ask, interactive)(plan):
        print(DECLINED)
        return 0
    bk = backup.Backup(description=f"loadout init in {project}", repo=project)
    hold = frozenset({project / ".codex" / "config.toml"}) if _codex_after_installs(project, install) else frozenset()
    problems = failures + w.apply(bk, hold=hold)
    notes = [n for n in notes if not n.startswith("Codex plugins of profile")]
    for i, prof in enumerate(profs):
        _after_apply(prof, project, bk, install, i == 0, notes, problems, approve=approver(yes, ask, interactive))
    rc = _report("Init", bk, notes, problems) or rc
    from . import targets
    on = repo_config.agents(project)
    if on["claude"] and targets.claude_enabled():
        print("next: start Claude Code here and run /loadout:onboard")
    else:
        print("next: start Codex here and ask it to use the loadout:onboard skill")
    return rc
