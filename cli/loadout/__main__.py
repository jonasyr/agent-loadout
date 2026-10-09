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
    parser = argparse.ArgumentParser(prog="loadout", description="Set up and maintain a Claude Code loadout.")
    # metavar hides internal subcommands (registered without help=) from the usage line
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    p = sub.add_parser("init", help="set up the current project",
                       description="Prepare the current project: AGENTS.md, CLAUDE.md, docs/, .gitignore entries, profiles. Never overwrites files.")
    p.add_argument("profiles", nargs="*", help="profiles to apply (default: suggest from the project and ask)")
    p.add_argument("--yes", action="store_true", help="no questions: git init if needed, apply the suggested profiles")
    p.add_argument("--no-install", action="store_true", help="do not install the profiles' plugins or run their commands")
    p.add_argument("--dry-run", action="store_true", help="show what would change, change nothing")
    p.set_defaults(func=lambda a: project.init(Path.cwd(), a.profiles, a.yes, not a.no_install, a.dry_run, _ask))

    p = sub.add_parser("profile", help="add a profile to the current project")
    p.add_argument("name", help="profile name, e.g. thesis, web, db, sonar, android (or one in <personal>/profiles)")
    p.add_argument("--no-install", action="store_true", help="do not install the profile's plugins or run its commands")
    p.set_defaults(func=lambda a: project.add_profile(Path.cwd(), a.name, install=not a.no_install))

    for register in EXTRA_COMMANDS:
        register(sub)
    return parser


EXTRA_COMMANDS: list = []  # later modules append register(subparsers) functions here


def main(argv: list[str] | None = None) -> int:
    from . import commands  # noqa: F401  (registers the remaining subcommands)

    for stream in (sys.stdout, sys.stderr):  # legacy Windows code pages must not crash on non-ASCII output
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except (InvalidJSON, ValueError) as exc:
        from .secrets import redact
        print(f"loadout: {redact(str(exc))}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
