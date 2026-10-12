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


def kit_version() -> str:
    """`loadout 0.1.0 (abc1234)`: the release from pyproject.toml and the kit's commit (left out if git cannot tell)."""
    import re
    from . import paths, runner
    text = (paths.kit_root() / "pyproject.toml").read_text(encoding="utf-8")
    release = re.search(r'^version = "([^"]+)"', text, re.M).group(1)
    head = runner.run(["git", "-C", str(paths.kit_root()), "rev-parse", "--short", "HEAD"], timeout=10)
    return f"loadout {release} ({head.stdout.strip()})" if head.ok and head.stdout.strip() else f"loadout {release}"


class _Version(argparse.Action):
    """Like action="version", but looked up only when asked for: hooks run loadout at every session start."""

    def __init__(self, option_strings, dest=argparse.SUPPRESS, default=argparse.SUPPRESS, help=None):
        super().__init__(option_strings=option_strings, dest=dest, default=default, nargs=0, help=help)

    def __call__(self, parser, namespace, values, option_string=None):
        print(kit_version())
        parser.exit()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="loadout", description="Set up and maintain a Claude Code loadout.")
    parser.add_argument("--version", action=_Version, help="show the version and the kit's commit, then exit")
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
