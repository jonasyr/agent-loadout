"""Registers subcommands implemented in other modules (kept separate to avoid import cycles)."""
from pathlib import Path

from . import backup

EXTRA_COMMANDS: list = []  # register(subparsers) functions; __main__.build_parser runs them (one registry, also under `python -m`)


def _register_restore(sub):
    p = sub.add_parser("restore", help="undo a loadout backup (without a path: pick one of the recent backups)")
    p.add_argument("backup_dir", nargs="?", help="backup directory a loadout command printed, e.g. ~/.local/state/loadout/backups/loadout-<timestamp>")
    p.add_argument("--list", action="store_true", help="list backups, newest first, with their paths (for agents and scripts)")
    p.add_argument("--last", action="store_true", help="restore the newest backup of any kind (with --repo: the repo's newest); asks in a terminal")
    p.add_argument("--repo", metavar="PATH", help="only the backups made for this repo")
    p.add_argument("--show", action="store_true", help="print what the backup at BACKUP_DIR puts back; change nothing")
    p.add_argument("--force", action="store_true", help="replay a backup that was already restored")

    def run(args):
        from . import restore_cmd, ui
        from .__main__ import _ask
        return restore_cmd.run(args.backup_dir, args.list, args.last, args.repo, args.force, _ask, ui.is_interactive(),
                               show=args.show)

    p.set_defaults(func=run)


EXTRA_COMMANDS.append(_register_restore)


def _register_adopt(sub):
    from . import adopt, out
    from .__main__ import _ask

    p = sub.add_parser("adopt", help="review and migrate the existing Claude Code setup")
    p.add_argument("--apply", action="store_true", help="choose and apply changes (default: dry run)")
    p.add_argument("--groups", help="apply exactly these groups, e.g. remove,migrate (update/install run each command after confirmation unless --yes); `secrets` also moves plaintext secrets to secrets.env; `own` is refused, use --own")
    p.add_argument("--skip", default="", help="comma-separated item names to skip in this run (nothing is remembered)")
    p.add_argument("--yes", action="store_true", help="no questions: apply --groups, or remove,migrate,scope-down, and move secrets (with --groups only if it names `secrets`); your own tools stay as they are")
    p.add_argument("--own", metavar="NAME=CHOICE,...",
                   help="Example: my-db=project:mydb,foo@bar=global. Decide for your own tools. "
                        "Choices: global, project:<profile>, leave, remove; others stay as they are. "
                        "A hook is named Event:matcher (Stop: has no matcher); add #n when several hooks "
                        "share a name (names: loadout configure own)")
    p.add_argument("--no-versions", action="store_true", help="skip network version checks")
    p.add_argument("--verbose", action="store_true", help="full detail: commands, long reasons, the items that stay")

    def run(a):
        if a.verbose:
            out.VERBOSE = True
        groups = {g.strip() for g in a.groups.split(",") if g.strip()} if a.groups else None
        skip = {s.strip() for s in a.skip.split(",") if s.strip()}
        return adopt.run(a.apply, groups, skip, a.yes, _ask, with_versions=not a.no_versions, own_spec=a.own)

    p.set_defaults(func=run)


EXTRA_COMMANDS.append(_register_adopt)


def _register_check(sub):
    from . import check, out, settings_merge

    p = sub.add_parser("check", help="verify this machine's loadout setup")
    p.add_argument("--verbose", action="store_true", help="list every check, not only the problems")

    def run_check(a):
        if a.verbose:
            out.VERBOSE = True
        text, code = (check.format_results if out.VERBOSE else check.format_summary)(check.run_checks())
        print(text)
        from . import steps, targets
        steps.print_pending(targets.claude_enabled(), targets.codex_enabled())
        return code

    p.set_defaults(func=run_check)

    p = sub.add_parser("apply-settings", help="merge kit + personal settings into ~/.claude/settings.json")

    def run_apply(a):
        from . import targets
        if not targets.claude_enabled():  # a turned-off agent's files stay untouched
            print("Claude Code is turned off (loadout configure set target claude on); nothing to merge")
            return 0
        before, after = settings_merge.apply_settings()
        print("settings updated" if before != after else "settings already up to date")
        return 0

    p.set_defaults(func=run_apply)


EXTRA_COMMANDS.append(_register_check)


def _hook_source(agent) -> str | None:
    """Claude Code's `source` (startup, resume, clear, compact) from the hook's stdin JSON; None when stdin is a
    terminal, empty, not JSON or has none (then the steps stay)."""
    import json
    import sys
    if agent != "claude":
        return None
    try:
        if sys.stdin is None or sys.stdin.isatty():
            return None
        data = json.loads(sys.stdin.read() or "null")
    except Exception:
        return None
    source = data.get("source") if isinstance(data, dict) else None
    return source if isinstance(source, str) else None


def _register_maintenance(sub):
    import time

    from . import maintenance, out
    from .__main__ import _ask

    p = sub.add_parser("hook-session-start")  # internal: no help=, so it stays out of --help
    p.add_argument("--agent", choices=("claude", "codex"), default=None)  # an older plugin copy passes none

    def hook(a):
        try:
            out = maintenance.session_start(time.time(), a.agent, _hook_source(a.agent))
        except Exception:
            return 0  # a hook must never break a session
        if out:
            print(out)
        return 0

    p.set_defaults(func=hook)

    p = sub.add_parser("maintenance")  # internal

    def maint(a):
        try:
            maintenance.maintain(time.time())
        except Exception:
            pass
        return 0

    p.set_defaults(func=maint)

    p = sub.add_parser("update", help="bring this machine current: pull, re-apply the setup, refresh plugins, "
                                      "update tools")
    p.add_argument("--yes", action="store_true", help="apply the whole plan without asking (it is still printed)")
    p.add_argument("--verbose", action="store_true", help="full detail: every command and line")

    def update_cmd(a):
        if a.verbose:
            out.VERBOSE = True
        flags = (["--yes"] if a.yes else []) + (["--verbose"] if a.verbose else [])
        return maintenance.update(a.yes, _ask, argv=flags)

    p.set_defaults(func=update_cmd)


EXTRA_COMMANDS.append(_register_maintenance)


def _register_bootstrap(sub):
    from . import bootstrap, out
    from .__main__ import _ask

    p = sub.add_parser("bootstrap", help="set up (or repair) this machine")
    p.add_argument("--install", action="store_true", help="install missing tool binaries")
    p.add_argument("--yes", action="store_true", help="accept defaults without asking (adopt applies remove/migrate/scope-down; never binary updates)")
    p.add_argument("--no-plugins", action="store_true", help="skip adding marketplaces and installing plugins (offline/CI)")
    p.add_argument("--no-adopt", action="store_true", help="skip reviewing the existing setup")
    p.add_argument("--verbose", action="store_true", help="print every detail of every step")
    p.add_argument("--agents", help="claude, codex or claude,codex; stored in your personal layer (default: the personal layer's stored choice, else ask; Claude Code without a terminal)")
    p.add_argument("--personal", metavar="new|URL",
                   help="the personal layer without asking: new (a starter) or the git URL to clone")
    p.add_argument("--answers", metavar="FILE",
                   help="JSON with the starter layer's answers (about, preferences; docs/how-to/install-with-an-agent.md)")
    p.add_argument("--codex-side", choices=("wsl", "windows"),
                   help="in WSL: set up Codex here (wsl) or leave it to bootstrap.ps1 on Windows (windows)")
    p.add_argument("--vscode-wsl", action="store_true",
                   help="in WSL with Codex: switch VS Code's Codex extension to WSL without asking (backup first)")
    p.add_argument("--vscode-path", action="store_true",
                   help="in WSL with VS Code's Remote-WSL server: put loadout's tool folders on PATH in "
                        "~/.vscode-server/server-env-setup without asking (backup first)")
    p.add_argument("--without-codex-cli", action="store_true",
                   help="with VS Code's Codex extension: skip the optional Codex CLI (loadout sets Codex up for the "
                        "extension; the CLI is optional, VS Code's Codex extension runs its own codex)")

    def run(a):
        if a.verbose:
            out.VERBOSE = True
        if a.vscode_wsl:
            from . import wsl
            if wsl.detect() is None:
                out.status("VS Code", "--vscode-wsl applies to loadout in WSL only; nothing changed", "warn")
        return bootstrap.bootstrap(a.install, a.yes, not a.no_plugins, not a.no_adopt, _ask, agents=a.agents, codex_side=a.codex_side,
                                   personal=a.personal, answers=a.answers, vscode_wsl=a.vscode_wsl,
                                   codex_cli=not a.without_codex_cli, vscode_path=a.vscode_path)

    p.set_defaults(func=run)


EXTRA_COMMANDS.append(_register_bootstrap)


def _register_configure(sub):
    from . import configure
    from .__main__ import _ask

    import argparse

    p = sub.add_parser("configure", help="choose preferences and global add-ons (personal layer)",
                       formatter_class=argparse.RawDescriptionHelpFormatter,
                       description="Without arguments: an interactive wizard. Choices go into your personal layer.",
                       epilog="examples:\n"
                              "  loadout configure show\n"
                              "  loadout configure prefs\n"
                              "  loadout configure set pref-choice effort_level high\n"
                              "  loadout configure set plugin hookify@claude-plugins-official on\n"
                              "  loadout configure set mcp dbhub on\n"
                              "  loadout configure own\n"
                              "  loadout configure set own foo@bar global\n"
                              "  loadout configure new skill notes --description 'Use when ...'\n"
                              "  loadout configure set pref effortLevel '\"high\"'")
    p.add_argument("action", nargs="?", choices=["show", "set", "prefs", "own", "new"],
                   help="show the current state, set one value, answer the working-preference questions, list your own tools (own), or create a skill of your own (new skill)")
    p.add_argument("kind", nargs="?", choices=["plugin", "mcp", "pref-choice", "pref", "own", "target", "skill"], help="what to set")
    p.add_argument("name", nargs="?", help="plugin id, MCP add-on id or server name, preference id, or settings key (ids: configure show), "
                                      "or one of your own tools (names: configure own)")
    p.add_argument("value", nargs="?", help="on|off for plugin/mcp; an option for pref-choice; a JSON value for pref; global|project:<profile>|leave|remove for own")
    p.add_argument("--all", action="store_true", help="with own: also list the tools you left on this machine")
    p.add_argument("--to", default="global", help="with new skill: global (default), project:<profile> or repo")
    p.add_argument("--description", help="with new skill: one line saying when an agent should use the skill")
    p.add_argument("--yes", action="store_true", help="with new skill --to repo: create it without asking (needed without a terminal)")
    p.add_argument("--first-run", action="store_true", help="also ask the 'about you' questions again (keeps your me.md unless you agree)")

    def run(a):
        if a.action is None:
            return configure.wizard(_ask, a.first_run)
        if a.action == "show":
            print(configure.show())
            return 0
        if a.action == "prefs":
            return configure.prefs(_ask)
        if a.action == "own":
            print("\n".join(configure.own_lines(a.all)))
            return 0
        if a.action == "new":
            if a.kind != "skill" or not a.name or a.value is not None:  # a stray value: --description forgotten?
                raise ValueError("usage: loadout configure new skill NAME [--to global|project:<profile>|repo] "
                                 "[--description TEXT]")
            import sys
            from . import new_skill, targets
            from .backup import Backup
            from .secrets import redact
            bk = Backup(description=f"configure new skill {redact(a.name)}")
            approve = None
            if a.to == "repo":
                from . import project, ui
                ask_yes = project.approver(a.yes, _ask, ui.is_interactive())

                def approve(plan):
                    print("\n".join(plan))
                    return ask_yes(plan)
            try:
                lines = new_skill.create(a.name, a.to, a.description, bk=bk, approve=approve)
            except new_skill.BadInput as exc:
                print(f"loadout: {redact(str(exc))}", file=sys.stderr)
                return 2
            except new_skill.Refused as exc:
                print(f"loadout: {redact(str(exc))}", file=sys.stderr)
                return 1
            print("\n".join(lines))
            if not bk.empty:
                print(f"backup: {bk.root}  (undo: loadout restore {bk.root})")
            from .project import MANAGE_OFF
            if lines == ["nothing changed"] or lines[-1:] == [MANAGE_OFF]:
                return 0
            print(f"Fill in SKILL.md. {targets.restart_hint()}")
            if a.to != "repo":
                configure.offer_commit(_ask)
            return 1 if any(": not linked" in line for line in lines) else 0  # an agent that is on cannot see it
        if not (a.kind and a.name and a.value) or a.kind == "skill":  # skill is for `new skill` only
            raise ValueError("usage: loadout configure set plugin|mcp|pref-choice|pref|own|target <name> <value>"
                             + ("; to create a skill: loadout configure new skill NAME" if a.kind == "skill" else ""))
        if a.kind == "own":
            return configure.set_own(a.name, a.value)
        if a.kind == "target":
            from . import codex, out, targets
            on = configure.parse_switch(a.value, "target")
            print(targets.set_target(a.name, on))  # ValueError (unknown agent, last one off) -> exit 1
            if on and a.name == "claude":
                from . import runner
                from .vscode import use_bundled_claude  # VS Code's Claude Code extension ships a claude: that counts
                if not runner.have("claude") and use_bundled_claude(on=True) is None:  # Codex only so far: install first
                    configure.offer_commit(_ask)
                    print("Claude Code is not installed yet: run `loadout bootstrap --install` to install and set it up")
                    return 0
                from . import link
                from .backup import Backup
                link.link_all(Backup(description="configure: link rules and skills for Claude Code"))
                configure.apply_all(_ask)  # includes the commit offer
                return 0
            configure.offer_commit(_ask)  # targets.json lives in the personal layer; uncommitted it pauses the sync
            if on and a.name == "codex":  # set Codex up now, not at the next bootstrap
                problem = codex.unavailable()
                if problem:
                    print(f"note: {problem}; Codex is set up once that is fixed (loadout bootstrap)")
                    return 1
                from .backup import Backup
                bk = Backup(description="configure: set up Codex")
                print("setting up Codex…")
                codex_lines = codex.apply_all(bk, say=out.progress)
                out.end_progress()
                for line in codex_lines:
                    print(line)
                for step in codex.open_steps():
                    print(f"Still to do: {step}")
                if not bk.empty:
                    print(f"backup: {bk.root}  (undo: loadout restore {bk.root})")
            return 0
        if a.kind == "plugin":
            configure.set_plugin(a.name, configure.parse_switch(a.value, "plugin"))
        elif a.kind == "mcp":
            for warning in configure.set_mcp(a.name, configure.parse_switch(a.value, "mcp")):
                print(f"note: {warning}")
        elif a.kind == "pref-choice":
            from . import preferences, ui
            lines = configure.set_pref_choice(a.name, a.value, _ask, ui.is_interactive())
            for line in lines:
                print(line)
            if any(preferences.NOT_EFFECTIVE in line for line in lines):
                configure.apply_all(lambda q: "n")
                return 1
        else:
            configure.set_pref(a.name, a.value)
        configure.apply_all(lambda q: "n")
        return 0

    p.set_defaults(func=run)


EXTRA_COMMANDS.append(_register_configure)


def _register_advisor(sub):
    from . import advisor

    p = sub.add_parser("advisor-mark")  # internal (called by /loadout:execution-advisor): no help=
    p.add_argument("plan", help="path of the implementation plan that was evaluated")

    def run(a):
        print(advisor.mark(a.plan))
        return 0

    p.set_defaults(func=run)


EXTRA_COMMANDS.append(_register_advisor)


def _register_usage(sub):
    import argparse

    def moment(text):
        from . import usage
        try:
            return usage.parse_moment(text)
        except ValueError as e:
            raise argparse.ArgumentTypeError(str(e))

    p = sub.add_parser("usage", help="how often the agents used each tool family, before and after a change "
                                     "(local transcripts, counts only)")
    p.add_argument("--days", type=int, default=14, help="window length in days (default 14)")
    when = p.add_mutually_exclusive_group()
    when.add_argument("--around", type=moment, metavar="MOMENT",
                      help="compare the days before MOMENT with the days after it (YYYY-MM-DD or YYYY-MM-DDTHH:MM)")
    when.add_argument("--since", type=moment, metavar="MOMENT", help="only the window from MOMENT until now")
    def positive(text):
        import argparse
        n = int(text)
        if n < 1:
            raise argparse.ArgumentTypeError("must be 1 or more")
        return n

    p.add_argument("--min-calls", type=positive, default=None, help="sessions with fewer tool calls are left out (default 5)")
    p.add_argument("--follow-within", type=positive, default=None,
                   help="tool calls after a Serena reminder that count as following it (default 5)")
    p.add_argument("--min-sessions", type=positive, default=None,
                   help="fewest sessions on each side before an arrow is shown (default 20)")
    p.add_argument("--sessions", action="store_true", help="one line per session (ids and counts only)")
    p.add_argument("--legacy", action="store_true", help="the old single-window counts; only --days applies")
    p.add_argument("--json", action="store_true", help="print the counts as JSON")

    def run(a):
        import json as _json
        import sys as _sys
        import time as _time
        from . import usage
        thresholds = (a.min_calls, a.follow_within, a.min_sessions)  # None: not given (defaults below)
        if a.legacy:
            if a.around is not None or a.since is not None or a.sessions or any(t is not None for t in thresholds):
                print("loadout: --legacy takes only --days (not --around, --since, --sessions or the thresholds)",
                      file=_sys.stderr)
                return 2
            report = usage.collect(max(1, a.days))
            if "claude" not in report and "codex" not in report:
                print("loadout: no session history found for the agents that are on", file=_sys.stderr)
                return 1
            print(_json.dumps(report, indent=2) if a.json else usage.render(report))
            return 0
        a.min_calls = 5 if a.min_calls is None else a.min_calls
        a.follow_within = 5 if a.follow_within is None else a.follow_within
        a.min_sessions = 20 if a.min_sessions is None else a.min_sessions
        if a.sessions and a.json:
            print("loadout: --sessions prints text lines; leave out --json", file=_sys.stderr)
            return 2
        now = _time.time()
        start, end, before = usage.plan_windows(max(1, a.days), a.around, a.since, now)
        kept: list = []
        rep = usage.report(start, end, before, min_calls=a.min_calls, follow_within=a.follow_within,
                           min_sessions=a.min_sessions, now=now, keep=kept)
        if "claude" not in rep and "codex" not in rep:
            print("loadout: no session history found for the agents that are on", file=_sys.stderr)
            return 1
        if a.sessions:
            print(usage.render_sessions(kept, rep["windows"], a.min_calls))
        else:
            print(_json.dumps(rep, indent=2) if a.json else usage.render_report(rep))
        return 0

    p.set_defaults(func=run)


EXTRA_COMMANDS.append(_register_usage)


def _register_kit_path(sub):
    p = sub.add_parser("kit-path", help="print the kit's folder (its rules/ and docs/ are read by the doc skills)")

    def run(a):
        from . import paths
        print(paths.kit_root().as_posix())  # forward slashes work in Git Bash and PowerShell
        return 0

    p.set_defaults(func=run)


EXTRA_COMMANDS.append(_register_kit_path)


def _register_explain(sub) -> None:
    p = sub.add_parser("explain", help="which entries in a repo file (or Codex's config.toml, hooks.json) loadout wrote, and whether each is unchanged")
    p.add_argument("file", help="a file in the current repo, e.g. .claude/settings.json, or ~/.codex/config.toml "
                                "or ~/.codex/hooks.json")

    def run(a):
        from .explain import explain
        return explain(a.file)
    p.set_defaults(func=run)


EXTRA_COMMANDS.append(_register_explain)
