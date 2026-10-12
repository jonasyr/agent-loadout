"""The README's hero, link row and install routes, and the wordmark it shows."""
import importlib.util
import re
import subprocess

import pytest

from loadout import paths
from test_repo_static import _anchors  # GitHub's heading anchors, the same rules as the link check

ROOT = paths.kit_root()
ASSETS = ROOT / "docs" / "assets"
WORDMARKS = [ASSETS / "wordmark.light.svg", ASSETS / "wordmark.dark.svg"]


def test_wordmarks_are_outlines():
    for svg in WORDMARKS:
        text = svg.read_text(encoding="utf-8")
        assert "<title>loadout</title>" in text and 'role="img"' in text and "viewBox=" in text
        for needle in ("<text", "font-family", "@import", "url(", "href="):
            assert needle not in text, f"{svg.name}: {needle} (letters must be outlines, nothing loaded)"


def test_wordmark_variants_use_the_agreed_colours():
    light, dark = (s.read_text(encoding="utf-8") for s in WORDMARKS)
    assert all(c in light for c in ('fill="#7c3aed"', 'stroke="#ffffff"', 'fill="#0f172a"'))
    assert all(c in dark for c in ('fill="#a78bfa"', 'stroke="#0f1117"', 'fill="#e6e6eb"'))


def _wordmark_module():
    spec = importlib.util.spec_from_file_location("wordmark", ASSETS / "wordmark.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # imports fontTools only when it draws, so tests need no fontTools
    return module


@pytest.mark.parametrize("offered", [
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",  # fc-match falls back to any font
    "/usr/share/fonts/TTF/JetBrainsMono-Regular.ttf",  # only Regular installed: a lighter wordmark
    "/usr/share/fonts/TTF/JetBrainsMono[wght].ttf",  # the variable font draws its default instance, Regular
])
def test_font_lookup_refuses_anything_but_jetbrains_mono_bold(offered, monkeypatch):
    wordmark = _wordmark_module()
    monkeypatch.setattr(wordmark.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 0, offered, ""))
    with pytest.raises(SystemExit) as exit_:
        wordmark.font_path(["wordmark.py"])
    assert "JetBrains Mono Bold" in str(exit_.value)


def test_font_lookup_accepts_the_bold_file(monkeypatch):
    wordmark = _wordmark_module()
    bold = "/usr/share/fonts/TTF/JetBrainsMono-Bold.ttf"
    monkeypatch.setattr(wordmark.subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess(a, 0, bold, ""))
    assert wordmark.font_path(["wordmark.py"]) == bold


def test_font_lookup_without_fontconfig_says_what_to_do(monkeypatch):
    wordmark = _wordmark_module()

    def missing(*a, **kw):
        raise FileNotFoundError("fc-match")
    monkeypatch.setattr(wordmark.subprocess, "run", missing)
    with pytest.raises(SystemExit) as exit_:
        wordmark.font_path(["wordmark.py"])
    assert "pass the .ttf path" in str(exit_.value)


def test_wordmark_numbers_are_rounded():
    for svg in WORDMARKS:
        assert not re.search(r"\d\.\d{4,}", svg.read_text(encoding="utf-8")), f"{svg.name}: unrounded coordinates"


README = ROOT / "README.md"
CURL = "curl -fsSL https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.sh | bash -s -- --install"
CLONE = "git clone https://github.com/jonasyr/agent-loadout"


def _readme():
    return README.read_text(encoding="utf-8").replace("\r", "")


def _hero(text):
    m = re.search(r'\A<div align="center">\n(.*?)\n</div>\n', text, re.S)
    assert m, 'README must open with <div align="center"> … </div>'
    return m.group(1)


def test_hero_shows_the_wordmark_in_both_variants():
    hero = _hero(_readme())
    assert '<source media="(prefers-color-scheme: dark)" srcset="docs/assets/wordmark.dark.svg">' in hero
    # sized by width, so GitHub's max-width: 100% can scale it down on a phone (a fixed height would clip it)
    assert re.search(r'<img alt="loadout" src="docs/assets/wordmark\.light\.svg" width="\d+">', hero)
    assert "Claude Code, fully set up in one command." in hero


def _hero_problems(hero):
    """GitHub parses Markdown inside an HTML block only after a blank line: one block may not mix HTML and Markdown."""
    problems = [] if hero.startswith("\n") and hero.endswith("\n") else ["no blank line after <div> or before </div>"]
    for block in hero.strip("\n").split("\n\n"):
        lines = block.splitlines()
        if block.startswith(" "):
            problems.append(f"indented block renders as code: {block[:40]!r}")
        if len({line.lstrip().startswith("<") for line in lines}) > 1:
            problems.append(f"HTML and Markdown in one block (the Markdown shows as text): {block[:40]!r}")
    return problems


def test_hero_check_catches_markdown_glued_to_html():
    assert _hero_problems("\n<sub>agent-loadout</sub>\n### Claude Code, fully set up in one command.\n")
    assert _hero_problems("<picture></picture>\n")
    assert not _hero_problems("\n<sub>agent-loadout</sub>\n\n### Claude Code\n")


def test_hero_markdown_is_separated_by_blank_lines():
    hero = _hero(_readme())
    assert hero.strip("\n").split("\n\n")[0].startswith("<picture>")
    assert not _hero_problems(hero)


def test_link_row_points_to_headings():
    text = _readme()
    row = next(line for line in _hero(text).splitlines() if line.startswith("**[Quick start]"))
    targets = re.findall(r"\]\(#([^)]+)\)", row)
    assert len(targets) == 5
    missing = [t for t in targets if t not in _anchors(README)]
    assert not missing, f"link row targets without a heading: {missing}"


def test_quick_start_shows_both_install_routes_in_order():
    text = _readme()
    quick = text[text.index("## Quick start"):text.index("## What you get")]
    assert CURL in quick and CLONE in quick
    assert quick.index(CURL) < quick.index(CLONE), "the one-liner comes first"
    details = "".join(re.findall(r"<details>.*?</details>", quick, re.S))
    assert CURL not in details and CLONE not in details, "neither install route may be hidden in <details>"


def test_commands_have_no_prompt_characters():
    blocks = re.findall(r"```(?:bash|powershell)\n(.*?)```", _readme(), re.S)
    assert blocks
    for block in blocks:
        for line in block.splitlines():
            assert not line.startswith(("$ ", "> ", "PS> ")), f"copy button would copy the prompt: {line}"


def test_trust_claims_keep_their_scope():
    """Shortened trust claims must not promise more than the code does (shell files and gh setup are not backed up)."""
    text = _readme()
    trust = text[text.index("## Why you can trust it"):text.index("## Docs")]
    assert "removes or replaces" in trust, "backups cover what loadout removes or replaces, not everything it touches"
    assert "Nothing of yours" not in trust and "Your tools never change without your answer" in trust
    assert "configure set pref" in trust, "values set with configure set pref skip the secret guard"
    assert "next session runs the new code" in trust and "ask first" in trust
