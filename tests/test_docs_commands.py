"""Every `loadout …` command on the pages an agent follows parses with the real CLI parser (spec Part 7)."""
import re
import shlex
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGES = [ROOT / "docs/how-to/install-with-an-agent.md", ROOT / "docs/how-to/setups.md",
         ROOT / "plugins/loadout/skills/configure/SKILL.md"]
FENCE = re.compile(r"^`{3}[^\n]*\n(.*?)^`{3}", re.S | re.M)
SPAN = re.compile(r"`(loadout [^`\n]+)`")
FILL = {"<list>": "codex", "<new|URL>": "new", "<URL>": "https://example.invalid/me.git",
        "<the mktemp path>": "/tmp/answers.json", "<the agreed groups>": "settings",
        "<claude or codex> <on or off>": "codex on", "--agents …": "--agents codex", "--to ...": "--to repo",
        "NAME": "web", "PATH": "/tmp/repo", "DIR": "/tmp/backup"}


def commands_in(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    found = [m.group(1) for m in SPAN.finditer(FENCE.sub("", text))]
    for block in FENCE.findall(text):
        found += [line.strip() for line in block.splitlines() if line.strip().startswith("loadout ")]
    return found


def _argv(command: str) -> list[str]:
    command = command.split(" </dev/null")[0].split(" #")[0]
    command = re.sub(r"\[([^\]]*)\]", r"\1", command)  # [--answers X] -> --answers X
    for key, value in FILL.items():
        command = command.replace(key, value)
    command = command.replace("…", "").replace("...", "")
    return shlex.split(command)[1:]


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_loadout_command_parses(page, fake_home):
    from loadout import commands  # noqa: F401  (registers the subcommands)
    from loadout.__main__ import build_parser
    bad = []
    for command in commands_in(page):
        argv = _argv(command)
        if len(argv) < 2 or argv[0].startswith("<"):  # a bare `loadout profile` in prose names the command
            continue
        try:
            build_parser().parse_args(argv)
        except SystemExit as exc:
            if exc.code:
                bad.append(command)
    assert not bad, "\n".join(bad)


def test_the_pages_have_commands():
    assert all(commands_in(p) for p in PAGES)
