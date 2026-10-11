# Windows and WSL
Native Windows runs hooks under Git Bash; WSL 2 is recommended. Tests with bash stubs skip on Windows.
WSL is detected by `cli/loadout/wsl.py` (shown in `loadout check` and at bootstrap start); CI has a `test (wsl2)` job. Compare paths as POSIX strings so WSL tests also pass on the Windows job.
Details: docs/how-to/wsl.md, docs/how-to/troubleshooting.md.
