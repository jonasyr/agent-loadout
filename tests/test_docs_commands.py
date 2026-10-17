"""Every `loadout …` command on the pages an agent follows parses with the real CLI parser (spec Part 7)."""
import re
import shlex
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGES = [ROOT / "docs/how-to/install-with-an-agent.md", ROOT / "docs/how-to/setups.md",
         ROOT / "plugins/loadout/skills/configure/SKILL.md", ROOT / "plugins/loadout/skills/onboard/SKILL.md"]
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


def _strict(parser):
    """No abbreviations: a flag the docs spell short (or a renamed one) must not parse as another."""
    parser.allow_abbrev = False
    for action in parser._actions:
        for sub in (getattr(action, "choices", None) or {}).values() if hasattr(action, "add_parser") else ():
            _strict(sub)
    return parser


def _parses(command: str) -> bool:
    from loadout import commands  # noqa: F401  (registers the subcommands)
    from loadout.__main__ import build_parser
    parser = _strict(build_parser())
    argv = _argv(command)
    if len(argv) == 1:  # a bare `loadout profile` in prose names the command: it must exist
        sub = next(a for a in parser._actions if hasattr(a, "add_parser"))
        return argv[0] in sub.choices
    try:
        parser.parse_args(argv)
    except SystemExit as exc:
        return not exc.code
    return True


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.name)
def test_every_loadout_command_parses(page, fake_home):
    bad = [c for c in commands_in(page) if _argv(c) and not _argv(c)[0].startswith("<") and not _parses(c)]
    assert not bad, "\n".join(bad)


def test_an_abbreviated_flag_or_unknown_command_does_not_pass(fake_home, capsys):
    assert _parses("loadout bootstrap --install --vscode-wsl")
    assert not _parses("loadout bootstrap --install --vscode")
    assert not _parses("loadout nosuchcommand")


def test_the_pages_have_commands():
    assert all(commands_in(p) for p in PAGES)


WALK = "## Codex only on Windows with VS Code"
STEPS = ["WSL 2", "bootstrap", "codex login", "/hooks", "loadout init --agents codex", "loadout check"]


def _walkthrough(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    assert WALK in text, path.name
    section = text.split(WALK, 1)[1].split("\n## ", 1)[0]
    return [line for line in section.splitlines() if re.match(r"\d+\. ", line)]


def test_walkthrough_is_the_same_six_steps_in_both_pages():
    pages = [ROOT / "docs/how-to/setups.md", ROOT / "docs/how-to/install-with-an-agent.md"]
    for page in pages:
        steps = _walkthrough(page)
        assert len(steps) == len(STEPS), (page.name, steps)
        for line, key in zip(steps, STEPS):
            assert key in line, (page.name, key, line)


def test_trust_is_accepted_in_the_wsl_terminal_not_the_extension():
    for page in (ROOT / "docs/how-to/setups.md", ROOT / "docs/how-to/install-with-an-agent.md"):
        step = _walkthrough(page)[4]
        assert "trust question" in step and "WSL terminal" in step, (page.name, step)


def test_agent_walkthrough_keeps_the_side_answer_and_section_4():
    text = (ROOT / "docs/how-to/install-with-an-agent.md").read_text(encoding="utf-8")
    section = text.split(WALK, 1)[1]
    assert "--codex-side windows" in section  # a Windows answer is not overridden
    assert "instead of sections 4" not in section  # the --install and --yes warnings still apply


def test_init_without_a_terminal_names_the_repo_agents_first():
    text = (ROOT / "docs/reference/cli.md").read_text(encoding="utf-8")
    assert "Without a terminal it takes your agents," not in text


def test_walkthrough_does_not_overstate_openais_guidance():
    # OpenAI offers WSL2 for Linux tooling, a workflow already in WSL2, or a Windows sandbox that falls short
    text = (ROOT / "docs/how-to/setups.md").read_text(encoding="utf-8")
    assert "OpenAI's recommended" not in text
