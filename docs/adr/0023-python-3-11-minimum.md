# 0023. Python 3.11 minimum

- Status: Accepted
- Date: 2026-10-13
- Source: [Hardening 1 plan](../superpowers/plans/2026-10-13-hardening-1-security.md)

## Context
loadout used to run on Python 3.10, but editing Codex's `config.toml` safely needs `tomllib`, which exists from Python 3.11. Every such edit therefore had a second code path for 3.10 that skipped the work with a message, and every path needed its own tests. These branches cost three review findings. [ADR 0020](0020-bootstrap-installs-the-toolchain-in-user-space.md) already gives the launcher and the plugin hooks a uv fallback, and Ubuntu 22.04 ships only Python 3.10.

## Decision
We will require Python 3.11. The launcher, `bin/loadout`, the plugin's `run.sh`, both bootstrap scripts and `pyproject.toml` check for 3.11, and the code uses `tomllib` without a fallback.

## Alternatives considered
- Keep 3.10 and ship a TOML parser: breaks the standard-library-only rule.
- Keep the 3.10 skip paths: untested edge cases and a weaker Codex target on older machines.

## Consequences
- A machine with only Python 3.10 downloads one uv-managed Python 3.11 the first time; nothing else changes for it.
- No TOML special cases remain in `codex.py`, `codex_project.py` and `own.py`.
