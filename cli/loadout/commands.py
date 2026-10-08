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
