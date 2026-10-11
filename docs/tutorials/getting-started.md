# Getting started

This tutorial takes you from nothing to a first Claude Code session with loadout. It follows one path. For details on any step, follow the links to the how-to and reference pages.

## Before you start

| | Linux / WSL | macOS | Windows (experimental) |
|---|---|---|---|
| git | `sudo apt install git` (Debian/Ubuntu; other distros: their package manager) | `xcode-select --install` | `winget install --id Git.Git -e` (Git Bash runs the hooks) |
| After bootstrap | `claude` (log in), `gh auth login` | same | same |

Bootstrap installs everything else that is missing, in your home folder and without sudo: uv (which also provides Python), Claude Code, Node.js, gh and the tools in [Included tools](../reference/included-tools.md#command-line-tools). It never replaces a tool you already have. The installers run without a further prompt; see [Security and trust](../explanation/security-and-trust.md#what-runs-when-you-ask).

Optional, only if you turn on Claude Code's sandbox (Linux, WSL 2): `sudo apt-get install bubblewrap socat`.

## Step 1: Run bootstrap

On Linux, macOS and WSL 2, run the one-liner. It clones the kit into `./agent-loadout` (use `--dir PATH` after `--` to choose another folder) and runs bootstrap:

```bash
curl -fsSL https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.sh | bash -s -- --install
```

Prefer to read the code first? Clone it and run the same script:

```bash
git clone https://github.com/jonasyr/agent-loadout && cd agent-loadout && ./bootstrap.sh --install
```

Keep the clone where it is. The installed links point into it. Bootstrap adds `~/.local/bin` and the folders of the tools it installed to your shell profile (block `# loadout PATH`), so open a new terminal when it is done. It ends with the steps still open on your machine.

On Windows, use WSL 2: open a WSL terminal, not PowerShell, and follow the steps above inside WSL. Then read [Use loadout on Windows with WSL 2](../how-to/wsl.md) (WSL version, repo location, Windows binaries on your `PATH`, sandbox packages); `loadout check` warns about each of these it can see.

Go on with [What bootstrap asks](#what-bootstrap-asks).

## Experimental: native Windows

Native Windows is experimental and not recommended. Use WSL 2 if you can.

1. Install Git for Windows (`winget install --id Git.Git -e`). `bootstrap.ps1` only warns when `bash` is missing, but Claude Code hooks need Git Bash. Python is not needed: uv provides it.
2. In PowerShell, run the one-liner (it clones into `.\agent-loadout`):

   ```powershell
   & ([scriptblock]::Create((irm https://raw.githubusercontent.com/jonasyr/agent-loadout/main/bootstrap.ps1))) --install
   ```

   Or clone and run the script, bypassing the execution policy for this one command:

   ```powershell
   git clone https://github.com/jonasyr/agent-loadout $HOME\agent-loadout
   cd $HOME\agent-loadout
   powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1 --install
   ```

   If you plan to keep secrets in `secrets.env`, also run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`: `Bypass` only lets this one command run, `RemoteSigned` lets your PowerShell profiles (and with them the secrets loader) run. Why: [Troubleshooting, Windows](../how-to/troubleshooting.md#windows).
3. Bootstrap writes the secrets loader into both your Windows PowerShell and PowerShell 7 profiles, and adds the tool folders to your user PATH.
4. Bootstrap installs codebase-memory-mcp with its `install.ps1`. The optional rtk has no Windows install command; install it by hand if you want it.
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

It is read-only. Each line is `ok`, `warn` or `FAIL`, and a problem line names the fix. If you see `loadout: command not found`, open a new terminal: bootstrap added `~/.local/bin` to your profile (Windows: your user PATH). More in [Troubleshooting](../how-to/troubleshooting.md). What each check means is in the [CLI reference](../reference/cli.md#loadout-check).

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
