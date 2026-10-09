"""loadout command line."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import project
from .jsonio import InvalidJSON


def _ask(question: str) -> str:
    try:
        return input(question)
    except EOFError:
        return ""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="loadout")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="set up the current project")
    p.add_argument("profiles", nargs="*")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--no-install", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=lambda a: project.init(Path.cwd(), a.profiles, a.yes, not a.no_install, a.dry_run, _ask))

    p = sub.add_parser("profile", help="add a profile to the current project")
    p.add_argument("name")
    p.add_argument("--no-install", action="store_true")
    p.set_defaults(func=lambda a: project.add_profile(Path.cwd(), a.name, install=not a.no_install))

    for register in EXTRA_COMMANDS:
        register(sub)
    return parser


EXTRA_COMMANDS: list = []  # later modules append register(subparsers) functions here


def main(argv: list[str] | None = None) -> int:
    from . import commands  # noqa: F401  (registers the remaining subcommands)

    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except (InvalidJSON, ValueError) as exc:
        from .secrets import redact
        print(f"loadout: {redact(str(exc))}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
