# One-command setup on a fresh machine

Status: approved design (2026-10-11). Part of sub-project C (publication), after the toolset showcase (PR #4) and before the demo and `v0.1.0`.

## 1. Goal

A new user goes from a bare machine to a green `loadout check` with one command plus at most a few clearly listed steps. Everything loadout can install without admin rights, it installs and configures. What it cannot (git, logging in) is listed in the README as one copy-paste line per OS, and bootstrap prints the same lines at its end.

Success criteria:
- On a bare Ubuntu 24.04 with only git, curl and ca-certificates, `bootstrap.sh --install --yes --no-plugins` (from a checkout, and as a one-liner without one) ends with a `loadout check` that has no `FAIL` line, and a new login shell finds `claude`, `serena`, `codebase-memory-mcp` and `loadout`. A CI job proves it.
- No step uses sudo or administrator rights.
- A tool that is already on `PATH` is never installed again or replaced.
- Native Windows is marked experimental and not recommended everywhere it appears; WSL 2 is the recommended Windows setup.

Decisions from the brainstorm (user, 2026-10-11): user space first (no sudo); approach A (bootstrap brings the toolchain) plus C (a one-liner); the one-liner is the same script as the clone path; native Windows experimental; the sandbox packages are optional.

## 2. Entry points

`bootstrap.sh` (Linux, macOS, WSL) and `bootstrap.ps1` (native Windows, experimental) are the only entry points. Each detects where it runs:

- **Inside a checkout** (the script's folder contains `bin/loadout`): it uses that checkout where it is. Nothing is cloned or moved.
- **Without a checkout** (piped: `curl -fsSL https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.sh | bash -s -- --install`, or the PowerShell equivalent): it needs git. If git is missing it prints the install line for the detected OS (§4) and exits 1. Otherwise it clones into `./agent-loadout` in the current folder (like `git clone`), or into the folder given with `--dir PATH`, and says where. If the target already is a clone of the kit (its `origin` points to `jonasyr/agent-loadout`), it uses it without cloning. A target that exists and is something else: exit 1 with a message, nothing touched. Then it continues inside the checkout as above.

Then, in both cases:

1. If `uv` is not on `PATH` (also checking `~/.local/bin/uv`), install it with the official installer (`curl -LsSf https://astral.sh/uv/install.sh | sh`; Windows `irm https://astral.sh/uv/install.ps1 | iex`). Prepend `~/.local/bin` to the script's `PATH`.
2. Run loadout through uv: `uv run --no-project --python 3.12 bin/loadout bootstrap "$@"`. uv downloads Python 3.12 if no suitable one exists. A system Python is no longer required. `--dir` is consumed by the script and not passed on.

The Python 3.10 guard in `bin/loadout` stays for direct use.

`bootstrap.ps1` prints at its start: "Native Windows is experimental and not recommended. WSL 2 is the recommended setup on Windows: docs/how-to/wsl.md". It continues. It keeps the Git Bash warning.

## 3. Toolchain: catalog, order, PATH

### 3.1 New install commands (user space only)

| Binary | posix | windows |
|---|---|---|
| `claude` | `curl -fsSL https://claude.ai/install.sh \| bash` | `irm https://claude.ai/install.ps1 \| iex` (PowerShell) |
| `mise` (new catalog binary, `status: core`, not `required`) | `curl -fsSL https://mise.run \| sh` | `winget install --id jdx.mise -e --scope user` (plan verifies the user-scope flag; else `--source winget` without scope) |
| `node` | `mise use -g node@lts` | same |
| `gh` | `mise use -g gh` | same |
| `rust-analyzer` | `mise use -g rust-analyzer` | same |

`git` keeps its `manual` text (§4). The existing commands for uv, serena, codebase-memory-mcp, rtk, playwright-cli, pyright and typescript-language-server stay.

### 3.2 Order and "missing only"

- New optional catalog field `needs: [ids]` on binaries: `serena` needs `uv`; `node`, `gh`, `rust-analyzer` need `mise`; `playwright-cli`, `pyright`, `typescript-language-server` need `node`. `bootstrap.check_prereqs` installs in an order that respects `needs` (a stable topological sort of the catalog order). Documented in `docs/reference/catalog-format.md`; a static test checks every `needs` id exists and there is no cycle.
- `mise` is installed only when a binary that needs it is missing and has no other install command for the platform. It is never installed on its own.
- A binary already on `PATH` (after the PATH update in 3.3) is skipped, whoever installed it. If a dependency failed to install, its dependants are skipped with "skipped: needs <id>".

### 3.3 PATH during and after bootstrap

- `paths.tool_dirs() -> list[Path]`: `~/.local/bin`, the mise shims folder (`~/.local/share/mise/shims`; Windows `%LOCALAPPDATA%\mise\shims`), and, when `npm` resolves, `npm prefix -g` + `/bin` (Windows: the prefix itself). Existing folders only.
- Before each install command and before the final check, bootstrap prepends `tool_dirs()` to its own `os.environ["PATH"]` (no duplicates), so each step finds what the earlier ones installed.
- When node is mise-managed, run `mise reshim` after npm installs so global npm binaries get shims (plan verifies whether this is needed with current mise).
- The same folders go into the user's shell profile through a marked block, separate from the secrets block: `# loadout PATH` in `~/.bashrc`, `~/.zshrc` (when zsh is the login shell or the file exists) and `~/.profile`; on Windows the user `PATH` environment variable (`[Environment]::SetEnvironmentVariable(..., "User")`, through a PowerShell command run once) instead of the profile. Backed up like today (`bootstrap._add_block`). Idempotent.
- The last bootstrap line says "Open a new terminal so the new PATH applies." only when the profile or the user PATH changed.

### 3.4 Python for the `loadout` command and the hooks

Without a system `python3` (≥ 3.10):

- `link.link_bin` writes `~/.local/bin/loadout` as a small launcher script instead of a link: it runs `python3 bin/loadout` when `python3` is ≥ 3.10, else `uv run --no-project --python 3.12 bin/loadout`. Windows: the existing `.cmd` shim gets the same fallback.
- `plugins/loadout/hooks/run.sh` gains `--python`: `run.sh [--soft] --python script.py args` runs the script with `python3` when it is ≥ 3.10, else with `uv run --no-project --python 3.12`, else does nothing (exit 0). `hooks.json` uses it for `advisor.py` and `reload_check.py` (today `run.sh --soft python3 ...`).
- `maintenance._spawn_background` keeps `sys.executable` (the interpreter that runs loadout, possibly uv's).

### 3.5 `loadout check`

New line "MCP servers on PATH": whether `serena` and `codebase-memory-mcp` resolve on the PATH a new terminal will have (current PATH plus `tool_dirs()`; a tool found only through `tool_dirs()` gives a `warn` "open a new terminal or add <dir> to PATH"). Claude Code starts the plugin's servers by name.

## 4. What stays manual

README section "Before you start" and the same lines in bootstrap's end summary for the detected OS:

| | Linux / WSL | macOS | Windows (experimental) |
|---|---|---|---|
| git | `sudo apt install git` (Debian/Ubuntu; other distros: their package manager) | `xcode-select --install` | `winget install --id Git.Git -e` (Git Bash runs the hooks) |
| After bootstrap | `claude` (log in), `gh auth login` | same | same |

Below the table: "Optional, only if you turn on Claude Code's sandbox (Linux, WSL 2): `sudo apt-get install bubblewrap socat`." The B-era WSL warning for missing bwrap/socat says "needed for Claude Code's sandbox".

Bootstrap's end summary lists what it installed, then "Still to do" with exactly the lines above that apply (git missing, not logged in to Claude Code or gh), for the detected OS. `loadout check` keeps naming the fix per line.

## 5. Docs

- **README**: Quick start leads with the one-liner for Linux, macOS and WSL; clone-and-run directly below ("read the code first"). Native Windows in a collapsed "Experimental: native Windows" block. Requirements line shrinks to "git; everything else is installed for you (see Before you start)". Badge: "Windows (WSL 2)".
- **getting-started tutorial**: same structure; native Windows under an "Experimental" heading with the not-recommended note.
- **included-tools**: mise, claude install commands; the requirements sentence.
- **security-and-trust**: the new installers (uv, Claude Code, mise, and the one-liner itself), whom each trusts, and how to avoid them (run without `--install`; clone and read first).
- **wsl.md, troubleshooting**: PATH and "open a new terminal"; sandbox packages optional.
- **ADR 0020** "Bootstrap installs the toolchain in user space": no sudo; uv supplies Python; mise only for node, gh, rust-analyzer; missing-only; the launcher and hook fallback.
- **AGENTS.md**: ADR range; nothing else unless a module is added.

## 6. Fresh-machine CI

New workflow `.github/workflows/fresh-machine.yml`, triggered on pull requests that touch `bootstrap.*`, `catalog.json`, `cli/loadout/bootstrap.py`, `cli/loadout/link.py`, `cli/loadout/paths.py` or the workflow itself, weekly (schedule), and manually (`workflow_dispatch`). Real installers run only here, on throwaway machines.

- **`fresh-machine (linux)`**: container `ubuntu:24.04`; `apt-get install -y git curl ca-certificates` as root; then as a new non-root user with an empty HOME:
  1. from the checkout copied to the user's home: `bash bootstrap.sh --install --yes --no-plugins`; then in a new login shell (`bash -lc`): `loadout check` must print no `FAIL`; `claude --version`, `serena --version`, `codebase-memory-mcp --version` succeed.
  2. one-liner form in an empty folder with a fresh HOME: `bash -s -- --install --yes --no-plugins < bootstrap.sh` run outside any checkout, cloning from the PR's head (the clone URL and ref are overridable for CI through environment variables `LOADOUT_REPO_URL` and `LOADOUT_REF`, documented as test-only); same checks.
- **`fresh-machine (windows)`**, experimental: `windows-latest` with Python, Node and gh removed from `PATH` for the job; `bootstrap.ps1 --install --yes --no-plugins`; `loadout check` without `FAIL`. `continue-on-error: true`: a red run is reported, not blocking.
- `--no-plugins` in CI: plugin installation needs a logged-in Claude Code; the plugin path is covered by unit tests.

Unit tests (normal suite, `fake_home`, `fake_runner`): install order with `needs` (including a failed dependency), missing-only, PATH prepending, the PATH profile block (idempotent, backed up), the launcher fallback, `run.sh --python` (python3 present, absent with uv, both absent), the end summary per OS, the `check` line, and the entry-script checkout detection (bash tests with a temporary directory, no network: the clone and uv steps are stubbed through `PATH`).

## 7. Out of scope

The VHS demo, GitHub metadata, vulnerability reporting and the release (rest of C); package-manager installs that need sudo; installing git; Codex (D).
