# 0020. Bootstrap installs the toolchain in user space

- Status: Accepted; its Python minimum (3.10) is superseded by [0023](0023-python-3-11-minimum.md). For Codex, see [ADR 0024](0024-codex-parity-update-model.md).
- Date: 2026-10-11
- Source: [One-command setup design](../superpowers/specs/2026-10-11-one-command-setup-design.md)

## Context
A fresh machine needed Python, Node.js, gh and Claude Code before bootstrap could run, and tools installed during bootstrap were not on its PATH. Setup took several manual steps per OS and failed in confusing ways.

## Decision
Bootstrap installs every missing tool it can without sudo or administrator rights: uv first (it provides Python for loadout), then Claude Code with Anthropic's native installer, mise for Node.js, gh and rust-analyzer, then the npm-based tools. It installs only what is missing and never replaces a tool already on PATH. It adds the user-space tool folders to its own PATH while it runs and to the shell profile (block `# loadout PATH`). The `loadout` launcher and the plugin's Python hooks fall back to uv when there is no Python 3.10+. git and logging in stay manual and are listed per OS.

## Alternatives considered
- The system package manager (apt, brew, winget machine scope): needs sudo or administrator rights and differs per distribution.
- mise for everything, including Python and uv: makes mise mandatory even for users who do not want it.
- Keep the prerequisites manual: the main source of failed setups.

## Consequences
- More upstream installers run with `--install` (uv, Claude Code, mise); they are listed in [Security and trust](../explanation/security-and-trust.md).
- A fresh-machine CI workflow runs the real installers on throwaway machines.
- Native Windows remains experimental.

## In the code
- `bootstrap.sh`, `bootstrap.ps1`
- `cli/loadout/bootstrap.py` (`check_prereqs`, `prepend_tool_dirs`, `PATH_MARKER`), `cli/loadout/paths.py` (`tool_dirs`)
- `bin/loadout`, `plugins/loadout/hooks/run.sh` (the uv fallback)
