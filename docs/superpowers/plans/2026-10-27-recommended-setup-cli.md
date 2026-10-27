# Recommended Setup in the CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `loadout check` and every `bootstrap` name this machine's setup cell and its recommended flags from the setup matrix, and bootstrap names the differences from that recommendation without asking anything.

**Architecture:** A new read-only module `cli/loadout/recommend.py` detects the cell (platform, chosen agents, surface, Codex side), holds the recommended flags per cell (a code mirror of `docs/reference/setup-matrix.md`, pinned by a test), and lists the differences. `check.run_checks` gets a first `Setup` row that carries the cell as info. `bootstrap._bootstrap` prints a "This machine" block after the Codex gate and before `Prerequisites`.

**Tech Stack:** Python 3.11+ standard library, pytest with `fake_home`/`fake_runner`.

**Spec:** `docs/superpowers/specs/2026-10-27-recommended-setup-cli-design.md`

**Code navigation:** Use codebase-memory (project `home-jonas-Documents-Code-agent-loadout`: `search_graph`, `get_code_snippet`, `trace_path`) and Serena (`find_symbol`, `find_referencing_symbols`) before grep.

## Global Constraints

- Standard-library Python only in `cli/loadout/`. Tests use `fake_home` and `fake_runner`, never the real home, and never real `claude`, `codex` or installers.
- Nothing reads files or VS Code extensions of an agent that is off. The only signal used about an agent that is off is `runner.have("codex")` (PATH), for difference (c).
- No new question, and no wait on input. The exit code of `bootstrap` and of `check` does not change because of the new text.
- The `Setup` row is always `ok`. It never warns or fails, and it does not repeat the warnings of existing rows.
- `docs/reference/setup-matrix.md` stays the human home. The code table mirrors it, and a test fails when they drift.
- Conventional Commits, no AI attribution.

## Review Focus

1. WSL with Codex on and the only Codex on Windows (`cs.side == "windows"`): the cell uses the "Codex on Windows, or on both sides" table, and no WSL Codex home is read. Test: `test_cell_wsl_codex_windows_side` (Task 1).
2. Codex off while a Windows VS Code Codex extension exists in WSL: `vscode.extensions` is called with `codex: False`, and the cell says nothing about Codex. Test: `test_codex_off_reads_no_codex_extension` (Task 1).
3. `loadout check` in calm mode (`format_summary`) shows the Setup line even when every row is ok. Test: `test_summary_shows_setup_line` (Task 2).
4. A non-interactive bootstrap (`--yes`, no terminal) prints the block and never calls `ask`. Test: `test_block_never_asks` (Task 3).
5. Native Windows: the cell says "experimental", uses the Linux flags and links `#native-windows-experimental`. Test: `test_cell_native_windows` (Task 1).

---

### Task 1: `recommend.py`: cell, flags, differences, matrix pin

**Files:**
- Create: `cli/loadout/recommend.py`
- Test: `tests/test_recommend.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Cell`, with these fields:
    - `platform: str`, one of `"linux"`, `"macos"`, `"wsl"`, `"windows"`;
    - `agents: tuple[str, ...]`: `("claude",)`, `("codex",)` or `("claude", "codex")`;
    - `surface: str`, one of `"cli"`, `"vscode"`, `"vscode+cli"`, `"windows-window"` (WSL only: an extension in a Windows window and no Remote-WSL one), `"none"`;
    - `codex_side: str | None`: `"windows"` or `"both"` in WSL with Codex on and that side, else `None`.
  - `detect(chosen: dict[str, bool], cs=None, codex_windows: bool = False, found: list | None = None) -> Cell`:
    - `chosen` is `{"claude": bool, "codex": bool}`;
    - `cs` is a `wsl.CodexSide` or `None`;
    - `codex_windows=True` forces `codex_side="windows"`, matching the bootstrap gate;
    - `found` holds pre-read `vscode.extensions` results; when `None`, it calls `vscode.extensions(chosen, win_home=getattr(cs, "windows_home", None), look=cs is None)`.
  - `describe(cell: Cell) -> str`: one line, for example `WSL 2 · Claude Code + Codex · CLI`. Native Windows carries `(experimental)`, and `"none"` reads `no CLI or VS Code extension found yet`.
  - `flags(cell: Cell) -> str`: the recommended bootstrap flags, for example `--install --agents claude,codex`.
  - `anchor(cell: Cell) -> str`: for example `docs/reference/setup-matrix.md#wsl-2`.
  - `differences(cell: Cell, chosen: dict[str, bool], install: bool, missing: list[str], vscode_wsl: bool, codex_cli: bool) -> list[str]`: one line per difference (a) to (d) from the spec.
  - `FLAGS: dict[tuple[str, str, str], tuple[str, ...]]`, keyed `(table, row, column)`. The value is the matrix cell's code spans that start with `--`, in order; `flags()` joins them with a space:
    - table: `"linux-macos"`, `"wsl"` or `"codex-windows"`;
    - row: the matrix row's first cell, verbatim, for example `"CLI only"`, `"VS Code extension"`, `"VS Code extension + CLI (optional)"`, `"A Windows window anyway (not recommended)"`, `"On Windows only"`, `"On both sides"`;
    - column: `"Claude Code"`, `"Codex"` or `"Both"`.
    - Rows whose cell says "As in the row above" carry the row above's flags.
    - Cells with no `--` code span are not in `FLAGS`: the Claude Code cells of the `codex-windows` table ("Not affected") and the Claude Code cell of the Windows-window row. For those, `detect` and `flags` fall back as follows: a Claude-only cell in WSL uses the `wsl` table; the Windows-window row's Claude Code column uses the `"VS Code extension"` row.

- [ ] **Step 1: Write the failing tests**

```python
from loadout import recommend, wsl
from loadout.recommend import Cell

BOTH = {"claude": True, "codex": True}

def test_matrix_pins_every_flag():  # FLAGS equals the `--` code spans of each matrix cell (row above resolved)
    for key in recommend.matrix_keys():
        assert recommend.FLAGS[key] == recommend.matrix_flags(key), key

def test_every_matrix_cell_has_flags():  # matrix_keys(): every cell with a `--` span; none missing, none extra
    assert set(recommend.matrix_keys()) == set(recommend.FLAGS)

def test_cell_linux_cli(fake_home, fake_runner, monkeypatch):
    monkeypatch.setattr(wsl, "detect", lambda: None)
    fake_runner.binaries = {"claude", "codex"}   # use the fixture's real attribute for binaries on PATH
    cell = recommend.detect(BOTH, found=[])
    assert cell == Cell("linux", ("claude", "codex"), "cli", None)
    assert recommend.flags(cell) == "--install --agents claude,codex"
    assert recommend.anchor(cell).endswith("#linux-and-macos")

def test_cell_none_falls_back_to_cli_row(...):  # no CLI, no extension
    # surface "none", flags of the "CLI only" row; describe() says "no CLI or VS Code extension found yet"

def test_cell_wsl_codex_windows_side(...):  # cs.side == "windows", agents both -> table "codex-windows", row "On Windows only"
    # flags(cell) == "--install --agents claude,codex --codex-side windows"

def test_codex_windows_override(...):  # cs.side == "wsl" but codex_windows=True -> codex_side "windows"

def test_codex_off_reads_no_codex_extension(...):  # spy on vscode.extensions: called with on["codex"] is False

def test_cell_native_windows(...):  # paths.platform_key() == "windows": describe has "(experimental)", flags as linux, anchor "#native-windows-experimental"

def test_differences(...):
    # (a) install=False, missing=["serena"] -> a line naming --install
    # (b) WSL, codex chosen, surface "windows-window" for codex, vscode_wsl=False -> a line naming --vscode-wsl
    # (c) chosen codex False, runner.have("codex") True -> a line saying a Codex CLI is on PATH but Codex is not chosen
    # (d) codex_cli=False and runner.have("codex") True -> a line naming --without-codex-cli
    # nothing differs -> []
```

Fill the placeholder bodies with the commented assertions, using the fixture's real API (read `tests/conftest.py`: `fake_runner.have`).

- [ ] **Step 2: Run, and expect a FAIL with an ImportError on `recommend`**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_recommend.py`

- [ ] **Step 3: Implement `cli/loadout/recommend.py`**

How the pieces work:
- **Platform:** `bootstrap.os_key()`, with `"wsl"` when `wsl.detect() == 2`. Import lazily, as the other modules do.
- **Surface:**
  - Take the union over the agents that are on: CLI = `runner.have(agent)`; extension = any `found` entry for that agent.
  - In WSL, extensions only in a Windows window (`install.where == "windows"` and not `vscode.runs_in_wsl(e)`) give `"windows-window"`.
- **Matrix helpers:** `matrix_flags(key) -> tuple[str, ...]` (the cell's `--` code spans) and `matrix_keys() -> list[tuple]` (the cells that have any). They parse the three tables under the headings `## Linux and macOS`, `## WSL 2` and `### Codex on Windows, or on both sides` in `paths.kit_root() / "docs/reference/setup-matrix.md"`.
  - "As in the row above" resolves to that row's cell.
  - These helpers are used only by tests and need no caching.
- **Row choice, `codex-windows` table:** the row is chosen by `codex_side`, and the column by the agents. The Claude Code column of that table holds no flags, so a Claude-only cell never uses that table.

- [ ] **Step 4: Run, and expect a PASS**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_recommend.py`

- [ ] **Step 5: Commit**

```bash
git add cli/loadout/recommend.py tests/test_recommend.py
git commit -m "feat(recommend): detect the setup cell and its recommended flags"
```

### Task 2: the `Setup` row in `loadout check`

**Files:**
- Modify: `cli/loadout/check.py`: `CheckResult`, `run_checks`, `format_results`, `format_summary`
- Modify: `docs/how-to/troubleshooting.md` and `docs/reference/cli.md`, the `loadout check` section
- Test: `tests/test_check_setup_row.py`; also keep `tests/test_names_checked.py` green

**Interfaces:**
- Consumes: `recommend.detect`, `recommend.describe`, `recommend.anchor` (Task 1).
- Produces:
  - `CheckResult.info: str = ""`, a new trailing field;
  - `check._setup(cs, codex_windows: bool) -> list[CheckResult]`, which returns `[CheckResult("Setup", True, info=f"{describe} — {anchor}")]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_setup_row_is_first_and_ok(...):  # run_checks()[0].name == "Setup", .ok is True, "·" in .info
def test_results_show_setup_info(...):    # format_results: "[ok  ] Setup: <info>" line
def test_summary_shows_setup_line(...):   # format_summary with every row ok: second line is "Setup: <info>"; exit code 0
def test_setup_row_never_fails(...):      # recommend.detect raising -> the row is still ok, info "unknown"; check does not crash
```

- [ ] **Step 2: Run, and expect a FAIL**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_check_setup_row.py`

- [ ] **Step 3: Implement**

- `_setup` goes first in `run_checks` and takes the same `cs` as the other rows, with `codex_windows` passed through. It wraps detection in `try/except Exception`, so an informational row can never break check.
- `format_results` appends `: {info}` to an ok row that has info.
- `format_summary` prints each info row's `"{name}: {info}"` line after the head line, so the count line stays first.
- The new row is counted in `N of M OK`.
- Docs:
  - add a `Setup` entry to troubleshooting: what it shows, no fix needed, and a pointer to the matrix;
  - add one sentence to the `loadout check` section of cli.md;
  - update `test_names_checked.py`'s expectations if it lists row names.

- [ ] **Step 4: Run, and expect a PASS, and run the full suite**

Run: `uv run --python 3.12 --with pytest pytest -q --deselect "tests/test_docs_links.py::test_links_resolve[docs/examples/Niklas_Serena_Config.md]"`
Expected: all pass. Existing check and bootstrap tests that index `run_checks()[0]` or count rows are fixed to the new first row; each such change is deliberate, so note it in the commit body.

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(check): a Setup row names this machine's cell and its matrix section"
```

### Task 3: the "This machine" block in `bootstrap`

**Files:**
- Modify: `cli/loadout/bootstrap.py`: `_bootstrap`, between the Codex gate and `_step("Prerequisites")`
- Modify: `docs/how-to/setups.md#recommended-setups` (one sentence), and `docs/tutorials/getting-started.md` only if it shows bootstrap's output
- Test: `tests/test_bootstrap_this_machine.py`

**Interfaces:**
- Consumes:
  - `recommend.detect(chosen, cs, codex_windows=gate is not None and WINDOWS_WAY in gate)`;
  - `recommend.describe`, `flags`, `anchor`, `differences` (Task 1);
  - `missing_tools(skip, recommended)` from bootstrap: required names are `[e["id"] for e, _cmds, optional in ... if not optional]`.
- Produces: `_this_machine(chosen, gate, install, vscode_wsl, codex_cli) -> None`, which prints and returns nothing.

- [ ] **Step 1: Write the failing tests**

```python
def test_block_shows_cell_and_flags(...):   # capsys: "This machine" status line with describe(); a line "recommended: <flags>" and the anchor; calm mode too
def test_block_names_differences(...):      # install=False with a missing required tool -> the (a) line in the output
def test_block_never_asks(...):              # non-interactive bootstrap with an ask that raises: the run completes, exit code as before
def test_block_on_every_run(...):           # an existing personal layer (not fresh): the block still shows
```

Follow the setup of `tests/test_bootstrap_calm.py` for a full `_bootstrap` run under `fake_home`/`fake_runner`.

- [ ] **Step 2: Run, and expect a FAIL**

Run: `uv run --python 3.12 --with pytest pytest -q tests/test_bootstrap_this_machine.py`

- [ ] **Step 3: Implement `_this_machine`**

- Call it right after the gate.
- Print through `_step("This machine")` and `out.status("This machine", describe(cell))`. The recommended line and each difference go through `out.problem`, or another output call that calm mode shows (check `out.py`; `out.detail` is verbose-only).
- For surface `"none"`, add the line `using VS Code? see <anchor>`.
- Wrap the whole thing in `try/except Exception`, so a detection error never stops bootstrap.
- Docs: in setups.md, one sentence that `loadout check` (the `Setup` row) and every bootstrap run name your cell and its recommended flags.

- [ ] **Step 4: Run the new tests and the full suite, and expect a PASS**

Run: `uv run --python 3.12 --with pytest pytest -q --deselect "tests/test_docs_links.py::test_links_resolve[docs/examples/Niklas_Serena_Config.md]"`

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(bootstrap): show this machine's cell, recommended flags and differences"
```
