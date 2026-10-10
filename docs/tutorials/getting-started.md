# Getting started

This tutorial takes you from nothing to a first Claude Code session with loadout. It follows one path. For details on any step, follow the links to the how-to and reference pages.

## Requirements

- Linux, macOS or Windows.
- You need Claude Code, git, Python 3.10+, Node.js and gh; `--install` adds uv and the rest of the tools where it has an install command for your platform. What it cannot install is listed with instructions. Python must be there first: `bootstrap.sh` and `bootstrap.ps1` need it before anything else runs.
- `--install` runs the installers without a further prompt, some of them `curl … | sh` scripts. See [Security and trust](../explanation/security-and-trust.md#what-runs-when-you-ask).
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

- **WSL 2 (recommended).** Open a WSL terminal, not PowerShell, and follow the Linux steps above inside WSL. Then read [Use loadout on Windows with WSL 2](../how-to/wsl.md) for the manual checks (WSL version, repo location, Windows binaries on your `PATH`, sandbox packages).
- **Native Windows.** Use PowerShell and the steps below. Native Windows needs Git for Windows.

### Native Windows

1. Install Python 3.10 or newer (for example `winget install Python.Python.3.12`) and Git for Windows. `bootstrap.ps1` stops without Python and only warns when `bash` is missing, but Claude Code hooks need Git Bash.
2. In PowerShell:

   ```powershell
   git clone https://github.com/jonasyr/agent-loadout $HOME\agent-loadout
   cd $HOME\agent-loadout
   powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1 --install
   ```

   If you plan to keep secrets in `secrets.env`, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` first. Then this command and your profiles both run. Why: [Troubleshooting, Windows](../how-to/troubleshooting.md#windows).
3. Bootstrap writes the secrets loader into both your Windows PowerShell and PowerShell 7 profiles.
4. Install codebase-memory-mcp by hand from its release archive (the `manual` hint names it); until then `loadout check` shows FAIL and bootstrap exits with 1. It has no Windows install command.
5. Without Developer Mode, Windows cannot create the links, and loadout copies files instead. Enable Developer Mode and re-run bootstrap to switch back to links. See [Troubleshooting](../how-to/troubleshooting.md).

Go on with [What bootstrap asks](#what-bootstrap-asks).

## What bootstrap asks

Bootstrap is safe to re-run. It works in steps and prints a heading for each. It asks you at most three things.

1. **Your personal layer.** Paste the git URL of your own personal repo to clone it. Leave it empty to create a starter. The starter asks four short questions about you, then the working preferences. If you already have a personal layer on this machine, bootstrap uses it and asks nothing. See [Personal layer](../reference/personal-layer.md).
2. **Preferences and add-ons.** `Customize preferences and global add-ons now? [y/N]` starts the configure wizard. You can run it later with `loadout configure`. See [Set your working preferences](../how-to/set-preferences.md).
3. **Your existing setup.** If Claude Code already has plugins, MCP servers, skills or hooks, `loadout adopt` reviews them. It offers to remove superseded or duplicate tools, to disable per-project tools globally, and to move plaintext secrets into `secrets.env`. For tools loadout does not manage, it asks whether to record them globally, put them in a personal profile, leave them, or remove them. Nothing changes without your answer. See [Handle your own tools](../how-to/your-own-tools.md).

Items you own that bootstrap removes or replaces go into a backup first. The end of the output names it and shows the undo command. See [Undo what loadout changed](../how-to/undo-and-restore.md).

Without a terminal (CI, `ssh host ./bootstrap.sh`, piped input) bootstrap skips the configure prompt and the adopt step and says so. It still runs `--install` when given, links files, creates a starter personal layer with default preferences if none exists, merges settings, applies your MCP servers and sets up plugins. Pass `--yes` to apply adopt's default groups (remove, migrate, scope-down) plus moving plaintext secrets, without asking. The flags are in the [CLI reference](../reference/cli.md#loadout-bootstrap).

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

`loadout init` creates `AGENTS.md`, `CLAUDE.md`, a `docs/` folder and `.gitignore` entries, and suggests profiles for domain tools. It never overwrites an existing scaffold file; profiles merge into `.claude/settings.json` and `.mcp.json`. Add `--dry-run` for a preview (it does not show the settings diff). Then open Claude Code in the repo and run:

```
/loadout:onboard
```

The skill reads the project and fills in the documentation. To add a profile later, run `loadout profile <name>` (see [Profile format](../reference/profile-format.md)).

## What happens by itself

After setup you do not have to run anything to stay current.

Claude Code updates the plugins, a session hook pulls the kit and your personal layer once a day, and a weekly check tells you when tool binaries have updates (`loadout update` applies them after asking). How this works: [The daily sync](../explanation/architecture.md#the-daily-sync). What runs without asking, and how to opt out, is in [Security and trust](../explanation/security-and-trust.md).

## Next

- Change preferences: [Set your working preferences](../how-to/set-preferences.md).
- Something went wrong: [Undo what loadout changed](../how-to/undo-and-restore.md).
- All commands: [CLI reference](../reference/cli.md).
