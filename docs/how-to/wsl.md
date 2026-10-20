# Use loadout on Windows with WSL 2

Use this page if you work on Windows. WSL 2 is the recommended setup for loadout. Native Windows is experimental and not recommended; its steps are in [Getting started](../tutorials/getting-started.md#experimental-native-windows).

loadout detects WSL. `loadout check` prints `WSL 1` or `WSL 2` and warns about the problems below that it can see: the kit, the personal layer or the current folder under `/mnt/<drive>/`; `node`, `npm`, `uv` or `git` resolving to a Windows program; with Claude Code on, WSL 1, `claude` resolving to a Windows program and (WSL 2) missing bubblewrap or socat; with Codex on, `codex` resolving to a Windows program and the [Windows side of Codex](#codex). Bootstrap prints the same warnings at its start and continues. The steps below are the fixes.

Anthropic supports both native Windows and WSL 2 for Claude Code and does not name a preferred one ([setup](https://code.claude.com/docs/en/setup)). loadout recommends WSL 2 for these reasons:

- **The sandbox.** On Windows, the sandbox works only inside WSL 2: native Windows runs commands unsandboxed and WSL 1 is not supported ([sandboxing](https://code.claude.com/docs/en/sandboxing)).
- **You get the Linux toolchain.** The install commands are the same as on Linux.
- **No Git Bash.** On native Windows, Claude Code runs hooks through Git Bash, so hook script paths need forward slashes or quotes. In WSL they are normal Linux paths.

## 1. Use WSL 2, not WSL 1

In PowerShell, check the version of your distribution and upgrade it:

```powershell
wsl -l -v
wsl --set-version <distro> 2
```

WSL 1 has a regression where Claude Code's native binary fails with `Exec format error` ([troubleshoot-install](https://code.claude.com/docs/en/troubleshoot-install)).

## 2. Install loadout inside WSL

Open the WSL terminal, not PowerShell. Run `cd ~`, then follow [Step 1 of the tutorial](../tutorials/getting-started.md#step-1-run-bootstrap) inside WSL.

With Codex only and VS Code, follow [Codex only on Windows with VS Code](setups.md#codex-only-on-windows-with-vs-code) instead. Which path fits your agents and surface: [Pick your setup](setups.md#recommended-setups).

Keep the clone in the Linux home: the installed links point into it. Choose Claude Code, Codex or both when bootstrap asks. Then restart Claude Code and/or Codex, whichever you chose (in the Codex CLI, approve loadout's hooks once with `/hooks`, see [Use loadout with Codex](codex.md#switch-it-on); VS Code's Codex extension has no `/hooks`, see [Codex in VS Code without the CLI](vscode.md#codex-in-vs-code-without-the-cli)), and run `loadout check`.

In VS Code, which window to open: [Recommended setups](setups.md#recommended-setups). The windows, their `VS Code (…)` rows in `loadout check` and the PATH fix `--vscode-path` are in [Use loadout with VS Code](vscode.md#windows-and-wsl).

## 3. Know which install loadout configures

A Windows-native install uses `%USERPROFILE%\.claude` (and `%USERPROFILE%\.codex` for Codex) and a WSL install uses the Linux `~/.claude` and `~/.codex` (or `$CODEX_HOME`); they do not share configuration. loadout configures the one it runs in. If you use both, you must set up both, and your personal layer in each home is separate until you sync it through git (see [Sync](../reference/personal-layer.md#sync)). For Codex, bootstrap checks which side you use first: see [Codex](#codex).

## 4. Keep repos in the Linux filesystem

Work in `~/`, for example `~/code/app`, not under `/mnt/c`. Projects on `/mnt/c` are slow, and search there can be incomplete ([troubleshooting](https://code.claude.com/docs/en/troubleshooting)).

## 5. Check that the tools are Linux binaries

WSL imports the Windows `PATH`. `claude`, `codex`, `node` or `uv` can then resolve to a Windows program under `/mnt/c`, which fails in odd ways ([troubleshoot-install](https://code.claude.com/docs/en/troubleshoot-install#npm-install-errors-in-wsl)). Check each one:

```bash
which claude codex node npm uv git
```

Each path must be inside WSL, such as `~/.local/bin/claude` or `/usr/bin/node`. A path that starts with `/mnt/c` is the Windows binary. Install the tool inside WSL yourself (for example `mise use -g node@lts`; `./bootstrap.sh --install` and `loadout update` treat a Windows tool on `PATH` as missing and install the Linux one in your home, git with your package manager; the Windows one stays as it is), and make sure its directory comes first in your `PATH`. Re-run `loadout check` afterwards.

The other fix, `appendWindowsPath = false` under `[interop]` in `/etc/wsl.conf`, stops WSL from importing the Windows `PATH` at all. It also hides Windows tools you may want, such as `code` and `explorer.exe`, and needs `wsl --shutdown` to take effect.

## 6. Install the sandbox packages (optional)

These packages are needed only if you turn on Claude Code's sandbox. The sandbox needs bubblewrap and socat:

```bash
sudo apt-get install bubblewrap socat
```

On Ubuntu 24.04 and later, bubblewrap may also need an AppArmor profile; see [sandboxing](https://code.claude.com/docs/en/sandboxing).

## Codex

Codex on Windows and Codex in WSL are two installs with two homes: `%USERPROFILE%\.codex` on Windows, `~/.codex` (or `$CODEX_HOME`) in WSL. loadout sets up one side per run: in WSL the WSL home, on Windows (`bootstrap.ps1`) the Windows home. It never writes the other side's home ([ADR 0029](../adr/0029-codex-on-windows-and-wsl.md)).

### Which side your Codex runs on

Bootstrap and `loadout check` in WSL look, read-only, at:

- `codex` on `PATH`: a Linux one, or a Windows one under `/mnt/<drive>/` (such as the npm shim in `AppData/Roaming/npm`), and `codex.exe`;
- sessions from the last 30 days in the Windows Codex home;
- the VS Code setting `chatgpt.runCodexInWindowsSubsystemForLinux` in `AppData/Roaming/Code/User/settings.json` on Windows (`true`: the extension runs Codex in WSL; `false`, or not set while the Codex extension is installed: on Windows). When you set up Codex in WSL but the extension still runs it on Windows, bootstrap offers the switch ([the next section](#when-your-only-codex-is-the-windows-one));
- `CODEX_HOME`, and whether it points into Windows.

loadout finds the Windows home through `cmd.exe` and `wslpath`; without Windows interop it tries `/mnt/c/Users/$USER`.

### When your only Codex is the Windows one

Bootstrap does not set up the WSL home for a Codex that does not read it. In a terminal it asks which side you want:

1. **Codex in WSL.** Run bootstrap with `--install` so it installs Codex in WSL (`mise use -g codex`); a Windows `codex` on `PATH` does not count. If VS Code's `settings.json` exists and the setting is not `true`, bootstrap offers to set it. On a yes it edits only that key in `settings.json` and keeps every other byte; it saves a copy first, so `loadout restore` puts it back. VS Code reloads. Without a terminal (or for an agent), `--vscode-wsl` makes the same edit without asking; without either, bootstrap prints the manual step. To do it by hand: in VS Code on Windows, open Settings, search for `chatgpt.runCodexInWindowsSubsystemForLinux` and tick it. `loadout check` shows a `VS Code` warning while the extension still runs the Windows Codex.
2. **Codex on Windows.** Run loadout's `bootstrap.ps1` in PowerShell on Windows, with the same personal layer. Bootstrap in WSL then skips its Codex step; the rest of the setup runs.

Without a terminal, or with `--yes`, pass `--codex-side wsl` or `--codex-side windows`. Without the flag the Codex step stops and prints both ways; the exit code is the same as without the step. In WSL, `loadout check` and the daily sync never set up or check the WSL home through a Windows `codex`: with only the Windows Codex, `loadout check` shows one `Codex` line that points to `bootstrap.ps1`.

Log in to Codex on the side you set up: `codex login` in WSL for Codex in WSL.

### Codex on both sides

If you use Codex on Windows too, run loadout on both sides. `loadout check` in WSL shows `Codex (Windows side)` when the Windows home has sessions from the last 30 days but no loadout block in its `AGENTS.md`.

### A CODEX_HOME that points into Windows

A WSL `CODEX_HOME` under `/mnt/<drive>/` is read by both sides, but the commands loadout writes fit only one. `loadout check` warns (`Codex home`), and bootstrap does not set it up unless you pass `--codex-side wsl`. The daily sync and `loadout configure` never write it; after `--codex-side wsl`, re-run bootstrap with that flag to refresh it. Fix: unset `CODEX_HOME` in WSL and let each side keep its own home.

### Repos on /mnt/d

A repo on a Windows drive works, but it is slower in WSL: Serena and codebase-memory index it more slowly. The links loadout makes in its skill folders are WSL links, which a Codex on Windows does not follow. `loadout init` and `loadout profile` print one note for such a repo. Keep repos in the Linux home if you can ([step 4](#4-keep-repos-in-the-linux-filesystem)).

## Problems

| Symptom | Fix |
|---|---|
| Login in WSL 2 does not open a browser or never completes | Paste the login code by hand, or set `BROWSER` to a Windows browser, for example `BROWSER="/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"`, or use `claude auth login`. See [troubleshoot-install](https://code.claude.com/docs/en/troubleshoot-install#oauth-login-fails-in-wsl2-ssh-or-containers). |
| `Exec format error` when starting `claude` | You are on WSL 1. Upgrade as in step 1. |
| The JetBrains plugin does not connect | With WSL 2 in NAT networking mode, add a Windows firewall rule or set `networkingMode=mirrored` in `.wslconfig`. See [JetBrains](https://code.claude.com/docs/en/jetbrains#wsl-configuration). |
| Searches miss files, or commands are slow | The repo is under `/mnt/c`. Move it into the Linux home. |
| `claude` or `node` behaves oddly | Step 5: it resolves to a Windows binary. |
| `Codex step skipped: …` in bootstrap | Your Codex runs on Windows, or `CODEX_HOME` points into Windows. Choose a side: [Codex](#codex). |

Other install problems: [troubleshooting](troubleshooting.md).
