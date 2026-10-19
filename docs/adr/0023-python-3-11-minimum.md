# 0023. Python 3.11 minimum

- Status: Accepted
- Date: 2026-10-13
- Source: [Hardening 1 plan](../superpowers/plans/2026-10-13-hardening-1-security.md)
- Supersedes: the Python minimum in [ADR 0020](0020-bootstrap-installs-the-toolchain-in-user-space.md) (3.10+)

## Context
loadout used to run on Python 3.10, but editing Codex's `config.toml` safely needs `tomllib`, which exists from Python 3.11. Every such edit therefore had a second code path for 3.10 that skipped the work with a message, and every path needed its own tests. These branches cost three review findings. [ADR 0020](0020-bootstrap-installs-the-toolchain-in-user-space.md) already gives the launcher and the plugin hooks a uv fallback, and Ubuntu 22.04 ships only Python 3.10.

## Decision
We will require Python 3.11. The launcher, `bin/loadout`, the plugin's `run.sh`, both bootstrap scripts and `pyproject.toml` check for 3.11, and the code uses `tomllib` without a fallback.

## Alternatives considered
- Keep 3.10 and ship a TOML parser: breaks the standard-library-only rule.
- Keep the 3.10 skip paths: untested edge cases and a weaker Codex target on older machines.

## Consequences
- A machine with only Python 3.10 runs loadout on the newest Python 3.11 or later that uv provides: bootstrap installs it, and an older launcher that still starts Python 3.10 continues under it (`bin/loadout` asks uv). Without uv, loadout asks to re-run bootstrap.
- No TOML special cases remain in `codex.py`, `codex_project.py` and `own.py`.

## In the code
- `bin/loadout`, `plugins/loadout/hooks/run.sh`, `bootstrap.sh`, `bootstrap.ps1`, `pyproject.toml`
