# README Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The README opens with a centred hero (wordmark, tagline, badges, link row), shows the demo, then a numbered Quick start with both install routes, followed by shorter "What you get", toolset, trust and docs sections.

**Architecture:** A maintainer script (`docs/assets/wordmark.py`, fontTools) renders a light and a dark wordmark SVG with the letters as outlines. `README.md` is rewritten to the agreed structure. `tests/test_readme.py` pins the hero, the link row, both install routes and the wordmark files; the existing link, demo and diagram tests keep guarding the rest.

**Tech Stack:** Markdown with GitHub's allowed HTML, Python 3 with fontTools (maintainer tool only), pytest, playwright-cli for checks.

**Spec:** `docs/superpowers/specs/2026-10-12-readme-polish-design.md`

## Global Constraints

- Headline: **Claude Code, fully set up in one command.** Second line: *The best plugins, MCP servers and rules, preconfigured to work together, on every machine, and kept up to date.*
- Link row: Quick start · What you get · Toolset · Trust · Docs.
- The curl one-liner line stays byte-identical: `curl -fsSL https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.sh | bash -s -- --install` (`tests/test_demo.py` compares the demo tape with it).
- Both install routes are visible, one-liner first ("Quickest: one command"), clone second ("Or clone it yourself"); neither hidden in `<details>`.
- Wordmark: light tile `#7c3aed`, chevron `#ffffff`, text `#0f172a`; dark tile `#a78bfa`, chevron `#0f1117`, text `#e6e6eb`; JetBrains Mono Bold as outlines; chevron drawn as a path.
- Only GitHub-allowed HTML (no CSS, no scripts); commands without `$` prompts; at most two GitHub alerts; no emojis.
- Facts are not changed; details stay in `docs/` and are linked.
- `cli/loadout/` stays standard library only (the wordmark script is outside it). Tests: stdlib + pytest.
- Conventional Commits; no `Co-Authored-By` or AI attribution; author `Jonas Weirauch <jonas.weirauch@gmx.de>`. Push and PR need the user's OK.

## Review Focus

1. **The link row's anchors drift from the headings** (a heading renamed later): GitHub silently scrolls nowhere. Pinned by `test_link_row_points_to_headings` (Task 2), which uses the README's own headings.
2. **Markdown inside the centred `<div>` renders as literal text** when a blank line is missing (GitHub only parses Markdown in an HTML block after a blank line). Pinned by `test_hero_markdown_is_separated_by_blank_lines` (Task 2).
3. **A wordmark SVG that still contains `<text>` or references a font** renders in a fallback font in some viewers. Pinned by `test_wordmarks_are_outlines` (Task 1).
4. **The wordmark script is run on a machine without JetBrains Mono** and silently uses another font via `fc-match`. Pinned by `test_font_lookup_refuses_other_fonts` (Task 1).
5. **The one-liner is edited "for readability"** and the demo no longer matches. Already pinned by `tests/test_demo.py::test_tape_types_the_readme_one_liner`; Task 2 runs it.

---

### Task 1: The wordmark

**Files:**
- Create: `docs/assets/wordmark.py`, `docs/assets/wordmark.light.svg`, `docs/assets/wordmark.dark.svg` (generated)
- Create: `tests/test_readme.py` (wordmark tests; Task 2 appends README tests)

**Interfaces:**
- Produces: `docs/assets/wordmark.light.svg`, `docs/assets/wordmark.dark.svg` (viewBox `0 0 358.8 72`, `role="img"`, `<title>loadout</title>`); `wordmark.font_path(argv: list[str]) -> str` (raises `SystemExit` when the resolved font is not JetBrains Mono).

- [ ] **Step 1: Write the failing tests**

`tests/test_readme.py`:

```python
"""The README's hero, link row and install routes, and the wordmark it shows."""
import re
import subprocess
import sys

import pytest

from loadout import paths

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


@pytest.mark.skipif(sys.platform != "linux", reason="uses fc-match from fontconfig")
def test_font_lookup_refuses_other_fonts(tmp_path):
    """fc-match falls back to any font; the script must not draw the wordmark in it."""
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "fc-match").write_text("#!/bin/sh\nprintf /usr/share/fonts/TTF/DejaVuSans-Bold.ttf\n", encoding="utf-8")
    (fake / "fc-match").chmod(0o755)
    # font_path sits above the fontTools imports, so it runs without fontTools (tests have only pytest)
    code = (
        "src = open('docs/assets/wordmark.py').read().split('from fontTools')[0];"
        "ns = {'__name__': 'wordmark'}; exec(src, ns); ns['font_path'](['wordmark.py'])"
    )
    p = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True,
                       env={"PATH": f"{fake}:/usr/bin:/bin"}, timeout=30)
    assert p.returncode != 0 and "JetBrains Mono" in p.stderr
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_readme.py`
Expected: FAIL: `FileNotFoundError` for `wordmark.light.svg` (2 tests); the font test fails because `docs/assets/wordmark.py` does not exist.

- [ ] **Step 3: Write the generator**

`docs/assets/wordmark.py`:

```python
"""Generates docs/assets/wordmark.{light,dark}.svg: a violet tile with a chevron, then "loadout" in JetBrains Mono Bold.

The letters become outlines, so the SVG needs no font and looks the same in every viewer (an image cannot load web
fonts). JetBrains Mono is under the SIL Open Font License, which permits this. Maintainer tool, not part of the CLI:
    uv run --with fonttools docs/assets/wordmark.py [FONT]
FONT defaults to the JetBrains Mono Bold that fontconfig finds (fc-match).
"""
import subprocess
import sys
from pathlib import Path


def font_path(argv):
    """The font file: the argument, else fontconfig's JetBrains Mono Bold; refuses a fallback font."""
    if len(argv) > 1:
        return argv[1]
    found = subprocess.run(["fc-match", "-f", "%{file}", "JetBrains Mono:style=Bold"],
                           capture_output=True, text=True, check=True).stdout
    if "JetBrainsMono" not in Path(found).name.replace(" ", ""):
        sys.exit(f"JetBrains Mono Bold is not installed (fontconfig offered {found}); pass the .ttf path as an argument")
    return found


from fontTools.pens.svgPathPen import SVGPathPen  # noqa: E402  (font_path above must work without fontTools)
from fontTools.pens.transformPen import TransformPen  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402

HERE = Path(__file__).resolve().parent
WORD = "loadout"
SIZE = 64  # font size in px
TILE = 72  # tile edge in px
GAP = 18  # space between tile and word
VARIANTS = {
    "light": {"tile": "#7c3aed", "chevron": "#ffffff", "text": "#0f172a"},
    "dark": {"tile": "#a78bfa", "chevron": "#0f1117", "text": "#e6e6eb"},
}


def word_path(font):
    """The word's outline as one SVG path with its baseline at y=0; returns (d, width, cap height)."""
    glyphs, cmap = font.getGlyphSet(), font.getBestCmap()
    scale = SIZE / font["head"].unitsPerEm
    pen = SVGPathPen(glyphs)
    x = 0
    for ch in WORD:
        name = cmap[ord(ch)]
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x, 0)))
        x += glyphs[name].width * scale
    return pen.getCommands(), x, font["OS/2"].sCapHeight * scale


def svg(variant, d, width, cap):
    c = VARIANTS[variant]
    total = TILE + GAP + width
    base = (TILE + cap) / 2  # centres the cap height on the tile
    cx, cy, a = TILE / 2 + 3, TILE / 2, 13  # the chevron: two strokes meeting at a point
    chevron = f"M{cx - a / 1.4:.1f} {cy - a:.1f} L{cx + a / 1.4:.1f} {cy:.1f} L{cx - a / 1.4:.1f} {cy + a:.1f}"
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total:.1f} {TILE}" width="{total:.0f}" height="{TILE}" role="img">\n'
        f"<title>loadout</title>\n"
        f'<rect width="{TILE}" height="{TILE}" rx="16" fill="{c["tile"]}"/>\n'
        f'<path d="{chevron}" fill="none" stroke="{c["chevron"]}" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>\n'
        f'<path transform="translate({TILE + GAP} {base:.1f})" fill="{c["text"]}" d="{d}"/>\n'
        f"</svg>\n"
    )


def main(argv):
    font = TTFont(font_path(argv))
    d, width, cap = word_path(font)
    for variant in VARIANTS:
        (HERE / f"wordmark.{variant}.svg").write_text(svg(variant, d, width, cap), encoding="utf-8", newline="\n")
        print(f"wrote docs/assets/wordmark.{variant}.svg")


if __name__ == "__main__":
    main(sys.argv)
```

- [ ] **Step 4: Generate the SVGs and run the tests**

Run: `uv run -q --with fonttools docs/assets/wordmark.py && uv run --python 3.12 --with pytest pytest -q tests/test_readme.py`
Expected: `wrote docs/assets/wordmark.light.svg`, `wrote docs/assets/wordmark.dark.svg`, then 3 passed. `head -2 docs/assets/wordmark.dark.svg` shows `viewBox="0 0 358.8 72"`.

- [ ] **Step 5: Full suite and commit**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: all pass.

```bash
git add docs/assets/wordmark.py docs/assets/wordmark.light.svg docs/assets/wordmark.dark.svg tests/test_readme.py
git commit -m "feat(readme): a loadout wordmark as outline SVGs for light and dark"
```

---

### Task 2: The README

**Files:**
- Modify: `README.md` (full rewrite to the structure below)
- Modify: `tests/test_readme.py` (append)
- Modify: `CONTRIBUTING.md` ("The README demo" section: one sentence on the wordmark)

**Interfaces:**
- Consumes: `docs/assets/wordmark.{light,dark}.svg` from Task 1; `docs/diagrams/toolset-workflow.{light,dark}.svg` (already in main).

- [ ] **Step 1: Append the failing README tests**

Add to `tests/test_readme.py`:

```python
README = ROOT / "README.md"
CURL = "curl -fsSL https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.sh | bash -s -- --install"
CLONE = "git clone https://github.com/jonasyr/agent-loadout"


def _readme():
    return README.read_text(encoding="utf-8").replace("\r", "")


def _hero(text):
    m = re.search(r'\A<div align="center">\n(.*?)\n</div>\n', text, re.S)
    assert m, 'README must open with <div align="center"> … </div>'
    return m.group(1)


def _slugs(text):
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    return {re.sub(r"[^\w\- ]", "", h.strip().lower()).replace(" ", "-") for h in re.findall(r"^#{1,6}\s+(.*)$", text, re.M)}


def test_hero_shows_the_wordmark_in_both_variants():
    hero = _hero(_readme())
    assert '<source media="(prefers-color-scheme: dark)" srcset="docs/assets/wordmark.dark.svg">' in hero
    assert re.search(r'<img alt="loadout" src="docs/assets/wordmark\.light\.svg" height="\d+">', hero)
    assert "Claude Code, fully set up in one command." in hero


def test_hero_markdown_is_separated_by_blank_lines():
    """GitHub parses Markdown inside an HTML block only after a blank line."""
    hero = _hero(_readme())
    blocks = hero.split("\n\n")
    assert blocks[0].startswith("<picture>") and blocks[0].endswith("</picture>")
    for block in blocks[1:]:
        assert not block.startswith(" "), f"indented hero block renders as code: {block[:40]!r}"


def test_link_row_points_to_headings():
    text = _readme()
    row = next(line for line in _hero(text).splitlines() if line.startswith("**[Quick start]"))
    targets = re.findall(r"\]\(#([^)]+)\)", row)
    assert [t for t in targets] and len(targets) == 5
    missing = [t for t in targets if t not in _slugs(text)]
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
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_readme.py`
Expected: the hero, blank-line, link-row and quick-start tests FAIL (no `<div align="center">`, no `## What you get` after the Quick start in the current order); `test_commands_have_no_prompt_characters` passes already (today's README has no prompts; it guards the rewrite).

- [ ] **Step 3: Rewrite README.md**

Replace the whole file with:

````markdown
<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/wordmark.dark.svg">
  <img alt="loadout" src="docs/assets/wordmark.light.svg" height="56">
</picture>

<sub>agent-loadout</sub>

### Claude Code, fully set up in one command.

The best plugins, MCP servers and rules, preconfigured to work together, on every machine, and kept up to date.

[![CI](https://github.com/jonasyr/agent-loadout/actions/workflows/ci.yml/badge.svg)](https://github.com/jonasyr/agent-loadout/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platforms: Linux, macOS, Windows (WSL 2)](https://img.shields.io/badge/platforms-Linux%20%C2%B7%20macOS%20%C2%B7%20Windows%20%28WSL%202%29-informational.svg)](docs/tutorials/getting-started.md)
[![Claude Code plugin](https://img.shields.io/badge/Claude%20Code-plugin-D97757.svg)](.claude-plugin/marketplace.json)

**[Quick start](#quick-start) · [What you get](#what-you-get) · [Toolset](#the-toolset) · [Trust](#why-you-can-trust-it) · [Docs](#docs)**

</div>

![The Quick start on a machine that already has Claude Code: the one-liner installs what is missing, reviews the existing setup with a reason for each change, applies the choices with an undo, then loadout check and loadout init, and Claude Code starts with the kit](docs/assets/demo.gif)

<sub>The Quick start below, on a machine that already has Claude Code. Recorded in a sandbox with fake data.</sub>

Claude Code gets much better with the right plugins, MCP servers and instructions, but setups drift: every machine ends up different, old tools linger and versions go stale. loadout is a reviewed shared kit (this repo) plus your personal layer (your own folder, ideally a private git repo); its CLI merges both into `~/.claude` and keeps them current ([how it works](docs/explanation/architecture.md)).

## Quick start

You need git and curl; you log in to Claude Code and gh at the end. The one line per OS is in [Before you start](docs/tutorials/getting-started.md#before-you-start).

> [!NOTE]
> On Windows, use WSL 2 and read [Use loadout on Windows with WSL 2](docs/how-to/wsl.md) first. Start in your Linux home folder: a shell started from Windows opens in `/mnt/c`.

### 1. Install

Both ways do the same: they put the kit in an `agent-loadout` folder and run its setup.

**Quickest: one command** (clones into your home folder)

```bash
cd ~
curl -fsSL https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.sh | bash -s -- --install
```

**Or clone it yourself** (you choose the folder and can read the code first)

```bash
git clone https://github.com/jonasyr/agent-loadout
cd agent-loadout
./bootstrap.sh --install
```

Keep the folder where it is: the installed links point into it.

<details>
<summary>What the installer does</summary>

It installs what is missing, in your home folder and without sudo: uv (which also provides Python), Claude Code, Node.js, gh and every tool in [the toolset](#the-toolset). It never replaces a tool you already have. `--install` runs those installers without a further prompt ([what runs when you ask](docs/explanation/security-and-trust.md#what-runs-when-you-ask)). The one-liner clones into `./agent-loadout`; add `--dir PATH` after `--install` to choose another folder.

Then it walks you through three steps (your personal layer, preferences, your existing setup) and, if it replaced anything, names the undo command. It ends with the steps still open on your machine. Step by step: [Getting started](docs/tutorials/getting-started.md).

</details>

<details>
<summary>Experimental: native Windows (not recommended; use WSL 2)</summary>

```powershell
cd $HOME
& ([scriptblock]::Create((irm https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.ps1))) --install
```

Git for Windows is required (Git Bash runs the hooks). Details: [Native Windows](docs/tutorials/getting-started.md#experimental-native-windows).

</details>

### 2. Log in

Open a new terminal (bootstrap added `~/.local/bin` to your shell profile), then:

```bash
claude                                  # log in to Claude Code, then quit it
gh auth login && gh auth setup-git      # log in to GitHub
```

### 3. Check

```bash
loadout check
```

A read-only health check: it prints `Health check: N of M OK` and names the fix for each problem.

### 4. Use it in a project

```bash
cd my-project
loadout init
```

Then open Claude Code there and run `/loadout:onboard`: it reads the project and writes its documentation.

## What you get

- **Curated defaults.** The toolset complements itself instead of overlapping, and every keep or drop decision has a written reason in [`catalog.json`](catalog.json).
- **Works on existing setups.** `loadout adopt` shows what it would change and why, asks first, and backs up what it replaces ([your own tools](docs/how-to/your-own-tools.md)).
- **Stays up to date by itself.** Claude Code updates the plugins, loadout pulls the kit and your personal layer daily, and you get a notice when tools have updates ([the daily sync](docs/explanation/architecture.md#the-daily-sync)).
- **Yours on top.** Your preferences, own tools and profiles live in your personal layer; change them with `loadout configure` or `/loadout:configure` ([preferences](docs/how-to/set-preferences.md)).
- **Projects too.** `loadout init` prepares any repo for agent work, profiles add domain tools only where needed, and three skills keep the docs true ([documentation strategy](docs/explanation/documentation-strategy.md)).

## The toolset

One workflow from idea to merged change: Claude plans before it builds, works with a code graph, current docs and a real browser, and ends every change with a review and docs that are still true.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/diagrams/toolset-workflow.dark.svg">
  <img alt="An idea or a bug goes through three stages. Think first: brainstorming, writing-plans, then execution-advisor. Build: a test-driven build, with codebase-memory, Serena and LSP diagnostics for the code, Context7 and Microsoft Learn for libraries, and frontend-design, playwright-cli and impeccable for UI work. Finish: review, /loadout:docs-sync, then commit-commands. rtk shrinks command output in every step." src="docs/diagrams/toolset-workflow.light.svg">
</picture>

<sub>[Source](docs/diagrams/toolset-workflow.mmd)</sub>

| Job | Tools | Kind |
|---|---|---|
| Plan before building | [superpowers](https://github.com/obra/superpowers) (brainstorm, plan, test-driven build, debug, verify) · `/loadout:execution-advisor` (inline or subagents, per task) | plugin · loadout skill |
| Understand the code | [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) (code graph: callers, impact, dead code) · [Serena](https://github.com/oraios/serena) (find, rename, edit symbols) · LSP plugins for [Python](https://github.com/microsoft/pyright), [TypeScript](https://github.com/typescript-language-server/typescript-language-server), [Rust](https://github.com/rust-lang/rust-analyzer) (type errors after each edit) | MCP servers · plugins |
| Current docs | [Context7](https://github.com/upstash/context7) (libraries and frameworks) · [Microsoft Learn](https://github.com/MicrosoftDocs/mcp) (.NET, Azure, Windows) | MCP servers via plugins |
| UI that looks designed | [frontend-design](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/frontend-design) (direction) · [playwright-cli](https://github.com/microsoft/playwright-cli) (real browser checks) · [impeccable](https://github.com/pbakaus/impeccable) (audit and polish) | plugins · CLI |
| Safe, documented changes | [security-guidance](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/security-guidance) (warnings and commit review) · `/loadout:docs-sync`, `/loadout:docs-audit`, `/loadout:onboard` (docs that match the code) · [commit-commands](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/commit-commands) (commit, push, PR) | plugins · loadout skills |
| Fewer tokens | [rtk](https://github.com/rtk-ai/rtk) (compact command output, applied by a hook) | CLI |

Domain tools (research, databases, SonarQube, Android) are added per project with profiles. How the pieces work together: [The toolset](docs/explanation/the-toolset.md). Every tool with its settings: [Included tools](docs/reference/included-tools.md).

## Why you can trust it

- **It updates itself, so you trust this repo.** A daily background job runs `git pull --ff-only` on this repo and your personal layer. Turn it off with `LOADOUT_NO_AUTO_PULL=1`, or point your clone at a fork you review ([the daily sync](docs/explanation/architecture.md#the-daily-sync)).
- **What it replaces can be restored.** Your own tools, files and links go into a timestamped backup before loadout touches them, and `loadout restore` puts them back. The routine sync of the kit's own settings is not backed up ([details](docs/how-to/undo-and-restore.md#what-restore-does-not-undo)).
- **Nothing of yours changes without your answer.** `loadout adopt` is a dry run until `--apply`, then asks per group and once more before it applies; tools loadout does not know stay as they are, and binary updates show each command first.
- **Secrets stay out of git.** Keys live in `~/.config/loadout/secrets.env` (readable only by you) and configs refer to them as `${VAR}`; a secret guard checks what is recorded into your personal layer ([secrets](docs/explanation/security-and-trust.md#secrets)).

What runs automatically and where the trust boundary is: [Security and trust](docs/explanation/security-and-trust.md). To report a vulnerability, see [SECURITY.md](SECURITY.md).

## Docs

The full index is [docs/README.md](docs/README.md).

| I want to | Read |
|---|---|
| Install step by step, per platform | [Getting started](docs/tutorials/getting-started.md) |
| Decide what happens to tools I already have | [Handle your own tools](docs/how-to/your-own-tools.md) |
| Undo something loadout changed | [Undo what loadout changed](docs/how-to/undo-and-restore.md) |
| Change my preferences or add tools globally | [Set your working preferences](docs/how-to/set-preferences.md) |
| Add domain tools to one repo | [Write a personal profile](docs/how-to/write-a-profile.md), [Profile format](docs/reference/profile-format.md) |
| Fix a problem | [Troubleshooting](docs/how-to/troubleshooting.md) |
| Look up a command, flag or exit code | [CLI reference](docs/reference/cli.md) |
| See which tools are included and why | [Included tools](docs/reference/included-tools.md) |
| See how the tools form one workflow | [The toolset](docs/explanation/the-toolset.md) |
| Understand how the parts fit together | [Architecture](docs/explanation/architecture.md) |
| Know why it was built this way | [Decision records](docs/adr/README.md) |
| Remove loadout | [Uninstall loadout](docs/how-to/uninstall.md) |
| Contribute | [CONTRIBUTING.md](CONTRIBUTING.md) |

Other agents (Codex, Gemini CLI, Cursor) are not supported yet; the plan is in [Architecture](docs/explanation/architecture.md#other-agents-planned).

## License

[MIT](LICENSE)
````

Facts to keep honest while transcribing (each was checked against the docs when planning; re-check any you change):
- the installer list and "never replaces a tool you already have": `docs/tutorials/getting-started.md` line 12;
- `--dir PATH`: `bootstrap.sh` line 6;
- `Health check: N of M OK` and "names the fix": `docs/tutorials/getting-started.md`, "Verify";
- the `#secrets` anchor: `docs/explanation/security-and-trust.md` has `## Secrets`.

Removed from the README (each fact stays in the linked page, nothing is lost): the plain-text secrets line about `configure set pref`, the redaction sentence, the "without a terminal it needs `--yes`" detail, the restart-Claude-Code note (in Getting started, "Verify").

- [ ] **Step 4: CONTRIBUTING sentence**

In `CONTRIBUTING.md`, at the end of "## The README demo", add:

```markdown
The hero's wordmark (`docs/assets/wordmark.light.svg` and `.dark.svg`) is generated with the letters as outlines: `uv run --with fonttools docs/assets/wordmark.py` (needs JetBrains Mono Bold installed, or pass its `.ttf` path).
```

- [ ] **Step 5: Run the README, link, demo and diagram tests**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_readme.py tests/test_repo_static.py tests/test_demo.py tests/test_diagrams.py`
Expected: all pass. If `test_relative_links_resolve` reports an anchor, the heading text in the target page differs from the link: fix the link, not the page.

`test_diagrams.py::test_each_embed_links_its_source` and friends now also cover the README's toolset embed (they scan README.md).

- [ ] **Step 6: Full suite and commit**

Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: all pass.

```bash
git add README.md tests/test_readme.py CONTRIBUTING.md
git commit -m "docs(readme): hero, Quick start up front with both install routes, shorter sections"
```

---

### Task 3: Check it where people read it

**Files:** none committed unless a fix is needed (then `README.md` and a `fix(readme): …` commit).

- [ ] **Step 1: Local check of the wordmark**

Serve a scratch page (in the session scratchpad, never the repo) that shows `wordmark.light.svg` on `#ffffff` and `wordmark.dark.svg` on `#0d1117` at `height="56"`, screenshot with playwright-cli (`PLAYWRIGHT_MCP_EXECUTABLE_PATH=/usr/bin/chromium`, run from the scratchpad so `.playwright-cli/` lands there), and look: tile and letters aligned, chevron centred, no clipping.

- [ ] **Step 2: Push the branch (needs the user's OK) and check on GitHub**

After the user's OK: `git push -u origin docs/readme-polish`. Then, for `https://github.com/jonasyr/agent-loadout/tree/docs/readme-polish`, take full-page screenshots at 320, 768 and 1280 px wide in light and dark (`set-color-scheme`), and look at each:
- hero centred; wordmark switches between light and dark; badges on one or two lines; link row wraps cleanly at 320 px;
- the NOTE box renders as an alert; both install code blocks have GitHub's copy button;
- both `<details>` collapse; the toolset diagram shows the right variant;
- every link-row link jumps to its section (click each once at 1280 px).

- [ ] **Step 3: Fix what the screenshots show**

Change only layout or wording that the screenshots prove wrong; re-run Task 2 Step 5; commit as `fix(readme): <what>`; push (the user already approved pushing this branch); re-check the affected view.

---

## After the tasks

- `/loadout:docs-sync` over the branch (the README links into docs; no doc facts changed).
- One whole-branch review, then the PR (the user's OK).
