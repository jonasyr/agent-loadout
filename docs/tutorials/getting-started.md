# Getting started

This tutorial takes you from nothing to a first Claude Code session with loadout. It follows one path. For details on any step, follow the links to the how-to and reference pages.

## Requirements

- Linux, macOS or Windows.
- Python 3.10 or newer. `bootstrap.sh` and `bootstrap.ps1` need it before anything else runs.
- Claude Code, git, Node.js, uv and the GitHub CLI (`gh`). `loadout bootstrap --install` installs what it can. What it cannot install is listed with instructions.
- On native Windows, Git for Windows (Git Bash). Claude Code runs hooks through it.

## Linux and macOS

Clone the kit and run bootstrap:

```bash
git clone https://github.com/jonasyr/agent-loadout ~/agent-loadout
cd ~/agent-loadout
./bootstrap.sh --install
```

Keep the clone where it is. The installed links point into it.

Go on with [What bootstrap asks](#what-bootstrap-asks).

## Windows

Choose one path first. Do not mix the two.

- **WSL 2 (recommended).** Open a WSL terminal, not PowerShell, and follow the Linux steps above inside WSL. Then read [Use loadout on Windows with WSL 2](../how-to/wsl.md) for the checks that matter there (WSL version, repo location, Windows binaries on your `PATH`, sandbox packages).
- **Native Windows.** Use PowerShell and the steps below. Native Windows needs Git for Windows.

### Native Windows

1. Install Python 3.10 or newer (for example `winget install Python.Python.3.12`) and Git for Windows. `bootstrap.ps1` stops without Python and only warns when `bash` is missing, but Claude Code hooks need Git Bash.
2. In PowerShell:

   ```powershell
   git clone https://github.com/jonasyr/agent-loadout $HOME\agent-loadout
   cd $HOME\agent-loadout
   .\bootstrap.ps1 --install
   ```

3. Bootstrap writes the secrets loader into both your Windows PowerShell and PowerShell 7 profiles. If PowerShell's execution policy is `Restricted`, profiles do not run. Bootstrap prints the command that allows them (`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`) and does not run it.
4. Without Developer Mode, Windows cannot create the links, and loadout copies files instead. Enable Developer Mode and re-run bootstrap to switch back to links. See [Troubleshooting](../how-to/troubleshooting.md).

Go on with [What bootstrap asks](#what-bootstrap-asks).

## What bootstrap asks

Bootstrap is safe to re-run. It works in steps and prints a heading for each. It asks you at most three things.

1. **Your personal layer.** Paste the git URL of your own personal repo to clone it. Leave it empty to create a starter. The starter asks four short questions about you, then the working preferences. If you already have a personal layer on this machine, bootstrap uses it and asks nothing. See [Personal layer](../reference/personal-layer.md).
2. **Preferences and add-ons.** `Customize preferences and global add-ons now? [y/N]` starts the configure wizard. You can run it later with `loadout configure`. See [Set your working preferences](../how-to/set-preferences.md).
3. **Your existing setup.** If Claude Code already has plugins, MCP servers, skills or hooks, `loadout adopt` reviews them. It offers to remove superseded or duplicate tools, to disable per-project tools globally, and to move plaintext secrets into `secrets.env`. For tools loadout does not manage, it asks whether to record them globally, put them in a personal profile, leave them, or remove them. Nothing changes without your answer. See [Handle your own tools](../how-to/your-own-tools.md).

Whatever bootstrap removes or replaces goes into a backup first. The end of the output names it and shows the undo command. See [Undo what loadout changed](../how-to/undo-and-restore.md).

Without a terminal (CI, `ssh host ./bootstrap.sh`, piped input) bootstrap skips the configure prompt and the adopt step and says so. It still links files, merges settings, applies your MCP servers and sets up plugins. Pass `--yes` to accept the safe defaults instead. The flags are in the [CLI reference](../reference/cli.md#loadout-bootstrap).

## Verify

Restart Claude Code. Then run:

```bash
loadout check
```

It is read-only. Each line is `ok`, `warn` or `FAIL`, and a problem line names the fix. If you see `loadout: command not found`, add `~/.local/bin` to your `PATH` (Windows: `%USERPROFILE%\.local\bin`) and open a new terminal. More in [Troubleshooting](../how-to/troubleshooting.md). What each check means is in the [CLI reference](../reference/cli.md#loadout-check).

## Prepare a project

In a repo, new or old:

```bash
cd my-project
loadout init
```

`loadout init` creates `AGENTS.md`, `CLAUDE.md`, a `docs/` folder and `.gitignore` entries, and suggests profiles for domain tools. It never overwrites a file. Add `--dry-run` to see the changes first. Then open Claude Code in the repo and run:

```
/loadout:onboard
```

The skill reads the project and fills in the documentation. To add a profile later, run `loadout profile <name>` (see [Profile format](../reference/profile-format.md)).

## What happens by itself

After setup you do not have to run anything to stay current.

- **At each session start** Claude Code runs a loadout hook. It shows any queued notice (for example "updates available") and starts the background job if it is due.
- **Once a day** the background job pulls the kit and your personal layer with `git pull --ff-only`, only when the checkout has no local changes. After a pull that brought commits it re-merges settings, applies your personal MCP servers and relinks skills and hook scripts.
- **Once a week** it checks tool versions. If something is outdated, the next session shows `run loadout update`. Tool binaries are never updated without your confirmation.
- **Plugins** are updated by Claude Code itself.

How this fits together is in [Architecture](../explanation/architecture.md). What runs without asking, and how to opt out, is in [Security and trust](../explanation/security-and-trust.md).

## Next

- Change preferences: [Set your working preferences](../how-to/set-preferences.md).
- Something went wrong: [Undo what loadout changed](../how-to/undo-and-restore.md).
- All commands: [CLI reference](../reference/cli.md).
