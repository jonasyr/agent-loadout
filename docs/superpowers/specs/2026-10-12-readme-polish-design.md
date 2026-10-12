# README polish: a hero, the Quick start up front, shorter sections

Date: 2026-10-12. Status: design approved in conversation (hero B with wordmark 1, structure, tagline 1, install section), awaiting spec review.

## Why

Today the install command appears after about 60 lines: the toolset table, "What you get" and "Why you can trust it" come
first, and the Quick start mixes the commands with three paragraphs of caveats. The tagline describes the mechanism
(kit plus settings, kept current), not the payoff (a fully set-up Claude Code that works out of the box).

**Goal:** a visitor understands in seconds what loadout is, sees it work (the GIF), and copies one command to install it,
by the route they prefer (one-liner or clone). Professional, modern, clean; nothing GitHub cannot render (no CSS,
no scripts; only GitHub's allowed HTML).

**Non-goals:** new content or features; changing facts (every fact keeps its home in `docs/`; the README links there);
the GitHub description, topics and social preview (next step, C).

## Structure (top to bottom)

1. **Hero**, centred (`<div align="center">`):
   - Wordmark: `<picture>` with `docs/assets/wordmark.dark.svg` for `prefers-color-scheme: dark` and
     `docs/assets/wordmark.light.svg` as the `<img>`, alt `loadout`, height about 56 px.
   - Under it, small: `agent-loadout` (the repo name; the command is `loadout`).
   - Headline (bold): **Claude Code, fully set up in one command.**
   - One line: *The best plugins, MCP servers and rules, preconfigured to work together, on every machine, and kept up to date.*
   - The four existing badges (CI, MIT, platforms, Claude Code plugin).
   - Link row: **Quick start · What you get · Toolset · Trust · Docs**, as `<a href="#…">` to the section headings.
2. **Demo GIF** and its one-line caption, unchanged.
3. **Intro**, two sentences: setups drift (machines differ, tools linger, versions go stale); loadout is a reviewed shared
   kit plus your personal layer, merged into `~/.claude` and kept current. Link: Architecture.
4. **Quick start** (`## Quick start`):
   - One line: what you need (git and curl; you log in to Claude Code and gh afterwards), linking
     *Before you start*.
   - A `> [!NOTE]` box: on Windows use WSL 2 (link to the WSL how-to); start in your home folder, because a shell started
     from Windows opens in `/mnt/c`.
   - `### 1. Install`: "Both ways do the same: they put the kit in an `agent-loadout` folder and run its setup."
     - **Quickest: one command** (clones into your home folder): the existing two lines `cd ~` and the curl one-liner,
       byte-identical (`tests/test_demo.py` compares the tape with this line).
     - **Or clone it yourself** (you choose the folder and can read the code first): `git clone …`, `cd agent-loadout`,
       `./bootstrap.sh --install`, one per line.
     - "Keep the folder where it is: the installed links point into it."
     - `<details>` **What the installer does**: installs what is missing in your home folder, without sudo (uv with
       Python, Claude Code, Node.js, gh and the toolset); `--install` runs those installers without a further prompt
       (link: Security and trust); the one-liner takes `--dir PATH` to clone somewhere else; it walks you through three
       steps (personal layer, preferences, your existing setup) and names the undo command if it replaced anything.
     - `<details>` **Experimental: native Windows**, the existing block.
   - `### 2. Log in`: open a new terminal (bootstrap added `~/.local/bin` to your shell profile), then `claude` and
     `gh auth login && gh auth setup-git`.
   - `### 3. Check`: `loadout check` (read-only health check).
   - `### 4. Use it in a project`: `loadout init`, then `/loadout:onboard` in Claude Code.
5. **What you get** (`## What you get`): the same five points, each a bold lead, one sentence and a link.
6. **Toolset** (`## The toolset`): one-sentence intro; the toolset workflow diagram embedded as in the docs
   (`<picture>` with `docs/diagrams/toolset-workflow.{dark,light}.svg`, the same alt text); the existing table; the
   existing two links (The toolset, Included tools) and the profiles sentence.
7. **Trust** (`## Why you can trust it`): the same four points, one or two sentences each, details linked; then the
   existing Security and trust and SECURITY.md line.
8. **Docs** (`## Docs`): the existing "I want to / Read" table and the docs index link; the "Other agents" sentence
   moves here.
9. **License**.

Style: commands without `$` prompts and one command per line, so GitHub's copy button gives a clean result; GitHub
alerts (`[!NOTE]`, `[!TIP]`) sparingly, at most two; no emojis; every heading reachable from the link row.

## Wordmark asset

- Design: a rounded violet tile with a `❯` chevron, then `loadout` in JetBrains Mono Bold. Light: tile `#7c3aed`,
  chevron white, text `#0f172a`. Dark: tile `#a78bfa`, chevron `#0f1117`, text `#e6e6eb` (the demo's colours).
- `docs/assets/wordmark.py` generates `wordmark.light.svg` and `wordmark.dark.svg`, converting the letters to outlines
  with fontTools from the installed JetBrains Mono (`uv run --with fonttools docs/assets/wordmark.py`), so the SVG needs
  no font and looks the same in every viewer. JetBrains Mono is under the SIL Open Font License, which permits this.
  The script is a maintainer tool; the CLI stays standard library only.
- The `❯` glyph is drawn as a path (two strokes), not taken from the font.
- Each SVG has a `viewBox`, a `role="img"` and a `<title>loadout</title>`.

## Tests

- `tests/test_readme.py` (standard library):
  - the hero holds a `<picture>` whose dark `<source>` and light `<img>` point to existing wordmark files, with alt text;
  - every `href="#…"` in the link row matches a heading anchor in the README (GitHub's slug rules, as in
    `test_repo_static._anchors`);
  - the Quick start contains both install routes: the curl one-liner and `git clone https://github.com/jonasyr/agent-loadout`;
  - both wordmark SVGs contain no `<text>` element (letters are outlines) and no external references.
- Existing tests keep guarding the rest: relative links (`test_repo_static`), the one-liner in the tape (`test_demo`),
  diagram embeds (`test_diagrams`, which also covers the README).

## Verification

- playwright-cli: the README on GitHub (after pushing the branch) at 320, 768 and 1280 px, light and dark: the hero
  centred, the wordmark switches variant, the link row wraps cleanly on a phone, code blocks show the copy button.
- Before pushing: the wordmark SVGs in a local page on light and dark backgrounds.

## Documentation

- CONTRIBUTING "The README demo" gains one sentence on regenerating the wordmark.
- AGENTS.md: no change (the map already lists `docs/`).
