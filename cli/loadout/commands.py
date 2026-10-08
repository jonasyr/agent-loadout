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
