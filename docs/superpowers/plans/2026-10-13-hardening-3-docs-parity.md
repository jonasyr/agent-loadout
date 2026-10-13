# Hardening 3: Docs Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** README, `docs/`, diagrams, manifests and linked rules present Claude Code and Codex as equal targets, with no claim the code contradicts.

**Architecture:** Shared pages describe both agents (two-column tables or `In Claude Code` / `In Codex` subsections where they differ); `docs/how-to/codex.md` keeps only Codex-only facts. Guard tests (links, Codex manifest, diagram skill) come first; a repo-local diagram skill drives the diagram changes; ADRs get status notes plus ADR 0024.

**Tech Stack:** Markdown, Mermaid (pinned mermaid-cli via `docs/diagrams/render.sh`, podman), pytest, playwright-cli.

**Spec:** `docs/superpowers/specs/2026-10-13-hardening-3-docs-parity-design.md`

## Global Constraints

- One home per fact (`docs/explanation/documentation-strategy.md`): a fact lives on one page; others link.
- Writing: `rules/docs-policy.md`; `docs/explanation/documentation-strategy.md` sections "Diátaxis: four kinds of docs" (page kinds) and "ADRs: decisions with their reasons" (Task 9). Style: plain English, short sentences, no marketing, match the surrounding page.
- ADR bodies are not rewritten; a changed decision gets a status note and ADR 0024.
- Every Codex claim is checked against `cli/loadout/` before it is written; the "Facts" blocks below name the source.
- Tests never touch the real home; no real `claude`/`codex` runs. Tests: `uv run --python 3.12 --with pytest pytest -q`.
- Conventional Commits; no AI attribution; author Jonas Weirauch <jonas.weirauch@gmx.de>.
- No CLI behaviour changes in this PR.

## Review Focus

1. A rewritten page drops a Claude Code fact while adding the Codex one (regression for Claude Code readers) — each doc task ends with a diff read against the old page: every removed sentence is either moved (link to its new home) or was false.
2. A Codex claim that is only true under a condition (Codex usable, after a pull that brought commits, trusted project) stated unconditionally — the stand-in review in Task 10 is briefed to check conditions.
3. An anchor renamed by a heading rewrite breaks links from other pages or from code output (`cli/loadout/` prints doc anchors) — Task 1's link test covers docs; Task 10 greps `cli/loadout/` and `plugins/` for `docs/...#` anchors.
4. Diagrams unreadable at phone width or in dark mode after adding a Codex subgraph — Task 3's browser check at 320 and 1280 px, light and dark.
5. `codex.md` shrink leaves a fact homeless (removed from codex.md, not added elsewhere) — Task 6 Step 1 builds the move table first; each row is checked off in Step 4.

## Codex facts (verified sources; use these, re-check the line if you change wording)

| Fact | Source |
|---|---|
| Agent choice in `targets.json` (personal layer); one agent must stay on; `loadout configure set target codex on/off`; codex 0.161+ | `targets.py`, current `docs/how-to/codex.md` |
| Restart text per agent: both → "Restart Claude Code (or run /reload-plugins) and Codex"; Codex only → "Restart Codex" | `targets.py:37-44` `restart_hint()` |
| Rules + `me.md` → marked block `<!-- loadout:start -->…<!-- loadout:end -->` in `~/.codex/AGENTS.md`; `AGENTS.override.md` shadows it (check warns) | `codex.py`, `codex.py:791` |
| Codex folder is `$CODEX_HOME`, else `~/.codex` | `paths.py:27-30` |
| Personal MCP → `[mcp_servers.*]` in `~/.codex/config.toml`; secrets as `env_vars` names; ownership recorded in `~/.claude/.loadout/codex-config.json` | `codex.py:219-220` |
| Personal skills → links in `~/.agents/skills` | `paths.agents_skills()` |
| Effort/notifications → `model_reasoning_effort`, `tui.notifications` | current codex.md |
| Daily sync: after the pull brought commits, if Codex is on and usable, `codex.apply_all(refresh=True)` refreshes plugins/config/skills, then drift notices | `maintenance.py:249-262` |
| Codex hooks: `hooks/codex.json`; SessionStart serena activate + `loadout hook-session-start`; SessionEnd serena cleanup; PreToolUse `Bash` → `rtk hook codex`, `mcp__serena__.*` → `serena-hooks auto-approve --client=codex`; PostToolUse `Edit|Write` → advisor record + `typecheck.py` (90 s hook timeout, 20 s per check); Stop advisor; SubagentStart subagent-context. No `Grep|Glob` hook, no reload check | `plugins/loadout/hooks/codex.json` |
| Codex runs plugin hooks only after approval in `/hooks`; loadout never approves | current codex.md, `rules` |
| Project: `.codex/config.toml` add-only MCP sections; `${VAR}` args skipped; profile plugins `enabled = true` in repo, `false` in `~/.codex/config.toml`; `.claude/skills/*` linked into `.agents/skills` as `../../.claude/skills/NAME`; read only in a trusted project; loadout never trusts | `codex_project.py`, `codex_project.py:86-115` |
| Restore removes Codex plugins/marketplaces loadout installed (recorded undo `codex plugin remove`, `codex plugin marketplace remove`) | `codex.py:564,577` |
| Ctrl+C → exit 130, "run the same command again to continue" | `__main__.py:83-86` |
| State `~/.claude/.loadout/`, backups `~/.claude/backups/` for every user | `paths.py:38-43` |
| Codex-only adopt: MCP in `config.toml`, skills in `~/.agents/skills`; global / leave / remove | current codex.md "Keep both the same" |
| Context7 plain URL for Codex; `codex mcp login context7` optional | current codex.md |
| Commit attribution in Codex is a ChatGPT account setting | current codex.md |

---

### Task 1: Guard tests for links and the Codex manifest

**Files:**
- Create: `tests/test_docs_links.py`
- Modify: whatever docs the new test finds broken (today's tree)

**Interfaces:**
- Produces: `tests/test_docs_links.py` with `anchors(path) -> set[str]` and `test_links_resolve[<file>]`; later tasks run it after every page edit.

- [ ] **Step 1: Write the tests**

```python
"""Every relative link and #anchor in the human docs resolves; the Codex plugin manifest points at real files."""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
FILES = sorted([ROOT / "README.md", ROOT / "AGENTS.md", ROOT / "CONTRIBUTING.md",
                *(p for p in DOCS.rglob("*.md") if p.relative_to(DOCS).parts[0] != "superpowers")])
FENCE = re.compile(r"^(```|~~~)[^\n]*\n.*?^\1[ \t]*$", re.S | re.M)
CODE = re.compile(r"`[^`\n]*`")
MD_LINK = re.compile(r"\]\(<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\)")
HTML_LINK = re.compile(r"""\b(?:href|src|srcset)=["']([^"']+)["']""")
HEADING = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$", re.M)
HTML_ID = re.compile(r"""\b(?:id|name)=["']([^"']+)["']""")


def _slug(text: str) -> str:
    """GitHub's heading anchor: lower case, markup and punctuation dropped, spaces to hyphens."""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)  # [label](url) -> label
    text = re.sub(r"<[^>]+>", "", text).replace("`", "").lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def anchors(path: Path) -> set[str]:
    text = FENCE.sub("", path.read_text(encoding="utf-8"))
    out, seen = set(), {}
    for m in HEADING.finditer(text):
        slug = _slug(m.group(1))
        n = seen.get(slug, 0)
        seen[slug] = n + 1
        out.add(slug if n == 0 else f"{slug}-{n}")
    out.update(HTML_ID.findall(text))
    return out


def _targets(path: Path) -> list[str]:
    text = CODE.sub("", FENCE.sub("", path.read_text(encoding="utf-8")))
    return MD_LINK.findall(text) + HTML_LINK.findall(text)


@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(ROOT)))
def test_links_resolve(path):
    bad = []
    for target in _targets(path):
        if re.match(r"[a-z][a-z0-9+.-]*:", target):  # https:, mailto:, ...
            continue
        file_part, _, anchor = target.partition("#")
        dest = (path.parent / file_part).resolve() if file_part else path
        if not dest.exists():
            bad.append(f"{target}: no such file")
        elif anchor and dest.suffix == ".md" and anchor not in anchors(dest):
            bad.append(f"{target}: no heading #{anchor} in {dest.relative_to(ROOT)}")
    assert not bad, "\n".join(bad)


def test_codex_manifest_points_at_real_files():
    plugin = ROOT / "plugins" / "loadout"
    data = json.loads((plugin / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert data.get("name") == "loadout" and data.get("description")
    for key in ("skills", "mcpServers", "hooks"):
        assert (plugin / data[key]).exists(), f"{key}: {data[key]} does not exist"
```

- [ ] **Step 2: Run them**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_docs_links.py`
Expected: the manifest test PASSES (guard); `test_links_resolve` either passes or FAILS naming today's broken links. Also sanity-check the slug function: temporarily break one known link (e.g. change `#what-bootstrap-asks` in `docs/tutorials/getting-started.md` to `#what-bootstrap-ask`), run, see it FAIL naming that link, revert.

- [ ] **Step 3: Fix every broken link the test names**

For each failure: find the heading it meant (`grep -n "^#" <target>`) and correct the link; never delete a link to make the test pass unless its target was removed on purpose (then link the new home).

- [ ] **Step 4: Run them again**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_docs_links.py`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_docs_links.py docs README.md AGENTS.md CONTRIBUTING.md
git commit -m "test(docs): every relative link and anchor resolves; Codex manifest paths exist"
```

---

### Task 2: The repo-local diagram skill

**Files:**
- Create: `.claude/skills/diagrams/SKILL.md`
- Create: symlink `.agents/skills/diagrams` → `../../.claude/skills/diagrams`
- Test: `tests/test_diagrams.py` (append)

Ruling (deviates from spec §3, which put the source in `.agents/skills` and the link in `.claude/skills`): the source goes in `.claude/skills` and the link in `.agents/skills`, because that is exactly the link `loadout init`/`profile` creates (`codex_project.py:98`); the reverse layout would make loadout report "left as is" on this repo. Update the spec line in the same commit.

**Interfaces:**
- Produces: the skill `diagrams`, used in Task 3.

- [ ] **Step 1: Write the failing test** (append to `tests/test_diagrams.py`; add `import os` if missing)

```python
@pytest.mark.skipif(os.name == "nt", reason="git checks symlinks out as files on Windows runners")
def test_diagram_skill_reaches_both_agents():
    skill = ROOT / ".claude" / "skills" / "diagrams" / "SKILL.md"
    front = re.match(r"---\n(.*?)\n---\n", skill.read_text(encoding="utf-8"), re.S)
    assert front, "SKILL.md needs YAML frontmatter"
    assert re.search(r"^name: diagrams$", front.group(1), re.M)
    assert re.search(r"^description: \S", front.group(1), re.M)
    link = ROOT / ".agents" / "skills" / "diagrams"
    assert link.is_symlink() and os.readlink(link) == "../../.claude/skills/diagrams"
```

(Use the module's existing root constant name if it differs from `ROOT`.)

- [ ] **Step 2: Run it**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_diagrams.py -k skill`
Expected: FAIL (`FileNotFoundError` for SKILL.md).

- [ ] **Step 3: Write the skill**

`.claude/skills/diagrams/SKILL.md`:

````markdown
---
name: diagrams
description: Use when creating or changing a diagram in this repo's docs (docs/diagrams/*.mmd), or when a docs change makes a diagram wrong. Writes Mermaid that follows the palette, renders the light and dark SVGs, and checks them in a browser.
---

# Diagrams in agent-loadout

The rules live in [CONTRIBUTING.md, Diagrams](../../../CONTRIBUTING.md#diagrams) and [docs/diagrams/README.md](../../../docs/diagrams/README.md); read both first. This skill adds the vocabulary and the checks.

## Classes

Colour comes only from classes in `docs/diagrams/palette.light.mmd` and `palette.dark.mmd` (same names in both). Never write `style` lines or inline colours.

| Class | Use for |
|---|---|
| `kit`, `kitGroup` | files and folders of the kit repo |
| `personal`, `personalGroup` | the personal layer |
| `claude`, `claudeGroup` | what lives in Claude Code's configuration |
| `codex`, `codexGroup` | what lives in Codex's configuration |
| `engine`, `engineGroup` | loadout's own processing steps (merge, sync) |
| `state`, `local` | machine-local state and snapshots (dashed) |
| `truth`, `notes`, `notesGroup`, `entry` | the documentation-layers diagram |
| `emph`, `truthLink`, `muted` | edges: the main path, the single-source link, background links |

Nodes: `class nodeId kit`. Subgraphs: `class SUBGRAPH kitGroup`. Edges: name them (`a e4@--> b`), then `class e4 emph`. A flowchart's last line is `%% palette`; `render.sh` replaces it with the palette. Sequence diagrams use `box rgba(...)` with the same hues as the palette (orange Claude Code, teal Codex, blue loadout, green your machine).

## Mermaid pitfalls

- Quote labels that contain parentheses, colons or slashes: `n["~/.codex/config.toml"]`.
- Line breaks: Markdown strings (`` "`**bold**\nline`" ``) or `<br/>`, never `\n` in plain labels.
- Keep labels short; the layout is `elk` with `wrappingWidth: 320`. A subgraph with more than six nodes is hard to read on a phone.

## Workflow

1. Edit `docs/diagrams/<name>.mmd`. A new class goes into both palette files with the same name.
2. Render: `docs/diagrams/render.sh <name>` (podman; `DIAGRAMS_ENGINE=docker` for docker). Palette or theme changes: `docs/diagrams/render.sh` renders all.
3. Check the output is a diagram: `grep -l "Syntax error" docs/diagrams/<name>.*.svg` must print nothing.
4. `uv run --python 3.12 --with pytest pytest -q tests/test_diagrams.py tests/test_diagrams_render.py`
5. Look at it: open each SVG with `playwright-cli` on a white and on a dark (`#0d1117`) page at 320 and 1280 px wide; screenshot to disk and read them. Every label fits its box, no edge label sits on a node, arrows point the right way.
6. Embed a new diagram with the `<picture>` snippet from CONTRIBUTING.md and alt text that says what a reader learns.
7. Commit the `.mmd` and both SVGs together (palette changes: all SVGs).
````

- [ ] **Step 4: Create the link and run the test**

```bash
mkdir -p .agents/skills && ln -s ../../.claude/skills/diagrams .agents/skills/diagrams
uv run --python 3.12 --with pytest pytest -q tests/test_diagrams.py
```
Expected: PASS (all of `test_diagrams.py`; the new links in SKILL.md are outside `docs/`, so Task 1's test does not scan them — check them by hand: `ls CONTRIBUTING.md docs/diagrams/README.md` from the repo root).

- [ ] **Step 5: Commit**

```bash
sed -i 's#New repo-local skill `.agents/skills/diagrams/SKILL.md` (Codex reads `.agents/skills`), linked from `.claude/skills/diagrams` (Claude Code)#New repo-local skill `.claude/skills/diagrams/SKILL.md` (Claude Code), linked from `.agents/skills/diagrams` (Codex) the way `loadout init` links project skills#' docs/superpowers/specs/2026-10-13-hardening-3-docs-parity-design.md
git add .claude/skills/diagrams .agents/skills/diagrams tests/test_diagrams.py docs/superpowers/specs/2026-10-13-hardening-3-docs-parity-design.md
git commit -m "feat(docs): repo-local diagram skill for Claude Code and Codex"
```

---

### Task 3: Diagrams show both agents

**Files:**
- Modify: `docs/diagrams/palette.light.mmd`, `palette.dark.mmd` (add `codex`, `codexGroup`)
- Modify: `docs/diagrams/architecture-overview.mmd`, `architecture-daily-sync.mmd`, `documentation-layers.mmd`
- Re-render: all SVGs (palette changed)
- Modify: alt text in the pages that embed them (`grep -rln "architecture-overview\|architecture-daily-sync\|documentation-layers\|settings-merge" docs README.md`)

**Interfaces:**
- Consumes: the `diagrams` skill (Task 2). Invoke it before editing.

- [ ] **Step 1: Palette classes** — append after the `claudeGroup` line in each file:

light:
```
  classDef codex fill:#ccfbf1,stroke:#0d9488,stroke-width:1.5px,color:#0f172a
  classDef codexGroup fill:#0d94880f,stroke:#0d9488,stroke-width:1.5px
```
dark:
```
  classDef codex fill:#042f2e,stroke:#2dd4bf,stroke-width:1.5px,color:#e6e6eb
  classDef codexGroup fill:#2dd4bf14,stroke:#2dd4bf,stroke-width:1.5px
```

- [ ] **Step 2: `architecture-overview.mmd`** — add after the `CC` subgraph:

```
  subgraph CX["Codex configuration · $CODEX_HOME or ~/.codex"]
    direction TB
    xPlugin["`**codex plugin**
    the same plugins and marketplaces`"]
    xAgents["`**~/.codex/AGENTS.md**
    loadout's block: rules and me.md`"]
    xConf["`**~/.codex/config.toml**
    your MCP servers, effort, notifications`"]
    xSkills["`**~/.agents/skills/**`"]
  end
```
edges (after the Claude edges):
```
  kPlugin -. "loadout installs and refreshes" .-> xPlugin
  kRules -- "copied into the block" --> xAgents
  pRules -- "copied into the block" --> xAgents
  pSkills -- link --> xSkills
  pMcp -- "owned sections" --> xConf
```
classes: `class xPlugin,xAgents,xConf,xSkills codex` and `class CX codexGroup`. Change `kRules` label line 2 to `how your agent uses the tools`. Before writing "copied into the block", verify in `codex.py` how the block is built (it may be written from the rule files' text); use the verb the code supports.

- [ ] **Step 3: `architecture-daily-sync.mmd`**
  - First box: `box rgba(234, 88, 12, 0.10) Your agent` with `participant S as Claude Code or Codex session`.
  - Add `participant X as ~/.codex` to the "Your machine" box after `C`.
  - Inside `opt new commits arrived`, after the relink line:
    ```
        opt Codex on and usable
          M->>X: refresh plugins, config and skills
        end
    ```
  - Match `maintenance.py:249-262` (Codex refresh runs inside the "new commits" branch; verify by reading the indentation there before writing).

- [ ] **Step 4: `documentation-layers.mmd`** — replace the label text `Claude Code auto memory` with `agent memory (this machine)`; keep the node id.

- [ ] **Step 5: Render, check, test**

```bash
docs/diagrams/render.sh
grep -l "Syntax error" docs/diagrams/*.svg
uv run --python 3.12 --with pytest pytest -q tests/test_diagrams.py tests/test_diagrams_render.py
```
Expected: render prints no error; grep prints nothing; tests PASS.

- [ ] **Step 6: Browser check** (skill workflow step 5) for `architecture-overview` and `architecture-daily-sync`, light and dark, 320 and 1280 px. Screenshots go to the scratchpad. Fix and re-render until every label fits.

- [ ] **Step 7: Alt text and caption**
  - Update each embedding page's alt text for the two changed diagrams so it mentions Codex.
  - Above the `settings-merge` embed, add the sentence: `The settings merge applies to Claude Code; Codex settings are handled as owned entries in config.toml (see [Use loadout with Codex](../how-to/codex.md)).` (adjust the relative link to the page's folder).

- [ ] **Step 8: Commit**

```bash
uv run --python 3.12 --with pytest pytest -q tests/test_docs_links.py tests/test_diagrams.py
git add docs/diagrams docs README.md
git commit -m "docs(diagrams): show Codex next to Claude Code in the overview and the daily sync"
```

---

### Task 4: Explanation pages — architecture and security

**Files:**
- Modify: `docs/explanation/architecture.md`, `docs/explanation/security-and-trust.md`

- [ ] **Step 1: architecture.md**
  - Intro and "The parts": the three parts are the kit, the personal layer and the agents' configuration (Claude Code: `~/.claude`, Codex: `$CODEX_HOME` or `~/.codex` and `~/.agents/skills`). Use a two-column table for what lands where.
  - New section `## loadout's own files` after "The parts": state in `~/.claude/.loadout/` (snapshot, `codex-config.json`, notices) and backups in `~/.claude/backups/`, for every user, Codex-only included (`paths.py:38-43`). Link it from `personal-repo.md` and `undo-and-restore.md` in Tasks 6.
  - "The daily sync": after the pull brought commits, Claude Code gets the merge and links; Codex (on and usable) gets `apply_all(refresh=True)` and drift notices (`maintenance.py:249-262`). Replace "Plugins are not part of this loop" with: Claude Code updates its plugins itself (marketplace `autoUpdate`); for Codex, loadout refreshes them in this step and in `loadout update`.
  - Fold the trailing `## Codex and other agents` section into the body; keep its anchor target alive by leaving a heading `## Other agents` with the sentence on adding further agents, or update every link to `#codex-and-other-agents` (`grep -rn "codex-and-other-agents" docs README.md cli plugins`).
- [ ] **Step 2: security-and-trust.md**
  - "What runs automatically": rows per agent (Claude Code session hook vs Codex session hook; both only through the plugin's hooks; Codex runs them only after `/hooks` approval).
  - Permissions: Codex `serena-hooks auto-approve --client=codex` for `mcp__serena__.*`, `rtk hook codex` (`hooks/codex.json`).
  - "What loadout touches": add `~/.codex/AGENTS.md` (own block only), `~/.codex/config.toml` (owned sections/keys, plugin `enabled` switches), `~/.agents/skills` links; repo `.codex/config.toml`, `.agents/skills`; project trust is the user's step; loadout never trusts a project or approves hooks.
  - MCP setup: Claude Code `claude mcp add-json`; Codex owned `[mcp_servers.*]` sections with `env_vars`.
- [ ] **Step 3: Diff read** — `git diff docs/explanation` and confirm every removed sentence was moved or false (Review Focus 1).
- [ ] **Step 4: Test and commit**

```bash
uv run --python 3.12 --with pytest pytest -q tests/test_docs_links.py
git add docs/explanation && git commit -m "docs(explanation): architecture and security cover Claude Code and Codex"
```
Expected: PASS.

---

### Task 5: Reference pages

**Files:**
- Modify: `docs/reference/personal-layer.md`, `profile-format.md`, `hooks.md`, `included-tools.md`, `cli.md`, `preferences-format.md`, `settings-merge.md`

- [ ] **Step 1: personal-layer.md** — "Where it goes" table gets columns `Claude Code | Codex`: `rules/me.md` → `~/.claude/rules/personal` | AGENTS.md block; `mcp.json` → user MCP | `[mcp_servers.*]` with `env_vars`; `skills/` → `~/.claude/skills` | `~/.agents/skills`; `settings.json` → merged | effort and notifications only; `hooks/`, `skills.json` → Claude Code | — (not used); `targets.json` (both).
- [ ] **Step 2: profile-format.md** — per key, a Codex sentence: `install` → `codex plugin add`, `enabled = true` in repo `.codex/config.toml`, `false` at user level; `mcp` → add-only sections, `${VAR}` args skipped with the reason; `skills` → linked into `.agents/skills`. One line: Codex reads the repo file only in a trusted project.
- [ ] **Step 3: hooks.md** — the per-hook table gets a `Codex` column (same/argument/—) from `hooks/codex.json`; add the `typecheck.py` row (Codex only, PostToolUse `Edit|Write`, 90 s, 20 s per check). This page becomes the home of "Codex runs plugin hooks only after approval in `/hooks`"; the `### In Codex` paragraph shrinks to that gate plus the manifest pointer.
- [ ] **Step 4: included-tools.md** — `codex` binary row with `target` (from `catalog.json` entry `codex`); LSP rows note "Codex: typecheck hook instead" linking `hooks.md`; rules location per agent.
- [ ] **Step 5: cli.md** — exit codes: add `130` interrupted (Ctrl+C), "run the same command again to continue"; `init`/`profile`: one table of what each writes per agent (replace the postscript at the Codex paragraph); `check`: Claude Code rows skipped when Claude Code is off, Codex rows when Codex is off (`check.py`); `apply-settings`: "Claude Code only"; backups location stated once, linking `architecture.md#loadouts-own-files`.
- [ ] **Step 6: preferences-format.md** — `ai_attribution`: Claude Code `attribution` key; Codex: account setting (link codex.md).
- [ ] **Step 7: settings-merge.md** — first paragraph: this merge is Claude Code's; Codex settings are owned entries (link codex.md "What loadout changes").
- [ ] **Step 8: Diff read, test, commit**

```bash
git diff docs/reference   # every removed sentence moved or false
uv run --python 3.12 --with pytest pytest -q tests/test_docs_links.py
git add docs/reference && git commit -m "docs(reference): per-agent behaviour in personal layer, profiles, hooks, tools and CLI"
```

---

### Task 6: How-to pages and the Codex page

**Files:**
- Modify: `docs/how-to/codex.md`, `uninstall.md`, `undo-and-restore.md`, `troubleshooting.md`, `your-own-tools.md`, `wsl.md`, `set-preferences.md`, `personal-repo.md`

- [ ] **Step 1: Move table** — before editing, list each section of `codex.md` with its destination, in the ledger:

| codex.md section | Stays / moves to |
|---|---|
| Switch it on (choice, `--agents`, `configure set target`, version floor, Codex only, first-run clone, Ctrl+C) | stays (Codex-only); `--agents` details link `cli.md#loadout-bootstrap` |
| What Codex gets (table) | moves to `reference/personal-layer.md` (done in Task 5); codex.md keeps one sentence + link |
| What stays different | stays |
| Keep both the same (adopt Codex-only items) | moves to `your-own-tools.md`; codex.md links |
| Projects | moves to `reference/profile-format.md` and `cli.md` (Task 5); codex.md keeps the trust paragraph |
| What loadout changes in `~/.codex` | moves to `explanation/security-and-trust.md` (Task 4); backup sentence to `undo-and-restore.md`; codex.md links |

- [ ] **Step 2: Rewrite `codex.md`** as "Codex-only details": switch it on, version floor, Codex only mode, first run, project trust, `/hooks` approval (link `hooks.md`), deferred MCP tools, drift, attribution, Context7. Intro sentence: "Most of loadout works the same in both agents; this page holds what only applies to Codex."
- [ ] **Step 3: The other how-tos**
  - `uninstall.md`: new `## Codex` section listing what to remove: the marked block in `~/.codex/AGENTS.md`; the `[mcp_servers.*]` sections recorded in `~/.claude/.loadout/codex-config.json`; links in `~/.agents/skills` pointing into the kit or personal layer; `codex plugin remove NAME@MARKET` and `codex plugin marketplace remove MARKET` for loadout's plugins; in repos, `.codex/config.toml` sections and `.agents/skills` links. Verify each against `codex.py` before writing.
  - `undo-and-restore.md`: backups hold `AGENTS.md` and `config.toml` copies; restore removes the Codex plugins and marketplaces loadout installed; fix line 48 so "plugins stay" is said for Claude Code only.
  - `troubleshooting.md`: Codex rows — hooks not approved (`/hooks`); project not trusted; "Serena is not available" (tools load on demand; ask by name); `AGENTS.override.md` shadows the block; plugin has no Codex route (marketplace not on GitHub).
  - `your-own-tools.md`: scan list per agent; the Codex-only adopt items (moved from codex.md); restart line per agent as `restart_hint()` prints.
  - `wsl.md`, `set-preferences.md`, `personal-repo.md`: agent-neutral wording; `CODEX_HOME` where `~/.claude` locations are listed; settings location per agent; state location links `architecture.md#loadouts-own-files`.
- [ ] **Step 4: Check the move table** — every row's destination contains the fact (`grep` a key phrase per row in its destination page). Ledger the result.
- [ ] **Step 5: Diff read, test, commit**

```bash
uv run --python 3.12 --with pytest pytest -q tests/test_docs_links.py
git add docs/how-to && git commit -m "docs(how-to): Codex in every how-to; codex.md keeps only Codex-only details"
```

---

### Task 7: Entry pages — README, docs map, tutorial, toolset

**Files:**
- Modify: `README.md`, `docs/README.md`, `docs/tutorials/getting-started.md`, `docs/explanation/the-toolset.md`, `docs/explanation/documentation-strategy.md`

- [ ] **Step 1: README.md**
  - Line 10 heading: `### Claude Code and Codex, fully set up in one command.`
  - Badge line 17: name both agents.
  - Demo caption 23-25: "The demo shows Claude Code; Codex gets the same setup."
  - Line 27: "merges both into your agents' configuration (`~/.claude`, `~/.codex`)".
  - Log in (31, 85): log in to the agents you chose (`claude`, `codex`), then `gh`.
  - Use it in a project (104): open your agent in the repo and run the onboard skill (`/loadout:onboard` in Claude Code; in Codex, ask for the loadout onboard skill / `$onboard` — verify the Codex skill invocation syntax with Context7 or `codex --help` docs before writing; if unsure, write "ask Codex to run the onboard skill").
  - What you get (110-118): both agents in the first bullet, Codex no longer a separate bullet.
  - Update model (114): per agent, as in architecture.md.
  - Line 121 "Claude plans": neutral ("plans").
  - Line 133 LSP: "type errors after each edit (LSP plugins in Claude Code, a type-check hook in Codex)".
  - Line 146 secrets: `${VAR}` for Claude Code, `env_vars` for Codex.
- [ ] **Step 2: docs/README.md** — map lines 16 and 40: both agents equal; codex.md described as "Codex-only details".
- [ ] **Step 3: getting-started.md**
  - Line 3: "to a first session in Claude Code or Codex".
  - "Before you start" row "After bootstrap": log in to your agents (`claude`, `codex`), then `gh`.
  - Windows step 1: Git Bash runs the hooks of both agents (verify Codex hooks use `shell: bash`: yes, `hooks/codex.json`).
  - "Log in": both agents.
  - New short step after "Log in" (Codex only): start `codex`, run `/hooks`, approve loadout's hooks.
  - "Verify": restart line per agent.
  - "Prepare a project": `init` writes for each agent on (table link to cli.md); Codex: start `codex` in the repo once and accept the trust question; onboard in either agent.
  - "What happens by itself": per agent, as in architecture.md.
- [ ] **Step 4: the-toolset.md** line 36 — `/code-review` is Claude Code's; name Codex's equivalent only if verified (Codex has `/review`: verify with Context7 `openai/codex` docs before writing; otherwise say "in Codex, ask for a review").
- [ ] **Step 5: documentation-strategy.md** lines 115, 121, 186 — "three skills" without "Claude Code"; onboard runs in either agent.
- [ ] **Step 6: Test, commit**

```bash
uv run --python 3.12 --with pytest pytest -q tests/test_docs_links.py
git add README.md docs && git commit -m "docs: README, docs map and getting started present Claude Code and Codex as equals"
```

---

### Task 8: AGENTS.md, CONTRIBUTING, manifests, demo text, rules, configure skill

**Files:**
- Modify: `AGENTS.md`, `CONTRIBUTING.md`, `.claude-plugin/marketplace.json`, `plugins/loadout/.claude-plugin/plugin.json`, `plugins/loadout/.codex-plugin/plugin.json`, `demo/loadout.tape`, `rules/tooling.md`, `rules/workflow.md`, `plugins/loadout/skills/configure/SKILL.md`

- [ ] **Step 1: AGENTS.md** — line 3: "A shareable setup for Claude Code and Codex: a plugin marketplace (kit) plus the `loadout` CLI that links rules, merges settings, configures Codex and manages per-project profiles." Hard conventions: "Never touch the real `~/.claude`, `~/.claude.json`, `~/.codex` or `~/.config/loadout`"; "never run real installers or mutating `claude` or `codex` commands". ADR range `0001-0024`. Map: add `.claude/skills/diagrams` (repo-local diagram skill, linked for Codex in `.agents/skills`).
- [ ] **Step 2: CONTRIBUTING.md** — bug report asks for `codex --version` when Codex is on; test isolation line names `~/.codex`; demo note "shows Claude Code"; diagrams section: one line "Agents: use the `diagrams` skill (`.claude/skills/diagrams`)".
- [ ] **Step 3: Manifests** — `marketplace.json` `metadata.description`: "A self-updating setup for Claude Code and Codex: …" (keep the rest). Make the two `plugin.json` descriptions the same sentence, agent-neutral (Claude one: drop nothing true; Codex one: drop "for Codex"; both mention the type check as "type errors after edits").
- [ ] **Step 4: demo/loadout.tape** — caption lines 3, 13, 20: "A reviewed setup for your coding agent" style; commands unchanged. Do not re-render the GIF (needs the demo container; note in the PR).
- [ ] **Step 5: rules** — `rules/tooling.md` "Type errors" row: "LSP plugins (Claude Code) or the type-check hook (Codex) report them after edits". `rules/workflow.md` review line: name Codex's review command only if verified in Task 7 Step 4, else "or ask your agent for a review".
- [ ] **Step 6: configure SKILL.md** line 44 — restart advice: "restart the agents that are on (Claude Code: or `/reload-plugins`)", matching `targets.restart_hint()`.
- [ ] **Step 7: Tests** — the configure evals' static checks and manifest tests must still pass:

```bash
uv run --python 3.12 --with pytest pytest -q
```
Expected: full suite PASS (the routing eval copies only the loadout row of `rules/tooling.md`; if `test_evals_static.py` pins row text, update the pin).

- [ ] **Step 8: Commit**

```bash
git add AGENTS.md CONTRIBUTING.md .claude-plugin plugins/loadout demo/loadout.tape rules
git commit -m "docs: agent-neutral manifests, rules and contributor notes"
```

---

### Task 9: ADRs

**Files:**
- Create: `docs/adr/0024-codex-parity-update-model.md`
- Modify: `docs/adr/0002-…`, `0006-…`, `0008-…`, `0015-…`, `0020-…`, `0022-…`, `docs/adr/README.md`

- [ ] **Step 1: ADR 0024** — follow the format of `0023-python-3-11-minimum.md` (read it first). Content:
  - Context: Codex became a second target (ADR 0022); several decisions were written for Claude Code only.
  - Decision: (1) for Codex, loadout itself installs and refreshes plugins and marketplaces, after a pull that brought commits and on `loadout update`, because Codex has no marketplace auto-update; (2) secrets reach Codex as `env_vars` names, since Codex does not expand `${VAR}`; (3) Codex gets type errors from the type-check hook, since it has no LSP plugins; (4) bootstrap installs only the chosen agents.
  - Consequences: restore removes Codex plugins it installed; a plugin from a marketplace not on GitHub has no Codex route; type checks run per edit with a 20 s limit.
- [ ] **Step 2: Status lines** — append to the Status section of 0002, 0006, 0008, 0015, 0020: `For Codex, see [ADR 0024](0024-codex-parity-update-model.md).` To 0022: `Project profiles and adopt for Codex shipped in #26; see also [ADR 0024](0024-codex-parity-update-model.md).`
- [ ] **Step 3: ADR index** — add 0024 to `docs/adr/README.md`.
- [ ] **Step 4: Test, commit**

```bash
uv run --python 3.12 --with pytest pytest -q tests/test_docs_links.py
git add docs/adr && git commit -m "docs(adr): 0024 Codex parity; status notes on decisions written for Claude Code"
```

---

### Task 10: Verify claims, anchors from code, docs audit

**Files:** whatever the checks find.

- [ ] **Step 1: Anchors printed by code** —
```bash
grep -rnoE "docs/[a-z/-]+\.md#[a-z0-9-]+" cli plugins rules bootstrap.sh bootstrap.ps1 | sort -u
```
For each, confirm the anchor exists (`python -c` with `tests/test_docs_links.anchors`, or grep the heading). Fix the docs or the string. Expected: all resolve.
- [ ] **Step 2: Full suite** — `uv run --python 3.12 --with pytest pytest -q > <workspace>/suite.txt; echo $?; tail -3 <workspace>/suite.txt`. Expected: exit 0.
- [ ] **Step 3: Final whole-branch review** (executing-plans), then the stand-in reviewer `.claude/agents/codex-reviewer.md` with the extra brief: "This PR changes docs. Find every doc claim the code in `cli/loadout/` or `plugins/loadout/hooks/` contradicts, and every Codex claim stated without the condition the code applies (Codex usable, new commits pulled, trusted project)." Fix P0-P2, loop until clean.
- [ ] **Step 4: `/loadout:docs-audit`** over the tree; fix its findings; commit `docs: fixes from the docs audit`.
- [ ] **Step 5: PR** — title `docs: Claude Code and Codex as equal targets (hardening 3)`; body lists the out-of-scope items (state location, Codex demo, kit diagram skill) and the not re-rendered demo GIF.
