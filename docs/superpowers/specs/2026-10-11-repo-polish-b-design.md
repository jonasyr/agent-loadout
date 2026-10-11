# Repo polish, sub-project B: small code items

Status: approved design (2026-10-11). Part of the repo-polish work: A docs and repo content (merged, PR #2) → **B small code items (this spec)** → C publication (demo, GitHub metadata, `v0.1.0`; every outward step only after the user confirms) → later D other agents (Codex).

## 1. Goal

Close the known gaps before publication, so loadout behaves well on WSL and native Windows and the docs no longer say "not yet". No features beyond the list below. Every item: tests first (`fake_home`, `fake_runner`, never the real `~/.claude`), docs in the same commit as the code.

Success criteria:
- Each item in §2–§7 is implemented with tests; the suite passes on Linux, Windows and the new WSL 2 job.
- `docs/how-to/wsl.md` no longer says loadout does not detect WSL; every changed behaviour is documented in the page that owns it.
- No real installer or mutating `claude` command runs in tests or from agents.

## 2. Wiley Scholar Gateway and connector duplicates

Facts (verified 2026-10-11): plugin `wiley-scholar-gateway` in marketplace `life-sciences` (repo `anthropics/life-sciences`). The user also has the same server as the claude.ai connector "claude.ai Wiley Scholar Gateway"; both together duplicate the tools in context. Same for Context7 (plugin `context7@claude-plugins-official` and "claude.ai Context7").

- `settings.base.json` → `extraKnownMarketplaces.life-sciences` (`{"source": {"source": "github", "repo": "anthropics/life-sciences"}}`, same shape as the existing entries). This makes the marketplace known; it installs nothing.
- `catalog.json` → entry `plugin-wiley-scholar-gateway`: `kind: plugin`, `status: profile`, `profile: thesis`, `match.names: ["wiley-scholar-gateway@life-sciences"]`, `connector: "claude.ai Wiley Scholar Gateway"`, reason: literature search across Wiley's peer-reviewed content; use either the plugin or the claude.ai connector, not both.
- New optional catalog field `connector` on `kind: plugin` entries (string: the connector's name as Claude Code lists it). Set it on the Wiley entry and on a new entry `plugin-context7` (`kind: plugin`, `status: core`, `match.names: ["context7@claude-plugins-official"]`, `connector: "claude.ai Context7"`; the kit enables this plugin in `settings.base.json`). Documented in `docs/reference/catalog-format.md`.
- `profiles/thesis.json` does **not** enable the plugin. Its `notes` say: literature search through the claude.ai Wiley Scholar Gateway connector; where there is no claude.ai login, enable the `wiley-scholar-gateway@life-sciences` plugin instead.
- `loadout check` gains a duplicate check: for each catalog entry with `connector` whose plugin is enabled in `~/.claude/settings.json` and whose connector name is in `~/.claude.json` → `claudeAiMcpEverConnected`, one WARN: "<plugin> and the claude.ai connector <name> provide the same tools (if the connector is still connected)", with the fix "disconnect the connector on claude.ai, or disable the plugin (for a plugin the kit enables: `\"enabledPlugins\": {\"<plugin>\": false}` in your personal `settings.json`, then `loadout apply-settings`)". Verify in the plan that a personal `false` overrides the kit's `true` in the desired overlay (it should: scalars, personal wins). `claudeAiMcpEverConnected` is undocumented and means "connected at some point"; the wording says so, and a missing or malformed key means no warning.

## 3. `/reload-plugins` notice

Problem (seen 2026-10-10): Claude Code auto-updated the loadout plugin a minute after a session started; the session kept the old version (skills and hooks missing) until `/reload-plugins`.

- New standalone hook script `plugins/loadout/hooks/reload_check.py` (stdlib, no import of the kit CLI, like `advisor.py`). Wired in `hooks.json` into `SessionStart` and `Stop` through `run.sh --soft`.
- Logic: read `CLAUDE_PLUGIN_ROOT`; read `~/.claude/plugins/installed_plugins.json` → `plugins["loadout@agent-loadout"]` (a list; use the entry with `scope: user`, else the first) → `installPath`. Compare both as resolved paths. If they differ and this session (`session_id` from the hook's stdin JSON) was not notified yet → print `{"systemMessage": "loadout: the plugin was updated after this session started. Run /reload-plugins to load the new skills and hooks."}` and record the session id in `~/.claude/.loadout/reload-notified.json` (keep the last 20 ids).
- Never block, never fail: any missing file, missing key, bad JSON or exception → no output, exit 0. No output when the paths match.
- Tests: paths equal → silent; different → one message, second call in the same session silent, new session → message again; missing/malformed `installed_plugins.json` → silent; no `CLAUDE_PLUGIN_ROOT` → silent.

## 4. WSL detection

New module `cli/loadout/wsl.py`:

- `detect(osrelease: Path = Path("/proc/sys/kernel/osrelease")) -> int | None`: `None` when not Linux or the file has no "microsoft" (case-insensitive); `2` when it contains "WSL2" (case-insensitive; e.g. `5.15.153.1-microsoft-standard-WSL2`); else `1` (WSL 1 reports e.g. `4.4.0-19041-Microsoft`).
- `problems(version: int, cwd: Path) -> list[tuple[str, str]]` (problem, fix), each independent:
  1. WSL 1 → "WSL 1: Claude Code's sandbox needs WSL 2, and its native binary can fail with `Exec format error`" / "in PowerShell: `wsl --set-version <distro> 2`".
  2. Kit root, personal root or `cwd` under `/mnt/<letter>/` → "<path> is on the Windows filesystem (slow, search can be incomplete)" / "move it into the Linux home, e.g. `~/code/...`".
  3. `claude`, `node`, `npm`, `uv` or `git` resolving (via `shutil.which`) to a path under `/mnt/` → "<tool> resolves to the Windows program <path>" / "install it inside WSL and put its directory first in PATH, or set `appendWindowsPath = false` in `/etc/wsl.conf`".
  4. `bwrap` or `socat` missing (WSL 2 only) → "sandbox packages missing: <names>" / "`sudo apt-get install bubblewrap socat`".
- `loadout check`: when `detect()` is not `None`, one OK line "WSL <n>" and one WARN per problem (fix shown like other WARNs). Not WSL → no lines.
- Bootstrap: at the start, when in WSL, print each problem with its fix and continue (no question, no exit code change).
- Docs: `docs/how-to/wsl.md` (detection now exists; the manual steps stay as the fix reference; drop "does not detect WSL yet"), `docs/reference/cli.md` (`check` lines), `docs/how-to/troubleshooting.md` (link).
- Tests: osrelease samples for WSL 1, WSL 2, plain Linux, missing file; problems with fake PATH (tool scripts under a fake `/mnt/c`-like path via a parameter for the mount prefix, default `/mnt/`), fake kit/personal roots, missing bwrap/socat; check and bootstrap output.

## 5. WSL 2 CI job

`.github/workflows/` (the existing test workflow): new job `test (wsl2)` on `windows-latest`:
- `Vampire/setup-wsl@v7` with `distribution: Ubuntu-24.04`, `wsl-version: 2`, `additional-packages: python3 python3-pip git` (or install `uv` the same way the Linux job does).
- `shell: wsl-bash {0}` steps: run the full suite (`uv run --python 3.12 --with pytest pytest -q`), then a smoke test: `python3 -c` that imports `loadout.wsl` and asserts `detect() == 2`, and `bin/loadout check` output contains "WSL 2" and no "WSL 1" problem. The check may exit non-zero for unrelated missing tools; the smoke test only greps its output.
- Runs on every push and PR, in parallel with the other jobs.
- If GitHub's runner cannot run WSL 2 (nested virtualization), stop and report to the user instead of falling back silently to WSL 1.

## 6. Small fixes

- **`LOADOUT_NO_AUTO_PULL=1` respawn.** `maintenance.session_start` treats the pull as due only when the opt-out is not set (`last-pull` is never stamped under the opt-out, so today maintenance starts at every session). Test: opt-out set, `last-update-check` fresh → no spawn; opt-out set, weekly check due → spawn.
- **codebase-memory install and update.** Upstream (README, v0.11.0): the install scripts configure coding agents unless given `--skip-config`, and `codebase-memory-mcp update` only prints the command to re-run the install script. loadout provides the MCP server through the plugin, so:
  - `install.posix`: `sh -c "curl -fsSL https://raw.githubusercontent.com/DeusData/codebase-memory-mcp/main/install.sh | bash -s -- --skip-config"`.
  - `install.windows`: `powershell -NoProfile -ExecutionPolicy Bypass -Command "& ([scriptblock]::Create((irm https://raw.githubusercontent.com/DeusData/codebase-memory-mcp/main/install.ps1))) --skip-config"`.
  - `update.posix` / `update.windows`: the same commands (re-running the script is the update).
  - Docs: `docs/reference/included-tools.md`, `docs/explanation/security-and-trust.md` if it lists install commands, and ADR **0019** "Upstream installers run without agent configuration" (the plugin owns MCP and hook configuration; `--skip-config` prevents duplicates; links `duplicates.py`). ADR index updated.
  - Tests: catalog static test that every codebase-memory install/update command contains `--skip-config` and that Windows has an install command.
- **Python ≥ 3.10.** `bin/loadout` checks `sys.version_info < (3, 10)` before importing the CLI and exits 1 with "loadout needs Python 3.10 or newer (found X.Y)". The file must stay parseable by old Pythons (no new syntax before the check). `loadout check` shows an OK line "Python X.Y". Tests: run `bin/loadout` logic with a patched version tuple (the check lives in a tiny function the test can call).
- **Execution advisor follow-ups.**
  - `plugins/loadout/skills/execution-advisor/SKILL.md` §2: the Risk row says "per-task independent review (a Delegated or Inline row with per-task review)" instead of "SDD task".
  - §6: "Independent Delegated rows that touch disjoint files may be dispatched in parallel (one message, several implementer subagents); record each as its own `Task <N>: complete` line."
  - `advisor.py` `stop()`: also skip the nudge when a sdd-workspace ledger for this plan already records progress: for the plan `docs/superpowers/plans/<date>-<name>.md`, if `.superpowers/sdd/<date>-<name>/progress.md` (relative to the repo root that contains the plan) contains a line matching `^Task \d+: complete`, treat execution as started. Tests for both ledger present/absent.
  - Eval: re-run only if the skill text change affects a graded case (run via `plugins/loadout/evals/run.sh --case <case>`; ask the user before a run).

## 7. Docs and agent notes

- Pages that own the changed facts: `how-to/wsl.md`, `how-to/troubleshooting.md` (reload notice, WSL), `reference/cli.md` (`check` lines), `reference/catalog-format.md` (`connector`), `reference/included-tools.md` (Wiley, codebase-memory flags), `reference/hooks.md` (new hook), `explanation/execution-advisor.md` if the parallel rule is mentioned there, ADR 0019, `README.md` only if a claim changes.
- `AGENTS.md` map: add `wsl.py`. Serena memories: update the Windows/WSL note.
- At the end: `/loadout:docs-sync`, re-index codebase-memory.

## 8. Out of scope

Codex/other agents (D), the demo and release (C), the backlog items not listed here (process-list secret exposure, fish/.bash_profile, browser eval rerun).
