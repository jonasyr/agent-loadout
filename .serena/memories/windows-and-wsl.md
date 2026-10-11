# Windows and WSL
Native Windows is experimental and not recommended (hooks run under Git Bash); WSL 2 is the recommended Windows setup. Tests with bash stubs skip on Windows.
WSL is detected by `cli/loadout/wsl.py` (shown in `loadout check` and at bootstrap start); CI has a `test (wsl2)` job. Compare paths as POSIX strings so WSL tests also pass on the Windows job.
npm's global commands on Windows live in `npm prefix -g` (anywhere; the GitHub runner uses `C:\npm\prefix`), not in mise's shims: `bootstrap.npm_global_dir()` adds it to PATH (PR #7).
Details: docs/how-to/wsl.md, docs/how-to/troubleshooting.md.
