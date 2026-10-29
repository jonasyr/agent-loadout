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
STILL_TO_DO = "Still to do:"


class Todo(str):
    """A note the user must act on: numbered under "Still to do:" at the end, once."""


class Info(str):
    """A note shown only with --verbose."""


class Done(str):
    """A line about what the run did beyond the plan's files (e.g. the skill links it made): shown in calm mode."""


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
    adds, bad = profiles.marketplace_adds(profile) if claude and targets.claude_enabled() else ([], [])
    for line in bad:
        warn(line)
        ok = False
    for name, cmd in adds:  # the marketplace the installs need (ADR 0037); Claude Code's own, restore cannot undo it
        info(secrets.redact(("would run: " if dry_run else "running: ") + " ".join(cmd)))
        if not dry_run:
            res = runner.run(cmd, cwd=str(project))
            if not res.ok:
                ok = False
                warn(secrets.redact(f"marketplace {name}: failed: {res.stderr.strip()}" if calm
                                    else f"  failed: {res.stderr.strip()}"))
            elif ran is not None:
                ran.append(f"marketplace {name}")  # the name: the origin can carry a token
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


TAKE_QUESTION = "Use the profile's values for these? [y/N] "
KEPT_NO_TERMINAL = "  kept the repo's values (run it again with --take-profile to use the profile's)"


def chooser(take: bool, ask: Ask, interactive: bool, dry_run: bool = False):
    """Whether to use the profile's values where a person changed an entry: --take-profile, else the question in a
    terminal; without one (and in a dry run) the repo's values stay. The entries are printed in every case."""
    def decide(lines: list[str]) -> bool:
        from .out import printable
        print("\n".join(printable(line) for line in lines))
        if take:
            return True
        if dry_run:
            return False
        if not interactive:
            print(KEPT_NO_TERMINAL)
            return False
        return ui.confirm(ask, TAKE_QUESTION)
    decide.take = take  # apply_profile then also lists what was offered before and declined
    return decide


def _agent_names(on: dict) -> str:
    return " and ".join(n for n, k in (("Claude Code", "claude"), ("Codex", "codex")) if on[k]) or "none"


def _show(project: Path, title: str, w, notes: list[str], skips=()) -> list[str]:
    from . import repo_config
    calm = _calm()
    plan = [f"Plan for {project.name if calm else project} ({title}; this repo's agents: "
            f"{_agent_names(repo_config.agents(project))}):"]
    plan += w.render(calm=calm) or ["  (no file changes)"]
    plan += [secrets.redact(f"  skip    {s.removeprefix('skipped ')}") for s in skips]
    plan += [secrets.redact(f"  note    {n}") for n in notes if not (calm and isinstance(n, Info))]
    from .out import printable
    plan = [printable(line) for line in plan]  # keys and values come from repo files
    print("\n".join(plan))
    return plan


CODEX_BAD = (": failed", "not installed", "no Codex route", "not linked", "switched off", "left as is", "has no plugin command")
RECORD_LATER = (".loadout.json: the record of profile {name}'s .codex/config.toml entries is written after the Codex "
                "plugin installs, naming only what was added")


def _planned(prof: profiles.Profile, project: Path) -> list[str]:
    """The parts of `prof` this repo's Codex can't take: planned skips (spec 2026-10-29 init output, G2)."""
    from . import codex_project, repo_config
    return codex_project.planned_skips(prof) if repo_config.agents(project)["codex"] else []


def _plan_profile(prof: profiles.Profile, project: Path, w, install: bool,
                  decide=None) -> tuple[list[str], list[str], list[str]]:
    """Collect everything a profile changes in the repo into `w`. Returns (notes, failures, skips): all are shown in
    the plan; failures also make the run end with problems (exit 1), as `_profile_now` does; skips are what this
    repo's Codex can't take, said once and not a problem."""
    import os
    from . import codex_project, repo_config, targets
    on = repo_config.agents(project)
    notes: list[str] = []
    failures: list[str] = []
    _, skipped = profiles.apply_profile(prof, project, w=w, decide=decide, notes=notes)
    failures += skipped
    notes += profiles.repo_off_notes(prof, project, install)
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
        if on["claude"] and targets.claude_enabled():  # a marketplace the installs need comes first (ADR 0037)
            adds, bad = profiles.marketplace_adds(prof)
            failures += bad
            for _, cmd in adds:
                w.run(cmd, profiles.reason(prof, "settings.extraKnownMarketplaces"))
        for pid in prof.install:
            if not (isinstance(pid, str) and profiles.PLUGIN_ID.match(pid)):
                failures.append(f"plugin {pid!r}: not a name@marketplace id, skipped")
            elif on["claude"] and targets.claude_enabled():
                w.run(["claude", "plugin", "install", pid, "--scope", "project"], profiles.reason(prof),
                      touches=(project / ".claude" / "settings.json",))
            elif on["claude"]:
                notes.append(Todo(f"plugin {pid}: {CLAUDE_OFF}"))
        for cmd in prof.commands:
            if isinstance(cmd, list) and cmd and all(isinstance(part, str) for part in cmd):
                w.run(cmd, profiles.reason(prof))
            else:
                failures.append(f"command {cmd!r}: not a list of words, skipped")
        if prof.commands and other is not None:  # the plan the user approves names the links made after the run
            rel = other.relative_to(project).as_posix()
            w.promise(f"skills these commands add, for {profiles.AGENT_OF[rel]} ({rel})")
    from . import skill_links
    links = profiles.link_skills(project, False, w=w)
    failures += [l for l in links if "not linked" in l or "left as is" in l]
    notes += [Todo(l) for l in links if l.startswith(skill_links.PREFIX)]
    if on["codex"]:
        held = _codex_after_installs(project, install)
        for line in codex_project.config(prof, project, False, w=w, record=not held):
            if line.startswith(("added", "enabled", "would")):
                continue
            (failures if line.startswith("skipped") or any(b in line for b in CODEX_BAD) else notes).append(line)
        if held and any(codex_project._wanted(prof)[:2]):
            try:  # the record is written later; say now if .loadout.json's layout will not take it
                repo_config.record_text(project, repo_config.current_text(project, w), prof.name, {})
                notes.append(Info(RECORD_LATER.format(name=prof.name)))
            except repo_config.Invalid as exc:
                failures.append(str(exc))
        if install and not targets.codex_enabled() and codex_project._wanted(prof)[1]:
            notes.append(Todo(f"Codex plugins of profile {prof.name}: not installed for Codex, which is off for "
                              "you (a Codex user installs them with loadout profile here)"))
        if install and targets.codex_enabled() and codex_project._wanted(prof)[1] and _no_codex():
            # neither a usable CLI nor VS Code's Codex extension: the plan shows the failures the run will report
            failures.extend(codex_project.plugins(prof, dry_run=True))
        elif install and targets.codex_enabled() and codex_project._wanted(prof)[1]:
            notes.append(Info(f"Codex plugins of profile {prof.name}: installed in your Codex (outside this repo, "
                              "with their own backup)"))
    skips = _planned(prof, project)
    return [n for n in notes if n not in skips], [f for f in failures if f not in skips], skips


def _no_codex() -> bool:
    from . import codex
    return not codex.has_codex()


def _codex_after_installs(project: Path, install: bool) -> bool:
    """True when the repo's .codex/config.toml waits for the Codex plugin installs (so it names only plugins that
    installed: a subset of what the plan showed)."""
    from . import repo_config, targets
    return install and repo_config.agents(project)["codex"] and targets.codex_enabled()


def _after_apply(prof: profiles.Profile, project: Path, bk, install: bool, drive_note: bool,
                 notes: list[str], problems: list[str]) -> bool:
    """After the plan's files and commands: links for the skills the commands installed (the plan's yes covers
    them; backed up like every repo write), then the Codex plugins and the repo's Codex config without the plugins
    that failed."""
    from . import codex, codex_project, repo_config, targets, wsl
    from .repo_writes import RepoWrites
    skips = _planned(prof, project)
    later = RepoWrites(project)
    later.watch(project / repo_config.FILE)  # the follow-up question is a second window for a change
    late = profiles.link_skills(project, False, w=later)
    problems += [l for l in late if "not linked" in l or "left as is" in l]
    from . import skill_links
    notes += [Todo(l) for l in late if l.startswith(skill_links.PREFIX) and l not in notes]
    if later.changes:
        if not _calm():
            from .out import printable
            follow = [f"linked for the repo's other agent (skills profile {prof.name}'s commands added):"]
            print("\n".join(printable(line) for line in follow + later.render()))
        failed = later.apply(bk)
        problems += failed
        if later.stale:  # .loadout.json changed: nothing after this may run
            return False
        notes += [Done(f"linked {c.why}") for c in later.changes
                  if c.kind == "link" and not any(c.why in f for f in failed)]
    if repo_config.agents(project)["codex"] and targets.codex_enabled():
        if install:
            lines = codex_project.plugins(prof, False)
            for line in lines:
                if line.startswith("backup: "):  # Codex's own backup: its undo line must reach the user
                    notes.append(line)
                elif line in skips:
                    continue
                elif line.startswith("skipped") or line == codex.PLUGINS_OLD or any(
                        s in line for s in (": failed", "not installed", "no Codex route")):
                    problems.append(line)
            failed = codex_project.failed_plugins(prof, lines)
            for line in codex_project.config(prof, project, False, skip=failed, w=RepoWrites(project, now=True, bk=bk)):
                if line in skips:
                    continue
                if line.startswith("skipped") or "left as is" in line:
                    problems.append(line)
                elif line.startswith(repo_config.FILE + ":") and line not in notes:
                    notes.append(Info(line))
            for pid in sorted(failed):
                notes.append(f"plugin {pid}: not named in .codex/config.toml, its install failed")
        tables, plugins_, _ = codex_project._wanted(prof)
        if (tables or plugins_ or any((project / ".agents" / "skills").glob("*"))) and not codex_project._trusted(project):
            if codex_project.TRUST_NOTE not in notes:
                notes.append(Todo(codex_project.TRUST_NOTE))
    note = wsl.repo_note(project) if drive_note else None
    if note and note not in notes:
        notes.append(Todo(note))
    if prof.notes:
        notes.append(Todo(f"note ({prof.name}): {prof.notes}"))
    return True


def _report(title: str, bk, notes: list[str], problems: list[str], done: str = "applied",
            todos_after=()) -> int:
    """The status line, the problems, then each to-do once, numbered (calm); --verbose also lists the other notes.
    A `backup: …` note is Codex's own undo line: always shown."""
    from . import out
    out.status(title, done if not problems else "applied with problems (below)", "ok" if not problems else "warn")
    todos = list(dict.fromkeys([n for n in notes if isinstance(n, Todo)] + list(todos_after)))
    shown = [n for n in notes if not isinstance(n, Todo)
             and (not _calm() or isinstance(n, Done) or n.startswith("backup: "))]
    for line in dict.fromkeys(problems + shown):  # each said once
        out.problem(secrets.redact(line))  # problem() escapes control characters, keeping line breaks
    if todos:
        from .out import printable
        print(STILL_TO_DO)
        for i, line in enumerate(todos, 1):
            print(printable(secrets.redact(f"  {i}. {line}")))
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


ALREADY = "profile {name}: already applied here (nothing to change)"


def missing_here(prof: profiles.Profile, project: Path) -> list[str]:
    """What this machine still lacks of `prof` (spec 2026-10-29 init output, G4): the Claude Code plugins installed
    for this project, the Codex plugins in the user's Codex, and what the profile's commands leave behind
    (`done_when`, any of its paths). Each only for an agent that is on for the repo and the user."""
    from . import codex, codex_project, repo_config, targets
    from .jsonio import InvalidJSON, get_dict, load_json
    on = repo_config.agents(project)
    out: list[str] = []
    if on["claude"] and targets.claude_enabled():
        try:
            installed = get_dict(load_json(paths.claude_home() / "plugins" / "installed_plugins.json"), "plugins")
        except InvalidJSON:
            installed = {}
        here = str(project.resolve())
        for pid in prof.install:
            if not (isinstance(pid, str) and profiles.PLUGIN_ID.match(pid)):
                continue
            entries = installed.get(pid)
            if not any(isinstance(e, dict) and e.get("scope") in ("project", "local") and e.get("projectPath") == here
                       for e in (entries if isinstance(entries, list) else [])):
                out.append(f"plugin {pid}")
    if on["codex"] and targets.codex_enabled():
        wanted = codex_project._wanted(prof)[1]
        have = codex.installed_plugins() if wanted else set()
        out += [f"Codex plugin {pid}" for pid in wanted if have is None or pid not in have]
    # a dangling link left behind is not done: only a path that exists counts
    if prof.commands and prof.done_when and not any((project / p).exists() for p in prof.done_when):
        out += [" ".join(cmd) for cmd in prof.commands if isinstance(cmd, list)]
    return out


def _still_needed(change, missing: list[str]) -> bool:
    """Whether a planned `run` step installs or makes something this machine lacks."""
    cmd = change.cmd or []
    if " ".join(cmd) in missing:  # a profile command, matched by its own text first
        return True
    if cmd[:3] == ["claude", "plugin", "install"]:
        return f"plugin {cmd[3]}" in missing
    if cmd[:4] == ["claude", "plugin", "marketplace", "add"]:  # needed only for a plugin still to install
        return any(m.startswith("plugin ") for m in missing)
    return " ".join(cmd) in missing


def add_profile(project: Path, name: str, install: bool = True, dry_run: bool = False, drive_note: bool = True,
                approve=None, result: dict | None = None, decide=None, refresh: bool = False) -> int:
    """approve(plan lines) -> bool: show the plan and ask (the CLI). None: apply at once, backed up (callers that
    already asked). dry_run: show the plan, change nothing. refresh: plan the whole profile even when it is
    already applied here."""
    from . import backup, repo_config
    from .repo_writes import RepoWrites
    project = Path(project).resolve()  # backups record absolute paths, so restore works from any folder
    result = result if result is not None else {}
    result["applied"] = False
    cfg = _config_or_report(project)
    if cfg is None:
        return 1
    prof = profiles.load_profile(name)
    if approve is None and not dry_run and cfg.manage:
        bk = backup.Backup(description=f"loadout profile {name} in {project}", repo=project)
        rc = _profile_now(project, prof, install, drive_note, bk)
        result["applied"] = True
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
    planned_notes, failures, skips = _plan_profile(prof, project, w, install, decide)
    notes += planned_notes
    if not refresh and cfg.exists and cfg.manage and not any(c.kind != "run" for c in w.changes) and not failures:
        try:
            recorded = name in repo_config.records(project)
        except repo_config.Invalid:
            recorded = False
        if recorded:
            missing = missing_here(prof, project) if install else []
            if not missing:
                from . import out
                result["already"] = True
                print(ALREADY.format(name=name))
                for line in dict.fromkeys(n for n in notes if isinstance(n, profiles.Kept)):
                    out.problem(secrets.redact(line))  # what stays the repo's own (ADR 0031)
                return 0
            w.keep(lambda c: c.kind != "run" or _still_needed(c, missing))
            codex_missing = [m.removeprefix("Codex plugin ") for m in missing if m.startswith("Codex plugin ")]
            if codex_missing:
                notes.append(f"Codex plugins to install here: {', '.join(codex_missing)}")
    plan = _show(project, f"profile {name}", w, failures + notes, skips)
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
    if w.stale:  # .loadout.json changed after the plan: no dependent step runs either
        return _report(f"Profile {name}", bk, [], problems[-1:])
    result["applied"] = True
    notes = [n for n in notes if not n.startswith(("Codex plugins of profile",))]
    _after_apply(prof, project, bk, install, drive_note, notes, problems)
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
    from .out import printable
    info = (lambda line: None) if calm else (lambda line: print(printable(line)))  # lines carry repo text
    warn = problems.append if calm else (lambda line: print(printable(line)))
    skipped: list[str] = []
    parts: list[str] = []
    merge_notes: list[str] = []
    changed, skipped = profiles.apply_profile(prof, project, w=w, notes=merge_notes)
    for line in merge_notes:
        (steps.append if calm else info)(line)
    for path in changed:
        info(f"updated {path}")
        parts.append(path.relative_to(project).as_posix() if paths.inside(path, project) else path.name)
    for line in skipped:
        warn(line)
    for line in profiles.repo_off_notes(prof, project, install):
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
        from . import skill_links
        if line.startswith(skill_links.PREFIX):
            (steps.append if calm else info)(line)
            continue
        (warn if bad else info)(line)
        links_ok = links_ok and not bad
        if line.startswith("linked skill"):
            parts.append(line.split()[2] + " skill link")
    if not links_ok:
        ok = False
    if skipped or not skills_ok:
        ok = False
    from . import codex, codex_project, targets
    if on["codex"]:  # the repo's Codex file; installs only for a user with Codex on
        codex_ok = links_ok
        skips = _planned(prof, project)
        for line in codex_project.apply(prof, project, install=install, dry_run=dry_run, w=w,
                                        user_codex=targets.codex_enabled()):
            if line in skips:  # planned: said once, not a problem
                (steps.append if calm else info)(line)
                continue
            bad = line.startswith("skipped") or line == codex.PLUGINS_OLD or any(s in line for s in (
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
    from . import backup, repo_config, skill_links
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
    skips: list[str] = []
    if git_init:
        w.run(["git", "init"], "init: make this folder a git repository", absent=(git_dir,))
        w.watch(git_dir)
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
            notes.append(Todo(f"no longer needed for this repo's agents (yours to remove): {', '.join(left)}"))
    profs = [profiles.load_profile(name) for name in chosen]
    with repo_config.pending(project, agents):
        hold = frozenset({project / ".codex" / "config.toml"}) if _codex_after_installs(project, install) else frozenset()
        for prof in profs:
            planned_notes, planned_failures, planned_skips = _plan_profile(
                prof, project, w, install, chooser(False, ask, interactive and not yes, dry_run))
            skips += [s for s in planned_skips if s not in skips]
            notes += [n for n in planned_notes if not (n.startswith(skill_links.PREFIX) and n in notes)]
            failures += planned_failures
        notes += [Todo(l) for l in skill_links.report(skill_links.plain_files(project)) if l not in notes]
        _, scaffold_notes = scaffold.scaffold(project, w=w)
        if not paths.inside(project / ".gitignore", project):
            failures.append("skipped .gitignore: it points outside the repo")
            rc = 1
        scaffold.ensure_gitignore(project, w=w)
        for note in scaffold_notes:
            if note.startswith("skipped"):  # a real problem: ! and exit 1 (spec: still problems)
                failures.append(note)
                rc = 1
            else:
                notes.append(f"note: {note}")
        title = "init" + (f", profiles {', '.join(chosen)}" if chosen else "")
        plan = _show(project, title, w, failures + notes, skips)
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
    problems = failures + w.apply(bk, hold=hold)
    if w.stale:  # .loadout.json changed after the plan: no dependent step runs either
        return _report("Init", bk, [], problems[-1:])
    notes = [n for n in notes if not n.startswith("Codex plugins of profile")]
    for i, prof in enumerate(profs):
        if not _after_apply(prof, project, bk, install, i == 0, notes, problems):
            break
    from . import targets
    on = repo_config.agents(project)
    if on["claude"] and targets.claude_enabled():
        nxt = "Start Claude Code here and run /loadout:onboard"
    else:
        nxt = "Start Codex here and ask it to use the loadout:onboard skill"
    done = f"applied ({', '.join(chosen)})" if chosen else "applied"
    return _report("Init", bk, notes, problems, done=done, todos_after=[nxt]) or rc
