# Windows and WSL
Native Windows is experimental and not recommended (hooks run under Git Bash); WSL 2 is the recommended Windows setup. Tests with bash stubs skip on Windows.
WSL is detected by `cli/loadout/wsl.py` (shown in `loadout check` and at bootstrap start); CI has a `test (wsl2)` job. Compare paths as POSIX strings so WSL tests also pass on the Windows job.
Open (2026-10-11): after bootstrap on native Windows, npm globals (playwright-cli, pyright, typescript-language-server) are not found (runner npm prefix `C:\npm\prefix`; mise shims cover only `.exe`); the experimental fresh-machine job prints diagnostics. Likely fix: `mise use -g npm:...` on Windows.
Details: docs/how-to/wsl.md, docs/how-to/troubleshooting.md.
