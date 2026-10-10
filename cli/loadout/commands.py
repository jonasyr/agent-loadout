"""Registers subcommands implemented in other modules (kept separate to avoid import cycles)."""
from .__main__ import EXTRA_COMMANDS  # noqa: F401
from pathlib import Path

from . import backup


def _register_restore(sub):
    p = sub.add_parser("restore", help="undo a loadout backup (--list shows them)")
    p.add_argument("backup_dir", nargs="?", help="backup directory printed by bootstrap/adopt, e.g. ~/.claude/backups/loadout-<timestamp>")
    p.add_argument("--list", action="store_true", help="list backups, newest first")
    p.add_argument("--force", action="store_true", help="replay a backup that was already restored")

    def run(args):
        if args.list or not args.backup_dir:
            rows = backup.list_backups()
            print("\n".join(rows) if rows else "no backups yet")
            if rows:
                print("\nundo one: loadout restore <path from the first column>")
            if not args.list:
                print("usage: loadout restore DIR")
            return 0
        lines, ok, pre = backup.restore(Path(args.backup_dir).expanduser(), force=args.force)
        for line in lines:
            print(line)
        if pre is not None:
            print(f"\nthe state this restore replaced is in {pre}  (undo this restore: loadout restore {pre})")
        return 0 if ok else 1

    p.set_defaults(func=run)


EXTRA_COMMANDS.append(_register_restore)


def _register_adopt(sub):
    from . import adopt
    from .__main__ import _ask

    p = sub.add_parser("adopt", help="review and migrate the existing Claude Code setup")
    p.add_argument("--apply", action="store_true", help="choose and apply changes (default: dry run)")
    p.add_argument("--groups", help="apply exactly these groups, e.g. remove,migrate (update/install run each command after confirmation unless --yes)")
    p.add_argument("--skip", default="", help="comma-separated item names to leave alone")
    p.add_argument("--yes", action="store_true", help="no questions: apply --groups, or remove,migrate,scope-down, and move secrets; your own tools stay as they are")
    p.add_argument("--own", metavar="NAME=CHOICE,...",
                   help="decide for your own tools: global, project:<profile>, leave or remove "
                        "(e.g. foo@bar=global,my-db=project:db); others stay as they are")
    p.add_argument("--no-versions", action="store_true", help="skip network version checks")

    def run(a):
        groups = {g.strip() for g in a.groups.split(",") if g.strip()} if a.groups else None
        skip = {s.strip() for s in a.skip.split(",") if s.strip()}
        return adopt.run(a.apply, groups, skip, a.yes, _ask, with_versions=not a.no_versions, own_spec=a.own)

    p.set_defaults(func=run)


EXTRA_COMMANDS.append(_register_adopt)


def _register_check(sub):
    from . import check, settings_merge

    p = sub.add_parser("check", help="verify this machine's loadout setup")

    def run_check(a):
        text, code = check.format_results(check.run_checks())
        print(text)
        return code

    p.set_defaults(func=run_check)

    p = sub.add_parser("apply-settings", help="merge kit + personal settings into ~/.claude/settings.json")

    def run_apply(a):
        before, after = settings_merge.apply_settings()
        print("settings updated" if before != after else "settings already up to date")
        return 0

    p.set_defaults(func=run_apply)


EXTRA_COMMANDS.append(_register_check)


def _register_maintenance(sub):
    import time

    from . import maintenance
    from .__main__ import _ask

    p = sub.add_parser("hook-session-start")  # internal: no help=, so it stays out of --help

    def hook(a):
        try:
            out = maintenance.session_start(time.time())
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

    p = sub.add_parser("update", help="update outdated tool binaries")
    p.add_argument("--yes", action="store_true", help="run every update command without asking (each is still printed)")
    p.set_defaults(func=lambda a: maintenance.update(a.yes, _ask))


EXTRA_COMMANDS.append(_register_maintenance)


def _register_bootstrap(sub):
    from . import bootstrap
    from .__main__ import _ask

    p = sub.add_parser("bootstrap", help="set up (or repair) this machine")
    p.add_argument("--install", action="store_true", help="install missing tool binaries")
    p.add_argument("--yes", action="store_true", help="accept defaults without asking (adopt applies remove/migrate/scope-down; never binary updates)")
    p.add_argument("--no-plugins", action="store_true", help="skip adding marketplaces and installing plugins (offline/CI)")
    p.add_argument("--no-adopt", action="store_true", help="skip reviewing the existing setup")
    p.set_defaults(func=lambda a: bootstrap.bootstrap(a.install, a.yes, not a.no_plugins, not a.no_adopt, _ask))


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
                              "  loadout configure set pref effortLevel '\"high\"'")
    p.add_argument("action", nargs="?", choices=["show", "set", "prefs", "own"],
                   help="show the current state, set one value, or answer the working-preference questions")
    p.add_argument("kind", nargs="?", choices=["plugin", "mcp", "pref-choice", "pref", "own"], help="what to set")
    p.add_argument("name", nargs="?", help="plugin id, MCP add-on id or server name, preference id, or settings key (ids: configure show)")
    p.add_argument("value", nargs="?", help="on|off for plugin/mcp; an option for pref-choice; a JSON value for pref; global|project:<profile>|leave|remove for own")
    p.add_argument("--all", action="store_true", help="with own: also list the tools you left on this machine")
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
        if not (a.kind and a.name and a.value):
            raise ValueError("usage: loadout configure set plugin|mcp|pref-choice|pref|own <name> <value>")
        if a.kind == "own":
            return configure.set_own(a.name, a.value)
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
