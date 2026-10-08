"""Registers subcommands implemented in other modules (kept separate to avoid import cycles)."""
from .__main__ import EXTRA_COMMANDS  # noqa: F401
from pathlib import Path

from . import backup


def _register_restore(sub):
    p = sub.add_parser("restore", help="undo a loadout backup")
    p.add_argument("backup_dir")

    def run(args):
        for line in backup.restore(Path(args.backup_dir).expanduser()):
            print(line)
        return 0

    p.set_defaults(func=run)


EXTRA_COMMANDS.append(_register_restore)


def _register_adopt(sub):
    from . import adopt
    from .__main__ import _ask

    p = sub.add_parser("adopt", help="review and migrate the existing Claude Code setup")
    p.add_argument("--apply", action="store_true", help="choose and apply changes (default: dry run)")
    p.add_argument("--groups", help="non-interactive: comma-separated groups to apply, e.g. remove,migrate")
    p.add_argument("--skip", default="", help="comma-separated item names to leave alone")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--no-versions", action="store_true", help="skip network version checks")

    def run(a):
        groups = {g.strip() for g in a.groups.split(",") if g.strip()} if a.groups else None
        skip = {s.strip() for s in a.skip.split(",") if s.strip()}
        return adopt.run(a.apply, groups, skip, a.yes, _ask, with_versions=not a.no_versions)

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

    p = sub.add_parser("hook-session-start", help=argparse_hidden())

    def hook(a):
        try:
            out = maintenance.session_start(time.time())
        except Exception:
            return 0  # a hook must never break a session
        if out:
            print(out)
        return 0

    p.set_defaults(func=hook)

    p = sub.add_parser("maintenance", help=argparse_hidden())

    def maint(a):
        try:
            maintenance.maintain(time.time())
        except Exception:
            pass
        return 0

    p.set_defaults(func=maint)

    p = sub.add_parser("update", help="update outdated tool binaries")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=lambda a: maintenance.update(a.yes, _ask))


def argparse_hidden():
    import argparse
    return argparse.SUPPRESS


EXTRA_COMMANDS.append(_register_maintenance)


def _register_bootstrap(sub):
    from . import bootstrap
    from .__main__ import _ask

    p = sub.add_parser("bootstrap", help="set up (or repair) this machine")
    p.add_argument("--install", action="store_true", help="install missing tool binaries")
    p.add_argument("--yes", action="store_true", help="accept defaults (adopt applies remove/migrate/scope-down/update)")
    p.add_argument("--no-plugins", action="store_true")
    p.add_argument("--no-adopt", action="store_true")
    p.set_defaults(func=lambda a: bootstrap.bootstrap(a.install, a.yes, not a.no_plugins, not a.no_adopt, _ask))


EXTRA_COMMANDS.append(_register_bootstrap)


def _register_configure(sub):
    from . import configure
    from .__main__ import _ask

    p = sub.add_parser("configure", help="choose preferences and global add-ons (personal layer)")
    p.add_argument("action", nargs="?", choices=["show", "set"])
    p.add_argument("kind", nargs="?", choices=["plugin", "mcp", "pref"])
    p.add_argument("name", nargs="?")
    p.add_argument("value", nargs="?")
    p.add_argument("--first-run", action="store_true")

    def run(a):
        if a.action is None:
            return configure.wizard(_ask, a.first_run)
        if a.action == "show":
            print(configure.show())
            return 0
        if not (a.kind and a.name and a.value):
            raise ValueError("usage: loadout configure set plugin|mcp|pref <name> <value>")
        if a.kind == "plugin":
            configure.set_plugin(a.name, a.value == "on")
        elif a.kind == "mcp":
            for warning in configure.set_mcp(a.name, a.value == "on"):
                print(f"note: {warning}")
        else:
            configure.set_pref(a.name, a.value)
        configure.apply_all(lambda q: "n")
        return 0

    p.set_defaults(func=run)


EXTRA_COMMANDS.append(_register_configure)
