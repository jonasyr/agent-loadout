# Windows and WSL
Native Windows is experimental; WSL 2 is the recommended Windows setup: docs/how-to/wsl.md, docs/reference/setup-matrix.md. Codex in WSL: one loadout per side (ADR 0029); VS Code side: docs/how-to/vscode.md#windows-and-wsl.
Where: `cli/loadout/wsl.py` (detection, `codex_side`, `windows_home`), `bootstrap.codex_gate`, `check._codex_side`, `check._vscode`, `bootstrap.setup_vscode_path`, `vscode.wsl_switch_overrides`.
Tests: patch `wsl.windows_home`/`wsl.MOUNT`, compare paths as POSIX strings, `fake_home` sets `USER`: CONTRIBUTING.md#test-rules.
Details: docs/how-to/troubleshooting.md.
