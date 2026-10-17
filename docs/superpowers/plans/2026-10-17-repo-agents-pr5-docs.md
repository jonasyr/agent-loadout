# Repo-agents PR 5 (docs and the full docs audit) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The walkthrough "Codex only on Windows with VS Code" in `setups.md` and the agent page, the pages it touches brought in line, and the full docs audit of Part 7 on the finished branch, with its findings fixed.

**Architecture:** Docs only, plus two tests that pin what the docs promise: every `loadout …` command on the agent-facing pages parses with the real CLI parser, and the two walkthrough copies list the same steps in the same order. The audit follows the `loadout:docs-audit` skill's steps (inventory, claims, verify, ask, fix, validate) with its checklist in `.loadout/docs-audit/`; findings are fixed per layer.

**Tech Stack:** Markdown docs; pytest (`uv run --python 3.12 --with pytest pytest -q`); `claude plugin validate`.

**Spec:** `docs/superpowers/specs/2026-10-16-repo-agents-and-careful-ux-design.md` (Part 4 walkthrough, Part 7, PR 5). The live tour (Part 5, last bullet) is **not** in this PR: the user deferred it.

## Global Constraints

- One home per fact: edit `docs/`, link from elsewhere (`rules/docs-policy.md`, `docs/explanation/documentation-strategy.md`).
- Walkthrough steps, same in both pages and in this order: "WSL 2, bootstrap (side, VS Code switch), `codex login` in WSL, `/hooks`, the first repo (`loadout init --agents codex`), `loadout check`."
- "The agent page (`install-with-an-agent.md`) and the configure skill are read as an agent would: every command in them runs as written on the platforms they name."
- "Each fact has one home; links and anchors resolve; no page states the old model. The audit's findings are fixed in PR 5, and the PR lists the pages it checked."
- Audit scope: "README, the tutorial, every how-to, reference, explanation (architecture, security and trust, documentation strategy), the ADR index (0027 marked as partly superseded by 0030), `AGENTS.md`'s map, the plugin's skills (configure, onboard, docs-sync, docs-audit) and the Serena memories."
- Conventional Commits (`docs: …`, `test: …`), no AI attribution. Never commit `docs/examples/Niklas_Serena_Config.md` (the user's untracked file in the main checkout; it is not in this worktree).
- Tests never touch the real `~/.claude`, `~/.codex`, `~/.config/loadout`; no real installers.

## Review Focus

1. A command on the agent page that an agent copies with placeholders filled (`--agents codex`, `--codex-side wsl`, `--vscode-wsl`) must parse; a renamed or removed flag must fail the test, not ship.
2. The walkthrough in `setups.md` and the agent page drifting apart (a step added to one only) must fail the test.
3. `/hooks` in the VS Code extension is not verified (live tour deferred): the walkthrough must name the path known to work (`codex` in the WSL terminal, `/hooks`) and not claim the extension offers it.
4. A page that still states the old model (repo files follow the user's agents, the profile wins, no repo backup, restore needs a copied path) must be found by the audit's grep pass, not only by reading.
5. Anchors renamed by the walkthrough headings must not break links from other pages (`test_docs_links.py`).

---

### Task 1: Commands on agent-facing pages parse

**Files:**
- Create: `tests/test_docs_commands.py`
- Modify (only if the test finds a broken command): `docs/how-to/install-with-an-agent.md`, `docs/how-to/setups.md`, `plugins/loadout/skills/configure/SKILL.md`

**Interfaces:**
- Produces: `commands_in(path) -> list[str]` and `PAGES` in `tests/test_docs_commands.py`; Task 2 adds no new pages to `PAGES` (both walkthrough pages are already in it).

- [ ] **Step 1: Write the test**

```python
"""Every `loadout …` command on the pages an agent follows parses with the real CLI parser (spec Part 7)."""
import re
import shlex
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGES = [ROOT / "docs/how-to/install-with-an-agent.md", ROOT / "docs/how-to/setups.md",
         ROOT / "plugins/loadout/skills/configure/SKILL.md"]
FENCE = re.compile(r"^```[^\n]*\n(.*?)^```", re.S | re.M)
SPAN = re.compile(r"`(loadout [^`\n]+)`")
FILL = {"<list>": "codex", "<new|URL>": "new", "<URL>": "https://example.invalid/me.git",
        "<the mktemp path>": "/tmp/answers.json", "<the agreed groups>": "settings",
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
        if not argv or argv[0].startswith("<"):
            continue
        try:
            build_parser().parse_args(argv)
        except SystemExit as exc:
            if exc.code:
                bad.append(command)
    assert not bad, "\n".join(bad)


def test_the_pages_have_commands():
    assert all(commands_in(p) for p in PAGES)
```

- [ ] **Step 2: Run it**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_docs_commands.py`
Expected: PASS, or FAIL listing commands that do not parse. A failing command is either a doc bug (fix the page) or a placeholder the `FILL` map lacks (add it; ledger a ruling naming it). To see the test catch a real break, temporarily change `--codex-side wsl` to `--codex-sides wsl` in the agent page, run, watch it FAIL, and revert.

- [ ] **Step 3: Commit**

```bash
git add tests/test_docs_commands.py docs plugins
git commit -m "test(docs): every loadout command on the agent-facing pages parses"
```

### Task 2: The walkthrough "Codex only on Windows with VS Code"

**Files:**
- Modify: `docs/how-to/setups.md` (new section after "Starting point", before "Afterwards")
- Modify: `docs/how-to/install-with-an-agent.md` (new section after "6. Finish")
- Modify: `tests/test_docs_commands.py` (walkthrough test)
- Read for facts: `docs/how-to/wsl.md`, `docs/how-to/codex.md`, `cli/loadout/bootstrap.py` (`_vscode_step`, `VSCODE_FLAG_HINT`), `cli/loadout/check.py` (`_vscode`)

**Interfaces:**
- Consumes: `commands_in` from Task 1.
- Produces: heading `## Codex only on Windows with VS Code` in both pages (anchor `codex-only-on-windows-with-vs-code`), each with a numbered list of six steps.

- [ ] **Step 1: Write the failing test** (append to `tests/test_docs_commands.py`)

```python
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
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_docs_commands.py -k walkthrough`
Expected: FAIL with `AssertionError: setups.md` (heading missing).

- [ ] **Step 3: Write the section in `setups.md`**

Insert before `## Afterwards`:

```markdown
## Codex only on Windows with VS Code

OpenAI's recommended setup ([Codex on Windows](https://learn.chatgpt.com/docs/windows/wsl)): Codex and loadout in WSL, repos in the Linux home, VS Code opened from WSL. The same steps, for an agent, are in [Set loadout up from inside an agent](install-with-an-agent.md#codex-only-on-windows-with-vs-code).

1. **WSL 2.** In PowerShell, `wsl -l -v` shows version 2 ([WSL 2](wsl.md#1-use-wsl-2-not-wsl-1)). Open the WSL terminal and work in the Linux home.
2. **bootstrap** inside WSL: `./bootstrap.sh --install --agents codex` in the clone. In a terminal it asks which side Codex runs on when it finds only the Windows one (answer WSL) and offers the VS Code switch (`chatgpt.runCodexInWindowsSubsystemForLinux`, with a backup). Without a terminal add `--codex-side wsl --vscode-wsl` ([which side](wsl.md#when-your-only-codex-is-the-windows-one)).
3. **`codex login`** in the WSL terminal.
4. **`/hooks`:** start `codex` in the WSL terminal and approve loadout's hooks once ([Use loadout with Codex](codex.md#switch-it-on)).
5. **The first repo**, in the Linux home: `loadout init --agents codex`, then `code .` to open it in VS Code. Start `codex` there once and accept the trust question ([Project trust](codex.md#project-trust)).
6. **`loadout check`:** each `warn` line names its fix; the `VS Code` row warns while the extension still runs the Windows Codex.
```

- [ ] **Step 4: Write the section in `install-with-an-agent.md`**

Append after section 6:

```markdown
## Codex only on Windows with VS Code

When the user is in WSL and chose Codex only, follow these steps in this order; they are the same as in [Find the path for your setup](setups.md#codex-only-on-windows-with-vs-code). Show each command and run it after a yes, as above.

1. **WSL 2:** step 1 printed `WSL`. If the user is not sure it is WSL 2, they run `wsl -l -v` in PowerShell ([WSL 2](wsl.md#1-use-wsl-2-not-wsl-1)).
2. **bootstrap:** `~/agent-loadout/bootstrap.sh --install --agents codex --codex-side wsl --vscode-wsl </dev/null` (or `loadout bootstrap --install --agents codex --codex-side wsl --vscode-wsl </dev/null` when loadout is installed). Ask before adding `--vscode-wsl`: it sets one VS Code setting, with a backup.
3. **`codex login`:** the user types it in the WSL terminal.
4. **`/hooks`:** the user starts `codex` in the WSL terminal and approves loadout's hooks once.
5. **The first repo:** in a repo in the Linux home, `loadout init --dry-run --agents codex </dev/null`, show the plan, then `loadout init --yes --agents codex </dev/null` after a yes. The user opens it with `code .` and accepts Codex's trust question once.
6. **`loadout check`:** give the fix for each `warn` or `FAIL` line in one line.
```

- [ ] **Step 5: Run the docs tests**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_docs_commands.py tests/test_docs_links.py`
Expected: PASS (walkthrough test, commands parse, anchors `#1-use-wsl-2-not-wsl-1`, `#when-your-only-codex-is-the-windows-one`, `#switch-it-on`, `#project-trust`, `#codex-only-on-windows-with-vs-code` resolve). If an anchor does not resolve, use the heading slug `test_docs_links.anchors` computes.

- [ ] **Step 6: Point the WSL page and the README at it**

In `docs/how-to/wsl.md` section "2. Install loadout inside WSL", add one sentence: `With Codex only and VS Code, follow [Codex only on Windows with VS Code](setups.md#codex-only-on-windows-with-vs-code).` Check `README.md`'s install section; if it lists setups, add the same link there in one line, otherwise leave README alone.

- [ ] **Step 7: Commit**

```bash
git add docs tests/test_docs_commands.py
git commit -m "docs(setups): walkthrough Codex only on Windows with VS Code, in setups and the agent page"
```

### Task 3: Full docs audit (Part 7): inventory, claims, verification

**Files:**
- Create: `.loadout/docs-audit/2026-10-17.md` (checklist, git-ignored; `.loadout/` must be in `.gitignore`: check with `git check-ignore .loadout/x`)
- Read: every file in the scope line of Global Constraints, plus `docs/how-to/*.md`, `docs/reference/*.md`, `docs/explanation/*.md`, `docs/tutorials/*.md`, `docs/README.md`, `CONTRIBUTING.md`, `.serena/memories/*.md`, `plugins/loadout/skills/{configure,onboard,docs-sync,docs-audit}/SKILL.md`

**Interfaces:**
- Produces: the checklist with one row per page (size, claims checked, findings with file:line and classification), consumed by Task 4.

- [ ] **Step 1: Inventory.** Write the checklist header and one unchecked row per artifact with its size (`wc -c`).

- [ ] **Step 2: Old-model grep pass.** Run and record every hit with its file:line and whether it is stale:

```bash
grep -rn -i -E "profile wins|deep.?merge|agents that are on|follow(s)? the (user's|agents)|no backup|not undo|restore --list|copy (the|a) path|--dry-run.*(omit|without).*settings" README.md AGENTS.md CONTRIBUTING.md docs plugins/loadout/skills .serena/memories --include=*.md | grep -v "docs/superpowers/\|docs/adr/00[0-2]"
```

Expected: each hit either describes the new model correctly (note "correct") or is stale (a finding). Old ADRs (0001–0029) are history and are not findings, except their status lines.

- [ ] **Step 3: Verify claims in parallel.** Dispatch Explore subagents (read-only), one per area: (a) README, tutorial, docs/README, CONTRIBUTING; (b) how-to pages; (c) reference pages (cli.md flags and exit codes against `commands.py`/`__main__.py`, profile-format against `profiles.py`/`repo_merge.py`, hooks, personal-layer); (d) explanation pages and ADR index status lines; (e) AGENTS.md map against `ls cli/loadout`, the four skills, Serena memories. Each gets: the rules of the docs-audit skill step 3 (classification `correct|stale|wrong|unclear|contradictory|duplicated|misplaced|unverifiable`, quote the code that settles a claim, harmless commands only) and must return findings as `file:line — classification — claim — evidence — proposed fix`. Also ask (c) for missing docs: a CLI flag or subcommand no reference page names.

- [ ] **Step 4: Add the known doc minors from the backlog** (`.superpowers/handoff/2026-10-13-hardening-backlog.md`, PR 1–4 deferred minors that are docs): `security-and-trust` cites `project._install`; cli.md `.loadout.json` paragraph order and `explain` exit codes; ADR 0031 "behaves as one without a record" wording (status note only, never the decision); `.loadout.json` reason on stdout; setups.md/cli.md nits from PR 3. Verify each against the code before keeping it.

- [ ] **Step 5: Record and sort.** Write every finding into the checklist. Questions only the user can answer (intent, contradictions the code cannot settle) are collected for the one batch in Task 4 step 1.

No commit (the checklist is git-ignored).

### Task 4: Fix the audit's findings, validate, list the pages

**Files:**
- Modify: whichever pages Task 3 found (expected among the scope pages), `AGENTS.md` map if it is wrong, `.serena/memories/*` if a summary or link is wrong
- Modify: `docs/superpowers/plans/2026-10-16-repo-agents-docs-baseline.md` (add `Full audit: PR 5` with the list of pages checked)

**Interfaces:**
- Consumes: the checklist from Task 3.

- [ ] **Step 1: Ask the user** the collected questions in one batch (multiple choice, at most four). If there are none, write `no open questions` in the checklist. This is one of the executor's stops: wait for the answers.

- [ ] **Step 2: Fix per layer.** Apply each finding's fix in its owning page; facts move to their one home and the other places link. Never edit an accepted ADR's decision; status lines only. Commit per layer:

```bash
git add docs README.md CONTRIBUTING.md && git commit -m "docs: full audit after the repo-agents change"
git add AGENTS.md && git commit -m "docs(agents): map matches the modules and pages"          # only if changed
git add plugins/loadout/skills && git commit -m "docs(skills): skills match the CLI"          # only if changed
git add .serena/memories && git commit -m "docs(memories): summaries link the current pages"  # only if changed
```

- [ ] **Step 3: Validate.**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_docs_links.py tests/test_docs_commands.py tests/test_readme.py tests/test_docs_guide_skills.py tests/test_skills.py`
Expected: PASS.
Re-run the grep from Task 3 step 2. Expected: no stale hit left.
Run: `claude plugin validate . && claude plugin validate plugins/loadout`
Expected: both pass.
Run: `uv run --python 3.12 --with pytest pytest -q`
Expected: all pass (2588 + the new tests).

- [ ] **Step 4: Record the checked pages.** In the docs baseline file add a section `## Full audit (PR 5)` listing every page checked and the number of findings fixed per page; this list also goes into the PR description. Delete `.loadout/docs-audit/2026-10-17.md` once the PR description holds the list.

```bash
git add docs/superpowers/plans/2026-10-16-repo-agents-docs-baseline.md
git commit -m "docs(plans): pages the PR 5 audit checked"
```
