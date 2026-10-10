# Use loadout on Windows with WSL 2

Use this page if you work on Windows. WSL 2 is the recommended setup for loadout. Native Windows is supported too: its steps are in the Windows part of the getting-started tutorial.

loadout does not detect WSL yet and `loadout check` has no WSL checks. Everything below is a manual step.

Anthropic supports both native Windows and WSL 2 for Claude Code and does not name a preferred one ([setup](https://code.claude.com/docs/en/setup.md)). loadout recommends WSL 2 for these reasons:

- **The sandbox works only on WSL 2.** It uses bubblewrap ([sandboxing](https://code.claude.com/docs/en/sandboxing.md)).
- **You get the Linux toolchain.** The install commands are the same as on Linux.
- **No Git Bash.** On native Windows, Claude Code runs hooks through Git Bash, so hook script paths need forward slashes or quotes. In WSL they are normal Linux paths.

## 1. Use WSL 2, not WSL 1

In PowerShell, check the version of your distribution and upgrade it:

```powershell
wsl -l -v
wsl --set-version <distro> 2
```

WSL 1 has a regression where Claude Code's native binary fails with `Exec format error` ([troubleshoot-install](https://code.claude.com/docs/en/troubleshoot-install.md)).

## 2. Install loadout inside WSL

Open the WSL terminal, not PowerShell, and follow the Linux steps of the tutorial:

```bash
git clone https://github.com/jonasyr/agent-loadout ~/agent-loadout
cd ~/agent-loadout
./bootstrap.sh --install
```

Keep the clone in the Linux home, as above: the installed links point into it. Then restart Claude Code and run `loadout check`.

## 3. Keep one Claude Code install

Claude Code reads its config from the Linux home (`~/.claude`). A Windows-native install uses `%USERPROFILE%\.claude` and does not share config with a WSL install. The Claude Code docs advise keeping only one of the two ([setup](https://code.claude.com/docs/en/setup.md)). loadout configures the one it runs in. If you use both, you must set up both, and your personal layer in each home is separate until you sync it through git (see [Sync](../reference/personal-layer.md#sync)).

## 4. Keep repos in the Linux filesystem

Work in `~/`, for example `~/code/app`, not under `/mnt/c`. Projects on `/mnt/c` are slow, and search there can be incomplete ([troubleshooting](https://code.claude.com/docs/en/troubleshooting.md)).

## 5. Check that the tools are Linux binaries

WSL imports the Windows `PATH`. `claude`, `node` or `uv` can then resolve to a Windows program under `/mnt/c`, which fails in odd ways. Check each one:

```bash
which claude node uv
```

Each path must be inside WSL, such as `~/.local/bin/claude` or `/usr/bin/node`. A path that starts with `/mnt/c` is the Windows binary. Install the tool inside WSL (`./bootstrap.sh --install` does it for what it can), and make sure its directory comes first in your `PATH`. Re-run `loadout check` afterwards.

## 6. Install the sandbox packages

Sandboxing needs bubblewrap and socat:

```bash
sudo apt-get install bubblewrap socat
```

On Ubuntu 24.04 and later, bubblewrap may also need an AppArmor profile; see [sandboxing](https://code.claude.com/docs/en/sandboxing.md).

## Problems

| Symptom | Fix |
|---|---|
| Login in WSL 2 does not open a browser or never completes | Paste the login code by hand, or set `BROWSER` to a Windows browser, for example `BROWSER="/mnt/c/Program Files/Google/Chrome/Application/chrome.exe"`, or use `claude auth login`. See [troubleshooting](https://code.claude.com/docs/en/troubleshooting.md). |
| `Exec format error` when starting `claude` | You are on WSL 1. Upgrade as in step 1. |
| The JetBrains plugin does not connect | With WSL 2 in NAT networking mode, add a Windows firewall rule or set `networkingMode=mirrored` in `.wslconfig`. See [troubleshooting](https://code.claude.com/docs/en/troubleshooting.md). |
| Searches miss files, or commands are slow | The repo is under `/mnt/c`. Move it into the Linux home. |
| `claude` or `node` behaves oddly | Step 5: it resolves to a Windows binary. |

Other install problems: [troubleshooting](troubleshooting.md).
