# Use loadout's Serena ("start clean") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a person replace their own Serena server with loadout's during setup (Codex included, also on Codex-only machines), safely and undoably, and stop `--yes` from silently removing a tuned Claude Code Serena.

**Architecture:** No new module. `inventory.classify` gains a `use_loadout` mode that turns an own Codex Serena table into an adopt verdict (as `_codex_cbm_verdicts` does for codebase-memory). `adopt` gets a Serena-only pass that bootstrap runs after the plugin install and before `codex_step`, with guards (replacement present first) and a rollback when loadout's Codex table was not written. ADR 0045 keeps a tuned Claude Code Serena on `--yes`, in the style of ADR 0041.

**Tech Stack:** Python 3.11+ standard library; pytest with `fake_home` / `fake_runner`.

**Spec:** `docs/superpowers/specs/2026-10-31-start-clean-design.md` (user decisions 2026-10-31: Enter = decide later; ADR 0045 goes in). Code facts verified 2026-11-02 against main 660f55a; the spec's line numbers are older.

## Global Constraints

- Every removal is backed up before it acts; `loadout restore` brings it back (Claude: `Backup.record_mcp_add`, config in a 0600 file; Codex: `codex.remove_server` saves `config.toml` first).
- An agent that is off in `targets.json`: nothing of it is read or asked (P1).
- External commands only through `runner.run` with argument lists.
- Output never prints a server's env or headers values (`redact`; the Claude config stays in its file).
- Never end a run without a working Serena silently: rollback or a printed line with the backup path.
- Flag names: `--use-loadout` and `--keep-own` on `bootstrap` and `adopt --apply`; both together → exit 2 with a message.
- Question text (terminal, Codex):
  ```
  Serena: yours (Codex config.toml "NAME") runs next to loadout's.
  Use loadout's and remove yours? Backed up; `loadout restore` brings it back.
  [y] use loadout's (recommended)  [n] keep mine, don't ask again  Enter: decide later
  ```
- Tests use `fake_home` and `fake_runner`; Conventional Commits.

## Calls made while planning (not in the spec; the user sees these with the plan)

1. One question per server: interactively the pass asks only about the **Codex** Serena; a plain Claude Code Serena stays with adopt's existing `migrate` group (Enter there removes it, as today). The pass acts on a Claude Code Serena only under `--use-loadout`. Reason: two questions about one server, with opposite Enter defaults, would contradict each other.
2. A tuned Serena (own settings) is never removed by `--use-loadout`; it is kept with a reason that names `loadout adopt --apply --own NAME=remove` (the ADR 0041 pattern). The spec's "typed `y`" for tuned ones is that command.
3. A "plain duplicate" compares command basename `serena` (or `serena.exe`), the argument **set** against loadout's for that agent, and no keys beyond `command`, `args`, `type`, `enabled`, `alwaysLoad`, `startup_timeout_sec`, `env` only when empty. Anything else is own settings (fail closed).

## Review Focus

1. A Codex `config.toml` whose Serena table has comments or a `[mcp_servers.NAME.env]` sub-table: rollback puts back exactly the removed text, sub-tables included.
2. `codex_step` not run in the same bootstrap (Codex unavailable, gate stops it) after the pass removed the table: rollback happens, the run says so.
3. A remembered leave (`own-decisions.json`) beats `--use-loadout`: nothing removed, one "kept (you chose leave)" line.
4. Codex on, Claude Code off (Codex-only machine): the pass runs; nothing under `~/.claude*` is read.
5. VS Code's Codex extension without the CLI: `codex.remove_server` runs the extension's codex (`codex.program()`); the pass works the same.

---

### Task 1: ADR 0045, a tuned Claude Code Serena is kept on `--yes`

**Files:**
- Modify: `cli/loadout/codex.py` (new `serena_has_own_settings`, next to `cbm_has_own_settings` ~:548), `cli/loadout/inventory.py:216-237` (Serena branch next to the ADR 0041 cbm branch; reason constant next to `CBM_OWN_CLAUDE` :247-253)
- Create: `docs/adr/0045-a-tuned-serena-is-kept.md`
- Test: `tests/test_inventory.py`

**Interfaces:**
- Produces: `codex.serena_has_own_settings(cfg: dict, agent: str) -> bool` (agent "claude" compares against `plugins/loadout/.mcp.json`'s serena args `["start-mcp-server","--context=claude-code","--project-from-cwd"]`; "codex" against `codex.SERENA["args"]`); `inventory.SERENA_OWN_CLAUDE: str` (contains `loadout adopt --apply --own NAME=remove` with the real name filled in at verdict time, or the literal `NAME` form if the constant is static: pick the static form `"... remove it with: loadout adopt --apply --own <name>=remove"` and format the name in).

- [ ] **Step 1: Failing tests**

```python
def test_a_plain_claude_serena_still_migrates(machine):  # the author fixture's serena is plain
    v = {x.item.name: x for x in inventory.classify(inventory.collect(with_versions=False))}
    assert v["serena"].action == "migrate"


@pytest.mark.parametrize("cfg", [
    {"command": "serena", "args": ["start-mcp-server", "--context=ide", "--project-from-cwd"]},
    {"command": "serena", "args": ["start-mcp-server", "--context=claude-code", "--project-from-cwd"],
     "env": {"SERENA_LOG": "debug"}},
    {"command": "/opt/fork/serena", "args": ["start-mcp-server", "--context=claude-code", "--project-from-cwd", "--x"]},
])
def test_a_tuned_claude_serena_is_kept(fake_home, fake_runner, cfg):
    (fake_home / ".claude.json").write_text(json.dumps({"mcpServers": {"serena": cfg}}))
    v = {x.item.name: x for x in inventory.classify(inventory.collect(with_versions=False))}
    assert v["serena"].action == "keep"
    assert "loadout adopt --apply --own serena=remove" in v["serena"].reason


def test_arg_order_and_type_do_not_count_as_own_settings():
    cfg = {"type": "stdio", "command": "serena", "args": ["start-mcp-server", "--project-from-cwd", "--context=claude-code"],
           "env": {}}
    assert not codex.serena_has_own_settings(cfg, "claude")
```

(Use the file's existing imports/fixtures: `machine` as in `tests/test_adopt.py:10-12`.)

- [ ] **Step 2: Run** `uv run --python 3.12 --with pytest pytest -q tests/test_inventory.py -k serena` — Expected: the tuned cases FAIL (migrate).
- [ ] **Step 3: Implement** the helper and the branch: `if isinstance(cfg, dict) and codex.is_serena(cfg) and codex.serena_has_own_settings(cfg, "claude")` → `Verdict(item, "keep", SERENA_OWN_CLAUDE.format(name=item.name), "mcp-serena")`; plain ones fall through to the catalog match (migrate) as today.
- [ ] **Step 4: Write ADR 0045** (format of `docs/adr/0041-*.md`): context (tuned forks went silently on `--yes`), decision (own settings → keep; plain → migrate; removal of a tuned one only by `--own NAME=remove`), amends 0016 and 0028, consequences.
- [ ] **Step 5: Run** `... pytest -q tests/test_inventory.py tests/test_adopt.py` — Expected: PASS.
- [ ] **Step 6: Commit** `feat(adopt): keep a Serena with its own settings on --yes (ADR 0045)`

### Task 2: `use_loadout` mode: an own Codex Serena becomes an adopt verdict

**Files:**
- Modify: `cli/loadout/inventory.py` (`classify(items, use_loadout: bool = False)` :168; new `_codex_serena_verdicts()` modelled on `_codex_cbm_verdicts` :256-280; called at the `return` :244 only when `use_loadout`)
- Test: `tests/test_codex_adopt.py` (fixtures `codex_on` :11-14, `_config` :17-21)

**Interfaces:**
- Consumes: `codex.serena_has_own_settings(cfg, "codex")` (Task 1), `codex.user_serena(data, owned)` / `codex.read_record()`.
- Produces: `inventory.classify(items, use_loadout=False)`; Codex Serena verdicts with `item.location == codex.CONFIG_LOCATION`, `item.kind == "mcp"`, `extra={"config": None, "serena": True}`, action `migrate` (plain) or `keep` with reason `SERENA_OWN_CODEX` (names `--own NAME=remove`); entry_id `"mcp-serena"`.

- [ ] **Step 1: Failing tests**

```python
PLAIN = '[mcp_servers.serena]\ncommand = "serena"\nargs = ["start-mcp-server", "--context=codex", "--project-from-cwd"]\n'
TUNED = '[mcp_servers.serena]\ncommand = "serena"\nargs = ["start-mcp-server", "--context=ide", "--project-from-cwd"]\n'


def test_codex_serena_is_no_item_without_use_loadout(codex_on):
    _config(PLAIN)
    assert not [v for v in inventory.classify(inventory.collect(with_versions=False)) if v.item.extra.get("serena")]


def test_use_loadout_makes_a_plain_codex_serena_migrate(codex_on):
    _config(PLAIN)
    v = [v for v in inventory.classify(inventory.collect(with_versions=False), use_loadout=True)
         if v.item.extra.get("serena")]
    assert [(x.item.name, x.action) for x in v] == [("serena", "migrate")]
    assert v[0].item.location == codex.CONFIG_LOCATION


def test_use_loadout_keeps_a_tuned_codex_serena(codex_on):
    _config(TUNED)
    v = [v for v in inventory.classify(inventory.collect(with_versions=False), use_loadout=True)
         if v.item.extra.get("serena")]
    assert v[0].action == "keep" and "--own serena=remove" in v[0].reason


def test_a_left_codex_serena_stays_kept(codex_on):
    _config(PLAIN)
    from loadout import own
    own.remember_leave(inventory.Item("mcp", "serena", "", codex.CONFIG_LOCATION, {}))
    v = [v for v in inventory.classify(inventory.collect(with_versions=False), use_loadout=True)
         if v.item.name == "serena"]
    assert v[0].action == "keep" and v[0].reason == own.LEFT_REASON
```

- [ ] **Step 2: Run** `... pytest -q tests/test_codex_adopt.py -k "serena or use_loadout"` — Expected: the 3 use_loadout tests FAIL.
- [ ] **Step 3: Implement.** Codex off → `[]` (no read). Leave check through `own.decided(own.decisions(), item)` before the own-settings test. Loadout's own table (exact text in `read_record()["tables"]`) is never a verdict.
- [ ] **Step 4: Run** `... pytest -q tests/test_codex_adopt.py tests/test_inventory.py tests/test_codex_serena.py` — Expected: PASS.
- [ ] **Step 5: Commit** `feat(adopt): an own Codex Serena can be adopted in use_loadout mode`

### Task 3: Codex table text out and back in

**Files:**
- Modify: `cli/loadout/codex.py` (two helpers near `remove_server` :2048)
- Test: `tests/test_codex_serena.py` (fixture `cfg` :7-13)

**Interfaces:**
- Produces: `codex.table_source(name: str) -> str | None` (the exact text of `[mcp_servers.NAME]` and its sub-tables, including the comment lines `_sections` attaches, from `config.toml`; None when absent or the file is unreadable); `codex.reinsert_table(text: str) -> str` (appends the text to `config.toml` atomically with `write_atomic_bytes`, keeping a CRLF file CRLF and a separating newline; returns `"Serena: put your server back in config.toml"`, or `"Serena: could not put your server back (…); restore it with: loadout restore <dir>"` on failure — the caller fills `<dir>`; never raises).

- [ ] **Step 1: Failing tests**

```python
SRC = ('# my serena\n[mcp_servers.serena]\ncommand = "serena"\nargs = ["start-mcp-server", "--context=ide"]\n\n'
       '[mcp_servers.serena.env]\nSERENA_LOG = "debug"\n')


def test_table_source_takes_the_table_with_its_subtables(cfg, fake_home):
    p = codex.config_path()
    p.write_text('model = "x"\n\n' + SRC + '\n[mcp_servers.other]\ncommand = "o"\n')
    src = codex.table_source("serena")
    assert "[mcp_servers.serena.env]" in src and "SERENA_LOG" in src and "other" not in src


def test_reinsert_puts_back_exactly_the_text(cfg, fake_home):
    p = codex.config_path()
    p.write_text('model = "x"\n')
    assert "put your server back" in codex.reinsert_table(SRC)
    assert p.read_text().endswith(SRC) and p.read_text().startswith('model = "x"\n')
```

(Use the module's real config-path helper name; `paths.codex_home() / "config.toml"` if there is no `config_path`.)

- [ ] **Step 2: Run** `... pytest -q tests/test_codex_serena.py -k "table_source or reinsert"` — Expected: FAIL (no such functions).
- [ ] **Step 3: Implement** with `_sections` (:732) over the file's lines; `reinsert_table` reads bytes, appends, writes atomically.
- [ ] **Step 4: Run** `... pytest -q tests/test_codex_serena.py` — Expected: PASS.
- [ ] **Step 5: Commit** `feat(codex): read a server table's exact text and put it back`

### Task 4: The Serena pass and the adopt flags

**Files:**
- Modify: `cli/loadout/adopt.py` (new `serena_pass`, `run(..., use_loadout=False, keep_own=False)`), `cli/loadout/commands.py:28-55` (`--use-loadout`, `--keep-own` on `adopt`)
- Test: `tests/test_serena_pass.py` (new)

**Interfaces:**
- Consumes: Tasks 1-3; `adopt._apply_mcp` (Codex path `codex.remove_server`, Claude path `record_mcp_add`); `own.remember_leave`; `cbm_installer._claude_plugin_on` (make it public as `claude_plugin_on`, keep the old name as an alias).
- Produces: `adopt.serena_pass(bk: Backup, ask, interactive: bool, use_loadout: bool, keep_own: bool) -> tuple[list[str], list[str]]` returning (lines to print, removed Codex table texts, for rollback). `SERENA_QUESTION` (the Global Constraints text, `NAME` formatted).

Behaviour, in this order: `keep_own` → `([], [])`. Verdicts = `classify(collect(...), use_loadout=True)` filtered to Serena (Claude: `codex.is_serena(cfg)`; Codex: `extra["serena"]`). A kept verdict with `own.LEFT_REASON` and `use_loadout` → line `"Serena: kept (you chose leave)"`. A `keep` with own settings → line with its reason (only when `use_loadout` or interactive). A `migrate`:
- Codex: guard `runner.have("serena")` (else line `"Serena: yours kept: loadout's needs the serena command, which is missing"`); guard: `config.toml` is a symlink → line, skip. Then `use_loadout` → remove; interactive → ask the question: `y` remove, `n` `own.remember_leave` + line, anything else nothing. Before removing, `text = codex.table_source(name)`; after a successful remove, append `text` to the returned list.
- Claude: only under `use_loadout`; guard `claude_plugin_on()` (else line `"Serena: yours kept: loadout's plugin is not installed yet"`); then remove through `_apply_mcp`.
`adopt --apply --use-loadout` runs `serena_pass(..., interactive=False, use_loadout=True)` before the normal flow; `--use-loadout` and `--keep-own` together → print `"--use-loadout and --keep-own exclude each other"`, return 2.

- [ ] **Step 1: Failing tests** (`tests/test_serena_pass.py`; reuse `codex_on`/`_config` patterns, `fake_runner.responses[("codex","mcp","remove","serena")]`):

```python
def test_flag_removes_a_plain_codex_serena_with_backup(...)        # remove ran; config.toml saved in bk; text returned
def test_interactive_y_removes_n_remembers_enter_does_nothing(...)  # parametrize answers
def test_tuned_codex_serena_is_kept_under_the_flag(...)            # reason names --own serena=remove
def test_missing_serena_command_keeps_the_codex_table(...)          # fake_runner.missing.add("serena")
def test_leave_beats_the_flag(...)                                  # "kept (you chose leave)"; no remove call
def test_keep_own_does_nothing_and_stores_nothing(...)
def test_claude_serena_only_with_the_flag_and_the_plugin(...)       # without plugin: kept + line; with: add-json undo recorded
def test_claude_off_reads_nothing_of_claude(...)                    # targets claude off; ~/.claude.json with serena untouched, no claude calls
def test_codex_off_reads_nothing_of_codex(...)
def test_symlinked_config_toml_is_skipped(...)
def test_no_duplicate_no_output(...)
def test_adopt_rejects_both_flags(...)                              # run(... use_loadout=True, keep_own=True) == 2
def test_output_never_shows_env_values(...)                         # Claude cfg with env {"TOKEN": "s3cret"}: "s3cret" not in output
```

Write each with concrete asserts on `fake_runner.calls`, the backup's steps and the returned lines.

- [ ] **Step 2: Run** `... pytest -q tests/test_serena_pass.py` — Expected: FAIL (no `serena_pass`).
- [ ] **Step 3: Implement** `serena_pass` and the flags.
- [ ] **Step 4: Run** `... pytest -q tests/test_serena_pass.py tests/test_adopt.py tests/test_codex_adopt.py` — Expected: PASS.
- [ ] **Step 5: Commit** `feat(adopt): a Serena pass and --use-loadout / --keep-own`

### Task 5: Bootstrap runs the pass, rolls back, and says what is left

**Files:**
- Modify: `cli/loadout/bootstrap.py` (`bootstrap(..., use_loadout=False, keep_own=False)` :1046; the pass between the plugin step :1173-1182 and the Codex section :1187; rollback after `codex_step` :1193-1198), `cli/loadout/commands.py` `_register_bootstrap` (~:175-215), `cli/loadout/check.py:346-361` (the "two Serena servers" fix text also names `loadout adopt --apply --use-loadout`)
- Test: `tests/test_bootstrap_own_serena.py` (helpers `_codex` :11-18, `_run` :20-22)

**Interfaces:**
- Consumes: `adopt.serena_pass` (Task 4), `codex.reinsert_table` (Task 3).

Behaviour: the pass runs when `personal_ok` and (Claude or Codex is on), also on Codex-only machines, with its own `Backup(description="use loadout's Serena")` (created lazily: no backup folder when nothing is removed). After the Codex section: if removed texts exist and `"serena" not in codex.read_record()["tables"]` (loadout's table was not written: `codex_step` failed or did not run), call `codex.reinsert_table(text)` for each and print its line (with the backup dir filled in on failure). The `SERENA_KEPT` note stays for a kept own table. Non-interactive runs without `--use-loadout` that have a plain duplicate add a "Still to do" line: `Serena runs twice: loadout adopt --apply --use-loadout (or leave yours: loadout configure own)`.

- [ ] **Step 1: Failing tests**

```python
def test_flag_replaces_the_codex_serena_in_one_run(...)          # remove called before codex_step; loadout's table written after
def test_codex_only_machine_runs_the_pass(...)                    # agents="codex"
def test_rollback_when_codex_step_does_not_write_serena(...)      # monkeypatch apply.codex_step to fail: table text back, line printed
def test_rollback_failure_names_the_backup(...)                   # reinsert fails (read-only file): line has "loadout restore"
def test_yes_alone_leaves_the_codex_serena(...)                   # SERENA_KEPT printed, no remove call
def test_both_flags_exit_2(...)                                   # through commands' parser
def test_non_interactive_names_the_next_step(...)                 # Still to do line
```

- [ ] **Step 2: Run** `... pytest -q tests/test_bootstrap_own_serena.py` — Expected: new tests FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the full suite `uv run --python 3.12 --with pytest pytest -q` — Expected: all pass.
- [ ] **Step 5: Commit** `feat(bootstrap): --use-loadout replaces your Serena with loadout's, with rollback`

### Task 6: Docs and spec

**Files:**
- Modify: `docs/reference/cli.md` (bootstrap and adopt flags: `--use-loadout`, `--keep-own`, their delta over `--yes`), `docs/how-to/codex.md` ("Serena already set up?": the choice, the flag, restore), `docs/reference/own-tools.md` (tuned Serena kept, ADR 0045), `docs/how-to/troubleshooting.md` (the "two Serena servers" row), `docs/superpowers/specs/2026-10-31-start-clean-design.md` (status: planned; drop section 5, now fixed by #76; stale line numbers removed; the three planning calls), `AGENTS.md` (ADR range 0001-0045)
- Test: `uv run --python 3.12 --with pytest pytest -q tests/test_docs_commands.py tests/test_docs_links.py`

- [ ] **Step 1:** Edit; each fact in one place.
- [ ] **Step 2: Run** the docs tests — Expected: PASS.
- [ ] **Step 3: Commit** `docs: use loadout's Serena (--use-loadout), ADR 0045`
